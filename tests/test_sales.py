"""Checks for the sale-parsing and history rules. Run: python tests/test_sales.py"""
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import scrape_prices as sp        # noqa: E402
import generate_history as gh     # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"   # trimmed copies of real BaT pages


def card(lid, title, result, ts=""):
    return (f'<div class="listing-card" data-listing_id="{lid}" data-timestamp_end="{ts}">'
            f'<div class="content"><h3><a href="https://bringatrailer.com/listing/{lid}/">{title}</a></h3>'
            f'<div class="item-results">{result}</div></div></div>')


BAT_PAGE = "<html><body>" + "".join([
    card(101, "1995 Nissan Skyline GT-R V-Spec", "Sold for USD $32,000 <span>on 3/25/2024</span>"),
    card(102, "1996 Nissan Skyline R33 GT-R V-Spec LM Limited", "Bid to USD $61,000 <span>on 4/1/2024</span>"),
    card(103, "R33-Powered 1990 Nissan Skyline GT-R", "Sold for USD $14,999 <span>on 8/9/2017</span>"),
    card(101, "1995 Nissan Skyline GT-R V-Spec", "Sold for USD $32,000 <span>on 3/25/2024</span>"),
    card(104, "1997 Nissan Skyline GT-R", "Sold for USD $70,000", ts="1717200000"),
]) + "</body></html>"


def test_bat_parsing():
    sales = sp.scrape_bat_search(BAT_PAGE, years="1995-1998")
    assert [s["listing_id"] for s in sales] == ["101", "104"], sales      # unsold, wrong year, repeat all dropped
    assert sales[0]["price"] == 32000 and sales[0]["date"] == "2024-03-25"
    assert sales[1]["date"] == "2024-06-01"                                  # falls back to data-timestamp_end
    no_filter = sp.scrape_bat_search(BAT_PAGE, years=None)
    assert [s["listing_id"] for s in no_filter] == ["101", "103", "104"]    # still never counts 'Bid to'


def test_parse_years():
    assert sp.parse_years("1995-1998") == (1995, 1998)
    assert sp.parse_years("2023-Present") == (2023, date.today().year + 1)   # next year's models are on sale
    assert sp.parse_years("2022") is None and sp.parse_years(None) is None


def test_decide_price():
    today = date(2026, 9, 28)
    recent = [{"price": p, "date": "2026-01-10"} for p in (40000, 50000, 60000)]
    assert sp.decide_price(recent, 99999, today)[:2] == (50000, "scraped")
    assert sp.decide_price(recent[:2], 99999, today)[:2] == (99999, "thin")
    old = [{"price": 32000, "date": "2024-03-25"}, {"price": 35500, "date": "2024-02-27"}]
    assert sp.decide_price(old + recent[:2], 99999, today)[1] == "thin"      # old sales never count toward the price
    undated = [{"price": p, "date": None} for p in (1, 2, 3)]
    assert sp.decide_price(undated, 99999, today)[:2] == (99999, "thin")   # undated figures never count
    assert sp.decide_price([], 99999, today)[:2] == (99999, "fallback")


def test_history_rules():
    h = {"car": {"sales": [
        {"date": "2024-03-25", "price": 32000, "venue": "bat-backfill"},
        {"date": "2024-06-01", "price": 70000, "venue": "manual"},
    ]}}
    listing = {"listing_id": "101", "price": 32000, "date": "2024-03-25", "url": "u", "title": "t", "venue": "bat"}
    assert gh.add_listing_sales(h, "car", [listing], "2026-09-28") == 0     # upgrades the matching backfill entry
    assert h["car"]["sales"][0]["listing_id"] == "101"
    assert gh.add_listing_sales(h, "car", [listing], "2026-10-05") == 0     # same listing next week: not re-added
    other = dict(listing, listing_id="104", price=70000, date="2024-06-01")
    assert gh.add_listing_sales(h, "car", [other], "2026-09-28") == 1       # a 'manual' row is never a twin
    assert [x["venue"] for x in h["car"]["sales"]] == ["bat-backfill", "manual", "bat"]


