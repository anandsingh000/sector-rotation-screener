"""
Sector Rotation Screener -- Streamlit dashboard.

Run locally:      streamlit run app.py
Deploy free:       push this repo to GitHub, then deploy at
                    https://share.streamlit.io (Streamlit Community Cloud)
                    pointing at app.py.
"""

from __future__ import annotations

import datetime as dt
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from screener import config, data, fundamentals, narrative, pipeline, scanner, ta

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


def _fetch_ohlc_resilient(symbol: str, period: str, interval: str, attempts: int = 3) -> pd.DataFrame:
    """
    Yahoo Finance occasionally hiccups (rate limit / transient network
    error) and returns nothing for one call while a nearly-identical call
    a moment later succeeds. A plain @st.cache_data fetch would lock that
    empty result in for the full TTL, so here we retry a few times AND
    evict the cache entry between attempts rather than trusting a single
    empty response.
    """
    df = pd.DataFrame()
    for attempt in range(attempts):
        df = _fetch_ohlc_cached(symbol, period, interval)
        if not df.empty:
            return df
        _fetch_ohlc_cached.clear(symbol, period, interval)
        if attempt < attempts - 1:
            time.sleep(1.5 * (attempt + 1))
    return df


def _fetch_fundamentals_resilient(symbol: str, attempts: int = 3) -> dict:
    info: dict = {}
    for attempt in range(attempts):
        info = _fetch_fundamentals_cached(symbol)
        if info and any(v is not None for v in info.values()):
            return info
        _fetch_fundamentals_cached.clear(symbol)
        if attempt < attempts - 1:
            time.sleep(1.5 * (attempt + 1))
    return info


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _load_market_universe_cached(path: str) -> pd.DataFrame:
    return data.load_market_universe(path)


@st.cache_data(show_spinner=False, ttl=60 * 30)
def _fetch_ohlcv_bulk_cached(yahoo_symbols: tuple[str, ...], period: str) -> dict[str, pd.DataFrame]:
    return data.fetch_ohlcv_bulk(list(yahoo_symbols), period=period)


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
if "draw_reset" not in st.session_state:
    st.session_state.draw_reset = 0

# ---------------------------------------------------------------------------
# Cross-tab symbol sync.
#
# Streamlit forbids writing to st.session_state[some_key] once the widget
# with that key has already rendered *in this run* -- so a later tab (e.g.
# Technical+Fundamental) can never directly poke an earlier tab's widget
# key (e.g. chart_symbol_pick) in the same script pass, no matter the
# order. To stay safe regardless of tab order, any tab that notices the
# user picked a different stock just stages it in `_pending_symbol` and
# triggers a rerun; this block -- which always runs before any widget
# below is instantiated -- is the only place that ever writes the three
# selectbox keys directly.
# ---------------------------------------------------------------------------
pending = st.session_state.pop("_pending_symbol", None)
if pending:
    st.session_state.selected_symbol = pending
    st.session_state.chart_symbol_pick = pending
    st.session_state.ta_symbol_pick = pending


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


