# Garage Terminal

A Bloomberg Terminal-style dashboard for tracking JDM, exotic, and Chinese-NEV car market prices. Built by Ghost Strategies.

![status](https://img.shields.io/badge/status-live-brightgreen) ![watchlist](https://img.shields.io/badge/watchlist-8-orange) ![tracked](https://img.shields.io/badge/cars%20tracked-37-blue)

---

## What it does

- **Price charts with real sale dots.** Each car shows an indicative estimate line anchored to its tracked price, plus a dot for each sold price the weekly scrape found. 1M / 3M / 6M / 1Y views (Chart.js).
- **Clear data labeling.** Every chart is marked EST because the line is indicative, not observed prices. It also shows how many scraped sale results are plotted, a THIN flag when there are fewer than 3, and the date of the latest one.
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

- **Sold-only median.** Each weekly run takes the median of the sold prices the scraper can reach (Bring a Trailer, plus Cars & Bids and classic.com where reachable) and writes it to the car's tracked price in `cars.config.js`. KBB, Edmunds, and CarGurus are asking-price references that show for context but never move the value. The median resists outliers.
- **Accumulate plus backfill.** `price_history.json` stores scraped sold prices with a date and venue. Each weekly scrape appends the sold prices it found, dated to the scrape day and de-duplicated only within that week, so the same sale can appear in several weeks. A one-time backfill seeded historical sales from BaT's completed-auction archive.
- **Estimate line plus sale dots.** `generate_history.py` draws each car's line as a 365-day mean-reverting path that ends at the tracked price. The path is generated deterministically per car, so it stays stable between runs, but it is an illustration, not observed prices. The dots are the scraped sold prices that fall within a plausible range of the tracked price.
- **What the counts mean.** The sale count on each chart counts scraped results, including repeats across weeks, so it overstates the number of unique sales. The dates on the dots are scrape dates, not auction end dates.
- **Chinese NEVs are manual.** The Nio, Zeekr, and Aito have no US market to scrape. Their prices come from Chinese sources and are entered with `add_manual_price.py`.

---

## Project structure

```
garage-terminal/
├── frontend/
│   ├── index.html         Full dashboard, self-contained, plus the config editor
│   ├── cars.config.js     Single source of truth: cars, prices, cost-to-own
│   ├── data.js            Generated charts: BAKED_HISTORY, BAKED_SALES, BAKED_META
│   └── price_history.json Accumulated scraped sold prices (the data store)
├── scraper/
│   ├── scrape_prices.py     Sold-only median from BaT + Cars & Bids + classic.com
│   ├── backfill_history.py  One-time historical seed from BaT completed auctions
│   ├── generate_history.py  Builds data.js (estimate line + sale dots + meta) and updates tracked prices
│   ├── add_manual_price.py  Logs manual prices for no-market cars (Chinese NEVs)
│   └── requirements.txt
├── backend/
│   └── main.py            Optional FastAPI demo server (mock data; the dashboard does not use it)
├── README.md
├── HOW_TO_ADD_A_CAR.md    Adding and updating vehicles
└── LICENSE
```

---

## Adding or updating cars

Two ways, both end in committing `cars.config.js`:

1. **Dashboard editor.** Click CONFIG, edit or add, Preview, Export, then commit the downloaded file.
2. **Hand-edit `cars.config.js`** and commit.

`import_duty_est` and `total_first_year_extra` are derived automatically from `avg_price` and `import_duty_pct`, so you never enter them. Full detail, including the Chinese-car manual price workflow, is in `HOW_TO_ADD_A_CAR.md`.

---

## Operations

```
cd scraper
pip install -r requirements.txt

# seed real history (run once; US-market cars only)
python backfill_history.py --dry-run     # validate BaT returns data; writes nothing
python backfill_history.py               # then the real seed
python generate_history.py               # build the charts

# weekly update (the recurring job, also run by GitHub Actions)
python scrape_prices.py
python generate_history.py

# log a Chinese-car price change
python add_manual_price.py nio-es9 78000 --date 2026-06-15
python generate_history.py
```

Always run `backfill_history.py --dry-run` before the real backfill. If it returns near-zero, BaT is blocking the scraper or its markup changed; stop rather than commit empty charts.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vanilla HTML, CSS Grid, JavaScript (ES2020) |
| Charts | Chart.js 4.x |
| Fonts | DM Mono, DM Sans (Google Fonts) |
| Scraper | Python (httpx, BeautifulSoup) |
| Backend | Optional FastAPI demo server (not used by the dashboard) |
| Hosting | Netlify / Vercel (static), GitHub Actions for the weekly cron |

---

## Data sources

- [Bring a Trailer](https://bringatrailer.com): completed-auction sold prices (the primary feed).
- [Cars & Bids](https://carsandbids.com): completed-auction sold prices where reachable.
- [classic.com](https://www.classic.com): auction-aggregated sold data where reachable.
- KBB, Edmunds, CarGurus: asking-price references only, never set the median.
- Chinese NEVs: [CnEVPost](https://cnevpost.com), [CarNewsChina](https://data.carnewschina.com), and Autohome, entered manually.
- [Hagerty Valuation Tools](https://www.hagerty.com/valuation-tools): the gold-standard condition-adjusted source. Paid (Drivers Club), no free API. The reliable upgrade path if this goes client-facing.

---

## License

MIT. Use it, fork it, build on it.

---

*Built by Ghost Strategies · ghoststrategies.io*
