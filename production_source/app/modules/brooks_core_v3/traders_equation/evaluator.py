"""Pure mathematical Trader's Equation evaluator; no trade-decision generation."""

from __future__ import annotations

from decimal import Decimal

from .entities import (
    TraderEquationAssessment,
    TraderEquationInput,
    TraderEquationStatus,
)
from .source import TraderEquationSourceEvidence


class BrooksTraderEquationEvaluator:
    """Evaluate supplied probability/risk/reward without estimating any of them."""

    def evaluate(self, item: TraderEquationInput) -> TraderEquationAssessment:
        missing = tuple(
            name
            for name, value in (
                ("probability_success", item.probability_success),
                ("risk", item.risk),
                ("reward", item.reward),
            )
            if value is None
        )
        if missing:
            return self._unresolved(item, missing)

        probability_success = item.probability_success
        risk = item.risk
        reward = item.reward
        assert probability_success is not None and risk is not None and reward is not None
        probability_failure = Decimal("1") - probability_success
        weighted_reward = probability_success * reward
        weighted_risk = probability_failure * risk
        expected_edge = weighted_reward - weighted_risk
        break_even_probability = risk / (risk + reward)

        if expected_edge > 0:
            status = TraderEquationStatus.FAVORABLE
        elif expected_edge < 0:
            status = TraderEquationStatus.UNFAVORABLE
        else:
            status = TraderEquationStatus.MARGINAL

        return TraderEquationAssessment(
            market_snapshot_id=item.market_snapshot_id,
            setup_candidate_id=item.setup_candidate_id,
            status=status,
            probability_success=probability_success,
            probability_failure=probability_failure,
            risk=risk,
            reward=reward,
            probability_basis=item.probability_basis,
            risk_basis=item.risk_basis,
            reward_basis=item.reward_basis,
            weighted_reward=weighted_reward,
            weighted_risk=weighted_risk,
            expected_edge=expected_edge,
            break_even_probability=break_even_probability,
            blockers=(
                "traders_equation_does_not_create_trade_decisions",
                "traders_equation_probability_must_be_supplied_upstream",
                "traders_equation_no_runtime_publication",
            ),
            source_evidence=TraderEquationSourceEvidence(),
        )

    @staticmethod
    def _unresolved(
        item: TraderEquationInput,
        missing: tuple[str, ...],
    ) -> TraderEquationAssessment:
        return TraderEquationAssessment(
            market_snapshot_id=item.market_snapshot_id,
            setup_candidate_id=item.setup_candidate_id,
            status=TraderEquationStatus.UNRESOLVED,
            probability_success=item.probability_success,
            probability_failure=(
                None
                if item.probability_success is None
                else Decimal("1") - item.probability_success
            ),
            risk=item.risk,
            reward=item.reward,
            probability_basis=item.probability_basis,
            risk_basis=item.risk_basis,
            reward_basis=item.reward_basis,
            weighted_reward=None,
            weighted_risk=None,
            expected_edge=None,
            break_even_probability=None,
            blockers=tuple(
                [f"missing_{name}" for name in missing]
                + [
                    "traders_equation_no_probability_inference",
                    "traders_equation_no_trade_decision",
                    "traders_equation_no_runtime_publication",
                ]
            ),
            source_evidence=TraderEquationSourceEvidence(),
        )
