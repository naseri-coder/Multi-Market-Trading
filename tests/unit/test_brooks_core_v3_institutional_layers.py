from __future__ import annotations

import ast
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.modules.brooks_core_v3.ai_council import (
    BrooksCoreV3AICouncil,
    CouncilOpinion,
    CouncilStance,
)
from app.modules.brooks_core_v3.calibration import (
    BrooksCalibrationService,
    CalibrationAction,
    CalibrationRecommendation,
    CalibrationTarget,
)
from app.modules.brooks_core_v3.decision_layer import (
    BrooksDecisionIntelligenceService,
    DecisionReadiness,
)
from app.modules.brooks_core_v3.domain.enums import TradeDirection
from app.modules.brooks_core_v3.domain.models import RiskPlan, SetupCandidate
from app.modules.brooks_core_v3.execution_planner import BrooksCoreV3ExecutionPlanner
from app.modules.brooks_core_v3.governance import (
    BrooksGovernanceService,
    BrooksRuntimeGovernanceAuditor,
    GovernanceStatus,
)
from app.modules.brooks_core_v3.traders_equation import (
    BrooksTraderEquationEvaluator,
    TraderEquationInput,
)

NOW = datetime(2026, 9, 5, tzinfo=UTC)

def setup(rule_id="BB-RNG-17-HL-BAR-COUNT"):
    return SetupCandidate(
        candidate_id="setup-1", market_snapshot_id="snapshot-1",
        setup_type="H2_CONFIRMED", direction=TradeDirection.LONG,
        rule_ids=(rule_id,), rule_evaluations=(), evidence=(("context", "bull"),),
        created_at=NOW,
    )


def risk_plan():
    return RiskPlan(
        market_snapshot_id="snapshot-1", setup_candidate_id="setup-1",
        entry_price=Decimal("100"), stop_price=Decimal("98"),
        targets=(Decimal("104"),),
    )


def equation(probability="0.60"):
    return BrooksTraderEquationEvaluator().evaluate(
        TraderEquationInput(
            market_snapshot_id="snapshot-1", setup_candidate_id="setup-1",
            probability_success=Decimal(probability), risk=Decimal("2"), reward=Decimal("4"),
            probability_basis="historical", risk_basis="risk-plan", reward_basis="risk-plan",
            evaluated_at=NOW,
        )
    )

def council(stance=CouncilStance.SUPPORT):
    opinion = CouncilOpinion(
        reviewer_id="reviewer", stance=stance, basis="reviewed",
        reasons=("reviewed",), evidence_refs=("e1",),
    )
    return BrooksCoreV3AICouncil().deliberate(
        market_snapshot_id="snapshot-1", setup_candidate_id="setup-1", opinions=(opinion,),
    )


def plan(item=None, probability="0.60"):
    item = item or setup()
    eq = equation(probability)
    cc = council()
    return BrooksCoreV3ExecutionPlanner().plan(
        setup=item, risk_plan=risk_plan(), equation=eq, council=cc,
    ), eq, cc


def recommendation(*, applied=False):
    return CalibrationRecommendation(
        finding_id="finding-1", target_type=CalibrationTarget.RULE,
        target_id="BB-RNG-17-HL-BAR-COUNT", action=CalibrationAction.REVIEW_ONLY,
        evidence=(("n", "112"),), source_report_sha256="a" * 64,
        applied=applied,
    )


