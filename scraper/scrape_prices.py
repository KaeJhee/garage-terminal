#!/usr/bin/env python3
"""
scrape_prices.py
================
Scrapes current average market prices for each car in WATCHLIST
from classic.com and Bring a Trailer (BaT).

Sources used per car:
  • classic.com market pages  — JDM/classic cars (R33, R32, Supra, Lamborghini)
  • Bring a Trailer            — completed auction data (JDM cars)
  • KBB                        — modern cars (R35 GT-R)
  • Edmunds / CarGurus         — fallback for any car

Results are written to: scraper/scraped_prices.json

Then run generate_history.py to regenerate frontend/data.js.

Usage:
    pip install httpx beautifulsoup4
    python scraper/scrape_prices.py

Environment variables (optional):
    SCRAPE_DELAY_SEC   — seconds to wait between requests (default: 2)
    SCRAPE_DRY_RUN     — if "1", print results without writing file
"""

import json
import os
import re
import time
import statistics
from datetime import datetime
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

DELAY = float(os.getenv("SCRAPE_DELAY_SEC", "2"))
DRY_RUN = os.getenv("SCRAPE_DRY_RUN", "0") == "1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OUTPUT_PATH = Path(__file__).parent / "scraped_prices.json"

# ---------------------------------------------------------------------------
# Car targets — mirrors WATCHLIST in cars.config.js
# Add a new car here when you add it to cars.config.js
# ---------------------------------------------------------------------------