def test_rejects_are_reported():
    sp.scrape_bat_search(BAT_PAGE, years="1995-1998")
    rejects = sp._SCRAPE_STATS["bat_rejects"]
    assert sorted((r["price"], r["reason"]) for r in rejects) == [(14999, "model year"), (61000, "unsold")]


def test_reconcile_removes_blended_backfill_rows():
    # Blended rows the old backfill really wrote (reproduced on the saved R33 page)
    h = {"car": {"sales": [
        {"date": "2024-03-25", "price": 32000, "venue": "bat-backfill"},   # twin of a real listing: upgraded
        {"date": "2024-03-25", "price": 33400, "venue": "bat-backfill"},   # sale blended with a same-day 'Bid to'
        {"date": "2024-03-25", "price": 52300, "venue": "bat-backfill"},   # weighted first-card average
        {"date": "2024-02-27", "price": 25250, "venue": "bat-backfill"},   # sale blended with a wrong-year car
        {"date": "2024-04-01", "price": 61000, "venue": "bat-backfill"},   # a 'Bid to' on its own day
        {"date": "2023-01-15", "price": 40000, "venue": "bat-backfill"},   # a day the scrape did not see: kept
        {"date": "2024-03-25", "price": 45000, "venue": "manual"},         # hand-curated: kept
    ]}}
    sales = [{"listing_id": "72816201", "price": 32000, "date": "2024-03-25", "venue": "bat"},
             {"listing_id": "90000001", "price": 61000, "date": "2024-03-25", "venue": "bat"},
             {"listing_id": "64308037", "price": 35500, "date": "2024-02-27", "venue": "bat"}]
    rejected = [{"price": 61000, "date": "2024-04-01", "reason": "unsold"},
                {"price": 14999, "date": "2024-02-27", "reason": "model year"}]
    gh.add_listing_sales(h, "car", sales, "2026-09-28")
    assert gh.reconcile_days(h, "car", sales, rejected) == 4
    left = sorted((x["date"], x["price"], bool(x.get("listing_id")), x["venue"]) for x in h["car"]["sales"])
    assert left == [("2023-01-15", 40000, False, "bat-backfill"), ("2024-02-27", 35500, True, "bat"),
                    ("2024-03-25", 32000, True, "bat-backfill"), ("2024-03-25", 45000, False, "manual"),
                    ("2024-03-25", 61000, True, "bat")], left


def test_band_guard():
    cfg = ("  {\n    id:         'v',\n    avg_price:  195000,\n    low_price:  150000,\n"
           "    high_price: 280000,\n    prev_avg:   195000,\n  },")
    meta = {"v": {"import_duty_pct": 0}}
    out = gh.patch_config_prices(cfg, {"v": {"price": 27000, "confidence": "scraped"}}, meta)
    assert "avg_price:  195000" in out                                        # far below the band: refused
    out = gh.patch_config_prices(cfg, {"v": {"price": 210000, "confidence": "scraped"}}, meta)
    assert "avg_price:  210000" in out and "prev_avg:   195000" in out     # inside the band: applied


def test_unchanged_price_keeps_the_change_arrow():
    cfg = ("  {\n    id:         'r32',\n    avg_price:  46000,\n    low_price:  7777,\n"
           "    high_price: 80000,\n    prev_avg:   45000,\n  },")
    meta = {"r32": {"import_duty_pct": 0}}
    same = {"r32": {"price": 46000, "confidence": "scraped"}}
    assert gh.patch_config_prices(cfg, same, meta) == cfg                   # re-runs leave prev_avg alone
    moved = gh.patch_config_prices(cfg, {"r32": {"price": 50000, "confidence": "scraped"}}, meta)
    assert "avg_price:  50000" in moved and "prev_avg:   46000" in moved     # a real move records the old price
    assert gh.patch_config_prices(moved, {"r32": {"price": 50000, "confidence": "scraped"}}, meta) == moved


