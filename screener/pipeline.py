"""
Orchestration layer: wires data -> integrity -> indicators -> scorer
into the two output tables the UI needs:

    - stock-level results  (one row per stock)
    - sector-level breadth (one row per sector)

This is the only module that needs to know about *all* the others.
"""

from __future__ import annotations

import pandas as pd

from . import config, data, indicators, integrity, scorer


def _dma_flags(close: pd.Series, window: int) -> bool | None:
    dma = close.rolling(window).mean()
    if len(close.dropna()) < window or pd.isna(dma.iloc[-1]):
        return None
    return bool(close.iloc[-1] > dma.iloc[-1])


def run_screen(
    universe: pd.DataFrame,
    close_wide: pd.DataFrame,
    benchmark_close: pd.Series,
    timeframe_key: str = config.DEFAULT_TIMEFRAME,
    progress_cb=None,
) -> dict[str, pd.DataFrame]:
    """
    Run the full four-layer screen for every stock in `universe`.

    Parameters
    ----------
    universe : DataFrame with columns symbol, name, sector
    close_wide : DataFrame, daily adjusted close, columns = symbol
    benchmark_close : daily adjusted close of the chosen benchmark
    timeframe_key : one of config.TIMEFRAMES keys

    Returns
    -------
    {"stocks": DataFrame, "sectors": DataFrame}
    """
    tf = config.TIMEFRAMES[timeframe_key]
    rows = []
    above50_daily: dict[str, bool | None] = {}
    above200_daily: dict[str, bool | None] = {}

    n = len(universe)
    for idx, u_row in enumerate(universe.itertuples(index=False)):
        symbol, name, sector = u_row.symbol, u_row.name, u_row.sector

        if symbol not in close_wide.columns:
            rows.append(_empty_row(symbol, name, sector, "NO DATA"))
            if progress_cb:
                progress_cb(idx + 1, n, symbol)
            continue

        raw_close = close_wide[symbol].dropna()
        if raw_close.empty:
            rows.append(_empty_row(symbol, name, sector, "NO DATA"))
            if progress_cb:
                progress_cb(idx + 1, n, symbol)
            continue

        # --- Section 6: data integrity -------------------------------------------------
        secondary = data.fetch_secondary_close(symbol)
        cleaned = integrity.validate_and_clean(raw_close, secondary)
        close = cleaned["close"]
        quality = cleaned["quality"]

        # --- daily-frequency layers (trend + breadth use daily bars regardless of TF) --
        trend = indicators.trend_filter(close, config.TREND_DMA_WINDOW)
        above50_daily[symbol] = _dma_flags(close, 50)
        above200_daily[symbol] = _dma_flags(close, 200)

        # --- Layer 2: RS ranking (daily-return based, timeframe-independent) ----------
        crs = indicators.composite_rs(close, benchmark_close)

        # --- Layer 1: RRG on the timeframe's resampled bars ----------------------------
        bars_needed = tf.min_bars_required
        stock_bars = data.resample_close(close, tf.resample_rule)
        bench_bars = data.resample_close(benchmark_close, tf.resample_rule)

        if len(stock_bars) >= bars_needed and len(bench_bars) >= bars_needed:
            rrg_df = indicators.compute_rrg(stock_bars, bench_bars, tf.W, tf.L)
            rrg_state = indicators.latest_rrg_state(rrg_df)
            rrg_score = indicators.rrg_score_from_state(rrg_state)
            tf_available = True
        else:
            rrg_state = {"rs_ratio": None, "rs_momentum": None, "quadrant": None, "direction": None}
            rrg_score = config.NEUTRAL_FALLBACK_SCORE
            tf_available = False

        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "quality": quality,
                "timeframe_available": tf_available,
                "quadrant": rrg_state["quadrant"],
                "direction": rrg_state["direction"],
                "rs_ratio": rrg_state["rs_ratio"],
                "rs_momentum": rrg_state["rs_momentum"],
                "rrg_score": rrg_score,
                "composite_rs_raw": crs,
                "above_200dma": trend["above_200dma"],
                "pct_from_200dma": trend["pct_from_dma"],
                "near_200dma": trend["near"],
                "trend_score": trend["trend_score"],
                "last_close": float(close.iloc[-1]),
            }
        )
        if progress_cb:
            progress_cb(idx + 1, n, symbol)

    stocks = pd.DataFrame(rows)

    # RS percentile is rank-across-universe (or, in the sector drill-down view,
    # rank-within-sector) -- Section 3.2.
    stocks["rs_percentile_universe"] = indicators.rs_percentile_rank(stocks.set_index("symbol")["composite_rs_raw"]).values
    stocks["rs_percentile_sector"] = (
        stocks.groupby("sector")["composite_rs_raw"]
        .transform(lambda s: indicators.rs_percentile_rank(s))
    )

    # --- Layer 4: sector breadth (computed across ALL stocks in each sector) ----------
    sector_rows = []
    for sector, grp in universe.groupby("sector"):
        syms = grp["symbol"].tolist()
        flags50 = pd.Series({s: above50_daily.get(s) for s in syms})
        flags200 = pd.Series({s: above200_daily.get(s) for s in syms})
        b50 = indicators.sector_breadth(flags50, 50)
        b200 = indicators.sector_breadth(flags200, 200)
        sector_rows.append(
            {
                "sector": sector,
                "n_constituents": len(syms),
                "breadth_50_pct": b50["breadth_pct"],
                "breadth_50_signal": b50["signal"],
                "breadth_200_pct": b200["breadth_pct"],
                "breadth_200_signal": b200["signal"],
            }
        )
    sectors = pd.DataFrame(sector_rows).sort_values("breadth_200_pct", ascending=False, na_position="last")

    # --- attach sector breadth_200 onto each stock row, then compute final score -------
    breadth_lookup = sectors.set_index("sector")["breadth_200_pct"].to_dict()
    stocks["sector_breadth_200"] = stocks["sector"].map(breadth_lookup)

    stocks["rotation_score"] = stocks.apply(
        lambda r: scorer.composite_rotation_score(
            r["rrg_score"], r["rs_percentile_universe"], r["trend_score"], r["sector_breadth_200"]
        ),
        axis=1,
    )

    stocks = stocks.sort_values("rotation_score", ascending=False).reset_index(drop=True)
    return {"stocks": stocks, "sectors": sectors}


def _empty_row(symbol: str, name: str, sector: str, quality: str) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "quality": quality,
        "timeframe_available": False,
        "quadrant": None,
        "direction": None,
        "rs_ratio": None,
        "rs_momentum": None,
        "rrg_score": config.NEUTRAL_FALLBACK_SCORE,
        "composite_rs_raw": None,
        "above_200dma": None,
        "pct_from_200dma": None,
        "near_200dma": None,
        "trend_score": config.NEUTRAL_FALLBACK_SCORE,
        "last_close": None,
    }
