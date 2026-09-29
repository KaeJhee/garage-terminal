#!/usr/bin/env python3
"""
report.py
=========
Runs after generate_history.py in the weekly job. It only reads:
scraper/scraped_prices.json (the scrape and its per-source diagnostics),
scraper/run_results.json (generate_history's price decisions and anchor
audit), frontend/cars.config.js, frontend/price_history.json and the config
checker's warnings. It writes no file in the repo.

  1. A per-car table in the job summary ($GITHUB_STEP_SUMMARY, else stdout).
  2. With --issue: one GitHub issue titled 'Cars that need a look', managed
     with the gh command and the workflow's built-in token. It is opened, or
     reopened, when a car needs a look; it gets a comment only when the list
     of cars and reasons changes (the comment is what emails the owner); it
     is closed when the list is empty. If the owner closes it by hand, it
     stays closed until the list changes.

     The issue body remembers two things in HTML comments: the list the
     owner was last told about, and the cars whose search failed this run.
     The comment that emails the owner is written before the body, so a gh
     failure between the two repeats the email next run instead of losing it.

Status:  PRICED  enough recent sales set the price
         THIN    some sales, fewer than needed; the price holds
         NO_DATA no sale counted; the price holds
         MANUAL  Chinese cars, priced by hand (not a problem)

Reason codes. Those in NEEDS_A_LOOK put the car in the issue:
  NO_BAT_SEARCH  no Bring a Trailer search in bat_url or scrape_extras
  SEARCH_404     Bring a Trailer answered 404 (its answer to no results)
  FETCH_FAILED   Bring a Trailer did not answer (network error or 5xx). A
                 first failure is listed for information only; a car goes in
                 the issue when its search also failed on the previous run
  NO_CARDS       the page loaded but showed no listings (with the final URL)
  ALL_REJECTED   listings were found and none counted (with counts)
  BAND_REFUSED   the sales median is outside the car's price band, so the
                 price was kept (with a suggested band: p10-p90 of the car's
                 listed sales in the last two years)
  ANCHOR_OFF     avg_price disagrees with its own band or its recent sales
  THIN           fewer recent sales than needed (with the days until the
                 oldest one leaves the two-year window)
  MANUAL         priced by hand

Usage:
    python scraper/report.py                 # table only
    python scraper/report.py --issue         # table, then update the issue (needs GH_TOKEN)
"""

import argparse, json, os, re, statistics, subprocess, sys
from datetime import date, timedelta
from pathlib import Path

import scrape_prices as sp
import generate_history as gen

ROOT       = Path(__file__).parent.parent
VALIDATOR  = ROOT / "tests" / "validate_config.js"
TITLE      = "Cars that need a look"
MARKER     = "cars-that-need-a-look"
FETCH_MARKER = "search-failed-last-run"
NEEDS_A_LOOK = ("NO_BAT_SEARCH", "SEARCH_404", "FETCH_FAILED", "NO_CARDS", "ALL_REJECTED", "BAND_REFUSED", "ANCHOR_OFF")
STATUS_ORDER = ("NO_DATA", "THIN", "PRICED", "MANUAL")

WHAT_TO_DO = {
    "NO_BAT_SEARCH": "Put a Bring a Trailer search in bat_url, for example https://bringatrailer.com/search/?s=make+model. "
                     "If bat_url has to stay a link to another site, add a scrape_extras search by hand instead (see the guide).",
    "SEARCH_404":    "Open the search link. If Bring a Trailer shows no results, try plainer words (a model name rather than "
                     "a chassis code) and put the new search link in bat_url.",
    "FETCH_FAILED":  "Usually nothing: this is often a short outage. If it shows up again next week, open the search link "
                     "and check that it still works.",
    "NO_CARDS":      "Open the link. If it shows no listings for this car, change bat_url to a search that does.",
    "ALL_REJECTED":  "",   # worded from the reject counts, per car
    "BAND_REFUSED":  "",   # the suggestion is per car
    "ANCHOR_OFF":    "Check avg_price, low_price and high_price against the sales on the search link, and correct the "
                     "one that is wrong.",
}
REJECT_WORDS = {"unsold": "did not sell", "model year": "were other model years or parts",
                "title filter": "did not match the title words",
                "implausible": "had a price too far from this car's price to be the same car"}


