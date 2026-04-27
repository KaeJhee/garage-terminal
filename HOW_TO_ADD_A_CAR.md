# How to Add a Car

`cars.config.js` is the single source of truth for the entire dashboard. Add a car there and **everything else updates automatically** — the chart, the ticker, the watchlist, the scraper, the price history. You never edit Python files, the HTML, or the workflow.

This is by design.

---

## The 60-second version

1. Open `frontend/cars.config.js`
2. Decide: should this car go in the **watchlist sidebar** or just on the **scrolling ticker**?
   - **Watchlist** = always visible in the left sidebar, gets a colored line on the main chart. Pick this for cars you actively track.
   - **Ticker** = scrolls across the top tape. Click to open the detail modal. Pick this for cars you're casually watching but don't need on the main chart.
3. Copy an existing car's block from the matching array (`WATCHLIST` or `TICKER_UNIVERSE`)
4. Paste it at the end of the array, change the fields
5. Save, commit, push

That's the whole workflow. The scraper picks it up next Sunday, generates 365 days of history, and updates the dashboard.

---

## The fields

```js
{
  id:         'mclaren-p1',                   // unique slug, lowercase, hyphens
  symbol:     'P1',                            // ticker label, 6-8 chars uppercase
  make:       'McLaren',
  model:      'P1',
  years:      '2013-2015',
  category:   'Exotic',                        // JDM | Modern | Exotic | Muscle | European
  engine:     '3.8L Twin-Turbo V8 Hybrid',
  power:      '903 hp',
  avg_price:  1900000,                         // current market avg (USD, integer)
  low_price:  1500000,                         // typical low end of the range
  high_price: 2400000,                         // typical high end
  prev_avg:   1850000,                         // previous period - used for delta arrow
  color:      CHART_COLORS.purple,             // pick from the CHART_COLORS palette
  note:       'Limited to 375 units. Prices climbing on hybrid hypercar revival.',
  bat_url:    'https://bringatrailer.com/search/?s=mclaren+p1',
  market_url: 'https://www.classic.com/m/mclaren/p1/',

  cost_to_own: {
    insurance_annual:       8000,
    insurance_note:         'Hagerty agreed-value or Chubb collector policy',
    import_duty_pct:        0,                 // 0 for US-spec cars
    import_duty_est:        0,                 // 0 for US-spec cars
    shipping_est:           0,                 // 0 for US-spec / domestic cars
    maintenance_annual:     12000,
    maintenance_note:       'Carbon tub inspection, hybrid battery service, McLaren-only',
    total_first_year_extra: 20000,             // sum of insurance + maintenance + duty + shipping
  },
},
```

### Field reference

| Field | What it does |
|-------|--------------|
| `id` | Unique slug. Used internally and for localStorage. Must match nothing else in the file. |
| `symbol` | Short ticker label shown on the scrolling tape and watchlist. 6-8 chars, uppercase, no spaces. |
| `make` / `model` / `years` | Display info. `model` shows on the chart header, `years` shows in the specs strip. |
| `category` | Drives the JDM Avg / Exotic Avg KPI tiles. Stick to: `JDM`, `Modern`, `Exotic`, `Muscle`, `European`. |
| `engine` / `power` / `note` | Specs strip + market note. Free-form text. |
| `avg_price` / `low_price` / `high_price` | Drive the price gauge and chart. The scraper will overwrite `avg_price` weekly with real market data. |
| `prev_avg` | Used to calculate the up/down arrow and percentage. The scraper overwrites this on each run with the prior week's `avg_price`. |
| `color` | Line color on the main chart. Pick from `CHART_COLORS` (defined at the top of the file). |
| `bat_url` | **Important.** This is what the scraper hits on Bring a Trailer. Use a search URL like `bringatrailer.com/search/?s=mclaren+p1`. |
| `market_url` | **Important.** This is what the scraper hits on classic.com. Use the model market page like `classic.com/m/mclaren/p1/`. |
| `cost_to_own` | All fields are required. For US-spec cars, set `import_duty_pct`, `import_duty_est`, and `shipping_est` to 0 — the dashboard will show "N/A · US Spec". |

### Computing `total_first_year_extra`

Add up the four cost components:

```
total_first_year_extra = insurance_annual + maintenance_annual + import_duty_est + shipping_est
```

For a US-spec car: only insurance + maintenance.
For a JDM import: all four.

The dashboard does not validate this — it just displays whatever you put. If the math is off, the "Year 1 Extra" total in the Cost-to-Own panel will be wrong. Easy to spot, easy to fix.

### Picking the right `bat_url` and `market_url`

The scraper uses these URLs. If they're broken or ambiguous, the scraper falls back to the `avg_price` you set. So while the dashboard works either way, real scraped pricing only happens when the URLs resolve.

**Bring a Trailer** — go to bringatrailer.com, search for the car, copy the URL of the search results page:
```
https://bringatrailer.com/search/?s=mclaren+p1
```

**classic.com** — go to classic.com, navigate to the make/model market page (not a specific listing). The URL pattern is:
```
https://www.classic.com/m/<make>/<model>/
https://www.classic.com/m/mclaren/p1/
https://www.classic.com/m/nissan/skyline/r34/gt-r/
```

If classic.com doesn't have a page for the car (rare), point `market_url` at the closest related page or just the make page. The scraper will gracefully fall back.

---

## Watchlist vs Ticker — picking the right array

The two arrays in `cars.config.js`:

```js
var WATCHLIST       = [ ... 5 cars ... ]      // Sidebar + main chart
var TICKER_UNIVERSE = [ ... 29 cars ... ]     // Scrolling tape only
```

Both arrays use the **same exact schema**. The only difference is where the car appears on the dashboard.

**Put a car in `WATCHLIST` when:**
- You want it visible without clicking
- You want a colored line on the main chart you can compare against
- It's a primary tracking target

**Put a car in `TICKER_UNIVERSE` when:**
- You want it on the scrolling tape with all the others
- You want to see its price casually but don't need it always on screen
- You're keeping the watchlist focused on a small number of cars

You can always promote a ticker car later via the dashboard's "Move to Watchlist" button (which works in-browser via localStorage). To make it permanent across all browsers and the deployed site, you click "Copy config snippet" in the modal — it puts a paste-ready block on your clipboard. Paste that into the `WATCHLIST` array, push, done.

---

## What happens after you push

```
1. You push to GitHub
   |
   v
2. Vercel + Netlify see the push, redeploy in ~30s
   |
   v
3. Your new car appears on the dashboard
   - Watchlist sidebar (if added to WATCHLIST)
   - Scrolling ticker (always)
   - Detail modal works (click the ticker)
   - Sparkline shows a JS-generated walk based on avg_price
   |
   v
4. Sunday at midnight UTC, GitHub Actions runs:
   - scrape_prices.py reads cars.config.js, scrapes BaT + classic.com for every car
   - Writes scraper/scraped_prices.json
   - generate_history.py reads that JSON, regenerates frontend/data.js
     with real 365-day histories for every car
   - Patches avg_price + prev_avg in cars.config.js with the latest scraped prices
   - Commits + pushes
   - Triggers Netlify and/or Vercel redeploy
   |
   v
5. Dashboard now shows real market data for your new car
```

You don't touch `scrape_prices.py`, `generate_history.py`, the workflow, or `data.js`. They all read from `cars.config.js`.

---

## Quick sanity checks before pushing

A few things that have bitten in the past:

1. **`id` must be unique.** If two cars have the same `id`, the scraper patcher will get confused and silently corrupt the file.

2. **`color: CHART_COLORS.<name>` must reference a real palette entry.** Check the top of `cars.config.js` for the available names. If you write `CHART_COLORS.fuchsia` and that doesn't exist, the chart line will be undefined.

3. **Trailing comma after the closing brace.** The arrays use trailing commas:
   ```js
   {
     id: 'foo',
     ...
   },   // <-- this comma matters
   ```
   Missing it on a non-final entry causes a JavaScript syntax error and the whole dashboard goes blank. Easy to test locally before pushing — open `frontend/index.html` in your browser. If the page is blank, hit F12 and look at the console for the syntax error.

4. **`total_first_year_extra` math.** Add the four components yourself. The dashboard doesn't recalculate it.

