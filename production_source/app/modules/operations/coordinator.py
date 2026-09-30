"""Single production coordinator for lifecycle, settlement, entitlement and health."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from telegram.ext import Application

from app.core.config import Settings
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.operations.health import record_health
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.payment_settlement import PaymentSettlementService
from app.modules.operations.vip_entitlements import VipEntitlementService

logger = logging.getLogger(__name__)


class BrooksProductionOperationsCoordinator:
    def __init__(self, *, settings: Settings, database) -> None:
        self.settings = settings
        self.database = database
        self._tasks: list[asyncio.Task[None]] = []
        self._provider = None
        self._application: Application | None = None

    async def start(self, application: Application) -> None:
        if not self.settings.brooks_operations_enabled:
            logger.info(
                "Brooks production operations disabled",
                extra={"event": "brooks_operations_disabled"},
            )
            return
        if self._tasks:
            raise RuntimeError("Brooks production operations already started")
        self._application = application
        self._provider = self._build_provider()
        self._tasks = [
            asyncio.create_task(
                self._loop(
                    component="signal_lifecycle",
                    interval=self.settings.signal_lifecycle_poll_interval_seconds,
                    action=self._run_lifecycle,
                ),
                name="signal-lifecycle-worker",
            ),
            asyncio.create_task(
                self._loop(
                    component="payment_settlement",
                    interval=self.settings.payment_settlement_poll_interval_seconds,
                    action=self._run_payment_settlement,
                ),
                name="payment-settlement-worker",
            ),
            asyncio.create_task(
                self._loop(
                    component="vip_entitlement",
                    interval=self.settings.vip_entitlement_poll_interval_seconds,
                    action=self._run_vip_entitlement,
                ),
                name="vip-entitlement-worker",
            ),
        ]
        logger.info(
            "Brooks production operations started",
            extra={
                "event": "brooks_operations_started",
                "ops_cutover_at": self.settings.brooks_ops_cutover_at.isoformat(),
                "signal_lifecycle_interval": self.settings.signal_lifecycle_poll_interval_seconds,
                "payment_settlement_interval": self.settings.payment_settlement_poll_interval_seconds,
                "vip_entitlement_interval": self.settings.vip_entitlement_poll_interval_seconds,
            },
        )

    async def shutdown(self, application: Application) -> None:
        del application
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._provider is not None:
            await self._provider.aclose()
            self._provider = None
        self._application = None
        logger.info(
            "Brooks production operations stopped",
            extra={"event": "brooks_operations_stopped"},
        )

    def _build_provider(self) -> BinanceFuturesMarketDataProvider:
        if self.settings.brooks_exchange != "binance" or self.settings.brooks_market_type != "futures":
            raise ValueError("Brooks production operations require binance/futures")
        return BinanceFuturesMarketDataProvider()

    async def _loop(
        self,
        *,
        component: str,
        interval: int,
        action: Callable[[], Awaitable[dict[str, int]]],
    ) -> None:
        while True:
            try:
                details = await action()
                await self._health(component, "OK", details, error=False)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "Production operations worker failed",
                    extra={
                        "event": "brooks_operations_worker_failed",
                        "component": component,
                    },
                )
                await self._health(
                    component,
                    "ERROR",
                    {"error_code": type(exc).__name__},
                    error=True,
                )
            await asyncio.sleep(interval)

    async def _run_lifecycle(self) -> dict[str, int]:
        assert self._provider is not None
        assert self._application is not None
        service = LiveSignalLifecycleService(
            database=self.database,
            provider=self._provider,
            bot=self._application.bot,
            vip_channel_id=self.settings.brooks_vip_channel_id or 0,
            cutover_at=self.settings.brooks_ops_cutover_at,
            candle_limit=self.settings.signal_lifecycle_candle_limit,
        )
        return await service.run_once()

    async def _run_payment_settlement(self) -> dict[str, int]:
        return await PaymentSettlementService(
            database=self.database,
            cutover_at=self.settings.brooks_ops_cutover_at,
        ).run_once()

    async def _run_vip_entitlement(self) -> dict[str, int]:
        assert self._application is not None
        service = VipEntitlementService(
            database=self.database,
            bot=self._application.bot,
            vip_channel_id=self.settings.brooks_vip_channel_id or 0,
            invite_ttl_hours=self.settings.vip_invite_ttl_hours,
        )
        return await service.run_once()

    async def _health(
        self,
        component: str,
        status: str,
        details: dict[str, object],
        *,
        error: bool,
    ) -> None:
        try:
            async with self.database.session() as session, session.begin():
                await record_health(
                    session,
                    component=component,
                    status=status,
                    details=details,
                    error=error,
                )
        except Exception:
            logger.exception(
                "Unable to persist runtime health",
                extra={"event": "runtime_health_write_failed", "component": component},
            )


