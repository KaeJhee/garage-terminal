# Garage Terminal: owner guide

Everything here happens in a web browser. `frontend/cars.config.js` holds every car. The dashboard's editor writes that file, you upload it to GitHub, and the site updates itself.

Bookmark the upload page: https://github.com/KaeJhee/garage-terminal/upload/main/frontend

## Add, edit or remove a car

1. Open https://garage.ghoststrategies.io and click **CONFIG** (gear, top bar).
2. Click **edit** on a car, **+ Add Car** for a new one, or **del** to remove one.
3. Fill in the fields (see "Fields" below) and click **Save Car**. Repeat for other cars.
4. Optional: **Preview in Session** shows the result in this browser only.
5. Click **Export cars.config.js**. The file downloads.
6. Open the upload page, drag the file in, and click **Commit changes**. The name must be exactly `cars.config.js`. Before exporting, delete the older `cars.config.js` from your Downloads folder, so the browser does not save the new one as `cars.config (1).js`.
7. A price run starts by itself. A few minutes later the site shows the change and fresh prices.

The site shows an uploaded file straight away, before any check runs. If the file has a problem, such as two cars with the same id, the price run stops, prices are not updated, and GitHub emails you that the run failed. Open the run and read the one-line reason. Then fix the car in the editor and upload again, or put the previous version back (see "If something goes wrong"). Check the site after every upload.

Do not rename an existing car's id: its stored sales are kept under the old id and would stop showing. Change the model or symbol instead.

A removed car disappears for new visitors. Anyone who moved it to their watchlist keeps it until they clear the site's data. Your own Export also clears it from your browser, so it does not come back in a later Export.

## Make a ticker car permanent in the watchlist

Click the car in the ticker, click **Move to Watchlist**, then **CONFIG**, **Export**, and upload. Export puts moved cars in the watchlist. **View on Main Chart** only lasts for this browser session and is never exported.

## Change a price, including the Chinese EVs

- US-market cars: each price run sets `avg_price` from Bring a Trailer sales once a car has at least 3 sales in the last two years whose median sits between 80% of `low_price` and 125% of `high_price`. To set a starting value, edit `avg_price` and upload. The next run with enough sales replaces it.
- Chinese cars (category Chinese): never scraped. Edit `avg_price` from Chinese sources (CnEVPost, CarNewsChina, Autohome) and upload. Put the old price in `prev_avg` so the change arrow shows the move.

## Fields

| Field | What it does |
|---|---|
| `id` | Unique slug, lowercase with hyphens. Set once. |
| `symbol` | Ticker label, uppercase, no spaces. |
| `list` | watchlist (sidebar and main chart) or ticker (scrolling tape). |
| `make`, `model`, `years`, `engine`, `power`, `note` | Display text. `years` such as `1995-1998` or `2023-Present` is also the model-year filter for sales; a single year applies no filter. |
| `category` | JDM, Modern, Exotic, Muscle, European or Chinese. A category added by hand is kept. |
| `avg_price`, `prev_avg` | Current price and the price before the last change (the arrow). |
| `low_price`, `high_price` | The price gauge, and the band that guards the price (see BAND_REFUSED). |
| `bat_url` | The Bring a Trailer search the price comes from, and the Listings button. |
| `market_url` | The Market button. Not scraped. |
| Cost to own | Insurance, maintenance, import duty rate (0 for US cars), shipping, registration. The page works out the duty and the first-year total. |

## Title filters and extra searches: a small edit on github.com

The editor has no boxes for `bat_title_include`, `bat_title_exclude` or `scrape_extras`, but Export keeps them. To change one, open `frontend/cars.config.js` on GitHub, click the pencil (Edit this file), edit the lines inside the car's block, and click **Commit changes**. That also starts a price run. The site shows the edit at once, so keep the commas and quotes exactly as in these examples, then check the site. If it shows no cars, undo the edit (see "If something goes wrong"). Examples:

```js
    bat_title_exclude: ['GT4 RS'],
    scrape_extras: [
      { type: 'bat_search', url: 'https://bringatrailer.com/search/?s=nissan+gt-r', years: '2017-2020' },
    ],
```

## Cars that need a look

