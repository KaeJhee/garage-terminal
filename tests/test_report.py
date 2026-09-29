"""Checks for scraper/report.py: reason codes, suggested bands, and the issue flow against a fake gh.
Run: python tests/test_report.py"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import generate_history as gen    # noqa: E402
import report                     # noqa: E402
import scrape_prices as sp        # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TODAY = date(2026, 9, 28)
SECRET = "ghs_THISMUSTNEVERAPPEAR0123456789"


def car(cid, **kw):
    return {"id": cid, "label": "Test " + cid, "category": "JDM", "bat_url": f"https://bringatrailer.com/search/?s={cid}",
            "avg_price": 100000, "low_price": 80000, "high_price": 130000, "years": "1990-1999", **kw}


def scraped(conf, sources, sales=()):
    return {"confidence": conf, "sources": sources, "sales": list(sales), "rejected": []}


def src(status=200, cards=0, items=0, rejects=None, final=None):
    return {"type": "bat_search", "url": "https://bringatrailer.com/search/?s=x", "status": status,
            "final_url": final or "https://bringatrailer.com/search/?s=x", "cards": cards, "items": items,
            "rejects": rejects or {"unsold": 0, "model year": 0, "title filter": 0, "implausible": 0}}


def row(c, s, decision=None, anchors=(), store=()):
    return report.build_row(c, s, decision, list(anchors), list(store), TODAY)


def test_reason_codes():
    r = row(car("nio", category="Chinese"), scraped("fallback", []))
    assert (r["status"], r["codes"], report.needs_a_look(r)) == ("MANUAL", ["MANUAL"], [])
    r = row(car("r35", bat_url="https://www.cars.com/shopping/nissan-gt_r/"),
            scraped("fallback", [{"type": "bat_search", "url": "https://www.cars.com/x", "skipped": "not a Bring a Trailer URL"}]))
    assert (r["status"], r["codes"]) == ("NO_DATA", ["NO_BAT_SEARCH"]) and "cars.com" in r["why"]["NO_BAT_SEARCH"]
    assert row(car("nsx"), scraped("fallback", [src(404)]))["codes"] == ["SEARCH_404"]
    r = row(car("dn"), scraped("fallback", [src(503)]))
    assert r["codes"] == ["FETCH_FAILED"] and "503" in r["short"][0]
    assert row(car("dn2"), scraped("fallback", [src(None)]))["codes"] == ["FETCH_FAILED"]
    r = row(car("fd"), scraped("fallback", [src(200, final="https://bringatrailer.com/mazda/rx-7-fd/")]))
    assert r["codes"] == ["NO_CARDS"] and "https://bringatrailer.com/mazda/rx-7-fd/" in r["short"][0]
    r = row(car("nsxr"), scraped("fallback", [src(200, cards=23, rejects={"unsold": 3, "model year": 14, "title filter": 0, "implausible": 6})]))
    assert r["codes"] == ["ALL_REJECTED"] and r["short"] == ["unsold 3, model year 14, implausible 6"], r
    assert "23 listings" in r["why"]["ALL_REJECTED"] and "14 were other model years or parts (this car's years: 1990-1999)" in r["why"]["ALL_REJECTED"]
    # a 404 on one search and cards on another: the cards explain it
    assert row(car("mix"), scraped("fallback", [src(404), src(200, cards=5, rejects={"unsold": 5})]))["codes"] == ["ALL_REJECTED"]
    # thin: days until the oldest recent sale leaves the two-year window (730 - 635 = 95)
    r = row(car("r33"), scraped("thin", [src(200, cards=4)], [{"date": "2025-01-01", "price": 1}, {"date": "2026-02-01", "price": 1}]))
    assert (r["status"], r["codes"], report.needs_a_look(r)) == ("THIN", ["THIN"], [])
    assert r["short"] == ["2 of 3 sales needed in two years; the oldest leaves in 95 days"], r["short"]
    r = row(car("ok"), scraped("scraped", [src(200, cards=20), src(404)]), {"result": "applied", "old": 95000, "new": 103469})
    assert (r["status"], r["codes"], r["price"]) == ("PRICED", [], "$95,000 → $103,469") and "1 of 2 searches failed" in r["short"][0]
    assert row(car("same"), scraped("scraped", [src(200, cards=9)]), {"result": "unchanged", "old": 5, "new": 5})["price"] == "$5 (same)"


def test_band_refused_suggests_a_band():
    store = [{"date": "2026-0%d-01" % m, "price": p, "venue": "bat", "listing_id": str(p)}
             for m, p in zip(range(1, 10), (21000, 24000, 25500, 26000, 27000, 28000, 30500, 33000, 41000))]
    store += [{"date": "2026-01-01", "price": 900000, "venue": "bat-backfill"},                  # no listing ID: ignored
              {"date": "2020-01-01", "price": 1000, "venue": "bat", "listing_id": "old"}]       # older than two years
    d = {"result": "refused", "old": 195000, "new": 27000, "allowed": [120000, 350000], "low_price": 150000, "high_price": 280000}
    r = row(car("vantage", low_price=150000, high_price=280000), scraped("scraped", [src(200, cards=24)]), d, store=store)
    assert r["codes"] == ["BAND_REFUSED"] and r["price"] == "$195,000 (kept)"
    assert report.suggest_band(store, TODAY) == (23000, 35000, 9)      # p10 $23,400 and p90 $34,600, rounded out
    assert "set low_price to $23,000 and high_price to $35,000" in r["fix"]["BAND_REFUSED"] and "$27,000" in r["why"]["BAND_REFUSED"]
    assert report.suggest_band(store[:2], TODAY) is None


def test_anchor_off():
    a = [{"id": "viper", "check": "sales median", "avg": 445000, "median": 35500, "n": 4, "message": "m"}]
    r = row(car("viper"), scraped("scraped", [src(200, cards=9)]), {"result": "unchanged", "old": 1, "new": 1}, a)
    assert r["codes"] == ["ANCHOR_OFF"] and "$35,500" in r["why"]["ANCHOR_OFF"]
    r = row(car("nio", category="Chinese"), None, None, [{"id": "nio", "check": "below band", "avg": 7800, "low": 73500, "message": "m"}])
    assert r["codes"] == ["MANUAL", "ANCHOR_OFF"] and report.needs_a_look(r) == ["ANCHOR_OFF"]


@contextlib.contextmanager
def fake_gh():
    """A temp dir with a 'gh' on PATH that records its calls, and GH_TOKEN set to a fake secret."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "gh").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FIXTURES / "fake_gh.py"}" "$@"\n')
        (tmp / "gh").chmod(0o755)
        saved = {k: os.environ.get(k) for k in ("PATH", "FAKE_GH_LOG", "FAKE_GH_STATE", "GH_TOKEN", "GITHUB_RUN_ID",
                                                "GITHUB_SERVER_URL", "GITHUB_REPOSITORY")}
        os.environ.update(PATH=f"{tmp}{os.pathsep}{os.environ['PATH']}", FAKE_GH_LOG=str(tmp / "log"),
                          FAKE_GH_STATE=str(tmp / "state.json"), GH_TOKEN=SECRET, GITHUB_SERVER_URL="https://github.com",
                          GITHUB_REPOSITORY="owner/repo", GITHUB_RUN_ID="1")
        try:
            yield tmp
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def calls(tmp):
    log = tmp / "log"
    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