def test_editor_export_still_patches():
    if not shutil.which("node"):
        print("  (skipped: node not installed)"); return
    root = Path(__file__).resolve().parent.parent
    js = ("const W=require(process.argv[1]);const fs=require('fs');"
          "const d=new Function(fs.readFileSync(process.argv[2],'utf8')+';return {CHART_COLORS,WATCHLIST,TICKER_UNIVERSE}')();"
          "process.stdout.write(W.serializeConfig(d.CHART_COLORS,d.WATCHLIST,d.TICKER_UNIVERSE));")
    exported = subprocess.run(["node", "-e", js, str(root / "frontend" / "config-writer.js"),
                               str(root / "frontend" / "cars.config.js")], capture_output=True, text=True, check=True).stdout
    meta = gh.load_cars_from_config()
    # Move every car with a price band to a new price inside it, then check each block was patched
    moves = {}
    for cid, m in meta.items():
        lo, hi = m["low_price"], m["high_price"]
        if 0 < lo < hi:
            new = int(round((lo + hi) / 2, -2))
            moves[cid] = new + 100 if new == m["avg_price"] else new
    assert moves
    out = gh.patch_config_prices(exported, {c: {"price": p, "confidence": "scraped"} for c, p in moves.items()}, meta)
    for cid, new in moves.items():
        start = out.index(f"id:         '{cid}'")
        block = out[start:out.index("\n  },", start)]
        assert re.search(rf"avg_price:\s*{new}\b", block), block
        assert re.search(rf"prev_avg:\s*{meta[cid]['avg_price']}\b", block), block
        if meta[cid]["import_duty_pct"]:
            duty = gh.js_round(new * meta[cid]["import_duty_pct"])
            assert re.search(rf"import_duty_est:\s*{duty}\b", block), block


def test_duty_rounds_halves_up_like_the_page():
    assert (gh.js_round(1162.5), gh.js_round(562.5), gh.js_round(1162.4), gh.js_round(0)) == (1163, 563, 1162, 0)
    cfg = ("  {\n    id:         'r32',\n    avg_price:  46000,\n    low_price:  7777,\n    high_price: 80000,\n"
           "    prev_avg:   45000,\n    cost_to_own: {\n      import_duty_pct:        0.025,\n      import_duty_est:        1150,\n"
           "      shipping_est:           4500,\n      total_first_year_extra: 5650,\n    },\n  },")
    meta = {"r32": {"import_duty_pct": 0.025, "shipping_est": 4500}}
    out = gh.patch_config_prices(cfg, {"r32": {"price": 46500, "confidence": "scraped"}}, meta)
    assert "import_duty_est:        1163" in out and "total_first_year_extra: 5663" in out, out


def test_averaged_backfill_day_is_replaced():
    h = {"car": {"sales": [{"date": "2025-04-04", "price": 60000, "venue": "bat-backfill"}]}}
    two = [{"listing_id": "a", "price": 50000, "date": "2025-04-04", "venue": "bat"},
           {"listing_id": "b", "price": 70000, "date": "2025-04-04", "venue": "bat"}]
    assert gh.add_listing_sales(h, "car", two, "2026-09-28") == 2
    gh.reconcile_days(h, "car", two, [])
    assert sorted(x["price"] for x in h["car"]["sales"]) == [50000, 70000]   # the $60,000 average is gone


def test_next_model_year_kept_for_present():
    page = card(201, "2027 Chevrolet Corvette Z06", "Sold for USD $160,000 <span>on 9/20/2026</span>")
    assert [s["listing_id"] for s in sp.scrape_bat_search(page, years="2023-Present")] == ["201"]


def test_plotted_count_covers_the_chart_year():
    today = date(2026, 9, 28)
    entry = {"sales": [{"date": "2026-06-01", "price": 50000, "venue": "bat"},
                       {"date": "2024-03-25", "price": 52000, "venue": "bat"},
                       {"date": "2026-09-28", "price": 51000, "venue": "bat"}]}   # today: the chart ends yesterday
    _, _, meta = gh.build_for_car(entry, today, 50000)
    assert (meta["n_total"], meta["n_plotted"], meta["last_sale"]) == (3, 1, "2026-09-28")


