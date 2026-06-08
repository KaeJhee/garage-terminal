#!/usr/bin/env python3
"""
backfill_history.py
===================
Seeds frontend/price_history.json with REAL historical sales scraped from
Bring a Trailer completed-auction pages. Run this ONCE per car (or
occasionally) to give the charts real past data instead of waiting weeks
for the forward accumulation to build up.

Each real sale becomes an "observed" point with source "bat-backfill".
generate_history.py then interpolates the daily chart line between them.

Idempotent: a sale on a date already present for a car is not duplicated.

IMPORTANT: BaT uses Cloudflare bot protection and the exact page markup
changes over time. The fetch+parse against the LIVE site must be validated
in your environment (this cannot be tested from a sandbox that can't reach
bringatrailer.com). The parser below is defensive: it extracts (date, price)
pairs from sold-listing markup and falls back to text patterns. Verify the
counts it reports look sane before trusting the data.

Usage:
    python scraper/backfill_history.py                 # all cars with a bat_url
    python scraper/backfill_history.py --car r33-gtr   # one car
    python scraper/backfill_history.py --dry-run       # parse + report, write nothing
"""

import argparse, json, re, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc

ROOT               = Path(__file__).parent.parent
PRICE_HISTORY_PATH = ROOT / "frontend" / "price_history.json"
CONFIG_JS_PATH     = ROOT / "frontend" / "cars.config.js"

DELAY = 3.0          # politeness delay between requests
MIN_PRICE = 3000
MAX_PRICE = 5_000_000

try:
    import httpx
    from bs4 import BeautifulSoup
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Config + history IO
# ---------------------------------------------------------------------------

def load_cars():
    js = r"""
        const fs=require('fs');
        const code=fs.readFileSync(process.argv[1],'utf-8');
        const fn=new Function(code+'; return {WATCHLIST,TICKER_UNIVERSE};');
        const d=fn(); const all=[...d.WATCHLIST,...d.TICKER_UNIVERSE]; const out=[];
        all.forEach(c=>{ if(c.id) out.push({id:c.id,label:(c.make||'')+' '+(c.model||''),bat_url:c.bat_url||''}); });
        process.stdout.write(JSON.stringify(out));
    """
    r = subprocess.run(["node","-e",js,str(CONFIG_JS_PATH)],
                       capture_output=True, text=True, check=True, timeout=15)
    return json.loads(r.stdout)

def load_history():
    return json.loads(PRICE_HISTORY_PATH.read_text()) if PRICE_HISTORY_PATH.exists() else {}

def save_history(h):
    PRICE_HISTORY_PATH.write_text(json.dumps(h, separators=(",", ":")))

# ---------------------------------------------------------------------------
# Parsing (testable without network)
# ---------------------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(
    ["january","february","march","april","may","june","july","august",
     "september","october","november","december"], 1)}

def parse_bat_sold(html: str) -> list:
    """
    Extract real sold listings as [{date: ISO, price: int}] from a BaT
    completed-auction page. Defensive: tries structured listing cards first,
    then falls back to 'Sold for $X on Month DD, YYYY' text patterns.
    Returns deduped, date-sorted list.
    """
    if not html:
        return []
    sales = []

    # Pattern: "sold for $73,000 on 4/12/24" or "Sold for USD $73,000 on April 12, 2024"
    text = re.sub(r"\s+", " ", html)

    # numeric date form: $73,000 on 4/12/24  or  4/12/2024
    for m in re.finditer(
        r"sold\s+for\s+(?:usd\s*)?\$?([\d,]{4,})\D{0,40}?(\d{1,2})/(\d{1,2})/(\d{2,4})",
        text, re.I):
        price = _to_int(m.group(1))
        mo, da, yr = int(m.group(2)), int(m.group(3)), int(m.group(4))
        yr = yr + 2000 if yr < 100 else yr
        d = _safe_date(yr, mo, da)
        if price and d:
            sales.append({"date": d, "price": price})

    # month-name date form: $73,000 on April 12, 2024
    for m in re.finditer(
        r"sold\s+for\s+(?:usd\s*)?\$?([\d,]{4,})\D{0,40}?"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})",
        text, re.I):
        price = _to_int(m.group(1))
        mo = MONTHS.get(_full_month(m.group(2).lower()), 0)
        da, yr = int(m.group(3)), int(m.group(4))
        d = _safe_date(yr, mo, da)
        if price and d:
            sales.append({"date": d, "price": price})

    # Structured cards (BeautifulSoup) - best-effort, markup varies
    if HAVE_DEPS:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for card in soup.find_all(class_=re.compile(r"listing|result|auction", re.I)):
                t = card.get_text(" ", strip=True)
                pm = re.search(r"\$([\d,]{4,})", t)
                dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
                if pm and dm:
                    price = _to_int(pm.group(1))
                    yr = int(dm.group(3)); yr = yr + 2000 if yr < 100 else yr
                    d = _safe_date(yr, int(dm.group(1)), int(dm.group(2)))
                    if price and d:
                        sales.append({"date": d, "price": price})
        except Exception:
            pass

    # Dedup by date: AVERAGE multiple sales on the same date (more accurate
    # than keeping the first), filter price range, sort chronologically.
    by_date = {}
    for s in sales:
        if MIN_PRICE <= s["price"] <= MAX_PRICE:
            by_date.setdefault(s["date"], []).append(s["price"])
    return [{"date": d, "price": round(sum(v) / len(v))} for d, v in sorted(by_date.items())]

