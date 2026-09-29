# Garage Terminal

A Bloomberg Terminal-style dashboard of collector car prices: JDM, exotic, European, muscle and Chinese NEV. Live at https://garage.ghoststrategies.io. Built by Ghost Strategies.

![status](https://img.shields.io/badge/status-live-brightgreen)

## What it shows

- A price chart per watchlist car (1M, 3M, 6M, 1Y): an estimate line that ends at the tracked price, plus a dot for each real sale. Every chart is marked EST and shows its sale count, a THIN flag when fewer than 3 sales are plotted, and the date of the last sale.
- A scrolling, searchable ticker, a watchlist sidebar with change arrows and portfolio totals, and a detail modal with price levels, cost to own and listing links.
- A CONFIG editor that adds, edits and removes cars and exports `cars.config.js`.

## How the data works

- Bring a Trailer is the only source. Only sold auctions count, each stored once by listing ID in `frontend/price_history.json` and dated to the auction end. An unsold result never removes a stored sale.
- A car's price is the median of its sales from the last two years, applied only with at least 3 sales and when the median sits between 80% of its `low_price` and 125% of its `high_price`. Otherwise the price holds.
- `years` and the optional title words keep other model years, trims and parts listings out.
- The estimate line is generated the same way every run, so it is an illustration, not observed prices.
- Chinese cars have no US market. Their prices are set by hand in the editor.
- The price run stops before committing when a check fails or no Bring a Trailer page shows a sold result, so the prices stay as they were. An uploaded `cars.config.js` is published as soon as it is uploaded, whether or not its checks pass.

## Keeping it up to date

`HOW_TO_ADD_A_CAR.md` is the owner guide: editing cars in the browser, uploading the file, and what each entry in the "Cars that need a look" issue means. The price run (`.github/workflows/update-prices.yml`) runs every Sunday, on demand, and whenever `cars.config.js` or the scraper changes on main.

## Project structure

```
frontend/  index.html (dashboard and editor), cars.config.js (every car), config-writer.js (the only
           writer of cars.config.js), data.js (generated charts), price_history.json (stored sales)
scraper/   scrape_prices.py, generate_history.py, report.py, requirements.txt
tests/     test_sales.py, test_report.py, test_config_roundtrip.js, validate_config.js, fixtures/
```

## For developers

```
pip install -r scraper/requirements.txt
python scraper/scrape_prices.py        # Bring a Trailer -> scraper/scraped_prices.json
python scraper/generate_history.py     # store sales, patch prices, rebuild data.js (--dev: data.js only)
python scraper/report.py               # per-car table (the workflow adds --issue)

python tests/test_sales.py
python tests/test_report.py
node tests/test_config_roundtrip.js
node tests/validate_config.js
```

Stack: vanilla HTML, CSS and JavaScript with Chart.js; Python (httpx, BeautifulSoup) for the scraper; GitHub Actions for the price run; Vercel for hosting (Root Directory `frontend`).

## License

MIT. Use it, fork it, build on it.

*Built by Ghost Strategies · ghoststrategies.io*
