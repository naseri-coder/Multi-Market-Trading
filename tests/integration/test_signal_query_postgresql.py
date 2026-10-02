"""Real PostgreSQL tests for Phase 13 public signal queries."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.signals.entities import SignalListMode
from app.modules.signals.errors import SignalNotFoundError
from app.modules.signals.models import (
    Signal,
    SignalDirection,
    SignalStatus,
    SignalTarget,
    SignalTargetStatus,
)
from app.modules.signals.query_service import SignalQueryService
from app.modules.signals.repository import SQLAlchemySignalRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real signal query integration test",
)


async def test_public_collections_detail_pagination_and_draft_visibility(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    now = datetime(2026, 9, 2, 12, tzinfo=UTC)
    created_ids: list[int] = []

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                open_rows = []
                for index in range(12):
                    created_at = (
                        now - timedelta(hours=index + 1)
                        if index < 2
                        else now - timedelta(hours=48 + index)
                    )
                    open_rows.append(
                        {
                            "symbol": f"P13O{index}/USDT",
                            "direction": SignalDirection.LONG.value,
                            "entry_price": Decimal("100"),
                            "stop_loss": Decimal("90"),
                            "leverage": Decimal("2"),
                            "status": SignalStatus.OPEN.value,
                            "created_at": created_at,
                            "updated_at": created_at,
                        }
                    )
                created_ids.extend(
                    (
                        await session.execute(
                            insert(Signal).values(open_rows).returning(Signal.id)
                        )
                    ).scalars()
                )

                terminal_rows = [
                    {
                        "symbol": "P13CLOSED/USDT",
                        "direction": SignalDirection.LONG.value,
                        "entry_price": Decimal("100"),
                        "stop_loss": Decimal("95"),
                        "leverage": Decimal("2"),
                        "status": SignalStatus.CLOSED.value,
                        "profit_loss": Decimal("5.25"),
                        "closed_at": now - timedelta(minutes=30),
                        "created_at": now - timedelta(hours=3),
                        "updated_at": now - timedelta(minutes=30),
                    },
                    {
                        "symbol": "P13OLD/USDT",
                        "direction": SignalDirection.SHORT.value,
                        "entry_price": Decimal("100"),
                        "stop_loss": Decimal("105"),
                        "leverage": Decimal("3"),
                        "status": SignalStatus.CLOSED.value,
                        "profit_loss": Decimal("-1.25"),
                        "closed_at": now - timedelta(hours=70),
                        "created_at": now - timedelta(hours=72),
                        "updated_at": now - timedelta(hours=70),
                    },
                    {
                        "symbol": "P13CANCEL/USDT",
                        "direction": SignalDirection.LONG.value,
                        "entry_price": Decimal("100"),
                        "stop_loss": Decimal("90"),
                        "leverage": Decimal("1"),
                        "status": SignalStatus.CANCELLED.value,
                        "profit_loss": None,
                        "closed_at": now - timedelta(hours=1),
                        "created_at": now - timedelta(hours=4),
                        "updated_at": now - timedelta(hours=1),
                    },
                    {
                        "symbol": "P13DRAFT/USDT",
                        "direction": SignalDirection.LONG.value,
                        "entry_price": Decimal("100"),
                        "stop_loss": Decimal("90"),
                        "leverage": Decimal("1"),
                        "status": SignalStatus.DRAFT.value,
                        "profit_loss": None,
                        "closed_at": None,
                        "created_at": now - timedelta(minutes=5),
                        "updated_at": now - timedelta(minutes=5),
                    },
                ]
                terminal_ids = list(
                    (
                        await session.execute(
                            insert(Signal).values(terminal_rows).returning(Signal.id)
                        )
                    ).scalars()
                )
                created_ids.extend(terminal_ids)

                detail_signal_id = created_ids[0]
                await session.execute(
                    insert(SignalTarget).values(
                        [
                            {
                                "signal_id": detail_signal_id,
                                "target_number": number,
                                "target_price": Decimal(100 + number),
                                "status": SignalTargetStatus.PENDING.value,
                                "hit_at": None,
                                "profit_loss": None,
                            }
                            for number in range(1, 13)
                        ]
                    )
                )

                service = SignalQueryService(
                    SQLAlchemySignalRepository(session),
                    clock=lambda: now,
                )
                live = await service.get_page(SignalListMode.LIVE.value)
                opened_first = await service.get_page(SignalListMode.OPEN.value)
                opened_second = await service.get_page(SignalListMode.OPEN.value, page=2)
                opened_clamped = await service.get_page(
                    SignalListMode.OPEN.value,
                    page=99,
                )
                history = await service.get_page(SignalListMode.HISTORY.value)

                assert live.total_items == 4
                assert all(item.status != SignalStatus.DRAFT.value for item in live.signals)
                assert opened_first.total_items == 12
                assert len(opened_first.signals) == 10
                assert len(opened_second.signals) == 2
                assert opened_clamped.page == 2
                assert len(opened_clamped.signals) == 2
                assert history.total_items == 3
                assert {item.status for item in history.signals} == {
                    SignalStatus.CLOSED.value,
                    SignalStatus.CANCELLED.value,
                }

                detail_first = await service.get_detail(detail_signal_id)
                detail_second = await service.get_detail(detail_signal_id, target_page=2)
                detail_clamped = await service.get_detail(detail_signal_id, target_page=99)
                assert len(detail_first.targets) == 10
                assert [item.target_number for item in detail_second.targets] == [11, 12]
                assert detail_clamped.target_page == 2
                assert detail_first.total_targets == 12

                with pytest.raises(SignalNotFoundError):
                    await service.get_detail(terminal_ids[-1])
            finally:
                await transaction.rollback()

        async with database.session() as verification_session:
            remaining = await verification_session.scalar(
                select(func.count(Signal.id)).where(Signal.id.in_(created_ids))
            )
            assert remaining == 0
    finally:
        await database.dispose()
