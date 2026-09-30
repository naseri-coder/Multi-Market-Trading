"""Pure shadow Scale-In evaluation.

This service evaluates source policy, aggregate risk, hypothetical average entry
and stop without placing an order or mutating the supplied position ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .accounting import PositionLedger
from .entities import ScaleInCategory
from .policy import ScaleInPolicyContext, ScaleInPolicyDecision, evaluate_policy
from .risk import AggregateRiskDecision, assess_scale_in


@dataclass(frozen=True, slots=True)
class ShadowScaleInResult:
    policy: ScaleInPolicyDecision
    risk: AggregateRiskDecision | None
    hypothetical_avg_entry: Decimal | None
    hypothetical_open_qty: Decimal
    hypothetical_stop: Decimal
    approved: bool
    reason: str


class ShadowScaleInEvaluator:
    def evaluate(
        self,
        *,
        position: PositionLedger,
        context: ScaleInPolicyContext,
        desired_qty: Decimal,
        expected_price: Decimal,
        structural_stop: Decimal,
        qty_step: Decimal,
        min_qty: Decimal = Decimal("0"),
        min_notional: Decimal = Decimal("0"),
        risk_buffer_per_unit: Decimal = Decimal("0"),
        category: ScaleInCategory | None = None,
    ) -> ShadowScaleInResult:
        before = (
            position.open_qty,
            position.avg_entry,
            position.executable_stop,
            position.realized_net_pnl,
            tuple((lot.execution_key, lot.open_qty) for lot in position.lots),
        )
        policy = evaluate_policy(context, category=category)
        if not policy.approved:
            return self._result_without_mutation(
                position=position, before=before, policy=policy, risk=None,
                desired_qty=desired_qty, expected_price=expected_price,
                structural_stop=structural_stop, approved=False, reason=policy.reason,
            )
        # Never widen the executable position stop to accommodate an add.
        if position.direction == "LONG" and structural_stop < position.executable_stop:
            reason = "STRUCTURAL_STOP_WOULD_WIDEN_POSITION_STOP"
            return self._result_without_mutation(
                position=position, before=before, policy=policy, risk=None,
                desired_qty=desired_qty, expected_price=expected_price,
                structural_stop=structural_stop, approved=False, reason=reason,
            )
        if position.direction == "SHORT" and structural_stop > position.executable_stop:
            reason = "STRUCTURAL_STOP_WOULD_WIDEN_POSITION_STOP"
            return self._result_without_mutation(
                position=position, before=before, policy=policy, risk=None,
                desired_qty=desired_qty, expected_price=expected_price,
                structural_stop=structural_stop, approved=False, reason=reason,
            )
        # A tighter structural stop may be used hypothetically; risk is evaluated at
        # the actual resulting aggregate executable stop, never a looser one.
        executable_stop = (
            max(position.executable_stop, structural_stop)
            if position.direction == "LONG"
            else min(position.executable_stop, structural_stop)
        )
        risk = assess_scale_in(
            direction=position.direction, lots=position.open_lots(),
            executable_stop=executable_stop,
            initial_trade_risk_budget=position.initial_trade_risk_budget,
            requested_qty=desired_qty, expected_price=expected_price,
            qty_step=qty_step, risk_buffer_per_unit=risk_buffer_per_unit,
            min_qty=min_qty, min_notional=min_notional,
            allow_clamp=False,
        )
        approved_qty = risk.approved_qty
        total_qty = position.open_qty + approved_qty
        avg = position.avg_entry
        if risk.approved and total_qty > 0:
            prior_notional = (position.avg_entry or Decimal("0")) * position.open_qty
            avg = (prior_notional + expected_price * approved_qty) / total_qty
        result = ShadowScaleInResult(
            policy=policy, risk=risk, hypothetical_avg_entry=avg,
            hypothetical_open_qty=total_qty, hypothetical_stop=executable_stop,
            approved=risk.approved, reason=risk.reason,
        )
        self._assert_unchanged(position, before)
        return result

    def _result_without_mutation(self, *, position, before, policy, risk,
                                 desired_qty, expected_price, structural_stop,
                                 approved, reason):
        del desired_qty, expected_price
        result = ShadowScaleInResult(
            policy=policy, risk=risk, hypothetical_avg_entry=position.avg_entry,
            hypothetical_open_qty=position.open_qty,
            hypothetical_stop=position.executable_stop,
            approved=approved, reason=reason,
        )
        self._assert_unchanged(position, before)
        return result

    @staticmethod
    def _assert_unchanged(position: PositionLedger, before: tuple) -> None:
        after = (
            position.open_qty,
            position.avg_entry,
            position.executable_stop,
            position.realized_net_pnl,
            tuple((lot.execution_key, lot.open_qty) for lot in position.lots),
        )
        if after != before:
            raise AssertionError("shadow Scale-In evaluation mutated real position state")
