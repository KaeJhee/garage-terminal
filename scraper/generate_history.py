#!/usr/bin/env python3
"""
generate_history.py
===================
Weekly step after scrape_prices.py:

  1. Store each new Bring a Trailer sale from scraper/scraped_prices.json in
     frontend/price_history.json, once per listing ID and dated to the auction
     end. Stored rows are removed only when the car's model-year or title
     rules now reject them, or when they are old blended backfill rows on a day
     the scrape saw in full. An 'unsold' card never removes a stored sale.
  2. Patch avg_price and prev_avg in cars.config.js for cars with enough
     recent sales ("scraped"). The page derives import duty and the
     first-year total from avg_price, so the config stores neither.
  3. Write frontend/data.js from the patched prices and the store:
       BAKED_HISTORY[id] = daily ESTIMATE line: a deterministic 365-day
                           mean-reverting path that ends at the tracked price
                           (kind "walk"). Indicative only, not observed prices.
       BAKED_SALES[id]   = individual real sales [{date, price, venue}] for the
                           transaction scatter.
       BAKED_META[id]    = {last_sale, n_total, n_plotted, ...} for the
                           sample-size display.

DATA MODEL (price_history.json):
  { "<id>": { "sales": [{date, price, venue, listing_id?, url?, title?}] } }
  venue: bat | bat-backfill | manual | manual-auto
  'manual' and 'manual-auto' rows are legacy placeholders (NOT_SALES): they
  stay in the store but are never plotted or counted, and no new ones are
  written.

Every file is written to a .tmp file first and then moved into place, so a
crash mid-write never leaves a truncated store, config or data.js.

After a scrape it also writes scraper/run_results.json (not committed): each
car's price decision (applied, unchanged, refused by the price band, or
skipped) and the anchor audit, for scraper/report.py.

With no scraped_prices.json, or with --dev, only data.js is rewritten;
price_history.json, cars.config.js and run_results.json are left untouched.
"""

import argparse, hashlib, json, os, random, re, statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scrape_prices as sp

UTC = timezone.utc

ROOT               = Path(__file__).parent.parent
SCRAPED_PATH       = ROOT / "scraper" / "scraped_prices.json"
PRICE_HISTORY_PATH = ROOT / "frontend" / "price_history.json"
DATA_JS_PATH       = ROOT / "frontend" / "data.js"
CONFIG_JS_PATH     = ROOT / "frontend" / "cars.config.js"
RESULTS_PATH       = ROOT / "scraper" / "run_results.json"   # read by report.py; gitignored

ROLL_WINDOW  = 90    # trailing days for the 90-day meta figures
STALE_DAYS   = 30    # no real sale in this many days -> stale flag
WALK_DAYS    = 365
PLAUSIBLE_LO = 0.25   # drop "sales" below 25% of tracked price
PLAUSIBLE_HI = 4.0    # drop "sales" above 4x tracked price
NOT_SALES    = ("manual", "manual-auto")   # legacy placeholder rows: kept in the store, never plotted or counted

