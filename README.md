# 🏎 Garage Terminal

> A Bloomberg Terminal-style dashboard for tracking JDM and exotic car market prices — built by Ghost Strategies.

![Terminal Preview](https://img.shields.io/badge/status-live-brightgreen) ![Cars Tracked](https://img.shields.io/badge/cars%20tracked-5-orange) ![Tickers](https://img.shields.io/badge/ticker%20symbols-37-blue)

---

## What It Does

- **Live-style price chart** per car with 1M / 3M / 6M / 1Y views (Chart.js)
- **Scrolling ticker tape** with 37 JDM + exotic + supercar symbols
- **Watchlist sidebar** with delta indicators (▲/▼) and portfolio totals
- **Right panel** with price levels, OHLC stats, full-fleet comparison, and direct listing links
- **Mobile responsive** — works on iPhone as a full-screen web app
- **Dark Bloomberg Terminal aesthetic** — amber on black, monospace everything

---

## Cars Tracked (Watchlist)

| Symbol | Car | Avg Market Price |
|--------|-----|-----------------|
| R33GTR | Nissan Skyline R33 GT-R (1995–98) | $77,396 |
| R32GTR | Nissan Skyline R32 GT-R (1989–94) | $53,401 |
| SUPRAA80 | Toyota Supra MK4 A80 (1993–02) | $50,000 |
| R35GTR | Nissan GT-R R35 2020 | $106,000 |
| HURASTO | Lamborghini Huracán STO 2022 | $427,632 |

---

## Ticker Universe (30+ Symbols)

NSX-NA1 · FD-RX7 · EVO-VI · STI-RA · S15-SPEC · NSX-R · AE86 · R34-GTR · 300ZX-Z32 · FC-RX7 · MR2-SW20 · S13-240SX · CELICA-GT4 · LANCER-EVO4 · 458-SPEC · GT3RS-991 · AVENTADOR · 720S · CAYMAN-GT4 · F8-TRIB · VANTAGE-GT3 · MCLAREN-600LT · AMG-GTR · M4-CSL · GT500-21 · ZL1-1LE · VIPER-ACR · CORVETTE-Z06 · and more

---

## Project Structure

```
garage-terminal/
├── frontend/
│   ├── index.html        ← Full dashboard (self-contained, no server required)
│   ├── data.js           ← 365-day baked price history for all 5 watchlist cars
│   └── cars.config.js    ← Watchlist definitions, prices, cost-to-own data
├── backend/
│   └── main.py           ← FastAPI server (optional — for live/refreshed data)
├── scraper/
│   ├── scrape_prices.py  ← Fetches live prices from classic.com and BaT
│   ├── generate_history.py ← Regenerates data.js from scraped or fallback prices
│   └── requirements.txt
├── .github/
│   └── workflows/
│       └── update-prices.yml ← GitHub Actions: auto-scrape every Sunday
├── .gitignore
└── README.md
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vanilla HTML · CSS Grid · JavaScript (ES2020) |
| Charts | [Chart.js 4.x](https://www.chartjs.org/) |
| Fonts | DM Mono · DM Sans (Google Fonts) |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Hosting | Netlify / Vercel (static) |

---


## Data Sources

Prices sourced from April 2026 market data:

- [classic.com](https://www.classic.com) — JDM auction averages (R32, R33, Supra)
- [Kelley Blue Book](https://www.kbb.com) — R35 GT-R pricing
- [Edmunds](https://www.edmunds.com) — Huracán STO listings average
- [Cars.com](https://www.cars.com) — Nationwide dealer inventory
- [Bring a Trailer](https://bringatrailer.com) — Auction results reference

> Price history is simulated with a mean-reverting random walk seeded from real market averages. For live scraped data, connect a Python fetcher to the backend.

---

## License

MIT — use it, fork it, build on it.

---

*Built with Ghost Strategies*
