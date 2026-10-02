"""Real PostgreSQL aggregation tests for rolling win-rate reports."""

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
from app.modules.signals.models import (
    Signal,
    SignalEvent,
    SignalEventType,
    SignalStatus,
)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real win-rate integration test",
)


async def test_realized_pnl_outcome_and_rolling_boundaries(
    valid_token: str,
) -> None:
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
                outcomes = (
                    ("A", "5", timedelta(hours=1)),
                    ("B", "4", timedelta(hours=3)),
                    ("C", "-2", timedelta(minutes=30)),
                    ("D", "0", timedelta(hours=24)),
                    ("E", "8", timedelta(hours=25)),
                    ("F", "9", timedelta(0)),
                )
                signal_rows = [
                    {
                        "symbol": f"P14{letter}/USDT",
                        "direction": "LONG",
                        "entry_price": Decimal("100"),
                        "stop_loss": Decimal("90"),
                        "leverage": Decimal("2"),
                        "status": SignalStatus.CLOSED.value,
                        "description": None,
                        "profit_loss": Decimal(pnl),
                        "closed_at": now - closed_ago,
                        "created_at": now - timedelta(days=2),
                        "updated_at": now - closed_ago,
                    }
                    for letter, pnl, closed_ago in outcomes
                ]
                created_ids.extend(
                    (
                        await session.execute(
                            insert(Signal)
                            .values(signal_rows)
                            .returning(Signal.id)
                        )
                    ).scalars()
                )
                first, second, third, boundary, old, end_boundary = created_ids
                event_rows = [
                    {
                        "signal_id": first,
                        "event_type": SignalEventType.TARGET_HIT.value,
                        "event_metadata": {},
                        "created_at": now - timedelta(hours=2),
                    },
                    {
                        "signal_id": first,
                        "event_type": SignalEventType.TARGET_HIT.value,
                        "event_metadata": {},
                        "created_at": now - timedelta(hours=1),
                    },
                    {
                        "signal_id": second,
                        "event_type": SignalEventType.STOP_HIT.value,
                        "event_metadata": {},
                        "created_at": now - timedelta(hours=3),
                    },
                    {
                        "signal_id": third,
                        "event_type": SignalEventType.TARGET_HIT.value,
                        "event_metadata": {},
                        "created_at": now - timedelta(hours=4),
                    },
                    {
                        "signal_id": third,
                        "event_type": SignalEventType.STOP_HIT.value,
                        "event_metadata": {},
                        "created_at": now - timedelta(minutes=30),
                    },
                    {
                        "signal_id": boundary,
                        "event_type": SignalEventType.TARGET_HIT.value,
                        "event_metadata": {},
                        "created_at": now - timedelta(hours=24),
                    },
                    {
                        "signal_id": old,
                        "event_type": SignalEventType.TARGET_HIT.value,
                        "event_metadata": {},
                        "created_at": now - timedelta(hours=25),
                    },
                    {
                        "signal_id": end_boundary,
                        "event_type": SignalEventType.TARGET_HIT.value,
                        "event_metadata": {},
                        "created_at": now,
                    },
                ]
                await session.execute(insert(SignalEvent).values(event_rows))

                service = WinRateService(
                    SQLAlchemyWinRateRepository(session),
                    clock=lambda: now,
                )
                daily = await service.get_report(WinRatePeriod.DAILY)
                weekly = await service.get_report(WinRatePeriod.WEEKLY)

                # Daily is [now - 24h, now): the exact start is included.
                assert daily.target_hit == 2
                assert daily.stop_hit == 2
                assert daily.winning_trades == 2
                assert daily.losing_trades == 1
                assert daily.breakeven_trades == 1
                assert daily.evaluated_signals == 3
                assert daily.win_rate == Decimal("66.67")
                # A profitable STOP is a WIN, while a losing TARGET would be a LOSS.
                assert daily.stop_profit_exits == 1
                assert weekly.target_hit == 3
                assert weekly.stop_hit == 2
                assert weekly.winning_trades == 3
                assert weekly.losing_trades == 1
                assert weekly.breakeven_trades == 1
                assert weekly.evaluated_signals == 4
                assert weekly.win_rate == Decimal("75.00")
            finally:
                await transaction.rollback()

        async with database.session() as verification:
            remaining = await verification.scalar(
                select(func.count(Signal.id)).where(Signal.id.in_(created_ids))
            )
            assert remaining == 0
    finally:
        await database.dispose()