@contextlib.contextmanager
def fake_bat(pages):
    """Serve fetch() from {url: (status, final_url, html)} and record every URL fetched."""
    fetched = []
    def fetch(client, url):
        fetched.append(url)
        return pages[url]
    saved = sp.fetch, sp.DELAY
    sp.fetch, sp.DELAY = fetch, 0
    try:
        yield fetched
    finally:
        sp.fetch, sp.DELAY = saved


def test_scrape_car_uses_bat_cards_only():
    url = "https://bringatrailer.com/search/?s=r33+gt-r"
    car = {"id": "r33", "label": "Nissan Skyline R33 GT-R", "fallback_avg": 40000, "sources": [
        {"type": "bat_search", "url": url, "years": "1995-1998"},
        {"type": "kbb", "url": "https://www.kbb.com/nissan/gt-r/2020/"}]}
    with fake_bat({url: (200, url, BAT_PAGE)}) as fetched:
        r = sp.scrape_car(None, car)
    assert fetched == [url]                                                  # the kbb extra is never fetched
    assert [x["listing_id"] for x in r["sales"]] == ["101", "104"]
    assert r["confidence"] == "thin" and r["avg_price"] == 40000
    assert sorted(x["reason"] for x in r["rejected"]) == ["model year", "unsold"]
    bat, kbb = r["sources"]
    assert (bat["status"], bat["final_url"], bat["kind"], bat["cards"], bat["items"]) == (200, url, "search", 4, 0)
    assert bat["rejects"] == {"unsold": 1, "model year": 1, "title filter": 0, "implausible": 0}
    assert kbb == {"type": "kbb", "url": "https://www.kbb.com/nissan/gt-r/2020/", "skipped": "no scraper"}
    assert not ({"sold_prices", "n_sales", "venues", "asking_ref", "sold_ref"} & set(r))   # outputs nothing reads
    assert r["scraped_at"].endswith("+00:00")                                # no more '+00:00Z'


def test_model_page_reads_embedded_auctions():
    # A search that redirected to /aston-martin/v12-vantage/: 2 live cards, 24 completed auctions in JSON
    page = (FIXTURES / "bat_model_v12_vantage.html").read_text()
    assert len(sp.parse_bat_cards(page)) == 2 and len(sp.parse_bat_model_items(page)) == 24
    sales = sp.scrape_bat_search(page, years="2023-Present")
    assert [(s["listing_id"], s["price"], s["date"]) for s in sales] == [
        ("116422858", 244000, "2026-08-12"), ("116877974", 302222, "2026-08-03"),
        ("104775089", 262000, "2026-03-17"), ("104130049", 251823, "2026-01-26")]
    assert sales[0]["title"] == "2,500-Mile 2023 Aston Martin V12 Vantage Coupe"
    assert sales[0]["url"] == "https://bringatrailer.com/listing/2023-aston-martin-v12-vantage-coupe-14/"
    assert sp._SCRAPE_STATS["bat_page"] == {"kind": "model", "cards": 2, "items": 24, "sold_seen": 21,
                                            "rejects": {"unsold": 3, "model year": 17, "title filter": 0, "implausible": 0}}
    # Unsold ('Bid to') items and parts under $5,000 never count; the year comes from the title
    r35 = sp.scrape_bat_search((FIXTURES / "bat_model_gtr_r35.html").read_text(), years="2020-2024")
    assert [s["listing_id"] for s in r35] == ["117012893"]
    assert sp._SCRAPE_STATS["bat_page"]["rejects"] == {"unsold": 1, "model year": 2, "title filter": 0, "implausible": 1}
    nsx = sp.scrape_bat_search((FIXTURES / "bat_model_acura_nsx.html").read_text(), years="1990-2001", exclude=["Zanardi"])
    assert [s["listing_id"] for s in nsx] == ["121482963", "120486585"]
    assert sp._SCRAPE_STATS["bat_page"]["rejects"] == {"unsold": 1, "model year": 0, "title filter": 1, "implausible": 1}
    s13 = sp.scrape_bat_search((FIXTURES / "bat_model_240sx.html").read_text(), years="1989-1994")
    assert [s["listing_id"] for s in s13] == ["114949770"]
    assert sorted((r["listing_id"], r["reason"]) for r in sp._SCRAPE_STATS["bat_rejects"]) == [
        ("112604159", "unsold"), ("116186273", "unsold"), ("120804089", "model year")]


