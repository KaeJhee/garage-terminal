#!/usr/bin/env python3
"""
scrape_prices.py
================
Scrapes current average market prices for EVERY car defined in
frontend/cars.config.js — both WATCHLIST and TICKER_UNIVERSE.

KEY DESIGN PRINCIPLE
--------------------
This script reads cars.config.js as the single source of truth.
You never edit this file when adding a new car. Just add the car to
cars.config.js (with bat_url, market_url, and avg_price fields) and
the scraper picks it up automatically on the next run.

Bring a Trailer is the only source (the others block the runner):
  - bat_url     -> a Bring a Trailer search. BaT often redirects a search to
                   a model page (e.g. /mclaren/720s/); its completed auctions
                   are read from the page's embedded JSON as well as its cards.
  - scrape_extras entries of type 'bat_search' are extra BaT searches, each
    with its own filters:
      scrape_extras: [
        { type: 'bat_search', url: 'https://bringatrailer.com/search/?s=...',
          years: '2017-2020', include: ['Nismo'], exclude: ['Parts'] },
      ]
    Entries of any other type are logged as 'no scraper' and never fetched.
  - market_url is the dashboard's Market link only; it is not scraped.
Cars in category 'Chinese' are priced by hand and skipped.

Each car's avg_price in cars.config.js is used as the fallback if no
sources return data.

scraped_prices.json also records, per source, the HTTP status, final URL,
page kind (search or model), cards and embedded items seen, and reject
counts by reason. If no page anywhere shows a single sold result, the run
stops with an error before writing it.

Output: scraper/scraped_prices.json
Then run generate_history.py to regenerate frontend/data.js.

Usage:
    pip install httpx beautifulsoup4
    python scraper/scrape_prices.py

Environment variables:
    SCRAPE_DELAY_SEC   - seconds to wait between requests (default: 2)
    SCRAPE_DRY_RUN     - if "1", print results without writing file
    SCRAPE_LIMIT       - if set, only scrape the first N cars (debug)
    MIN_SALES_FOR_PRICE - qualifying sales needed before a tracked price updates (default: 3)
    RECENT_DAYS        - how far back a dated sale counts toward the price (default: 730)
"""

import json
import os
import re
import statistics
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from html import unescape

UTC = timezone.utc
from pathlib import Path

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit(
        "Missing dependencies. Run:  pip install httpx beautifulsoup4"
    )

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DELAY   = float(os.getenv("SCRAPE_DELAY_SEC", "2"))
DRY_RUN = os.getenv("SCRAPE_DRY_RUN", "0") == "1"
LIMIT   = int(os.getenv("SCRAPE_LIMIT", "0")) or None
MIN_SALES_FOR_PRICE = int(os.getenv("MIN_SALES_FOR_PRICE", "3"))
RECENT_DAYS         = int(os.getenv("RECENT_DAYS", "730"))

ROOT          = Path(__file__).parent.parent
CONFIG_PATH   = ROOT / "frontend" / "cars.config.js"
OUTPUT_PATH   = Path(__file__).parent / "scraped_prices.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ---------------------------------------------------------------------------
# Load cars from cars.config.js (single source of truth)
# ---------------------------------------------------------------------------

