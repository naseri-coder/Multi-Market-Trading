"""Adapter from Phase-3 expectation/risk contracts into Trader's Equation inputs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.modules.brooks_core_v3.domain.models import RiskPlan, SetupCandidate

from .entities import TraderEquationInput


def from_phase3_contracts(
    *,
    setup: SetupCandidate,
    risk_plan: RiskPlan,
    probability_success: Decimal | None,
    probability_basis: str | None,
    evaluated_at: datetime,
    target_index: int = 0,
) -> TraderEquationInput:
    if risk_plan.market_snapshot_id != setup.market_snapshot_id:
        raise ValueError("risk plan snapshot must match setup candidate")
    if risk_plan.setup_candidate_id != setup.candidate_id:
        raise ValueError("risk plan must belong to setup candidate")
    if target_index < 0:
        raise ValueError("target_index cannot be negative")

    entry = risk_plan.entry_price
    stop = risk_plan.stop_price
    target = risk_plan.targets[target_index] if target_index < len(risk_plan.targets) else None

    if entry is not None and stop is not None:
        if setup.direction.value == "LONG" and stop >= entry:
            raise ValueError("LONG risk plan stop must be below entry")
        if setup.direction.value == "SHORT" and stop <= entry:
            raise ValueError("SHORT risk plan stop must be above entry")
    if entry is not None and target is not None:
        if setup.direction.value == "LONG" and target <= entry:
            raise ValueError("LONG reward target must be above entry")
        if setup.direction.value == "SHORT" and target >= entry:
            raise ValueError("SHORT reward target must be below entry")

    risk = None if entry is None or stop is None else abs(entry - stop)
    reward = None if entry is None or target is None else abs(target - entry)

    return TraderEquationInput(
        market_snapshot_id=setup.market_snapshot_id,
        setup_candidate_id=setup.candidate_id,
        probability_success=probability_success,
        risk=risk,
        reward=reward,
        probability_basis=probability_basis,
        risk_basis=("phase3_risk_plan_entry_to_stop" if risk is not None else None),
        reward_basis=(
            f"phase3_risk_plan_entry_to_target_{target_index + 1}"
            if reward is not None
            else None
        ),
        evaluated_at=evaluated_at,
    )