def test_search_pages_have_no_embedded_auctions():
    for name in ("bat_search_mr2.html", "bat_search_z06.html"):
        page = (FIXTURES / name).read_text()
        assert sp.parse_bat_model_items(page) is None, name
    mr2 = sp.scrape_bat_search((FIXTURES / "bat_search_mr2.html").read_text(), years="1991-1995")
    assert [s["price"] for s in mr2] == [32014, 15250, 5200]
    assert sp._SCRAPE_STATS["bat_page"] == {"kind": "search", "cards": 4, "items": 0, "sold_seen": 3,
                                            "rejects": {"unsold": 1, "model year": 0, "title filter": 0, "implausible": 0}}


def test_card_and_embedded_item_count_once():
    item = {"id": 501, "title": "2023 Aston Martin V12 Vantage Coupe", "url": "https://bringatrailer.com/listing/x/",
            "sold_text": "Sold for USD $250,000 <span> on 9/7/2026 </span>", "timestamp_end": 1788804749, "year": None}
    script = ("<script>\n        var auctionsCompletedInitialData = "
              + json.dumps({"items": [item, dict(item, id=502, sold_text="Bid to USD $240,000 <span> on 9/8/2026 </span>")]})
              + ";\n</script>")
    # the same listing as a card with a result, and a live card (no result yet) for an embedded auction
    page = (card(501, "2023 Aston Martin V12 Vantage Coupe", "Sold for USD $250,000 <span>on 9/7/2026</span>")
            + card(502, "2023 Aston Martin V12 Vantage Coupe", "") + script)
    sales = sp.scrape_bat_search(page, years="2023-Present")
    assert [(s["listing_id"], s["price"], s["date"]) for s in sales] == [("501", 250000, "2026-09-07")]
    assert [(r["listing_id"], r["reason"]) for r in sp._SCRAPE_STATS["bat_rejects"]] == [("502", "unsold")]
    assert sp._SCRAPE_STATS["bat_page"]["sold_seen"] == 1


def test_model_page_redirect_and_404_are_recorded():
    search = "https://bringatrailer.com/search/?s=aston+vantage+v12"
    model = "https://bringatrailer.com/aston-martin/v12-vantage/"
    empty = "https://bringatrailer.com/search/?s=honda+nsx+na1"
    page = (FIXTURES / "bat_model_v12_vantage.html").read_text()
    car = {"id": "vantage-gt3", "label": "Aston Martin Vantage", "fallback_avg": 195000, "sources": [
        {"type": "bat_search", "url": search, "years": "2023-Present"},
        {"type": "bat_search", "url": empty, "years": "2023-Present"},
        {"type": "bat_search", "url": search, "years": "2023-Present"}]}      # a repeated search counts nothing twice
    with fake_bat({search: (200, model, page), empty: (404, empty, None)}):
        r = sp.scrape_car(None, car)
    assert (r["confidence"], r["avg_price"]) == ("scraped", 256911)          # median of the four 2023 cars
    first, missing, again = r["sources"]
    assert (first["status"], first["final_url"], first["kind"], first["counted"]) == (200, model, "model", 4)
    assert missing["status"] == 404 and missing["note"].startswith("no results") and "kind" not in missing
    assert again["counted"] == 0 and len(r["sales"]) == 4


def test_chinese_cars_and_non_bat_urls_are_not_fetched():
    cars = [{"id": "nio-es9", "label": "Nio ES9", "category": "Chinese", "fallback_avg": 78000,
             "sources": [{"type": "bat_search", "url": "https://bringatrailer.com/search/?s=nio+es9"}]},
            {"id": "r35-gtr", "label": "Nissan GT-R", "category": "Modern", "fallback_avg": 106000,
             "sources": [{"type": "bat_search", "url": "https://www.cars.com/shopping/nissan-gt_r-2020/"}]}]
    with fake_bat({}) as fetched:
        nio, r35 = (sp.scrape_car(None, c) for c in cars)
    assert fetched == []
    assert (nio["confidence"], nio["avg_price"], nio["sources"]) == ("fallback", 78000, [])
    assert r35["confidence"] == "fallback" and r35["sources"][0]["skipped"] == "not a Bring a Trailer URL"


