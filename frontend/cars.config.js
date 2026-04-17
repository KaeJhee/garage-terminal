/**
 * ============================================================
 * GARAGE TERMINAL — CAR CONFIGURATION
 * ============================================================
 *
 * HOW TO ADD A NEW CAR TO THE WATCHLIST
 * ---------------------------------------
 * 1. Copy one of the existing car objects below
 * 2. Paste it at the end of the WATCHLIST array
 * 3. Fill in all fields (see FIELD REFERENCE below)
 * 4. Pick a unique color from CHART_COLORS
 * 5. Save the file and refresh the dashboard
 *
 * The dashboard automatically picks up all cars in WATCHLIST —
 * no other files need to be changed.
 *
 * ============================================================
 * FIELD REFERENCE
 * ============================================================
 *
 * id          → Unique slug, lowercase, hyphens only. Used as key everywhere.
 *               Examples: "nsx-na1", "evo-ix", "gt3rs-992"
 *
 * symbol      → Ticker-style label shown in the sidebar and ticker tape.
 *               6–8 chars, uppercase, no spaces.
 *               Examples: "NSXNA1", "EVOIX", "GT3RS992"
 *
 * make        → Manufacturer name. Examples: "Honda", "Porsche"
 *
 * model       → Full display name shown as the chart title.
 *               Examples: "NSX NA1", "Porsche 911 GT3 RS (992)"
 *
 * years       → Production years shown in the header.
 *               Examples: "1990–2005", "2023", "2019–2021"
 *
 * category    → One of: "JDM" | "Modern" | "Exotic" | "Muscle" | "European"
 *               Controls which KPI bucket the car falls into.
 *
 * engine      → Engine description for the specs strip.
 *               Examples: "C32B VTEC V6", "4.0L Flat-6 NA"
 *
 * power       → Power output string shown in specs.
 *               Examples: "290 hp", "500 hp (factory)"
 *
 * avg_price   → Current average market price in USD (integer).
 *               Source this from classic.com, BaT recent results, or KBB.
 *
 * low_price   → Realistic entry-level price (not a basket case).
 *               This sets the left end of the price range gauge.
 *
 * high_price  → Top of the typical price range (not a record outlier).
 *               This sets the right end of the price range gauge.
 *
 * prev_avg    → Previous period's average price (used to calculate ▲/▼ delta).
 *               If you don't have this, set it 3–8% below avg_price for an up trend,
 *               or 1–3% above for a down trend.
 *
 * color       → Hex color for this car's chart line and comparison dot.
 *               Pick from CHART_COLORS below, or any distinct hex.
 *               Avoid colors already used by other cars.
 *
 * note        → One-sentence market insight shown in the specs strip.
 *               Keep under 120 characters.
 *
 * bat_url     → Link to active listings (Bring a Trailer, Cars.com, Edmunds, etc.)
 *               This powers the "Listings ↗" button.
 *
 * market_url  → Link to market data page (classic.com, KBB, CarGurus, etc.)
 *               This powers the "Market ↗" button.
 *
 * cost_to_own → Object with estimated first-year ownership costs beyond purchase price.
 *               Used by the Cost-to-Own panel on each car card.
 *
 *   insurance_annual    → Annual specialty/classic insurance estimate (USD integer).
 *                         JDM classics → Hagerty/Grundy rates. US-spec → standard market.
 *   insurance_note      → Short note on insurance type or provider basis.
 *
 *   import_duty_pct     → Import duty rate as decimal (e.g. 0.025 = 2.5%).
 *                         US-spec or domestic cars: set to 0.
 *   import_duty_est     → Estimated duty dollar amount (integer).
 *                         = avg_price × import_duty_pct. Set to 0 for US-spec.
 *   shipping_est        → Estimated shipping cost from Japan to US West Coast (integer).
 *                         Typically $3,050–$5,500 flat. Set to 0 for US-spec.
 *
 *   maintenance_annual  → Estimated annual maintenance cost (USD integer).
 *                         Includes oil changes, service intervals, wear items.
 *   maintenance_note    → Short note on what's covered or why the estimate is set.
 *
 *   total_first_year_extra → Sum of all above one-time + first-year recurring costs.
 *                            = import_duty_est + shipping_est + insurance_annual + maintenance_annual
 *
 * ============================================================
 * CHART COLORS — pick one per car, keep them visually distinct
 * ============================================================
 */