def writes(tmp, since=0):
    return [" ".join(c["args"][:2]) for c in calls(tmp)[since:] if c["args"][1] != "list"]


def test_issue_flow_against_a_fake_gh():
    nsxr = row(car("nsx-r"), scraped("fallback", [src(200, cards=23, rejects={"unsold": 3, "model year": 20})]))
    fd = row(car("fd-rx7"), scraped("fallback", [src(200, final="https://bringatrailer.com/mazda/rx-7-fd/")]))
    r33 = row(car("r33"), scraped("thin", [src(200, cards=4)], [{"date": "2026-01-01", "price": 1}]))
    nio = row(car("nio", category="Chinese"), None)
    ok = row(car("ok"), scraped("scraped", [src(200, cards=20)]), {"result": "unchanged", "old": 1, "new": 1})
    state = lambda tmp: json.loads((tmp / "state.json").read_text())["issues"]
    with fake_gh() as tmp:
        # A look-alike issue someone else opened is left alone
        (tmp / "state.json").write_text(json.dumps({"issues": [{"number": 1, "title": report.TITLE, "state": "OPEN", "body": "hi",
                                                                "comments": [], "author": {"login": "someone", "is_bot": False}}]}))
        assert report.sync_issue([ok, r33, nio], "2026-09-28", "owner/repo") == "nothing to report"
        assert writes(tmp) == []                                               # clean list, no issue of ours: only a list call
        assert report.sync_issue([ok, nsxr, fd, r33, nio], "2026-09-28", "owner/repo") == "opened https://github.com/owner/repo/issues/2"
        issue = state(tmp)[1]
        assert issue["state"] == "OPEN" and issue["title"] == "Cars that need a look" and state(tmp)[0]["body"] == "hi"
        body = issue["body"]
        assert body.startswith("<!-- cars-that-need-a-look: fd-rx7:NO_CARDS nsx-r:ALL_REJECTED -->\n"
                               "<!-- search-failed-last-run:  -->\n"), body[:120]
        assert "https://github.com/owner/repo/upload/main/frontend" in body and "Also thin this run" in body and "r33" in body
        assert "nio" not in body                                               # Chinese cars are manual, not problems
        n = len(calls(tmp))
        os.environ["GITHUB_RUN_ID"] = "2"                                      # a second identical run: body refreshed, no comment
        assert report.sync_issue([ok, nsxr, fd, r33, nio], "2026-10-05", "owner/repo") == "#2 unchanged"
        assert writes(tmp, n) == ["issue edit"] and state(tmp)[1]["comments"] == []
        n = len(calls(tmp))
        assert report.sync_issue([ok, nsxr, fd, r33, nio], "2026-10-05", "owner/repo") == "#2 unchanged"
        assert writes(tmp, n) == []                                            # nothing new at all: nothing written
        fixed_fd = row(car("fd-rx7"), scraped("scraped", [src(200, cards=20)]), {"result": "applied", "old": 42000, "new": 36875})
        new_404 = row(car("s15"), scraped("fallback", [src(404)]))
        assert report.sync_issue([ok, nsxr, fixed_fd, new_404], "2026-10-12", "owner/repo") == "commented on #2"
        assert state(tmp)[1]["comments"][-1].startswith("The list changed after the run of 2026-10-12")
        assert "New: s15 (SEARCH_404)." in state(tmp)[1]["comments"][-1] and "Fixed: fd-rx7 (NO_CARDS)." in state(tmp)[1]["comments"][-1]
        assert report.sync_issue([ok, fixed_fd, r33], "2026-10-19", "owner/repo") == "closed #2"
        assert state(tmp)[1]["state"] == "CLOSED" and "Nothing needs a look" in state(tmp)[1]["comments"][-1]
        assert report.markers(state(tmp)[1]["body"]) == ("", set())             # the bot's close clears the list
        n = len(calls(tmp))
        assert report.sync_issue([ok, fixed_fd, r33], "2026-10-26", "owner/repo") == "nothing to report" and writes(tmp, n) == []
        assert report.sync_issue([ok, new_404], "2026-11-02", "owner/repo") == "commented on #2"   # reopened, not a new issue
        assert writes(tmp, n) == ["issue reopen", "issue comment", "issue edit"] and state(tmp)[1]["state"] == "OPEN"
        assert len(state(tmp)) == 2
        everything = json.dumps(calls(tmp)) + json.dumps(state(tmp))
        assert SECRET not in everything and "GH_TOKEN" not in everything


