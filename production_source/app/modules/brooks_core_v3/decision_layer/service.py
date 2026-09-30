"""Pure fail-closed decision orchestration for Brooks Core v3."""
from __future__ import annotations

from app.modules.brooks_core_v3.ai_council import CouncilDeliberation, CouncilResolution
from app.modules.brooks_core_v3.domain.models import SetupCandidate
from app.modules.brooks_core_v3.execution_planner import ExecutionPlanDraft, PlanReadiness
from app.modules.brooks_core_v3.knowledge.source_registry import REGISTRY
from app.modules.brooks_core_v3.traders_equation import (
    TraderEquationAssessment,
    TraderEquationStatus,
)

from .entities import DecisionIntelligenceAssessment, DecisionReadiness


class BrooksDecisionIntelligenceService:
    """Combine already-produced assessments without scoring or side effects."""

    def assess(
        self,
        *,
        setup: SetupCandidate,
        equation: TraderEquationAssessment,
        council: CouncilDeliberation,
        plan: ExecutionPlanDraft,
    ) -> DecisionIntelligenceAssessment:
        self._validate_identity(setup=setup, equation=equation, council=council, plan=plan)
        mapped = tuple(rule_id for rule_id in setup.rule_ids if rule_id in REGISTRY)
        unmapped = tuple(rule_id for rule_id in setup.rule_ids if rule_id not in REGISTRY)
        blockers: list[str] = []
        if unmapped:
            blockers.append("unmapped_brooks_rules")
        if equation.status is not TraderEquationStatus.FAVORABLE:
            blockers.append(f"traders_equation_{equation.status.value.lower()}")
        if council.resolution is not CouncilResolution.UNANIMOUS_SUPPORT:
            blockers.append(f"ai_council_{council.resolution.value.lower()}")
        if plan.readiness is not PlanReadiness.READY_FOR_REVIEW:
            blockers.append(f"execution_plan_{plan.readiness.value.lower()}")

        readiness = (
            DecisionReadiness.READY_FOR_REVIEW
            if not blockers
            else DecisionReadiness.BLOCKED
        )
        blockers.extend((
            "decision_intelligence_review_only",
            "decision_intelligence_no_signal_generation",
            "decision_intelligence_no_publication",
        ))
        return DecisionIntelligenceAssessment(
            market_snapshot_id=setup.market_snapshot_id,
            setup_candidate_id=setup.candidate_id,
            readiness=readiness,
            source_mapped_rule_ids=mapped,
            unmapped_rule_ids=unmapped,
            blockers=tuple(dict.fromkeys(blockers)),
            audit_refs=(equation.formula_version, council.resolution.value, plan.planner_version),
        )
    @staticmethod
    def _validate_identity(
        *,
        setup: SetupCandidate,
        equation: TraderEquationAssessment,
        council: CouncilDeliberation,
        plan: ExecutionPlanDraft,
    ) -> None:
        snapshots = {
            setup.market_snapshot_id,
            equation.market_snapshot_id,
            council.market_snapshot_id,
            plan.market_snapshot_id,
        }
        candidates = {
            setup.candidate_id,
            equation.setup_candidate_id,
            council.setup_candidate_id,
            plan.setup_candidate_id,
        }
        if len(snapshots) != 1 or len(candidates) != 1:
            raise ValueError("decision inputs must share one snapshot and setup")
