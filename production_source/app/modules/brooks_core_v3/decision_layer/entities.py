"""Pure institutional decision-intelligence contracts for Brooks Core v3."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DecisionReadiness(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    BLOCKED = "BLOCKED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


@dataclass(frozen=True, slots=True)
class DecisionIntelligenceAssessment:
    market_snapshot_id: str
    setup_candidate_id: str
    readiness: DecisionReadiness
    source_mapped_rule_ids: tuple[str, ...]
    unmapped_rule_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    audit_refs: tuple[str, ...]

    @property
    def publication_allowed(self) -> bool:
        return False
