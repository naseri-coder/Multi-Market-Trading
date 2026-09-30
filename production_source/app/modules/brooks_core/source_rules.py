"""Source-grounded deterministic Brooks rule primitives.

This module deliberately implements only rules whose machine condition is explicit in the
reviewed source catalog. Qualitative concepts that need engineering thresholds remain blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.modules.market_data.entities import Candle
from app.modules.signal_automation.entities import BrooksRuleEvidence

RuleStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE", "AMBIGUOUS"]


@dataclass(frozen=True, slots=True)
class SourceRuleResult:
    rule_id: str
    status: RuleStatus
    source_pages: tuple[int, ...]
    output: str
    evidence: tuple[tuple[str, str], ...] = ()
    failed_conditions: tuple[str, ...] = ()

    def to_evidence(self) -> BrooksRuleEvidence:
        return BrooksRuleEvidence(
            rule_id=self.rule_id,
            status=self.status,
            source_pages=self.source_pages,
            evidence=self.evidence,
            failed_conditions=self.failed_conditions,
        )


def evaluate_br010_inside_bar(current: Candle, previous: Candle) -> SourceRuleResult:
    """BR-010, source page 16."""
    matched = current.high <= previous.high and current.low >= previous.low
    return SourceRuleResult(
        rule_id="BR-010",
        status="PASS" if matched else "FAIL",
        source_pages=(16,),
        output="inside_bar" if matched else "not_inside_bar",
        evidence=(
            ("current_high", str(current.high)),
            ("current_low", str(current.low)),
            ("previous_high", str(previous.high)),
            ("previous_low", str(previous.low)),
        ),
        failed_conditions=()
        if matched
        else ("current_high <= previous_high AND current_low >= previous_low",),
    )


def evaluate_br011_outside_bar(current: Candle, previous: Candle) -> SourceRuleResult:
    """BR-011, source page 16."""
    matched = current.high >= previous.high and current.low <= previous.low
    return SourceRuleResult(
        rule_id="BR-011",
        status="PASS" if matched else "FAIL",
        source_pages=(16,),
        output="outside_bar" if matched else "not_outside_bar",
        evidence=(
            ("current_high", str(current.high)),
            ("current_low", str(current.low)),
            ("previous_high", str(previous.high)),
            ("previous_low", str(previous.low)),
        ),
        failed_conditions=()
        if matched
        else ("current_high >= previous_high AND current_low <= previous_low",),
    )


def br012_default_ema_length() -> SourceRuleResult:
    """BR-012: source catalog states the default course moving average is EMA 20."""
    return SourceRuleResult(
        rule_id="BR-012",
        status="PASS",
        source_pages=(20,),
        output="ema_length=20",
        evidence=(("ema_length", "20"),),
    )


def evaluate_br015_with_trend(
    *,
    trend_direction: str,
    trade_direction: str,
) -> SourceRuleResult:
    """BR-015, source page 26. Does not infer the trend direction."""
    if trend_direction not in {"LONG", "SHORT"}:
        return SourceRuleResult(
            rule_id="BR-015",
            status="AMBIGUOUS",
            source_pages=(26,),
            output="trend_direction_unresolved",
            failed_conditions=("trend_direction must already be resolved",),
        )
    if trade_direction not in {"LONG", "SHORT"}:
        raise ValueError("trade_direction must be LONG or SHORT")

    with_trend = trade_direction == trend_direction
    return SourceRuleResult(
        rule_id="BR-015",
        status="PASS",
        source_pages=(26,),
        output="WITH_TREND" if with_trend else "COUNTERTREND",
        evidence=(
            ("trend_direction", trend_direction),
            ("trade_direction", trade_direction),
        ),
    )


def evaluate_br017_always_in_from_resolved_trend(
    *,
    trend_state: str,
) -> SourceRuleResult:
    """BR-017, pages 28-29. Does not implement the unresolved flip algorithm."""
    if trend_state == "BULL_TREND":
        output = "ALWAYS_IN_LONG"
    elif trend_state == "BEAR_TREND":
        output = "ALWAYS_IN_SHORT"
    else:
        return SourceRuleResult(
            rule_id="BR-017",
            status="AMBIGUOUS",
            source_pages=(28, 29),
            output="always_in_unresolved",
            failed_conditions=("resolved bull/bear trend state required",),
        )
    return SourceRuleResult(
        rule_id="BR-017",
        status="PASS",
        source_pages=(28, 29),
        output=output,
        evidence=(("trend_state", trend_state),),
    )


def br019_range_breakout_failure_heuristic() -> SourceRuleResult:
    """Store source 80% heuristic as evidence, never calibrated confidence."""
    return SourceRuleResult(
        rule_id="BR-019",
        status="PASS",
        source_pages=(59, 97, 122),
        output="source_heuristic_only",
        evidence=(
            ("source_claim_percent", "80"),
            ("calibrated_probability", "NO"),
        ),
    )


def br020_volume_optional_policy() -> SourceRuleResult:
    return SourceRuleResult(
        rule_id="BR-020",
        status="PASS",
        source_pages=(67, 68, 69),
        output="volume_not_required",
        evidence=(("volume_required", "false"),),
    )


def br027_candlestick_confirmation_guard() -> SourceRuleResult:
    return SourceRuleResult(
        rule_id="BR-027",
        status="PASS",
        source_pages=(116, 117),
        output="pattern_alone_insufficient",
        evidence=(("additional_price_action_required", "true"),),
    )


def br029_market_inertia_heuristic() -> SourceRuleResult:
    return SourceRuleResult(
        rule_id="BR-029",
        status="PASS",
        source_pages=(120,),
        output="source_heuristic_only",
        evidence=(
            ("source_claim_percent", "80"),
            ("calibrated_probability", "NO"),
        ),
    )


def br030_reversal_failure_heuristic() -> SourceRuleResult:
    return SourceRuleResult(
        rule_id="BR-030",
        status="PASS",
        source_pages=(121,),
        output="source_heuristic_only",
        evidence=(
            ("source_claim_percent", "80"),
            ("calibrated_probability", "NO"),
        ),
    )


def br035_indicators_secondary_guard() -> SourceRuleResult:
    return SourceRuleResult(
        rule_id="BR-035",
        status="PASS",
        source_pages=(133, 134, 135),
        output="indicator_divergence_alone_insufficient",
        evidence=(("bars_primary", "true"),),
    )