var CHART_COLORS = {
  amber:   '#e8a020',   // ← R33 GTR (in use)
  teal:    '#3cb8c0',   // ← R32 GTR (in use)
  green:   '#3ab86e',   // ← Supra A80 (in use)
  blue:    '#4b8ef5',   // ← R35 GTR (in use)
  purple:  '#a06ef0',   // ← Huracán STO (in use)
  // --- Available ---
  orange:  '#f5804b',
  pink:    '#f06ea0',
  cyan:    '#22d3ee',
  lime:    '#84cc16',
  rose:    '#fb7185',
  sky:     '#38bdf8',
  gold:    '#fbbf24',
  indigo:  '#818cf8',
  coral:   '#ff6b6b',
  mint:    '#6ee7b7',
};

/**
 * ============================================================
 * WATCHLIST — Cars shown in the sidebar and on the chart
 * ============================================================
 *
 * Add or remove cars here. The dashboard auto-adjusts.
 * Maximum recommended: 12 cars (sidebar gets crowded above that).
 */
var WATCHLIST = [

  // ─── DREAM CAR ─────────────────────────────────────────
  {
    id:         'r33-gtr',
    symbol:     'R33GTR',
    make:       'Nissan',
    model:      'Skyline R33 GT-R',
    years:      '1995–1998',
    category:   'JDM',
    engine:     'RB26DETT Twin-Turbo I6',
    power:      '276 hp (underrated)',
    avg_price:  77396,
    low_price:  32000,
    high_price: 120000,
    prev_avg:   74200,
    color:      CHART_COLORS.amber,
    note:       'V-Spec variants command premium. Watch for V-Spec II Nür.',
    bat_url:    'https://bringatrailer.com/search/?s=r33+gt-r',
    market_url: 'https://www.classic.com/m/nissan/skyline/r33/gt-r/',
    cost_to_own: {
      insurance_annual:       750,
      insurance_note:         'Hagerty/Grundy specialty classic car policy',
      import_duty_pct:        0.025,
      import_duty_est:        1935,
      shipping_est:           4500,
      maintenance_annual:     1200,
      maintenance_note:       'RB26 oil, boost system, intercooler service',
      total_first_year_extra: 8385,
    },
  },

  // ─── JDM LEGENDS ───────────────────────────────────────
  {
    id:         'r32-gtr',
    symbol:     'R32GTR',
    make:       'Nissan',
    model:      'Skyline R32 GT-R',
    years:      '1989–1994',
    category:   'JDM',
    engine:     'RB26DETT Twin-Turbo I6',
    power:      '276 hp (factory)',
    avg_price:  53401,
    low_price:  7777,
    high_price: 80000,
    prev_avg:   51800,
    color:      CHART_COLORS.teal,
    note:       "'Godzilla.' Group A homologation specials fetch $200K+.",
    bat_url:    'https://bringatrailer.com/search/?s=r32+gt-r',
    market_url: 'https://www.classic.com/m/nissan/skyline/r32/gt-r/',
    cost_to_own: {
      insurance_annual:       700,
      insurance_note:         'Hagerty specialty classic; older platform, limited value',
      import_duty_pct:        0.025,
      import_duty_est:        1335,
      shipping_est:           4500,
      maintenance_annual:     1500,
      maintenance_note:       'RB26 service + age-related rubber, seals, hoses',
      total_first_year_extra: 8035,
    },
  },

  {
    id:         'supra-a80',
    symbol:     'SUPRAA80',
    make:       'Toyota',
    model:      'Supra MK4 A80',
    years:      '1993–2002',
    category:   'JDM',
    engine:     '2JZ-GTE Twin-Turbo I6',
    power:      '320 hp (factory)',
    avg_price:  50000,
    low_price:  30000,
    high_price: 80000,
    prev_avg:   48500,
    color:      CHART_COLORS.green,
    note:       '2JZ legendary for 1000+ hp builds. Turbo coupes most sought.',
    bat_url:    'https://bringatrailer.com/search/?s=toyota+supra+mk4',
    market_url: 'https://www.cargurus.com/research/price-trends/Toyota-Supra-d309',
    cost_to_own: {
      insurance_annual:       800,
      insurance_note:         'Specialty classic policy; Hagerty/Grundy for A80',
      import_duty_pct:        0.025,
      import_duty_est:        1250,
      shipping_est:           4500,
      maintenance_annual:     900,
      maintenance_note:       '2JZ-GTE turbo service; RepairPal est. $561–$810/yr',
      total_first_year_extra: 7450,
    },
  },

  // ─── MODERN ────────────────────────────────────────────
  {
    id:         'r35-gtr',
    symbol:     'R35GTR',
    make:       'Nissan',
    model:      'GT-R R35 (2020)',
    years:      '2020',
    category:   'Modern',
    engine:     'VR38DETT Twin-Turbo V6',
    power:      '565 hp',
    avg_price:  106000,
    low_price:  88400,
    high_price: 150000,
    prev_avg:   108200,
    color:      CHART_COLORS.blue,
    note:       'KBB Fair Purchase $106K (Premium). NISMO at $212K original MSRP.',
    bat_url:    'https://www.cars.com/shopping/nissan-gt_r-2020/',
    market_url: 'https://www.kbb.com/nissan/gt-r/2020/',
    cost_to_own: {
      insurance_annual:       4200,
      insurance_note:         'TheZebra/CarEdge full coverage; supercar premium rate',
      import_duty_pct:        0,
      import_duty_est:        0,
      shipping_est:           0,
      maintenance_annual:     2500,
      maintenance_note:       'US-spec; Nissan dealer service + performance intervals',
      total_first_year_extra: 6700,
    },
  },

  // ─── EXOTIC ────────────────────────────────────────────
  {
    id:         'huracan-sto',
    symbol:     'HURASTO',
    make:       'Lamborghini',
    model:      'Huracán STO (2022)',
    years:      '2022',
    category:   'Exotic',
    engine:     'N/A V10',
    power:      '631 hp',
    avg_price:  427632,
    low_price:  384995,
    high_price: 580000,
    prev_avg:   419500,
    color:      CHART_COLORS.purple,
    note:       'Super Trofeo Omologata — road-legal race spec. 37 US listings.',
    bat_url:    'https://www.edmunds.com/used-lamborghini-huracan-sto/',
    market_url: 'https://www.classic.com/m/lamborghini/huracan/sto/',
    cost_to_own: {
      insurance_annual:       8500,
      insurance_note:         'STO track-spec premium; Way.com $2,626 base + STO uplift',
      import_duty_pct:        0,
      import_duty_est:        0,
      shipping_est:           0,
      maintenance_annual:     4500,
      maintenance_note:       'CarBuzz: $850–1,500/yr basic + $3,500–6,000 major/5yr',
      total_first_year_extra: 13000,
    },
  },

  // ─── ADD NEW CARS BELOW THIS LINE ──────────────────────
  //
  // Example — Honda NSX NA1:
  //
  // {
  //   id:         'nsx-na1',
  //   symbol:     'NSXNA1',
  //   make:       'Honda',
  //   model:      'NSX NA1',
  //   years:      '1990–2005',
  //   category:   'JDM',
  //   engine:     'C32B VTEC V6',
  //   power:      '270 hp',
  //   avg_price:  95000,
  //   low_price:  55000,
  //   high_price: 185000,
  //   prev_avg:   90000,
  //   color:      CHART_COLORS.orange,
  //   note:       'NSX-R variant (NA1) commands $150K+. US-spec vs JDM price gap narrowing.',
  //   bat_url:    'https://bringatrailer.com/search/?s=honda+nsx',
  //   market_url: 'https://www.classic.com/m/honda/nsx/',
  // },

];

