"""Real PostgreSQL tests for publication and performance isolation."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.analytics.entities import WinRatePeriod
from app.modules.analytics.repository import SQLAlchemyWinRateRepository
from app.modules.analytics.service import WinRateService
from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signals.entities import SignalListMode
from app.modules.signals.errors import SignalNotFoundError
from app.modules.signals.models import (
    Signal,
    SignalDirection,
    SignalEvent,
    SignalEventType,
    SignalPublicationScope,
    SignalStatus,
)
from app.modules.signals.query_service import SignalQueryService
from app.modules.signals.repository import SQLAlchemySignalRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for Phase 3 PostgreSQL isolation tests",
)


def signal_row(*, symbol: str, scope: str, status: str, now: datetime) -> dict[str, object]:
    terminal = status in (SignalStatus.CLOSED.value, SignalStatus.CANCELLED.value)
    return {
        "symbol": symbol,
        "direction": SignalDirection.LONG.value,
        "entry_price": Decimal("100"),
        "stop_loss": Decimal("90"),
        "leverage": Decimal("1"),
        "status": status,
        "publication_scope": scope,
        "profit_loss": Decimal("5") if status == SignalStatus.CLOSED.value else None,
        "closed_at": now - timedelta(minutes=5) if terminal else None,
        "created_at": now - timedelta(hours=1),
        "updated_at": now - timedelta(minutes=5) if terminal else now - timedelta(hours=1),
    }


@pytest.mark.asyncio
async def test_publication_and_winrate_isolation(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    now = datetime(2099, 9, 2, 12, tzinfo=UTC)
    created_ids: list[int] = []

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                visible_rows = [
                    signal_row(symbol="P3PUBLIC/USDT", scope=SignalPublicationScope.PUBLIC.value, status=SignalStatus.OPEN.value, now=now),
                    signal_row(symbol="P3PUBLICVIP/USDT", scope=SignalPublicationScope.PUBLIC_VIP.value, status=SignalStatus.OPEN.value, now=now),
                    signal_row(symbol="P3PRIVATE/USDT", scope=SignalPublicationScope.PRIVATE_TEST.value, status=SignalStatus.OPEN.value, now=now),
                    signal_row(symbol="P3INTERNAL/USDT", scope=SignalPublicationScope.INTERNAL.value, status=SignalStatus.OPEN.value, now=now),
                    signal_row(symbol="P3VIP/USDT", scope=SignalPublicationScope.VIP.value, status=SignalStatus.OPEN.value, now=now),
                ]
                created_ids.extend(
                    (
                        await session.execute(insert(Signal).values(visible_rows).returning(Signal.id))
                    ).scalars()
                )
                public_id, public_vip_id, private_id, internal_id, vip_id = created_ids

                query = SignalQueryService(SQLAlchemySignalRepository(session), clock=lambda: now)
                opened = await query.get_page(SignalListMode.OPEN.value)
                visible_ids = {item.id for item in opened.signals}

                assert public_id in visible_ids
                assert public_vip_id in visible_ids
                assert private_id not in visible_ids
                assert internal_id not in visible_ids
                assert vip_id not in visible_ids

                with pytest.raises(SignalNotFoundError):
                    await query.get_detail(private_id)
                with pytest.raises(SignalNotFoundError):
                    await query.get_detail(internal_id)

                perf_rows = [
                    signal_row(symbol="P3MANUAL/USDT", scope=SignalPublicationScope.PUBLIC.value, status=SignalStatus.CLOSED.value, now=now),
                    signal_row(symbol="P3PAPER/USDT", scope=SignalPublicationScope.PRIVATE_TEST.value, status=SignalStatus.CLOSED.value, now=now),
                    signal_row(symbol="P3SHADOW/USDT", scope=SignalPublicationScope.INTERNAL.value, status=SignalStatus.CLOSED.value, now=now),
                    signal_row(symbol="P3LIVE/USDT", scope=SignalPublicationScope.PUBLIC.value, status=SignalStatus.CLOSED.value, now=now),
                ]
                perf_rows[-1]["profit_loss"] = Decimal("-3")
                perf_ids = list(
                    (
                        await session.execute(insert(Signal).values(perf_rows).returning(Signal.id))
                    ).scalars()
                )
                created_ids.extend(perf_ids)
                manual_id, paper_id, shadow_id, live_id = perf_ids

                await session.execute(
                    insert(SignalAutomationMetadata).values(
                        [
                            {
                                "signal_id": paper_id,
                                "producer": "BROOKS",
                                "generation_mode": "PAPER",
                                "exchange": "binance",
                                "market_type": "spot",
                                "timeframe": "15m",
                                "setup_type": "H2",
                                "source_signal_id": "P3-PAPER",
                                "idempotency_key": "a" * 64,
                                "market_snapshot_id": "p3-paper-snap",
                                "market_snapshot_hash": "p3-paper-hash",
                                "engine_version": "phase3-test",
                                "rule_set_version": "phase3-test",
                                "configuration_version": "phase3-test",
                                "reasoning": [],
                                "rule_ids": [],
                                "failed_rules": [],
                                "analysis_metadata": {},
                                "counts_toward_performance": False,
                            },
                            {
                                "signal_id": shadow_id,
                                "producer": "BROOKS",
                                "generation_mode": "SHADOW",
                                "exchange": "binance",
                                "market_type": "spot",
                                "timeframe": "15m",
                                "setup_type": "H2",
                                "source_signal_id": "P3-SHADOW",
                                "idempotency_key": "b" * 64,
                                "market_snapshot_id": "p3-shadow-snap",
                                "market_snapshot_hash": "p3-shadow-hash",
                                "engine_version": "phase3-test",
                                "rule_set_version": "phase3-test",
                                "configuration_version": "phase3-test",
                                "reasoning": [],
                                "rule_ids": [],
                                "failed_rules": [],
                                "analysis_metadata": {},
                                "counts_toward_performance": False,
                            },
                            {
                                "signal_id": live_id,
                                "producer": "BROOKS",
                                "generation_mode": "LIVE",
                                "exchange": "binance",
                                "market_type": "spot",
                                "timeframe": "15m",
                                "setup_type": "H2",
                                "source_signal_id": "P3-LIVE",
                                "idempotency_key": "c" * 64,
                                "market_snapshot_id": "p3-live-snap",
                                "market_snapshot_hash": "p3-live-hash",
                                "engine_version": "phase3-test",
                                "rule_set_version": "phase3-test",
                                "configuration_version": "phase3-test",
                                "reasoning": [],
                                "rule_ids": [],
                                "failed_rules": [],
                                "analysis_metadata": {},
                                "counts_toward_performance": True,
                            },
                        ]
                    )
                )

                await session.execute(
                    insert(SignalEvent).values(
                        [
                            {"signal_id": manual_id, "event_type": SignalEventType.TARGET_HIT.value, "event_metadata": {}, "created_at": now - timedelta(hours=1)},
                            {"signal_id": paper_id, "event_type": SignalEventType.STOP_HIT.value, "event_metadata": {}, "created_at": now - timedelta(hours=1)},
                            {"signal_id": shadow_id, "event_type": SignalEventType.TARGET_HIT.value, "event_metadata": {}, "created_at": now - timedelta(hours=1)},
                            {"signal_id": live_id, "event_type": SignalEventType.STOP_HIT.value, "event_metadata": {}, "created_at": now - timedelta(hours=1)},
                        ]
                    )
                )

                report = await WinRateService(
                    SQLAlchemyWinRateRepository(session),
                    clock=lambda: now,
                ).get_report(WinRatePeriod.DAILY)

                assert report.target_hit == 1
                assert report.stop_hit == 1
                assert report.winning_trades == 1
                assert report.losing_trades == 1
                assert report.evaluated_signals == 2
                assert report.win_rate == Decimal("50.00")
            finally:
                await transaction.rollback()

        async with database.session() as verify:
            remaining = await verify.scalar(
                select(func.count(Signal.id)).where(Signal.id.in_(created_ids))
            )
            assert remaining == 0
    finally:
        await database.dispose()
