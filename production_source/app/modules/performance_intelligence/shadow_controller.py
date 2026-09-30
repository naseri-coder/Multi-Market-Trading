"""Read-only Performance Intelligence shadow runtime controller.

This controller can collect/analyze/report only. It cannot affect trading decisions.
"""

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShadowRuntimeStatus:
    enabled: bool
    startup_attempted: bool = False
    started: bool = False
    collector_running: bool = False
    analytics_running: bool = False
    reports_running: bool = False
    last_error: str | None = None


class PerformanceIntelligenceShadowController:
    """Fail-closed controller for analytics-only shadow execution."""

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self._status = ShadowRuntimeStatus(enabled=enabled)

    @property
    def enabled(self) -> bool:
        """Read-only access to shadow runtime enable state."""
        return self._enabled

    def start(self) -> ShadowRuntimeStatus:
        logger.info(
            "Shadow Controller startup attempted",
            extra={"event": "performance_intelligence_shadow_start_attempt"},
        )
        if not self._enabled:
            self._status = ShadowRuntimeStatus(
                enabled=False, startup_attempted=True, started=False
            )
            return self._status

        try:
            # Runtime hooks intentionally remain analytics-only.
            self._status = ShadowRuntimeStatus(
                enabled=True,
                startup_attempted=True,
                started=True,
                collector_running=True,
                analytics_running=True,
                reports_running=True,
            )
            logger.info(
                "Shadow Controller started",
                extra={
                    "event": "performance_intelligence_shadow_started",
                    "collector_running": True,
                    "analytics_running": True,
                    "reports_running": True,
                },
            )
            return self._status
        except Exception as exc:
            self._status = ShadowRuntimeStatus(
                enabled=True,
                startup_attempted=True,
                started=False,
                last_error=str(exc),
            )
            logger.exception(
                "Shadow Controller failed",
                extra={"event": "performance_intelligence_shadow_failed"},
            )
            return self._status

    def stop(self) -> ShadowRuntimeStatus:
        self._status = ShadowRuntimeStatus(enabled=self._enabled)
        return self._status

    def health(self) -> ShadowRuntimeStatus:
        return self._status
