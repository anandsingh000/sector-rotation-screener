"""
Composite Rotation Score (Section 4):

    rotation_score = 0.25*RRG_score + 0.35*RS_percentile
                    + 0.20*trend_score + 0.20*breadth_200

If a component can't be computed, it falls back to a neutral 50 so the
score stays defined (documented in the methodology as worth remembering
when judging stocks with short histories).
"""

from __future__ import annotations

from . import config


def composite_rotation_score(
    rrg_score: float | None,
    rs_percentile: float | None,
    trend_score: float | None,
    breadth_200: float | None,
) -> float:
    rrg_score = config.NEUTRAL_FALLBACK_SCORE if rrg_score is None else rrg_score
    rs_percentile = config.NEUTRAL_FALLBACK_SCORE if rs_percentile is None else rs_percentile
    trend_score = config.NEUTRAL_FALLBACK_SCORE if trend_score is None else trend_score
    breadth_200 = config.NEUTRAL_FALLBACK_SCORE if breadth_200 is None else breadth_200

    w = config.SCORE_WEIGHTS
    return (
        w["rrg"] * rrg_score
        + w["rs_percentile"] * rs_percentile
        + w["trend"] * trend_score
        + w["breadth_200"] * breadth_200
    )