def issues(tmp):
    return json.loads((tmp / "state.json").read_text())["issues"]


def close_by_hand(tmp):
    st = json.loads((tmp / "state.json").read_text())
    st["issues"][0]["state"] = "CLOSED"
    (tmp / "state.json").write_text(json.dumps(st))


def sync_failing(rows, when, command):
    os.environ["FAKE_GH_FAIL"] = command
    try:
        report.sync_issue(rows, when, "owner/repo")
        raise AssertionError("expected gh to fail")
    except SystemExit as e:
        assert "502" in str(e)
    finally:
        os.environ.pop("FAKE_GH_FAIL", None)


def test_a_gh_failure_repeats_the_email_instead_of_losing_it():
    nsxr = row(car("nsx-r"), scraped("fallback", [src(200, cards=23, rejects={"model year": 20})]))
    fd = row(car("fd-rx7"), scraped("fallback", [src(404)]))
    with fake_gh() as tmp:
        report.sync_issue([nsxr], "2026-10-04", "owner/repo")
        sync_failing([nsxr, fd], "2026-10-11", "comment")                    # fd-rx7 is new, the comment gets a 502
        assert issues(tmp)[0]["comments"] == []
        assert report.sync_issue([nsxr, fd], "2026-10-18", "owner/repo") == "commented on #1"
        assert "New: fd-rx7 (SEARCH_404)." in issues(tmp)[0]["comments"][-1]
        assert report.sync_issue([nsxr, fd], "2026-10-25", "owner/repo") == "#1 unchanged"
        sync_failing([], "2026-11-01", "close")                                # clean run, the close gets a 502
        assert report.sync_issue([], "2026-11-08", "owner/repo") == "closed #1"
        assert sum("Nothing needs a look" in c for c in issues(tmp)[0]["comments"]) == 1
        sync_failing([nsxr], "2026-11-15", "comment")                          # reopened, then the comment fails
        assert report.sync_issue([nsxr], "2026-11-22", "owner/repo") == "commented on #1"
        assert issues(tmp)[0]["state"] == "OPEN" and len(issues(tmp)) == 1


