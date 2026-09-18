"""
Data layer: universe loading + EOD price fetching + timeframe resampling.

Prices come from Yahoo Finance (via yfinance) using NSE tickers suffixed
with ".NS". This is the free option that works out-of-the-box on any
machine with internet access -- no broker/API key needed.

A `fetch_secondary_close()` stub is provided for Section 6's two-source
cross-check. By default it returns None (no secondary source configured),
in which case every stock is tagged SINGLE-SOURCE rather than silently
claiming a validation that didn't happen. Wire in a second provider there
(e.g. an NSE-official CSV/API client, or another vendor) if you want real
CONFIRMED/SUSPECT reconciliation.
"""

from __future__ import annotations

import os
import time

import pandas as pd
import yfinance as yf

from . import config


def load_universe(path: str = config.NIFTY500_LIST_PATH) -> pd.DataFrame:
    """
    Load the stock universe: columns `symbol` (NSE code, no suffix),
    `name`, `sector` (NSE macro-sector / Industry classification).

    Refresh this file from NSE's published Nifty 500 constituent list
    (https://www.nseindia.com/market-data/live-equity-market -> Nifty 500
    -> "Download CSV") whenever the index is reconstituted. The sample
    shipped in this repo covers a representative slice across sectors so
    the app runs immediately -- replace it with the full official list for
    real use.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"symbol", "name", "sector"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")
    df["symbol"] = df["symbol"].str.strip().str.upper()
    df["sector"] = df["sector"].str.strip()
    return df.drop_duplicates(subset="symbol").reset_index(drop=True)


def _to_yahoo_symbol(nse_symbol: str) -> str:
    return f"{nse_symbol}.NS"


def resolve_yahoo_symbol(symbol: str, exchange: str | None = None, yahoo_symbol: str | None = None) -> str:
    """
    Work out the Yahoo Finance ticker for a universe row.

    - If the row already gives an explicit `yahoo_symbol`, use it verbatim
      (needed for BSE: Yahoo identifies BSE-listed stocks by their numeric
      BSE *scrip code* + ".BO", e.g. "500325.BO" for Reliance on BSE --
      not the trading symbol -- so there's no reliable way to derive it
      from the symbol alone).
    - Else if exchange == "BSE", assume `symbol` IS already the scrip code
      and append ".BO".
    - Else default to NSE's ".NS" suffix (existing behaviour, unchanged).
    """
    if yahoo_symbol is not None and pd.notna(yahoo_symbol) and str(yahoo_symbol).strip():
        return str(yahoo_symbol).strip()
    if exchange and str(exchange).strip().upper() == "BSE":
        return f"{str(symbol).strip()}.BO"
    return _to_yahoo_symbol(symbol)


def load_market_universe(path: str) -> pd.DataFrame:
    """
    Load a broader NSE+BSE universe for the Market Scanner tab. Same
    required columns as `load_universe` (symbol, name, sector) plus two
    optional ones:

      - exchange: "NSE" or "BSE" (defaults to "NSE" if omitted)
      - yahoo_symbol: explicit Yahoo ticker override (see
        `resolve_yahoo_symbol` -- effectively required for real BSE rows
        since Yahoo keys BSE stocks by scrip code, not trading symbol)

    Adds a `yahoo_symbol` column (resolved) to the returned DataFrame so
    downstream code never has to re-derive it.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"symbol", "name", "sector"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")

    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["sector"] = df["sector"].astype(str).str.strip()
    if "exchange" not in df.columns:
        df["exchange"] = "NSE"
    else:
        df["exchange"] = df["exchange"].fillna("NSE").astype(str).str.strip().str.upper()
    if "yahoo_symbol" not in df.columns:
        df["yahoo_symbol"] = None

    df["yahoo_symbol"] = df.apply(
        lambda r: resolve_yahoo_symbol(r["symbol"], r["exchange"], r.get("yahoo_symbol")), axis=1
    )
    return df.drop_duplicates(subset=["yahoo_symbol"]).reset_index(drop=True)


def _extract_close_series(data: pd.DataFrame, ticker: str) -> pd.Series | None:
    """
    Pull the 'Close' column for `ticker` out of whatever shape yfinance
    handed back. Different yfinance versions (and single- vs multi-ticker
    downloads) return either a plain Index of fields, or a MultiIndex as
    either (Ticker, Field) or (Field, Ticker) -- this normalises all of
    them to a single 1-D Series so the rest of the code never has to care.
    """
    if data is None or data.empty:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(data.columns.get_level_values(0))
        if ticker in level0:
            sub = data[ticker]
            col = sub["Close"] if "Close" in sub.columns else None
        elif "Close" in level0:
            sub = data["Close"]
            col = sub[ticker] if ticker in sub.columns else None
        else:
            col = None
    else:
        col = data["Close"] if "Close" in data.columns else None

    if col is None:
        return None
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    return col


def fetch_close_prices(
    symbols: list[str],
    years: int = config.HISTORY_YEARS,
    batch_size: int = 50,
    pause_sec: float = 1.0,
    progress_cb=None,
) -> pd.DataFrame:
    """
    Download adjusted daily close prices for a list of NSE symbols.

    Returns a wide DataFrame: index = date, columns = symbol (no .NS
    suffix), values = adjusted close. Batches requests to stay well within
    Yahoo Finance's rate limits.
    """
    period = f"{years}y"
    yahoo_symbols = [_to_yahoo_symbol(s) for s in symbols]
    frames = []

    for i in range(0, len(yahoo_symbols), batch_size):
        batch = yahoo_symbols[i : i + batch_size]
        data = yf.download(
            batch,
            period=period,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
        )
        cols = {}
        for t in batch:
            s = _extract_close_series(data, t)
            if s is not None:
                cols[t] = s
        close = pd.DataFrame(cols)
        frames.append(close)

        if progress_cb:
            progress_cb(min(i + batch_size, len(yahoo_symbols)), len(yahoo_symbols))
        if i + batch_size < len(yahoo_symbols):
            time.sleep(pause_sec)

    wide = pd.concat(frames, axis=1)
    wide.columns = [c.replace(".NS", "") for c in wide.columns]
    return wide.sort_index()


