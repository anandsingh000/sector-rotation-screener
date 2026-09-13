"""
The four analytical layers (Section 3 of the methodology).

    3.1  Relative Rotation Graph (RRG)
    3.2  Relative Strength (RS) ranking
    3.3  Absolute trend filter (200-DMA)
    3.4  Sector breadth

Every formula below is a direct, literal translation of the document's
pseudocode -- kept 1:1 so the tool can be audited line-by-line against
the methodology PDF.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# 3.1  RRG
# ---------------------------------------------------------------------------
def compute_rrg(stock_close: pd.Series, benchmark_close: pd.Series, W: int, L: int) -> pd.DataFrame:
    """
    raw_rs = (stock_close / benchmark_close) * 100
    rs_ratio = 100 + (raw_rs - SMA(raw_rs, W)) / StdDev(raw_rs, W)
    roc = rs_ratio / rs_ratio.shift(L)
    rs_momentum = 100 + (roc - SMA(roc, W)) / StdDev(roc, W)

    Returns a DataFrame indexed like the (aligned) input series with
    columns: raw_rs, rs_ratio, roc, rs_momentum.
    """
    df = pd.DataFrame({"stock": stock_close, "benchmark": benchmark_close}).dropna()
    raw_rs = (df["stock"] / df["benchmark"]) * 100

    rs_ratio = 100 + (raw_rs - raw_rs.rolling(W).mean()) / raw_rs.rolling(W).std()
    roc = rs_ratio / rs_ratio.shift(L)
    rs_momentum = 100 + (roc - roc.rolling(W).mean()) / roc.rolling(W).std()

    return pd.DataFrame({"raw_rs": raw_rs, "rs_ratio": rs_ratio, "roc": roc, "rs_momentum": rs_momentum})


def classify_quadrant(rs_ratio: float, rs_momentum: float) -> str:
    """Section 3.1 quadrant table."""
    if rs_ratio > 100 and rs_momentum > 100:
        return "Leading"
    if rs_ratio < 100 and rs_momentum > 100:
        return "Improving"
    if rs_ratio > 100 and rs_momentum < 100:
        return "Weakening"
    return "Lagging"  # rs_ratio < 100 and rs_momentum < 100


def classify_direction(rs_momentum_series: pd.Series) -> str:
    """'accelerating' if the latest momentum reading is rising, else 'decelerating'."""
    valid = rs_momentum_series.dropna()
    if len(valid) < 2:
        return "decelerating"
    return "accelerating" if valid.iloc[-1] > valid.iloc[-2] else "decelerating"


def latest_rrg_state(rrg_df: pd.DataFrame) -> dict:
    """Convenience: pull the latest quadrant + direction + raw values out of an RRG frame."""
    valid = rrg_df.dropna(subset=["rs_ratio", "rs_momentum"])
    if valid.empty:
        return {"rs_ratio": np.nan, "rs_momentum": np.nan, "quadrant": None, "direction": None}
    last = valid.iloc[-1]
    quadrant = classify_quadrant(last["rs_ratio"], last["rs_momentum"])
    direction = classify_direction(valid["rs_momentum"])
    return {
        "rs_ratio": float(last["rs_ratio"]),
        "rs_momentum": float(last["rs_momentum"]),
        "quadrant": quadrant,
        "direction": direction,
    }


def rrg_score_from_state(state: dict) -> float:
    """Section 4 mapping table; falls back to neutral 50 if undefined."""
    if state.get("quadrant") is None or state.get("direction") is None:
        return config.NEUTRAL_FALLBACK_SCORE
    return config.RRG_SCORE_MAP.get((state["quadrant"], state["direction"]), config.NEUTRAL_FALLBACK_SCORE)


# ---------------------------------------------------------------------------
# 3.2  Relative Strength (RS) ranking
# ---------------------------------------------------------------------------
def period_return(close: pd.Series, lookback_days: int) -> float | None:
    """Simple total return over the trailing `lookback_days` bars."""
    if len(close.dropna()) <= lookback_days:
        return None
    end = close.dropna().iloc[-1]
    start = close.dropna().iloc[-1 - lookback_days]
    if start == 0 or pd.isna(start):
        return None
    return (end / start) - 1.0


def composite_rs(stock_close: pd.Series, benchmark_close: pd.Series) -> float | None:
    """
    for each look-back: RS = stock_return - benchmark_return
    composite_rs = sum(weight_i * RS_i)
    """
    parts = []
    weights = []
    for label, days in config.RS_LOOKBACK_DAYS.items():
        sret = period_return(stock_close, days)
        bret = period_return(benchmark_close, days)
        if sret is None or bret is None:
            continue
        parts.append(sret - bret)
        weights.append(config.RS_WEIGHTS[label])
    if not parts:
        return None
    weights = np.array(weights)
    weights = weights / weights.sum()  # renormalise if some look-backs were unavailable
    return float(np.dot(parts, weights))


def rs_percentile_rank(composite_rs_values: pd.Series) -> pd.Series:
    """
    Rank-convert composite RS values to a 0-100 percentile across the given
    universe (or sub-universe, e.g. a single sector for the drill-down view).
    """
    valid = composite_rs_values.dropna()
    if valid.empty:
        return pd.Series(index=composite_rs_values.index, dtype=float)
    pct = valid.rank(pct=True) * 100
    return pct.reindex(composite_rs_values.index)


# ---------------------------------------------------------------------------
# 3.3  Absolute trend filter (200-DMA)
# ---------------------------------------------------------------------------
def trend_filter(close: pd.Series, window: int = config.TREND_DMA_WINDOW) -> dict:
    """
    above_200dma = close > SMA(close, 200)
    trend_score = 100 if above else 0
    pct_from_dma = (close / SMA(close, 200) - 1) * 100
    """
    dma = close.rolling(window).mean()
    valid = close.dropna()
    if len(valid) < window or pd.isna(dma.iloc[-1]):
        return {"above_200dma": None, "trend_score": config.NEUTRAL_FALLBACK_SCORE, "pct_from_dma": None, "near": None}

    last_close = close.iloc[-1]
    last_dma = dma.iloc[-1]
    above = bool(last_close > last_dma)
    pct_from = (last_close / last_dma - 1) * 100
    near = abs(pct_from) <= config.NEAR_DMA_BAND_PCT
    return {
        "above_200dma": above,
        "trend_score": 100 if above else 0,
        "pct_from_dma": float(pct_from),
        "near": bool(near),
    }


# ---------------------------------------------------------------------------
# 3.4  Sector breadth
# ---------------------------------------------------------------------------
def breadth_signal(pct_above: float) -> str:
    if pct_above >= config.BREADTH_SIGNAL_THRESHOLDS["strong"]:
        return "Strong"
    if pct_above >= config.BREADTH_SIGNAL_THRESHOLDS["mixed_low"]:
        return "Mixed"
    return "Weak"


def sector_breadth(above_dma_flags: pd.Series, window: int) -> dict:
    """
    breadth_N = (constituents above their N-DMA) / total * 100

    `above_dma_flags` is a boolean Series (one row per constituent stock)
    indicating whether that stock is currently above its N-day DMA.
    """
    valid = above_dma_flags.dropna()
    if valid.empty:
        return {"breadth_pct": None, "signal": None, "n_constituents": 0}
    pct = float(valid.mean() * 100)
    return {"breadth_pct": pct, "signal": breadth_signal(pct), "n_constituents": int(len(valid))}