def test_an_issue_closed_by_hand_stays_closed_until_the_list_changes():
    nsxr = row(car("nsx-r"), scraped("fallback", [src(200, cards=23, rejects={"model year": 20})]))
    fd = row(car("fd-rx7"), scraped("fallback", [src(404)]))
    with fake_gh() as tmp:
        report.sync_issue([nsxr], "2026-10-04", "owner/repo")
        close_by_hand(tmp)
        n = len(calls(tmp))
        for when in ("2026-10-11", "2026-10-18"):
            assert report.sync_issue([nsxr], when, "owner/repo").startswith("#1 unchanged (closed by hand")
        assert writes(tmp, n) == [] and issues(tmp)[0]["state"] == "CLOSED" and issues(tmp)[0]["comments"] == []
        assert report.sync_issue([nsxr, fd], "2026-10-25", "owner/repo") == "commented on #1"   # the list changed
        c = issues(tmp)[0]["comments"]
        assert issues(tmp)[0]["state"] == "OPEN" and len(c) == 1 and "New: fd-rx7 (SEARCH_404)." in c[0] and "nsx-r" not in c[0]
        close_by_hand(tmp)
        assert report.sync_issue([], "2026-11-01", "owner/repo") == "commented on closed #1"  # now clear: say so once
        assert report.sync_issue([], "2026-11-08", "owner/repo") == "nothing to report"
        assert len(issues(tmp)[0]["comments"]) == 2 and issues(tmp)[0]["state"] == "CLOSED"


