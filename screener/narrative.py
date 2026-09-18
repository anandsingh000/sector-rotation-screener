"""
Builds the Hinglish narrative shown in the "Technical + Fundamental"
tab. Pure text formatting -- all the actual numbers come from
`indicators.py` (core rotation layers), `ta.py` (RSI/MACD/52-wk range)
and `fundamentals.py` (yfinance Ticker.info).
"""

from __future__ import annotations


def _fmt(value, suffix: str = "", digits: int = 2, none_text: str = "uplabdh nahi") -> str:
    if value is None:
        return none_text
    try:
        if value != value:  # NaN check without importing pandas/numpy here
            return none_text
    except TypeError:
        pass
    return f"{value:.{digits}f}{suffix}"


def _fmt_cr(value) -> str:
    """Format a rupee value (in raw units) as Rs. crore, 2 decimals."""
    if value is None:
        return "uplabdh nahi"
    try:
        return f"₹{value / 1e7:,.0f} Cr"
    except (TypeError, ZeroDivisionError):
        return "uplabdh nahi"


def build_technical_narrative(
    symbol: str,
    last_close: float | None,
    trend: dict,
    rrg_state: dict,
    rotation_score: float | None,
    rsi_value: float | None,
    rsi_zone_label: str,
    macd_state_label: str,
    range_52w: dict,
) -> str:
    above = trend.get("above_200dma")
    pct_from_dma = trend.get("pct_from_dma")
    quadrant = rrg_state.get("quadrant")
    direction = rrg_state.get("direction")

    trend_line = "uplabdh nahi (kaafi price history nahi hai)"
    if above is not None:
        trend_word = "upar" if above else "neeche"
        trend_meaning = "long-term uptrend" if above else "long-term downtrend / weakness"
        trend_line = (
            f"Stock apne 200-din ke moving average (200-DMA) se **{trend_word}** trade kar raha hai "
            f"({_fmt(pct_from_dma, '%')} distance), jo ke ek **{trend_meaning}** ka signal hai."
        )

    quadrant_meaning = {
        "Leading": "index se zyada strong hai aur woh strength abhi bhi badh rahi hai",
        "Improving": "abhi index se peeche hai, lekin momentum sudhar raha hai — turning-up phase",
        "Weakening": "index se strong to hai, lekin momentum kam ho raha hai — savdhaan rehna chahiye",
        "Lagging": "index se kamzor hai aur weakness continue ho rahi hai",
    }.get(quadrant, "abhi calculate nahi ho paaya (kaafi data nahi)")

    rsi_meaning = {
        "overbought": "yeh **overbought** zone hai — short-term mein pullback/consolidation aa sakta hai",
        "oversold": "yeh **oversold** zone hai — short-term mein bounce-back ka chance ban sakta hai",
        "neutral": "yeh **neutral** zone hai — koi extreme signal nahi",
        "unknown": "abhi calculate nahi ho paaya",
    }.get(rsi_zone_label, "abhi calculate nahi ho paaya")

    macd_meaning = {
        "bullish": "MACD line signal line ke **upar** hai — short-term momentum bullish hai",
        "bearish": "MACD line signal line ke **neeche** hai — short-term momentum bearish hai",
        "unknown": "abhi calculate nahi ho paaya",
    }.get(macd_state_label, "abhi calculate nahi ho paaya")

    range_line = "uplabdh nahi"
    if range_52w.get("high") is not None:
        range_line = (
            f"52-hafton ka high ₹{range_52w['high']:.2f} hai aur low ₹{range_52w['low']:.2f} hai. "
            f"Current price high se {_fmt(range_52w['pct_from_high'], '%')} aur low se "
            f"{_fmt(range_52w['pct_from_low'], '%')} door hai."
        )

    score_line = ""
    if rotation_score is not None:
        score_line = f"\n- **Overall Rotation Score:** {rotation_score:.1f}/100 (jitna zyada, utna zyada 'strong setup' — 0-100 scale)"

    return f"""
### {symbol} — Technical Analysis (Hinglish)

- **Trend (200-DMA):** {trend_line}
- **RRG Quadrant:** Stock abhi **{quadrant or 'N/A'}** quadrant mein hai, direction **{direction or 'N/A'}** — matlab {quadrant_meaning}.
- **RSI (14):** {_fmt(rsi_value, digits=1)} — {rsi_meaning}
- **MACD:** {macd_meaning}
- **52-week range:** {range_line}{score_line}

> Yeh sab short-term / medium-term indicators hain — inhe akela istemal na karein, price action aur volume ke saath cross-check zaroor karein.
""".strip()


