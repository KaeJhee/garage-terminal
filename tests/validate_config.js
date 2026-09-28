// Sanity checks for frontend/cars.config.js. Run: node tests/validate_config.js
// Errors stop the weekly update before anything is scraped or committed. Warnings are printed only.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const CONFIG = path.join(ROOT, 'frontend', 'cars.config.js');
const CATEGORIES = ['JDM', 'Modern', 'Exotic', 'Muscle', 'European', 'Chinese'];   // the editor's list
const errors = [], warnings = [];

// A browser that already has cars.config.js in Downloads saves "cars.config (1).js"; an upload
// under that name would sit next to the real file and change nothing
(function findStray(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === '.git' || e.name === 'node_modules') continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) findStray(p);
    else if (/^cars\.config.*\.js$/i.test(e.name) && p !== CONFIG) {
      errors.push(path.relative(ROOT, p) + ': extra config file. Upload it as frontend/cars.config.js instead, then delete this one.');
    }
  }
})(ROOT);

let d;
try {
  d = new Function(fs.readFileSync(CONFIG, 'utf8') + ';return {CHART_COLORS, WATCHLIST, TICKER_UNIVERSE};')();
} catch (e) {
  console.log('ERROR cars.config.js does not load: ' + e.message);
  process.exit(1);
}

const colors = new Set(Object.values(d.CHART_COLORS || {}));
const ids = {}, symbols = {};
const cars = [].concat(d.WATCHLIST || [], d.TICKER_UNIVERSE || []);
if (!cars.length) errors.push('no cars found in WATCHLIST or TICKER_UNIVERSE');

for (const c of cars) {
  const name = c.id || '(car with no id)';
  if (!c.id) errors.push(name + ': id is empty');
  else if (ids[c.id]) errors.push(name + ': duplicate id (an id can appear only once across WATCHLIST and TICKER_UNIVERSE)');
  ids[c.id] = true;
  if (!c.symbol) errors.push(name + ': symbol is empty');
  else if (symbols[c.symbol]) errors.push(name + ': duplicate symbol ' + c.symbol);
  symbols[c.symbol] = true;
  if (!colors.has(c.color)) errors.push(name + ': color is not one of CHART_COLORS');
  if (!(typeof c.avg_price === 'number' && c.avg_price > 0)) errors.push(name + ': avg_price is missing');
  if (c.years != null && c.years !== '') {
    const m = /^\s*(\d{4})\s*(?:-\s*(\d{4}|present)\s*)?$/i.exec(String(c.years));
    if (!m || (m[2] && /^\d/.test(m[2]) && +m[2] < +m[1])) errors.push(name + ': years "' + c.years + '" should look like 1995-1998, 2023-Present or 2020');
  }
  if (c.low_price > 0 && c.high_price > 0 && c.low_price >= c.high_price) errors.push(name + ': low_price must be below high_price');

  const isBat = u => /^https:\/\/(www\.)?bringatrailer\.com\//.test(u || '');
  const extras = Array.isArray(c.scrape_extras) ? c.scrape_extras.filter(x => x && x.type === 'bat_search' && isBat(x.url)) : [];
  if (c.category !== 'Chinese' && !isBat(c.bat_url) && !extras.length) {
    warnings.push(name + ': no Bring a Trailer search in bat_url or scrape_extras, so this car is not scraped');
  }
  if (c.low_price > 0 && c.high_price > 0 && (c.avg_price < c.low_price || c.avg_price > c.high_price)) {
    const refused = c.avg_price < c.low_price * 0.8 || c.avg_price > c.high_price * 1.25;
    warnings.push(name + ': avg_price ' + c.avg_price + ' is outside low_price ' + c.low_price + ' to high_price ' + c.high_price +
      (refused ? ', and sale prices near it will be refused by the price guard' : ''));
  }
  if (c.category && CATEGORIES.indexOf(c.category) < 0) warnings.push(name + ': category "' + c.category + '" is not in the editor list');
}

for (const w of warnings) console.log('WARN  ' + w);
for (const e of errors) console.log('ERROR ' + e);
console.log(errors.length ? errors.length + ' error(s)' : 'config OK: ' + cars.length + ' cars');
process.exit(errors.length ? 1 : 0);
