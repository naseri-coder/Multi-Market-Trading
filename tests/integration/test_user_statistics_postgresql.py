"""Transactional user-statistics test against real PostgreSQL."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.users.models import User, UserStatus
from app.modules.users.statistics_repository import SQLAlchemyUserStatisticsRepository
from app.modules.users.statistics_service import UserStatisticsService

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real user statistics integration test",
)


async def test_real_statistics_query_counts_each_required_bucket(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    now = datetime(2026, 9, 16, 8, 30, tzinfo=UTC)
    base_id = 800_000_000_000_000_000 + uuid4().int % 100_000_000_000_000
    telegram_ids = [base_id + index for index in range(6)]

    rows = [
        {
            "telegram_user_id": telegram_ids[0],
            "first_name": "Today Active",
            "status": UserStatus.ACTIVE.value,
            "created_at": now - timedelta(hours=1),
            "updated_at": now,
            "last_activity": now,
        },
        {
            "telegram_user_id": telegram_ids[1],
            "first_name": "Week Active",
            "status": UserStatus.ACTIVE.value,
            "created_at": now - timedelta(days=2),
            "updated_at": now,
            "last_activity": now,
        },
        {
            "telegram_user_id": telegram_ids[2],
            "first_name": "Month Active",
            "status": UserStatus.ACTIVE.value,
            "created_at": now - timedelta(days=10),
            "updated_at": now,
            "last_activity": now,
        },
        {
            "telegram_user_id": telegram_ids[3],
            "first_name": "Stale Active",
            "status": UserStatus.ACTIVE.value,
            "created_at": now - timedelta(days=60),
            "updated_at": now,
            "last_activity": now - timedelta(days=31),
        },
        {
            "telegram_user_id": telegram_ids[4],
            "first_name": "Deactivated Recent",
            "status": UserStatus.DEACTIVATED.value,
            "created_at": now - timedelta(days=60),
            "updated_at": now,
            "last_activity": now,
        },
        {
            "telegram_user_id": telegram_ids[5],
            "first_name": "Blocked Recent",
            "status": UserStatus.BLOCKED.value,
            "created_at": now - timedelta(days=60),
            "updated_at": now,
            "last_activity": now,
        },
    ]

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                repository = SQLAlchemyUserStatisticsRepository(session)
                service = UserStatisticsService(repository, clock=lambda: now)
                before = await service.get_dashboard_statistics()

                await session.execute(insert(User).values(rows))
                after = await service.get_dashboard_statistics()

                assert after.total_users == before.total_users + 6
                assert after.active_users == before.active_users + 3
                assert after.inactive_users == before.inactive_users + 3
                assert after.new_users_today == before.new_users_today + 1
                assert after.new_users_this_week == before.new_users_this_week + 2
                assert after.new_users_this_month == before.new_users_this_month + 3
            finally:
                await transaction.rollback()

        async with database.session() as session:
            remaining = await session.scalar(
                select(func.count(User.id)).where(User.telegram_user_id.in_(telegram_ids))
            )
            assert remaining == 0
    finally:
        await database.dispose()