def build_fundamental_narrative(symbol: str, f: dict) -> str:
    if not f or all(v is None for v in f.values()):
        return (
            f"### {symbol} — Fundamental Analysis (Hinglish)\n\n"
            "Fundamental data is waqt fetch nahi ho saka (Yahoo Finance par is ticker ke liye "
            "coverage available nahi hai, ya network issue hai). Thodi der baad phir try karein."
        )

    name = f.get("longName") or symbol
    sector = f.get("sector") or "uplabdh nahi"
    industry = f.get("industry") or "uplabdh nahi"

    pe = _fmt(f.get("trailingPE"))
    fwd_pe = _fmt(f.get("forwardPE"))
    pb = _fmt(f.get("priceToBook"))
    roe = _fmt((f.get("returnOnEquity") or 0) * 100 if f.get("returnOnEquity") is not None else None, "%")
    de = _fmt(f.get("debtToEquity"))
    margin = _fmt((f.get("profitMargins") or 0) * 100 if f.get("profitMargins") is not None else None, "%")
    div_yield = _fmt((f.get("dividendYield") or 0) * 100 if f.get("dividendYield") is not None else None, "%")
    beta = _fmt(f.get("beta"))
    mcap = _fmt_cr(f.get("marketCap"))
    revenue = _fmt_cr(f.get("totalRevenue"))
    eps = _fmt(f.get("trailingEps"))
    rec = f.get("recommendationKey") or "uplabdh nahi"
    target = f.get("targetMeanPrice")
    analysts = f.get("numberOfAnalystOpinions")

    pe_comment = ""
    try:
        pe_val = float(f.get("trailingPE"))
        if pe_val < 15:
            pe_comment = "yeh apeksha-krit sasta (low) P/E hai"
        elif pe_val < 30:
            pe_comment = "yeh ek moderate P/E hai"
        else:
            pe_comment = "yeh ek high P/E hai — market growth expectations price mein already factor kar chuka hai"
    except (TypeError, ValueError):
        pe_comment = "P/E comment ke liye data uplabdh nahi"

    analyst_line = ""
    if target and analysts:
        analyst_line = f"\n- **Analyst view:** {analysts} analysts track kar rahe hain, average target price ₹{target:.2f} hai, recommendation: **{rec}**."

    return f"""
### {symbol} — Fundamental Analysis (Hinglish)

**{name}** ({sector} / {industry})

- **Market Cap:** {mcap}
- **P/E Ratio (trailing / forward):** {pe} / {fwd_pe} — {pe_comment}
- **P/B Ratio:** {pb} (book value ke muqable stock kitna mehnga trade ho raha hai)
- **ROE (Return on Equity):** {roe} (company apne equity capital par kitna return bana rahi hai)
- **Debt-to-Equity:** {de} (jitna zyada, utna zyada leverage/risk)
- **Net Profit Margin:** {margin}
- **Dividend Yield:** {div_yield}
- **Beta:** {beta} (1 se zyada matlab index se zyada volatile)
- **Revenue (TTM):** {revenue}
- **EPS (trailing):** {eps}{analyst_line}

> Yeh data Yahoo Finance se aata hai aur NSE stocks ke liye coverage/accuracy vary kar sakti hai — company ke official annual report/quarterly results se hamesha cross-verify karein.
""".strip()
