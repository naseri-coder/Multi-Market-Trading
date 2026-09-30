"""Recommendation-only learning/calibration contracts for Brooks Core v3."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CalibrationTarget(StrEnum):
    RULE = "RULE"
    PATTERN = "PATTERN"
    CONTEXT = "CONTEXT"
    THRESHOLD = "THRESHOLD"


class CalibrationAction(StrEnum):
    REVIEW_INCREASE = "REVIEW_INCREASE"
    REVIEW_DECREASE = "REVIEW_DECREASE"
    REVIEW_ONLY = "REVIEW_ONLY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class CalibrationRecommendation:
    finding_id: str
    target_type: CalibrationTarget
    target_id: str
    action: CalibrationAction
    evidence: tuple[tuple[str, str], ...]
    source_report_sha256: str
    applied: bool = False

    def __post_init__(self) -> None:
        if not self.finding_id.strip() or not self.target_id.strip():
            raise ValueError("finding_id and target_id are required")
        if len(self.source_report_sha256) != 64:
            raise ValueError("source_report_sha256 must be sha256")
        if self.applied:
            raise ValueError("calibration recommendations cannot auto-apply")


@dataclass(frozen=True, slots=True)
class CalibrationReviewBook:
    recommendations: tuple[CalibrationRecommendation, ...]
    source_report_sha256: str
    blockers: tuple[str, ...] = (
        "calibration_recommendations_not_applied",
        "calibration_requires_separate_controlled_change",
    )

    @property
    def automatic_application_allowed(self) -> bool:
        return False