def run_scraper_main(cars, pages):
    """Run sp.main() on the given cars and pages; returns (exit code or None, written JSON or None)."""
    with tempfile.TemporaryDirectory() as tmp:
        saved = sp.load_cars_from_config, sp.OUTPUT_PATH
        sp.load_cars_from_config, sp.OUTPUT_PATH = (lambda: cars), Path(tmp) / "scraped_prices.json"
        code = None
        try:
            with fake_bat(pages):
                sp.main()
        except SystemExit as e:
            code = e.code
        finally:
            out = sp.OUTPUT_PATH
            sp.load_cars_from_config, sp.OUTPUT_PATH = saved
        return code, (json.loads(out.read_text()) if out.exists() else None)


def test_no_sold_card_anywhere_fails_before_writing():
    url = "https://bringatrailer.com/search/?s=r33+gt-r"
    cars = [{"id": "r33", "label": "R33", "fallback_avg": 40000, "sources": [{"type": "bat_search", "url": url}]}]
    code, written = run_scraper_main(cars, {url: (200, url, BAT_PAGE)})
    assert code is None and written["prices"]["r33"]["sold_seen"] == 3 and written["thin"] == 1
    code, written = run_scraper_main(cars, {url: (200, url, "<html><body></body></html>")})   # empty page
    assert code not in (None, 0) and written is None
    reworded = BAT_PAGE.replace("Sold for", "Winning Bid")                   # BaT rewords its result line
    code, written = run_scraper_main(cars, {url: (200, url, reworded)})
    assert code not in (None, 0) and written is None


def test_unsold_reject_never_removes_a_stored_sale():
    # The 'Winning Bid' simulation: every card now reads as unsold. On HEAD this deleted every stored sale.
    stored = [{"date": "2024-03-25", "price": 32000, "venue": "bat", "listing_id": "101", "title": "1995 Nissan Skyline GT-R V-Spec"},
              {"date": "2024-06-01", "price": 70000, "venue": "bat", "listing_id": "104", "title": "1997 Nissan Skyline GT-R"}]
    h = {"car": {"sales": [dict(x) for x in stored]}}
    sp.scrape_bat_search(BAT_PAGE.replace("Sold for", "Winning Bid"), years="1995-1998")
    rejected = sp._SCRAPE_STATS["bat_rejects"]
    assert {r["reason"] for r in rejected} == {"unsold"} and {"101", "104"} <= {r["listing_id"] for r in rejected}
    assert gh.reconcile_days(h, "car", [], rejected) == 0
    assert h["car"]["sales"] == stored


