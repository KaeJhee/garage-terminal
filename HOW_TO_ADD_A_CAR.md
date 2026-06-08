# How to Add or Update a Vehicle

`cars.config.js` is the single source of truth for the whole dashboard. The chart, the ticker, the watchlist, the scraper, and the price history all read from it. There are two ways to edit it, and both produce the same file.

---

## Two ways to edit

**1. The dashboard editor (easiest).** Click the **gear CONFIG** button in the top bar. You get a list of every car, an edit form, an Add Car button, a live in-session preview, and an Export button that downloads a complete `cars.config.js`. You then hand that file to Code to commit. Use this for everyday edits and for adding cars.

**2. Hand-editing `cars.config.js`.** Copy an existing car block, change the fields, commit. Use this if you prefer working in the file directly.

The dashboard editor just generates the file for you and recomputes the derived fields automatically. The result is identical to hand-editing.

### Important: the site cannot save its own config

This is a static site with no backend, so the dashboard cannot write to its own files. The editor's Preview applies only to your browser session. To make a change permanent on the live site you Export the config and commit it. The cycle is edit, preview, export, commit.

---

## Using the dashboard editor

1. Click **gear CONFIG** in the top bar.
2. To change a car, click **edit** on its row. To add one, click **+ Add Car**.
3. Fill in the fields (see the field list below). Choose the list (watchlist or ticker) and a color from the dropdown.
4. Click **Save Car**. The car goes into your working set.
5. Click **Preview in Session** to see it on the dashboard immediately (this browser only).
6. Click **Export cars.config.js** to download the file.
7. Send the file to Code: "replace frontend/cars.config.js with this, run generate_history.py, then commit."

The editor recomputes `import_duty_est` and `total_first_year_extra` for you on export, and writes colors back as `CHART_COLORS` references. You do not enter those by hand.

---

## Hand-editing the config

1. Open `frontend/cars.config.js`.
2. Decide: watchlist (sidebar plus a colored chart line) or ticker (scrolling tape only).
3. Copy a car block from the matching array (`WATCHLIST` or `TICKER_UNIVERSE`).
4. Paste it at the end of the array and change the fields.
5. Save, commit, push.

### The fields

```js
{
  id:         'mclaren-p1',          // unique slug, lowercase, hyphens only
  symbol:     'P1',                   // ticker label, uppercase, no spaces
  make:       'McLaren',
  model:      'P1',
  years:      '2013-2015',
  category:   'Exotic',               // JDM | Modern | Exotic | Muscle | European | Chinese
  engine:     '3.8L Twin-Turbo V8 Hybrid',
  power:      '903 hp',
  avg_price:  1900000,                // current market price, USD integer
  low_price:  1500000,
  high_price: 2400000,
  prev_avg:   1850000,                // prior value, drives the delta arrow
  color:      CHART_COLORS.purple,    // pick from CHART_COLORS at top of file
  note:       'Limited to 375 units.',
  bat_url:    'https://bringatrailer.com/search/?s=mclaren+p1',
  market_url: 'https://www.classic.com/m/mclaren/p1/',
  cost_to_own: {
    insurance_annual:   8000,
    insurance_note:     'Agreed-value collector policy',
    import_duty_pct:    0,            // 0 for US-spec cars; e.g. 0.025 for a 2.5% rate
    shipping_est:       0,
    maintenance_annual: 12000,
    maintenance_note:   'Carbon tub inspection, hybrid battery service',
    // import_duty_est and total_first_year_extra are DERIVED. Do not set them.
    // registration_est and import_note are OPTIONAL (used for imports).
  },
},
```

### Field reference

| Field | What it does |
|-------|--------------|
| `id` | Unique slug. Used internally and for localStorage. Must match nothing else in the file. |
| `symbol` | Short ticker label on the tape and watchlist. Uppercase, no spaces. |
| `make` / `model` / `years` | Display info. `model` is the chart header, `years` is in the specs strip. |
| `category` | Drives the KPI tiles. Use: `JDM`, `Modern`, `Exotic`, `Muscle`, `European`, `Chinese`. |
| `engine` / `power` / `note` | Specs strip and market note. Free-form text. |
| `avg_price` / `low_price` / `high_price` | Drive the price gauge and chart. The scraper overwrites `avg_price` weekly for US-market cars. |
| `prev_avg` | Used for the up/down arrow and percentage. The scraper overwrites it with the prior period's value. |
| `color` | Chart line color. Pick a name from `CHART_COLORS` at the top of the file. |
| `bat_url` | Bring a Trailer search URL the scraper hits. Example: `bringatrailer.com/search/?s=mclaren+p1`. |
| `market_url` | classic.com market page the scraper hits. Example: `classic.com/m/mclaren/p1/`. |
| `cost_to_own` | First-year ownership costs. See below. `import_duty_est` and `total_first_year_extra` are derived, not entered. |

### Cost-to-own is self-computing

You set `import_duty_pct` (for example `0.025` for a 2.5 percent rate, `0` for US-spec). The dashboard derives the rest live, every render:

```
import_duty_est        = avg_price * import_duty_pct
total_first_year_extra = import_duty_est + shipping_est + registration_est + insurance_annual + maintenance_annual
```

You never compute or update those two by hand. When a scraped price changes, the duty and total recompute themselves. Two optional fields apply to imports: `registration_est` (a flat registration or compliance cost) and `import_note` (a short line describing the import path). Leave them off for US-spec cars.

---