After every price run, the issue **Cars that need a look** lists each car whose price could not be checked, with what to do. GitHub emails you when it opens and when its list changes (you watch your own repository by default). It closes itself when the list is empty. If you close it yourself, it stays closed until the list changes. Each run's full table is on the run's Summary page in the Actions tab.

| Code | What it means | What to do |
|---|---|---|
| NO_BAT_SEARCH | The car has no Bring a Trailer search. | Put a search in `bat_url`, or add a `scrape_extras` search if `bat_url` must point elsewhere. |
| SEARCH_404 | Bring a Trailer found no results for the search. | Try plainer words, such as a model name instead of a chassis code. |
| FETCH_FAILED | Bring a Trailer did not answer. A first failure is only mentioned below the list; the car joins the list if it fails again the next run. | Usually nothing. If it is in the list, check the search link. |
| NO_CARDS | The page loaded but showed no listings. | Change `bat_url` to a search that shows this car. |
| ALL_REJECTED | Listings were found, none counted: unsold, other years or parts, title words, or a price far off. | The issue says which. Other years or title words: widen `years` or the title words. Price far off: set `avg_price`, `low_price` and `high_price` near the sale prices. Other cars: change `bat_url`. |
| BAND_REFUSED | The sales median is outside the price band, so the price was kept. | If the sales are the right car, use the suggested `low_price` and `high_price`. If not, fix the search. |
| ANCHOR_OFF | `avg_price` is far from its own band or its recent sales. | Correct whichever of `avg_price`, `low_price` or `high_price` is wrong. |
| THIN | Fewer than 3 recent sales, so the price holds. | Nothing. Listed for information. |
| MANUAL | Chinese car, priced by hand. | Nothing. Never a problem. |

## If something goes wrong

- Re-running is always safe: Actions tab, **Weekly Price Update**, **Run workflow**. A price can still move without a new sale, when an old sale passes two years and stops counting.
- A failed scrape commits nothing, so prices stay as they were. The run page keeps its scrape as a download for 90 days. An uploaded `cars.config.js` is different: it is live as soon as it is uploaded.
- A file with another name, such as `cars.config (1).js`, was uploaded by mistake: every price run fails until it is gone. Open it on GitHub, open the **...** menu, choose **Delete file**, and click **Commit changes**. Then upload `cars.config.js` again.
- To undo a change: open `frontend/cars.config.js` on GitHub, click **History**, open the version you want, click **Download raw file**, and upload it with the upload link. The run that follows puts back the newer scraped price of every car with enough recent sales.

## Hosting

Vercel publishes every push to main. The project's Root Directory is `frontend`, set in the Vercel dashboard. The scheduled price run is every Sunday at 00:00 UTC.

---


## Notes moved from cars.config.js

These notes used to sit inside `cars.config.js`. They moved here, word for word, so that an Export from the editor reproduces the file exactly. Some lines describe the older way of working (committing by hand, pasting a snippet, the April 2026 starting prices). Where they differ from the steps above, the steps above are current.

### Field reference (the old file header)

```text
/**
 * ============================================================
 * GARAGE TERMINAL - CAR CONFIGURATION
 * ============================================================
 *
 * SINGLE SOURCE OF TRUTH. The chart, ticker, watchlist, scraper,
 * and price history all read from this file.
 *
 * EASIEST WAY TO EDIT: the dashboard CONFIG button (gear, top bar).
 * Add/edit cars, Preview live, Export this file, commit it. The
 * editor derives the duty fields and writes colors for you.
 *
 * BY HAND: copy a car block from WATCHLIST or TICKER_UNIVERSE,
 * paste at the end of the array, change the fields, commit.
 * Full guide: HOW_TO_ADD_A_CAR.md
 *
 * ============================================================
 * FIELD REFERENCE
 * ============================================================
 *
 * id          -> Unique slug, lowercase, hyphens only.
 * symbol      -> Ticker label, uppercase, no spaces.
 * make/model  -> Display info. model is the chart header.
 * years       -> Production years, e.g. "1995-1998".
 * category    -> JDM | Modern | Exotic | Muscle | European | Chinese
 * engine/power-> Specs strip text.
 * avg_price   -> Current market price USD (integer). Scraper
 *                overwrites this weekly for US-market cars.
 * low/high    -> Range ends for the price gauge.
 * prev_avg    -> Prior value, drives the delta arrow.
 * color       -> CHART_COLORS.<name> (see palette below).
 * note        -> One-line market insight.
 * bat_url     -> Bring a Trailer search URL (scraped).
 * market_url  -> Market link on the dashboard (not scraped).
 * cost_to_own -> First-year ownership costs:
 *   insurance_annual, insurance_note,
 *   import_duty_pct (0 for US-spec), shipping_est,
 *   maintenance_annual, maintenance_note,
 *   registration_est (OPTIONAL, imports),
 *   import_note (OPTIONAL, imports).
 *
 * DERIVED, DO NOT SET: import_duty_est and total_first_year_extra
 * are computed live from avg_price * import_duty_pct + flat costs.
 *
 * PRICING: only SOLD Bring a Trailer listings set the price, as the
 * MEDIAN of the last two years, once there are 3 or more sales.
 *
 * ============================================================
 * CHART COLORS
 * ============================================================
 */
```

