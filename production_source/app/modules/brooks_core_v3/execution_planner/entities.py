"""Non-executing planning contracts for Brooks Core v3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.modules.brooks_core_v3.domain.models import RiskPlan
from app.modules.brooks_core_v3.domain.enums import TradeDirection


PLANNER_VERSION = "brooks-core-v3-execution-planner-review-v1"


class PlanReadiness(StrEnum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ExecutionPlanDraft:
    market_snapshot_id: str
    setup_candidate_id: str
    direction: TradeDirection
    risk_plan: RiskPlan
    readiness: PlanReadiness
    blockers: tuple[str, ...]
    audit_refs: tuple[str, ...]
    planner_version: str = PLANNER_VERSION

    def __post_init__(self) -> None:
        if not self.market_snapshot_id.strip() or not self.setup_candidate_id.strip():
            raise ValueError("snapshot/setup ids are required")
        if self.risk_plan.market_snapshot_id != self.market_snapshot_id:
            raise ValueError("risk plan snapshot mismatch")
        if self.risk_plan.setup_candidate_id != self.setup_candidate_id:
            raise ValueError("risk plan setup mismatch")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("planner blockers cannot contain blanks")
        if any(not item.strip() for item in self.audit_refs):
            raise ValueError("planner audit refs cannot contain blanks")
        if not self.planner_version.strip():
            raise ValueError("planner_version is required")

    @property
    def execution_allowed(self) -> bool:
        return False

    @property
    def publication_allowed(self) -> bool:
        return False
