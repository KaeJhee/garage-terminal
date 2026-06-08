#!/usr/bin/env python3
"""
generate_history.py
===================
Builds the chart data from REAL individual sales accumulated in
frontend/price_history.json. Produces three objects in frontend/data.js:

  BAKED_HISTORY[id] = daily line: trailing-90-day MEDIAN of real sales,
                      with a band (lo/hi = P25/P75) and a "kind" flag
                      (observed | interpolated | stale | synthetic | manual).
  BAKED_SALES[id]   = individual real sales [{date, price, venue}] for the
                      transaction scatter.
  BAKED_META[id]    = {last_sale, n_sales_90d, median_90d, stale, confidence,
                      as_of} for the staleness + sample-size display.

DATA MODEL (price_history.json):
  { "<id>": { "sales": [{date, price, venue}], "synthetic": [{date, price}] } }
  venue: bat | carsandbids | classic_com | bat-backfill | manual
  "manual" = fallback placeholder when no sold data exists (e.g. Chinese EVs,
  or a week the scrape found nothing). Manual points are NOT real sales: they
  render as a flat, greyed line and are excluded from the scatter.

ACCUMULATION:
  - Each run reads scraped_prices.json. Real sold prices are appended as
    individual sales dated to the scrape date, deduped by ISO week + venue.
  - Fallback (no sold data) records ONE manual point for the week.
  - First time a car is seen, a frozen synthetic lead-in is created so the
    chart isn't empty. It only renders before the first real sale.

  --dev writes nothing real (preview build only).
"""

import argparse, hashlib, json, random, re, subprocess, sys, time, statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc

ROOT               = Path(__file__).parent.parent
SCRAPED_PATH       = ROOT / "scraper" / "scraped_prices.json"
PRICE_HISTORY_PATH = ROOT / "frontend" / "price_history.json"
DATA_JS_PATH       = ROOT / "frontend" / "data.js"
CONFIG_JS_PATH     = ROOT / "frontend" / "cars.config.js"

SYNTHETIC_DAYS = 358
ROLL_WINDOW    = 90    # trailing days for rolling median + band
STALE_DAYS     = 30    # no real sale in this many days -> stale flag
WALK_DAYS    = 365
PLAUSIBLE_LO = 0.25   # drop "sales" below 25% of tracked price
PLAUSIBLE_HI = 4.0    # drop "sales" above 4x tracked price

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_cars_from_config() -> dict:
    if not CONFIG_JS_PATH.exists():
        raise SystemExit(f"cars.config.js not found at {CONFIG_JS_PATH}")
    js = r"""
        const fs=require('fs');
        const code=fs.readFileSync(process.argv[1],'utf-8');
        const fn=new Function(code+'; return {WATCHLIST,TICKER_UNIVERSE};');
        const d=fn(); const all=[...d.WATCHLIST,...d.TICKER_UNIVERSE]; const out={};
        all.forEach(c=>{ if(!c.id) return; const cto=c.cost_to_own||{};
          out[c.id]={avg_price:c.avg_price||0,low_price:c.low_price||0,high_price:c.high_price||0,import_duty_pct:cto.import_duty_pct||0,
            shipping_est:cto.shipping_est||0,registration_est:cto.registration_est||0,
            insurance_annual:cto.insurance_annual||0,maintenance_annual:cto.maintenance_annual||0}; });
        process.stdout.write(JSON.stringify(out));
    """
    try:
        r = subprocess.run(["node","-e",js,str(CONFIG_JS_PATH)],
                           capture_output=True, text=True, check=True, timeout=15)
    except FileNotFoundError:
        raise SystemExit("Node.js is required to parse cars.config.js.")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"Failed to parse cars.config.js:\n{e.stderr}")
    return json.loads(r.stdout)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_synthetic_leadin(car_id, end_price, end_date, days=SYNTHETIC_DAYS):
    rng = random.Random(int(hashlib.md5(str(car_id).encode()).hexdigest(), 16) & 0xffffffff)
    target = float(end_price); vol = target*0.018; mr = 0.015
    drift = rng.choice([-1,1]); start = target*(1+drift*rng.uniform(0.05,0.12))
    prices=[start]
    for _ in range(days-1):
        prev=prices[-1]; pull=mr*(target-prev); shock=rng.gauss(0,vol)
        if rng.random()<0.02: shock*=rng.uniform(2,4)
        prices.append(max(prev+pull+shock, target*0.3))
    prices[-1]=target
    sd=end_date-timedelta(days=days)
    return [{"date":(sd+timedelta(days=i)).isoformat(),"price":round(p,0)} for i,p in enumerate(prices)]