/**
 * ============================================================
 * TICKER UNIVERSE — Cars in the scrolling ticker tape
 * ============================================================
 *
 * These are NOT in the watchlist — they're background market
 * data for the ticker. Add any car symbol here.
 * Format: { symbol, name, price, change (%), direction }
 *
 * Tip: When you add a car to WATCHLIST, it auto-appears in the
 * ticker too (injected by the dashboard JS). You don't need to
 * add it here separately unless you want it ONLY in the ticker.
 */
var TICKER_UNIVERSE = [
  { symbol: 'NSX-NA1',     name: 'Honda NSX NA1',              price: 95000,  change: 2.1  },
  { symbol: 'FD-RX7',      name: 'Mazda RX-7 FD3S',            price: 42000,  change: -0.8 },
  { symbol: 'EVO-VI',      name: 'Mitsubishi Evo VI TME',       price: 68000,  change: 3.4  },
  { symbol: 'STI-RA',      name: 'Subaru STI RA',               price: 38000,  change: 1.2  },
  { symbol: 'S15-SPEC',    name: 'Nissan Silvia S15',           price: 35000,  change: 4.7  },
  { symbol: 'NSX-R',       name: 'Honda NSX-R',                 price: 185000, change: 5.2  },
  { symbol: 'AE86',        name: 'Toyota AE86 Trueno',          price: 28000,  change: 6.1  },
  { symbol: 'R34-GTR',     name: 'Nissan R34 GT-R',             price: 168000, change: 8.3  },
  { symbol: 'GTO-3S',      name: 'Mitsubishi GTO 3S',           price: 22000,  change: -2.1 },
  { symbol: '300ZX-Z32',   name: 'Nissan 300ZX Z32 TT',         price: 45000,  change: 3.9  },
  { symbol: 'FC-RX7',      name: 'Mazda RX-7 FC3S',             price: 18000,  change: 2.8  },
  { symbol: 'MR2-SW20',    name: 'Toyota MR2 SW20',             price: 24000,  change: -0.5 },
  { symbol: 'S13-240SX',   name: 'Nissan 240SX S13',            price: 19000,  change: 1.6  },
  { symbol: 'CELICA-GT4',  name: 'Toyota Celica GT-Four',       price: 31000,  change: 4.2  },
  { symbol: 'LANCER-EVO4', name: 'Mitsubishi Evo IV',           price: 55000,  change: 2.9  },
  { symbol: '458-SPEC',    name: 'Ferrari 458 Speciale',        price: 390000, change: 1.8  },
  { symbol: 'GT3RS-991',   name: 'Porsche 991 GT3 RS',          price: 210000, change: -0.9 },
  { symbol: 'AVENTADOR',   name: 'Lamborghini Aventador S',     price: 420000, change: 2.4  },
  { symbol: '720S',        name: 'McLaren 720S',                price: 265000, change: -3.1 },
  { symbol: 'CAYMAN-GT4',  name: 'Porsche Cayman GT4',          price: 118000, change: 1.4  },
  { symbol: 'F8-TRIB',     name: 'Ferrari F8 Tributo',          price: 340000, change: 0.7  },
  { symbol: 'VANTAGE-GT3', name: 'Aston Vantage GT3',           price: 195000, change: 3.8  },
  { symbol: 'MCLAREN-600LT',name:'McLaren 600LT',               price: 225000, change: -1.2 },
  { symbol: 'AMG-GTR',     name: 'Mercedes-AMG GT R',           price: 165000, change: 0.5  },
  { symbol: 'M4-CSL',      name: 'BMW M4 CSL',                  price: 145000, change: 2.1  },
  { symbol: 'GT500-21',    name: 'Shelby GT500 2021',           price: 92000,  change: 4.5  },
  { symbol: 'ZL1-1LE',     name: 'Camaro ZL1 1LE',              price: 75000,  change: 1.9  },
  { symbol: 'VIPER-ACR',   name: 'Dodge Viper ACR',             price: 188000, change: 6.2  },
  { symbol: 'CORVETTE-Z06',name: 'Corvette Z06 C8',             price: 118000, change: -0.3 },
  // Add more ticker-only symbols here ↓
];
