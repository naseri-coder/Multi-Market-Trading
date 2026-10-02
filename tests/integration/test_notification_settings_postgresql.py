"""Real PostgreSQL tests for Phase 16 notification settings."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.notifications.models import (
    NotificationType,
    UserNotificationSetting,
)
from app.modules.notifications.repository import (
    SQLAlchemyNotificationSettingsRepository,
)
from app.modules.notifications.service import NotificationSettingsService
from app.modules.users.models import User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "TEST_DATABASE_URL is required for the real notification settings "
        "integration test"
    ),
)


async def test_defaults_idempotency_isolation_constraints_and_user_cascade(
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
    now = datetime(2099, 9, 2, 1, tzinfo=UTC)
    telegram_base = (
        710_000_000_000_000_000
        + uuid4().int % 100_000_000_000_000
    )

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
                                        "first_name": "Phase16 First",
                                        "last_activity": now,
                                    },
                                    {
                                        "telegram_user_id": telegram_base + 1,
                                        "first_name": "Phase16 Second",
                                        "last_activity": now,
                                    },
                                ]
                            )
                            .returning(User.id)
                        )
                    ).scalars()
                )
                service = NotificationSettingsService(
                    SQLAlchemyNotificationSettingsRepository(session),
                    clock=lambda: now,
                )

                first_defaults = await service.get_preferences(user_ids[0])
                assert len(first_defaults) == 6
                assert all(item.is_enabled for item in first_defaults)

                disabled = await service.set_enabled(
                    user_ids[0],
                    NotificationType.NEW_SIGNAL,
                    is_enabled=False,
                )
                repeated = await service.set_enabled(
                    user_ids[0],
                    NotificationType.NEW_SIGNAL,
                    is_enabled=False,
                )
                assert disabled.changed is True
                assert repeated.changed is False

                second_defaults = await service.get_preferences(user_ids[1])
                assert len(second_defaults) == 6
                assert all(item.is_enabled for item in second_defaults)

                await session.execute(
                    delete(UserNotificationSetting).where(
                        UserNotificationSetting.user_id == user_ids[0],
                        UserNotificationSetting.notification_type.in_(
                            (
                                NotificationType.TARGET_HIT.value,
                                NotificationType.STOP_HIT.value,
                            )
                        ),
                    )
                )
                repaired = await service.get_preferences(user_ids[0])
                repaired_by_type = {
                    item.notification_type: item for item in repaired
                }
                assert len(repaired) == 6
                assert (
                    repaired_by_type[
                        NotificationType.NEW_SIGNAL.value
                    ].is_enabled
                    is False
                )
                assert (
                    repaired_by_type[
                        NotificationType.TARGET_HIT.value
                    ].is_enabled
                    is True
                )

                async def assert_rejected(statement) -> None:
                    with pytest.raises(IntegrityError):
                        async with session.begin_nested():
                            await session.execute(statement)

                await assert_rejected(
                    insert(UserNotificationSetting).values(
                        user_id=user_ids[0],
                        notification_type="EMAIL",
                        is_enabled=True,
                    )
                )
                await assert_rejected(
                    insert(UserNotificationSetting).values(
                        user_id=user_ids[0],
                        notification_type=NotificationType.NEW_SIGNAL.value,
                        is_enabled=True,
                    )
                )

                first_count = await session.scalar(
                    select(func.count(UserNotificationSetting.id)).where(
                        UserNotificationSetting.user_id == user_ids[0]
                    )
                )
                second_count = await session.scalar(
                    select(func.count(UserNotificationSetting.id)).where(
                        UserNotificationSetting.user_id == user_ids[1]
                    )
                )
                assert first_count == 6
                assert second_count == 6

                await session.execute(
                    delete(User).where(User.id == user_ids[1])
                )
                cascade_count = await session.scalar(
                    select(func.count(UserNotificationSetting.id)).where(
                        UserNotificationSetting.user_id == user_ids[1]
                    )
                )
                assert cascade_count == 0
            finally:
                await transaction.rollback()

        async with database.session() as verification:
            remaining_users = await verification.scalar(
                select(func.count(User.id)).where(
                    User.telegram_user_id.in_(
                        (telegram_base, telegram_base + 1)
                    )
                )
            )
            assert remaining_users == 0
    finally:
        await database.dispose()