CONFIG_FIELDS = ("avg_price", "low_price", "high_price", "import_duty_pct", "shipping_est", "registration_est",
                 "insurance_annual", "maintenance_annual", "years", "title_include", "title_exclude")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_cars_from_config() -> dict:
    """{id: {avg_price, low_price, high_price, cost fields, years, title_include, title_exclude}},
    read with the scraper's loader so both scripts see the same config."""
    return {c["id"]: {k: c[k] for k in CONFIG_FIELDS} for c in sp.load_cars_from_config() if c["id"]}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_atomic(path, text):
    """Write to a .tmp file, then move it into place, so a crash never leaves a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)

def make_synthetic_leadin(car_id, end_price, end_date, days=WALK_DAYS):
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

def d(s): return datetime.fromisoformat(s).date()

def load_price_history():
    return json.loads(PRICE_HISTORY_PATH.read_text()) if PRICE_HISTORY_PATH.exists() else {}

def save_price_history(history):
    write_atomic(PRICE_HISTORY_PATH, json.dumps(history, separators=(",", ":")))

# ---------------------------------------------------------------------------
# Accumulation
# ---------------------------------------------------------------------------

def add_listing_sales(history, car_id, sales, today_iso):
    """Record each BaT sale once, keyed by its listing ID and dated to the
    auction end. A listing already stored is skipped, and a backfill entry
    with the same date and price is upgraded in place rather than duplicated.
    Returns the number of new sales added."""
    entry = history.setdefault(car_id, {"sales": []})
    stored = entry["sales"]
    ids = {x["listing_id"] for x in stored if x.get("listing_id")}
    added = 0
    for s in sales:
        price = round(float(s["price"]), 0)
        lid = s["listing_id"]
        if lid in ids:
            continue
        day = s.get("date") or today_iso
        twin = next((x for x in stored if not x.get("listing_id") and x.get("venue") not in NOT_SALES
                     and x["date"] == day and round(float(x["price"]), 0) == price), None)
        info = {"listing_id": lid, "url": s.get("url"), "title": s.get("title")}
        if twin:
            twin.update(info)
        else:
            stored.append({"date": day, "price": price, "venue": s.get("venue", "bat"), **info})
            added += 1
        ids.add(lid)
    return added

def reconcile_days(history, car_id, sales, rejected):
    """For every day the scraper saw listing cards (sold or rejected), the only
    real sales that day are the sold listings now stored with IDs. The old
    archive backfill wrote one blended row per day, mixing in unsold 'Bid to'
    results, other model years, and page-level duplicates, so any backfill row
    on a covered day whose price matches none of that day's sold listings is
    not a sale and is removed. Days the scraper did not see are left alone.
    A stored listing the scraper now rejects for its model year or title (for
    example after a title filter was added) is removed too. An 'unsold' reject
    never removes one: a completed sale cannot become unsold, so it only means
    the page changed."""
    entry = history.get(car_id)
    if not entry:
        return 0
    covered = {s["date"] for s in sales if s.get("date")} | {r["date"] for r in rejected if r.get("date")}
    if not covered:
        return 0
    dropped_ids = {r["listing_id"] for r in rejected
                   if r.get("listing_id") and r.get("reason") in ("model year", "title filter")}
    real = {}
    for x in entry["sales"]:
        if x.get("listing_id") and x["listing_id"] not in dropped_ids:
            real.setdefault(x["date"], set()).add(round(float(x["price"])))
    before = len(entry["sales"])
    entry["sales"] = [x for x in entry["sales"]
                      if (x.get("listing_id") and x["listing_id"] not in dropped_ids)
                      or (not x.get("listing_id") and ("backfill" not in x.get("venue", "") or x["date"] not in covered
                                                       or round(float(x["price"])) in real.get(x["date"], set())))]
    return before - len(entry["sales"])

def enforce_car_rules(history, car_id, rules):
    """Apply the car's current model-year and title rules to its stored,
    listing-tracked sales, so a rule added later (or a new search URL that no
    longer shows the old listings) still clears sales of the wrong trim."""
    entry = history.get(car_id)
    if not entry or not rules:
        return 0
    span = sp.parse_years(rules.get("years"))
    inc, exc = rules.get("title_include"), rules.get("title_exclude")
    # Even with no rules set, a stored title without a model year is a parts listing, not a car
    before = len(entry["sales"])
    entry["sales"] = [x for x in entry["sales"]
                      if not (x.get("listing_id") and x.get("title")
                              and sp.card_verdict({"sold": True, "title": x["title"]}, span, inc, exc))]
    return before - len(entry["sales"])

# ---------------------------------------------------------------------------
# Build chart objects: rolling median line + band + scatter + meta
# ---------------------------------------------------------------------------

def build_for_car(entry, today, avg_price):
    if not avg_price or avg_price <= 0:
        return None, [], {}
    real = [s for s in entry.get("sales", []) if s.get("venue") not in NOT_SALES]
    lo_b, hi_b = avg_price * PLAUSIBLE_LO, avg_price * PLAUSIBLE_HI
    clean = sorted([s for s in real if lo_b <= float(s["price"]) <= hi_b], key=lambda s: s["date"])
    walk = make_synthetic_leadin(entry.get("_id", "car"), avg_price, today, days=WALK_DAYS)
    line = [{"date": p["date"], "price": p["price"], "lo": p["price"], "hi": p["price"],
             "volume": 0, "kind": "walk"} for p in walk]
    scatter = [{"date": s["date"], "price": round(float(s["price"])), "venue": s["venue"]} for s in clean]
    n_plotted = sum(1 for s in clean if line[0]["date"] <= s["date"] <= line[-1]["date"])   # the chart's date range
    if clean:
        sd = [d(s["date"]) for s in clean]; sp = [float(s["price"]) for s in clean]
        win90 = [sp[i] for i, x in enumerate(sd) if (today - x).days <= ROLL_WINDOW]
        meta = {"last_sale": sd[-1].isoformat(), "n_total": len(clean), "n_plotted": n_plotted, "n_sales_90d": len(win90),
                "median_90d": round(statistics.median(win90)) if win90 else round(statistics.median(sp)),
                "stale": (today - sd[-1]).days > STALE_DAYS, "confidence": "estimate+sales",
                "as_of": sd[-1].isoformat()}
    else:
        meta = {"last_sale": None, "n_total": 0, "n_plotted": 0, "n_sales_90d": 0, "median_90d": avg_price,
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
    write_atomic(DATA_JS_PATH, out)
    stale=sum(1 for m in meta.values() if m.get("stale"))
    print(f"OK  data.js: {len(baked)} cars, {sum(len(s) for s in sales.values())} real sales, {stale} stale")
    return audit_anchors(cfg, history, today)

def audit_anchors(cfg, history, today):
    """Flag cars whose avg_price (the chart anchor) looks wrong, so a bad value
    surfaces here instead of silently distorting a chart. The sales check uses
    only stored sales with a listing ID from the last RECENT_DAYS (the window
    the price is set from): untitled backfill rows, such as parts listings
    stored years ago, can't raise it. Returns [{id, check, message}]."""
    found = []
    cutoff = (today - timedelta(days=sp.RECENT_DAYS)).isoformat()
    for cid, c in cfg.items():
        avg = c.get("avg_price", 0)
        if not avg:
            continue
        lo, hi = c.get("low_price", 0), c.get("high_price", 0)
        if lo and avg < lo * 0.5:
            found.append({"id": cid, "check": "below band", "avg": avg, "low": lo,
                          "message": f"avg_price ${avg:,} far BELOW low_price ${lo:,}"})
        elif hi and avg > hi * 1.5:
            found.append({"id": cid, "check": "above band", "avg": avg, "high": hi,
                          "message": f"avg_price ${avg:,} far ABOVE high_price ${hi:,}"})
        listed = [float(s["price"]) for s in history.get(cid, {}).get("sales", [])
                  if s.get("listing_id") and s.get("venue") not in NOT_SALES and s.get("date", "") >= cutoff]
        if len(listed) >= 3:
            med = statistics.median(listed)
            if med > avg * 3 or med < avg / 3:
                found.append({"id": cid, "check": "sales median", "avg": avg, "median": round(med), "n": len(listed),
                              "message": f"median of {len(listed)} recent listed sales ${med:,.0f} disagrees with avg_price ${avg:,} (>3x)"})
    if found:
        print("\n** ANCHOR AUDIT - review before trusting these charts:")
        for f in found:
            print(f"  !! {f['id']}: {f['message']}")
    else:
        print("\nAnchor audit: all avg_price anchors look consistent.")
    return found

