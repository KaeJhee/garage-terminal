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

import argparse, json, random, re, subprocess, sys, time, statistics
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
FRESH_DAYS     = 14    # a sale within this many days -> "observed" (fresh)
STALE_DAYS     = 30    # no real sale in this many days -> stale flag

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
          out[c.id]={avg_price:c.avg_price||0,import_duty_pct:cto.import_duty_pct||0,
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
    rng = random.Random(hash(car_id) & 0xffffffff)
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

def _pctl(vals, q):
    if not vals: return None
    s=sorted(vals); k=(len(s)-1)*q; f=int(k); c=min(f+1,len(s)-1)
    return s[f] + (s[c]-s[f])*(k-f)

def build_for_car(entry, today):
    MANUAL_VENUES = ("manual", "manual-auto")
    real = sorted([s for s in entry.get("sales",[]) if s.get("venue") not in MANUAL_VENUES], key=lambda s:s["date"])
    # Prefer hand-curated "manual" points; fall back to auto-recorded if none.
    user_manual = [s for s in entry.get("sales",[]) if s.get("venue")=="manual"]
    auto_manual = [s for s in entry.get("sales",[]) if s.get("venue")=="manual-auto"]
    manual = sorted(user_manual if user_manual else auto_manual, key=lambda s:s["date"])

    # ---- MANUAL-ONLY car (no US market): stepped line of manually-sourced
    # prices over time. These are real China-market prices you enter by hand
    # (launch, each price cut), carried forward until the next update. Greyed
    # + marked manual since they are not US auction transactions.
    if not real:
        if not manual:
            return None, [], {}
        mpts = manual  # already sorted by date
        first = d(mpts[0]["date"])
        start = first if (today - first).days >= ROLL_WINDOW else today - timedelta(days=ROLL_WINDOW)
        line=[]; cur=start; mi=0
        while cur <= today:
            while mi+1 < len(mpts) and d(mpts[mi+1]["date"]) <= cur:
                mi += 1
            price = mpts[mi]["price"]
            line.append({"date":cur.isoformat(),"price":price,"lo":price,"hi":price,"volume":0,"kind":"manual"})
            cur += timedelta(days=1)
        meta={"last_sale":None,"n_sales_90d":0,"median_90d":mpts[-1]["price"],"stale":True,
              "confidence":"manual","as_of":mpts[-1]["date"]}
        return line, [], meta

    # ---- REAL-SALES car: rolling-90d median line + P25/P75 band + scatter ----
    # Chart starts at the first real sale (no invented pre-history).
    sale_dates=[d(s["date"]) for s in real]
    sale_prices=[float(s["price"]) for s in real]
    first_sale=sale_dates[0]
    line=[]
    last_median=None
    cur=first_sale
    while cur <= today:
        lo_d=cur-timedelta(days=ROLL_WINDOW)
        window=[sale_prices[i] for i,sd in enumerate(sale_dates) if lo_d <= sd <= cur]
        if window:
            med=round(statistics.median(window))
            lo=round(_pctl(window,0.25)); hi=round(_pctl(window,0.75))
            last_median=med
            recent=any((cur-sd).days <= FRESH_DAYS for sd in sale_dates if sd<=cur)
            kind="observed" if recent else "interpolated"
            n=sum(1 for sd in sale_dates if sd==cur)
        else:
            med=last_median if last_median is not None else round(sale_prices[-1])
            lo=hi=med; kind="stale"; n=0
        line.append({"date":cur.isoformat(),"price":med,"lo":lo,"hi":hi,"volume":n,"kind":kind})
        cur += timedelta(days=1)

    # scatter = individual real sales
    scatter=[{"date":s["date"],"price":round(s["price"]),"venue":s["venue"]} for s in real]

    # meta
    last_sale=sale_dates[-1]
    win90=[sale_prices[i] for i,sd in enumerate(sale_dates) if (today-sd).days <= ROLL_WINDOW]
    meta={"last_sale":last_sale.isoformat(),
          "n_sales_90d":len(win90),
          "median_90d":round(statistics.median(win90)) if win90 else last_median,
          "stale":(today-last_sale).days > STALE_DAYS,
          "confidence":"scraped",
          "as_of":last_sale.isoformat()}
    return line, scatter, meta

def build_data_js(history, today):
    baked, sales, meta = {}, {}, {}
    for cid, entry in history.items():
        line, scat, m = build_for_car(entry, today)
        if line:
            baked[cid]=line
            if scat: sales[cid]=scat
            meta[cid]=m
    out = ("var BAKED_HISTORY = " + json.dumps(baked, separators=(",",":")) + ";\n" +
           "var BAKED_SALES = "   + json.dumps(sales, separators=(",",":")) + ";\n" +
           "var BAKED_META = "    + json.dumps(meta,  separators=(",",":")) + ";\n")
    DATA_JS_PATH.write_text(out)
    stale=sum(1 for m in meta.values() if m.get("stale"))
    print(f"OK  data.js: {len(baked)} cars, {sum(len(s) for s in sales.values())} real sales, {stale} stale")

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
        build_data_js(history,today)
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

    build_data_js(history,today)
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
