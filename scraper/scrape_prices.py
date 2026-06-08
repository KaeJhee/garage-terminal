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

Sources used per car (auto-derived from cars.config.js):
  - market_url  -> classic.com market page (parsed by scrape_classic_com)
  - bat_url     -> Bring a Trailer search (parsed by scrape_bat_search)

Optional per-car overrides via cars.config.js:
  scrape_extras: [
    { type: 'kbb',      url: 'https://www.kbb.com/...' },
    { type: 'edmunds',  url: 'https://www.edmunds.com/...' },
    { type: 'cargurus', url: 'https://www.cargurus.com/...' },
  ]

Each car's avg_price in cars.config.js is used as the fallback if no
sources return data.

Output: scraper/scraped_prices.json
Then run generate_history.py to regenerate frontend/data.js.

Usage:
    pip install httpx beautifulsoup4
    python scraper/scrape_prices.py

Environment variables:
    SCRAPE_DELAY_SEC   - seconds to wait between requests (default: 2)
    SCRAPE_DRY_RUN     - if "1", print results without writing file
    SCRAPE_LIMIT       - if set, only scrape the first N cars (debug)
"""

import json
import os
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone

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
    (WATCHLIST + TICKER_UNIVERSE) with the fields needed for scraping.

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
        const out = all.map(c => ({
            id:         c.id,
            label:      [c.make, c.model].filter(Boolean).join(' '),
            bat_url:    c.bat_url || null,
            market_url: c.market_url || null,
            avg_price:  c.avg_price || 0,
            extras:     c.scrape_extras || [],
        }));
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

    # Build the source list per car (default 2 sources from URLs + any extras)
    for car in cars:
        sources = []
        if car.get("market_url"):
            sources.append({
                "type": "classic_com",
                "url":  car["market_url"],
                "note": "auto: market_url",
            })
        if car.get("bat_url"):
            sources.append({
                "type":        "bat_search",
                "url":         car["bat_url"],
                "search_term": car["label"],
                "note":        "auto: bat_url",
            })
        # Cars & Bids: build a completed-auction search URL from the label.
        # Modern enthusiast/JDM/exotic coverage; real sold results, scrapeable.
        cab_q = re.sub(r"\s+", "%20", car["label"].strip())
        if cab_q:
            sources.append({
                "type": "carsandbids",
                "url":  f"https://carsandbids.com/search/{cab_q}?status=ended",
                "note": "auto: carsandbids",
            })
        # Add any per-car extras (KBB, Edmunds, CarGurus, etc.)
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

def fetch(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    WARN  fetch failed for {url[:70]}...  -> {e}")
        return None


def extract_prices_from_text(text: str, min_price=5000, max_price=3_000_000) -> list[int]:
    prices = []
    for m in re.finditer(r"\$\s*([\d,]+)", text):
        val = int(m.group(1).replace(",", ""))
        if min_price <= val <= max_price:
            prices.append(val)
    for m in re.finditer(r"\$\s*([\d.]+)\s*([KMkm])", text):
        num, suffix = float(m.group(1)), m.group(2).upper()
        val = int(num * (1_000_000 if suffix == "M" else 1_000))
        if min_price <= val <= max_price:
            prices.append(val)
    return prices


# ---------------------------------------------------------------------------
# Source-specific scrapers
# ---------------------------------------------------------------------------

# Per-car volume accumulator. scrape_bat_search writes its real
# sold-listing count here; scrape_car reads it to set n_sales.
_SCRAPE_STATS = {"bat_sales": 0, "cab_sales": 0}

def scrape_classic_com(html: str, **_) -> int | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(string=re.compile(r"\bAvg(erage)?\b", re.I)):
        parent = tag.find_parent()
        if parent:
            sib = parent.find_next_sibling()
            if sib:
                prices = extract_prices_from_text(sib.get_text())
                if prices:
                    return prices[0]
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            text = json.dumps(data)
            prices = extract_prices_from_text(text)
            if prices:
                return int(statistics.median(prices))
        except Exception:
            pass

    all_prices = extract_prices_from_text(soup.get_text())
    if len(all_prices) >= 3:
        return int(statistics.median(all_prices))
    return None


def scrape_bat_search(html: str, search_term: str = "", **_) -> list:
    """Return ALL individual sold prices found (list[int]); [] if none.
    Returning the raw list lets the car aggregator compute a real median
    and a real sale count instead of a pre-averaged single value."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")

    sold_prices = []
    for tag in soup.find_all(class_=re.compile(r"sold|result|price", re.I)):
        sold_prices.extend(extract_prices_from_text(tag.get_text()))

    full_text = soup.get_text()
    for m in re.finditer(r"sold[^$]{0,30}\$([\d,]+)", full_text, re.I):
        try:
            val = int(m.group(1).replace(",", ""))
            if 5000 <= val <= 3_000_000:
                sold_prices.append(val)
        except ValueError:
            pass

    _SCRAPE_STATS["bat_sales"] = len(sold_prices)
    return sold_prices