tab_stocks, tab_sectors, tab_rrg, tab_chart, tab_ta_fa, tab_scanner, tab_about = st.tabs(
    [
        "\U0001F4C8 Stock Rankings",
        "\U0001F3E2 Sector Breadth",
        "\U0001F300 RRG Chart",
        "\U0001F4C9 Chart & Drawing",
        "\U0001F52C Technical + Fundamental",
        "\U0001F310 Market Scanner",
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
        if picked_symbol != st.session_state.selected_symbol:
            st.session_state._pending_symbol = picked_symbol
            st.rerun()
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

    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
    default_idx = all_symbols.index(st.session_state.selected_symbol) if st.session_state.selected_symbol in all_symbols else 0
    _chart_kwargs = {} if "chart_symbol_pick" in st.session_state else {"index": default_idx}
    chart_symbol = c1.selectbox("Stock", all_symbols, key="chart_symbol_pick", **_chart_kwargs)
    chart_period = c2.selectbox("Period", data.CHART_PERIODS, index=data.CHART_PERIODS.index("1y"), key="chart_period_pick")
    chart_interval_label = c3.selectbox("Interval", list(data.CHART_INTERVALS.keys()), index=0, key="chart_interval_pick")
    chart_interval = data.CHART_INTERVALS[chart_interval_label]
    if c4.button("\U0001F9F9 Clear drawings", use_container_width=True, key="chart_clear_drawings_btn"):
        st.session_state.draw_reset += 1
    if c5.button("\U0001F504 Retry data", use_container_width=True, key="chart_retry_btn"):
        _fetch_ohlc_cached.clear(chart_symbol, chart_period, chart_interval)
        st.rerun()

    if chart_symbol != st.session_state.selected_symbol:
        # User manually changed the stock right here in this tab -- sync
        # the other two tabs to match, same as a table click would.
        st.session_state._pending_symbol = chart_symbol
        st.rerun()

    with st.spinner(f"Loading {chart_symbol} chart..."):
        ohlc = _fetch_ohlc_resilient(chart_symbol, chart_period, chart_interval)

    if ohlc.empty:
        st.warning(
            "Chart data load nahi ho saka. Yeh aksar Yahoo Finance ke temporary rate-limit/network glitch ki "
            "wajah se hota hai — 'Retry data' button dabao ya thodi der (30-60 sec) baad phir try karo. Agar "
            "phir bhi na aaye to symbol/period/interval badal kar dekhein."
        )
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
    col_pick, col_retry = st.columns([4, 1])
    default_idx2 = all_symbols.index(st.session_state.selected_symbol) if st.session_state.selected_symbol in all_symbols else 0
    _ta_kwargs = {} if "ta_symbol_pick" in st.session_state else {"index": default_idx2}
    ta_symbol = col_pick.selectbox("Stock chunein", all_symbols, key="ta_symbol_pick", **_ta_kwargs)
    if col_retry.button("\U0001F504 Retry data", use_container_width=True, key="ta_retry_btn"):
        _fetch_ohlc_cached.clear(ta_symbol, "1y", "1d")
        _fetch_fundamentals_cached.clear(ta_symbol)
        st.rerun()

    if ta_symbol != st.session_state.selected_symbol:
        # Manually changed here -- sync table + chart tab to match.
        st.session_state._pending_symbol = ta_symbol
        st.rerun()

    with st.spinner("Data fetch ho raha hai..."):
        ohlc_ta = _fetch_ohlc_resilient(ta_symbol, "1y", "1d")
        fund_data = _fetch_fundamentals_resilient(ta_symbol)

    row_match = stocks[stocks["symbol"] == ta_symbol]
    row = row_match.iloc[0] if not row_match.empty else None

    if ohlc_ta.empty or "Close" not in ohlc_ta.columns or row is None:
        st.warning(
            "Is stock ke liye chart data uplabdh nahi hai, is liye technical analysis nahi ban paayega. "
            "Yeh aksar Yahoo Finance ke temporary glitch ki wajah se hota hai — upar 'Retry data' button "
            "try karo."
        )
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

with tab_scanner:
    st.subheader("\U0001F310 Market Scanner (NSE + BSE)")
    st.caption(
        "Poori universe scan karta hai: 52-week/1-week high-low, volume activity, RSI, EMA 20/50 crossover — "
        "sabke liye turant. Cash flow trend, ROE, ROCE aur valuation (jo Yahoo Finance se ek-ek stock ke liye "
        "alag fetch karne padte hain) sirf niche diye gaye 'Fundamentals scan limit' tak ke stocks ke liye "
        "compute hote hain, taake poora scan practical waqt mein chal sake."
    )

    sc1, sc2, sc3 = st.columns([2, 1, 1])
    scanner_universe_path = sc1.text_input(
        "Universe CSV path", value="data/full_market_list.csv", key="scanner_universe_path",
        help="symbol, name, sector, exchange (NSE/BSE), yahoo_symbol columns. Full official NSE+BSE lists "
             "replace the shipped demo sample — see README.",
    )
    exchange_pick = sc2.selectbox("Exchange", ["Both", "NSE only", "BSE only"], key="scanner_exchange_pick")
    fundamentals_limit = sc3.number_input(
        "Fundamentals scan limit", min_value=0, max_value=500, value=40, step=10, key="scanner_fund_limit",
        help="Higher = more stocks get Cash Flow/ROE/ROCE/Valuation, but takes longer and risks Yahoo "
             "Finance rate-limits. Price/volume/RSI/EMA columns always cover the FULL universe regardless.",
    )

    run_scan = st.button("\U0001F680 Run Market Scan", type="primary", key="run_scanner_btn")

    if run_scan:
        try:
            scan_universe = _load_market_universe_cached(scanner_universe_path)
        except Exception as e:
            st.error(f"Universe file load nahi ho saki: {e}")
            scan_universe = None

        if scan_universe is not None:
            if exchange_pick == "NSE only":
                scan_universe = scan_universe[scan_universe["exchange"] == "NSE"]
            elif exchange_pick == "BSE only":
                scan_universe = scan_universe[scan_universe["exchange"] == "BSE"]

            yahoo_symbols = tuple(scan_universe["yahoo_symbol"].tolist())
            price_progress = st.progress(0.0, text="Price/volume data fetch ho raha hai...")

            def _price_cb(done, total):
                price_progress.progress(done / max(total, 1), text=f"Price/volume data: {done}/{total} stocks")

            ohlcv_map = data.fetch_ohlcv_bulk(list(yahoo_symbols), period="1y", progress_cb=_price_cb)
            price_progress.empty()

            fund_progress = st.progress(0.0, text="Fundamentals fetch ho raha hai (dheere)...")

            def _fund_cb(done, total):
                fund_progress.progress(done / max(total, 1), text=f"Fundamentals: {done}/{total} stocks")

            scan_result = scanner.run_market_scan(
                scan_universe, ohlcv_map, fundamentals_limit=fundamentals_limit, progress_cb=_fund_cb,
            )
            fund_progress.empty()
            st.session_state.scanner_result = scan_result
            st.session_state.scanner_last_run = dt.datetime.now()

    scan_result = st.session_state.get("scanner_result")
    if scan_result is None:
        st.info("Upar 'Run Market Scan' dabao — universe load hokar scan shuru ho jayega.")
    else:
        n_scanned_fund = int(scan_result["fundamentals_scanned"].sum()) if "fundamentals_scanned" in scan_result else 0
        st.caption(
            f"Last scan: {st.session_state.get('scanner_last_run')} — "
            f"{len(scan_result)} stocks (price data), {n_scanned_fund} scanned for fundamentals."
        )

        # ---- column filter panel ------------------------------------------------
        COLUMN_MAP = {
            "symbol": "Symbol", "name": "Name", "sector": "Sector", "exchange": "Exchange",
            "ltp": "LTP", "52w_high": "52W High", "52w_low": "52W Low",
            "pct_from_52w_high": "% from 52W High", "pct_from_52w_low": "% from 52W Low",
            "1w_high": "1W High", "1w_low": "1W Low",
            "volume_ratio": "Volume vs 20d Avg (x)", "volume_surge": "Volume Surge",
            "cash_flow_trend": "Cash Flow Trend", "roe": "ROE %", "roce": "ROCE %",
            "rsi": "RSI (14)", "ema_state": "EMA 20/50 Crossover", "valuation": "Valuation",
        }
        for key in COLUMN_MAP:
            state_key = f"scancol_{key}"
            if state_key not in st.session_state:
                st.session_state[state_key] = True

        with st.expander("\U0001F527 Filter columns (tick/untick)", expanded=False):
            bcol1, bcol2, _ = st.columns([1, 1, 4])
            if bcol1.button("Select all", key="scancol_select_all"):
                for key in COLUMN_MAP:
                    st.session_state[f"scancol_{key}"] = True
            if bcol2.button("Clear all", key="scancol_clear_all"):
                for key in COLUMN_MAP:
                    st.session_state[f"scancol_{key}"] = False

            grid_cols = st.columns(4)
            for i, (key, label) in enumerate(COLUMN_MAP.items()):
                grid_cols[i % 4].checkbox(label, key=f"scancol_{key}")

        visible_cols = [key for key in COLUMN_MAP if st.session_state.get(f"scancol_{key}", True)]

        # ---- quick sub-filters ---------------------------------------------------
        fcol1, fcol2, fcol3 = st.columns(3)
        only_volume_surge = fcol1.checkbox("Sirf Volume Surge wale stocks", key="scanner_only_surge")
        only_rising_cf = fcol2.checkbox("Sirf Cash Flow Rising wale stocks", key="scanner_only_cf_rising")
        valuation_pick = fcol3.multiselect(
            "Valuation", ["Undervalued", "Fair Value", "Overvalued"], key="scanner_valuation_pick",
        )

        view = scan_result.copy()
        if only_volume_surge:
            view = view[view["volume_surge"] == True]  # noqa: E712
        if only_rising_cf:
            view = view[view["cash_flow_trend"] == "Rising"]
        if valuation_pick:
            view = view[view["valuation"].isin(valuation_pick)]

        if not visible_cols:
            st.warning("Kam az kam ek column select karo dikhane ke liye.")
        else:
            display_df = view[visible_cols].rename(columns=COLUMN_MAP)
            fmt = {}
            for key, label in COLUMN_MAP.items():
                if key not in visible_cols:
                    continue
                if key in ("ltp", "52w_high", "52w_low", "1w_high", "1w_low"):
                    fmt[label] = "{:.2f}"
                elif key in ("pct_from_52w_high", "pct_from_52w_low", "roe", "roce"):
                    fmt[label] = "{:.1f}"
                elif key == "volume_ratio":
                    fmt[label] = "{:.2f}x"
                elif key == "rsi":
                    fmt[label] = "{:.1f}"
            st.dataframe(display_df.style.format(fmt, na_rep="—"), use_container_width=True, height=560)
            st.download_button(
                "Download scan results (CSV)", view.to_csv(index=False),
                "market_scan.csv", "text/csv", key="scanner_download_btn",
            )

        st.caption(
            "\u26A0\uFE0F Valuation column ek simplified heuristic hai (sector ke andar P/E comparison par "
            "based) — DCF ya intrinsic-value model nahi hai. Investment advice nahi hai; khud research karein "
            "ya SEBI-registered adviser se baat karein."
        )

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
