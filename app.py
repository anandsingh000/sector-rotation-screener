"""
Sector Rotation Screener -- Streamlit dashboard.

Run locally:      streamlit run app.py
Deploy free:       push this repo to GitHub, then deploy at
                    https://share.streamlit.io (Streamlit Community Cloud)
                    pointing at app.py.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from screener import config, data, fundamentals, narrative, pipeline, ta

st.set_page_config(page_title="Sector Rotation Screener", layout="wide", page_icon="\U0001F4CA")

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.title("Sector Rotation Screener")
st.sidebar.caption("RRG + Relative Strength + 200-DMA Trend + Sector Breadth")

benchmark_label = st.sidebar.selectbox("Benchmark", list(config.BENCHMARK_CHOICES.keys()), index=0)
benchmark_symbol = config.BENCHMARK_CHOICES[benchmark_label]

timeframe_key = st.sidebar.selectbox(
    "Timeframe",
    list(config.TIMEFRAMES.keys()),
    format_func=lambda k: config.TIMEFRAMES[k].label,
    index=list(config.TIMEFRAMES.keys()).index(config.DEFAULT_TIMEFRAME),
)

universe_path = st.sidebar.text_input("Universe CSV path", value=config.NIFTY500_LIST_PATH)

run_clicked = st.sidebar.button("\U0001F504 Run / refresh screen", type="primary", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Educational use only — not investment advice. Data is EOD and may lag by a "
    "trading day. Do your own due diligence; consider a SEBI-registered adviser."
)


# ---------------------------------------------------------------------------
# Cached data fetch (expensive network calls)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)  # 6h cache
def _load_universe(path: str) -> pd.DataFrame:
    return data.load_universe(path)


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _fetch_prices(symbols: tuple[str, ...], years: int) -> pd.DataFrame:
    return data.fetch_close_prices(list(symbols), years=years)


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _fetch_benchmark(symbol: str, years: int) -> pd.Series:
    return data.fetch_benchmark_close(symbol, years=years)


@st.cache_data(show_spinner=False, ttl=60 * 30)  # 30 min cache -- user changes this a lot
def _fetch_ohlc_cached(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return data.fetch_ohlc(symbol, period=period, interval=interval)


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _fetch_fundamentals_cached(symbol: str) -> dict:
    return fundamentals.fetch_fundamentals(symbol)


def render_rrg_chart(stocks: pd.DataFrame, sector_filter: str | None):
    df = stocks.dropna(subset=["rs_ratio", "rs_momentum"])
    if sector_filter and sector_filter != "All sectors":
        df = df[df["sector"] == sector_filter]
    if df.empty:
        st.info("No stocks with a computable RRG position for this timeframe/filter yet.")
        return

    fig = go.Figure()
    fig.add_shape(type="rect", x0=100, x1=df["rs_ratio"].max() + 2, y0=100, y1=df["rs_momentum"].max() + 2,
                  fillcolor="rgba(0,180,0,0.06)", line_width=0)
    fig.add_shape(type="rect", x0=df["rs_ratio"].min() - 2, x1=100, y0=100, y1=df["rs_momentum"].max() + 2,
                  fillcolor="rgba(0,120,255,0.06)", line_width=0)
    fig.add_shape(type="rect", x0=100, x1=df["rs_ratio"].max() + 2, y0=df["rs_momentum"].min() - 2, y1=100,
                  fillcolor="rgba(255,180,0,0.06)", line_width=0)
    fig.add_shape(type="rect", x0=df["rs_ratio"].min() - 2, x1=100, y0=df["rs_momentum"].min() - 2, y1=100,
                  fillcolor="rgba(255,0,0,0.06)", line_width=0)
    fig.add_hline(y=100, line_dash="dot", line_color="gray")
    fig.add_vline(x=100, line_dash="dot", line_color="gray")

    fig.add_trace(go.Scatter(
        x=df["rs_ratio"], y=df["rs_momentum"], mode="markers+text",
        text=df["symbol"], textposition="top center", textfont=dict(size=9),
        marker=dict(size=9, color=df["rotation_score"], colorscale="RdYlGn", showscale=True,
                    colorbar=dict(title="Score")),
        hovertext=df.apply(lambda r: f"{r['symbol']} ({r['sector']})<br>Score: {r['rotation_score']:.1f}"
                                      f"<br>Quadrant: {r['quadrant']} / {r['direction']}", axis=1),
        hoverinfo="text",
    ))
    fig.update_layout(
        xaxis_title="RS-Ratio", yaxis_title="RS-Momentum",
        height=560, margin=dict(l=10, r=10, t=30, b=10),
        annotations=[
            dict(x=0.98, y=0.98, xref="paper", yref="paper", text="Leading", showarrow=False, font=dict(color="green")),
            dict(x=0.02, y=0.98, xref="paper", yref="paper", text="Improving", showarrow=False, font=dict(color="blue")),
            dict(x=0.98, y=0.02, xref="paper", yref="paper", text="Weakening", showarrow=False, font=dict(color="orange")),
            dict(x=0.02, y=0.02, xref="paper", yref="paper", text="Lagging", showarrow=False, font=dict(color="red")),
        ],
    )
    st.plotly_chart(fig, use_container_width=True)


def quality_badge(q: str) -> str:
    return {
        config.QUALITY_CONFIRMED: "\U0001F7E2 CONFIRMED",
        config.QUALITY_PARTIAL: "\U0001F7E1 PARTIAL",
        config.QUALITY_SUSPECT: "\U0001F534 SUSPECT",
        config.QUALITY_SINGLE_SOURCE: "\u26AA SINGLE-SOURCE",
    }.get(q, q)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.title("\U0001F4CA Sector Rotation Screener")
st.caption(f"NSE universe • {config.TIMEFRAMES[timeframe_key].label} RRG • Benchmark: {benchmark_label} "
           f"• As of {dt.date.today().isoformat()}")

if "results" not in st.session_state:
    st.session_state.results = None

if run_clicked or st.session_state.results is None:
    try:
        universe = _load_universe(universe_path)
    except Exception as e:
        st.error(f"Couldn't load universe file: {e}")
        st.stop()

    progress = st.progress(0.0, text="Fetching prices...")

    def cb(done, total, *_):
        progress.progress(done / total, text=f"Fetching prices... {done}/{total}")

    with st.spinner("Downloading benchmark history..."):
        benchmark_close = _fetch_benchmark(benchmark_symbol, config.HISTORY_YEARS)

    symbols = tuple(universe["symbol"].tolist())
    close_wide = _fetch_prices(symbols, config.HISTORY_YEARS)
    progress.progress(1.0, text="Scoring...")

    results = pipeline.run_screen(universe, close_wide, benchmark_close, timeframe_key)
    progress.empty()
    st.session_state.results = results
    st.session_state.last_run = dt.datetime.now()

results = st.session_state.results
if results is None:
    st.info("Click **Run / refresh screen** in the sidebar to fetch data and compute scores.")
    st.stop()

stocks, sectors = results["stocks"], results["sectors"]
st.caption(f"Last computed: {st.session_state.get('last_run')}")

all_symbols = sorted(stocks["symbol"].dropna().unique().tolist())
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = all_symbols[0] if all_symbols else None
    st.session_state._last_table_pick = st.session_state.selected_symbol
    st.session_state._last_chart_pick = st.session_state.selected_symbol
    st.session_state._last_ta_pick = st.session_state.selected_symbol
if "draw_reset" not in st.session_state:
    st.session_state.draw_reset = 0


def _get_selection_rows(event) -> list[int]:
    """Handle both attribute-style and dict-style selection event shapes."""
    try:
        return list(event.selection["rows"])
    except Exception:
        pass
    try:
        return list(event.selection.rows)
    except Exception:
        return []


tab_stocks, tab_sectors, tab_rrg, tab_chart, tab_ta_fa, tab_about = st.tabs(
    [
        "\U0001F4C8 Stock Rankings",
        "\U0001F3E2 Sector Breadth",
        "\U0001F300 RRG Chart",
        "\U0001F4C9 Chart & Drawing",
        "\U0001F52C Technical + Fundamental",
        "\u2139\uFE0F Methodology",
    ]
)

with tab_stocks:
    col1, col2, col3 = st.columns([2, 2, 2])
    sector_options = ["All sectors"] + sorted(stocks["sector"].dropna().unique().tolist())
    sector_pick = col1.selectbox("Filter by sector", sector_options)
    quadrant_pick = col2.multiselect("Filter by quadrant", ["Leading", "Improving", "Weakening", "Lagging"])
    min_score = col3.slider("Minimum rotation score", 0, 100, 0)

    view = stocks.copy()
    if sector_pick != "All sectors":
        view = view[view["sector"] == sector_pick]
    if quadrant_pick:
        view = view[view["quadrant"].isin(quadrant_pick)]
    view = view[view["rotation_score"] >= min_score]

    view["quality_display"] = view["quality"].map(quality_badge)
    display_cols = {
        "symbol": "Symbol", "name": "Name", "sector": "Sector",
        "rotation_score": "Score", "quadrant": "Quadrant", "direction": "Direction",
        "rs_ratio": "RS-Ratio", "rs_momentum": "RS-Mom",
        "rs_percentile_universe": "RS %ile (univ.)",
        "above_200dma": "Above 200DMA", "pct_from_200dma": "% from 200DMA",
        "quality_display": "Data quality",
    }
    view = view.reset_index(drop=True)
    st.caption("\U0001F449 Kisi bhi row par click karo — us stock ka chart 'Chart & Drawing' tab mein aur uska "
               "technical/fundamental analysis 'Technical + Fundamental' tab mein khul jayega.")
    select_event = st.dataframe(
        view[list(display_cols.keys())].rename(columns=display_cols).style.format({
            "Score": "{:.1f}", "RS-Ratio": "{:.2f}", "RS-Mom": "{:.2f}",
            "RS %ile (univ.)": "{:.1f}", "% from 200DMA": "{:.2f}%",
        }, na_rep="—"),
        use_container_width=True, height=560,
        on_select="rerun", selection_mode="single-row", key="rankings_table",
    )
    selected_rows = _get_selection_rows(select_event)
    if selected_rows:
        picked_symbol = view.iloc[selected_rows[0]]["symbol"]
        if picked_symbol != st.session_state.get("_last_table_pick"):
            # A genuinely NEW row was clicked (not just the same selection
            # persisting across an unrelated rerun) -- push it to all three
            # tabs' shared state so they all jump to it together.
            st.session_state._last_table_pick = picked_symbol
            st.session_state._last_chart_pick = picked_symbol
            st.session_state._last_ta_pick = picked_symbol
            st.session_state.selected_symbol = picked_symbol
            st.session_state.chart_symbol_pick = picked_symbol
            st.session_state.ta_symbol_pick = picked_symbol
        st.success(f"Selected: **{picked_symbol}** — 'Chart & Drawing' aur 'Technical + Fundamental' tabs par khud-ba-khud khul jayega.")

    st.download_button("Download full results (CSV)", stocks.to_csv(index=False), "rotation_scores.csv", "text/csv")

with tab_sectors:
    st.subheader("Sector breadth (% of constituents above their DMA)")
    sec_display = sectors.rename(columns={
        "sector": "Sector", "n_constituents": "# Stocks",
        "breadth_50_pct": "Breadth 50-DMA %", "breadth_50_signal": "50-DMA Signal",
        "breadth_200_pct": "Breadth 200-DMA %", "breadth_200_signal": "200-DMA Signal",
    })
    st.dataframe(
        sec_display.style.format({"Breadth 50-DMA %": "{:.1f}", "Breadth 200-DMA %": "{:.1f}"}, na_rep="—"),
        use_container_width=True, height=520,
    )

with tab_rrg:
    st.subheader(f"RRG — {config.TIMEFRAMES[timeframe_key].label} rotation")
    sector_pick_rrg = st.selectbox("Sector filter", ["All sectors"] + sorted(stocks["sector"].dropna().unique().tolist()), key="rrg_sector")
    render_rrg_chart(stocks, sector_pick_rrg)

with tab_chart:
    st.subheader("\U0001F4C9 Stock Chart & Drawing Panel")
    st.caption("Yahan timeframe (period + interval) poori tarah aapke control mein hai — screener ke sidebar "
               "timeframe se independent.")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    default_idx = all_symbols.index(st.session_state.selected_symbol) if st.session_state.selected_symbol in all_symbols else 0
    chart_symbol = c1.selectbox("Stock", all_symbols, index=default_idx, key="chart_symbol_pick")
    chart_period = c2.selectbox("Period", data.CHART_PERIODS, index=data.CHART_PERIODS.index("1y"), key="chart_period_pick")
    chart_interval_label = c3.selectbox("Interval", list(data.CHART_INTERVALS.keys()), index=0, key="chart_interval_pick")
    chart_interval = data.CHART_INTERVALS[chart_interval_label]
    if c4.button("\U0001F9F9 Clear drawings", use_container_width=True):
        st.session_state.draw_reset += 1

    if chart_symbol != st.session_state.get("_last_chart_pick"):
        # User manually changed the stock right here in this tab -- sync
        # the other two tabs to match, same as a table click would.
        st.session_state._last_chart_pick = chart_symbol
        st.session_state._last_ta_pick = chart_symbol
        st.session_state._last_table_pick = chart_symbol
        st.session_state.selected_symbol = chart_symbol
        st.session_state.ta_symbol_pick = chart_symbol

    with st.spinner(f"Loading {chart_symbol} chart..."):
        ohlc = _fetch_ohlc_cached(chart_symbol, chart_period, chart_interval)

    if ohlc.empty:
        st.warning("Chart data load nahi ho saka — symbol check karein ya thodi der baad try karein.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=ohlc.index, open=ohlc["Open"], high=ohlc["High"], low=ohlc["Low"], close=ohlc["Close"],
            name=chart_symbol, increasing_line_color="#0E7C61", decreasing_line_color="#c0392b",
        ))
        for w, color in [(50, "#f39c12"), (200, "#8e44ad")]:
            if len(ohlc) > w:
                sma = ohlc["Close"].rolling(w).mean()
                fig.add_trace(go.Scatter(x=ohlc.index, y=sma, mode="lines", name=f"SMA {w}",
                                          line=dict(width=1.3, color=color)))
        fig.update_layout(
            height=600, margin=dict(l=10, r=10, t=30, b=10),
            xaxis_rangeslider_visible=False,
            dragmode="pan",
            newshape=dict(line_color="#e63946", line_width=2, fillcolor="rgba(230,57,70,0.15)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        plot_config = {
            "scrollZoom": True,
            "displaylogo": False,
            "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "drawcircle", "eraseshape"],
        }
        st.plotly_chart(
            fig, use_container_width=True, config=plot_config,
            key=f"chart_{chart_symbol}_{chart_period}_{chart_interval}_{st.session_state.draw_reset}",
        )
        st.caption(
            "\u270F\uFE0F Chart ke top-right modebar mein line / open-path / rectangle / circle draw tools aur "
            "eraser milenge — apna analysis khud mark kar sakte ho (trendlines, support/resistance zones, "
            "patterns waghera). Yeh drawings sirf is session ke liye hain — 'Clear drawings' button se reset "
            "kar sakte ho, aur symbol/period/interval badalne par bhi apne aap clear ho jayengi."
        )

        if "Volume" in ohlc.columns:
            vol_fig = go.Figure(go.Bar(x=ohlc.index, y=ohlc["Volume"], marker_color="#457b9d"))
            vol_fig.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Volume")
            st.plotly_chart(vol_fig, use_container_width=True, config={"displaylogo": False})

with tab_ta_fa:
    st.subheader("\U0001F52C Technical + Fundamental Analysis (Hinglish)")
    default_idx2 = all_symbols.index(st.session_state.selected_symbol) if st.session_state.selected_symbol in all_symbols else 0
    ta_symbol = st.selectbox("Stock chunein", all_symbols, index=default_idx2, key="ta_symbol_pick")

    if ta_symbol != st.session_state.get("_last_ta_pick"):
        # Manually changed here -- sync table + chart tab to match.
        st.session_state._last_ta_pick = ta_symbol
        st.session_state._last_chart_pick = ta_symbol
        st.session_state._last_table_pick = ta_symbol
        st.session_state.selected_symbol = ta_symbol
        st.session_state.chart_symbol_pick = ta_symbol

    with st.spinner("Data fetch ho raha hai..."):
        ohlc_ta = _fetch_ohlc_cached(ta_symbol, "1y", "1d")
        fund_data = _fetch_fundamentals_cached(ta_symbol)

    row_match = stocks[stocks["symbol"] == ta_symbol]
    row = row_match.iloc[0] if not row_match.empty else None

    if ohlc_ta.empty or "Close" not in ohlc_ta.columns or row is None:
        st.warning("Is stock ke liye chart data uplabdh nahi hai, is liye technical analysis nahi ban paayega.")
    else:
        close_ta = ohlc_ta["Close"].dropna()
        rsi_series = ta.rsi(close_ta)
        rsi_val = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else None
        macd_df = ta.macd(close_ta)
        macd_lbl = ta.macd_state(macd_df)
        range52 = ta.fifty_two_week_range(close_ta)

        trend_dict = {"above_200dma": row["above_200dma"], "pct_from_dma": row["pct_from_200dma"]}
        rrg_dict = {"quadrant": row["quadrant"], "direction": row["direction"]}

        tech_text = narrative.build_technical_narrative(
            ta_symbol, row["last_close"], trend_dict, rrg_dict, row["rotation_score"],
            rsi_val, ta.rsi_zone(rsi_val), macd_lbl, range52,
        )
        st.markdown(tech_text)

    st.markdown("---")
    fund_text = narrative.build_fundamental_narrative(ta_symbol, fund_data)
    st.markdown(fund_text)

with tab_about:
    st.markdown(
        """
### How the score is built
`rotation_score = 0.25×RRG_score + 0.35×RS_percentile + 0.20×trend_score + 0.20×breadth_200`

| Layer | What it checks |
|---|---|
| **RRG** | Is the stock outperforming the benchmark, and is that outperformance improving? |
| **RS ranking** | A hard, comparable 0–100 percentile of excess return across the universe |
| **200-DMA trend** | Is the stock actually in a long-term uptrend (not just "leading in a downtrend")? |
| **Sector breadth** | Is the sector's move broad-based, or one stock carrying it? |

**Limitations:** this is a screener, not a predictor. It describes what looks strong *now* —
it ignores valuation, fundamentals, news, liquidity, position sizing and taxes, and momentum
can reverse sharply. Not investment advice; consider a SEBI-registered investment adviser.
        """
    )
