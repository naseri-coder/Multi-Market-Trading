"""Real PostgreSQL tests for Phase 15 user favorites."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.favorites.errors import FavoriteSignalNotFoundError
from app.modules.favorites.models import UserFavorite
from app.modules.favorites.repository import SQLAlchemyFavoriteRepository
from app.modules.favorites.service import FavoriteService
from app.modules.signals.models import Signal, SignalStatus
from app.modules.users.models import User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real favorites integration test",
)


async def test_favorites_are_idempotent_isolated_paginated_and_cascade_safe(
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
    now = datetime(2099, 9, 1, 20, tzinfo=UTC)
    suffix = uuid4().hex[:8].upper()
    telegram_base = 700_000_000_000_000_000 + uuid4().int % 100_000_000_000_000
    created_signal_ids: list[int] = []

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                user_ids = list(
                    (
                        await session.execute(
                            insert(User)
                            .values(
                                [
                                    {
                                        "telegram_user_id": telegram_base,
                                        "first_name": "Phase15 First",
                                        "last_activity": now,
                                    },
                                    {
                                        "telegram_user_id": telegram_base + 1,
                                        "first_name": "Phase15 Second",
                                        "last_activity": now,
                                    },
                                ]
                            )
                            .returning(User.id)
                        )
                    ).scalars()
                )
                signal_rows = [
                    {
                        "symbol": f"P15{suffix}{index}/USDT",
                        "direction": "LONG",
                        "entry_price": Decimal("100"),
                        "stop_loss": Decimal("90"),
                        "leverage": Decimal("2"),
                        "status": SignalStatus.OPEN.value,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for index in range(12)
                ]
                signal_rows.append(
                    {
                        "symbol": f"P15{suffix}DRAFT/USDT",
                        "direction": "LONG",
                        "entry_price": Decimal("100"),
                        "stop_loss": Decimal("90"),
                        "leverage": Decimal("2"),
                        "status": SignalStatus.DRAFT.value,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                created_signal_ids.extend(
                    (
                        await session.execute(
                            insert(Signal)
                            .values(signal_rows)
                            .returning(Signal.id)
                        )
                    ).scalars()
                )
                public_ids = created_signal_ids[:-1]
                draft_id = created_signal_ids[-1]
                service = FavoriteService(
                    SQLAlchemyFavoriteRepository(session),
                    clock=lambda: now,
                )

                for signal_id in public_ids:
                    result = await service.add(user_ids[0], signal_id)
                    assert result.changed is True
                duplicate = await service.add(user_ids[0], public_ids[0])
                await service.add(user_ids[1], public_ids[0])

                assert duplicate.changed is False
                assert await service.is_favorite(user_ids[0], public_ids[0]) is True
                first = await service.get_page(user_ids[0], page=1)
                second = await service.get_page(user_ids[0], page=2)
                clamped = await service.get_page(user_ids[0], page=99)
                isolated = await service.get_page(user_ids[1])
                assert (len(first.signals), len(second.signals)) == (10, 2)
                assert first.total_items == 12
                assert clamped.page == 2
                assert isolated.total_items == 1

                with pytest.raises(FavoriteSignalNotFoundError):
                    await service.add(user_ids[0], draft_id)

                removed = await service.remove(user_ids[0], public_ids[0])
                repeated = await service.remove(user_ids[0], public_ids[0])
                assert removed.changed is True
                assert repeated.changed is False

                cascade_signal_id = public_ids[1]
                await session.execute(
                    delete(Signal).where(Signal.id == cascade_signal_id)
                )
                signal_favorite_count = await session.scalar(
                    select(func.count(UserFavorite.id)).where(
                        UserFavorite.signal_id == cascade_signal_id
                    )
                )
                assert signal_favorite_count == 0

                await session.execute(delete(User).where(User.id == user_ids[1]))
                user_favorite_count = await session.scalar(
                    select(func.count(UserFavorite.id)).where(
                        UserFavorite.user_id == user_ids[1]
                    )
                )
                assert user_favorite_count == 0
            finally:
                await transaction.rollback()

        async with database.session() as verification:
            remaining_users = await verification.scalar(
                select(func.count(User.id)).where(
                    User.telegram_user_id.in_((telegram_base, telegram_base + 1))
                )
            )
            remaining_signals = await verification.scalar(
                select(func.count(Signal.id)).where(
                    Signal.id.in_(created_signal_ids)
                )
            )
            assert remaining_users == 0
            assert remaining_signals == 0
    finally:
        await database.dispose()