# ---------------------------------------------------------------------------
# Config patch (avg_price and prev_avg only)
# ---------------------------------------------------------------------------

NUM = r"\d+(?:\.\d+)?"   # a price as written in cars.config.js


def patch_config_prices(config_text, price_data, results=None):
    """Returns the patched config text. If a dict is passed as results, each
    car's decision is recorded in it: {result: applied | unchanged | refused |
    skipped | not found, old, new, and for a refusal the allowed range}."""
    updated=config_text
    results={} if results is None else results
    for cid,result in price_data.items():
        if result.get("confidence")!="scraped": 
            results[cid]={"result":"skipped","confidence":result.get("confidence")}
            print(f"  --  {cid}: skip patch ({result.get('confidence')})"); continue
        new_avg=int(round(result["price"]))
        idm=re.search(rf"id:\s*['\"]{re.escape(cid)}['\"]", updated)
        if not idm: results[cid]={"result":"not found","new":new_avg}; print(f"  WARN {cid}: id not found"); continue
        bs=idm.start(); be=updated.find("\n  },",bs)
        if be==-1: results[cid]={"result":"not found","new":new_avg}; print(f"  WARN {cid}: block end not found"); continue
        be+=len("\n  },"); block=updated[bs:be]
        # NUM also takes a decimal (the editor allows one), so the whole old number is read and replaced
        oam=re.search(rf"avg_price:\s*({NUM})",block)
        if not oam: results[cid]={"result":"not found","new":new_avg}; continue
        old_txt=oam.group(1); old_avg=float(old_txt) if "." in old_txt else int(old_txt)
        # The car's own configured band is the sanity check: a median far outside it means the
        # search matched a different model, so keep the current price and say so
        lo=re.search(rf"low_price:\s*({NUM})",block); hi=re.search(rf"high_price:\s*({NUM})",block)
        if lo and hi and not (float(lo.group(1))*0.8 <= new_avg <= float(hi.group(1))*1.25):
            allowed=[int(float(lo.group(1))*0.8), int(float(hi.group(1))*1.25)]
            results[cid]={"result":"refused","old":old_avg,"new":new_avg,"allowed":allowed,
                          "low_price":round(float(lo.group(1))),"high_price":round(float(hi.group(1)))}
            print(f"  !!  {cid}: median ${new_avg:,} is outside ${allowed[0]:,}-${allowed[1]:,} (80% of low_price to 125% of high_price), not applied"); continue
        if new_avg==old_avg:
            # Unchanged price: leave prev_avg alone so the change arrow keeps the last real move
            results[cid]={"result":"unchanged","old":old_avg,"new":new_avg}
            print(f"  ==  {cid}: unchanged at ${new_avg:,}"); continue
        nb=re.sub(rf"(avg_price:\s*){NUM}",rf"\g<1>{new_avg}",block,count=1)
        nb=re.sub(rf"(prev_avg:\s*){NUM}",rf"\g<1>{old_txt}",nb,count=1)
        updated=updated[:bs]+nb+updated[be:]
        results[cid]={"result":"applied","old":old_avg,"new":new_avg}
        print(f"  OK  {cid}: avg {old_avg:,}->{new_avg:,}")
    return updated

