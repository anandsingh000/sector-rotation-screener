# Sector Rotation Screener

NSE Nifty 500 screener implementing **RRG + Relative Strength + 200-DMA
Trend + Sector Breadth**, blended into one 0-100 Rotation Score, exactly
as described in `Screener_Methodology.pdf` (Section 4 onward).

> ⚠️ **Educational use only — not investment advice.** Do your own due
> diligence and consider a SEBI-registered investment adviser.

---

## 1. What's in this repo

```
sector-rotation-screener/
├── app.py                     # Streamlit dashboard (entry point)
├── screener/
│   ├── config.py               # every weight/window/threshold from the methodology
│   ├── data.py                 # yfinance price fetching + resampling
│   ├── integrity.py             # Section 6: two-source reconciliation + bad-tick repair
│   ├── indicators.py            # Sections 3.1–3.4: RRG, RS, 200-DMA, breadth
│   ├── scorer.py                # Section 4: composite Rotation Score
│   └── pipeline.py               # wires it all together into result tables
├── data/nifty500_list.csv       # sample universe (symbol, name, sector)
├── requirements.txt
└── .streamlit/config.toml       # theme
```

## 2. Run it on your computer

**Requirements:** Python 3.10+ and internet access (to fetch prices from
Yahoo Finance).

```bash
# 1. clone or unzip this project, then cd into it
cd sector-rotation-screener

# 2. create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. install dependencies
pip install -r requirements.txt

# 4. run the app
streamlit run app.py
```

It opens automatically at `http://localhost:8501`. Pick a benchmark and
timeframe in the sidebar, then click **Run / refresh screen**.

First run downloads ~7 years of daily prices for every symbol in
`data/nifty500_list.csv`, so it takes a couple of minutes depending on
universe size and your connection. Results are cached for 6 hours.

## 3. Using the full official Nifty 500 list

The shipped `data/nifty500_list.csv` is a **representative sample** (a
few stocks per sector) so the app runs immediately. For the real, full
universe:

1. Go to the NSE website → Market Data → Indices → **Nifty 500** →
   download the constituent CSV.
2. Reshape/rename it to exactly three columns: `symbol,name,sector`
   (`symbol` = NSE trading symbol without `.NS`, `sector` = the
   "Industry" column NSE publishes).
3. Replace `data/nifty500_list.csv`, or point the sidebar's "Universe
   CSV path" at your new file.

## 4. Put it on GitHub

```bash
cd sector-rotation-screener
git init
git add .
git commit -m "Sector rotation screener"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

(Create the empty repo on github.com first, then run the commands
above with its URL.)

### Easier: use the included batch file (Windows)

`upload_to_github.bat` does all of the above for you. Double-click it and
it will:

1. check Git is installed, and `git init` the folder if needed
2. set the branch to `main`
3. ask for your repo URL the first time (`https://github.com/USER/REPO.git`
   — no angle brackets), and remember it afterwards
4. stage everything, ask for a commit message (blank = a default one)
5. push to GitHub, with a readable error if something fails

Run it again any time you change the code — it skips the setup steps it
already did and just commits + pushes. If your app is deployed on
Streamlit Cloud, it redeploys itself a minute or two after the push.

## 5. Run it from a website (free) — Streamlit Community Cloud

1. Go to **https://share.streamlit.io** and sign in with your GitHub
   account.
2. Click **New app** → pick your repo, branch `main`, main file path
   `app.py`.
3. Click **Deploy**. In a minute or two you'll get a public URL like
   `https://<something>.streamlit.app` that runs this exact app — no
   server of your own needed.
4. Any time you `git push` an update, the deployed app redeploys
   automatically.

That's it — same code, same `requirements.txt`, running locally and on
the web from the same GitHub repo.

