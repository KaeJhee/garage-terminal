"""Checks for the sale-parsing and history rules. Run: python tests/test_sales.py"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import scrape_prices as sp        # noqa: E402
import generate_history as gh     # noqa: E402
import backfill_history as bf     # noqa: E402


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
        {"date": "2026-09-27", "price": 32000, "venue": "bat_search"},
        {"date": "2026-09-20", "price": 32000, "venue": "bat_search"},
        {"date": "2026-09-20", "price": 45000, "venue": "manual"},
    ]}}
    assert gh.drop_legacy_bat_search(h) == 2
    assert [x["venue"] for x in h["car"]["sales"]] == ["bat-backfill", "manual"]
    listing = {"listing_id": "101", "price": 32000, "date": "2024-03-25", "url": "u", "title": "t", "venue": "bat"}
    assert gh.add_listing_sales(h, "car", [listing], "2026-09-28") == 0     # upgrades the matching backfill entry
    assert h["car"]["sales"][0]["listing_id"] == "101"
    assert gh.add_listing_sales(h, "car", [listing], "2026-10-05") == 0     # same listing next week: not re-added
    other = dict(listing, listing_id="104", price=70000, date="2024-06-01")
    assert gh.add_listing_sales(h, "car", [other], "2026-09-28") == 1
    cab = {"price": 45000, "date": None, "venue": "carsandbids"}
    assert gh.add_listing_sales(h, "car", [cab], "2026-09-28") == 1
    assert gh.add_listing_sales(h, "car", [cab], "2026-10-05") == 0         # same venue + price inside the lookback
    assert gh.add_listing_sales(h, "car", [cab], "2027-03-01") == 1         # outside the lookback: a new sale


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


def test_backfill_skips_unsold_cards():
    # Wrapped the way real search pages are, so a page-level container can't leak a 'Bid to' price
    page = '<body class="search search-results"><div class="search-results-loop">' + BAT_PAGE + '</div></body>'
    got = bf.parse_bat_sold(page, years="1995-1998")
    assert got == [{"date": "2024-03-25", "price": 32000}, {"date": "2024-06-01", "price": 70000}], got
    # Two different sales on one day stay two sales (no averaging)
    text_only = "Sold for USD $50,000 on 5/1/2024. Sold for USD $70,000 on 5/1/2024."
    assert bf.parse_bat_sold(text_only) == [{"date": "2024-05-01", "price": 50000}, {"date": "2024-05-01", "price": 70000}]


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


def test_undated_sold_figures_are_reference_only():
    pages = {"bat_search": BAT_PAGE, "carsandbids": '<div class="result">Sold for $45,000</div>'}
    sp.fetch = lambda client, url: pages["bat_search" if "bringatrailer" in url else "carsandbids"]
    sp.DELAY = 0
    car = {"id": "r33", "label": "Nissan Skyline R33 GT-R", "fallback_avg": 40000, "sources": [
        {"type": "bat_search", "url": "https://bringatrailer.com/x", "years": "1995-1998"},
        {"type": "carsandbids", "url": "https://carsandbids.com/x"}]}
    r = sp.scrape_car(None, car)
    assert [x["listing_id"] for x in r["sales"]] == ["101", "104"]
    assert r["sold_ref"] == 45000 and r["confidence"] == "thin" and r["avg_price"] == 40000
    assert sorted(x["reason"] for x in r["rejected"]) == ["model year", "unsold"]


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


def test_carsandbids_counts_once():
    page = '<div class="auction-result">Sold for $45,000</div>'
    assert sp.scrape_carsandbids(page) == [45000]


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} passed")
