"""Transactional user repository test against real PostgreSQL."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.users.entities import TelegramUserIdentity
from app.modules.users.models import User, UserStatus
from app.modules.users.repository import SQLAlchemyUserRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real user repository integration test",
)


async def test_real_user_upsert_prevents_duplicates_and_updates_profile(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    telegram_user_id = 800_000_000_000_000_000 + uuid4().int % 100_000_000_000_000
    first_activity = datetime(2026, 9, 1, 8, tzinfo=UTC)
    second_activity = first_activity + timedelta(minutes=5)

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                repository = SQLAlchemyUserRepository(session)
                first = await repository.upsert(
                    TelegramUserIdentity(
                        telegram_user_id=telegram_user_id,
                        username="first_username",
                        first_name="First",
                        last_name=None,
                        language_code="fa",
                        is_bot=False,
                    ),
                    activity_at=first_activity,
                )
                second = await repository.upsert(
                    TelegramUserIdentity(
                        telegram_user_id=telegram_user_id,
                        username="updated_username",
                        first_name="Updated",
                        last_name="User",
                        language_code="en",
                        is_bot=False,
                    ),
                    activity_at=second_activity,
                )
                count = await session.scalar(
                    select(func.count(User.id)).where(User.telegram_user_id == telegram_user_id)
                )

                assert first.created is True
                assert second.created is False
                assert first.profile.id == second.profile.id
                assert second.profile.username == "updated_username"
                assert second.profile.first_name == "Updated"
                assert second.profile.last_activity == second_activity
                assert count == 1

                await session.execute(
                    update(User)
                    .where(User.id == second.profile.id)
                    .values(status=UserStatus.BLOCKED.value)
                )
                reactivated = await repository.upsert(
                    identity=TelegramUserIdentity(
                        telegram_user_id=telegram_user_id,
                        username="returned_user",
                        first_name="Returned",
                        last_name=None,
                        language_code="fa",
                        is_bot=False,
                    ),
                    activity_at=second_activity,
                )
                assert reactivated.profile.status == UserStatus.ACTIVE.value

                await session.execute(
                    update(User)
                    .where(User.id == second.profile.id)
                    .values(status=UserStatus.DEACTIVATED.value)
                )
                deactivated = await repository.upsert(
                    identity=TelegramUserIdentity(
                        telegram_user_id=telegram_user_id,
                        username="deactivated_user",
                        first_name="Deactivated",
                        last_name=None,
                        language_code="fa",
                        is_bot=False,
                    ),
                    activity_at=second_activity,
                )
                assert deactivated.profile.status == UserStatus.DEACTIVATED.value
            finally:
                await transaction.rollback()
    finally:
        await database.dispose()
