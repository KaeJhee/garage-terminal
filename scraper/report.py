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
     is closed when the list is empty.

Status:  PRICED  enough recent sales set the price
         THIN    some sales, fewer than needed; the price holds
         NO_DATA no sale counted; the price holds
         MANUAL  Chinese cars, priced by hand (not a problem)

Reason codes. Those in NEEDS_A_LOOK put the car in the issue:
  NO_BAT_SEARCH  no Bring a Trailer search in bat_url or scrape_extras
  SEARCH_404     Bring a Trailer answered 404 (its answer to no results)
  FETCH_FAILED   Bring a Trailer did not answer (network error or 5xx)
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
    "ALL_REJECTED":  "Open the search link and compare the listings with the car. If they are this car, widen years or "
                     "loosen the title words. If they are other cars, change bat_url.",
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
    row = {"id": cid, "label": car.get("label") or cid, "codes": [], "short": [], "why": {}, "search": None}
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
                row["fix"] = (f"If these sales are the right car, set low_price to {money(band[0])} and high_price to "
                              f"{money(band[1])} (the middle 80% of its {band[2]} listed sales in the last two years). "
                              "If they are a different car, fix the search instead.")
            else:
                row["short"].append(f"median {money(d['new'])} outside {money(d['allowed'][0])}-{money(d['allowed'][1])}")
                row["fix"] = "Check the sales on the search link. If they are the right car, widen low_price and high_price; if not, fix the search."
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
    return [c for c in row["codes"] if c in NEEDS_A_LOOK]


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
        out.append(f"| {r['id']} | {r['status']} | {r['price']} | {', '.join(r['codes']) or '-'} | {cell('; '.join(r['short'])) or '-'} |")
    if warnings:
        out += ["", f"<details><summary>Config checks: {len(warnings)} warning(s)</summary>", ""]
        out += [f"- {w}" for w in warnings] + ["", "</details>"]
    return "\n".join(out) + "\n"


def signature(rows):
    return " ".join(f"{r['id']}:{c}" for r in rows for c in needs_a_look(r))


def issue_body(rows, when, repo):
    flagged = [r for r in rows if needs_a_look(r)]
    link = run_link()
    out = [f"<!-- {MARKER}: {signature(rows)} -->",
           f"The price run found {plural(len(flagged), 'car that needs', 'cars that need')} a look. This issue updates itself after every "
           "run, and closes itself when nothing needs a look.", "",
           f"Run of {when}" + (f" ([details]({link}))." if link else "."), ""]
    for r in flagged:
        out += [f"### {r['id']}: {r['label']}", ""]
        for c in needs_a_look(r):
            out += [f"**{c}.** {r['why'].get(c, '')}", ""]
            fix = r.get("fix") if c == "BAND_REFUSED" else WHAT_TO_DO[c]
            out += [f"What to do: {fix}", ""]
        if r.get("search"):
            out += [f"Search used: {r['search']}", ""]
    thin = [r for r in rows if "THIN" in r["codes"] and not needs_a_look(r)]
    if thin:
        out += ["Also thin this run (few recent sales, so the price holds; nothing to do):", ""]
        out += [f"- {r['id']}: {r['short'][-1]}" for r in thin] + [""]
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


def sync_issue(rows, when, repo):
    """Create, reopen, comment on, or close the issue. Returns what it did."""
    issue = find_issue(repo)
    now = signature(rows)
    link = run_link()
    run = f"the run of {when}" + (f" ([details]({link}))" if link else "")
    if not now:
        if issue and issue.get("state", "").upper() == "OPEN":
            gh_cmd(["issue", "comment", str(issue["number"]), "--repo", repo, "--body-file", "-"],
                   f"Nothing needs a look after {run}. Closing; this issue reopens by itself if a car needs a look again.\n")
            gh_cmd(["issue", "close", str(issue["number"]), "--repo", repo])
            return f"closed #{issue['number']}"
        return "nothing to report"
    body = issue_body(rows, when, repo)
    if not issue:
        out = gh_cmd(["issue", "create", "--repo", repo, "--title", TITLE, "--body-file", "-"], body)
        return f"opened {out.strip()}"
    num = str(issue["number"])
    m = re.search(rf"<!-- {MARKER}: (.*?) -->", issue.get("body") or "")
    before = m.group(1) if m and issue.get("state", "").upper() == "OPEN" else ""
    if (issue.get("body") or "") != body:
        gh_cmd(["issue", "edit", num, "--repo", repo, "--body-file", "-"], body)
    if issue.get("state", "").upper() != "OPEN":
        gh_cmd(["issue", "reopen", num, "--repo", repo])
    if before == now:
        return f"#{num} unchanged"
    old, new = set(before.split()), set(now.split())
    lines = [f"The list changed after {run}."]
    added = sorted(new - old)
    gone = sorted(old - new)
    if added:
        lines.append("New: " + ", ".join(x.replace(":", " (") + ")" for x in added) + ".")
    if gone:
        lines.append("Fixed: " + ", ".join(x.replace(":", " (") + ")" for x in gone) + ".")
    lines.append("The issue description above has the full list and what to do.")
    gh_cmd(["issue", "comment", num, "--repo", repo, "--body-file", "-"], "\n\n".join(lines) + "\n")
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
    emit(summary_markdown(rows, when, config_warnings(), note))
    if args.issue:
        if note:
            print("Issue not changed: " + note)
            return
        if not args.repo:
            raise SystemExit("--issue needs --repo or GITHUB_REPOSITORY")
        print("Issue: " + sync_issue(rows, when[:10], args.repo))


if __name__ == "__main__":
    main()