def test_the_order_of_cars_does_not_change_the_list():
    s15 = row(car("s15-spec"), scraped("fallback", [src(404)]))
    nsxr = row(car("nsx-r"), scraped("fallback", [src(200, cards=23, rejects={"model year": 20})]))
    with fake_gh() as tmp:
        report.sync_issue([s15, nsxr], "2026-09-28", "owner/repo")
        assert report.sync_issue([nsxr, s15], "2026-10-05", "owner/repo") == "#1 unchanged"   # nsx-r moved to the watchlist
        assert issues(tmp)[0]["comments"] == []
        # a marker written in config order (before this was sorted) still compares as the same list
        st = json.loads((tmp / "state.json").read_text())
        st["issues"][0]["body"] = st["issues"][0]["body"].replace("nsx-r:ALL_REJECTED s15-spec:SEARCH_404", "s15-spec:SEARCH_404 nsx-r:ALL_REJECTED")
        (tmp / "state.json").write_text(json.dumps(st))
        assert report.sync_issue([nsxr, s15], "2026-10-12", "owner/repo") == "#1 unchanged"


def test_a_first_fetch_failure_is_information_only():
    nsxr = row(car("nsx-r"), scraped("fallback", [src(200, cards=23, rejects={"model year": 20})]))
    ok = row(car("fd-rx7"), scraped("scraped", [src(200, cards=20)]), {"result": "unchanged", "old": 1, "new": 1})
    blip = lambda: row(car("fd-rx7"), scraped("fallback", [src(503)]))
    with fake_gh() as tmp:
        assert report.sync_issue([blip()], "2026-09-28", "owner/repo").startswith("opened")   # no issue to remember in yet
        assert report.sync_issue([ok], "2026-10-05", "owner/repo") == "closed #1"
        n = len(calls(tmp))
        assert report.sync_issue([blip()], "2026-10-12", "owner/repo") == "#1 updated"         # remembered, no email
        assert writes(tmp, n) == ["issue edit"] and issues(tmp)[0]["state"] == "CLOSED"
        assert report.markers(issues(tmp)[0]["body"]) == ("", {"fd-rx7"})
        assert report.sync_issue([ok], "2026-10-19", "owner/repo") == "#1 updated"              # it answered again: forgotten
        assert report.sync_issue([ok], "2026-10-26", "owner/repo") == "nothing to report"
        assert len(issues(tmp)[0]["comments"]) == 1                                             # only the first close
        report.sync_issue([blip()], "2026-11-02", "owner/repo")
        assert report.sync_issue([blip()], "2026-11-09", "owner/repo") == "commented on #1"    # twice in a row: a problem
        assert "New: fd-rx7 (FETCH_FAILED)." in issues(tmp)[0]["comments"][-1]
        # while the issue is open for another car, a first failure is listed below the problems, not in the list
        assert report.sync_issue([nsxr, ok], "2026-11-16", "owner/repo") == "commented on #1"
        r = blip()
        assert report.sync_issue([nsxr, r], "2026-11-23", "owner/repo") == "#1 unchanged"
        body = issues(tmp)[0]["body"]
        assert r["first_failure"] and report.needs_a_look(r) == [] and "did not answer these searches" in body
        assert report.markers(body) == ("nsx-r:ALL_REJECTED", {"fd-rx7"})


def test_all_rejected_advice_follows_the_reject_counts():
    def fix(rejects):
        return row(car("x"), scraped("fallback", [src(200, cards=10, rejects=rejects)]))["fix"]["ALL_REJECTED"]
    assert "avg_price" in fix({"implausible": 10}) and "widen years" not in fix({"implausible": 10})     # corvette-z06
    assert "avg_price" in fix({"unsold": 1, "implausible": 2})
    assert "widen years" in fix({"model year": 14, "implausible": 6}) and "avg_price" not in fix({"model year": 14})
    assert "loosen the title words" in fix({"title filter": 3})
    assert "Unsold auctions never count" in fix({"unsold": 5})
    body = report.issue_body([row(car("z06"), scraped("fallback", [src(200, cards=10, rejects={"implausible": 10})]))], "2026-09-28", "o/r")
    assert "set avg_price near those sale prices" in body


