"""
Fundamental data fetch (per-stock, on-demand -- not part of the bulk
screen). Uses yfinance's `Ticker.info`, which wraps Yahoo Finance's
quote-summary endpoint. Coverage/completeness for NSE names varies
stock-to-stock, so every field is fetched defensively and the caller
must handle `None` values -- never assume a field is present.
"""

from __future__ import annotations

import time

import yfinance as yf

_FIELDS = [
    "longName", "sector", "industry", "marketCap", "currentPrice",
    "trailingPE", "forwardPE", "priceToBook", "returnOnEquity",
    "debtToEquity", "profitMargins", "grossMargins", "operatingMargins",
    "dividendYield", "earningsGrowth", "revenueGrowth", "beta",
    "totalRevenue", "totalDebt", "freeCashflow",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "recommendationKey", "targetMeanPrice", "numberOfAnalystOpinions",
    "bookValue", "trailingEps", "forwardEps",
]


def fetch_fundamentals(nse_symbol: str) -> dict:
    """
    Returns a dict of the fields in `_FIELDS` (missing ones as None), or
    an empty dict if the ticker/info could not be fetched at all.

    Retried a couple of times since Yahoo's quote-summary endpoint (what
    `Ticker.info`/`get_info()` wraps) can intermittently rate-limit or
    return an empty payload; also falls back to the older `.info`
    property for yfinance versions that don't have `get_info()`.
    """
    yahoo_symbol = f"{nse_symbol}.NS"
    for attempt in range(2):
        try:
            ticker = yf.Ticker(yahoo_symbol)
            info = ticker.get_info() if hasattr(ticker, "get_info") else ticker.info
        except Exception:
            info = None
        if info:
            return {field: info.get(field) for field in _FIELDS}
        time.sleep(1.0)
    return {}
