"""Report builders for daily/weekly/monthly performance views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from .report_templates import PerformanceReportType, PerformanceTelegramReportTemplate


class PerformanceReportEngine:
    def __init__(self, *, timezone_name: str = "UTC") -> None:
        self._telegram_template = PerformanceTelegramReportTemplate(timezone_name)

    def build(self, metrics: dict, period: str) -> dict:
        return {
            "title": "BROOKS CORE PERFORMANCE REPORT",
            "period": period,
            "summary": metrics,
            "analysis_only": True,
        }

    def daily(self, metrics: dict) -> dict:
        return self.build(metrics, "daily")

    def weekly(self, metrics: dict) -> dict:
        return self.build(metrics, "weekly")

    def monthly(self, metrics: dict) -> dict:
        return self.build(metrics, "monthly")

    def telegram(
        self,
        *,
        report_type: PerformanceReportType,
        generated_at: datetime | None = None,
        runtime_health: Mapping[str, object] | None = None,
        signal_performance: Mapping[str, object] | None = None,
        pattern_intelligence: Mapping[str, object] | None = None,
        failure_analysis: Mapping[str, object] | None = None,
        opportunity_analysis: Mapping[str, object] | None = None,
        confidence_calibration: Mapping[str, object] | None = None,
        comparison: Mapping[str, object] | None = None,
        runtime_status: Mapping[str, object] | None = None,
        recommended_improvements: Sequence[str] | None = None,
    ) -> str:
        return self._telegram_template.render(
            report_type=report_type,
            generated_at=generated_at,
            runtime_health=runtime_health,
            signal_performance=signal_performance,
            pattern_intelligence=pattern_intelligence,
            failure_analysis=failure_analysis,
            opportunity_analysis=opportunity_analysis,
            confidence_calibration=confidence_calibration,
            comparison=comparison,
            runtime_status=runtime_status,
            recommended_improvements=recommended_improvements,
        )