def scrape_kbb(html: str, **_) -> int | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(string=re.compile(r"fair\s+purchase|fair\s+market", re.I)):
        parent = tag.find_parent()
        if parent:
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]
            section = parent.find_parent()
            if section:
                prices = extract_prices_from_text(section.get_text())
                if prices:
                    return int(statistics.median(prices))
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            text = json.dumps(data)
            prices = extract_prices_from_text(text)
            if prices:
                return int(statistics.median(prices))
        except Exception:
            pass
    return None


def scrape_edmunds(html: str, **_) -> int | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(string=re.compile(r"avg\s+list|average\s+list|typical", re.I)):
        parent = tag.find_parent()
        if parent:
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]
    all_prices = extract_prices_from_text(soup.get_text())
    if len(all_prices) >= 3:
        return int(statistics.median(all_prices))
    return None


def scrape_cargurus(html: str, **_) -> int | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(string=re.compile(r"avg\s+list|average\s+price|market\s+avg", re.I)):
        parent = tag.find_parent()
        if parent:
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]
    all_prices = extract_prices_from_text(soup.get_text())
    if len(all_prices) >= 3:
        return int(statistics.median(all_prices))
    return None


def scrape_carsandbids(html: str, **_) -> list:
    """Cars & Bids completed-auction results. Returns ALL individual sold
    prices (list[int]). C&B marks results with 'Sold for $X'; bids that did
    not meet reserve show 'Bid to $X' and are excluded (asking, not sold)."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    sold = []
    text = re.sub(r"\s+", " ", soup.get_text())
    # Only "Sold for $X" - exclude "Bid to $X" (reserve not met)
    for m in re.finditer(r"sold\s+for\s+\$?([\d,]{4,})", text, re.I):
        try:
            val = int(m.group(1).replace(",", ""))
            if 5000 <= val <= 3_000_000:
                sold.append(val)
        except ValueError:
            pass
    # structured cards
    for card in soup.find_all(class_=re.compile(r"auction|result|listing", re.I)):
        t = card.get_text(" ", strip=True)
        if re.search(r"sold\s+for", t, re.I):
            for p in extract_prices_from_text(t):
                if 5000 <= p <= 3_000_000:
                    sold.append(p)
    _SCRAPE_STATS["cab_sales"] = len(sold)
    return sold


SCRAPER_MAP = {
    "classic_com":  scrape_classic_com,
    "bat_search":   scrape_bat_search,
    "carsandbids":  scrape_carsandbids,
    "kbb":          scrape_kbb,
    "edmunds":      scrape_edmunds,
    "cargurus":     scrape_cargurus,
}

# Which source types are REAL SOLD transactions vs ASKING prices.
# Only SOLD sources feed the market price + sample count. Asking prices
# (dealer/retail listings) are kept for reference only - they bias high.
SOLD_SOURCES   = {"classic_com", "bat_search", "carsandbids"}
ASKING_SOURCES = {"kbb", "edmunds", "cargurus"}


# ---------------------------------------------------------------------------
# Per-car scraping
# ---------------------------------------------------------------------------

def scrape_car(client: httpx.Client, car: dict) -> dict:
    car_id   = car["id"]
    label    = car["label"]
    fallback = car["fallback_avg"]
    sold_prices   = []   # real individual sold transactions (drive the price)
    asking_prices = []   # dealer/retail asking (reference only, biased high)
    venues = []          # which sold venues returned data
    _SCRAPE_STATS["bat_sales"] = 0
    _SCRAPE_STATS["cab_sales"] = 0

    print(f"\n  [{car_id}] {label}")
    for source in car["sources"]:
        src_type = source["type"]
        url      = source["url"]
        print(f"    -> {src_type}: {url[:65]}...")

        html = fetch(client, url)
        if html:
            fn = SCRAPER_MAP.get(src_type)
            if fn:
                kw = {k: v for k, v in source.items() if k not in ("type", "url", "note")}
                result = fn(html, **kw)
                # normalize: scrapers may return list[int] (sold pools) or int (single)
                vals = result if isinstance(result, list) else ([result] if result else [])
                vals = [int(v) for v in vals if v]
                if vals:
                    if src_type in SOLD_SOURCES:
                        sold_prices.extend(vals)
                        venues.append(src_type)
                        print(f"       OK  {len(vals)} sold from {src_type} (median ${int(statistics.median(vals)):,})")
                    else:
                        asking_prices.extend(vals)
                        print(f"       ~~  {len(vals)} ASKING from {src_type} (reference only)")
                else:
                    print(f"       --  no price parsed from {src_type}")
            else:
                print(f"       --  no scraper for type '{src_type}'")
        time.sleep(DELAY)

    # Price = MEDIAN of real sold transactions (resists outliers; right-skewed
    # collector prices make mean misleading). Asking prices never set the price.
    if fallback:
        lo_b, hi_b = fallback * 0.25, fallback * 4.0
        kept = [p for p in sold_prices if lo_b <= p <= hi_b]
        if len(kept) != len(sold_prices):
            print(f"       filtered {len(sold_prices)-len(kept)} implausible price(s)")
        sold_prices = kept
    if sold_prices:
        avg = int(statistics.median(sold_prices))
        confidence = "scraped"
        print(f"    OK  {car_id}: median ${avg:,}  (n={len(sold_prices)} sold across {len(set(venues))} venue(s))")
    else:
        avg = fallback
        confidence = "fallback"
        print(f"    -- {car_id}: no sold data, fallback ${avg:,}")

    return {
        "id":           car_id,
        "label":        label,
        "avg_price":    avg,                       # median of sold
        "confidence":   confidence,
        "n_sales":      len(sold_prices),          # REAL sold count (sample size)
        "sold_prices":  sold_prices,               # individual sales (for scatter/backfill)
        "venues":       sorted(set(venues)),
        "asking_ref":   int(statistics.median(asking_prices)) if asking_prices else None,
        "scraped_at":   datetime.now(UTC).isoformat() + "Z",
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
        print(f"  WARN  {len(skipped)} cars have no bat_url or market_url, will use fallback only:")
        for c in skipped:
            print(f"        - {c['id']}")

    results = []
    with httpx.Client() as client:
        for car in cars:
            result = scrape_car(client, car)
            results.append(result)

    output = {
        "scraped_at": datetime.now(UTC).isoformat() + "Z",
        "total_cars": len(results),
        "scraped":    sum(1 for r in results if r["confidence"] == "scraped"),
        "fallback":   sum(1 for r in results if r["confidence"] == "fallback"),
        "prices":     {r["id"]: r for r in results},
    }

    print("\n" + "=" * 60)
    print(f"Summary: {output['scraped']} scraped, {output['fallback']} fallback, "
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
