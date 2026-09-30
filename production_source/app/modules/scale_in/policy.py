"""Source-grounded Scale-In policy layer.

The policy may propose an add.  It never mutates a position and never overrides
the aggregate risk engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .entities import PositionState, ScaleInCategory

POLICY_VERSION = "brooks-scale-in-policy-v1-shadow-safe"
TREND_REGIMES = frozenset({"TREND", "BULL_TREND", "BEAR_TREND", "STRONG_TREND"})
_ENABLED_V1 = frozenset({
    ScaleInCategory.ADD_TO_WINNER,
    ScaleInCategory.ADD_ON_PULLBACK,
    ScaleInCategory.ADD_AFTER_CONFIRMATION,
})


@dataclass(frozen=True, slots=True)
class ScaleInPolicyContext:
    direction: str
    position_state: PositionState
    always_in: str
    market_regime: str
    setup_type: str
    full_pipeline_approved: bool
    premise_valid: bool
    unrealized_pnl: Decimal


@dataclass(frozen=True, slots=True)
class ScaleInPolicyDecision:
    approved: bool
    category: ScaleInCategory
    rule_id: str
    reason: str
    policy_version: str = POLICY_VERSION


def classify_category(ctx: ScaleInPolicyContext) -> ScaleInCategory:
    setup = ctx.setup_type.upper()
    regime = ctx.market_regime.upper()
    if any(token in setup for token in ("PULLBACK", "H2", "L2", "WEDGE_BULL_FLAG", "WEDGE_BEAR_FLAG")):
        return ScaleInCategory.ADD_ON_PULLBACK
    if ctx.unrealized_pnl > 0 and regime in TREND_REGIMES and "BREAKOUT" in setup:
        return ScaleInCategory.ADD_TO_WINNER
    return ScaleInCategory.ADD_AFTER_CONFIRMATION


def evaluate_policy(ctx: ScaleInPolicyContext, *, category: ScaleInCategory | None = None) -> ScaleInPolicyDecision:
    selected = category or classify_category(ctx)
    rule_id = {
        ScaleInCategory.ADD_TO_WINNER: "BR-SCALE-PRESS-WINNER",
        ScaleInCategory.ADD_ON_PULLBACK: "BR-SCALE-TREND-PULLBACK",
        ScaleInCategory.ADD_AFTER_CONFIRMATION: "BR-SCALE-SECOND-CONFIRMATION",
    }.get(selected, "BR-SCALE-DISABLED-CATEGORY")
    if selected not in _ENABLED_V1:
        return ScaleInPolicyDecision(False, selected, rule_id, "CATEGORY_NOT_ENABLED_V1")
    if ctx.position_state is not PositionState.OPEN:
        return ScaleInPolicyDecision(False, selected, rule_id, "POSITION_NOT_OPEN")
    if not ctx.full_pipeline_approved:
        return ScaleInPolicyDecision(False, selected, rule_id, "FRESH_CANDIDATE_NOT_FULLY_APPROVED")
    if not ctx.premise_valid:
        return ScaleInPolicyDecision(False, selected, rule_id, "ORIGINAL_PREMISE_INVALID")
    if ctx.always_in.upper() != ctx.direction.upper():
        return ScaleInPolicyDecision(False, selected, rule_id, "ALWAYS_IN_MISMATCH")
    if ctx.market_regime.upper() not in TREND_REGIMES:
        return ScaleInPolicyDecision(False, selected, rule_id, "V1_REQUIRES_TREND_CONTEXT")
    if selected is ScaleInCategory.ADD_TO_WINNER and ctx.unrealized_pnl <= 0:
        return ScaleInPolicyDecision(False, selected, rule_id, "POSITION_NOT_WINNING")
    return ScaleInPolicyDecision(True, selected, rule_id, "SOURCE_SUPPORTED_CONTEXT_CONFIRMED")