class InstitutionalLayerTests(unittest.TestCase):
    def test_decision_layer_ready_for_review(self):
        item = setup()
        draft, eq, cc = plan(item)
        result = BrooksDecisionIntelligenceService().assess(
            setup=item, equation=eq, council=cc, plan=draft,
        )
        self.assertEqual(result.readiness, DecisionReadiness.READY_FOR_REVIEW)
        self.assertEqual(result.unmapped_rule_ids, ())
        self.assertFalse(result.publication_allowed)

    def test_decision_layer_blocks_unmapped_rule(self):
        item = setup("UNMAPPED-RULE")
        draft, eq, cc = plan(item)
        result = BrooksDecisionIntelligenceService().assess(
            setup=item, equation=eq, council=cc, plan=draft,
        )
        self.assertEqual(result.readiness, DecisionReadiness.BLOCKED)
        self.assertEqual(result.unmapped_rule_ids, ("UNMAPPED-RULE",))

    def test_decision_layer_blocks_unfavorable_equation(self):
        item = setup()
        draft, _, cc = plan(item)
        bad_eq = equation("0.20")
        result = BrooksDecisionIntelligenceService().assess(
            setup=item, equation=bad_eq, council=cc, plan=draft,
        )
        self.assertEqual(result.readiness, DecisionReadiness.BLOCKED)

    def test_calibration_is_recommendation_only(self):
        book = BrooksCalibrationService().review((recommendation(),))
        self.assertEqual(len(book.recommendations), 1)
        self.assertFalse(book.automatic_application_allowed)
        self.assertFalse(book.recommendations[0].applied)

    def test_calibration_rejects_applied_recommendation(self):
        with self.assertRaises(ValueError):
            recommendation(applied=True)

    def test_governance_allows_review_but_never_auto_change(self):
        item = setup()
        draft, eq, cc = plan(item)
        decision = BrooksDecisionIntelligenceService().assess(
            setup=item, equation=eq, council=cc, plan=draft,
        )
        book = BrooksCalibrationService().review((recommendation(),))
        result = BrooksGovernanceService().review(decision=decision, calibration=book)
        self.assertEqual(result.status, GovernanceStatus.REVIEW_ALLOWED)
        self.assertFalse(result.automatic_production_change_allowed)
        self.assertFalse(result.publication_allowed)

    def test_governance_blocks_without_frozen_calibration(self):
        item = setup()
        draft, eq, cc = plan(item)
        decision = BrooksDecisionIntelligenceService().assess(
            setup=item, equation=eq, council=cc, plan=draft,
        )
        result = BrooksGovernanceService().review(decision=decision)
        self.assertEqual(result.status, GovernanceStatus.BLOCKED)
        self.assertIn("calibration_snapshot_not_attached", result.blockers)

    def test_runtime_governance_shadow_observes_without_control(self):
        candidate = type("Candidate", (), {
            "rule_ids": ("BB-RNG-17-HL-BAR-COUNT",),
            "market_snapshot_id": "snapshot-1", "setup_type": "H2_CONFIRMED",
            "direction": "LONG",
        })()
        result = BrooksRuntimeGovernanceAuditor().assess(
            candidate=candidate, council_approved=True, risk_approved=True,
            probability_calibrated=True, trader_equation_favorable=True,
            quality_approved=True, gate_approved=True,
        )
        self.assertEqual(result.status, "OBSERVED_PASS")
        self.assertEqual(result.unmapped_rule_ids, ())
        self.assertFalse(result.publication_allowed)

    def test_runtime_governance_shadow_flags_unmapped(self):
        candidate = type("Candidate", (), {
            "rule_ids": ("UNKNOWN",), "market_snapshot_id": "snapshot-1",
            "setup_type": "X", "direction": "LONG",
        })()
        result = BrooksRuntimeGovernanceAuditor().assess(
            candidate=candidate, council_approved=True, risk_approved=True,
            probability_calibrated=True, trader_equation_favorable=True,
            quality_approved=True, gate_approved=True,
        )
        self.assertEqual(result.status, "OBSERVED_BLOCKED")
        self.assertEqual(result.unmapped_rule_ids, ("UNKNOWN",))

    def test_new_layers_have_no_side_effect_imports(self):
        root = Path(__file__).resolve().parents[2]
        forbidden = ("sqlalchemy", "telegram", "app.db", "app.modules.paper_runtime")
        offenders = []
        for stage in ("decision_layer", "calibration", "governance"):
            for path in (root / "app/modules/brooks_core_v3" / stage).glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names = [node.module]
                    for name in names:
                        if any(name == item or name.startswith(item + ".") for item in forbidden):
                            offenders.append((stage, path.name, name))
        self.assertEqual(offenders, [])

    def test_runtime_wiring_is_observational_only(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / "app/modules/brooks_runtime/coordinator.py").read_text()
        self.assertIn("brooks_v3_governance_shadow_evaluated", text)
        self.assertIn('"production_behavior_changed": False', text)
        self.assertNotIn("if governance_audit.status", text)


if __name__ == "__main__":
    unittest.main()