### Chart color notes (beside the palette)

```text
  amber:   '#e8a020',   // R33 GTR (in use)
  teal:    '#3cb8c0',   // R32 GTR (in use)
  green:   '#3ab86e',   // Supra A80 (in use)
  blue:    '#4b8ef5',   // R35 GTR (in use)
  purple:  '#a06ef0',   // Huracan STO (in use)
```

### Watchlist notes

```text
/**
 * ============================================================
 * WATCHLIST - Cars shown in the sidebar and on the main chart
 * ============================================================
 */
  // DREAM CAR
  // JDM LEGENDS
  // MODERN
  // EXOTIC
  // ADD NEW WATCHLIST CARS BELOW THIS LINE
  // (User-promoted cars from the ticker are stored in localStorage
  //  and merged at runtime. To make permanent, paste the snippet
  //  produced by the "Move to Watchlist" copy button here.)
```

The watchlist labels grouped the cars as: DREAM CAR (r33-gtr), JDM LEGENDS (r32-gtr, supra-a80), MODERN (r35-gtr), EXOTIC (huracan-sto).

### Chinese NEV import and tariff notes (above nio-es9, zeekr-9x and aito-m9)

```text
  // ============================================================
  // CHINESE NEV FLAGSHIPS - grey-market import cost modeling
  // ------------------------------------------------------------
  // These are NOT US-legal. No FMVSS/EPA certification and they are
  // brand new, so the 25-yr import exemption does not apply. Realistic
  // routes are Show-or-Display (NHTSA, ~2,500 mi/yr cap, rarely granted)
  // or off-road/private use only. Costs modeled as worst-case landed.
  //
  // TARIFF: Section 301 levies 100% on Chinese pure-BEVs (HTS 8703.80)
  // on top of the 2.5% MFN auto duty. Plug-in hybrids and EREVs fall
  // under different HTS codes that carry the 25% Section 301 rate, not
  // the 100%, so the PHEV/EREV cars below model ~37.5% effective.
  // Rates current as of mid-2026; adjust import_duty_pct if policy moves.
  // avg_price = China market value converted to USD (the car itself).
  // ============================================================
```

### Ticker notes

```text
/**
 * ============================================================
 * TICKER UNIVERSE - Cars in the scrolling ticker
 * ============================================================
 *
 * Every ticker entry uses the FULL watchlist schema. Click any
 * ticker symbol on the dashboard to open its detail panel with
 * a 90-day sparkline, listing links, and a "Move to Watchlist"
 * button that promotes the car to the main chart.
 *
 * Prices are estimates based on April 2026 market references
 * (Classic.com averages, BaT auction medians, KBB/Edmunds where
 * applicable). Update them when refreshing watchlist data.
 *
 * Maintenance/insurance estimates assume a clean, drivable
 * example with specialty insurance for classics (Hagerty/Grundy)
 * or full-coverage for moderns (TheZebra/CarEdge baseline).
 */
  // ==========================================================
  // JDM ICONS
  // ==========================================================
  // ==========================================================
  // EUROPEAN / EXOTIC
  // ==========================================================
  // ==========================================================
  // AMERICAN MUSCLE
  // ==========================================================
```

The ticker labels grouped the cars as: JDM ICONS (nsx-na1 to lancer-evo4), EUROPEAN / EXOTIC (458-spec to m4-csl), AMERICAN MUSCLE (gt500-21 to corvette-z06).

---

*Garage Terminal · Ghost Strategies · ghoststrategies.io*
