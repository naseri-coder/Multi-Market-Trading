"""Research-only verification of the current public pretrade risk contract."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.modules.brooks_core.market_context import build_market_context
from app.modules.operations.trade_management import build_trade_management_plan
from app.modules.risk_engine.service import RiskEngineService


def _decimal(value):
    try:
        result = Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ValueError("CURRENT_RISK_METADATA_INVALID") from exc
    if not result.is_finite():
        raise ValueError("CURRENT_RISK_METADATA_INVALID")
    return result


def read_current_risk(candidate, *, assessment=None, need_trade_plan=False):
    """Read one assessment and independently verify public management economics.

    The returned plan is for offline research consumers. This module is not a
    runtime reward engine and does not infer an objective for an open runner.
    """
    lifecycle = getattr(candidate, "target_plan_lifecycle", None)
    snapshot = getattr(candidate, "snapshot", None)
    if lifecycle is None or snapshot is None:
        raise ValueError("CURRENT_RISK_CONTEXT_REQUIRED")
    direction = candidate.direction
    entry, stop = _decimal(candidate.entry_price), _decimal(candidate.stop_loss)
    raw_targets = tuple(candidate.targets)
    sign = Decimal(1) if direction == "LONG" else Decimal(-1)
    if (
        direction not in {"LONG", "SHORT"}
        or entry <= 0
        or stop <= 0
        or sign * (entry - stop) <= 0
        or not raw_targets
        or any(sign * (_decimal(price) - entry) <= 0 for price in raw_targets)
    ):
        raise ValueError("CURRENT_RISK_INVALID_GEOMETRY")
    if lifecycle.direction != direction or not lifecycle.plan_id or not lifecycle.state:
        raise ValueError("CURRENT_RISK_CONTEXT_REQUIRED")
    risk = assessment if assessment is not None else RiskEngineService().evaluate(candidate)
    try:
        breakdown = risk.metadata["risk_semantic_breakdown"]
        reward = breakdown["plan_reward"]
        plan_rr = _decimal(breakdown["plan_rr"])
        if (
            breakdown["risk_semantic_model"] != "PLAN_WEIGHTED_PRETRADE"
            or reward["mode"] != "PLAN_WEIGHTED_PRETRADE"
        ):
            raise ValueError("CURRENT_RISK_CONTEXT_REQUIRED")
        context = build_market_context(snapshot)
        reversal = getattr(candidate, "reversal_outcome_context", None)
        if reversal is not None and reversal.state != "PENDING_REVERSAL_OUTCOME":
            reversal = None
        targets = tuple(
            SimpleNamespace(target_number=i, target_price=_decimal(price), status="PENDING")
            for i, price in enumerate(raw_targets, 1)
        )
        plan = build_trade_management_plan(
            direction=direction,
            entry_price=entry,
            initial_stop_loss=stop,
            targets=targets,
            market_regime=context.regime,
            rule_ids=tuple(candidate.rule_ids),
            context_metadata={"channel_quality": context.channel_quality},
            reversal_outcome_context=reversal,
        )
        initial_risk = abs(entry - stop)
        contributions = reward["target_contributions"]
        geometry = len(contributions) == len(targets)
        allocations = True
        contribution_sum = Decimal(0)
        for target, row in zip(targets, contributions, strict=True):
            target_r = sign * (target.target_price - entry) / initial_risk
            fraction = plan.fraction_for_target(target.target_number)
            geometry &= (
                row["target_number"] == target.target_number
                and _decimal(row["target_price"]) == target.target_price
                and _decimal(row["target_r"]) == target_r
            )
            allocations &= (
                0 <= fraction <= 1
                and _decimal(row["allocation_fraction"]) == fraction
                and _decimal(row["weighted_target_r"]) == fraction * target_r
            )
            contribution_sum += fraction * target_r
        runner_zero = (
            reward["runner_policy"] == "UNDEFINED_OBJECTIVE_ZERO_CONSERVATIVE"
            and reward["runner_objective"] is None
            and reward["runner_r"] == "0"
            and reward["weighted_runner_r"] == "0"
        )
        score = sum(
            (_decimal(breakdown[key]) for key in
             ("rr_points", "geometry_points", "structural_points")),
            Decimal(0),
        )
        score = min(max(score, Decimal(0)), Decimal(100)).quantize(Decimal("0.01"))
        invariants = {
            "full_initial_risk_match": (
                _decimal(reward["initial_risk"]) == initial_risk == plan.initial_risk
                and _decimal(reward["entry"]) == entry
                and _decimal(reward["initial_stop"]) == stop
            ),
            "target_geometry_match": geometry,
            "public_plan_allocations_match": (
                allocations
                and 0 <= plan.runner_fraction <= 1
                and sum((f for _, f in plan.target_exit_fractions), Decimal(0))
                + plan.runner_fraction == 1
                and _decimal(reward["runner_fraction"]) == plan.runner_fraction
                and reward["tm_context_class"] == plan.context_class
            ),
            "weighted_contribution_sum_match": (
                contribution_sum + _decimal(reward["weighted_runner_r"])
                == plan_rr == _decimal(reward["plan_rr"])
            ),
            "runner_zero_conservative": runner_zero,
            "typed_context_match": (
                reward["target_plan_id"] == lifecycle.plan_id
                and reward["target_plan_state"] == lifecycle.state
            ),
            "risk_score_decomposition_match": (
                score == _decimal(breakdown["total_risk_score"])
                == _decimal(risk.risk_score)
            ),
        }
    except (KeyError, TypeError, AttributeError, ArithmeticError) as exc:
        raise ValueError("CURRENT_RISK_METADATA_INVALID") from exc
    if not runner_zero:
        raise ValueError("CURRENT_RISK_RUNNER_POLICY_MISMATCH")
    if not all(invariants.values()):
        raise ValueError("CURRENT_RISK_PLAN_MISMATCH")
    return {
        "assessment": risk,
        "breakdown": breakdown,
        "plan_breakdown": reward,
        "plan_rr": plan_rr,
        "trade_management_plan": plan if need_trade_plan else None,
        "invariants": invariants,
    }
