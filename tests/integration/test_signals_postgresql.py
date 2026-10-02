"""Transactional Phase 11 signal-schema checks against real PostgreSQL."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.signals.models import (
    Signal,
    SignalDirection,
    SignalEvent,
    SignalEventType,
    SignalStatus,
    SignalTarget,
    SignalTargetStatus,
)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real signal integration test",
)


async def test_signal_schema_constraints_precision_and_cascade(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    now = datetime(2026, 9, 1, 18, tzinfo=UTC)
    signal_id: int | None = None

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                signal_id = (
                    await session.execute(
                        insert(Signal)
                        .values(
                            symbol="BTC/USDT",
                            direction=SignalDirection.LONG.value,
                            entry_price=Decimal("61234.123456789012345678"),
                            stop_loss=Decimal("60000.000000000000000001"),
                            leverage=Decimal("5.50"),
                            status=SignalStatus.OPEN.value,
                            description="Phase 11 schema validation",
                        )
                        .returning(Signal.id)
                    )
                ).scalar_one()

                await session.execute(
                    insert(SignalTarget).values(
                        [
                            {
                                "signal_id": signal_id,
                                "target_number": 1,
                                "target_price": Decimal("62000.000000000000000001"),
                                "status": SignalTargetStatus.PENDING.value,
                                "hit_at": None,
                                "profit_loss": None,
                            },
                            {
                                "signal_id": signal_id,
                                "target_number": 2,
                                "target_price": Decimal("63000.000000000000000002"),
                                "status": SignalTargetStatus.HIT.value,
                                "hit_at": now,
                                "profit_loss": Decimal("2.87500000"),
                            },
                        ]
                    )
                )
                await session.execute(
                    insert(SignalEvent).values(
                        [
                            {
                                "signal_id": signal_id,
                                "event_type": SignalEventType.CREATED.value,
                                "event_metadata": {"source": "phase11-test"},
                            },
                            {
                                "signal_id": signal_id,
                                "event_type": SignalEventType.TARGET_HIT.value,
                                "event_metadata": {"target_number": 2},
                            },
                        ]
                    )
                )

                stored_signal = await session.scalar(
                    select(Signal).where(Signal.id == signal_id)
                )
                assert stored_signal is not None
                assert stored_signal.entry_price == Decimal("61234.123456789012345678")
                assert stored_signal.leverage == Decimal("5.50")
                assert stored_signal.closed_at is None

                targets = (
                    (
                        await session.execute(
                            select(SignalTarget)
                            .where(SignalTarget.signal_id == signal_id)
                            .order_by(SignalTarget.target_number)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert [target.target_number for target in targets] == [1, 2]
                assert targets[1].profit_loss == Decimal("2.87500000")

                events = (
                    (
                        await session.execute(
                            select(SignalEvent)
                            .where(SignalEvent.signal_id == signal_id)
                            .order_by(SignalEvent.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert events[0].event_metadata == {"source": "phase11-test"}
                assert events[1].event_metadata == {"target_number": 2}

                async def assert_rejected(statement) -> None:
                    with pytest.raises(IntegrityError):
                        async with session.begin_nested():
                            await session.execute(statement)

                await assert_rejected(
                    insert(Signal).values(
                        symbol="ETH/USDT",
                        direction="SIDEWAYS",
                        entry_price=Decimal("100"),
                        stop_loss=Decimal("90"),
                        leverage=Decimal("2"),
                        status=SignalStatus.OPEN.value,
                    )
                )
                await assert_rejected(
                    insert(SignalTarget).values(
                        signal_id=signal_id,
                        target_number=1,
                        target_price=Decimal("64000"),
                    )
                )
                await assert_rejected(
                    insert(SignalTarget).values(
                        signal_id=signal_id,
                        target_number=3,
                        target_price=Decimal("64000"),
                        status=SignalTargetStatus.HIT.value,
                    )
                )
                await assert_rejected(
                    insert(SignalEvent).values(
                        signal_id=signal_id,
                        event_type=SignalEventType.UPDATED.value,
                        event_metadata=["not", "an", "object"],
                    )
                )

                await session.execute(delete(Signal).where(Signal.id == signal_id))
                target_count = await session.scalar(
                    select(func.count(SignalTarget.id)).where(
                        SignalTarget.signal_id == signal_id
                    )
                )
                event_count = await session.scalar(
                    select(func.count(SignalEvent.id)).where(SignalEvent.signal_id == signal_id)
                )
                assert target_count == 0
                assert event_count == 0
            finally:
                await transaction.rollback()

        async with database.session() as verification_session:
            remaining = await verification_session.scalar(
                select(func.count(Signal.id)).where(Signal.id == signal_id)
            )
            assert remaining == 0
    finally:
        await database.dispose()
