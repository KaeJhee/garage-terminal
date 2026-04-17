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

## Ticker Universe (37 Symbols)

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

---

## Pushing to GitHub (First Time)

### Step 1 — Install Git

If you haven't already, download and install Git from [git-scm.com](https://git-scm.com/download/win).  
During install, leave all defaults as-is and click Next through everything.

Verify it worked — open a new PowerShell window and run:
```powershell
git --version
```
You should see something like `git version 2.44.0`.

---

### Step 2 — Create a GitHub Repository

1. Go to [github.com](https://github.com) and sign in (or create a free account)
2. Click the **+** icon in the top-right → **New repository**
3. Name it `garage-terminal`
4. Leave it **Private** (recommended) or Public — your choice
5. **Do NOT check** "Add a README" or any other options — the repo must be empty
6. Click **Create repository**
7. GitHub will show you a page with setup instructions — leave it open, you'll need the URL in Step 4

---

### Step 3 — Open PowerShell in Your Project Folder

Navigate to your `garage-terminal` folder in PowerShell:

```powershell
cd "C:\Users\krisg\OneDrive\Documents\Ghost Strategies\Tools\Garage Terminal\garage-terminal"
```

> Tip: You can also open File Explorer, navigate to the `garage-terminal` folder, then type `powershell` in the address bar and press Enter.

---

### Step 4 — Initialize Git and Push

Run these commands **one at a time** in order:

```powershell
# 1. Initialize a git repository in this folder
git init

# 2. Tell git who you are (use your GitHub email and name)
git config user.email "you@example.com"
git config user.name "Your Name"

# 3. Stage all files for the first commit
git add .

# 4. Create the first commit
git commit -m "Initial commit — Garage Terminal dashboard"

# 5. Rename the default branch to main
git branch -M main

# 6. Connect your local folder to the GitHub repo you created in Step 2
#    Replace YOUR_USERNAME with your actual GitHub username
git remote add origin https://github.com/YOUR_USERNAME/garage-terminal.git

# 7. Push everything up to GitHub
git push -u origin main
```

Git will prompt you to sign in to GitHub in your browser — follow the popup and authorize it.

---

### Step 5 — Verify It Worked

Go back to your GitHub repository page and refresh it. You should see all your files listed there — `frontend/`, `backend/`, `scraper/`, etc.

---

## Pushing Future Updates

Any time you change a file and want to save it to GitHub, run these three commands from the `garage-terminal` folder:

```powershell
git add .
git commit -m "Brief description of what you changed"
git push
```

That's it. You don't need to repeat the setup steps — just those three lines every time.

---

## Running Locally (Two Terminals)

**Terminal 1 — Backend server:**
```powershell
py -m uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Data watcher (keeps data.js current):**
```powershell
py scraper/generate_history.py --dev --watch --interval 60
```

Then open `http://localhost:5000` in your browser.  
If data looks stale after running the watcher, hard-refresh with `Ctrl + Shift + R`.

---

## Quickstart — Static Frontend (No Backend Needed)

The dashboard is fully self-contained. Just open `frontend/index.html` in any browser — no server, no install, no dependencies.

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/garage-terminal.git
cd garage-terminal

# Open in browser (macOS)
open frontend/index.html

# Or just double-click frontend/index.html in File Explorer (Windows)
```

---

## Running the Full Backend (Optional)

The Python backend generates fresh price history and powers the `/api/*` endpoints.

### Requirements

- Python 3.10+
- pip

### Install & Run

```powershell
# Install dependencies
py -m pip install fastapi uvicorn httpx beautifulsoup4

# Start the server
py -m uvicorn backend.main:app --reload --port 8000

# Open in browser
http://localhost:5000
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server status |
| GET | `/api/watchlist` | All 5 cars with price + delta |
| GET | `/api/car/{id}` | Single car detail |
| GET | `/api/car/{id}/history?period=1Y` | Price history (1M/3M/6M/1Y) |
| GET | `/api/ticker` | Full 37-car ticker feed |
| GET | `/api/market-summary` | Portfolio totals and averages |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vanilla HTML · CSS Grid · JavaScript (ES2020) |
| Charts | [Chart.js 4.x](https://www.chartjs.org/) |
| Fonts | DM Mono · DM Sans (Google Fonts) |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Hosting | Netlify / Vercel (static) |

---

## Deploying the Frontend

### Netlify (Recommended — Free)

1. Go to [netlify.com](https://netlify.com) → sign up
2. Click **Add new site → Import an existing project**
3. Connect your GitHub account → select `garage-terminal`
4. Set **Publish directory** to `frontend`
5. Click **Deploy** — live in ~30 seconds

### Vercel (Also Free)

1. Go to [vercel.com](https://vercel.com) → sign up with GitHub
2. Click **New Project → Import** → select `garage-terminal`
3. Set **Root Directory** to `frontend`
4. Click **Deploy**

---

## Auto Price Updates (GitHub Actions)

Once pushed to GitHub, a workflow runs every Sunday at midnight that:
1. Scrapes current prices from classic.com and BaT
2. Regenerates `data.js` with fresh history
3. Commits the updated file to the repo
4. Triggers a Netlify redeploy automatically via webhook

No manual intervention needed after initial setup.

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

## Roadmap

- [ ] Live price scraper (BaT + classic.com + Bring a Trailer)
- [ ] Price alert system (email/SMS when car drops below target)
- [ ] Multi-car chart overlay (compare all 5 on one chart)
- [ ] Add more watchlist cars
- [ ] Export to CSV / PDF

---

## License

MIT — use it, fork it, build on it.

---

*Built with Ghost Strategies · San Antonio, TX*
