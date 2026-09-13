"""
Central configuration for the Sector Rotation Screener.

Every constant here comes directly from the methodology document
(Sector Rotation Screener | Methodology & Logic). Change values here,
not inside the calculation modules, so the engine stays auditable.
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Timeframes  (Section 5 of the methodology)
# W = RRG smoothing window, L = momentum look-back, on resampled bars.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TimeframeSpec:
    label: str
    resample_rule: str   # pandas offset alias used to build bars
    W: int                # smoothing window (in bars)
    L: int                # momentum look-back (in bars)
    min_bars_required: int  # below this we mark the timeframe N/A


TIMEFRAMES: dict[str, TimeframeSpec] = {
    "weekly":      TimeframeSpec("Weekly",      "W-FRI", 14, 52, 90),
    "monthly":     TimeframeSpec("Monthly",     "ME",    10, 12, 40),
    "quarterly":   TimeframeSpec("Quarterly",   "QE",     4,  4, 16),
    "semi_annual": TimeframeSpec("Semi-annual", "2QE",    3,  2,  8),
    "annual":      TimeframeSpec("Annual",      "YE",     2,  1,  5),
}

DEFAULT_TIMEFRAME = "weekly"

# ---------------------------------------------------------------------------
# Relative Strength (Layer 2) look-backs + weights.
# The doc specifies 4 look-backs weighted 0.15 / 0.25 / 0.30 / 0.30 (recent
# weighted more) but does not name the exact windows. 1M / 3M / 6M / 12M
# trading-day windows are used here as the common convention for Indian
# equity screeners -- change RS_LOOKBACK_DAYS if you intend something else.
# ---------------------------------------------------------------------------
RS_LOOKBACK_DAYS: dict[str, int] = {
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "12M": 252,
}
RS_WEIGHTS: dict[str, float] = {
    "1M": 0.15,
    "3M": 0.25,
    "6M": 0.30,
    "12M": 0.30,
}

# ---------------------------------------------------------------------------
# Layer 3 -- absolute trend filter
# ---------------------------------------------------------------------------
TREND_DMA_WINDOW = 200
NEAR_DMA_BAND_PCT = 2.0  # within +/- this % of the 200-DMA is "near"

# ---------------------------------------------------------------------------
# Layer 4 -- sector breadth
# ---------------------------------------------------------------------------
BREADTH_WINDOWS = (50, 200)
BREADTH_SIGNAL_THRESHOLDS = {"strong": 70, "mixed_low": 40}  # >=70 Strong, 40-69 Mixed, <40 Weak

# ---------------------------------------------------------------------------
# Composite Rotation Score weights  (Section 4)
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "rrg": 0.25,
    "rs_percentile": 0.35,
    "trend": 0.20,
    "breadth_200": 0.20,
}

NEUTRAL_FALLBACK_SCORE = 50  # used when a component can't be computed

# RRG quadrant + direction -> RRG_score  (Section 4)
RRG_SCORE_MAP = {
    ("Leading", "accelerating"): 100,
    ("Improving", "accelerating"): 80,
    ("Leading", "decelerating"): 70,
    ("Weakening", "accelerating"): 50,
    ("Improving", "decelerating"): 40,
    ("Weakening", "decelerating"): 30,
    ("Lagging", "accelerating"): 20,
    ("Lagging", "decelerating"): 10,
}

# ---------------------------------------------------------------------------
# Universe / benchmark
# ---------------------------------------------------------------------------
DEFAULT_BENCHMARK = "^CRSLDX"       # NIFTY 500 (Yahoo Finance symbol)
BENCHMARK_CHOICES = {
    "NIFTY 500": "^CRSLDX",
    "NIFTY 50": "^NSEI",
    "NIFTY MIDCAP 150": "NIFTYMIDCAP150.NS",
}

HISTORY_YEARS = 7  # Section 2: ~7 years of EOD history per stock

NIFTY500_LIST_PATH = "data/nifty500_list.csv"

# Data-integrity quality statuses (Section 6)
QUALITY_CONFIRMED = "CONFIRMED"
QUALITY_PARTIAL = "PARTIAL"
QUALITY_SUSPECT = "SUSPECT"
QUALITY_SINGLE_SOURCE = "SINGLE-SOURCE"

# Bad-tick repair: a one-day return beyond this magnitude that fully reverses
# the next day is treated as a spike and interpolated over.
BAD_TICK_RETURN_THRESHOLD = 0.20
