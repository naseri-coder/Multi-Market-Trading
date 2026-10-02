"""Transactional SignalService integration tests against real PostgreSQL."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.signals.entities import CreateSignal, UpdateSignal
from app.modules.signals.errors import InvalidSignalError, SignalStateError
from app.modules.signals.models import (
    Signal,
    SignalEvent,
    SignalEventType,
    SignalStatus,
    SignalTarget,
    SignalTargetStatus,
)
from app.modules.signals.repository import SQLAlchemySignalRepository
from app.modules.signals.service import SignalService

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real signal service integration test",
)


async def test_signal_service_complete_lifecycle_and_rollback(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    clock_value = [datetime(2026, 9, 1, 20, tzinfo=UTC)]
    symbols = ("PH12LONG/USDT", "PH12DRAFT/USDT", "PH12CANCEL/USDT")

    def clock() -> datetime:
        value = clock_value[0]
        clock_value[0] += timedelta(microseconds=1)
        return value

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                service = SignalService(SQLAlchemySignalRepository(session), clock=clock)

                draft = await service.create_signal(
                    CreateSignal(
                        symbol="ph12draft/usdt",
                        direction="LONG",
                        entry_price="200",
                        stop_loss="180",
                        leverage="3.25",
                        description="Draft before update",
                        as_draft=True,
                    )
                )
                assert draft.status == SignalStatus.DRAFT.value
                draft = await service.update_signal(
                    draft.id,
                    UpdateSignal(
                        symbol="PH12DRAFT/USDT",
                        entry_price="210",
                        stop_loss="190",
                        leverage="4.50",
                        clear_description=True,
                    ),
                )
                assert draft.entry_price == Decimal("210.000000000000000000")
                assert draft.description is None

                draft_target = await service.add_target(draft.id, target_price="220")
                assert draft_target.target_number == 1
                with pytest.raises(SignalStateError):
                    await service.hit_target(draft.id, draft_target.id, profit_loss="1")

                long_signal = await service.create_signal(
                    CreateSignal(
                        symbol="ph12long/usdt",
                        direction="long",
                        entry_price="100",
                        stop_loss="90",
                        leverage="5",
                        description="Phase 12 lifecycle",
                    )
                )
                assert long_signal.status == SignalStatus.OPEN.value

                first = await service.add_target(long_signal.id, target_price="110")
                second = await service.add_target(long_signal.id, target_price="120")
                third = await service.add_target(long_signal.id, target_price="130")
                assert [first.target_number, second.target_number, third.target_number] == [1, 2, 3]

                with pytest.raises(SignalStateError, match="Earlier"):
                    await service.hit_target(long_signal.id, second.id, profit_loss="4.00")

                first = await service.hit_target(long_signal.id, first.id, profit_loss="2.50")
                second = await service.hit_target(long_signal.id, second.id, profit_loss="4.75")
                assert first.status == SignalTargetStatus.HIT.value
                assert second.profit_loss == Decimal("4.75000000")

                long_signal = await service.update_stop_loss(
                    long_signal.id,
                    stop_loss="105",
                )
                assert long_signal.stop_loss == Decimal("105.000000000000000000")

                with pytest.raises(SignalStateError):
                    await service.update_stop_loss(long_signal.id, stop_loss="104")
                with pytest.raises(SignalStateError):
                    await service.update_signal(
                        long_signal.id,
                        UpdateSignal(entry_price="101"),
                    )

                long_signal = await service.update_signal(
                    long_signal.id,
                    UpdateSignal(symbol="PH12LONG/USDT", description="Updated lifecycle"),
                )
                assert long_signal.description == "Updated lifecycle"

                long_signal = await service.close_signal(
                    long_signal.id,
                    profit_loss="7.125",
                )
                assert long_signal.status == SignalStatus.CLOSED.value
                assert long_signal.profit_loss == Decimal("7.12500000")
                assert long_signal.closed_at is not None

                third = await session.scalar(
                    select(SignalTarget).where(SignalTarget.id == third.id)
                )
                assert third is not None
                assert third.status == SignalTargetStatus.CANCELLED.value

                history = await service.signal_history(long_signal.id, limit=50)
                assert history[0].event_type == SignalEventType.CLOSED.value
                assert {event.event_type for event in history} == {
                    SignalEventType.CREATED.value,
                    SignalEventType.TARGET_ADDED.value,
                    SignalEventType.TARGET_HIT.value,
                    SignalEventType.STOP_LOSS_UPDATED.value,
                    SignalEventType.UPDATED.value,
                    SignalEventType.CLOSED.value,
                }
                assert history[0].metadata["profit_loss"] == "7.125"

                with pytest.raises(SignalStateError):
                    await service.close_signal(long_signal.id, profit_loss="8")
                with pytest.raises(SignalStateError):
                    await service.add_target(long_signal.id, target_price="140")

                cancelled_signal = await service.create_signal(
                    CreateSignal(
                        symbol="PH12CANCEL/USDT",
                        direction="SHORT",
                        entry_price="100",
                        stop_loss="110",
                        leverage="2",
                    )
                )
                cancelled_signal = await service.cancel_signal(cancelled_signal.id)
                assert cancelled_signal.status == SignalStatus.CANCELLED.value

                with pytest.raises(InvalidSignalError):
                    await service.create_signal(
                        CreateSignal("INVALID", "LONG", "100", "101", "2")
                    )

                target_count = await session.scalar(
                    select(func.count(SignalTarget.id)).where(
                        SignalTarget.signal_id == long_signal.id
                    )
                )
                event_count = await session.scalar(
                    select(func.count(SignalEvent.id)).where(
                        SignalEvent.signal_id == long_signal.id
                    )
                )
                assert target_count == 3
                assert event_count == 9
            finally:
                await transaction.rollback()

        async with database.session() as verification_session:
            remaining = await verification_session.scalar(
                select(func.count(Signal.id)).where(Signal.symbol.in_(symbols))
            )
            assert remaining == 0
    finally:
        await database.dispose()
