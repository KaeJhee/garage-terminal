#!/usr/bin/env python3
"""
add_manual_price.py
===================
Add a manually-sourced price point to a car's history. Use this for cars with
NO US auction market - mainly the Chinese NEVs (Nio ES9, Zeekr 9X, Aito M9),
whose prices come from Chinese sources (CnEVPost, CarNewsChina, Autohome), not
from BaT/Cars & Bids scraping.

Each point is a real China-market price on a real date. The chart connects them
as a stepped "manual" line (greyed/dotted) so you can see price cuts over time.
These are NOT marked as US sold transactions - they are honest manual marks.

USAGE
  # Add today's price
  python add_manual_price.py nio-es9 78000

  # Add a historical price point (e.g. launch price, or a known price cut)
  python add_manual_price.py nio-es9 81000 --date 2026-05-27
  python add_manual_price.py nio-es9 78000 --date 2026-06-15

  # Convert from RMB at a given USD rate (handy for China prices)
  python add_manual_price.py zeekr-9x 538000 --rmb --fx 0.1395 --date 2026-03-01

  # List a car's current manual points
  python add_manual_price.py nio-es9 --list

After adding points, rebuild the charts:
  python generate_history.py
"""

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

PRICE_HISTORY_PATH = Path(__file__).parent.parent / "frontend" / "price_history.json"


def load():
    if PRICE_HISTORY_PATH.exists():
        return json.loads(PRICE_HISTORY_PATH.read_text())
    return {}


def save(history):
    PRICE_HISTORY_PATH.write_text(json.dumps(history, separators=(",", ":")))


def main():
    ap = argparse.ArgumentParser(description="Add a manual price point for a no-market car.")
    ap.add_argument("car_id", help="car id from cars.config.js (e.g. nio-es9)")
    ap.add_argument("price", nargs="?", type=float, help="price (USD, or RMB with --rmb)")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--rmb", action="store_true", help="price is in RMB; convert with --fx")
    ap.add_argument("--fx", type=float, default=0.1395, help="RMB->USD rate (default 0.1395)")
    ap.add_argument("--list", action="store_true", help="list this car's manual points")
    args = ap.parse_args()

    history = load()
    entry = history.setdefault(args.car_id, {"sales": []})

    if args.list:
        pts = [s for s in entry["sales"] if s.get("venue") == "manual"]
        if not pts:
            print(f"{args.car_id}: no manual points")
        else:
            print(f"{args.car_id}: {len(pts)} manual point(s)")
            for s in sorted(pts, key=lambda x: x["date"]):
                print(f"  {s['date']}  ${int(s['price']):,}")
        return

    if args.price is None:
        ap.error("price is required unless --list is used")

    usd = args.price * args.fx if args.rmb else args.price
    usd = round(usd)
    date = args.date or datetime.now(timezone.utc).date().isoformat()

    # Replace any existing manual point on the SAME date (so re-runs update it)
    entry["sales"] = [s for s in entry["sales"]
                      if not (s.get("venue") == "manual" and s["date"] == date)]
    entry["sales"].append({"date": date, "price": usd, "venue": "manual"})
    entry["sales"].sort(key=lambda s: s["date"])
    save(history)

    src = f"  (from RMB {int(args.price):,} @ {args.fx})" if args.rmb else ""
    print(f"OK  {args.car_id}: added manual ${usd:,} on {date}{src}")
    print("Now run:  python generate_history.py")


if __name__ == "__main__":
    main()
