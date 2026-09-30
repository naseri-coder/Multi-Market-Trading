from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from app.modules.brooks_core_v3.domain.enums import TradeDirection
from app.modules.brooks_core_v3.domain.models import RiskPlan, SetupCandidate
from app.modules.brooks_core_v3.traders_equation import (
    BrooksTraderEquationEvaluator,
    TraderEquationInput,
    TraderEquationStatus,
    from_phase3_contracts,
)

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def equation_input(*, probability="0.60", risk="2", reward="2"):
    return TraderEquationInput(
        market_snapshot_id="snapshot-1",
        setup_candidate_id="setup-1",
        probability_success=None if probability is None else Decimal(probability),
        risk=None if risk is None else Decimal(risk),
        reward=None if reward is None else Decimal(reward),
        probability_basis=None if probability is None else "reviewed_upstream_assessment",
        risk_basis=None if risk is None else "reviewed_risk_plan",
        reward_basis=None if reward is None else "reviewed_reward_plan",
        evaluated_at=NOW,
    )


class TraderEquationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = BrooksTraderEquationEvaluator()

    def test_favorable_equation(self):
        result = self.engine.evaluate(equation_input(probability="0.60", risk="2", reward="2"))
        self.assertEqual(result.status, TraderEquationStatus.FAVORABLE)
        self.assertEqual(result.weighted_reward, Decimal("1.20"))
        self.assertEqual(result.weighted_risk, Decimal("0.80"))
        self.assertEqual(result.expected_edge, Decimal("0.40"))
        self.assertEqual(result.break_even_probability, Decimal("0.5"))

    def test_marginal_equation(self):
        result = self.engine.evaluate(equation_input(probability="0.50", risk="2", reward="2"))
        self.assertEqual(result.status, TraderEquationStatus.MARGINAL)
        self.assertEqual(result.expected_edge, Decimal("0.00"))

    def test_unfavorable_equation(self):
        result = self.engine.evaluate(equation_input(probability="0.40", risk="2", reward="1"))
        self.assertEqual(result.status, TraderEquationStatus.UNFAVORABLE)
        self.assertLess(result.expected_edge, 0)

    def test_missing_probability_is_unresolved(self):
        result = self.engine.evaluate(equation_input(probability=None))
        self.assertEqual(result.status, TraderEquationStatus.UNRESOLVED)
        self.assertIn("missing_probability_success", result.blockers)
        self.assertIsNone(result.expected_edge)

    def test_missing_risk_or_reward_is_unresolved(self):
        for kwargs, blocker in (
            ({"risk": None}, "missing_risk"),
            ({"reward": None}, "missing_reward"),
        ):
            with self.subTest(blocker=blocker):
                result = self.engine.evaluate(equation_input(**kwargs))
                self.assertEqual(result.status, TraderEquationStatus.UNRESOLVED)
                self.assertIn(blocker, result.blockers)

    def test_probability_requires_explicit_basis(self):
        with self.assertRaises(ValueError):
            TraderEquationInput(
                market_snapshot_id="snapshot-1",
                setup_candidate_id="setup-1",
                probability_success=Decimal("0.60"),
                risk=Decimal("1"),
                reward=Decimal("1"),
                probability_basis=None,
                risk_basis="risk",
                reward_basis="reward",
                evaluated_at=NOW,
            )

    def test_phase3_adapter_derives_only_distances(self):
        setup = SetupCandidate(
            candidate_id="setup-1",
            market_snapshot_id="snapshot-1",
            setup_type="H2_CONFIRMED",
            direction=TradeDirection.LONG,
            rule_ids=("BB-RNG-17-HL-BAR-COUNT",),
            rule_evaluations=(),
            evidence=(("context", "bull trend"),),
            created_at=NOW,
        )
        risk_plan = RiskPlan(
            market_snapshot_id="snapshot-1",
            setup_candidate_id="setup-1",
            entry_price=Decimal("100"),
            stop_price=Decimal("98"),
            targets=(Decimal("104"),),
        )
        item = from_phase3_contracts(
            setup=setup,
            risk_plan=risk_plan,
            probability_success=Decimal("0.60"),
            probability_basis="reviewed_upstream_assessment",
            evaluated_at=NOW,
        )
        self.assertEqual(item.risk, Decimal("2"))
        self.assertEqual(item.reward, Decimal("4"))

    def test_source_evidence_and_safety_surface(self):
        result = self.engine.evaluate(equation_input())
        self.assertEqual(result.source_evidence.rule_id, "BB-RNG-25-TRADERS-EQUATION")
        self.assertEqual(result.source_evidence.source_pdf_pages, (172, 173, 177))
        self.assertFalse(result.publication_allowed)
        for forbidden in ("decision", "entry_price", "stop_loss", "targets", "leverage"):
            self.assertFalse(hasattr(result, forbidden))

    def test_same_input_is_deterministic(self):
        item = equation_input(probability="0.60", risk="2", reward="4")
        self.assertEqual(self.engine.evaluate(item), self.engine.evaluate(item))

    def test_stage_has_no_production_wiring_imports(self):
        root = Path(__file__).resolve().parents[2]
        stage = root / "app/modules/brooks_core_v3/traders_equation"
        forbidden = (
            "sqlalchemy",
            "telegram",
            "app.db",
            "app.modules.paper_runtime",
            "app.modules.brooks_runtime",
            "app.modules.operations",
            "app.modules.signal_automation",
        )
        offenders = []
        for path in stage.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif module:
                    names = [module]
                for name in names:
                    if any(name == item or name.startswith(item + ".") for item in forbidden):
                        offenders.append((path.name, name))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
