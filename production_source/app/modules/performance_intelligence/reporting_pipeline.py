"""Analytics-only report pipeline ending at a private Telegram publisher."""

from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any, Iterable, Mapping, Sequence

from .analytics import PerformanceAnalytics
from .collector import PerformanceCollector
from .report_templates import PerformanceReportType
from .reports import PerformanceReportEngine
from .telegram_publisher import PerformancePublishResult, PerformanceTelegramPublisher

logger = logging.getLogger(__name__)


class PerformanceReportingPipeline:
    """Collect -> Analyze -> Report Engine -> Telegram Publisher, with no decision hooks."""

    def __init__(
        self,
        *,
        collector: PerformanceCollector,
        analytics: PerformanceAnalytics,
        report_engine: PerformanceReportEngine,
        publisher: PerformanceTelegramPublisher,
    ) -> None:
        self.collector = collector
        self.analytics = analytics
        self.report_engine = report_engine
        self.publisher = publisher
        self.started = False
        self.runtime_state = {
            "started": False,
            "collector_attached": True,
            "analytics_attached": True,
            "report_engine_attached": True,
            "publisher_attached": True,
        }

    def start(self) -> dict[str, bool]:
        """Initialize read-only reporting runtime state."""
        self.started = True
        self.runtime_state["started"] = True
        return self.runtime_state

    def stop(self) -> None:
        """Stop reporting runtime state safely."""
        self.started = False
        self.runtime_state["started"] = False

    async def run(
        self,
        *,
        signals: Iterable[Any],
        report_type: PerformanceReportType,
        runtime_health: Mapping[str, object] | None = None,
        pattern_intelligence: Mapping[str, object] | None = None,
        failure_analysis: Mapping[str, object] | None = None,
        opportunity_analysis: Mapping[str, object] | None = None,
        confidence_calibration: Mapping[str, object] | None = None,
        comparison: Mapping[str, object] | None = None,
        runtime_status: Mapping[str, object] | None = None,
        recommended_improvements: Sequence[str] | None = None,
    ) -> PerformancePublishResult:
        snapshots = [self.collector.collect(signal) for signal in signals]
        rows = [asdict(snapshot) for snapshot in snapshots]
        metrics = self.analytics.summarize(rows)
        message = self.report_engine.telegram(
            report_type=report_type,
            runtime_health=runtime_health,
            signal_performance=metrics,
            pattern_intelligence=pattern_intelligence,
            failure_analysis=failure_analysis,
            opportunity_analysis=opportunity_analysis,
            confidence_calibration=confidence_calibration,
            comparison=comparison,
            runtime_status=runtime_status,
            recommended_improvements=recommended_improvements,
        )
        try:
            return await self.publisher.publish(message)
        except Exception as exc:  # fail-open boundary: reporting must not stop analytics/runtime
            logger.exception(
                "Performance report pipeline publisher boundary failed",
                extra={"event": "performance_report_pipeline_failed"},
            )
            return PerformancePublishResult(
                success=False, attempts=0, error=exc.__class__.__name__
            )