def test_the_price_run_builds_on_the_current_main():
    # A run that waited in the queue must start from main as it is then, not from the commit that queued it,
    # or its push conflicts with the run before it. A misnamed config upload must start a run too.
    wf = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "update-prices.yml").read_text()
    step = wf[wf.index("uses: actions/checkout@"):wf.index("- name:", wf.index("uses: actions/checkout@"))]
    assert "ref: ${{ github.ref }}" in step, step
    assert "- 'frontend/cars.config*.js'" in wf and "group: garage-data" in wf and "cancel-in-progress: false" in wf


@contextlib.contextmanager
def report_sandbox(scrape, results):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "scraped_prices.json").write_text(json.dumps(scrape))
        if results is not None:
            (tmp / "run_results.json").write_text(json.dumps(results))
        shutil.copy(FIXTURES / "fixture_price_history.json", tmp / "price_history.json")
        saved = (gen.SCRAPED_PATH, gen.RESULTS_PATH, gen.PRICE_HISTORY_PATH, sp.CONFIG_PATH)
        gen.SCRAPED_PATH, gen.RESULTS_PATH, gen.PRICE_HISTORY_PATH = tmp / "scraped_prices.json", tmp / "run_results.json", tmp / "price_history.json"
        sp.CONFIG_PATH = FIXTURES / "fixture_config.js"
        try:
            yield tmp
        finally:
            gen.SCRAPED_PATH, gen.RESULTS_PATH, gen.PRICE_HISTORY_PATH, sp.CONFIG_PATH = saved


def test_main_writes_the_summary_and_skips_the_issue_on_a_stale_results_file():
    if not shutil.which("node"):
        print("  (skipped: node not installed)"); return
    scrape = {"scraped_at": "2026-09-28T22:05:18+00:00", "prices": {
        "fx-r32": scraped("fallback", [src(404)]), "fx-gt4": scraped("scraped", [src(200, cards=20)]),
        "fx-na1": scraped("thin", [src(200, cards=3)], [{"date": "2026-09-01", "price": 95000}])}}
    results = {"scraped_at": "2026-09-28T22:05:18+00:00", "prices": {"fx-gt4": {"result": "applied", "old": 118000, "new": 134000}},
               "anchor_audit": []}
    with fake_gh() as tmp, report_sandbox(scrape, results):
        saved = os.environ.get("GITHUB_STEP_SUMMARY")                         # the runner's own, in CI
        os.environ["GITHUB_STEP_SUMMARY"] = str(tmp / "summary.md")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                report.main(["--issue"])
            text = (tmp / "summary.md").read_text()
            assert "Scrape of 2026-09-28 22:05 UTC: 1 PRICED, 1 THIN, 1 NO_DATA, 0 MANUAL. 1 price changed." in text, text
            assert "| fx-r32 | NO_DATA | $46,000 (kept) | SEARCH_404 |" in text and "| fx-gt4 | PRICED | $118,000 → $134,000 | - |" in text
            assert writes(tmp) == ["issue create"]
            n = len(calls(tmp))
            results["scraped_at"] = "2026-09-21T00:00:00+00:00"                # left over from another run
            (gen.RESULTS_PATH).write_text(json.dumps(results))
            with contextlib.redirect_stdout(io.StringIO()):
                report.main(["--issue"])
            assert "belongs to another scrape" in (tmp / "summary.md").read_text() and calls(tmp)[n:] == []
        finally:
            if saved is None:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
            else:
                os.environ["GITHUB_STEP_SUMMARY"] = saved


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} passed")
