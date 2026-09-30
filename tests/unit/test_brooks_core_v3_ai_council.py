from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from app.modules.brooks_core_v3.ai_council import (
    BrooksCoreV3AICouncil,
    CouncilOpinion,
    CouncilResolution,
    CouncilStance,
    trader_equation_opinion,
)
from app.modules.brooks_core_v3.traders_equation import (
    BrooksTraderEquationEvaluator,
    TraderEquationInput,
)

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def opinion(reviewer: str, stance: CouncilStance) -> CouncilOpinion:
    return CouncilOpinion(
        reviewer_id=reviewer,
        stance=stance,
        basis="reviewed_evidence",
        reasons=("review complete",),
        evidence_refs=("evidence-1",),
    )


class AICouncilV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.council = BrooksCoreV3AICouncil()

    def deliberate(self, opinions):
        return self.council.deliberate(
            market_snapshot_id="snapshot-1",
            setup_candidate_id="setup-1",
            opinions=tuple(opinions),
        )

    def test_unanimous_support(self):
        result = self.deliberate(
            [opinion("a", CouncilStance.SUPPORT), opinion("b", CouncilStance.SUPPORT)]
        )
        self.assertEqual(result.resolution, CouncilResolution.UNANIMOUS_SUPPORT)
        self.assertEqual(result.support_count, 2)
        self.assertFalse(result.publication_allowed)

    def test_unanimous_opposition(self):
        result = self.deliberate(
            [opinion("a", CouncilStance.OPPOSE), opinion("b", CouncilStance.OPPOSE)]
        )
        self.assertEqual(result.resolution, CouncilResolution.UNANIMOUS_OPPOSITION)

    def test_split(self):
        result = self.deliberate(
            [opinion("a", CouncilStance.SUPPORT), opinion("b", CouncilStance.OPPOSE)]
        )
        self.assertEqual(result.resolution, CouncilResolution.SPLIT)

    def test_abstention_is_unresolved(self):
        result = self.deliberate(
            [opinion("a", CouncilStance.SUPPORT), opinion("b", CouncilStance.ABSTAIN)]
        )
        self.assertEqual(result.resolution, CouncilResolution.UNRESOLVED)

    def test_empty_council_is_unresolved(self):
        self.assertEqual(self.deliberate([]).resolution, CouncilResolution.UNRESOLVED)

    def test_duplicate_reviewer_is_rejected(self):
        with self.assertRaises(ValueError):
            self.deliberate(
                [opinion("same", CouncilStance.SUPPORT), opinion("same", CouncilStance.SUPPORT)]
            )

    def test_no_numeric_approval_surface(self):
        result = self.deliberate([opinion("a", CouncilStance.SUPPORT)])
        for forbidden in ("approved", "score", "final_score", "confidence", "decision"):
            self.assertFalse(hasattr(result, forbidden))

    def test_traders_equation_maps_to_council_stance_without_new_math(self):
        assessment = BrooksTraderEquationEvaluator().evaluate(
            TraderEquationInput(
                market_snapshot_id="snapshot-1",
                setup_candidate_id="setup-1",
                probability_success=Decimal("0.60"),
                risk=Decimal("2"),
                reward=Decimal("2"),
                probability_basis="reviewed_upstream_assessment",
                risk_basis="reviewed_risk_plan",
                reward_basis="reviewed_reward_plan",
                evaluated_at=NOW,
            )
        )
        vote = trader_equation_opinion(assessment)
        self.assertEqual(vote.stance, CouncilStance.SUPPORT)
        self.assertIn("BB-RNG-25-TRADERS-EQUATION", vote.evidence_refs)

    def test_stage_has_no_production_wiring_imports(self):
        root = Path(__file__).resolve().parents[2]
        stage = root / "app/modules/brooks_core_v3/ai_council"
        forbidden = ("sqlalchemy", "telegram", "app.db", "app.modules.brooks_runtime")
        offenders = []
        for path in stage.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if any(name == item or name.startswith(item + ".") for item in forbidden):
                        offenders.append((path.name, name))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
