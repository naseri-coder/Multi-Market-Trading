"""Fail-closed Execution Planner for review-only Brooks Core v3 output."""

from __future__ import annotations

from app.modules.brooks_core_v3.ai_council import CouncilDeliberation, CouncilResolution
from app.modules.brooks_core_v3.domain.models import RiskPlan, SetupCandidate
from app.modules.brooks_core_v3.traders_equation import (
    TraderEquationAssessment,
    TraderEquationStatus,
)

from .entities import ExecutionPlanDraft, PlanReadiness


class BrooksCoreV3ExecutionPlanner:
    def plan(
        self,
        *,
        setup: SetupCandidate,
        risk_plan: RiskPlan,
        equation: TraderEquationAssessment,
        council: CouncilDeliberation,
    ) -> ExecutionPlanDraft:
        self._validate_identity(
            setup=setup,
            risk_plan=risk_plan,
            equation=equation,
            council=council,
        )
        blockers = list(self._completeness_blockers(risk_plan))
        incomplete = bool(blockers)
        if equation.status is not TraderEquationStatus.FAVORABLE:
            blockers.append(f"traders_equation_{equation.status.value.lower()}")
        if council.resolution is not CouncilResolution.UNANIMOUS_SUPPORT:
            blockers.append(f"ai_council_{council.resolution.value.lower()}")

        if incomplete:
            readiness = PlanReadiness.INCOMPLETE
        elif blockers:
            readiness = PlanReadiness.BLOCKED
        else:
            readiness = PlanReadiness.READY_FOR_REVIEW

        blockers.extend(
            (
                "execution_planner_review_only",
                "execution_planner_no_exchange_orders",
                "execution_planner_no_runtime_publication",
            )
        )

        return ExecutionPlanDraft(
            market_snapshot_id=setup.market_snapshot_id,
            setup_candidate_id=setup.candidate_id,
            direction=setup.direction,
            risk_plan=risk_plan,
            readiness=readiness,
            blockers=tuple(dict.fromkeys(blockers)),
            audit_refs=(
                equation.formula_version,
                equation.source_evidence.rule_id,
                council.resolution.value,
            ),
        )

    @staticmethod
    def _validate_identity(
        *,
        setup: SetupCandidate,
        risk_plan: RiskPlan,
        equation: TraderEquationAssessment,
        council: CouncilDeliberation,
    ) -> None:
        snapshot_ids = {
            setup.market_snapshot_id,
            risk_plan.market_snapshot_id,
            equation.market_snapshot_id,
            council.market_snapshot_id,
        }
        setup_ids = {
            setup.candidate_id,
            risk_plan.setup_candidate_id,
            equation.setup_candidate_id,
            council.setup_candidate_id,
        }
        if len(snapshot_ids) != 1:
            raise ValueError("planner inputs must share one market snapshot")
        if len(setup_ids) != 1:
            raise ValueError("planner inputs must share one setup candidate")

    @staticmethod
    def _completeness_blockers(risk_plan: RiskPlan) -> tuple[str, ...]:
        missing = []
        if risk_plan.entry_price is None:
            missing.append("missing_entry_price")
        if risk_plan.stop_price is None:
            missing.append("missing_stop_price")
        if not risk_plan.targets:
            missing.append("missing_targets")
        return tuple(missing)
