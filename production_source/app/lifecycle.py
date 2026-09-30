"""Application resource startup and shutdown coordination."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from telegram.ext import Application

from app.core.config import Settings
from app.db.errors import DatabaseUnavailableError
from app.db.session import DatabaseManager
from app.modules.performance_intelligence import (
    PerformanceAnalytics,
    PerformanceCollector,
    PerformanceReportEngine,
    PerformanceReportingPipeline,
    PerformanceReportType,
    PerformanceTelegramPublisher,
)
from app.modules.performance_intelligence.shadow_controller import (
    PerformanceIntelligenceShadowController,
)

logger = logging.getLogger(__name__)


class ApplicationLifecycle:
    """Bind infrastructure lifecycle to the Telegram application lifecycle."""

    def __init__(self, database: DatabaseManager, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.shadow_controller = PerformanceIntelligenceShadowController(
            enabled=settings.performance_intelligence_shadow_mode
        )
        self.reporting_pipeline: PerformanceReportingPipeline | None = None
        self.reporting_task: asyncio.Task[None] | None = None

    async def _reporting_loop(self) -> None:
        logger.info(
            "Performance reporting task started",
            extra={
                "event": "performance_reporting_task_started",
                "task_exists": self.reporting_task is not None,
                "pipeline_exists": self.reporting_pipeline is not None,
                "interval": getattr(self.settings, "performance_report_interval", 3600),
            },
        )
        try:
            if self.reporting_pipeline is not None:
                logger.info(
                    "Performance reporting initial execution started",
                    extra={"event": "performance_reporting_initial_execution_started"},
                )
                try:
                    result = await self.reporting_pipeline.run(
                        signals=[],
                        report_type=PerformanceReportType.RUNTIME_HEALTH,
                    )
                    logger.info(
                        "Performance report delivery result",
                        extra={
                            "event": "performance_report_delivery_result",
                            "success": getattr(result, "success", None),
                            "message_id": getattr(result, "message_id", None),
                            "attempts": getattr(result, "attempts", None),
                        },
                    )
                    logger.info(
                        "Performance reporting initial execution completed",
                        extra={"event": "performance_reporting_initial_execution_completed"},
                    )
                except Exception:
                    logger.exception(
                        "Performance reporting initial execution failed",
                        extra={"event": "performance_reporting_initial_execution_failed"},
                    )

            while True:
                await asyncio.sleep(getattr(self.settings, "performance_report_interval", 3600))
                if self.reporting_pipeline is not None:
                    logger.info(
                        "Performance reporting execution started",
                        extra={"event": "performance_reporting_execution_started"},
                    )
                    try:
                        result = await self.reporting_pipeline.run(
                            signals=[],
                            report_type=PerformanceReportType.RUNTIME_HEALTH,
                        )
                        logger.info(
                            "Performance report delivery result",
                            extra={
                                "event": "performance_report_delivery_result",
                                "success": getattr(result, "success", None),
                                "message_id": getattr(result, "message_id", None),
                                "attempts": getattr(result, "attempts", None),
                            },
                        )
                        logger.info(
                            "Performance reporting execution completed",
                            extra={"event": "performance_reporting_execution_completed"},
                        )
                    except Exception:
                        logger.exception(
                            "Performance reporting execution failed",
                            extra={"event": "performance_reporting_execution_failed"},
                        )
        except asyncio.CancelledError:
            logger.info(
                "Performance reporting task cancelled",
                extra={"event": "performance_reporting_task_cancelled"},
            )
            raise

    async def startup_core(
        self,
        runtime_state: dict[str, object],
        *,
        telegram_bot: object | None = None,
    ) -> None:
        """Start non-transport application resources shared by all runtime modes."""
        runtime_state["database"] = self.database

        if self.settings.performance_reports_enabled:
            if telegram_bot is None:
                raise RuntimeError(
                    "Performance Telegram reporting requires an active Telegram runtime"
                )
            publisher = PerformanceTelegramPublisher(
                bot=telegram_bot,
                channel_id=self.settings.performance_report_channel_id or 0,
                parse_mode=self.settings.performance_report_parse_mode,
                max_retry=self.settings.performance_report_max_retry,
            )
            logger.info(
                "Performance reporting pipeline creation attempt",
                extra={"event": "performance_reporting_pipeline_creation_attempt"},
            )
            self.reporting_pipeline = PerformanceReportingPipeline(
                collector=PerformanceCollector(),
                analytics=PerformanceAnalytics(),
                report_engine=PerformanceReportEngine(
                    timezone_name=self.settings.performance_report_timezone
                ),
                publisher=publisher,
            )
            logger.info(
                "Performance reporting pipeline created",
                extra={
                    "event": "performance_reporting_pipeline_created",
                    "pipeline_exists": self.reporting_pipeline is not None,
                    "publisher_attached": True,
                    "report_engine_attached": True,
                    "collector_attached": True,
                    "analytics_attached": True,
                },
            )
            logger.info(
                "Performance reporting pipeline starting",
                extra={"event": "performance_reporting_pipeline_starting"},
            )
            start = getattr(self.reporting_pipeline, "start", None)
            if start is not None:
                start()
            logger.info(
                "Performance reporting pipeline started",
                extra={
                    "event": "performance_reporting_pipeline_started",
                    "pipeline_exists": self.reporting_pipeline is not None,
                    "publisher_attached": True,
                    "report_engine_attached": True,
                    "collector_attached": True,
                    "analytics_attached": True,
                },
            )
            if self.reporting_task is None:
                self.reporting_task = asyncio.create_task(self._reporting_loop())
                logger.info(
                    "Performance reporting task created",
                    extra={
                        "event": "performance_reporting_task_created",
                        "task_exists": True,
                        "pipeline_exists": self.reporting_pipeline is not None,
                        "interval": getattr(self.settings, "performance_report_interval", 3600),
                    },
                )
            else:
                logger.info(
                    "Performance reporting task already exists",
                    extra={"event": "performance_reporting_task_already_exists"},
                )

        logger.info(
            "Performance Intelligence shadow flag evaluated",
            extra={
                "event": "shadow_flag_value",
                "enabled": self.settings.performance_intelligence_shadow_mode,
            },
        )
        if self.settings.performance_intelligence_shadow_mode:
            logger.info(
                "Shadow Controller start entering",
                extra={
                    "event": "shadow_controller_start_entering",
                    "enabled": self.shadow_controller.enabled,
                },
            )
            status = self.shadow_controller.start()
            logger.info(
                "Shadow Controller start returned",
                extra={
                    "event": "shadow_controller_start_returned",
                    "enabled": status.enabled,
                    "startup_attempted": status.startup_attempted,
                    "started": status.started,
                    "collector_running": status.collector_running,
                    "analytics_running": status.analytics_running,
                    "reports_running": status.reports_running,
                    "last_error": status.last_error,
                },
            )
            runtime_state["performance_intelligence_shadow"] = status

        try:
            health = await self.database.health_check()
        except DatabaseUnavailableError:
            runtime_state.pop("performance_intelligence_shadow", None)
            self.shadow_controller.stop()
            self.reporting_pipeline = None
            runtime_state.pop("database", None)
            await self.database.dispose()
            raise

        logger.info(
            "PostgreSQL connection established",
            extra={"event": "database_started", "latency_ms": health.latency_ms},
        )

    async def startup(self, application: Application) -> None:
        """Adapt the PTB startup callback to the shared core lifecycle."""
        await self.startup_core(application.bot_data, telegram_bot=application.bot)

    async def shutdown_core(self, runtime_state: dict[str, object]) -> None:
        """Dispose non-transport resources shared by all runtime modes."""
        runtime_state.pop("performance_intelligence_shadow", None)
        self.shadow_controller.stop()
        if self.reporting_task is not None:
            self.reporting_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reporting_task
            self.reporting_task = None
        if self.reporting_pipeline is not None:
            stop = getattr(self.reporting_pipeline, "stop", None)
            if stop is not None:
                stop()
            self.reporting_pipeline = None
        runtime_state.pop("database", None)
        await self.database.dispose()
        logger.info("PostgreSQL pool disposed", extra={"event": "database_stopped"})

    async def shutdown(self, application: Application) -> None:
        """Adapt the PTB shutdown callback to the shared core lifecycle."""
        await self.shutdown_core(application.bot_data)
