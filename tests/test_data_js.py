"""Checks for the data.js chart format ({start, prices} per car). Run: python tests/test_data_js.py"""
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))
import generate_history as gh     # noqa: E402

DATA_JS = ROOT / "frontend" / "data.js"
INDEX_HTML = ROOT / "frontend" / "index.html"


def expander():
    """The page's own expander: the inline script right after the data.js tag in index.html."""
    m = re.search(r'<script src="data\.js"></script>\s*<script>(.*?)</script>', INDEX_HTML.read_text(), re.S)
    assert m, "no expander script right after <script src=\"data.js\"> in index.html"
    return m.group(1)


def expand(data_js_text):
    """Load a data.js text, run the page's expander on it in node and return BAKED_HISTORY."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "data.js"
        path.write_text(data_js_text)
        js = ("const fs = require('fs');"
              "const code = fs.readFileSync(process.argv[1], 'utf8') + '\\n' + process.argv[2] + '\\n;return BAKED_HISTORY;';"
              "process.stdout.write(JSON.stringify(new Function(code)()));")
        out = subprocess.run(["node", "-e", js, str(path), expander()], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def days_from(start, n):
    """The dates the old data.js wrote: one per day from start, by Python's date arithmetic."""
    s = date.fromisoformat(start)
    return [(s + timedelta(days=i)).isoformat() for i in range(n)]


def test_committed_data_js_is_under_200_kb():
    assert DATA_JS.stat().st_size < 200_000, DATA_JS.stat().st_size


def test_committed_lines_expand_to_one_point_per_day():
    raw = json.loads(DATA_JS.read_text().split("\n")[0][len("var BAKED_HISTORY = "):-1])
    lines = expand(DATA_JS.read_text())
    assert sorted(lines) == sorted(raw) and len(lines) > 0
    for cid, line in lines.items():
        assert [p["date"] for p in line] == days_from(raw[cid]["start"], len(raw[cid]["prices"])), cid
        assert [p["price"] for p in line] == raw[cid]["prices"], cid
        assert len(line) == gh.WALK_DAYS, cid
    assert len(lines["r33-gtr"]) == 365


def test_expanded_lines_equal_the_old_format():
    """For every car in the config, the generator's {start, prices} expanded by the page gives exactly
    the old line's dates and prices, including across a leap day and the DST changes."""
    history, cfg = gh.load_price_history(), gh.load_cars_from_config()
    saved = gh.DATA_JS_PATH
    for today in (date(2026, 9, 29), date(2028, 3, 1), date(2027, 1, 1)):
        with tempfile.TemporaryDirectory() as tmp:
            gh.DATA_JS_PATH = Path(tmp) / "data.js"
            try:
                gh.build_data_js(history, today, cfg)
                lines = expand(gh.DATA_JS_PATH.read_text())
            finally:
                gh.DATA_JS_PATH = saved
        priced = [cid for cid, c in cfg.items() if (c.get("avg_price") or 0) > 0]
        assert sorted(lines) == sorted(priced) and len(lines) > 0
        for cid in priced:
            old = gh.make_synthetic_leadin(cid, cfg[cid]["avg_price"], today, days=gh.WALK_DAYS)
            assert [p["date"] for p in lines[cid]] == [p["date"] for p in old], (today, cid)
            assert [p["price"] for p in lines[cid]] == [p["price"] for p in old], (today, cid)


def test_an_old_data_js_still_loads():
    """A cached data.js from before this format stores arrays of points; the expander leaves them as they are."""
    old = {"r33-gtr": [{**p, "lo": p["price"], "hi": p["price"], "volume": 0, "kind": "walk"}
                       for p in gh.make_synthetic_leadin("r33-gtr", 32000, date(2026, 9, 29))]}
    text = "var BAKED_HISTORY = " + json.dumps(old, separators=(",", ":")) + ";\nvar BAKED_SALES = {};\nvar BAKED_META = {};\n"
    assert expand(text) == old


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for fn in fns:
        # The generator prints its own progress; keep it out of the log and show it on failure
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                fn()
        except BaseException:
            print(out.getvalue())
            raise
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} passed")