### Alternative hosts
If you'd rather not use Streamlit Cloud, the same `app.py` also runs on
**Hugging Face Spaces** (choose the Streamlit SDK) or any VM/container
host (Render, Railway, a plain VPS) via:
```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## 6. Per-stock chart, drawing panel & Hinglish analysis

Click any row in the **Stock Rankings** table to select that stock — it
carries over to two new tabs:

- **📉 Chart & Drawing** — candlestick chart with 50/200-DMA overlay and
  a volume panel. Period and interval are set manually here, independent
  of the screener's own sidebar timeframe. The chart's modebar (top
  right) has line / open-path / rectangle / circle drawing tools and an
  eraser, so you can mark up trendlines, support/resistance zones, etc.,
  directly on the chart. These drawings live only in the browser for
  that session — they reset if you change symbol/period/interval or use
  "Clear drawings".
- **🔬 Technical + Fundamental** — a Hinglish write-up combining the
  rotation-score layers (200-DMA trend, RRG quadrant) with extra
  standard indicators (RSI-14, MACD, 52-week range), plus a fundamentals
  section (P/E, P/B, ROE, debt/equity, margins, dividend yield, analyst
  view) pulled from Yahoo Finance's ticker info. Fundamentals coverage
  for NSE names varies by stock — some fields may show "uplabdh nahi".

Both tabs have a **🔄 Retry data** button. Yahoo Finance occasionally
rate-limits or hiccups on a single request; the app already retries a
few times automatically and evicts any empty result from its cache
rather than serving a stale "no data" for the next 30 minutes, but the
button forces an immediate fresh attempt if you don't want to wait.

## 7. Market Scanner (NSE + BSE)

A separate, broader scan across NSE **and** BSE stocks (independent of
the Nifty 500 rotation screen above). For each stock it shows, for the
whole universe instantly: LTP, 52-week high/low, 1-week high/low, volume
vs its 20-day average (flagging volume surges), RSI(14), and a 20/50-EMA
crossover state. Because cash-flow trend, ROE, ROCE and a valuation label
need a separate Yahoo Finance fundamentals request *per stock*, those are
computed only for the first **N** stocks (the "Fundamentals scan limit"
you set in the tab — raise it if you want more covered, at the cost of a
slower scan and a higher chance of hitting Yahoo's rate limits).

- **Universe file**: `data/full_market_list.csv` — same `symbol, name,
  sector` columns as the main Nifty 500 list, plus `exchange` (`NSE` or
  `BSE`) and `yahoo_symbol`. Yahoo identifies BSE stocks by their numeric
  **BSE scrip code** (e.g. `500325.BO` for Reliance), not the trading
  symbol, so BSE rows need an explicit `yahoo_symbol`; NSE rows can leave
  it blank (`SYMBOL.NS` is derived automatically). The shipped file is a
  small curated demo (the Nifty 500 sample plus ~17 large BSE names) —
  for a real full-market scan, build your own CSV from NSE's and BSE's
  official listed-securities downloads and point the tab's "Universe CSV
  path" at it. A full NSE (~2,000) + BSE (~5,000) scan will take a long
  time for the fundamentals portion given Yahoo's per-stock rate limits —
  scan in batches via the fundamentals-limit control rather than all at
  once.
- **Column filter**: an expander with a tick/untick checkbox per column,
  plus "Select all" / "Clear all".
- **Valuation column** is a deliberately simple heuristic (the stock's
  trailing P/E vs. the *median* P/E of other scanned stocks in its
  sector) — not a DCF or intrinsic-value model. Treat it as a rough first
  filter, not a valuation call.

## 8. Data-integrity notes (Section 6 of the methodology)

- Prices come from Yahoo Finance (`yfinance`), adjusted for
  splits/dividends.
- Bad-tick repair (isolated one-day spikes that reverse the next day)
  runs on every series before it reaches any indicator.
- The methodology calls for cross-checking against a **second**,
  independent source. `screener/data.py::fetch_secondary_close()` is a
  stub for that — by default it returns `None`, so every stock is
  honestly tagged **SINGLE-SOURCE** rather than falsely claiming a
  cross-check that isn't wired up. Plug a second provider (an NSE
  official feed, another vendor's API, etc.) into that function to get
  real CONFIRMED / PARTIAL / SUSPECT statuses.

## 9. Assumptions worth knowing about

The methodology document specifies the RS composite's 4 look-back
weights (0.15 / 0.25 / 0.30 / 0.30) but not the exact look-back windows.
This build uses 1M / 3M / 6M / 12M (trading days: 21/63/126/252), the
common convention for Indian-equity screeners. Change
`RS_LOOKBACK_DAYS` in `screener/config.py` if you intend different
windows — everything downstream picks it up automatically.

## 10. Running the backend regression test

`tests/test_app_backend.py` uses Streamlit's official headless
`AppTest` framework to actually run `app.py` and simulate real widget
interactions (clicking "Run / refresh", switching stocks in the Chart
and Technical+Fundamental tabs back and forth, changing period/interval,
clicking "Clear drawings" / "Retry data") and asserts no exception is
raised at any step. All network calls are swapped for synthetic data
inside the test, so it runs without internet access:

```bash
pip install -r requirements.txt
python tests/test_app_backend.py
```

Run this after making any change to `app.py` — it's what caught the
duplicate-chart-element and clashing-button-key bugs during development,
and it will catch similar regressions before they reach your browser.

## 11. Limitations (from the methodology, Section 8)

- It's a screener, not a predictor — it describes what looks strong
  *now*, momentum can reverse sharply.
- Ignores valuation, fundamentals, news, liquidity, position sizing,
  taxes.
- Universe is today's Nifty 500 membership; data is EOD, may lag a
  trading day.