def money(n):
    return f"${n:,.0f}"


def load_json(path):
    return json.loads(path.read_text()) if path.exists() else None


# ---------------------------------------------------------------------------
# One row per car
# ---------------------------------------------------------------------------

def suggest_band(store_sales, today):
    """p10 and p90 of the car's stored sales with a listing ID from the last two years,
    rounded out to the nearest $1,000. None with fewer than 3 such sales."""
    cutoff = (today - timedelta(days=sp.RECENT_DAYS)).isoformat()
    prices = [float(s["price"]) for s in store_sales
              if s.get("listing_id") and s.get("venue") not in gen.NOT_SALES and s.get("date", "") >= cutoff]
    if len(prices) < 3:
        return None
    q = statistics.quantiles(prices, n=10, method="inclusive")
    lo, hi = int(q[0] // 1000 * 1000), int(-(-q[-1] // 1000) * 1000)
    return lo, max(hi, lo + 1000), len(prices)


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def rejects_text(counts, years=None):
    words = dict(REJECT_WORDS)
    if years:
        words["model year"] += f" (this car's years: {years})"
    return ", ".join(f"{v} {words[k]}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v)


def all_rejected_advice(counts):
    """What to do for ALL_REJECTED, from why the listings were turned away."""
    look = "Open the search link and compare the listings with the car."
    other = "If they are other cars, change bat_url."
    top = max(counts, key=lambda k: counts[k]) if any(counts.values()) else None
    if top == "implausible":
        return (f"{look} If they are this car, its price is probably wrong: set avg_price near those sale prices, "
                f"with low_price and high_price around it. {other}")
    if top in ("model year", "title filter"):
        return f"{look} If they are this car, widen years or loosen the title words. {other}"
    if top == "unsold":
        return f"{look} Unsold auctions never count, so if they are this car there is nothing to fix yet. {other}"
    return f"{look} {other}"


def fetch_problem(car, fetched):
    """The reason a car with no counted sale got none, from its per-source diagnostics."""
    with_cards = [d for d in fetched if d.get("cards") or d.get("items")]
    if with_cards:
        counts = {}
        for d in with_cards:
            for k, v in (d.get("rejects") or {}).items():
                counts[k] = counts.get(k, 0) + v
        seen = sum(d.get("cards", 0) + d.get("items", 0) for d in with_cards)
        short = ", ".join(f"{k} {v}" for k, v in counts.items() if v) or "no priced listings"
        return ("ALL_REJECTED", short,
                f"Bring a Trailer showed {seen} listings for this car, but none counted as a sale: "
                f"{rejects_text(counts, car.get('years')) or 'none had a price'}.")
    loaded = [d for d in fetched if d.get("status") == 200]
    if loaded:
        url = loaded[0].get("final_url") or loaded[0]["url"]
        return ("NO_CARDS", f"no listings at {url}", f"The search opened {url}, which showed no listings.")
    failed = [d for d in fetched if d.get("status") != 404]
    if failed:
        st = failed[0].get("status") or "no answer"
        return ("FETCH_FAILED", f"HTTP {st}", f"Bring a Trailer did not answer this car's search (error: {st}).")
    return ("SEARCH_404", "404: " + ", ".join(d["url"] for d in fetched),
            "Bring a Trailer answered 'no results' (404) for this car's search.")


def build_row(car, scraped, decision, anchors, store_sales, today):
    cid = car["id"]
    row = {"id": cid, "label": car.get("label") or cid, "codes": [], "short": [], "why": {}, "fix": {}, "search": None}
    avg = car.get("avg_price") or 0
    if car.get("category") == "Chinese":
        row.update(status="MANUAL", price=f"{money(avg)} (by hand)")
        row["codes"].append("MANUAL"); row["short"].append("priced by hand")
    elif scraped is None:
        row.update(status="NO_DATA", price=f"{money(avg)} (kept)")
        row["short"].append("not in this scrape")
    else:
        conf = scraped.get("confidence")
        row["status"] = {"scraped": "PRICED", "thin": "THIN"}.get(conf, "NO_DATA")
        sources = scraped.get("sources") or []
        fetched = [d for d in sources if "skipped" not in d]
        row["search"] = next((d["url"] for d in fetched), car.get("bat_url"))
        if not fetched:
            other = f" Its Listings link (bat_url) is {car['bat_url']}, which is not Bring a Trailer." \
                if car.get("bat_url") and not sp.is_bat_url(car["bat_url"]) else ""
            row["codes"].append("NO_BAT_SEARCH"); row["short"].append("no Bring a Trailer search")
            row["why"]["NO_BAT_SEARCH"] = "This car has no Bring a Trailer search, so nothing was looked up." + other
        elif conf == "fallback":
            code, short, why = fetch_problem(car, fetched)
            row["codes"].append(code); row["short"].append(short); row["why"][code] = why
            if code == "ALL_REJECTED":
                counts = {}
                for d in fetched:
                    for k, v in (d.get("rejects") or {}).items():
                        counts[k] = counts.get(k, 0) + v
                row["fix"]["ALL_REJECTED"] = all_rejected_advice(counts)
        else:
            bad = [d for d in fetched if d.get("status") != 200]
            if bad:   # another search worked, so this is a note, not a problem
                row["short"].append(f"{len(bad)} of {len(fetched)} searches failed ({', '.join(str(d.get('status')) for d in bad)})")
        if conf == "thin":
            cutoff = (today - timedelta(days=sp.RECENT_DAYS)).isoformat()
            recent = sorted(s["date"] for s in scraped.get("sales", []) if s.get("date") and s["date"] >= cutoff)
            if recent:
                left = sp.RECENT_DAYS - (today - date.fromisoformat(recent[0])).days
                txt = f"{len(recent)} of {sp.MIN_SALES_FOR_PRICE} sales needed in two years; the oldest leaves in {left} days"
            else:
                txt = f"no sale in the last two years; {plural(len(scraped.get('sales', [])), 'older sale', 'older sales')}"
            row["codes"].append("THIN"); row["short"].append(txt)
        d = decision or {}
        if d.get("result") == "applied":
            row["price"] = f"{money(d['old'])} → {money(d['new'])}"
        elif d.get("result") == "unchanged":
            row["price"] = f"{money(d['new'])} (same)"
        else:
            row["price"] = f"{money(d.get('old', avg))} (kept)"
        if d.get("result") == "refused":
            band = suggest_band(store_sales, today)
            row["codes"].append("BAND_REFUSED")
            why = (f"Recent sales put this car at {money(d['new'])}, outside what its price band allows "
                   f"({money(d['allowed'][0])} to {money(d['allowed'][1])}, from low_price {money(d['low_price'])} and "
                   f"high_price {money(d['high_price'])}). The price stayed at {money(d['old'])}.")
            if band:
                row["short"].append(f"median {money(d['new'])} outside {money(d['allowed'][0])}-{money(d['allowed'][1])}; "
                                    f"suggested band {money(band[0])}-{money(band[1])}")
                row["fix"]["BAND_REFUSED"] = (f"If these sales are the right car, set low_price to {money(band[0])} and high_price to "
                              f"{money(band[1])} (the middle 80% of its {band[2]} listed sales in the last two years). "
                              "If they are a different car, fix the search instead.")
            else:
                row["short"].append(f"median {money(d['new'])} outside {money(d['allowed'][0])}-{money(d['allowed'][1])}")
                row["fix"]["BAND_REFUSED"] = "Check the sales on the search link. If they are the right car, widen low_price and high_price; if not, fix the search."
            row["why"]["BAND_REFUSED"] = why
    mine = [a for a in anchors if a["id"] == cid]
    if mine:
        row["codes"].append("ANCHOR_OFF")
        row["short"].append("; ".join(a["message"] for a in mine))
        row["why"]["ANCHOR_OFF"] = " ".join(anchor_text(a) for a in mine)
    return row


def anchor_text(a):
    if a["check"] == "below band":
        return f"avg_price {money(a['avg'])} is far below low_price {money(a['low'])}."
    if a["check"] == "above band":
        return f"avg_price {money(a['avg'])} is far above high_price {money(a['high'])}."
    return (f"The {a['n']} sales with a listing in the last two years have a median of {money(a['median'])}, "
            f"more than 3 times away from avg_price {money(a['avg'])}. Either avg_price or the search is wrong.")


def needs_a_look(row):
    return [c for c in row["codes"] if c in NEEDS_A_LOOK and not (c == "FETCH_FAILED" and row.get("first_failure"))]


def hold_first_fetch_failures(rows, failed_before):
    """A search that fails once is usually a short outage: it goes in the issue only when the same car's
    search also failed on the previous run. failed_before is None when there is no issue to remember
    the previous run in (then every failure counts, so a lasting one is never missed)."""
    for r in rows:
        if "FETCH_FAILED" in r["codes"]:
            r["first_failure"] = failed_before is not None and r["id"] not in failed_before


def fetch_failed(rows):
    return " ".join(sorted(r["id"] for r in rows if "FETCH_FAILED" in r["codes"]))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def run_link():
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None


def summary_markdown(rows, when, warnings, note=None):
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("PRICED", "THIN", "NO_DATA", "MANUAL")}
    flagged = [r for r in rows if needs_a_look(r)]
    changed = sum(1 for r in rows if "→" in r["price"])
    out = ["## Price run report", "",
           f"Scrape of {when}: " + ", ".join(f"{v} {k}" for k, v in counts.items()) + f". {plural(changed, 'price', 'prices')} changed.", ""]
    if note:
        out += [f"**{note}**", ""]
    out += [f"**{plural(len(flagged), 'car needs', 'cars need')} a look:** " + ", ".join(f"{r['id']} ({', '.join(needs_a_look(r))})" for r in flagged)
            if flagged else "**No car needs a look.**", ""]
    out += ["| Car | Status | Price | Reason | Details |", "|---|---|---|---|---|"]
    order = sorted(rows, key=lambda r: (not needs_a_look(r), STATUS_ORDER.index(r["status"])))
    for r in order:
        cell = lambda s: s.replace("|", "\\|")
        short = r["short"] + (["first failure, listed only if it fails again next run"] if r.get("first_failure") else [])
        out.append(f"| {r['id']} | {r['status']} | {r['price']} | {', '.join(r['codes']) or '-'} | {cell('; '.join(short)) or '-'} |")
    if warnings:
        out += ["", f"<details><summary>Config checks: {len(warnings)} warning(s)</summary>", ""]
        out += [f"- {w}" for w in warnings] + ["", "</details>"]
    return "\n".join(out) + "\n"


def signature(rows):
    """The list the owner is told about, sorted so that the order of cars in the config does not matter."""
    return " ".join(sorted(f"{r['id']}:{c}" for r in rows for c in needs_a_look(r)))


def markers(body):
    """(the list last told to the owner, the cars whose search failed on that run) from an issue body."""
    body = body or ""
    m = re.search(rf"<!-- {MARKER}: ?(.*?) ?-->", body)
    f = re.search(rf"<!-- {FETCH_MARKER}: ?(.*?) ?-->", body)
    return (m.group(1).strip() if m else ""), set(f.group(1).split()) if f else set()


def marker_lines(sig, failed):
    return [f"<!-- {MARKER}: {sig} -->", f"<!-- {FETCH_MARKER}: {failed} -->"]


def issue_body(rows, when, repo):
    flagged = [r for r in rows if needs_a_look(r)]
    link = run_link()
    out = marker_lines(signature(rows), fetch_failed(rows)) + [
           f"The price run found {plural(len(flagged), 'car that needs', 'cars that need')} a look. This issue updates itself after every "
           "run, and closes itself when nothing needs a look.", "",
           f"Run of {when}" + (f" ([details]({link}))." if link else "."), ""]
    for r in flagged:
        out += [f"### {r['id']}: {r['label']}", ""]
        for c in needs_a_look(r):
            out += [f"**{c}.** {r['why'].get(c, '')}", ""]
            fix = r["fix"].get(c) or WHAT_TO_DO[c]
            out += [f"What to do: {fix}", ""]
        if r.get("search"):
            out += [f"Search used: {r['search']}", ""]
    thin = [r for r in rows if "THIN" in r["codes"] and not needs_a_look(r)]
    if thin:
        out += ["Also thin this run (few recent sales, so the price holds; nothing to do):", ""]
        out += [f"- {r['id']}: {r['short'][-1]}" for r in thin] + [""]
    once = [r for r in rows if r.get("first_failure")]
    if once:
        out += ["Bring a Trailer did not answer these searches this run. Usually a short outage, so nothing to do; "
                "a car moves up into the list if its search fails again next run:", ""]
        out += [f"- {r['id']}" for r in once] + [""]
    out += ["---", "",
            "How to fix a car: on the dashboard click CONFIG, click edit on the car, change the field, click Save Car, "
            f"then Export cars.config.js. Upload that file at https://github.com/{repo}/upload/main/frontend and click "
            "Commit changes. The price run starts by itself, and this issue updates when it finishes.", "",
            f"What each reason means: https://github.com/{repo}/blob/main/HOW_TO_ADD_A_CAR.md#cars-that-need-a-look"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# The issue, through gh
# ---------------------------------------------------------------------------

def gh_cmd(args, body=None):
    r = subprocess.run(["gh", *args], input=body, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"gh {args[0]} {args[1]} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def find_issue(repo):
    """The bot's own 'Cars that need a look' issue: open first, then the newest. An issue someone
    else opened with the same title is ignored."""
    found = json.loads(gh_cmd(["issue", "list", "--repo", repo, "--state", "all", "--limit", "500",
                               "--json", "number,title,state,body,author"]) or "[]")
    mine = [i for i in found if i.get("title") == TITLE and
            ((i.get("author") or {}).get("is_bot") or "github-actions" in (i.get("author") or {}).get("login", ""))]
    mine.sort(key=lambda i: (i.get("state", "").upper() == "OPEN", i["number"]), reverse=True)
    return mine[0] if mine else None


def quiet_body(repo, failed):
    """The body while nothing needs a look. It has no date, so a clean run leaves it alone."""
    return "\n".join(marker_lines("", failed) + [
        "Nothing needs a look right now. This issue reopens by itself, with a comment, when a car needs a look.", "",
        f"What each reason means: https://github.com/{repo}/blob/main/HOW_TO_ADD_A_CAR.md#cars-that-need-a-look"]) + "\n"


_LOOKUP = object()


def sync_issue(rows, when, repo, issue=_LOOKUP):
    """Create, reopen, comment on, or close the issue. Returns what it did.

    The marker in the body is the list the owner was last told about. Each write that emails the
    owner (create, comment) happens before the body records the new list, so a gh failure in
    between means a repeated email next run, never a lost one. main() passes the issue it already
    looked up; otherwise it is looked up here and first fetch failures are held back."""
    if issue is _LOOKUP:
        issue = find_issue(repo)
        hold_first_fetch_failures(rows, markers(issue["body"])[1] if issue else None)
    now = signature(rows)
    failed = fetch_failed(rows)
    link = run_link()
    run = f"the run of {when}" + (f" ([details]({link}))" if link else "")
    if not issue:
        if not now:
            return "nothing to report"
        out = gh_cmd(["issue", "create", "--repo", repo, "--title", TITLE, "--body-file", "-"], issue_body(rows, when, repo))
        return f"opened {out.strip()}"
    num = str(issue["number"])
    is_open = issue.get("state", "").upper() == "OPEN"
    before, failed_before = markers(issue.get("body"))
    did = []
    if not now:
        if is_open:
            gh_cmd(["issue", "close", num, "--repo", repo]); did.append(f"closed #{num}")
        if before:      # the owner was told about a list, so tell them it is clear
            gh_cmd(["issue", "comment", num, "--repo", repo, "--body-file", "-"],
                   f"Nothing needs a look after {run}. This issue is closed and reopens by itself if a car needs a look again.\n")
            did = did or [f"commented on closed #{num}"]
        body = quiet_body(repo, failed)
        if (issue.get("body") or "") != body and (before or failed != " ".join(sorted(failed_before))):
            gh_cmd(["issue", "edit", num, "--repo", repo, "--body-file", "-"], body)
            did = did or [f"#{num} updated"]
        return did[0] if did else "nothing to report"
    body = issue_body(rows, when, repo)
    old, new = set(before.split()), set(now.split())
    if old == new:
        if not is_open:
            # Closed by hand with this same list: it stays closed, and only the failed searches are remembered
            if set(failed.split()) != failed_before:
                gh_cmd(["issue", "edit", num, "--repo", repo, "--body-file", "-"], body)
            return f"#{num} unchanged (closed by hand, stays closed until the list changes)"
        if (issue.get("body") or "") != body:
            gh_cmd(["issue", "edit", num, "--repo", repo, "--body-file", "-"], body)
        return f"#{num} unchanged"
    if not is_open:
        gh_cmd(["issue", "reopen", num, "--repo", repo])
    lines = [f"The list changed after {run}."]
    added = sorted(new - old)
    gone = sorted(old - new)
    if added:
        lines.append("New: " + ", ".join(x.replace(":", " (") + ")" for x in added) + ".")
    if gone:
        lines.append("Fixed: " + ", ".join(x.replace(":", " (") + ")" for x in gone) + ".")
    lines.append("The issue description above has the full list and what to do.")
    gh_cmd(["issue", "comment", num, "--repo", repo, "--body-file", "-"], "\n\n".join(lines) + "\n")
    gh_cmd(["issue", "edit", num, "--repo", repo, "--body-file", "-"], body)
    return f"commented on #{num}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def config_warnings():
    try:
        r = subprocess.run(["node", str(VALIDATOR)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.startswith(("WARN", "ERROR"))]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Per-car report and the 'Cars that need a look' issue")
    ap.add_argument("--issue", action="store_true", help="also update the GitHub issue (needs gh and GH_TOKEN)")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"), help="owner/name (default: $GITHUB_REPOSITORY)")
    args = ap.parse_args(argv)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    emit = lambda text: (open(summary_path, "a").write(text) if summary_path else None, print(text))

    scrape = load_json(gen.SCRAPED_PATH)
    if not scrape:
        emit("## Price run report\n\nNo scrape results this run, so there is nothing to report. The issue was not changed.\n")
        return
    results = load_json(gen.RESULTS_PATH)
    note = None
    if not results or results.get("scraped_at") != scrape.get("scraped_at"):
        results = {"prices": {}, "anchor_audit": []}
        note = ("run_results.json is missing or belongs to another scrape, so band refusals and the anchor audit "
                "are not shown, and the issue was not changed.")
    when = (scrape.get("scraped_at") or "")[:16].replace("T", " ") + " UTC"
    today = date.fromisoformat(scrape["scraped_at"][:10]) if scrape.get("scraped_at") else date.today()
    store = load_json(gen.PRICE_HISTORY_PATH) or {}
    rows = [build_row(car, scrape.get("prices", {}).get(car["id"]), results["prices"].get(car["id"]),
                      results["anchor_audit"], store.get(car["id"], {}).get("sales", []), today)
            for car in sp.load_cars_from_config()]
    issue = None
    if args.issue and not note:
        if not args.repo:
            raise SystemExit("--issue needs --repo or GITHUB_REPOSITORY")
        issue = find_issue(args.repo)     # it remembers which searches failed on the previous run
        hold_first_fetch_failures(rows, markers(issue["body"])[1] if issue else None)
    emit(summary_markdown(rows, when, config_warnings(), note))
    if args.issue:
        if note:
            print("Issue not changed: " + note)
            return
        print("Issue: " + sync_issue(rows, when[:10], args.repo, issue))


if __name__ == "__main__":
    main()