5. **The `avg_price` is your initial value.** The scraper will replace it Sunday with whatever it finds. If the URLs are broken, your initial value sticks. So put in a realistic number — don't use 0 or a placeholder.

---

## Testing locally before pushing (optional but smart)

Quick way to verify nothing is broken:

```bash
cd ~/Desktop/garage-terminal/frontend
open index.html
```

Or use a tiny static server (avoids `file://` quirks):

```bash
cd ~/Desktop/garage-terminal/frontend
python3 -m http.server 8000
# then open http://localhost:8000 in your browser
```

If the new car shows up on the ticker and clicking it opens a detail modal with the right data, you're good to push.

To regenerate `data.js` locally without waiting for the Sunday cron:

```bash
cd ~/Desktop/garage-terminal
python3 scraper/generate_history.py --dev
```

This uses the `avg_price` values straight from `cars.config.js` and regenerates `data.js` for all cars. No scraping happens. Useful for previewing what the chart will look like before the next real scrape.

---

## Removing a car

Just delete its block from the array. The scraper, the data file, and the dashboard will all stop referencing it on the next run.

If a user has the car in their localStorage watchlist (via the "Move to Watchlist" feature), they'll keep seeing it locally until they clear browser data — but new visitors won't.

---

## Adding a category that isn't in the list

The dashboard only shows averages for `JDM` and `Exotic` in the sidebar KPIs. If you add `Hypercar` or `Pre-war` or whatever as a new category, those cars work fine but don't get a dedicated KPI tile. To add one, edit `renderPortfolio()` in `index.html`:

```js
var hyperCars = WATCHLIST.filter(c => c.category === 'Hypercar');
var hyperAvg  = hyperCars.length ? hyperCars.reduce((s,c)=>s+c.avg_price,0) / hyperCars.length : null;
// then add a kpi-row entry for it
```

This is the only place where the file structure isn't fully driven by `cars.config.js`. Everything else is.

---

## Adding extra scrape sources for a specific car

The default scraper hits two sources per car: classic.com (from `market_url`) and BaT (from `bat_url`). For most cars that's plenty.

If a car needs additional sources — say, KBB for current modern cars or Edmunds for late-model exotics — add a `scrape_extras` field:

```js
{
  id: 'r35-gtr-50th',
  ...
  bat_url:    'https://bringatrailer.com/search/?s=r35+gt-r+50th',
  market_url: 'https://www.classic.com/m/nissan/gt-r/r35/',
  scrape_extras: [
    { type: 'kbb',     url: 'https://www.kbb.com/nissan/gt-r/2020/' },
    { type: 'edmunds', url: 'https://www.edmunds.com/nissan/gt-r/2020/' },
  ],
  cost_to_own: { ... },
},
```

Supported `type` values: `kbb`, `edmunds`, `cargurus`. The scraper averages every source that returns a valid price.

This is optional — leave it off and the car gets the standard 2-source scrape.

---

## Troubleshooting

**"My car shows up but the price is wrong."**
The scraper either failed silently (network blip on Sunday) or the URLs aren't resolving. Check the GitHub Actions run log: Repo → Actions tab → most recent run. Look for the line `[your-car-id]` in the scraper output. If it says `using fallback`, the URLs need to be checked.

**"My car doesn't show up at all."**
Most likely a JS syntax error in `cars.config.js`. Open the dashboard, hit F12, look at the Console tab. The error will name the line.

**"The detail modal opens but the sparkline is flat."**
The car has `avg_price: 0` or no `avg_price`. The sparkline needs a non-zero value to anchor the walk.

**"The 'Move to Watchlist' feature added the car but it's not on the deployed site."**
That feature uses browser localStorage — it's local to that browser only. To make it permanent everywhere, click "Copy config snippet" in the modal, paste into `cars.config.js` WATCHLIST array, push to GitHub.

**"I added 10 cars and the data.js file got huge."**
Each car adds about 18-20KB of price history. 10 new cars = ~200KB extra in `data.js`. Still small by web standards (gzipped it's a fraction of that). If it ever becomes a real problem, the script can be updated to only generate history for WATCHLIST cars and let ticker cars use the JS-generated walk on demand. Not worth doing yet.

---

*Garage Terminal · Ghost Strategies · ghoststrategies.io*