## Updating an existing car's price

**US-market cars:** you usually do not need to. The weekly scrape replaces `avg_price` and `prev_avg` with the real sold median. If you want to set a starting value or a manual override, edit `avg_price` (in the editor or by hand) and the duty and total recompute on their own.

**Chinese cars, and any car with no US market:** these are different. The Nio, Zeekr, and Aito cannot be sold in the US, so the scraper finds nothing and they stay manual forever. You update their price by hand from Chinese sources (CnEVPost, CarNewsChina, Autohome) using the helper:

```
# add today's price
python scraper/add_manual_price.py nio-es9 78000

# add a historical point (launch price, or a price cut you found)
python scraper/add_manual_price.py nio-es9 81000 --date 2026-04-01

# convert straight from RMB (e.g. Zeekr 9X ASP 538,000 RMB at 0.1395)
python scraper/add_manual_price.py zeekr-9x 538000 --rmb --fx 0.1395 --date 2026-03-01

# list what you have logged, then rebuild the charts
python scraper/add_manual_price.py nio-es9 --list
python scraper/generate_history.py
```

Each entry is a real China-market price on a real date. The chart connects them as a stepped grey manual line so you can see the price changes over time. These hand-entered points are protected: the weekly scrape will not overwrite them. Also update that car's `avg_price` in the config to the latest value, so the KPI tiles and the cost-to-own card match.

---

## Watchlist vs ticker

```js
var WATCHLIST       = [ ... 8 cars ... ]      // sidebar plus main chart
var TICKER_UNIVERSE = [ ... 29 cars ... ]     // scrolling tape only
```

Both arrays use the same schema. The only difference is where the car appears.

Put a car in `WATCHLIST` when you want it always visible with a colored line on the main chart. Put it in `TICKER_UNIVERSE` when you want it on the tape but not always on screen. In the dashboard editor, the `list` dropdown sets this. You can also promote a ticker car in-browser via "Move to Watchlist" (localStorage only); to make that permanent, move it in the editor or the config and commit.

---

## What happens after you commit

1. You push to GitHub.
2. Vercel and Netlify redeploy in about 30 seconds. The car appears on the ticker, and in the watchlist if you put it there.
3. Until real sales exist, the car shows a flat line marked **MANUAL**. This is the honest "no data yet" state, not a bug.
4. The Sunday GitHub Actions cron (or a manual run) runs `scrape_prices.py` then `generate_history.py`. It pulls sold prices, stores them in `price_history.json`, rebuilds `data.js` as a rolling-90-day median line plus a scatter of the real sales, and patches `avg_price`, `prev_avg`, and the duty in the config.
5. To seed real historical sales for US-market cars right away, run the backfill once (see below) instead of waiting for the cron.

### How prices are computed now

- Only **sold** prices set the value. Bring a Trailer, Cars & Bids, and classic.com are sold sources. KBB, Edmunds, and CarGurus are asking-price references and never set the price.
- The value is the **median** of sold prices, not the mean, so one outlier sale does not move it.
- Every car shows its sample size ("N sales, 90d") and a status badge: **LIVE**, **STALE** (no sale in 30+ days), **THIN** (fewer than 3 sales in 90 days), or **MANUAL** (no market data).

---

## Running the backfill and updates (Code does this)

```
cd scraper
pip install -r requirements.txt

# validate BaT returns data BEFORE the real run (writes nothing)
python backfill_history.py --dry-run

# if the dry-run shows real per-car counts:
python backfill_history.py        # seeds real historical sales
python generate_history.py        # builds the charts from real sales

# the recurring weekly job:
python scrape_prices.py
python generate_history.py
```

Always run `--dry-run` first. If it returns near-zero, Bring a Trailer is blocking the scraper or its markup shifted; stop rather than commit empty charts.

---

## Sanity checks before committing

1. **`id` must be unique.** Duplicate ids confuse the scraper's price patcher.
2. **`color` must reference a real `CHART_COLORS` entry.** Check the top of the file. A bad name leaves the line undefined.
3. **Trailing comma after each car block.** A missing comma is a syntax error and the dashboard goes blank. Open the page, hit F12, read the console.
4. **Use a realistic `avg_price`, not 0.** The chart and cost-to-own anchor on it.

You no longer compute `total_first_year_extra`. It is derived.

---

## Local testing

```
cd frontend
python3 -m http.server 8000
# open http://localhost:8000
```

Regenerate `data.js` without scraping, to preview new cars:

```
python3 scraper/generate_history.py --dev
```

This builds the chart objects from the current config and `price_history.json` without writing real data or touching the config.

---

## Removing a car

Delete its block from the array, or click **del** in the dashboard editor and Export. The scraper and dashboard stop referencing it on the next run. A user who promoted it locally keeps seeing it until they clear browser data; new visitors do not.

---

## Extra scrape sources (optional)

The scraper hits classic.com (from `market_url`), Bring a Trailer (from `bat_url`), and Cars & Bids (built automatically from the label). To add more, use `scrape_extras`:

```js
scrape_extras: [
  { type: 'kbb',     url: 'https://www.kbb.com/nissan/gt-r/2020/' },
  { type: 'edmunds', url: 'https://www.edmunds.com/nissan/gt-r/2020/' },
],
```

Supported types: `kbb`, `edmunds`, `cargurus`. Note these are asking-price references: they appear for context but do not set the median price. Only sold sources do.

---

*Garage Terminal · Ghost Strategies · ghoststrategies.io*
