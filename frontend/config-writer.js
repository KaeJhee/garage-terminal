// config-writer.js: the one place that writes cars.config.js text.
// Used by the dashboard's config editor (Export, Copy config snippet) and by the node tests.
// It writes every key it is given, so fields the editor has no input for survive an export.
// Layout contract relied on by scraper/generate_history.py: unquoted keys, two-space car
// indent, and each car block closed by "\n  },".
(function (root) {
  var CAR_ORDER = ['id', 'symbol', 'make', 'model', 'years', 'category', 'engine', 'power',
    'avg_price', 'low_price', 'high_price', 'prev_avg', 'color', 'note', 'bat_url',
    'bat_title_include', 'bat_title_exclude', 'market_url', 'scrape_extras'];
  var CTO_ORDER = ['insurance_annual', 'insurance_note', 'import_duty_pct',
    'shipping_est', 'registration_est', 'registration_note', 'import_note',
    'maintenance_annual', 'maintenance_note'];
  var RUNTIME = { delta: 1, delta_pct: 1, delta_dir: 1, _list: 1, __sessionOnly: 1 };
  // Duty and first-year total are never written: the page derives them from avg_price (ctoDerived)
  var DERIVED = { import_duty_est: 1, total_first_year_extra: 1 };

  function key(k) { return /^[A-Za-z_$][\w$]*$/.test(k) ? k : jsLit(k); }

  function jsLit(v) {
    if (Array.isArray(v)) return '[' + v.map(jsLit).join(', ') + ']';
    if (v && typeof v === 'object') {
      return '{ ' + Object.keys(v).filter(function (k) { return v[k] !== undefined; })
        .map(function (k) { return key(k) + ': ' + jsLit(v[k]); }).join(', ') + ' }';
    }
    if (typeof v === 'string') {
      // Single quotes, or double quotes when that avoids escaping an apostrophe
      var q = v.indexOf("'") >= 0 && v.indexOf('"') < 0 ? '"' : "'";
      return q + v.replace(/\\/g, '\\\\').replace(q === '"' ? /"/g : /'/g, '\\' + q)
        .replace(/\n/g, '\\n').replace(/\r/g, '\\r') + q;
    }
    return String(v);
  }

  function pad(k, width) { var s = key(k) + ':'; return s.length < width ? s + new Array(width - s.length + 1).join(' ') : s + ' '; }

  function ordered(obj, order, last) {
    var ks = Object.keys(obj).filter(function (k) { return obj[k] !== undefined && !RUNTIME[k] && k !== last; });
    return order.filter(function (k) { return ks.indexOf(k) >= 0; })
      .concat(ks.filter(function (k) { return order.indexOf(k) < 0; }))
      .concat(last && obj[last] !== undefined ? [last] : []);
  }

  function serializeCar(c, colors) {
    var hex = {};
    Object.keys(colors || {}).forEach(function (k) { hex[colors[k]] = k; });
    var L = ['  {'];
    ordered(c, CAR_ORDER, 'cost_to_own').forEach(function (k) {
      var v = c[k];
      if (k === 'color' && hex[v]) L.push('    ' + pad(k, 12) + 'CHART_COLORS.' + hex[v] + ',');
      else if (k === 'scrape_extras' && Array.isArray(v)) {
        L.push('    scrape_extras: [');
        v.forEach(function (x) { L.push('      ' + jsLit(x) + ','); });
        L.push('    ],');
      } else if (k === 'cost_to_own' && v && typeof v === 'object' && !Array.isArray(v)) {
        var cto = {};
        Object.keys(v).forEach(function (ck) { if (!DERIVED[ck]) cto[ck] = v[ck]; });
        if (!Object.keys(cto).length) return;
        L.push('    cost_to_own: {');
        ordered(cto, CTO_ORDER).forEach(function (ck) {
          L.push('      ' + pad(ck, 24) + jsLit(cto[ck]) + ',');
        });
        L.push('    },');
      } else L.push('    ' + pad(k, 12) + jsLit(v) + ',');
    });
    L.push('  },');
    return L.join('\n');
  }

  function serializeConfig(colors, watchlist, ticker) {
    var colorLines = Object.keys(colors).map(function (k) { return '  ' + pad(k, 9) + jsLit(colors[k]) + ','; });
    function list(cars) { return cars.map(function (c) { return serializeCar(c, colors); }).join('\n\n'); }
    return '// cars.config.js: Garage Terminal\'s single source of truth for every car.\n' +
      '// Edit it with the dashboard\'s CONFIG editor. Field guide: HOW_TO_ADD_A_CAR.md\n\n' +
      'var CHART_COLORS = {\n' + colorLines.join('\n') + '\n};\n\n' +
      'var WATCHLIST = [\n' + list(watchlist) + '\n];\n\n' +
      'var TICKER_UNIVERSE = [\n' + list(ticker) + '\n];\n';
  }

  var api = { jsLit: jsLit, serializeCar: serializeCar, serializeConfig: serializeConfig };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.GarageConfig = api;
})(this);
