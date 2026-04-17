"""
Dream Garage — Bloomberg Terminal Backend
FastAPI server providing car market price data, simulated price history,
and a real-time ticker feed for the frontend dashboard.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import random
import math
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import os

app = FastAPI(title="Dream Garage API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# DATA — Watchlist cars (target acquisitions)
# ============================================================
WATCHLIST = [
    {
        "id": "r33-gtr",
        "symbol": "R33GTR",
        "make": "Nissan",
        "model": "Skyline R33 GT-R",
        "years": "1995–1998",
        "category": "JDM",
        "badge": "dream",
        "engine": "RB26DETT Twin-Turbo I6",
        "power": "276 hp (underrated)",
        "avg_price": 77396,
        "low_price": 32000,
        "high_price": 120000,
        "prev_avg": 74200,
        "color": "#e8a020",
        "note": "V-Spec variants command premium. Watch for V-Spec II Nür.",
        "bat_url": "https://bringatrailer.com/search/?s=r33+gt-r",
        "market_url": "https://www.classic.com/m/nissan/skyline/r33/gt-r/",
    },
    {
        "id": "r32-gtr",
        "symbol": "R32GTR",
        "make": "Nissan",
        "model": "Skyline R32 GT-R",
        "years": "1989–1994",
        "category": "JDM",
        "badge": "jdm",
        "engine": "RB26DETT Twin-Turbo I6",
        "power": "276 hp (factory)",
        "avg_price": 53401,
        "low_price": 7777,
        "high_price": 80000,
        "prev_avg": 51800,
        "color": "#3cb8c0",
        "note": "'Godzilla.' Group A homologation specials fetch $200K+.",
        "bat_url": "https://bringatrailer.com/search/?s=r32+gt-r",
        "market_url": "https://www.classic.com/m/nissan/skyline/r32/gt-r/",
    },
    {
        "id": "supra-a80",
        "symbol": "SUPRAA80",
        "make": "Toyota",
        "model": "Supra MK4 A80",
        "years": "1993–2002",
        "category": "JDM",
        "badge": "jdm",
        "engine": "2JZ-GTE Twin-Turbo I6",
        "power": "320 hp (factory)",
        "avg_price": 50000,
        "low_price": 30000,
        "high_price": 80000,
        "prev_avg": 48500,
        "color": "#3ab86e",
        "note": "2JZ legendary for 1000+ hp builds. Turbo coupes most sought.",
        "bat_url": "https://bringatrailer.com/search/?s=toyota+supra+mk4",
        "market_url": "https://www.cargurus.com/research/price-trends/Toyota-Supra-d309",
    },
    {
        "id": "r35-gtr",
        "symbol": "R35GTR",
        "make": "Nissan",
        "model": "GT-R R35 (2020)",
        "years": "2020",
        "category": "Modern",
        "badge": "modern",
        "engine": "VR38DETT Twin-Turbo V6",
        "power": "565 hp",
        "avg_price": 106000,
        "low_price": 88400,
        "high_price": 150000,
        "prev_avg": 108200,
        "color": "#4b8ef5",
        "note": "KBB Fair Purchase $106K (Premium). NISMO at $212K original MSRP.",
        "bat_url": "https://www.cars.com/shopping/nissan-gt_r-2020/",
        "market_url": "https://www.kbb.com/nissan/gt-r/2020/",
    },
    {
        "id": "huracan-sto",
        "symbol": "HURASTО",
        "make": "Lamborghini",
        "model": "Huracán STO (2022)",
        "years": "2022",
        "category": "Exotic",
        "badge": "exotic",
        "engine": "N/A V10",
        "power": "631 hp",
        "avg_price": 427632,
        "low_price": 384995,
        "high_price": 580000,
        "prev_avg": 419500,
        "color": "#a06ef0",
        "note": "Super Trofeo Omologata — road-legal race spec. 37 US listings.",
        "bat_url": "https://www.edmunds.com/used-lamborghini-huracan-sto/",
        "market_url": "https://www.classic.com/m/lamborghini/huracan/sto/",
    },
]

# ============================================================
# TICKER — Extended JDM + Supercar universe
# ============================================================
TICKER_CARS = [
    # JDM Icons
    {"symbol": "NSX-NA1", "name": "Honda NSX NA1", "price": 95000, "change": 2.1},
    {"symbol": "FD-RX7", "name": "Mazda RX-7 FD3S", "price": 42000, "change": -0.8},
    {"symbol": "EVO-VI", "name": "Mitsubishi Evo VI TME", "price": 68000, "change": 3.4},
    {"symbol": "STI-RA", "name": "Subaru STI RA", "price": 38000, "change": 1.2},
    {"symbol": "S15-SPEC", "name": "Nissan Silvia S15", "price": 35000, "change": 4.7},
    {"symbol": "SUPRA-TT", "name": "Toyota Supra 3.0T", "price": 52000, "change": -1.5},
    {"symbol": "NSX-R", "name": "Honda NSX-R", "price": 185000, "change": 5.2},
    {"symbol": "AE86", "name": "Toyota AE86 Trueno", "price": 28000, "change": 6.1},
    {"symbol": "R34-GTR", "name": "Nissan R34 GT-R", "price": 168000, "change": 8.3},
    {"symbol": "GTO-3S", "name": "Mitsubishi GTO 3S", "price": 22000, "change": -2.1},
    {"symbol": "300ZX-Z32", "name": "Nissan 300ZX Z32 TT", "price": 45000, "change": 3.9},
    {"symbol": "FC-RX7", "name": "Mazda RX-7 FC3S", "price": 18000, "change": 2.8},
    {"symbol": "MR2-SW20", "name": "Toyota MR2 SW20", "price": 24000, "change": -0.5},
    {"symbol": "S13-240SX", "name": "Nissan 240SX S13", "price": 19000, "change": 1.6},
    {"symbol": "CELICA-GT4", "name": "Toyota Celica GT-Four", "price": 31000, "change": 4.2},
    {"symbol": "BEAT", "name": "Honda Beat PP1", "price": 12000, "change": 7.8},
    {"symbol": "CR-X", "name": "Honda CR-X Del Sol SiR", "price": 14000, "change": 3.1},
    {"symbol": "LANCER-EVO4", "name": "Mitsubishi Evo IV", "price": 55000, "change": 2.9},
    # European / Exotic
    {"symbol": "458-SPEC", "name": "Ferrari 458 Speciale", "price": 390000, "change": 1.8},
    {"symbol": "GT3RS-991", "name": "Porsche 991 GT3 RS", "price": 210000, "change": -0.9},
    {"symbol": "AVENTADOR", "name": "Lamborghini Aventador S", "price": 420000, "change": 2.4},
    {"symbol": "720S", "name": "McLaren 720S", "price": 265000, "change": -3.1},
    {"symbol": "CAYMAN-GT4", "name": "Porsche Cayman GT4", "price": 118000, "change": 1.4},
    {"symbol": "F8-TRIB", "name": "Ferrari F8 Tributo", "price": 340000, "change": 0.7},
    {"symbol": "VANTAGE-GT3", "name": "Aston Vantage GT3", "price": 195000, "change": 3.8},
    {"symbol": "MCLAREN-600LT", "name": "McLaren 600LT", "price": 225000, "change": -1.2},
    {"symbol": "AMG-GTR", "name": "Mercedes-AMG GT R", "price": 165000, "change": 0.5},
    {"symbol": "M4-CSL", "name": "BMW M4 CSL", "price": 145000, "change": 2.1},
    # American Muscle
    {"symbol": "GT500-21", "name": "Shelby GT500 2021", "price": 92000, "change": 4.5},
    {"symbol": "ZL1-1LE", "name": "Camaro ZL1 1LE", "price": 75000, "change": 1.9},
    {"symbol": "VIPER-ACR", "name": "Dodge Viper ACR", "price": 188000, "change": 6.2},
    {"symbol": "CORVETTE-Z06", "name": "Corvette Z06 C8", "price": 118000, "change": -0.3},
]


def generate_price_history(base_price: float, days: int = 365, volatility: float = 0.015) -> List[Dict]:
    """Generate realistic price history — price walks around base with gentle trend and noise."""
    history = []
    # Start 8-15% below current avg, trend up to current
    start_mult = random.uniform(0.87, 0.93)
    price = base_price * start_mult

    start_date = datetime.now() - timedelta(days=days)

    for i in range(days):
        # Very gentle daily trend toward base_price
        progress = i / days  # 0 → 1
        trend_target = base_price * (start_mult + (1.0 - start_mult) * progress)
        mean_revert = (trend_target - price) * 0.008  # pull toward trend target

        # Daily noise
        noise = random.gauss(0, volatility) * price

        # Occasional spikes (auction events)
        if random.random() < 0.015:
            noise += price * random.uniform(0.02, 0.06)
        elif random.random() < 0.008:
            noise -= price * random.uniform(0.02, 0.04)

        price = price + mean_revert + noise
        price = max(price, base_price * 0.55)  # hard floor
        price = min(price, base_price * 1.40)  # hard ceiling

        date_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        history.append({
            "date": date_str,
            "price": round(price, 0),
            "volume": random.randint(1, 15),
        })

    return history


# Pre-generate price histories at startup
_price_histories: Dict[str, List[Dict]] = {}

@app.on_event("startup")
async def startup_event():
    random.seed(42)
    for car in WATCHLIST:
        volatility = 0.022 if car["category"] == "JDM" else 0.012
        _price_histories[car["id"]] = generate_price_history(
            car["avg_price"],
            days=365,
            volatility=volatility
        )


# ============================================================
# API ROUTES
# ============================================================

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/watchlist")
def get_watchlist():
    """Return all watchlist cars with current market data and deltas."""
    result = []
    for car in WATCHLIST:
        delta = car["avg_price"] - car["prev_avg"]
        delta_pct = round((delta / car["prev_avg"]) * 100, 2)
        result.append({
            **car,
            "delta": round(delta, 0),
            "delta_pct": delta_pct,
            "delta_dir": "up" if delta > 0 else "down" if delta < 0 else "flat",
        })
    return result


@app.get("/api/car/{car_id}")
def get_car(car_id: str):
    """Return detailed data for a single car."""
    car = next((c for c in WATCHLIST if c["id"] == car_id), None)
    if not car:
        return {"error": "Car not found"}
    delta = car["avg_price"] - car["prev_avg"]
    delta_pct = round((delta / car["prev_avg"]) * 100, 2)
    return {**car, "delta": round(delta, 0), "delta_pct": delta_pct}


@app.get("/api/car/{car_id}/history")
def get_price_history(car_id: str, period: str = "1Y"):
    """Return price history for a car. Periods: 1M, 3M, 6M, 1Y."""
    history = _price_histories.get(car_id)
    if not history:
        return {"error": "Car not found"}

    period_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    days = period_map.get(period, 365)
    sliced = history[-days:]

    # Calculate stats from this slice
    prices = [h["price"] for h in sliced]
    return {
        "car_id": car_id,
        "period": period,
        "data": sliced,
        "stats": {
            "open": prices[0],
            "close": prices[-1],
            "high": max(prices),
            "low": min(prices),
            "change": round(prices[-1] - prices[0], 0),
            "change_pct": round(((prices[-1] - prices[0]) / prices[0]) * 100, 2),
            "avg": round(sum(prices) / len(prices), 0),
        }
    }


@app.get("/api/ticker")
def get_ticker():
    """Return live ticker data for the scrolling tape."""
    random.seed(int(time.time() / 60))  # changes every minute
    result = []
    for car in TICKER_CARS:
        # Small random walk from last known price
        jitter = random.uniform(-0.015, 0.015)
        new_price = round(car["price"] * (1 + jitter), 0)
        new_change = round(car["change"] + random.uniform(-0.3, 0.3), 2)
        result.append({
            "symbol": car["symbol"],
            "name": car["name"],
            "price": new_price,
            "change": new_change,
            "direction": "up" if new_change > 0 else "down",
        })

    # Also include watchlist cars in ticker
    for car in WATCHLIST:
        delta_pct = round(((car["avg_price"] - car["prev_avg"]) / car["prev_avg"]) * 100, 2)
        result.insert(random.randint(0, 5), {
            "symbol": car["symbol"],
            "name": car["model"],
            "price": car["avg_price"],
            "change": delta_pct,
            "direction": "up" if delta_pct > 0 else "down",
            "watchlist": True,
        })

    return result


@app.get("/api/market-summary")
def market_summary():
    """Market overview stats."""
    total_portfolio = sum(c["avg_price"] for c in WATCHLIST)
    gainers = [c for c in WATCHLIST if c["avg_price"] > c["prev_avg"]]
    losers = [c for c in WATCHLIST if c["avg_price"] < c["prev_avg"]]

    jdm_avg = sum(c["avg_price"] for c in WATCHLIST if c["category"] == "JDM") / max(1, sum(1 for c in WATCHLIST if c["category"] == "JDM"))
    exotic_avg = sum(c["avg_price"] for c in WATCHLIST if c["category"] == "Exotic") / max(1, sum(1 for c in WATCHLIST if c["category"] == "Exotic"))

    return {
        "total_portfolio": total_portfolio,
        "cars_tracked": len(WATCHLIST),
        "gainers": len(gainers),
        "losers": len(losers),
        "jdm_avg": round(jdm_avg, 0),
        "exotic_avg": round(exotic_avg, 0),
        "market_status": "OPEN",
        "last_updated": datetime.now().isoformat(),
        "ticker_count": len(TICKER_CARS),
    }


# ============================================================
# Serve frontend static files (after API routes)
# ============================================================
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=False)
