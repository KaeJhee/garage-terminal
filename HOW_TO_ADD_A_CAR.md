# How to Add a Car to Garage Terminal

Adding a new car to the watchlist takes about 5 minutes.
You only ever touch **one file**: `frontend/cars.config.js`.

---

## Step 1 — Open `cars.config.js`

```
garage-terminal/
└── frontend/
    └── cars.config.js   ← edit this file only
```

---

## Step 2 — Copy a car block

Find the section at the bottom of the `WATCHLIST` array:

```js
// ─── ADD NEW CARS BELOW THIS LINE ──────────────────────
```

Copy any existing car object (e.g., the NSX example that's commented out)
and paste it right before the closing `];`.

---

## Step 3 — Fill in the fields

Here's a complete example — a Mitsubishi Evo IX:

```js
{
  id:         'evo-ix',          // unique slug, lowercase, hyphens only
  symbol:     'EVOIX',           // 6-8 chars, uppercase, shown in sidebar/ticker
  make:       'Mitsubishi',      // manufacturer
  model:      'Lancer Evo IX',   // full display name on the chart
  years:      '2005–2007',       // production years
  category:   'JDM',             // JDM | Modern | Exotic | Muscle | European
  engine:     '4G63T Turbo I4',  // engine description
  power:      '286 hp (factory)',
  avg_price:  42000,             // current average market price (USD)
  low_price:  22000,             // realistic entry-level price
  high_price: 75000,             // top of the typical range
  prev_avg:   39500,             // previous period avg (used for ▲/▼ delta)
                                 // tip: set ~3-8% below avg_price for upward trend
  color:      CHART_COLORS.orange,  // pick any unused color from the palette below
  note:       'MR edition commands $15K+ premium. CT9A chassis.',
  bat_url:    'https://bringatrailer.com/search/?s=evo+ix',
  market_url: 'https://www.classic.com/m/mitsubishi/lancer-evolution/',

  // ─── COST-TO-OWN — First-year ownership cost estimates ────────────────
  // JDM import example (25-yr US exemption qualifies for 2.5% duty)
  cost_to_own: {
    insurance_annual:       700,          // Annual specialty insurance estimate
    insurance_note:         'Hagerty/Grundy specialty classic car policy',
    import_duty_pct:        0.025,        // 2.5% US import duty (25-yr exemption)
    import_duty_est:        1050,         // avg_price x import_duty_pct
    shipping_est:           4500,         // Japan → US West Coast
    maintenance_annual:     1200,         // Annual maintenance estimate
    maintenance_note:       '4G63T service, intercooler, clutch wear items',
    total_first_year_extra: 7450,         // duty + shipping + insurance + maintenance
  },
},
```

> **For US-spec cars** (R35 GT-R, Huracan STO, etc.), set `import_duty_pct`,
> `import_duty_est`, and `shipping_est` all to `0`. The panel will display
> "N/A — US Spec" automatically for those rows.

---

## Step 4 — Pick a color

Open `CHART_COLORS` at the top of the file and pick any color marked `// --- Available ---`:

| Name     | Hex       | Preview |
|----------|-----------|---------|
| orange   | `#f5804b` | warm orange |
| pink     | `#f06ea0` | hot pink |
| cyan     | `#22d3ee` | bright cyan |
| lime     | `#84cc16` | electric lime |
| rose     | `#fb7185` | rose red |
| sky      | `#38bdf8` | sky blue |
| gold     | `#fbbf24` | gold yellow |
| indigo   | `#818cf8` | soft indigo |
| coral    | `#ff6b6b` | coral red |
| mint     | `#6ee7b7` | mint green |

Mark the color as `(in use)` in the comment after you pick it, so you don't accidentally reuse it.

---

## Step 5 — Find the right prices

**avg_price** — the most important field. Sources (in order of preference):

| Car type | Best source |
|----------|-------------|
| JDM classics | [classic.com](https://classic.com) — search the make/model |
| JDM classics | [Bring a Trailer](https://bringatrailer.com) — sort completed auctions |
| Modern performance | [KBB Used](https://kbb.com) — select "Fair Market Range" |
| Modern performance | [Cars.com](https://cars.com) — check "Avg. Listed Price" |
| Exotic / European | [Edmunds Used](https://edmunds.com) |
| Any car | [CarGurus Price Trends](https://cargurus.com) |

**prev_avg** — if you don't have a previous data point, estimate it:
- Appreciating market: set 3–8% below `avg_price`
- Depreciating market: set 1–3% above `avg_price`

---

## Step 6 — Also add to the scraper (for auto-updates)

If you want the weekly GitHub Actions job to keep prices fresh for your
new car, add an entry to `scraper/scrape_prices.py` in the `CARS` list:

```python
{
    "id": "evo-ix",
    "label": "Mitsubishi Lancer Evo IX",
    "sources": [
        {
            "type": "classic_com",
            "url": "https://www.classic.com/m/mitsubishi/lancer-evolution/",
        },
        {
            "type": "bat_search",
            "url": "https://bringatrailer.com/search/?s=evo+ix",
            "search_term": "evo ix",
        },
    ],
    "fallback_avg": 42000,   # used if scraping fails
},
```

---

## Step 7 — Save, refresh, push

1. Save `cars.config.js`
2. Open the dashboard in your browser → hard-refresh (`Cmd+Shift+R` on Mac)
3. The new car automatically appears in the sidebar and ticker
4. Push to GitHub:

```bash
cd garage-terminal
git add frontend/cars.config.js scraper/scrape_prices.py
git commit -m "feat: add Evo IX to watchlist"
git push
```

Netlify/Vercel will automatically redeploy within ~30 seconds.

---

## Field Reference (quick cheat sheet)

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Lowercase slug, hyphens. Must be **unique**. Used as dictionary key everywhere. |
| `symbol` | string | 6–8 chars, uppercase. Shown in sidebar + ticker. Must be **unique**. |
| `make` | string | Manufacturer name |
| `model` | string | Full display name on the chart |
| `years` | string | Production years, e.g. `"1995–1998"` |
| `category` | string | `"JDM"` \| `"Modern"` \| `"Exotic"` \| `"Muscle"` \| `"European"` |
| `engine` | string | Engine description (shown in specs strip) |
| `power` | string | Horsepower string (shown in specs strip) |
| `avg_price` | integer | Current average market price in USD |
| `low_price` | integer | Realistic entry-level price (not a basket case) |
| `high_price` | integer | Top of typical range (not a record outlier) |
| `prev_avg` | integer | Previous period average (sets the ▲/▼ delta) |
| `color` | string | Hex color or `CHART_COLORS.<name>`. Must be visually distinct. |
| `note` | string | One-sentence market insight (under 120 chars) |
| `bat_url` | string | Link to listings (BaT, Cars.com, Edmunds, etc.) |
| `market_url` | string | Link to market data (classic.com, KBB, CarGurus, etc.) |
| `cost_to_own` | object | First-year ownership cost breakdown (see below) |

### cost_to_own sub-fields

| Sub-field | Type | Notes |
|-----------|------|-------|
| `insurance_annual` | integer | Annual specialty insurance estimate (USD) |
| `insurance_note` | string | Short note on insurance type/provider |
| `import_duty_pct` | decimal | 0.025 for JDM imports (25-yr exemption). 0 for US-spec. |
| `import_duty_est` | integer | Duty amount = avg_price × import_duty_pct. 0 for US-spec. |
| `shipping_est` | integer | Shipping Japan → US West Coast (~$4,500). 0 for US-spec. |
| `maintenance_annual` | integer | Annual maintenance estimate (USD) |
| `maintenance_note` | string | Short note on what maintenance covers |
| `total_first_year_extra` | integer | **Sum of all above** = duty + shipping + insurance + maintenance |

> The `total_first_year_extra` field is what the dashboard uses for the
> True Acquisition Cost display. You must calculate it manually — the
> dashboard does not auto-sum the sub-fields.

---

## Maximum watchlist size

The dashboard comfortably handles up to **12 cars** in the sidebar before it
gets crowded on mobile. Beyond that, consider splitting into multiple dashboards.

---

## Removing a car

Delete its object from the `WATCHLIST` array in `cars.config.js`.
Also remove it from `scraper/scrape_prices.py` if you added it there.

---

*Questions? All dashboard logic lives in `frontend/index.html`.
The config file is loaded at line ~622 as `<script src="cars.config.js">`.*