def iso_week(date_str):
    y,w,_=datetime.fromisoformat(date_str).date().isocalendar(); return f"{y}-W{w:02d}"

def d(s): return datetime.fromisoformat(s).date()

def load_price_history():
    return json.loads(PRICE_HISTORY_PATH.read_text()) if PRICE_HISTORY_PATH.exists() else {}

# ---------------------------------------------------------------------------
# Accumulation
# ---------------------------------------------------------------------------

def add_real_sales(history, car_id, sold_prices, venues, today_iso):
    """Add this week's real sold prices as individual sales dated today,
    deduped by ISO week + forward venues (re-run same week replaces them)."""
    entry = history.setdefault(car_id, {"sales": []})
    this_week = iso_week(today_iso)
    venue_tag = venues[0] if venues else "scrape"
    # remove existing FORWARD sales (not backfill, not manual) for this ISO week
    entry["sales"] = [s for s in entry["sales"]
                      if not (s.get("venue") not in ("manual",) and "backfill" not in s.get("venue","")
                              and iso_week(s["date"]) == this_week)]
    for p in sold_prices:
        entry["sales"].append({"date": today_iso, "price": round(p,0), "venue": venue_tag})

def record_manual(history, car_id, price, today_iso):
    """No sold data: auto-record ONE placeholder for this week (venue
    'manual-auto'). Never touches hand-curated 'manual' points."""
    entry = history.setdefault(car_id, {"sales": []})
    this_week = iso_week(today_iso)
    entry["sales"] = [s for s in entry["sales"]
                      if not (s.get("venue")=="manual-auto" and iso_week(s["date"])==this_week)]
    entry["sales"].append({"date": today_iso, "price": round(price,0), "venue": "manual-auto"})

# ---------------------------------------------------------------------------
# Build chart objects: rolling median line + band + scatter + meta
# ---------------------------------------------------------------------------

def build_for_car(entry, today, avg_price):
    if not avg_price or avg_price <= 0:
        return None, [], {}
    real = [s for s in entry.get("sales", []) if s.get("venue") not in ("manual", "manual-auto")]
    lo_b, hi_b = avg_price * PLAUSIBLE_LO, avg_price * PLAUSIBLE_HI
    clean = sorted([s for s in real if lo_b <= float(s["price"]) <= hi_b], key=lambda s: s["date"])
    walk = make_synthetic_leadin(entry.get("_id", "car"), avg_price, today, days=WALK_DAYS)
    line = [{"date": p["date"], "price": p["price"], "lo": p["price"], "hi": p["price"],
             "volume": 0, "kind": "walk"} for p in walk]
    scatter = [{"date": s["date"], "price": round(float(s["price"])), "venue": s["venue"]} for s in clean]
    if clean:
        sd = [d(s["date"]) for s in clean]; sp = [float(s["price"]) for s in clean]
        win90 = [sp[i] for i, x in enumerate(sd) if (today - x).days <= ROLL_WINDOW]
        meta = {"last_sale": sd[-1].isoformat(), "n_total": len(clean), "n_sales_90d": len(win90),
                "median_90d": round(statistics.median(win90)) if win90 else round(statistics.median(sp)),
                "stale": (today - sd[-1]).days > STALE_DAYS, "confidence": "estimate+sales",
                "as_of": sd[-1].isoformat()}
    else:
        meta = {"last_sale": None, "n_total": 0, "n_sales_90d": 0, "median_90d": avg_price,
                "stale": True, "confidence": "estimate", "as_of": None}
    return line, scatter, meta

