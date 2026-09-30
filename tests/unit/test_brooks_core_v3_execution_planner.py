from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import unittest

from app.modules.brooks_core_v3.ai_council import (
    BrooksCoreV3AICouncil, CouncilOpinion, CouncilStance,
)
from app.modules.brooks_core_v3.domain.enums import TradeDirection
from app.modules.brooks_core_v3.domain.models import RiskPlan, SetupCandidate
from app.modules.brooks_core_v3.execution_planner import (
    BrooksCoreV3ExecutionPlanner, PlanReadiness,
)
from app.modules.brooks_core_v3.traders_equation import (
    BrooksTraderEquationEvaluator, TraderEquationInput,
)

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def setup():
    return SetupCandidate(
        candidate_id="setup-1", market_snapshot_id="snapshot-1",
        setup_type="H2_CONFIRMED", direction=TradeDirection.LONG,
        rule_ids=("BB-RNG-17-HL-BAR-COUNT",), rule_evaluations=(),
        evidence=(("context", "bull"),), created_at=NOW,
    )

def risk_plan(*, complete=True):
    return RiskPlan(
        market_snapshot_id="snapshot-1", setup_candidate_id="setup-1",
        entry_price=Decimal("100") if complete else None,
        stop_price=Decimal("98") if complete else None,
        targets=(Decimal("104"),) if complete else (),
    )


def equation(probability="0.60"):
    return BrooksTraderEquationEvaluator().evaluate(
        TraderEquationInput(
            market_snapshot_id="snapshot-1", setup_candidate_id="setup-1",
            probability_success=Decimal(probability), risk=Decimal("2"), reward=Decimal("4"),
            probability_basis="reviewed", risk_basis="risk-plan", reward_basis="risk-plan",
            evaluated_at=NOW,
        )
    )


def council(stance=CouncilStance.SUPPORT):
    opinion = CouncilOpinion(
        reviewer_id="reviewer-1", stance=stance, basis="reviewed",
        reasons=("reviewed",), evidence_refs=("e1",),
    )
    return BrooksCoreV3AICouncil().deliberate(
        market_snapshot_id="snapshot-1", setup_candidate_id="setup-1",
        opinions=(opinion,),
    )


class ExecutionPlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = BrooksCoreV3ExecutionPlanner()

    def test_complete_favorable_inputs_are_ready_for_review_only(self):
        result = self.planner.plan(
            setup=setup(), risk_plan=risk_plan(), equation=equation(), council=council()
        )
        self.assertEqual(result.readiness, PlanReadiness.READY_FOR_REVIEW)
        self.assertFalse(result.execution_allowed)
        self.assertFalse(result.publication_allowed)

    def test_unfavorable_equation_blocks(self):
        result = self.planner.plan(
            setup=setup(), risk_plan=risk_plan(), equation=equation("0.20"), council=council()
        )
        self.assertEqual(result.readiness, PlanReadiness.BLOCKED)

    def test_non_supporting_council_blocks(self):
        result = self.planner.plan(
            setup=setup(), risk_plan=risk_plan(), equation=equation(),
            council=council(CouncilStance.OPPOSE),
        )
        self.assertEqual(result.readiness, PlanReadiness.BLOCKED)

    def test_incomplete_risk_plan_is_incomplete(self):
        result = self.planner.plan(
            setup=setup(), risk_plan=risk_plan(complete=False),
            equation=equation(), council=council(),
        )
        self.assertEqual(result.readiness, PlanReadiness.INCOMPLETE)
        self.assertIn("missing_entry_price", result.blockers)
        self.assertIn("missing_stop_price", result.blockers)
        self.assertIn("missing_targets", result.blockers)

    def test_identity_mismatch_is_rejected(self):
        bad = RiskPlan(
            market_snapshot_id="other", setup_candidate_id="setup-1",
            entry_price=Decimal("100"), stop_price=Decimal("98"),
            targets=(Decimal("104"),),
        )
        with self.assertRaises(ValueError):
            self.planner.plan(
                setup=setup(), risk_plan=bad, equation=equation(), council=council()
            )

    def test_planner_does_not_create_new_trade_geometry(self):
        rp = risk_plan()
        result = self.planner.plan(
            setup=setup(), risk_plan=rp, equation=equation(), council=council()
        )
        self.assertIs(result.risk_plan, rp)
        self.assertFalse(hasattr(result, "order_id"))
        self.assertFalse(hasattr(result, "exchange_order"))


if __name__ == "__main__":
    unittest.main()
