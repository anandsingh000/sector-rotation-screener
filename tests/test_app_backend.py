"""
Full backend backtest of app.py using Streamlit's official headless
AppTest framework -- this actually runs the real app.py script (not
just its helper functions) and simulates real widget interactions
(button clicks, selectbox changes) exactly like a browser would,
asserting no exception surfaces at any step.

All network calls (yfinance) are monkeypatched with synthetic data
since this sandbox has no internet access to Yahoo Finance -- the
goal here is to exercise every code path in app.py itself (session
state sync, widget wiring, chart rendering, narrative building).
"""
import os
import sys
import numpy as np
import pandas as pd

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)
_APP_PATH = os.path.join(_PROJECT_ROOT, "app.py")

from screener import data as data_module
from screener import fundamentals as fundamentals_module
from screener import scanner as scanner_module

np.random.seed(7)
DATES = pd.bdate_range("2018-01-01", periods=2000)


def make_series(drift, vol, start=100.0):
    rets = np.random.normal(drift, vol, len(DATES))
    return pd.Series(start * np.exp(np.cumsum(rets)), index=DATES)


_UNIVERSE = pd.DataFrame({
    "symbol": ["TCS", "INFY", "RELIANCE", "HDFCBANK", "SIEMENS", "AARTIIND", "MARUTI", "SUNPHARMA"],
    "name": ["TCS", "Infosys", "Reliance", "HDFC Bank", "Siemens", "Aarti Industries", "Maruti Suzuki", "Sun Pharma"],
    "sector": ["Information Technology", "Information Technology", "Oil Gas & Consumable Fuels",
               "Financial Services", "Capital Goods", "Chemicals", "Automobile and Auto Components", "Healthcare"],
})

_SERIES_CACHE = {s: make_series(np.random.uniform(-0.0003, 0.0012), np.random.uniform(0.014, 0.024))
                 for s in _UNIVERSE["symbol"]}


def fake_load_universe(path=None):
    return _UNIVERSE.copy()


def fake_fetch_close_prices(symbols, years=7, **kwargs):
    return pd.DataFrame({s: _SERIES_CACHE[s] for s in symbols if s in _SERIES_CACHE})


def fake_fetch_benchmark_close(symbol, years=7):
    return make_series(0.0004, 0.011).rename("benchmark")


_PERIOD_BARS = {"3mo": 63, "6mo": 126, "1y": 252, "2y": 504, "5y": 1260, "max": 2000}


def fake_fetch_ohlc(symbol, period="1y", interval="1d"):
    n = _PERIOD_BARS.get(period, 252)
    base = _SERIES_CACHE.get(symbol, make_series(0.0005, 0.02))
    close = base.iloc[-n:]
    df = pd.DataFrame({
        "Open": close * 0.995, "High": close * 1.012, "Low": close * 0.988,
        "Close": close, "Volume": np.random.randint(50_000, 900_000, len(close)),
    }, index=close.index)
    return df


def fake_fetch_fundamentals(symbol):
    return {
        "longName": f"{symbol} Ltd", "sector": "Test Sector", "industry": "Test Industry",
        "marketCap": 5.2e11, "trailingPE": 27.3, "forwardPE": 23.1, "priceToBook": 9.4,
        "returnOnEquity": 0.24, "debtToEquity": 15.2, "profitMargins": 0.17,
        "dividendYield": 0.011, "beta": 0.85, "totalRevenue": 1.8e11, "trailingEps": 52.1,
        "recommendationKey": "buy", "targetMeanPrice": 4100.0, "numberOfAnalystOpinions": 22,
    }


data_module.load_universe = fake_load_universe
data_module.fetch_close_prices = fake_fetch_close_prices
data_module.fetch_benchmark_close = fake_fetch_benchmark_close
data_module.fetch_ohlc = fake_fetch_ohlc
fundamentals_module.fetch_fundamentals = fake_fetch_fundamentals

_SCANNER_UNIVERSE = pd.DataFrame({
    "symbol": ["TCS", "INFY", "500325"],
    "name": ["TCS", "Infosys", "Reliance (BSE)"],
    "sector": ["Information Technology", "Information Technology", "Oil Gas & Consumable Fuels"],
    "exchange": ["NSE", "NSE", "BSE"],
    "yahoo_symbol": ["TCS.NS", "INFY.NS", "500325.BO"],
})


def fake_load_market_universe(path=None):
    return _SCANNER_UNIVERSE.copy()


def fake_fetch_ohlcv_bulk(yahoo_symbols, period="1y", **kwargs):
    out = {}
    for ysym in yahoo_symbols:
        base = make_series(np.random.uniform(-0.0003, 0.0012), np.random.uniform(0.015, 0.025)).iloc[-260:]
        vol = np.random.randint(20_000, 300_000, len(base)).astype(float)
        out[ysym] = pd.DataFrame({
            "Open": base * 0.995, "High": base * 1.012, "Low": base * 0.988,
            "Close": base, "Volume": vol,
        }, index=base.index)
    return out


def fake_fetch_deep_fundamentals(yahoo_symbol):
    return {"roe": 18.5, "pe": 22.0, "pb": 4.2, "cash_flow_trend": "Rising", "roce": 17.0}


data_module.load_market_universe = fake_load_market_universe
data_module.fetch_ohlcv_bulk = fake_fetch_ohlcv_bulk
scanner_module.fetch_deep_fundamentals = fake_fetch_deep_fundamentals

from streamlit.testing.v1 import AppTest  # noqa: E402

FAILURES = []


