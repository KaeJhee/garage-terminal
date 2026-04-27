#!/usr/bin/env python3
"""
generate_history.py
===================
Reads scraped_prices.json (output of scrape_prices.py) and regenerates
frontend/data.js with fresh 365-day price history for each car.

Also patches avg_price and prev_avg in cars.config.js so the watchlist
header stats reflect the latest scraped price.

KEY DESIGN PRINCIPLE
--------------------
This script reads cars.config.js as the single source of truth for
fallback prices in --dev mode. You never edit this file when adding a
new car. Just add the car to cars.config.js and the dev-mode fallback
will use its avg_price automatically.

Usage:
    # Normal (requires scraped_prices.json):
    python scraper/generate_history.py

    # Dev mode - uses fallback prices from cars.config.js, no scraper needed:
    python scraper/generate_history.py --dev

    # Watch mode - auto-regenerates every N minutes (default: 60):
    python scraper/generate_history.py --watch
    python scraper/generate_history.py --watch --interval 30

    # Dev + watch (most useful for localhost):
    python scraper/generate_history.py --dev --watch
"""

import argparse
import json
import re
import subprocess
import sys
import time
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT           = Path(__file__).parent.parent
SCRAPED_PATH   = ROOT / "scraper" / "scraped_prices.json"
DATA_JS_PATH   = ROOT / "frontend" / "data.js"
CONFIG_JS_PATH = ROOT / "frontend" / "cars.config.js"

# ---------------------------------------------------------------------------
# Load fallback prices from cars.config.js
# ---------------------------------------------------------------------------

