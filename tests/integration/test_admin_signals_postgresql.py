"""Real PostgreSQL coverage for the Phase 20 administrator signal panel."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.signals.admin_query_service import AdminSignalQueryService
from app.modules.signals.entities import AdminSignalListMode, CreateSignal, UpdateSignal
from app.modules.signals.models import Signal, SignalEvent, SignalEventType, SignalStatus
from app.modules.signals.repository import SQLAlchemySignalRepository
from app.modules.signals.service import SignalService

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real admin signal integration test",
)


async def test_admin_signal_lifecycle_pagination_targets_and_rollback(
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
    clock_value = [datetime(2099, 9, 2, 8, tzinfo=UTC)]
    symbols = tuple(f"PH20-{number:02d}/USDT" for number in range(1, 14))

    def clock() -> datetime:
        value = clock_value[0]
        clock_value[0] += timedelta(microseconds=1)
        return value

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                repository = SQLAlchemySignalRepository(session)
                service = SignalService(repository, clock=clock)
                query = AdminSignalQueryService(repository)

                drafts = [
                    await service.create_signal(
                        CreateSignal(
                            symbol=symbol,
                            direction="LONG",
                            entry_price="100",
                            stop_loss="90",
                            leverage="5",
                            description="Phase 20 administrator panel",
                            as_draft=True,
                        )
                    )
                    for symbol in symbols[:12]
                ]
                first_page = await query.get_page(
                    AdminSignalListMode.DRAFTS.value,
                    page=1,
                )
                second_page = await query.get_page(
                    AdminSignalListMode.DRAFTS.value,
                    page=2,
                )
                assert len(first_page.signals) == 10
                assert first_page.total_items >= 12
                assert any(item.id == drafts[0].id for item in second_page.signals)

                managed = drafts[-1]
                targets = [
                    await service.add_target(
                        managed.id,
                        target_price=Decimal(110 + number),
                    )
                    for number in range(12)
                ]
                target_first = await query.get_detail(managed.id, target_page=1)
                target_second = await query.get_detail(managed.id, target_page=2)
                assert len(target_first.targets) == 10
                assert len(target_second.targets) == 2

                managed = await service.update_signal(
                    managed.id,
                    UpdateSignal(symbol=symbols[11], description="Edited before publish"),
                )
                managed = await service.publish_signal(managed.id)
                assert managed.status == SignalStatus.OPEN.value
                active = await query.get_page(AdminSignalListMode.ACTIVE.value)
                assert any(item.id == managed.id for item in active.signals)

                first_target = await service.hit_target(
                    managed.id,
                    targets[0].id,
                    profit_loss="2.50",
                )
                assert first_target.profit_loss == Decimal("2.50000000")
                managed = await service.update_stop_loss(managed.id, stop_loss="101")
                assert managed.stop_loss == Decimal("101.000000000000000000")
                managed = await service.close_signal(managed.id, profit_loss="3.25")
                assert managed.status == SignalStatus.CLOSED.value

                cancelled = await service.cancel_signal(drafts[-2].id)
                assert cancelled.status == SignalStatus.CANCELLED.value
                history = await query.get_page(AdminSignalListMode.HISTORY.value)
                history_ids = {item.id for item in history.signals}
                assert {managed.id, cancelled.id} <= history_ids

                published_events = await session.scalar(
                    select(func.count(SignalEvent.id)).where(
                        SignalEvent.signal_id == managed.id,
                        SignalEvent.event_type == SignalEventType.PUBLISHED.value,
                    )
                )
                assert published_events == 1
            finally:
                await transaction.rollback()

        async with database.session() as verification:
            remaining = await verification.scalar(
                select(func.count(Signal.id)).where(Signal.symbol.in_(symbols))
            )
            assert remaining == 0
    finally:
        await database.dispose()