def _to_int(s):
    try:
        v = int(s.replace(",", ""))
        return v if MIN_PRICE <= v <= MAX_PRICE else None
    except ValueError:
        return None

def _full_month(abbr):
    for full in MONTHS:
        if full.startswith(abbr):
            return full
    return ""

def _safe_date(y, m, d):
    try:
        return datetime(y, m, d).date().isoformat()
    except ValueError:
        return None

# ---------------------------------------------------------------------------
# Merge into price_history.json
# ---------------------------------------------------------------------------

def merge_sales(history: dict, car_id: str, sales: list) -> int:
    entry = history.setdefault(car_id, {"sales": [], "synthetic": []})
    existing = {(s["date"], s["price"]) for s in entry["sales"]}
    added = 0
    for s in sales:
        key = (s["date"], round(s["price"]))
        if key in existing:
            continue
        entry["sales"].append({"date": s["date"], "price": round(s["price"]),
                               "venue": "bat-backfill"})
        existing.add(key)
        added += 1
    entry["sales"].sort(key=lambda p: p["date"])
    return added

# ---------------------------------------------------------------------------
# Fetch + run
# ---------------------------------------------------------------------------

def fetch(client, url, retries=1):
    for attempt in range(retries + 1):
        try:
            r = client.get(url, timeout=25, follow_redirects=True)
            if r.status_code == 200:
                return r.text
            # 403/404 on BaT search is often transient rate-limiting; retry once.
            if r.status_code in (403, 404) and attempt < retries:
                print(f"    HTTP {r.status_code} - retrying in {DELAY:.0f}s")
                time.sleep(DELAY)
                continue
            print(f"    HTTP {r.status_code} (BaT bot protection likely)")
            return None
        except Exception as e:
            if attempt < retries:
                print(f"    fetch error: {e} - retrying in {DELAY:.0f}s")
                time.sleep(DELAY)
                continue
            print(f"    fetch error: {e}")
            return None
    return None

def run(only_car=None, dry_run=False):
    if not HAVE_DEPS:
        raise SystemExit("Requires httpx + beautifulsoup4 (pip install -r requirements.txt)")
    cars = load_cars()
    if only_car:
        cars = [c for c in cars if c["id"] == only_car]
        if not cars:
            raise SystemExit(f"Car '{only_car}' not found")
    history = load_history()
    total_added = 0
    with httpx.Client(headers=HEADERS) as client:
        for c in cars:
            if not c["bat_url"]:
                print(f"--  {c['id']}: no bat_url, skip")
                continue
            print(f"\n[{c['id']}] {c['label']}\n    GET {c['bat_url'][:70]}")
            html = fetch(client, c["bat_url"])
            sales = parse_bat_sold(html)
            print(f"    parsed {len(sales)} real sold listings")
            if sales and not dry_run:
                added = merge_sales(history, c["id"], sales)
                total_added += added
                print(f"    +{added} new observed points")
            elif sales:
                print(f"    (dry-run) would add up to {len(sales)} points")
            time.sleep(DELAY)
    if not dry_run:
        save_history(history)
        print(f"\nOK  Backfill complete: +{total_added} real sales into price_history.json")
        print("    Now run generate_history.py to rebuild data.js.")
    else:
        print("\nDry-run complete: nothing written.")

def main():
    ap = argparse.ArgumentParser(description="Garage Terminal - BaT historical backfill")
    ap.add_argument("--car", help="Backfill a single car id")
    ap.add_argument("--dry-run", action="store_true", help="Parse + report, write nothing")
    args = ap.parse_args()
    print("=" * 60); print("GARAGE TERMINAL - BaT Historical Backfill"); print("=" * 60)
    run(only_car=args.car, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