def build_data_js(history, today, cfg):
    baked, sales, meta = {}, {}, {}
    for cid, c in cfg.items():
        entry = dict(history.get(cid, {"sales": []}))
        entry["_id"] = cid
        line, scat, m = build_for_car(entry, today, c.get("avg_price", 0))
        if line:
            baked[cid] = line
            if scat: sales[cid] = scat
            meta[cid] = m
    out = ("var BAKED_HISTORY = " + json.dumps(baked, separators=(",",":")) + ";\n" +
           "var BAKED_SALES = "   + json.dumps(sales, separators=(",",":")) + ";\n" +
           "var BAKED_META = "    + json.dumps(meta,  separators=(",",":")) + ";\n")
    DATA_JS_PATH.write_text(out)
    stale=sum(1 for m in meta.values() if m.get("stale"))
    print(f"OK  data.js: {len(baked)} cars, {sum(len(s) for s in sales.values())} real sales, {stale} stale")
    audit_anchors(cfg, history)

def audit_anchors(cfg, history):
    """Flag cars whose avg_price (the chart anchor) looks wrong, so a bad value
    surfaces here instead of silently distorting a chart."""
    warns = []
    for cid, c in cfg.items():
        avg = c.get("avg_price", 0)
        if not avg:
            continue
        lo, hi = c.get("low_price", 0), c.get("high_price", 0)
        if lo and avg < lo * 0.5:
            warns.append(f"  !! {cid}: avg_price ${avg:,} far BELOW low_price ${lo:,}")
        elif hi and avg > hi * 1.5:
            warns.append(f"  !! {cid}: avg_price ${avg:,} far ABOVE high_price ${hi:,}")
        raw = [float(s["price"]) for s in history.get(cid, {}).get("sales", [])
               if s.get("venue") not in ("manual", "manual-auto")]
        if len(raw) >= 3:
            med = statistics.median(raw)
            if med > avg * 3 or med < avg / 3:
                warns.append(f"  !! {cid}: real-sales median ${med:,.0f} disagrees with avg_price ${avg:,} (>3x)")
    if warns:
        print("\n** ANCHOR AUDIT - review before trusting these charts:")
        for w in warns:
            print(w)
    else:
        print("\nAnchor audit: all avg_price anchors look consistent.")

# ---------------------------------------------------------------------------
# Config patch (price + duty recompute)
# ---------------------------------------------------------------------------

def patch_config_prices(config_text, price_data, meta):
    updated=config_text
    for cid,result in price_data.items():
        if result.get("confidence")!="scraped": 
            print(f"  --  {cid}: skip patch (fallback)"); continue
        new_avg=int(round(result["price"]))
        idm=re.search(rf"id:\s*['\"]{re.escape(cid)}['\"]", updated)
        if not idm: print(f"  WARN {cid}: id not found"); continue
        bs=idm.start(); be=updated.find("\n  },",bs)
        if be==-1: print(f"  WARN {cid}: block end not found"); continue
        be+=len("\n  },"); block=updated[bs:be]
        oam=re.search(r"avg_price:\s*(\d+)",block)
        if not oam: continue
        old_avg=int(oam.group(1)); m=meta.get(cid,{}); pct=m.get("import_duty_pct",0)
        nd=int(round(new_avg*pct))
        nt=nd+m.get("shipping_est",0)+m.get("registration_est",0)+m.get("insurance_annual",0)+m.get("maintenance_annual",0)
        nb=re.sub(r"(avg_price:\s*)\d+",rf"\g<1>{new_avg}",block,count=1)
        nb=re.sub(r"(prev_avg:\s*)\d+",rf"\g<1>{old_avg}",nb,count=1)
        if pct>0:
            nb=re.sub(r"(import_duty_est:\s*)\d+",rf"\g<1>{nd}",nb,count=1)
            nb=re.sub(r"(total_first_year_extra:\s*)\d+",rf"\g<1>{nt}",nb,count=1)
        updated=updated[:bs]+nb+updated[be:]
        print(f"  OK  {cid}: avg {old_avg:,}->{new_avg:,} duty->{nd:,}")
    return updated

