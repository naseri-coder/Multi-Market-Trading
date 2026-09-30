"""HTML-safe Telegram templates for Performance Intelligence reports."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from html import escape
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo


class PerformanceReportType(StrEnum):
    RUNTIME_STARTED = "runtime_started"
    RUNTIME_HEALTH = "runtime_health"
    DAILY = "daily_performance"
    OBSERVATION_COMPLETE = "observation_complete"
    ERROR = "error"
    WEEKLY = "weekly_summary"
    MONTHLY = "monthly_summary"


class PerformanceTelegramReportTemplate:
    """Render compact HTML accepted by Telegram's supported formatting subset."""

    _MAX_TEXT = 4096

    def __init__(self, timezone_name: str = "UTC") -> None:
        self.timezone = ZoneInfo(timezone_name)

    @staticmethod
    def _mapping_lines(values: Mapping[str, object] | None) -> list[str]:
        if not values:
            return ["—"]
        return [f"• <b>{escape(str(key))}</b>: {escape(str(value))}" for key, value in values.items()]

    @staticmethod
    def _recommendation_lines(values: Sequence[str] | None) -> list[str]:
        if not values:
            return ["—"]
        return [f"• {escape(str(value))}" for value in values]

    def render(
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
        moment = generated_at or datetime.now(self.timezone)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=self.timezone)
        moment = moment.astimezone(self.timezone)
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📊 <b>Performance Intelligence Report</b>",
            f"<b>Type:</b> {escape(report_type.value)}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🕒 <b>Time</b>: {escape(moment.isoformat())}",
            "",
            "⚙ <b>Runtime Health</b>",
            *self._mapping_lines(runtime_health),
            "",
            "📈 <b>Signal Performance</b>",
            *self._mapping_lines(signal_performance),
            "",
            "🎯 <b>Pattern Intelligence</b>",
            *self._mapping_lines(pattern_intelligence),
            "",
            "❌ <b>Failure Analysis</b>",
            *self._mapping_lines(failure_analysis),
            "",
            "💎 <b>Opportunity Analysis</b>",
            *self._mapping_lines(opportunity_analysis),
            "",
            "📊 <b>Confidence Calibration</b>",
            *self._mapping_lines(confidence_calibration),
            "",
            "⚖ <b>Compare</b>",
            "Performance Intelligence VS Brooks Core v3",
            *self._mapping_lines(comparison),
            "",
            "🟢 <b>Runtime Status</b>",
            *self._mapping_lines(runtime_status),
            "",
            "💡 <b>Recommended Improvements</b>",
            *self._recommendation_lines(recommended_improvements),
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]
        text = "\n".join(lines)
        if len(text) <= self._MAX_TEXT:
            return text
        suffix = "\n…\n━━━━━━━━━━━━━━━━━━━━━━"
        return text[: self._MAX_TEXT - len(suffix)] + suffix
