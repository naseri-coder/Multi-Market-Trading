"""Risk-normalized SHADOW Scale-In runtime.

This is intentionally separate from real Signal/TM state.  It seeds one
hypothetical position from a fully-approved natural candidate and evaluates a
later fully-approved same-direction candidate as at most one v1 add.

ENGINEERING_POLICY: shadow uses a normalized 1R budget, allocates 50% of that
budget to the initial hypothetical lot, and permits at most one add.  No
exchange quantity or order is implied.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .accounting import PositionLedger
from .entities import EntryFill, PositionState
from .policy import ScaleInPolicyContext
from .shadow import ShadowScaleInEvaluator, ShadowScaleInResult

SHADOW_VERSION = "brooks-scale-in-shadow-v1-normalized-risk"
NORMALIZED_RISK_BUDGET = Decimal("1")
INITIAL_RISK_ALLOCATION = Decimal("0.5")
MAX_SCALE_ADDS = 1
QTY_STEP = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class ShadowPositionState:
    ledger: PositionLedger
    source_signal_id: str
    scale_adds: int
    last_setup_type: str


@dataclass(frozen=True, slots=True)
class ShadowRuntimeDecision:
    action: str
    position: ShadowPositionState
    evaluation: ShadowScaleInResult | None
    metadata: dict[str, object]


def _unit_qty(entry: Decimal, stop: Decimal, allocation: Decimal) -> Decimal:
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("shadow seed requires positive stop distance")
    raw = allocation / distance
    return (raw / QTY_STEP).to_integral_value(rounding="ROUND_DOWN") * QTY_STEP


def seed_shadow_position(candidate: Any, *, now: datetime | None = None) -> ShadowPositionState:
    entry = Decimal(str(candidate.entry_price))
    stop = Decimal(str(candidate.stop_loss))
    qty = _unit_qty(entry, stop, INITIAL_RISK_ALLOCATION)
    if qty <= 0:
        raise ValueError("normalized shadow quantity rounded to zero")
    position_id = f"shadow:{candidate.source_signal_id}"
    ledger = PositionLedger(
        position_id=position_id, direction=str(candidate.direction),
        initial_trade_risk_budget=NORMALIZED_RISK_BUDGET, executable_stop=stop,
    )
    ledger.apply_entry_fill(EntryFill(
        execution_key=f"{position_id}:seed", position_id=position_id,
        direction=str(candidate.direction), filled_qty=qty, requested_qty=qty,
        fill_price=entry, fill_time=now or datetime.now(UTC),
        entry_reason="SHADOW_INITIAL_FULL_PIPELINE_APPROVAL", scale_sequence_number=0,
        structural_stop_at_entry=stop, risk_budget_at_entry=NORMALIZED_RISK_BUDGET,
        fill_source="SHADOW", setup_type=str(candidate.setup_type),
        rule_id="ENG-SCALE-SHADOW-SEED-50PCT-RISK",
        metadata={"shadow_version": SHADOW_VERSION, "tm_plan": getattr(candidate, "tm_plan", None)},
    ))
    return ShadowPositionState(ledger, str(candidate.source_signal_id), 0, str(candidate.setup_type))


def evaluate_shadow_candidate(*, state: ShadowPositionState, candidate: Any,
                              market_regime: str, always_in: str,
                              full_pipeline_approved: bool, premise_valid: bool = True) -> ShadowRuntimeDecision:
    if state.ledger.state is not PositionState.OPEN:
        return ShadowRuntimeDecision("NO_ACTION", state, None, {"reason":"POSITION_NOT_OPEN"})
    if state.scale_adds >= MAX_SCALE_ADDS:
        return ShadowRuntimeDecision("NO_ACTION", state, None, {"reason":"MAX_SCALE_ADDS_REACHED"})
    if str(candidate.direction) != state.ledger.direction:
        return ShadowRuntimeDecision("NO_ACTION", state, None, {"reason":"DIRECTION_MISMATCH"})
    expected = Decimal(str(candidate.entry_price))
    mark_pnl = state.ledger.unrealized_pnl(expected)
    desired = state.ledger.lots[0].filled_qty  # equal-size add; source-supported common practice, not universal.
    ctx = ScaleInPolicyContext(
        direction=state.ledger.direction, position_state=state.ledger.state,
        always_in=always_in, market_regime=market_regime,
        setup_type=str(candidate.setup_type), full_pipeline_approved=full_pipeline_approved,
        premise_valid=premise_valid, unrealized_pnl=mark_pnl,
    )
    evaluation = ShadowScaleInEvaluator().evaluate(
        position=state.ledger, context=ctx, desired_qty=desired,
        expected_price=expected, structural_stop=Decimal(str(candidate.stop_loss)),
        qty_step=QTY_STEP,
    )
    action = "SHADOW_SCALE_APPROVED" if evaluation.approved else "SHADOW_SCALE_REJECTED"
    # Deliberately no fill application here: this is a decision shadow, not a simulated execution.
    return ShadowRuntimeDecision(action, state, evaluation, {
        "shadow_version": SHADOW_VERSION,
        "desired_qty": str(desired),
        "normalized_initial_trade_risk_budget": str(NORMALIZED_RISK_BUDGET),
        "initial_risk_allocation": str(INITIAL_RISK_ALLOCATION),
    })
