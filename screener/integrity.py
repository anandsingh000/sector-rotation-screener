"""
Data-integrity engine (Section 6 of the methodology).

Bad price data silently corrupts every downstream indicator, so before a
stock's prices reach the scoring engine they are:

  1. Cross-checked on RETURNS (not raw levels) against a second source,
     since adjusted vs. official feeds legitimately diverge on raw price
     around corporate actions.
  2. Scanned for isolated one-day spikes that fully reverse the next day
     ("bad ticks") and repaired by interpolation.
  3. Tagged with a quality status: CONFIRMED / PARTIAL / SUSPECT /
     SINGLE-SOURCE, carried through to the UI so nothing is used blindly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def repair_bad_ticks(close: pd.Series, threshold: float = config.BAD_TICK_RETURN_THRESHOLD) -> tuple[pd.Series, int]:
    """
    Detect isolated one-day spikes that reverse the next day and replace
    them with a linear interpolation between their neighbours.

    Returns (repaired_series, number_of_repairs).
    """
    s = close.copy()
    ret = s.pct_change()
    repairs = 0

    # A spike at t: |ret[t]| > threshold AND ret[t+1] moves back the other
    # way by a similar magnitude (i.e. it round-trips), which is the
    # signature of a bad print rather than a genuine, sustained move.
    for i in range(1, len(s) - 1):
        r_today = ret.iloc[i]
        r_next = ret.iloc[i + 1]
        if pd.isna(r_today) or pd.isna(r_next):
            continue
        if abs(r_today) > threshold and np.sign(r_today) == -np.sign(r_next) and abs(r_next) > threshold * 0.6:
            s.iloc[i] = np.nan
            repairs += 1

    if repairs:
        s = s.interpolate(method="linear", limit_direction="both")
    return s, repairs


def reconcile_sources(
    primary_close: pd.Series,
    secondary_close: pd.Series | None,
    return_tolerance: float = 0.01,
) -> str:
    """
    Compare daily returns of two independently-sourced price series.

    Returns one of QUALITY_CONFIRMED / QUALITY_PARTIAL / QUALITY_SUSPECT /
    QUALITY_SINGLE_SOURCE. Raw price levels are never compared directly --
    only returns, since level offsets are expected around dividends/splits
    depending on each feed's adjustment policy.
    """
    if secondary_close is None or secondary_close.empty:
        return config.QUALITY_SINGLE_SOURCE

    a = primary_close.pct_change().dropna()
    b = secondary_close.pct_change().dropna()
    common = a.index.intersection(b.index)
    if len(common) < max(20, int(0.5 * min(len(a), len(b)))):
        return config.QUALITY_PARTIAL

    diff = (a.loc[common] - b.loc[common]).abs()
    mismatch_rate = (diff > return_tolerance).mean()

    if mismatch_rate <= 0.02:
        return config.QUALITY_CONFIRMED
    elif mismatch_rate <= 0.08:
        return config.QUALITY_PARTIAL
    else:
        return config.QUALITY_SUSPECT


def validate_and_clean(
    primary_close: pd.Series,
    secondary_close: pd.Series | None = None,
) -> dict:
    """
    Run the full integrity pipeline on one stock's close-price series.

    Returns a dict: {"close": repaired_series, "quality": status_str,
    "repairs": int}. This is the series that should feed every downstream
    calculation (RRG, RS, DMA, breadth).
    """
    repaired, n_repairs = repair_bad_ticks(primary_close)
    quality = reconcile_sources(repaired, secondary_close)
    return {"close": repaired, "quality": quality, "repairs": n_repairs}
