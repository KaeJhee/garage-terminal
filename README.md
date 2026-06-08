# Garage Terminal

A Bloomberg Terminal-style dashboard for tracking JDM, exotic, and Chinese-NEV car market prices. Built by Ghost Strategies.

![status](https://img.shields.io/badge/status-live-brightgreen) ![watchlist](https://img.shields.io/badge/watchlist-8-orange) ![tracked](https://img.shields.io/badge/cars%20tracked-37-blue)

---

## What it does

- **Real-sale price charts.** Each car shows a rolling 90-day median of actual sold prices, a P25 to P75 band, and a scatter of the individual sales behind it. 1M / 3M / 6M / 1Y views (Chart.js).
- **Honest data labeling.** Every car carries a status badge: LIVE, STALE (no sale in 30+ days), THIN (fewer than 3 sales in 90 days), or MANUAL (no market data), plus its sample size and the date of the last sale.
- **Scrolling ticker tape** with all 37 symbols, searchable and filterable.
- **Watchlist sidebar** with delta indicators and portfolio totals.
- **Detail modal** with price levels, cost-to-own, sparkline, and direct listing links.
- **In-dashboard config editor.** A CONFIG button opens an editor to add, edit, or remove cars, preview live, and export a complete `cars.config.js` to commit.
- **Mobile responsive** dark Bloomberg aesthetic, amber on black, monospace throughout.

---

## Watchlist

| Symbol | Car | Category | Avg Price |
|--------|-----|----------|-----------|
| R33GTR | Nissan Skyline R33 GT-R (1995-98) | JDM | $77,396 |
| R32GTR | Nissan Skyline R32 GT-R (1989-94) | JDM | $53,401 |
| SUPRAA80 | Toyota Supra MK4 A80 (1993-02) | JDM | $51,491 |
| R35GTR | Nissan GT-R R35 (2020) | Modern | $106,000 |
| HURASTO | Lamborghini Huracan STO (2022) | Exotic | $427,632 |
| NIO-ES9 | Nio ES9 | Chinese | $78,000 |
| ZEEKR9X | Zeekr 9X | Chinese | $75,000 |
| AITO-M9 | Aito M9 (EREV) | Chinese | $70,000 |

Plus a 29-car ticker universe spanning JDM, exotic, European, and muscle.

---

## How the data works

The charts are built from real individual sales, not a simulation.

- **Sold-only median.** Bring a Trailer, Cars & Bids, and classic.com are sold sources and set the price. KBB, Edmunds, and CarGurus are asking-price references that show for context but never move the value. The price is the median of sold prices, which resists outliers.
- **Accumulate plus backfill.** `price_history.json` stores individual real sales with date and venue. The weekly scrape appends new sales. A one-time backfill seeds historical sales from BaT's completed-auction archive.
- **Rolling median line plus scatter.** `generate_history.py` builds a daily trailing-90-day median line with a P25 to P75 band, and emits the individual sales for the scatter. The line is solid where a recent sale anchors it, dashed where it is interpolated from older sales, and greyed where stale or manual.
- **No invented history.** A car with no sales yet shows a flat line marked MANUAL. Charts start where real data starts. This flat-until-data state is honest, not broken.
- **Chinese NEVs are manual.** The Nio, Zeekr, and Aito have no US market to scrape. Their prices come from Chinese sources and are entered with `add_manual_price.py`, then charted as a stepped manual line.

---

## Project structure

```
garage-terminal/
├── frontend/
│   ├── index.html         Full dashboard, self-contained, plus the config editor
│   ├── cars.config.js     Single source of truth: cars, prices, cost-to-own
│   ├── data.js            Generated charts: BAKED_HISTORY, BAKED_SALES, BAKED_META
│   └── price_history.json Accumulated real individual sales (the data store)
├── scraper/
│   ├── scrape_prices.py     Sold-only median from BaT + Cars & Bids + classic.com
│   ├── backfill_history.py  One-time historical seed from BaT completed auctions
│   ├── generate_history.py  Builds data.js (rolling median + scatter + status meta)
│   ├── add_manual_price.py  Logs manual prices for no-market cars (Chinese NEVs)
│   └── requirements.txt
├── backend/
│   └── main.py            Optional FastAPI server for live/refreshed data
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
| Backend | FastAPI plus Uvicorn (optional) |
| Hosting | Netlify / Vercel (static), GitHub Actions for the weekly cron |

---

## Data sources

- [Bring a Trailer](https://bringatrailer.com) and [Cars & Bids](https://carsandbids.com): real completed-auction sold prices (the primary feed).
- [classic.com](https://www.classic.com): auction-aggregated sold data where reachable.
- KBB, Edmunds, CarGurus: asking-price references only, never set the median.
- Chinese NEVs: [CnEVPost](https://cnevpost.com), [CarNewsChina](https://data.carnewschina.com), and Autohome, entered manually.
- [Hagerty Valuation Tools](https://www.hagerty.com/valuation-tools): the gold-standard condition-adjusted source. Paid (Drivers Club), no free API. The reliable upgrade path if this goes client-facing.

---

## License

MIT. Use it, fork it, build on it.

---

*Built by Ghost Strategies · ghoststrategies.io*
