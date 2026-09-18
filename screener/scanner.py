"""
Analytics for the "Market Scanner" tab -- a broad NSE+BSE scan, distinct
from the core 4-layer Rotation Score (indicators.py/scorer.py, which stay
untouched) and from the per-stock chart tab's RSI/MACD (ta.py, reused
here for RSI).

Every function here is best-effort: yfinance's fundamentals coverage for
Indian stocks (especially smaller/BSE-only names) is inconsistent, so
missing inputs simply produce "Unknown"/None rather than raising --
callers must handle that.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from . import ta


# ---------------------------------------------------------------------------
# Price/volume-based signals (from bulk OHLCV -- fast, no per-stock network
# calls beyond the initial bulk download).
# ---------------------------------------------------------------------------
def range_stats(high: pd.Series, low: pd.Series, window: int) -> dict:
    """Highest High / lowest Low over the trailing `window` trading days."""
    h, l = high.dropna().tail(window), low.dropna().tail(window)
    if h.empty or l.empty:
        return {"high": None, "low": None}
    return {"high": float(h.max()), "low": float(l.min())}


def pct_from(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference == 0:
        return None
    return (value / reference - 1) * 100


def volume_signal(volume: pd.Series, lookback: int = 20, surge_ratio: float = 1.5) -> dict:
    """
    Compares the latest day's volume to the trailing `lookback`-day average
    (excluding today). `surge=True` flags a volume spike -- a common
    "something's happening" tell independent of price direction.
    """
    v = volume.dropna()
    if len(v) < lookback + 1:
        return {"latest": None, "avg": None, "ratio": None, "surge": False}
    latest = float(v.iloc[-1])
    avg = float(v.iloc[-(lookback + 1):-1].mean())
    ratio = (latest / avg) if avg else None
    return {"latest": latest, "avg": avg, "ratio": ratio, "surge": bool(ratio and ratio >= surge_ratio)}


def ema_crossover_state(close: pd.Series, fast: int = 20, slow: int = 50) -> str:
    """
    'Bullish Crossover' / 'Bearish Crossover' if the cross happened on the
    most recent bar, else just the current alignment ('Bullish'/'Bearish').
    """
    valid = close.dropna()
    if len(valid) < slow + 2:
        return "Unknown"
    ema_fast = valid.ewm(span=fast, adjust=False).mean()
    ema_slow = valid.ewm(span=slow, adjust=False).mean()
    diff = (ema_fast - ema_slow).dropna()
    if len(diff) < 2:
        return "Unknown"
    today, yday = diff.iloc[-1], diff.iloc[-2]
    if yday <= 0 < today:
        return "Bullish Crossover"
    if yday >= 0 > today:
        return "Bearish Crossover"
    return "Bullish" if today > 0 else "Bearish"


# ---------------------------------------------------------------------------
# Fundamentals-based signals (cash-flow trend, ROCE) -- one extra yfinance
# Ticker per stock, on top of the info/ROE/P-E/P-B already fetched by
# screener.fundamentals.fetch_fundamentals(). Deliberately NOT retried
# per-call (unlike fundamentals.py) since a full-universe scan already
# makes many calls -- a handful landing as "Unknown" is an acceptable
# trade-off for scan speed; the per-stock Technical+Fundamental tab (which
# DOES retry) is the place to double-check any one name.
# ---------------------------------------------------------------------------
def _find_row(df: pd.DataFrame, name_fragments: tuple[str, ...]) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for idx in df.index:
        low = str(idx).lower()
        if any(frag in low for frag in name_fragments):
            row = df.loc[idx].dropna()
            if not row.empty:
                return row
    return None


def cash_flow_trend(ticker: yf.Ticker) -> str:
    """
    'Rising' / 'Falling' / 'Flat' based on the two most recent quarters of
    operating cash flow; 'Unknown' if the statement isn't available.
    """
    try:
        qcf = ticker.quarterly_cashflow
    except Exception:
        return "Unknown"
    row = _find_row(qcf, ("operating cash flow", "cash from operating"))
    if row is None or len(row) < 2:
        return "Unknown"
    # yfinance columns are most-recent-first
    recent, prior = row.iloc[0], row.iloc[1]
    if prior == 0:
        return "Unknown"
    change = (recent - prior) / abs(prior)
    if change > 0.03:
        return "Rising"
    if change < -0.03:
        return "Falling"
    return "Flat"


def compute_roce(ticker: yf.Ticker) -> float | None:
    """ROCE % = EBIT / (Total Assets - Current Liabilities) * 100, most recent annual period."""
    try:
        fin = ticker.financials
        bs = ticker.balance_sheet
    except Exception:
        return None

    ebit_row = _find_row(fin, ("ebit", "operating income"))
    assets_row = _find_row(bs, ("total assets",))
    curr_liab_row = _find_row(bs, ("total current liabilities", "current liabilities"))
    if ebit_row is None or assets_row is None or curr_liab_row is None:
        return None

    ebit = ebit_row.iloc[0]
    capital_employed = assets_row.iloc[0] - curr_liab_row.iloc[0]
    if not capital_employed:
        return None
    return float(ebit / capital_employed * 100)


def fetch_deep_fundamentals(yahoo_symbol: str) -> dict:
    """
    One consolidated per-stock fetch used by the Market Scanner: ROE /
    trailing P/E / P/B (from `.info`), cash-flow trend, and ROCE.
    Every field is None/"Unknown" on failure -- never raises.
    """
    out = {"roe": None, "pe": None, "pb": None, "cash_flow_trend": "Unknown", "roce": None}
    try:
        ticker = yf.Ticker(yahoo_symbol)
    except Exception:
        return out

    try:
        info = ticker.get_info() if hasattr(ticker, "get_info") else ticker.info
    except Exception:
        info = None
    if info:
        roe = info.get("returnOnEquity")
        out["roe"] = roe * 100 if roe is not None else None
        out["pe"] = info.get("trailingPE")
        out["pb"] = info.get("priceToBook")

    out["cash_flow_trend"] = cash_flow_trend(ticker)
    out["roce"] = compute_roce(ticker)
    return out


# ---------------------------------------------------------------------------
# Valuation heuristic
# ---------------------------------------------------------------------------
def valuation_label(pe: float | None, sector_median_pe: float | None) -> str:
    """
    A DELIBERATELY SIMPLE heuristic -- not a DCF or intrinsic-value model.
    Compares trailing P/E against the sector's median P/E within the
    scanned universe; falls back to crude absolute P/E bands if no sector
    median is available. Always treat this as a rough first filter, not a
    valuation call.
    """
    if pe is None or pe <= 0:
        return "Unknown"
    if sector_median_pe and sector_median_pe > 0:
        ratio = pe / sector_median_pe
        if ratio < 0.85:
            return "Undervalued"
        if ratio > 1.15:
            return "Overvalued"
        return "Fair Value"
    if pe < 15:
        return "Undervalued"
    if pe > 35:
        return "Overvalued"
    return "Fair Value"


# ---------------------------------------------------------------------------
# Orchestration: bulk price/volume/RSI/EMA scan (fast, whole universe) +
# deep fundamentals (slow, limited to `fundamentals_limit` stocks).
# ---------------------------------------------------------------------------
def run_market_scan(
    universe: pd.DataFrame,
    ohlcv_map: dict[str, pd.DataFrame],
    fundamentals_limit: int = 60,
    progress_cb=None,
) -> pd.DataFrame:
    """
    universe: DataFrame with symbol, name, sector, exchange, yahoo_symbol
              (as returned by data.load_market_universe)
    ohlcv_map: {yahoo_symbol: OHLCV DataFrame} from data.fetch_ohlcv_bulk

    Returns one row per stock with price/volume/RSI/EMA columns for the
    WHOLE universe, and fundamentals columns (ROE, P/E, P/B, cash-flow
    trend, ROCE, valuation) only for the first `fundamentals_limit`
    stocks that had usable price data -- the rest show "Not scanned" so
    it's clear more weren't checked rather than silently blank.
    """
    rows = []
    for u in universe.itertuples(index=False):
        ysym = u.yahoo_symbol
        df = ohlcv_map.get(ysym)
        base = {
            "symbol": u.symbol, "name": u.name, "sector": u.sector,
            "exchange": u.exchange, "yahoo_symbol": ysym,
        }
        if df is None or df.empty or "Close" not in df.columns:
            rows.append({**base, "has_price_data": False, "ltp": None})
            continue

        close = df["Close"].dropna()
        high = df["High"] if "High" in df.columns else close
        low = df["Low"] if "Low" in df.columns else close
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(dtype=float)

        ltp = float(close.iloc[-1]) if not close.empty else None
        r52 = range_stats(high, low, 252)
        r1w = range_stats(high, low, 5)
        vol = volume_signal(volume)
        rsi_series = ta.rsi(close).dropna()
        rsi_last = float(rsi_series.iloc[-1]) if not rsi_series.empty else None

        rows.append({
            **base, "has_price_data": True, "ltp": ltp,
            "52w_high": r52["high"], "52w_low": r52["low"],
            "pct_from_52w_high": pct_from(ltp, r52["high"]),
            "pct_from_52w_low": pct_from(ltp, r52["low"]),
            "1w_high": r1w["high"], "1w_low": r1w["low"],
            "volume_latest": vol["latest"], "volume_avg20": vol["avg"],
            "volume_ratio": vol["ratio"], "volume_surge": vol["surge"],
            "rsi": rsi_last, "ema_state": ema_crossover_state(close),
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    scan_targets = result.loc[result["has_price_data"], "yahoo_symbol"].head(fundamentals_limit).tolist()
    deep: dict[str, dict] = {}
    for i, ysym in enumerate(scan_targets):
        deep[ysym] = fetch_deep_fundamentals(ysym)
        if progress_cb:
            progress_cb(i + 1, len(scan_targets))

    for field in ("roe", "pe", "pb", "cash_flow_trend", "roce"):
        result[field] = result["yahoo_symbol"].map(lambda s, f=field: deep.get(s, {}).get(f))
    result["fundamentals_scanned"] = result["yahoo_symbol"].isin(scan_targets)

    sector_median_pe = (
        result.loc[result["fundamentals_scanned"] & result["pe"].notna(), ["sector", "pe"]]
        .groupby("sector")["pe"].median()
    )
    result["sector_median_pe"] = result["sector"].map(sector_median_pe)
    result["valuation"] = result.apply(
        lambda r: valuation_label(r["pe"], r["sector_median_pe"]) if r["fundamentals_scanned"] else "Not scanned",
        axis=1,
    )
    return result