def test_phase1_exported_extras_reach_the_scraper():
    if not shutil.which("node"):
        print("  (skipped: node not installed)"); return
    root = Path(__file__).resolve().parent.parent
    extra = {"type": "bat_search", "url": "https://bringatrailer.com/nissan/gtr-r35/", "years": "2009-2024",
             "exclude": ["Wheels", "Seats"]}
    js = ("const W=require(process.argv[1]);const fs=require('fs');"
          "const d=new Function(fs.readFileSync(process.argv[2],'utf8')+';return {CHART_COLORS,WATCHLIST,TICKER_UNIVERSE}')();"
          "const c=[...d.WATCHLIST,...d.TICKER_UNIVERSE].find(c=>c.id==='r35-gtr');c.scrape_extras=[JSON.parse(process.argv[3])];"
          "process.stdout.write(W.serializeConfig(d.CHART_COLORS,d.WATCHLIST,d.TICKER_UNIVERSE));")
    exported = subprocess.run(["node", "-e", js, str(root / "frontend" / "config-writer.js"),
                               str(root / "frontend" / "cars.config.js"), json.dumps(extra)],
                              capture_output=True, text=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "cars.config.js"
        cfg.write_text(exported)
        saved, sp.CONFIG_PATH = sp.CONFIG_PATH, cfg
        try:
            cars = {c["id"]: c for c in sp.load_cars_from_config()}
        finally:
            sp.CONFIG_PATH = saved
    src = [s for s in cars["r35-gtr"]["sources"] if s.get("note") == "extra"]
    assert src == [{"type": "bat_search", "url": extra["url"], "note": "extra", "years": "2009-2024",
                    "exclude": ["Wheels", "Seats"]}], src
    kw = {k: v for k, v in src[0].items() if k not in ("type", "url", "note")}
    page = (FIXTURES / "bat_model_gtr_r35.html").read_text()
    assert [s["listing_id"] for s in sp.scrape_bat_search(page, **kw)] == ["121020553", "119507289", "117012893"]


def test_generator_loader_matches_the_scraper_config():
    if not shutil.which("node"):
        print("  (skipped: node not installed)"); return
    cfg = gh.load_cars_from_config()
    assert len(cfg) == 37 and set(next(iter(cfg.values()))) == set(gh.CONFIG_FIELDS)
    evo = cfg["evo-vi"]
    assert evo["title_include"] == ["Makinen", "Mäkinen", "TME"] and evo["years"] == "1999-2001"
    assert evo["import_duty_pct"] == 0.025 and evo["low_price"] > 0 and evo["high_price"] > evo["low_price"]


@contextlib.contextmanager
def generator_sandbox(scraped=None):
    """A temp copy of the frontend files with generate_history's paths pointed at it."""
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in ("cars.config.js", "price_history.json", "data.js"):
            shutil.copy(root / "frontend" / name, tmp / name)
        if scraped is not None:
            (tmp / "scraped_prices.json").write_text(json.dumps(scraped))
        names = ("SCRAPED_PATH", "PRICE_HISTORY_PATH", "DATA_JS_PATH", "CONFIG_JS_PATH")
        saved = [getattr(gh, n) for n in names] + [sp.CONFIG_PATH]
        for n, f in zip(names, ("scraped_prices.json", "price_history.json", "data.js", "cars.config.js")):
            setattr(gh, n, tmp / f)
        sp.CONFIG_PATH = tmp / "cars.config.js"
        try:
            yield tmp
        finally:
            for n, v in zip(names, saved):
                setattr(gh, n, v)
            sp.CONFIG_PATH = saved[-1]


def test_without_a_scrape_only_data_js_is_written():
    if not shutil.which("node"):
        print("  (skipped: node not installed)"); return
    for dev in (False, True):
        with generator_sandbox() as tmp:
            before = {f: (tmp / f).read_bytes() for f in ("cars.config.js", "price_history.json")}
            (tmp / "data.js").write_text("stale")
            gh.run_generate(dev)
            assert {f: (tmp / f).read_bytes() for f in before} == before           # store and config untouched
            assert (tmp / "data.js").read_text().startswith("var BAKED_HISTORY = ")
            assert sorted(p.name for p in tmp.iterdir()) == ["cars.config.js", "data.js", "price_history.json"]


def test_no_new_placeholder_rows_and_stored_rows_kept():
    if not shutil.which("node"):
        print("  (skipped: node not installed)"); return
    store = json.loads((Path(__file__).resolve().parent.parent / "frontend" / "price_history.json").read_text())
    sold = next(x for x in store["r32-gtr"]["sales"] if x.get("listing_id"))
    # A fallback car (the old code added a 'manual-auto' row for it) and a stored sale now showing as unsold
    scraped = {"prices": {"nsx-na1": {"avg_price": 95000, "confidence": "fallback", "sales": [], "rejected": []},
                          "r32-gtr": {"avg_price": 46000, "confidence": "thin", "sales": [], "rejected": [
                              {"listing_id": sold["listing_id"], "price": sold["price"], "date": sold["date"], "reason": "unsold"}]}}}
    with generator_sandbox(scraped) as tmp:
        gh.run_generate(False)
        after = json.loads((tmp / "price_history.json").read_text())
        assert sorted(p.name for p in tmp.iterdir()) == ["cars.config.js", "data.js", "price_history.json", "scraped_prices.json"]
    assert after == store                                                    # nothing added, nothing removed


def test_interrupted_store_write_keeps_the_old_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "price_history.json"
        path.write_text(json.dumps({"car": {"sales": [{"date": "2024-01-01", "price": 1, "venue": "bat"}] * 700}}))
        saved_path, saved_replace = gh.PRICE_HISTORY_PATH, gh.os.replace
        gh.PRICE_HISTORY_PATH = path
        def killed(src, dst):
            raise KeyboardInterrupt("killed before the move")
        gh.os.replace = killed
        try:
            gh.save_price_history({"car": {"sales": []}})
        except KeyboardInterrupt:
            pass
        finally:
            gh.PRICE_HISTORY_PATH, gh.os.replace = saved_path, saved_replace
        assert len(json.loads(path.read_text())["car"]["sales"]) == 700          # still the whole old store


def test_title_filters():
    page = "".join([
        card(301, "2015 Ferrari 458 Speciale", "Sold for USD $650,000 <span>on 7/3/2025</span>"),
        card(302, "2015 Ferrari 458 Speciale A", "Sold for USD $2,125,000 <span>on 7/22/2026</span>"),
        card(303, "1987 Mazda RX-7 Turbo II 5-Speed", "Sold for USD $22,250 <span>on 8/5/2025</span>"),
        card(304, "1989 Mazda RX-7 Convertible", "Sold for USD $6,169 <span>on 5/24/2025</span>"),
    ])
    assert [x["listing_id"] for x in sp.scrape_bat_search(page, exclude=["Speciale A", "Aperta"])] == ["301", "303", "304"]
    assert sorted((r["listing_id"], r["reason"]) for r in sp._SCRAPE_STATS["bat_rejects"]) == [("302", "title filter")]
    assert [x["listing_id"] for x in sp.scrape_bat_search(page, include=["Turbo II", "Turbo 2"])] == ["303"]


def test_rejected_listing_already_stored_is_removed():
    h = {"car": {"sales": [{"date": "2026-07-22", "price": 2125000, "venue": "bat", "listing_id": "302", "title": "2015 Ferrari 458 Speciale A"},
                           {"date": "2025-07-03", "price": 650000, "venue": "bat", "listing_id": "301", "title": "2015 Ferrari 458 Speciale"}]}}
    rejected = [{"listing_id": "302", "price": 2125000, "date": "2026-07-22", "reason": "title filter"}]
    assert gh.reconcile_days(h, "car", [], rejected) == 1
    assert [x["listing_id"] for x in h["car"]["sales"]] == ["301"]


def test_car_rules_apply_to_stored_listings():
    h = {"fc": {"sales": [
        {"date": "2025-08-05", "price": 22250, "venue": "bat", "listing_id": "303", "title": "1987 Mazda RX-7 Turbo II 5-Speed"},
        {"date": "2025-05-24", "price": 6169, "venue": "bat", "listing_id": "304", "title": "1989 Mazda RX-7 Convertible"},
        {"date": "2024-01-01", "price": 15000, "venue": "bat-backfill"},                     # no title: can't judge, kept
        {"date": "2023-06-01", "price": 9000, "venue": "bat", "listing_id": "305", "title": "1979 Mazda RX-7 Turbo II"},
    ]}}
    rules = {"years": "1985-1991", "title_include": ["Turbo II", "Turbo 2"], "title_exclude": None}
    assert gh.enforce_car_rules(h, "fc", rules) == 2
    assert sorted(x.get("listing_id", "-") for x in h["fc"]["sales"]) == ["-", "303"]
    assert gh.enforce_car_rules(h, "fc", {"years": "2022"}) == 0                          # no rules in effect


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for fn in fns:
        # The code under test prints its own progress (e.g. "OK  r33-gtr: avg 32,000->76,000" from a
        # fixture). Keep it out of the log so it is never mistaken for a real price change; show it on failure.
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                fn()
        except BaseException:
            print(out.getvalue())
            raise
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} passed")
