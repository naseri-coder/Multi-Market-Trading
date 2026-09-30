"""Immutable, threshold-free AI Council contracts for Brooks Core v3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CouncilStance(StrEnum):
    SUPPORT = "SUPPORT"
    OPPOSE = "OPPOSE"
    ABSTAIN = "ABSTAIN"


class CouncilResolution(StrEnum):
    UNANIMOUS_SUPPORT = "UNANIMOUS_SUPPORT"
    UNANIMOUS_OPPOSITION = "UNANIMOUS_OPPOSITION"
    SPLIT = "SPLIT"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class CouncilOpinion:
    reviewer_id: str
    stance: CouncilStance
    basis: str
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reviewer_id.strip() or not self.basis.strip():
            raise ValueError("reviewer_id and basis are required")
        if not self.reasons or any(not reason.strip() for reason in self.reasons):
            raise ValueError("council opinion requires non-blank reasons")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("evidence_refs cannot contain blanks")


@dataclass(frozen=True, slots=True)
class CouncilDeliberation:
    market_snapshot_id: str
    setup_candidate_id: str
    opinions: tuple[CouncilOpinion, ...]
    resolution: CouncilResolution
    support_count: int
    oppose_count: int
    abstain_count: int
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.market_snapshot_id.strip() or not self.setup_candidate_id.strip():
            raise ValueError("snapshot/setup ids are required")
        reviewer_ids = [item.reviewer_id for item in self.opinions]
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError("council reviewer ids must be unique")
        if any(value < 0 for value in (self.support_count, self.oppose_count, self.abstain_count)):
            raise ValueError("council counts cannot be negative")
        if sum((self.support_count, self.oppose_count, self.abstain_count)) != len(self.opinions):
            raise ValueError("council counts must match opinions")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("council blockers cannot contain blanks")

    @property
    def publication_allowed(self) -> bool:
        return False