# ---------------------------------------------------------------------------
# Load scrape
# ---------------------------------------------------------------------------

def load_scrape():
    if not SCRAPED_PATH.exists():
        print("WARN  scraped_prices.json not found"); return {}, False
    scraped=json.loads(SCRAPED_PATH.read_text()); out={}
    for cid,r in scraped.get("prices",{}).items():
        out[cid]={"price":r.get("avg_price",0),"confidence":r.get("confidence","scraped"),
                  "sold_prices":r.get("sold_prices",[]),"venues":r.get("venues",[]),
                  "n_sales":r.get("n_sales",0)}
    print(f"Loaded {len(out)} scraped prices")
    return out, True

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def run_generate(dev_mode):
    print("-"*60); print(f"Generating  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    meta=load_cars_from_config(); today=datetime.now(UTC).date(); today_iso=today.isoformat()

    if dev_mode:
        history=load_price_history()
        if not history:
            print("Dev: no price_history.json, ephemeral preview")
            for cid,m in meta.items():
                if m["avg_price"]:
                    history[cid]={"sales":[{"date":today_iso,"price":m["avg_price"],"venue":"manual"}]}
        build_data_js(history,today,meta)
        print("--  Dev mode: price_history.json + cars.config.js NOT modified"); print("Done."); return

    price_data,is_real=load_scrape()
    if not is_real or not price_data:
        print("Falling back to cars.config.js avg_price (manual points this week)")
        price_data={cid:{"price":m["avg_price"],"confidence":"fallback","sold_prices":[],"venues":[],"n_sales":0}
                    for cid,m in meta.items() if m["avg_price"]}

    history=load_price_history()
    for cid,obs in price_data.items():
        if obs["confidence"]=="scraped" and obs["sold_prices"]:
            add_real_sales(history,cid,obs["sold_prices"],obs["venues"],today_iso)
        elif obs["price"]:
            # Defer to hand-curated manual points if the user owns this car's history
            entry = history.get(cid, {})
            has_user_manual = any(s.get("venue")=="manual" for s in entry.get("sales",[]))
            if not has_user_manual:
                record_manual(history,cid,obs["price"],today_iso)
    PRICE_HISTORY_PATH.write_text(json.dumps(history,separators=(",",":")))
    real=sum(len([s for s in e["sales"] if s.get("venue") not in ("manual","manual-auto")]) for e in history.values())
    print(f"OK  price_history.json: {len(history)} cars, {real} real sales total")

    build_data_js(history,today,meta)
    print("Patching cars.config.js (price + duty recompute)...")
    CONFIG_JS_PATH.write_text(patch_config_prices(CONFIG_JS_PATH.read_text(),price_data,meta))
    print("OK  Updated cars.config.js"); print("Done.")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dev",action="store_true"); ap.add_argument("--watch",action="store_true")
    ap.add_argument("--interval",type=int,default=60); args=ap.parse_args()
    print("="*60); print("GARAGE TERMINAL - History Accumulator (rolling median + scatter)")
    if args.dev: print("Mode: DEV (no real writes)")
    print("="*60)
    run_generate(args.dev)
    if args.watch:
        try:
            while True: time.sleep(args.interval*60); run_generate(args.dev)
        except KeyboardInterrupt: print("\nStopped."); sys.exit(0)

if __name__=="__main__": main()
