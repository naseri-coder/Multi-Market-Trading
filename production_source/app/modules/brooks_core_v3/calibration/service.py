"""Validation-only calibration registry; never mutates production parameters."""
from __future__ import annotations

from .entities import CalibrationRecommendation, CalibrationReviewBook


class BrooksCalibrationService:
    def review(
        self,
        recommendations: tuple[CalibrationRecommendation, ...],
    ) -> CalibrationReviewBook:
        finding_ids = [item.finding_id for item in recommendations]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("calibration finding ids must be unique")
        if any(item.applied for item in recommendations):
            raise ValueError("calibration layer cannot accept applied recommendations")
        report_hashes = {item.source_report_sha256 for item in recommendations}
        if len(report_hashes) > 1:
            raise ValueError("calibration review must use one frozen research report")
        source_hash = next(iter(report_hashes), "0" * 64)
        return CalibrationReviewBook(
            recommendations=tuple(recommendations),
            source_report_sha256=source_hash,
        )