def load_cars_from_config() -> list[dict]:
    """
    Read frontend/cars.config.js and return a unified list of all cars
    (WATCHLIST + TICKER_UNIVERSE) with the fields needed for scraping, plus
    the price band and cost fields generate_history.py uses.

    Uses Node.js to evaluate the JS file - both WATCHLIST and TICKER_UNIVERSE
    are pure data declarations, no browser APIs needed.
    """
    if not CONFIG_PATH.exists():
        raise SystemExit(f"cars.config.js not found at {CONFIG_PATH}")

    # Tiny inline node script: read file, eval as a function body so the
    # var declarations become locals, return WATCHLIST + TICKER_UNIVERSE
    # combined and shaped for the scraper.
    js_extractor = r"""
        const fs = require('fs');
        const path = process.argv[1];
        const code = fs.readFileSync(path, 'utf-8');
        const fn = new Function(code + '; return { WATCHLIST, TICKER_UNIVERSE };');
        const data = fn();
        const all = [...data.WATCHLIST, ...data.TICKER_UNIVERSE];
        const out = all.map(c => {
            const cto = c.cost_to_own || {};
            return {
                id:         c.id,
                label:      [c.make, c.model].filter(Boolean).join(' '),
                category:   c.category || null,
                bat_url:    c.bat_url || null,
                avg_price:  c.avg_price || 0,
                low_price:  c.low_price || 0,
                high_price: c.high_price || 0,
                import_duty_pct:    cto.import_duty_pct || 0,
                shipping_est:       cto.shipping_est || 0,
                registration_est:   cto.registration_est || 0,
                insurance_annual:   cto.insurance_annual || 0,
                maintenance_annual: cto.maintenance_annual || 0,
                years:      c.years || null,
                title_include: c.bat_title_include || null,
                title_exclude: c.bat_title_exclude || null,
                extras:     c.scrape_extras || [],
            };
        });
        process.stdout.write(JSON.stringify(out));
    """

    try:
        result = subprocess.run(
            ["node", "-e", js_extractor, str(CONFIG_PATH)],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except FileNotFoundError:
        raise SystemExit(
            "Node.js is required to parse cars.config.js. Install it from "
            "https://nodejs.org or via 'brew install node' on macOS."
        )
    except subprocess.CalledProcessError as e:
        raise SystemExit(
            f"Failed to parse cars.config.js:\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
        )

    cars = json.loads(result.stdout)

    # Build the source list per car: bat_url plus any extras
    for car in cars:
        sources = []
        if car.get("bat_url"):
            sources.append({
                "type":        "bat_search",
                "url":         car["bat_url"],
                "search_term": car["label"],
                "years":       car.get("years"),
                "include":     car.get("title_include"),
                "exclude":     car.get("title_exclude"),
                "note":        "auto: bat_url",
            })
        # Per-car extras: 'bat_search' entries are scraped, other types are logged and skipped
        for extra in car.get("extras", []) or []:
            if extra.get("type") and extra.get("url"):
                sources.append({
                    "type": extra["type"],
                    "url":  extra["url"],
                    "note": "extra",
                    **{k: v for k, v in extra.items() if k not in ("type", "url")},
                })
        car["sources"]      = sources
        car["fallback_avg"] = car["avg_price"]

    return cars


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch(client: httpx.Client, url: str):
    """GET a page, following redirects. Returns (status, final_url, html).
    html is None when the request failed or came back with an error status
    (BaT answers a search that has no results with 404)."""
    try:
        r = client.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    except Exception as e:
        print(f"    WARN  fetch failed for {url[:70]}...  -> {e}")
        return None, url, None
    if r.is_error:
        print(f"    WARN  HTTP {r.status_code} for {url[:70]}...")
        return r.status_code, str(r.url), None
    return r.status_code, str(r.url), r.text


def is_bat_url(url: str) -> bool:
    return bool(re.match(r"https?://(www\.)?bringatrailer\.com/", url or "", re.I))


# ---------------------------------------------------------------------------
# Bring a Trailer pages
# ---------------------------------------------------------------------------

# scrape_bat_search leaves the cards it rejected and the page's counts here for scrape_car
_SCRAPE_STATS = {"bat_rejects": [], "bat_page": {}}

REJECT_REASONS = ("unsold", "model year", "title filter", "implausible")

def parse_years(years):
    """'1995-1998' -> (1995, 1998); '2023-Present' -> (2023, next year), since
    next year's models go on sale during the current one.
    A single year like '2022' is a representative model year, not a hard
    range, so it returns None and no year filter is applied."""
    if not years:
        return None
    m = re.match(r"\s*(\d{4})\s*-\s*(\d{4}|present)\s*$", str(years), re.I)
    if not m:
        return None
    lo = int(m.group(1))
    hi = date.today().year + 1 if m.group(2).lower() == "present" else int(m.group(2))
    return (lo, hi)


def title_year(title: str):
    m = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", title or "")
    return int(m.group(1)) if m else None


def bat_listing(listing_id, url, title, result_text, timestamp_end) -> dict:
    """One BaT listing, in the shape both page readers return:
    {listing_id, url, title, sold, price, date}. result_text is the result
    line, such as 'Sold for USD $32,000 on 3/25/2024' or 'Bid to USD $61,000
    on 4/1/2024'; without a date in it, the auction end timestamp is used."""
    text = re.sub(r"\s+", " ", result_text or "").strip()
    pm = re.search(r"\$\s*([\d,]+)", text)
    dm = re.search(r"on\s+(\d{1,2})/(\d{1,2})/(\d{4})", text)
    day = None
    if dm:
        day = date(int(dm.group(3)), int(dm.group(1)), int(dm.group(2))).isoformat()
    elif str(timestamp_end or "").isdigit():
        day = datetime.fromtimestamp(int(timestamp_end), UTC).date().isoformat()
    return {
        "listing_id": listing_id,
        "url":        url,
        "title":      title,
        "sold":       bool(re.match(r"sold\b", text, re.I)),
        "price":      int(pm.group(1).replace(",", "")) if pm else None,
        "date":       day,
    }


def parse_bat_cards(html: str) -> list:
    """Every listing card on a BaT page, sold or not:
    [{listing_id, url, title, sold, price, date}]. Cards carry a
    data-listing_id, a title link, and a result line such as
    'Sold for USD $32,000 on 3/25/2024' or 'Bid to USD $61,000 on 4/1/2024'."""
    soup = BeautifulSoup(html, "html.parser")
    cards, seen = [], set()
    for card in soup.select("[data-listing_id]"):
        lid = card.get("data-listing_id")
        if not lid or lid in seen:
            continue
        seen.add(lid)
        link = card.select_one("h3 a[href]") or card.select_one('a[href*="/listing/"]')
        result = card.select_one(".item-results")
        cards.append(bat_listing(lid, link["href"] if link else None,
                                 link.get_text(" ", strip=True) if link else "",
                                 result.get_text(" ", strip=True) if result else "",
                                 card.get("data-timestamp_end", "")))
    return cards


def parse_bat_model_items(html: str):
    """A BaT model page (a search often redirects to one, e.g. /mclaren/720s/)
    renders few or no cards, but embeds its 24 most recent completed auctions
    as JSON: 'var auctionsCompletedInitialData = {"items": [...]};'. Returns
    those auctions in the parse_bat_cards shape, or None when the page has no
    such JSON (a search page)."""
    m = re.search(r"\bvar\s+auctionsCompletedInitialData\s*=\s*", html)
    if not m:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError as e:
        print(f"       WARN  model page auction data unreadable: {e}")
        return []
    items = []
    for it in data.get("items") or []:
        if not it.get("id"):
            continue
        result = unescape(re.sub(r"<[^>]+>", " ", it.get("sold_text") or ""))
        items.append(bat_listing(str(it["id"]), it.get("url"), unescape(it.get("title") or "").strip(),
                                 result, it.get("timestamp_end")))
    return items


def card_verdict(card, span, include=None, exclude=None):
    """Why a listing card doesn't count as a sale for this car, or None if it does.
    include: the title must contain one of these (a trim, e.g. 'Turbo II').
    exclude: skip titles containing any of these (e.g. 'Aperta')."""
    if not card["sold"]:
        return "unsold"
    y = title_year(card["title"])
    # Every car listing's title starts with its model year; wheels, engines and other parts have none
    if y is None:
        return "model year"
    if span and not (span[0] <= y <= span[1]):
        return "model year"
    t = (card["title"] or "").lower()
    if include and not any(k.lower() in t for k in include):
        return "title filter"
    if exclude and any(k.lower() in t for k in exclude):
        return "title filter"
    return None


def scrape_bat_search(html: str, search_term: str = "", years=None, include=None, exclude=None, **_) -> list:
    """Real BaT sales for this car: one dict per SOLD listing, keyed by its
    listing ID, dated to the auction end. Reads the page's listing cards and,
    on a model page, its embedded completed auctions, counting each listing
    once. Unsold auctions ('Bid to'), listings outside the car's model years,
    and titles failing the car's include or exclude words are skipped and
    reported as rejects. The page's counts go to _SCRAPE_STATS['bat_page']."""
    _SCRAPE_STATS["bat_rejects"], _SCRAPE_STATS["bat_page"] = [], {}
    if not html:
        return []
    span = parse_years(years)
    cards = parse_bat_cards(html)
    items = parse_bat_model_items(html)
    listings = {}
    for c in cards + (items or []):
        have = listings.get(c["listing_id"])
        if have is None or (have["price"] is None and c["price"]):
            listings[c["listing_id"]] = c
    sales, rejects = [], []
    counts = dict.fromkeys(REJECT_REASONS, 0)
    for c in listings.values():
        if not c["price"]:
            continue
        if not (5000 <= c["price"] <= 3_000_000):
            counts["implausible"] += 1
            continue
        why = card_verdict(c, span, include, exclude)
        if why:
            counts[why] += 1
            if c["date"]:
                rejects.append({"listing_id": c["listing_id"], "price": c["price"], "date": c["date"], "reason": why})
            continue
        sales.append({"listing_id": c["listing_id"], "url": c["url"], "title": c["title"],
                      "price": c["price"], "date": c["date"], "venue": "bat"})
    _SCRAPE_STATS["bat_rejects"] = rejects
    _SCRAPE_STATS["bat_page"] = {
        "kind":      "search" if items is None else "model",
        "cards":     len(cards),
        "items":     len(items or []),
        "sold_seen": sum(1 for c in listings.values() if c["sold"]),
        "rejects":   counts,
    }
    return sales


# ---------------------------------------------------------------------------
# Per-car scraping
# ---------------------------------------------------------------------------

def decide_price(sales, fallback, today=None):
    """Price = MEDIAN of recent real sales (resists outliers; right-skewed
    collector prices make a mean misleading). Only dated sales that ended
    within RECENT_DAYS count. Fewer than MIN_SALES_FOR_PRICE of them is too
    thin to move the tracked price, so it stays at the fallback.
    Returns (price, confidence, recent_sales)."""
    today = today or date.today()
    cutoff = (today - timedelta(days=RECENT_DAYS)).isoformat()
    recent = [s for s in sales if s.get("date") and s["date"] >= cutoff]
    if len(recent) >= MIN_SALES_FOR_PRICE:
        return int(statistics.median(s["price"] for s in recent)), "scraped", recent
    if sales:
        return fallback, "thin", recent
    return fallback, "fallback", recent


def scrape_car(client: httpx.Client, car: dict, today=None) -> dict:
    car_id   = car["id"]
    label    = car["label"]
    fallback = car["fallback_avg"]
    sales, rejected = [], []   # sold BaT listings {price, date, listing_id, ...}; cards that don't count
    diags = []                 # one per source: what was fetched and what the page held

    print(f"\n  [{car_id}] {label}")
    sources = car["sources"]
    if car.get("category") == "Chinese":
        print("    --  category 'Chinese' is priced by hand, not scraped")
        sources = []
    for source in sources:
        url = source["url"]
        print(f"    -> {source['type']}: {url[:65]}...")
        diag = {"type": source["type"], "url": url}
        diags.append(diag)
        if source["type"] != "bat_search":
            diag["skipped"] = "no scraper"
            print(f"       --  no scraper for type '{source['type']}', not fetched")
            continue
        if not is_bat_url(url):
            diag["skipped"] = "not a Bring a Trailer URL"
            print("       --  not a Bring a Trailer URL, not fetched")
            continue
        status, final_url, html = fetch(client, url)
        diag["status"], diag["final_url"] = status, final_url
        if status == 404:
            diag["note"] = "no results (BaT returns 404 for a search with no results)"
            print("       --  no results: BaT answered 404")
        if html:
            kw = {k: v for k, v in source.items() if k not in ("type", "url", "note")}
            found = scrape_bat_search(html, **kw)
            page = _SCRAPE_STATS["bat_page"]
            diag.update(page)
            rejected += _SCRAPE_STATS["bat_rejects"]
            have = {s["listing_id"] for s in sales}
            found = [s for s in found if s["listing_id"] not in have]   # another source already counted it
            if fallback:
                lo_b, hi_b = fallback * 0.25, fallback * 4.0
                kept = [s for s in found if lo_b <= s["price"] <= hi_b]
                if len(kept) != len(found):
                    print(f"       filtered {len(found)-len(kept)} implausible price(s)")
                page["rejects"]["implausible"] += len(found) - len(kept)
                found = kept
            diag["counted"] = len(found)
            sales += found
            moved = f" -> {final_url}" if final_url != url else ""
            print(f"       {page['kind']} page{moved}: {page['cards']} cards, {page['items']} embedded auctions, "
                  f"{page['sold_seen']} sold; rejects: " + (", ".join(f"{k} {v}" for k, v in page["rejects"].items() if v) or "none"))
            if found:
                print(f"       OK  {len(found)} sold (median ${int(statistics.median(s['price'] for s in found)):,})")
            else:
                print("       --  no sold listings counted")
        time.sleep(DELAY)

    avg, confidence, recent = decide_price(sales, fallback, today)
    if confidence == "scraped":
        print(f"    OK  {car_id}: median ${avg:,}  (n={len(recent)} recent sold)")
    elif confidence == "thin":
        print(f"    ~~  {car_id}: only {len(recent)} recent sale(s), keeping ${avg:,} (needs {MIN_SALES_FOR_PRICE})")
    else:
        print(f"    -- {car_id}: no sold data, fallback ${avg:,}")

    return {
        "id":         car_id,
        "label":      label,
        "avg_price":  avg,              # median of recent sold
        "confidence": confidence,
        "sales":      sales,            # every sold listing found, with id + real date
        "rejected":   rejected,         # unsold / wrong-year / filtered cards seen, for purging old entries
        "sold_seen":  sum(d.get("sold_seen", 0) for d in diags),   # sold results on the pages, before any filter
        "sources":    diags,            # per source: status, final_url, kind, cards, items, reject counts
        "scraped_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("GARAGE TERMINAL - Price Scraper")
    print(f"Started: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    print(f"\nLoading cars from {CONFIG_PATH.relative_to(ROOT)}...")
    cars = load_cars_from_config()
    if LIMIT:
        cars = cars[:LIMIT]
        print(f"  (SCRAPE_LIMIT={LIMIT}: only scraping first {LIMIT} cars)")
    print(f"Loaded {len(cars)} cars total")

    skipped = [c for c in cars if not c["sources"]]
    if skipped:
        print(f"  WARN  {len(skipped)} cars have no bat_url, will use fallback only:")
        for c in skipped:
            print(f"        - {c['id']}")

    results = []
    with httpx.Client() as client:
        for car in cars:
            result = scrape_car(client, car)
            results.append(result)

    # A BaT layout change reads as zero sold results everywhere. Stop before
    # writing, so the weekly job fails instead of committing an empty week.
    if results and not any(r["sold_seen"] for r in results):
        raise SystemExit("ERROR  No page showed a single sold result. Bring a Trailer may have changed its "
                         "layout or blocked the runner. scraped_prices.json was NOT written.")

    output = {
        "scraped_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "total_cars": len(results),
        "scraped":    sum(1 for r in results if r["confidence"] == "scraped"),
        "fallback":   sum(1 for r in results if r["confidence"] == "fallback"),
        "thin":       sum(1 for r in results if r["confidence"] == "thin"),
        "prices":     {r["id"]: r for r in results},
    }

    print("\n" + "=" * 60)
    print(f"Summary: {output['scraped']} scraped, {output['thin']} thin, {output['fallback']} fallback, "
          f"{output['total_cars']} total")
    print("=" * 60)

    if DRY_RUN:
        print("\n[DRY RUN] Would write:\n")
        print(json.dumps(output, indent=2)[:2000])
    else:
        OUTPUT_PATH.write_text(json.dumps(output, indent=2))
        print(f"\nWrote {len(results)} results -> {OUTPUT_PATH}")

    return output


if __name__ == "__main__":
    main()