def load_fallback_prices_from_config() -> dict[str, int]:
    """
    Read frontend/cars.config.js and return { car_id: avg_price } for every
    car in WATCHLIST + TICKER_UNIVERSE. Used as the fallback when we don't
    have fresh scraped data (--dev mode, or fallback-confidence cars).
    """
    if not CONFIG_JS_PATH.exists():
        raise SystemExit(f"cars.config.js not found at {CONFIG_JS_PATH}")

    js_extractor = r"""
        const fs = require('fs');
        const path = process.argv[1];
        const code = fs.readFileSync(path, 'utf-8');
        const fn = new Function(code + '; return { WATCHLIST, TICKER_UNIVERSE };');
        const data = fn();
        const all = [...data.WATCHLIST, ...data.TICKER_UNIVERSE];
        const out = {};
        all.forEach(c => { if (c.id) out[c.id] = c.avg_price || 0; });
        process.stdout.write(JSON.stringify(out));
    """
    try:
        result = subprocess.run(
            ["node", "-e", js_extractor, str(CONFIG_JS_PATH)],
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

    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Price history generator
# ---------------------------------------------------------------------------

def generate_history(
    car_id: str,
    target_price: int,
    days: int = 365,
    seed: int | None = None,
) -> list[dict]:
    """
    Generate a realistic 365-day mean-reverting price series ending at
    target_price. Ornstein-Uhlenbeck-style random walk - gradual drifts,
    occasional spikes, mean reversion to the target.
    """
    rng = random.Random(seed or hash(car_id))

    vol            = target_price * 0.018
    drift_dir      = rng.choice([-1, 1])
    start_price    = target_price * (1 + drift_dir * rng.uniform(0.05, 0.12))
    mean_reversion = 0.015

    prices = [start_price]
    for _ in range(days - 1):
        prev  = prices[-1]
        pull  = mean_reversion * (target_price - prev)
        shock = rng.gauss(0, vol)
        if rng.random() < 0.02:
            shock *= rng.uniform(2, 4)
        new_price = max(prev + pull + shock, target_price * 0.3)
        prices.append(new_price)

    prices[-1] = float(target_price)  # anchor endpoint

    today      = datetime.now(UTC).date()
    start_date = today - timedelta(days=days - 1)
    history    = []
    for i, price in enumerate(prices):
        date = start_date + timedelta(days=i)
        history.append({
            "date":   date.isoformat(),
            "price":  round(price, 0),
            "volume": rng.randint(1, 15),
        })

    return history


# ---------------------------------------------------------------------------
# cars.config.js patcher (only patches cars with confidence: 'scraped')
# ---------------------------------------------------------------------------

def patch_config_prices(config_text: str, price_data: dict) -> str:
    """
    Replace avg_price and prev_avg in cars.config.js for each car that has
    fresh scraped data. Patches both WATCHLIST and TICKER_UNIVERSE entries
    by id - the regex matches by `id:` field, regardless of which array.
    Skips cars with confidence: 'fallback'.
    """
    updated = config_text

    for car_id, result in price_data.items():
        if result.get("confidence") != "scraped":
            print(f"  --  {car_id}: skipping (fallback price, not scraped)")
            continue

        new_avg   = result["avg_price"]
        avg_match = re.search(
            rf"(id:\s*['\"]){re.escape(car_id)}(['\"].*?avg_price:\s*)(\d+)",
            updated,
            re.DOTALL,
        )
        if avg_match:
            old_avg  = int(avg_match.group(3))
            new_prev = old_avg

            updated = re.sub(
                rf"(id:\s*['\"]){re.escape(car_id)}(['\"].*?avg_price:\s*)(\d+)",
                lambda m: m.group(1) + car_id + m.group(2) + str(new_avg),
                updated,
                flags=re.DOTALL,
            )
            block_pattern = rf"(id:\s*['\"]){re.escape(car_id)}['\"].*?(?=\n  \{{|\Z)"

            def replace_prev_avg(m):
                block = m.group(0)
                return re.sub(r"(prev_avg:\s*)(\d+)", rf"\g<1>{new_prev}", block)

            updated = re.sub(block_pattern, replace_prev_avg, updated, flags=re.DOTALL)

            print(f"  OK  {car_id}: avg_price {old_avg:,} -> {new_avg:,}  |  prev_avg -> {new_prev:,}")
        else:
            print(f"  WARN  {car_id}: could not find block in config to patch")

    return updated


# ---------------------------------------------------------------------------
# Load prices - scraped file or dev fallback
# ---------------------------------------------------------------------------

def load_prices(dev_mode: bool) -> tuple[dict, bool]:
    """
    Returns (price_data_dict, is_scraped).
    price_data_dict format: { car_id: { "avg_price": int, "confidence": str } }
    """
    if not dev_mode and SCRAPED_PATH.exists():
        scraped    = json.loads(SCRAPED_PATH.read_text())
        price_data = scraped["prices"]
        print(f"Loaded {len(price_data)} car prices from scraped_prices.json")
        return price_data, True

    if not dev_mode and not SCRAPED_PATH.exists():
        print("WARN  scraped_prices.json not found - switching to dev mode automatically.")
        print("      (Run scrape_prices.py to get live prices.)")

    # Dev fallback: load every car from cars.config.js as the source of truth
    fallback = load_fallback_prices_from_config()
    price_data = {
        car_id: {"avg_price": price, "confidence": "fallback"}
        for car_id, price in fallback.items()
    }
    print(f"Dev mode: loaded fallback prices for {len(price_data)} cars from cars.config.js")
    return price_data, False


# ---------------------------------------------------------------------------
# Core generate function
# ---------------------------------------------------------------------------

def run_generate(dev_mode: bool) -> None:
    print("-" * 60)
    print(f"Generating  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")

    price_data, is_scraped = load_prices(dev_mode)

    # Generate 365-day history for every car with a price
    baked = {}
    for car_id, result in price_data.items():
        avg = result["avg_price"]
        if not avg:
            print(f"  --  {car_id}: skipping (no price)")
            continue
        history = generate_history(
            car_id=car_id,
            target_price=avg,
            days=365,
            seed=int(datetime.now(UTC).strftime("%Y%W")) + hash(car_id) % 10000,
        )
        baked[car_id] = history
        print(f"  {car_id}: {len(history)} days  latest=${history[-1]['price']:,.0f}")

    # Write data.js
    data_js = "var BAKED_HISTORY = " + json.dumps(baked, separators=(",", ":")) + ";\n"
    DATA_JS_PATH.write_text(data_js)
    size_kb = DATA_JS_PATH.stat().st_size / 1024
    print(f"OK  Wrote frontend/data.js  ({size_kb:.0f} KB, {len(baked)} cars)")

    # Only patch cars.config.js if we have real scraped data
    if is_scraped:
        print("Patching cars.config.js prices...")
        config_text = CONFIG_JS_PATH.read_text()
        patched     = patch_config_prices(config_text, price_data)
        CONFIG_JS_PATH.write_text(patched)
        print("OK  Updated cars.config.js")
    else:
        print("--  Skipping cars.config.js patch (dev/fallback mode)")

    print("Done.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Garage Terminal - History Generator")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use cars.config.js avg_price values instead of scraped_prices.json",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and regenerate data.js on a timer",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        metavar="MINUTES",
        help="How often to regenerate in --watch mode (default: 60 minutes)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("GARAGE TERMINAL - History Generator")
    if args.dev:
        print("Mode: DEV (fallback prices from cars.config.js, no scraper needed)")
    if args.watch:
        print(f"Mode: WATCH (regenerating every {args.interval} min)")
    print("=" * 60)

    run_generate(dev_mode=args.dev)

    if args.watch:
        interval_secs = args.interval * 60
        print(f"\nWatching - next run in {args.interval} min  (Ctrl+C to stop)\n")
        try:
            while True:
                time.sleep(interval_secs)
                run_generate(dev_mode=args.dev)
                print(f"Next run in {args.interval} min  (Ctrl+C to stop)\n")
        except KeyboardInterrupt:
            print("\nStopped.")
            sys.exit(0)


if __name__ == "__main__":
    main()