CARS = [
    {
        "id": "r33-gtr",
        "label": "Nissan Skyline R33 GT-R",
        "sources": [
            {
                "type": "classic_com",
                "url": "https://www.classic.com/m/nissan/skyline/r33/gt-r/",
                "note": "classic.com R33 GT-R market page",
            },
            {
                "type": "bat_search",
                "url": "https://bringatrailer.com/listing/category/nissan/?s=skyline+r33+gt-r",
                "search_term": "r33 gt-r",
                "note": "BaT completed auctions",
            },
        ],
        "fallback_avg": 77396,
    },
    {
        "id": "r32-gtr",
        "label": "Nissan Skyline R32 GT-R",
        "sources": [
            {
                "type": "classic_com",
                "url": "https://www.classic.com/m/nissan/skyline/r32/gt-r/",
                "note": "classic.com R32 GT-R market page",
            },
            {
                "type": "bat_search",
                "url": "https://bringatrailer.com/listing/category/nissan/?s=skyline+r32+gt-r",
                "search_term": "r32 gt-r",
                "note": "BaT completed auctions",
            },
        ],
        "fallback_avg": 53401,
    },
    {
        "id": "supra-a80",
        "label": "Toyota Supra MK4 A80",
        "sources": [
            {
                "type": "classic_com",
                "url": "https://www.classic.com/m/toyota/supra/",
                "note": "classic.com Supra market page",
            },
            {
                "type": "bat_search",
                "url": "https://bringatrailer.com/listing/category/toyota/?s=supra+mk4",
                "search_term": "toyota supra mk4",
                "note": "BaT completed auctions",
            },
            {
                "type": "cargurus",
                "url": "https://www.cargurus.com/research/price-trends/Toyota-Supra-d309",
                "note": "CarGurus price trends",
            },
        ],
        "fallback_avg": 50000,
    },
    {
        "id": "r35-gtr",
        "label": "Nissan GT-R R35 (2020)",
        "sources": [
            {
                "type": "kbb",
                "url": "https://www.kbb.com/nissan/gt-r/2020/",
                "note": "KBB fair purchase price",
            },
            {
                "type": "classic_com",
                "url": "https://www.classic.com/m/nissan/gt-r/r35/",
                "note": "classic.com R35 market page",
            },
        ],
        "fallback_avg": 106000,
    },
    {
        "id": "huracan-sto",
        "label": "Lamborghini Huracán STO (2022)",
        "sources": [
            {
                "type": "classic_com",
                "url": "https://www.classic.com/m/lamborghini/huracan/sto/",
                "note": "classic.com Huracán STO market page",
            },
            {
                "type": "edmunds",
                "url": "https://www.edmunds.com/lamborghini/huracan-sto/2022/",
                "note": "Edmunds used price",
            },
        ],
        "fallback_avg": 427632,
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch(client: httpx.Client, url: str) -> str | None:
    """Fetch a URL and return HTML text, or None on error."""
    try:
        r = client.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  ⚠  fetch error {url[:60]}…  →  {e}")
        return None


def extract_prices_from_text(text: str, min_price=5000, max_price=3_000_000) -> list[int]:
    """
    Pull dollar amounts from raw text.
    Looks for patterns like $45,000  |  $1.2M  |  45000  near keyword 'price'
    """
    prices = []
    # $123,456 or $123456
    for m in re.finditer(r'\$\s*([\d,]+)', text):
        val = int(m.group(1).replace(',', ''))
        if min_price <= val <= max_price:
            prices.append(val)
    # $1.2M / $450K
    for m in re.finditer(r'\$\s*([\d.]+)\s*([KMkm])', text):
        num, suffix = float(m.group(1)), m.group(2).upper()
        val = int(num * (1_000_000 if suffix == 'M' else 1_000))
        if min_price <= val <= max_price:
            prices.append(val)
    return prices


# ---------------------------------------------------------------------------
# Source-specific scrapers
# ---------------------------------------------------------------------------

def scrape_classic_com(html: str, car_id: str) -> int | None:
    """
    classic.com market pages show an 'Average' or 'Avg Sale' figure.
    The page structure can vary, so we try multiple selectors.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: look for the stat block with label "Average" or "Avg"
    for tag in soup.find_all(string=re.compile(r'\bAvg(erage)?\b', re.I)):
        parent = tag.find_parent()
        if parent:
            # The price is typically the next sibling or nearby element
            sib = parent.find_next_sibling()
            if sib:
                prices = extract_prices_from_text(sib.get_text())
                if prices:
                    return prices[0]
            # Try the parent's text
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]

    # Strategy 2: look for JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            # Walk the JSON looking for price-like numbers
            text = json.dumps(data)
            prices = extract_prices_from_text(text)
            if prices:
                return int(statistics.median(prices))
        except Exception:
            pass

    # Strategy 3: brute-force — grab all dollar amounts from the page
    # and take the median as a rough average
    all_prices = extract_prices_from_text(soup.get_text())
    if len(all_prices) >= 3:
        return int(statistics.median(all_prices))

    return None


def scrape_bat_search(html: str, search_term: str) -> int | None:
    """
    BaT search results — pull sold prices from completed listing cards.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    sold_prices = []

    # BaT uses various class names for the sold price; try a few patterns
    for tag in soup.find_all(class_=re.compile(r'sold|result|price', re.I)):
        prices = extract_prices_from_text(tag.get_text())
        sold_prices.extend(prices)

    # Fallback: scan all text for dollar amounts near the word "sold"
    full_text = soup.get_text()
    for m in re.finditer(r'sold[^$]{0,30}\$([\d,]+)', full_text, re.I):
        try:
            val = int(m.group(1).replace(',', ''))
            if 5000 <= val <= 3_000_000:
                sold_prices.append(val)
        except ValueError:
            pass

    if len(sold_prices) >= 3:
        # Use recent results (first half of the list — BaT is newest-first)
        recent = sold_prices[:max(3, len(sold_prices)//2)]
        return int(statistics.mean(recent))

    if sold_prices:
        return int(statistics.mean(sold_prices))

    return None


def scrape_kbb(html: str) -> int | None:
    """KBB — extract 'Fair Market Range' or 'Fair Purchase Price'."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # Look for "Fair Purchase Price" label
    for tag in soup.find_all(string=re.compile(r'fair\s+purchase|fair\s+market', re.I)):
        parent = tag.find_parent()
        if parent:
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]
            # Try surrounding section
            section = parent.find_parent()
            if section:
                prices = extract_prices_from_text(section.get_text())
                if prices:
                    return int(statistics.median(prices))

    # Fallback: JSON-LD
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


def scrape_edmunds(html: str) -> int | None:
    """Edmunds — extract average listed price."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(string=re.compile(r'avg\s+list|average\s+list|typical', re.I)):
        parent = tag.find_parent()
        if parent:
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]

    all_prices = extract_prices_from_text(soup.get_text())
    if len(all_prices) >= 3:
        return int(statistics.median(all_prices))
    return None


def scrape_cargurus(html: str) -> int | None:
    """CarGurus — extract average price from research/price-trends page."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(string=re.compile(r'avg\s+list|average\s+price|market\s+avg', re.I)):
        parent = tag.find_parent()
        if parent:
            prices = extract_prices_from_text(parent.get_text())
            if prices:
                return prices[0]

    all_prices = extract_prices_from_text(soup.get_text())
    if len(all_prices) >= 3:
        return int(statistics.median(all_prices))
    return None


SCRAPER_MAP = {
    "classic_com": scrape_classic_com,
    "bat_search":  lambda html, **kw: scrape_bat_search(html, kw.get("search_term", "")),
    "kbb":         lambda html, **kw: scrape_kbb(html),
    "edmunds":     lambda html, **kw: scrape_edmunds(html),
    "cargurus":    lambda html, **kw: scrape_cargurus(html),
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scrape_car(client: httpx.Client, car: dict) -> dict:
    """Scrape all sources for a car and return a result dict."""
    car_id   = car["id"]
    label    = car["label"]
    fallback = car["fallback_avg"]
    prices_found = []

    print(f"\n  [{car_id}] {label}")
    for source in car["sources"]:
        src_type = source["type"]
        url      = source["url"]
        note     = source.get("note", "")
        print(f"    → {src_type}: {url[:60]}…")

        html = fetch(client, url)
        if html:
            fn = SCRAPER_MAP.get(src_type)
            if fn:
                kw = {k: v for k, v in source.items() if k not in ("type", "url", "note")}
                price = fn(html, **kw)
                if price:
                    print(f"       ✓ found price: ${price:,}")
                    prices_found.append(price)
                else:
                    print(f"       ✗ could not parse price from {src_type}")
            else:
                print(f"       ✗ no scraper for type '{src_type}'")
        time.sleep(DELAY)

    if prices_found:
        avg = int(statistics.mean(prices_found))
        print(f"    ✅ {car_id}: ${avg:,}  (from {len(prices_found)} source(s))")
        confidence = "scraped"
    else:
        avg = fallback
        print(f"    ⚠  {car_id}: using fallback ${avg:,}")
        confidence = "fallback"

    return {
        "id":         car_id,
        "label":      label,
        "avg_price":  avg,
        "confidence": confidence,
        "sources_hit": len(prices_found),
        "scraped_at": datetime.utcnow().isoformat() + "Z",
    }


def main():
    print("=" * 60)
    print("GARAGE TERMINAL — Price Scraper")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    results = []
    with httpx.Client() as client:
        for car in CARS:
            result = scrape_car(client, car)
            results.append(result)

    output = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "prices": {r["id"]: r for r in results},
    }

    if DRY_RUN:
        print("\n[DRY RUN] Would write:\n")
        print(json.dumps(output, indent=2))
    else:
        OUTPUT_PATH.write_text(json.dumps(output, indent=2))
        print(f"\n✅ Wrote {len(results)} results → {OUTPUT_PATH}")

    return output


if __name__ == "__main__":
    main()
