// Checks that the config editor's writer loses nothing. Run: node tests/test_config_roundtrip.js
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const W = require('../frontend/config-writer.js');

const CONFIG = path.join(__dirname, '..', 'frontend', 'cars.config.js');
const parse = text => new Function(text + ';return {CHART_COLORS, WATCHLIST, TICKER_UNIVERSE};')();
const write = d => W.serializeConfig(d.CHART_COLORS, d.WATCHLIST, d.TICKER_UNIVERSE);
const car = (extra) => Object.assign({ id: 't', symbol: 'T', avg_price: 100000, color: '#e8a020' }, extra);
const one = c => parse(W.serializeConfig({ amber: '#e8a020' }, [c], [])).WATCHLIST[0];

// The writer leaves out the two derived cost keys (the page works them out), and a cost_to_own left
// empty by that. A file from before that change (an undo from History, or an Export from a page
// opened before it) still carries them, and must pass.
const FIXTURE = path.join(__dirname, 'fixtures', 'fixture_config.js');
const underived = d => {
  for (const c of [...d.WATCHLIST, ...d.TICKER_UNIVERSE]) {
    if (!c.cost_to_own) continue;
    delete c.cost_to_own.import_duty_est; delete c.cost_to_own.total_first_year_extra;
    if (!Object.keys(c.cost_to_own).length) delete c.cost_to_own;
  }
  return d;
};

const tests = {
  'unedited export parses back identical for every car'() {
    for (const file of [CONFIG, FIXTURE]) {
      const orig = parse(fs.readFileSync(file, 'utf8'));
      const again = parse(write(orig));
      assert.deepStrictEqual(again, underived(parse(fs.readFileSync(file, 'utf8'))), file);
      assert.ok(orig.WATCHLIST.length + orig.TICKER_UNIVERSE.length > 0);
    }
    assert.ok(/import_duty_est/.test(fs.readFileSync(FIXTURE, 'utf8')), 'the fixture keeps the old layout on purpose');
  },
  'writing twice gives the same bytes'() {
    const first = write(parse(fs.readFileSync(CONFIG, 'utf8')));
    assert.strictEqual(write(parse(first)), first);
  },
  'scrape_extras entries keep every key, and a type-less entry gains none'() {
    const extras = [
      { type: 'bat_search', url: 'https://bringatrailer.com/search/?s=nissan+gt-r', years: '2017-2020', include: ['nismo'], exclude: ['parts'] },
      { url: 'x' },
    ];
    assert.deepStrictEqual(one(car({ scrape_extras: extras })).scrape_extras, extras);
  },
  'cost_to_own keeps fields the form has no input for'() {
    const cto = { insurance_annual: 3200, import_duty_pct: 1, shipping_est: 5000, registration_est: 4500,
      registration_note: 'Customs broker + bond', import_note: 'Pure BEV', maintenance_annual: 3500 };
    const got = one(car({ avg_price: 78000, cost_to_own: cto })).cost_to_own;
    assert.deepStrictEqual(got, cto);
  },
  'duty and first-year total are never written, since the page derives them'() {
    const got = one(car({ cost_to_own: { import_duty_pct: 0.025, import_duty_est: 2500, shipping_est: 4500, total_first_year_extra: 7000 } }));
    assert.deepStrictEqual(got.cost_to_own, { import_duty_pct: 0.025, shipping_est: 4500 });
    assert.ok(!('cost_to_own' in one(car({ cost_to_own: { import_duty_est: 1, total_first_year_extra: 2 } }))));
  },
  'notes with line breaks, quotes and backslashes survive'() {
    const note = 'line1\nline2 "q" it\'s \\ done\r';
    assert.strictEqual(one(car({ note })).note, note);
  },
  'session-only and derived runtime keys are never written'() {
    const text = W.serializeCar(car({ delta: 1, delta_pct: 2, delta_dir: 'up', _list: 'ticker', __sessionOnly: true }), {});
    assert.ok(!/delta|_list|__sessionOnly/.test(text), text);
  },
  'unknown keys survive, including ones that need quotes'() {
    const got = one(car({ custom_field: 7, 'odd-key': 'x', flags: { a: true, b: null } }));
    assert.deepStrictEqual([got.custom_field, got['odd-key'], got.flags], [7, 'x', { a: true, b: null }]);
  },
  'palette colors are written by name, others as text'() {
    assert.ok(W.serializeCar(car({}), { amber: '#e8a020' }).includes('color:      CHART_COLORS.amber,'));
    assert.strictEqual(one(car({ color: '#123456' })).color, '#123456');
  },
  'every car block keeps the layout the weekly price patch relies on'() {
    const text = write(parse(fs.readFileSync(CONFIG, 'utf8')));
    const d = parse(text);
    for (const c of [...d.WATCHLIST, ...d.TICKER_UNIVERSE]) {
      const start = text.indexOf("id:         '" + c.id + "'");
      assert.ok(start > 0, c.id);
      const block = text.slice(start, text.indexOf('\n  },', start));
      assert.ok(new RegExp('avg_price:\\s*' + c.avg_price + '\\b').test(block), c.id + ' avg_price');
      assert.ok(new RegExp('prev_avg:\\s*' + c.prev_avg + '\\b').test(block), c.id + ' prev_avg');
    }
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try { fn(); console.log('PASS ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + e.message); }
}
console.log(failed ? failed + ' failed' : Object.keys(tests).length + ' passed');
process.exit(failed ? 1 : 0);
