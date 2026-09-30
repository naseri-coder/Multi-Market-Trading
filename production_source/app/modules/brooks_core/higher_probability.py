"""Qualitative Brooks higher-probability filter.

The labels are relative quality bands, not calibrated probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate


class ProbabilityBand(StrEnum):
    HIGHER = "HIGHER"
    NORMAL = "NORMAL"
    LOWER = "LOWER"


@dataclass(frozen=True, slots=True)
class HigherProbabilityAssessment:
    band: ProbabilityBand
    reasons: tuple[str, ...]


def assess_higher_probability(candidate: BrooksPatternCandidate, context, advanced=None):
    reasons: list[str] = []
    regime_direction = {"BULL_TREND": "LONG", "BEAR_TREND": "SHORT"}.get(context.regime)
    if regime_direction and candidate.direction != regime_direction:
        return HigherProbabilityAssessment(
            ProbabilityBand.LOWER,
            ("countertrend_against_resolved_trend",),
        )

    if advanced is not None:
        tight = getattr(advanced, "tight_channel_direction", "UNRESOLVED")
        if tight in {"LONG", "SHORT"} and candidate.direction != tight:
            return HigherProbabilityAssessment(
                ProbabilityBand.LOWER,
                ("countertrend_first_breakout_against_tight_channel",),
            )

    if candidate.family == "FAILED_FAILURE":
        reasons.append("failed_failure_is_second_signal")
    if candidate.setup_type in {"H2_CONFIRMED", "L2_CONFIRMED"}:
        reasons.append("second_entry_with_trend")
    if candidate.setup_type in {"H3_WEDGE_BULL_FLAG_LONG", "L3_WEDGE_BEAR_FLAG_SHORT"}:
        reasons.append("with_trend_three_push_wedge_flag")
    if candidate.setup_type in {"DOUBLE_BOTTOM_PULLBACK_LONG", "DOUBLE_TOP_PULLBACK_SHORT"}:
        reasons.append("double_top_bottom_pullback_is_reliable_breakout_pullback")
    if candidate.setup_type in {"TWENTY_GAP_BAR_LONG", "TWENTY_GAP_BAR_SHORT"}:
        reasons.append("first_ema_touch_after_twenty_gap_with_price_action_trigger")
    if candidate.setup_type in {"SECOND_MA_GAP_BAR_LONG", "SECOND_MA_GAP_BAR_SHORT"}:
        reasons.append("second_ma_gap_attempt_after_failed_first_attempt")
    if "REVERSAL_BAR_FAILURE" in candidate.setup_type:
        reasons.append("failed_countertrend_reversal_with_trend")
    if candidate.setup_type in {"DOUBLE_TOP_BEAR_FLAG_SHORT", "DOUBLE_BOTTOM_BULL_FLAG_LONG"}:
        reasons.append("with_trend_double_top_bottom_flag")
    if candidate.family == "BREAKOUT_PULLBACK":
        reasons.append("with_trend_breakout_pullback")
    if candidate.family == "BREAKOUT" and context.breakout_streak >= 2:
        reasons.append("multi_bar_breakout_follow_through")

    if reasons:
        return HigherProbabilityAssessment(ProbabilityBand.HIGHER, tuple(reasons))
    return HigherProbabilityAssessment(
        ProbabilityBand.NORMAL,
        ("no_source_grounded_probability_upgrade_or_downgrade",),
    )