# ---------------------------------------------------------------------------
# Load scrape
# ---------------------------------------------------------------------------

def load_scrape():
    if not SCRAPED_PATH.exists():
        print("WARN  scraped_prices.json not found"); return {}
    scraped=json.loads(SCRAPED_PATH.read_text()); out={}
    for cid,r in scraped.get("prices",{}).items():
        out[cid]={"price":r.get("avg_price",0),"confidence":r.get("confidence","scraped"),
                  "sales":r.get("sales",[]),"rejected":r.get("rejected",[])}
    print(f"Loaded {len(out)} scraped prices")
    return out

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def describe(row):
    return f"listing {row['listing_id']}" if row.get("listing_id") else f"{row.get('venue')} row {row['date']} ${float(row['price']):,.0f}"

def run_generate(dev_mode):
    print("-"*60); print(f"Generating  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    meta=load_cars_from_config(); today=datetime.now(UTC).date(); today_iso=today.isoformat()
    history=load_price_history()
    price_data={} if dev_mode else load_scrape()
    if not price_data:
        print("--  No scrape results: rebuilding data.js only (price_history.json and cars.config.js untouched)")
        build_data_js(history,today,meta)
        print("Done."); return

    before={cid:list(e.get("sales",[])) for cid,e in history.items()}
    for cid,obs in price_data.items():
        if obs["sales"] or obs["rejected"]:
            n=add_listing_sales(history,cid,obs["sales"],today_iso)
            if n: print(f"  +{n} new sale(s) for {cid}")
            gone=reconcile_days(history,cid,obs["sales"],obs["rejected"])
            if gone: print(f"  -{gone} stored entr{'y' if gone==1 else 'ies'} for {cid} removed: no matching sold listing on a covered day, or a listing now rejected for its model year or title")
    for cid,rules in meta.items():
        off=enforce_car_rules(history,cid,rules)
        if off: print(f"  -{off} stored sale(s) for {cid} fail its model-year or title rules")
    for cid,rows in before.items():
        now={id(x) for x in history.get(cid,{}).get("sales",[])}
        for x in rows:
            if id(x) not in now: print(f"     removed from {cid}: {describe(x)}")
    save_price_history(history)
    real=sum(len([s for s in e["sales"] if s.get("venue") not in NOT_SALES]) for e in history.values())
    print(f"OK  price_history.json: {len(history)} cars, {real} real sales total")

    print("Patching cars.config.js (avg_price and prev_avg)...")
    decisions={}
    write_atomic(CONFIG_JS_PATH, patch_config_prices(CONFIG_JS_PATH.read_text(),price_data,decisions))
    print("OK  Updated cars.config.js")
    anchors=build_data_js(history,today,load_cars_from_config())   # re-read so each line ends at the patched price
    # For report.py: tied to this scrape by its scraped_at, so a stale file is never read as this run's
    scraped_at=json.loads(SCRAPED_PATH.read_text()).get("scraped_at") if SCRAPED_PATH.exists() else None
    write_atomic(RESULTS_PATH, json.dumps({"scraped_at":scraped_at,"generated_on":today_iso,
                                           "prices":decisions,"anchor_audit":anchors}, indent=1))
    print(f"OK  {RESULTS_PATH.name}: {sum(1 for r in decisions.values() if r['result']=='refused')} refused by the price band, "
          f"{len(anchors)} anchor warning(s)")
    print("Done.")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dev",action="store_true",help="ignore scraped_prices.json; rebuild data.js only")
    args=ap.parse_args()
    print("="*60); print("GARAGE TERMINAL - History Accumulator (estimate line + sale dots)")
    if args.dev: print("Mode: DEV (data.js only)")
    print("="*60)
    run_generate(args.dev)

if __name__=="__main__": main()
