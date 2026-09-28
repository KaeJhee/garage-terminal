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
| `make` / `model` | Display info. `model` is the chart header. |
| `years` | Shown in the specs strip, and also the scraper's model-year filter. A range such as `1995-1998` or `2023-Present` drops Bring a Trailer listings whose title year falls outside it (Present allows next year's models) and removes matching stored backfill entries, so the range must cover every model year that should count. A single year such as `2022` applies no filter. |
| `category` | Drives the KPI tiles. Use: `JDM`, `Modern`, `Exotic`, `Muscle`, `European`, `Chinese`. |
| `engine` / `power` / `note` | Specs strip and market note. Free-form text. |
| `avg_price` / `low_price` / `high_price` | Drive the price gauge and chart. The weekly run updates `avg_price` only when at least 3 sold listings ended in the last two years and their median falls between 80% of `low_price` and 125% of `high_price`. |
| `prev_avg` | Used for the up/down arrow and percentage. The scraper overwrites it with the prior period's value. |
| `color` | Chart line color. Pick a name from `CHART_COLORS` at the top of the file. |
| `bat_url` | Bring a Trailer search URL the scraper hits. Example: `bringatrailer.com/search/?s=mclaren+p1`. |
| `bat_title_include` | Optional. A listing counts only if its title contains one of these words, for a specific trim. Example: `['Turbo II', 'Turbo 2']`. |
| `bat_title_exclude` | Optional. Listings whose title contains any of these words are skipped. Example: `['Speciale A', 'Aperta']`. Bring a Trailer often sends a search to a model page that also lists sibling versions (the `cayman gt4` search lands on a page with GT4 RS sales), so exclude those here. |
| `market_url` | The dashboard's Market link. Not scraped. Example: `classic.com/m/mclaren/p1/`. |
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

**US-market cars:** you usually do not need to. The weekly scrape replaces `avg_price` and `prev_avg` with the real sold median once there are at least 3 recent qualifying sales and their median is near the car's price band (80% of `low_price` to 125% of `high_price`); until then the value you set stays. If you want to set a starting value or a manual override, edit `avg_price` (in the editor or by hand) and the duty and total recompute on their own.

**Chinese cars, and any car with no US market:** these are different. The Nio, Zeekr, and Aito cannot be sold in the US, so the scraper skips cars in the `Chinese` category and they stay manual. Update their `avg_price` by hand (in the editor or the config) from Chinese sources (CnEVPost, CarNewsChina, Autohome); the KPI tiles, the estimate line, and the cost-to-own card all follow it.

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
3. Until real sales exist, the chart shows the estimate line and "no real sales on record". This is the honest "no data yet" state, not a bug.
4. The Sunday GitHub Actions cron (or a manual run) runs `scrape_prices.py` then `generate_history.py`. It pulls sold prices, stores them in `price_history.json`, rebuilds `data.js` as an estimate line plus a dot for each day in the past year with a real sale (the median when several share a day), and patches `avg_price`, `prev_avg`, and the duty when there are enough recent sales.

### How prices are computed now

- Only **sold** Bring a Trailer listings set the value, each counted once by listing ID and dated to the auction end. Bring a Trailer is the only source scraped.
- The value is the **median** of sold prices, not the mean, so one outlier sale does not move it.
- Every chart is marked **EST** (the line is indicative) and shows how many sold listings fall in the last year, how many are on record, a **THIN** flag when fewer than 3 are plotted, and the date of the last sale.

---

## Running the weekly update (Code does this)

```
cd scraper
pip install -r requirements.txt

# the recurring weekly job:
python scrape_prices.py
python generate_history.py
```

If no Bring a Trailer page shows a single sold result, `scrape_prices.py` stops with an error and writes nothing. That means Bring a Trailer is blocking the scraper or its markup shifted; nothing is committed that week.

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

This rewrites only `data.js`, from the current config and `price_history.json`. The store and the config are not touched.

---

## Removing a car

Delete its block from the array, or click **del** in the dashboard editor and Export. The scraper and dashboard stop referencing it on the next run. A user who promoted it locally keeps seeing it until they clear browser data; new visitors do not.

---

## Extra scrape sources (optional)

The scraper reads Bring a Trailer from `bat_url` (`market_url` is only the dashboard's Market link). To add more Bring a Trailer searches or model pages for a car, each with its own filters, use `scrape_extras`:

```js
scrape_extras: [
  { type: 'bat_search', url: 'https://bringatrailer.com/nissan/gtr-r35/', years: '2017-2024', exclude: ['Wheels'] },
],
```

`years`, `include`, and `exclude` work like the car's `years`, `bat_title_include`, and `bat_title_exclude`. Only `bat_search` entries are scraped; entries of any other type are kept in the config but logged as "no scraper" and never fetched.

---

*Garage Terminal · Ghost Strategies · ghoststrategies.io*
