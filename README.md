# Garage Terminal

A Bloomberg Terminal-style dashboard for tracking JDM, exotic, and Chinese-NEV car market prices. Built by Ghost Strategies.

![status](https://img.shields.io/badge/status-live-brightgreen) ![watchlist](https://img.shields.io/badge/watchlist-8-orange) ![tracked](https://img.shields.io/badge/cars%20tracked-37-blue)

---

## What it does

- **Price charts with real sale dots.** Each car shows an indicative estimate line anchored to its tracked price, plus a dot for each day in the past year with a real sale, placed on the auction end date (the median when several sales share a day). 1M / 3M / 6M / 1Y views (Chart.js).
- **Clear data labeling.** Every chart is marked EST because the line is indicative, not observed prices. It also shows how many sold listings fall in the chart's year and how many are on record, a THIN flag when fewer than 3 are plotted, and the date of the last sale.
- **Scrolling ticker tape** with all 37 symbols, searchable and filterable.
- **Watchlist sidebar** with delta indicators and portfolio totals.
- **Detail modal** with price levels, cost-to-own, sparkline, and direct listing links.
- **In-dashboard config editor.** A CONFIG button opens an editor to add, edit, or remove cars, preview live, and export a complete `cars.config.js` to commit.
- **Mobile responsive** dark Bloomberg aesthetic, amber on black, monospace throughout.

---

## Watchlist

| Symbol | Car | Category |
|--------|-----|----------|
| R33GTR | Nissan Skyline R33 GT-R (1995-98) | JDM |
| R32GTR | Nissan Skyline R32 GT-R (1989-94) | JDM |
| SUPRAA80 | Toyota Supra MK4 A80 (1993-02) | JDM |
| R35GTR | Nissan GT-R R35 (2020) | Modern |
| HURASTO | Lamborghini Huracan STO (2022) | Exotic |
| NIO-ES9 | Nio ES9 | Chinese |
| ZEEKR9X | Zeekr 9X | Chinese |
| AITO-M9 | Aito M9 (EREV) | Chinese |

Current prices live in `frontend/cars.config.js`, which the weekly job updates.

Plus a 29-car ticker universe spanning JDM, exotic, European, and muscle.

---

## How the data works

Tracked prices come from real sold prices. The chart lines are an estimate drawn around them, and the dots are the scraped sales.

- **Sold-only median, with a minimum sample.** Each weekly run takes the median of recent Bring a Trailer sales and writes it to the car's tracked price in `cars.config.js`, but only when at least 3 qualifying sales ended in the last two years and the median falls between 80% of the car's `low_price` and 125% of its `high_price`. Otherwise the tracked price stays where it is and the chart shows how old the last sale is. Bring a Trailer is the only source scraped.
- **Each sale stored once.** The scraper reads Bring a Trailer's listing cards: the listing ID, title, sold price, and auction end date. When BaT redirects a search to a model page (for example `/mclaren/720s/`), it reads the page's embedded list of recent completed auctions instead, with the same rules. Unsold auctions ("Bid to") are skipped, and so are listings whose model year falls outside the car's configured `years` range (a range such as `1995-1998` or `2023-Present`, where Present allows next year's models; a single year applies no filter). Optional `bat_title_include` and `bat_title_exclude` words narrow a search to one trim, and are re-checked every run against stored sales that carry a listing title (untitled backfill rows can't be judged and are kept). `price_history.json` keeps each sale once by listing ID, dated to when the auction ended. A one-time backfill seeded historical sales from BaT's completed-auction archive.
- **Estimate line plus sale dots.** `generate_history.py` draws each car's line as a 365-day mean-reverting path that ends at the tracked price. The path is generated deterministically per car, so it stays stable between runs, but it is an illustration, not observed prices. The dots are the scraped sold prices that fall within a plausible range of the tracked price.
- **Coverage.** A search page lists only a handful of results, so thinly traded cars can have few dots and old last-sale dates. That is shown, not hidden.
- **Chinese NEVs are manual.** The Nio, Zeekr, and Aito have no US market to scrape. Their prices come from Chinese sources and are set by hand as `avg_price` in `cars.config.js`; the scraper skips the `Chinese` category.

---

## Project structure

```
garage-terminal/
├── frontend/
│   ├── index.html         Full dashboard, self-contained, plus the config editor
│   ├── cars.config.js     Single source of truth: cars, prices, cost-to-own
│   ├── data.js            Generated charts: BAKED_HISTORY, BAKED_SALES, BAKED_META
│   └── price_history.json Real sales, each stored once (the data store)
├── scraper/
│   ├── scrape_prices.py     Sold listings from Bring a Trailer, each by listing ID
│   ├── generate_history.py  Builds data.js (estimate line + sale dots + meta) and updates tracked prices
│   └── requirements.txt
├── README.md
├── HOW_TO_ADD_A_CAR.md    Adding and updating vehicles
└── LICENSE
```

---

## Adding or updating cars

Two ways, both end in committing `cars.config.js`:

1. **Dashboard editor.** Click CONFIG, edit or add, Preview, Export, then commit the downloaded file.
2. **Hand-edit `cars.config.js`** and commit.

Import duty and the first-year total are worked out by the page from `avg_price` and `import_duty_pct`, so the file stores neither. Full detail, including the Chinese-car manual price workflow, is in `HOW_TO_ADD_A_CAR.md`.

---

## Operations

```
cd scraper
pip install -r requirements.txt

# weekly update (the recurring job, also run by GitHub Actions)
python scrape_prices.py
python generate_history.py

# rebuild data.js only (no scrape; the store and config are not touched)
python generate_history.py --dev
```

If no Bring a Trailer page shows a single sold result, `scrape_prices.py` stops with an error and writes nothing, so a blocked scraper or a markup change fails the run instead of committing an empty week.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vanilla HTML, CSS Grid, JavaScript (ES2020) |
| Charts | Chart.js 4.x |
| Fonts | DM Mono, DM Sans (Google Fonts) |
| Scraper | Python (httpx, BeautifulSoup) |
| Hosting | Netlify / Vercel (static), GitHub Actions for the weekly cron |

---

## Data sources

- [Bring a Trailer](https://bringatrailer.com): completed-auction sold prices (the primary feed).
- Chinese NEVs: [CnEVPost](https://cnevpost.com), [CarNewsChina](https://data.carnewschina.com), and Autohome, entered manually.
- [Hagerty Valuation Tools](https://www.hagerty.com/valuation-tools): the gold-standard condition-adjusted source. Paid (Drivers Club), no free API. The reliable upgrade path if this goes client-facing.

---

## License

MIT. Use it, fork it, build on it.

---

*Built by Ghost Strategies · ghoststrategies.io*
