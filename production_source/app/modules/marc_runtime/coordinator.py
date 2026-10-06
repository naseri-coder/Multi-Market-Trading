"""Isolated runtime coordinator for the MARC strategy core."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from telegram.ext import Application

from app.modules.marc_runtime.contracts import MARCEngine, MARCRuntimeContext
from app.modules.marc_runtime.registry import (
    MARCEngineRegistry,
    default_fm_engine_registry,
)
from app.modules.signal_strategies.entities import (
    MARC_STRATEGY_CODE,
    SignalStrategyRecord,
)
from app.modules.signal_strategies.publisher import TelegramStrategyVipPublisher
from app.modules.signal_strategies.repository import (
    SQLAlchemySignalStrategyRepository,
)
from app.modules.signal_strategies.service import SignalStrategyService

logger = logging.getLogger(__name__)

_RECONCILE_INTERVAL_SECONDS = 5.0


class MARCRuntimeCoordinator:
    """Connect an optional MARC engine to only the MARC strategy route.

    This coordinator never imports Brooks runtime/core modules. With no
    registered MARC engine it synchronizes engine_ready=false and performs no
    market analysis or Telegram publication.
    """

    def __init__(
        self,
        *,
        database: Any,
        registry: MARCEngineRegistry = default_fm_engine_registry,
    ) -> None:
        self.database = database
        self.registry = registry
        self._task: asyncio.Task[None] | None = None
        self._application: Application | None = None
        self._running_engine: MARCEngine | None = None
        self._running_channel_id: int | None = None

    async def _sync_engine_ready(self, ready: bool) -> SignalStrategyRecord:
        async with self.database.session() as session, session.begin():
            return await SignalStrategyService(
                SQLAlchemySignalStrategyRepository(session)
            ).set_engine_ready(MARC_STRATEGY_CODE, ready=ready)

    async def _load_route(self) -> SignalStrategyRecord:
        async with self.database.session() as session:
            return await SignalStrategyService(
                SQLAlchemySignalStrategyRepository(session)
            ).get(MARC_STRATEGY_CODE)

    async def start(self, application: Application) -> None:
        if self._task is not None:
            raise RuntimeError("MARC runtime coordinator is already started")

        self._application = application
        engine = self.registry.get()
        route = await self._sync_engine_ready(engine is not None)

        if engine is None:
            logger.info(
                "MARC engine is not connected; runtime remains fail-closed",
                extra={
                    "event": "fm_engine_not_connected",
                    "strategy_code": MARC_STRATEGY_CODE,
                    "configured_enabled": route.enabled,
                    "channel_configured": route.private_channel_id is not None,
                },
            )
            return

        await self._reconcile_once()
        self._task = asyncio.create_task(
            self._reconcile_loop(),
            name="fm-strategy-runtime-coordinator",
        )
        logger.info(
            "MARC runtime coordinator started",
            extra={
                "event": "marc_runtime_coordinator_started",
                "engine_id": engine.engine_id,
                "engine_version": engine.engine_version,
            },
        )

    async def shutdown(self, application: Application) -> None:
        del application
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._stop_engine()
        self._application = None
        logger.info(
            "MARC runtime coordinator stopped",
            extra={"event": "marc_runtime_coordinator_stopped"},
        )

    async def _reconcile_loop(self) -> None:
        while True:
            try:
                await self._reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "MARC runtime route reconciliation failed",
                    extra={"event": "marc_runtime_reconcile_failed"},
                )
            await asyncio.sleep(_RECONCILE_INTERVAL_SECONDS)

    async def _reconcile_once(self) -> None:
        engine = self.registry.get()
        if engine is None:
            await self._stop_engine()
            await self._sync_engine_ready(False)
            return

        route = await self._load_route()
        if not route.effective_enabled:
            await self._stop_engine()
            return

        channel_id = route.private_channel_id
        if channel_id is None:
            await self._stop_engine()
            return

        if self._running_engine is engine and self._running_channel_id == channel_id:
            return

        await self._stop_engine()
        application = self._application
        if application is None:
            raise RuntimeError("MARC runtime requires an initialized Telegram application")

        publisher = TelegramStrategyVipPublisher(
            bot=application.bot,
            private_channel_id=channel_id,
        )
        context = MARCRuntimeContext(
            database=self.database,
            publisher=publisher,
            private_channel_id=channel_id,
        )
        try:
            await engine.start(context)
        except Exception:
            logger.exception(
                "MARC engine startup failed; Brooks runtime remains isolated",
                extra={
                    "event": "fm_engine_start_failed",
                    "engine_id": engine.engine_id,
                    "engine_version": engine.engine_version,
                    "channel_id": channel_id,
                },
            )
            return

        self._running_engine = engine
        self._running_channel_id = channel_id
        logger.info(
            "MARC engine started on its independent strategy route",
            extra={
                "event": "fm_engine_started",
                "engine_id": engine.engine_id,
                "engine_version": engine.engine_version,
                "strategy_code": MARC_STRATEGY_CODE,
                "channel_id": channel_id,
            },
        )

    async def _stop_engine(self) -> None:
        engine = self._running_engine
        self._running_engine = None
        self._running_channel_id = None
        if engine is None:
            return
        try:
            await engine.shutdown()
        except Exception:
            logger.exception(
                "MARC engine shutdown failed without affecting Brooks runtime",
                extra={
                    "event": "fm_engine_shutdown_failed",
                    "engine_id": engine.engine_id,
                    "engine_version": engine.engine_version,
                },
            )
            return
        logger.info(
            "MARC engine stopped",
            extra={
                "event": "fm_engine_stopped",
                "engine_id": engine.engine_id,
                "engine_version": engine.engine_version,
            },
        )
