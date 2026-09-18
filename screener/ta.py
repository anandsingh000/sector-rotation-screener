"""
Supplementary technical-analysis helpers used only in the per-stock
"Chart & Drawing" and "Technical + Fundamental" tabs.

These (RSI, MACD, 52-week range) are standard extra indicators for a
human reading a single stock's chart -- they are NOT part of the core
four-layer Rotation Score (see indicators.py / scorer.py for that,
which stay a strict 1:1 mirror of the methodology PDF). Kept in a
separate module on purpose so the audited scoring engine is never
touched by chart-tab additions.
"""

from __future__ import annotations

import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Classic Wilder RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Standard MACD: line, signal, histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def moving_averages(close: pd.Series, windows: tuple[int, ...] = (20, 50, 200)) -> pd.DataFrame:
    return pd.DataFrame({f"sma_{w}": close.rolling(w).mean() for w in windows})


def fifty_two_week_range(close: pd.Series) -> dict:
    last_year = close.tail(252)
    if last_year.empty:
        return {"high": None, "low": None, "pct_from_high": None, "pct_from_low": None}
    hi, lo, last = last_year.max(), last_year.min(), close.iloc[-1]
    return {
        "high": float(hi),
        "low": float(lo),
        "pct_from_high": float((last / hi - 1) * 100),
        "pct_from_low": float((last / lo - 1) * 100),
    }


def rsi_zone(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "unknown"
    if value >= 70:
        return "overbought"
    if value <= 30:
        return "oversold"
    return "neutral"


def macd_state(macd_df: pd.DataFrame) -> str:
    valid = macd_df.dropna()
    if valid.empty:
        return "unknown"
    last = valid.iloc[-1]
    return "bullish" if last["macd"] > last["signal"] else "bearish"
