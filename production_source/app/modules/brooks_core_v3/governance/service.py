"""Fail-closed governance review for Brooks Core v3 decision intelligence."""
from __future__ import annotations

from app.modules.brooks_core_v3.calibration import CalibrationReviewBook
from app.modules.brooks_core_v3.decision_layer import (
    DecisionIntelligenceAssessment,
    DecisionReadiness,
)

from .entities import GovernanceReview, GovernanceStatus


class BrooksGovernanceService:
    def review(
        self,
        *,
        decision: DecisionIntelligenceAssessment,
        calibration: CalibrationReviewBook | None = None,
    ) -> GovernanceReview:
        blockers: list[str] = []
        if decision.readiness is not DecisionReadiness.READY_FOR_REVIEW:
            blockers.append(f"decision_{decision.readiness.value.lower()}")
        if decision.unmapped_rule_ids:
            blockers.append("unmapped_brooks_rules")
        if calibration is None:
            blockers.append("calibration_snapshot_not_attached")
        elif calibration.automatic_application_allowed:
            blockers.append("unsafe_calibration_auto_apply")

        status = GovernanceStatus.REVIEW_ALLOWED if not blockers else GovernanceStatus.BLOCKED
        blockers.extend((
            "governance_review_only",
            "governance_no_automatic_parameter_changes",
            "governance_no_runtime_publication",
        ))
        refs = [*decision.audit_refs]
        if calibration is not None:
            refs.append(calibration.source_report_sha256)
        return GovernanceReview(
            market_snapshot_id=decision.market_snapshot_id,
            setup_candidate_id=decision.setup_candidate_id,
            status=status,
            blockers=tuple(dict.fromkeys(blockers)),
            audit_refs=tuple(refs),
        )