def check(label, at):
    if at.exception:
        FAILURES.append((label, str(at.exception[0])))
        print(f"[FAIL] {label}: {at.exception[0]}")
    else:
        print(f"[ OK ] {label}")


print("=== 1. Initial load ===")
at = AppTest.from_file(_APP_PATH)
at.run(timeout=120)
check("initial script run (before any Run-click)", at)

print("\n=== 2. Click 'Run / refresh screen' ===")
at.sidebar.button[0].click().run(timeout=120)
check("after clicking Run/refresh", at)

print("\n=== 3. Select a different stock in the Chart tab ===")
chart_select = at.selectbox(key="chart_symbol_pick")
target = "SIEMENS" if chart_select.value != "SIEMENS" else "INFY"
chart_select.set_value(target).run(timeout=60)
check(f"chart tab -> select {target}", at)
print("    selected_symbol now:", at.session_state["selected_symbol"])

print("\n=== 4. Select a different stock in the Technical+Fundamental tab ===")
ta_select = at.selectbox(key="ta_symbol_pick")
target2 = "AARTIIND" if ta_select.value != "AARTIIND" else "MARUTI"
ta_select.set_value(target2).run(timeout=60)
check(f"TA tab -> select {target2}", at)
print("    selected_symbol now:", at.session_state["selected_symbol"])
print("    chart_symbol_pick now:", at.session_state["chart_symbol_pick"])

print("\n=== 5. Ping-pong: change chart tab again right after TA tab changed it ===")
chart_select2 = at.selectbox(key="chart_symbol_pick")
target3 = "TCS" if chart_select2.value != "TCS" else "RELIANCE"
chart_select2.set_value(target3).run(timeout=60)
check(f"chart tab -> select {target3} (right after TA-driven sync)", at)

print("\n=== 6. Change period + interval in Chart tab (this previously duplicated the chart element) ===")
period_select = at.selectbox(key="chart_period_pick")
period_select.set_value("6mo").run(timeout=60)
check("chart tab -> period 6mo", at)
interval_select = at.selectbox(key="chart_interval_pick")
interval_select.set_value("Weekly").run(timeout=60)
check("chart tab -> interval Weekly", at)

print("\n=== 7. Click 'Clear drawings' ===")
clear_btn = [b for b in at.button if "Clear drawings" in b.label][0]
clear_btn.click().run(timeout=60)
check("clear drawings button", at)

print("\n=== 8. Click 'Retry data' in Chart tab ===")
retry_btns = [b for b in at.button if "Retry data" in b.label]
retry_btns[0].click().run(timeout=60)
check("retry data (chart tab)", at)

print("\n=== 9. Click 'Retry data' in Technical+Fundamental tab (if a second one exists) ===")
if len(retry_btns) > 1:
    retry_btns[1].click().run(timeout=60)
    check("retry data (TA tab)", at)

print("\n=== 10. Market Scanner -> Run Market Scan ===")
scan_btn = [b for b in at.button if b.key == "run_scanner_btn"]
if scan_btn:
    scan_btn[0].click().run(timeout=120)
    check("market scanner -> Run Market Scan", at)
    print("    scanner_result rows:", len(at.session_state["scanner_result"]) if "scanner_result" in at.session_state else "N/A")
else:
    print("    [SKIP] run_scanner_btn not found")

print("\n=== 11. Market Scanner -> open column filter expander + Clear all / Select all ===")
clear_all_btn = [b for b in at.button if b.key == "scancol_clear_all"]
if clear_all_btn:
    clear_all_btn[0].click().run(timeout=60)
    check("scanner -> Clear all columns", at)
select_all_btn = [b for b in at.button if b.key == "scancol_select_all"]
if select_all_btn:
    select_all_btn[0].click().run(timeout=60)
    check("scanner -> Select all columns", at)

print("\n=== 12. Market Scanner -> toggle a single column checkbox ===")
col_checkbox = [c for c in at.checkbox if c.key == "scancol_roce"]
if col_checkbox:
    col_checkbox[0].set_value(False).run(timeout=60)
    check("scanner -> untick ROCE column", at)

print("\n=== 13. Market Scanner -> sub-filters (volume surge, cash flow rising, valuation) ===")
surge_cb = [c for c in at.checkbox if c.key == "scanner_only_surge"]
if surge_cb:
    surge_cb[0].set_value(True).run(timeout=60)
    check("scanner -> only volume surge filter", at)
cf_cb = [c for c in at.checkbox if c.key == "scanner_only_cf_rising"]
if cf_cb:
    cf_cb[0].set_value(True).run(timeout=60)
    check("scanner -> only cash-flow-rising filter", at)
val_pick = [m for m in at.multiselect if m.key == "scanner_valuation_pick"]
if val_pick:
    val_pick[0].set_value(["Undervalued"]).run(timeout=60)
    check("scanner -> valuation filter = Undervalued", at)

print("\n=== 14. Market Scanner -> exchange filter change + re-run scan ===")
exch_select = [s for s in at.selectbox if s.key == "scanner_exchange_pick"]
if exch_select:
    exch_select[0].set_value("BSE only").run(timeout=60)
    check("scanner -> exchange = BSE only", at)
if scan_btn:
    scan_btn2 = [b for b in at.button if b.key == "run_scanner_btn"]
    scan_btn2[0].click().run(timeout=120)
    check("scanner -> re-run scan after exchange change", at)

print("\n=== 15. Re-run the whole script fresh once more (idempotency check) ===")
at.run(timeout=60)
check("final fresh rerun", at)

print("\n\n================ SUMMARY ================")
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for label, msg in FAILURES:
        print(f" - {label}: {msg}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED -- no exceptions across every simulated interaction.")
