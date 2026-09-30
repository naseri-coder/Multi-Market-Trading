"""Governance and decision-intelligence contracts for Brooks Core v3."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GovernanceStatus(StrEnum):
    BLOCKED = "BLOCKED"
    REVIEW_ALLOWED = "REVIEW_ALLOWED"


@dataclass(frozen=True, slots=True)
class GovernanceReview:
    market_snapshot_id: str
    setup_candidate_id: str
    status: GovernanceStatus
    blockers: tuple[str, ...]
    audit_refs: tuple[str, ...]

    @property
    def automatic_production_change_allowed(self) -> bool:
        return False

    @property
    def publication_allowed(self) -> bool:
        return False