def fetch_benchmark_close(yahoo_symbol: str, years: int = config.HISTORY_YEARS) -> pd.Series:
    data = yf.download(yahoo_symbol, period=f"{years}y", interval="1d", auto_adjust=True, progress=False)
    close = _extract_close_series(data, yahoo_symbol)
    if close is None:
        raise ValueError(
            f"Could not fetch Close prices for benchmark '{yahoo_symbol}'. "
            "Check the symbol is correct and Yahoo Finance is reachable."
        )
    return close.rename("benchmark")


def fetch_secondary_close(nse_symbol: str) -> pd.Series | None:
    """
    Stub for a second, independent price feed used in Section 6's
    reconciliation. Returns None by default (no secondary source wired
    in), which the integrity engine reports honestly as SINGLE-SOURCE.

    To enable real CONFIRMED/SUSPECT reconciliation, implement a fetch
    here against a second provider and return an adjusted close Series
    indexed by date.
    """
    return None


def resample_close(close: pd.Series, rule: str) -> pd.Series:
    """
    Resample a daily close series to the bar frequency a given timeframe
    needs (Section 5), taking the last observed price in each bar.
    """
    return close.resample(rule).last().dropna()


# ---------------------------------------------------------------------------
# Single-stock OHLCV fetch -- used by the per-stock Chart & Drawing tab and
# the Technical/Fundamental tab, where the user picks the symbol and
# timeframe manually (independent of the bulk screen above).
# ---------------------------------------------------------------------------
def _normalize_single_ticker_ohlcv(raw: pd.DataFrame, yahoo_symbol: str) -> pd.DataFrame:
    """Flatten whatever column shape yfinance returned into plain Open/High/Low/Close/Volume."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        level1 = set(raw.columns.get_level_values(1))
        if yahoo_symbol in level0:
            df = raw[yahoo_symbol].copy()
        elif yahoo_symbol in level1:
            df = raw.xs(yahoo_symbol, axis=1, level=1).copy()
        else:
            # only one ticker was requested but yfinance still kept a
            # MultiIndex -- just take the first ticker's block
            first = raw.columns.get_level_values(0)[0]
            df = raw[first].copy()
    else:
        df = raw.copy()

    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    return df[keep].dropna(how="all")


# Interval/period choices exposed in the UI -> yfinance interval codes.
CHART_INTERVALS = {
    "Daily": "1d",
    "Weekly": "1wk",
    "Monthly": "1mo",
}
CHART_PERIODS = ["3mo", "6mo", "1y", "2y", "5y", "max"]


def fetch_ohlc(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    Fetch OHLCV for a single NSE symbol at a user-chosen period/interval.
    Independent of the bulk `fetch_close_prices` used for the screen --
    called on demand when the user opens the chart for one stock.

    Yahoo Finance occasionally throws (rate limit, transient network
    blip, an HTML error page where JSON was expected) rather than just
    returning empty -- retried a couple of times here so a single hiccup
    doesn't surface as "no data" to the user.
    """
    yahoo_symbol = _to_yahoo_symbol(symbol)
    last_df = pd.DataFrame()
    for attempt in range(2):
        try:
            raw = yf.download(
                yahoo_symbol, period=period, interval=interval,
                auto_adjust=True, progress=False,
            )
            last_df = _normalize_single_ticker_ohlcv(raw, yahoo_symbol)
            if not last_df.empty:
                return last_df
        except Exception:
            pass
        if attempt == 0:
            time.sleep(1.0)
    return last_df


# ---------------------------------------------------------------------------
# Bulk OHLCV fetch (Close + High + Low + Volume) -- used by the Market
# Scanner tab, which needs more than just Close (52-week/1-week high-low,
# volume-surge detection) for a large list of symbols at once.
# ---------------------------------------------------------------------------
def fetch_ohlcv_bulk(
    yahoo_symbols: list[str],
    period: str = "1y",
    batch_size: int = 50,
    pause_sec: float = 1.0,
    progress_cb=None,
) -> dict[str, pd.DataFrame]:
    """
    Download Open/High/Low/Close/Volume for many tickers (already-resolved
    Yahoo symbols, e.g. "TCS.NS" or "500325.BO") in batches.

    Returns {yahoo_symbol: OHLCV DataFrame}. Symbols that failed to
    download are simply absent from the result (caller should treat a
    missing key the same as "no data").
    """
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(yahoo_symbols), batch_size):
        batch = yahoo_symbols[i : i + batch_size]
        try:
            raw = yf.download(
                batch, period=period, interval="1d",
                auto_adjust=True, group_by="ticker", progress=False, threads=True,
            )
        except Exception:
            raw = None

        if raw is not None and not raw.empty:
            for t in batch:
                df = _normalize_single_ticker_ohlcv(raw, t)
                if not df.empty:
                    out[t] = df

        if progress_cb:
            progress_cb(min(i + batch_size, len(yahoo_symbols)), len(yahoo_symbols))
        if i + batch_size < len(yahoo_symbols):
            time.sleep(pause_sec)

    return out
