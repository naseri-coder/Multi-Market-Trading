"""Notification settings repository error-boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.modules.notifications.errors import NotificationSettingsRepositoryError
from app.modules.notifications.repository import (
    SQLAlchemyNotificationSettingsRepository,
)

NOW = datetime(2026, 9, 2, 1, tzinfo=UTC)
TYPES = ("NEW_SIGNAL", "TARGET_HIT")


async def test_default_initialization_maps_database_error() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=SQLAlchemyError("sensitive database detail"))
    )
    repository = SQLAlchemyNotificationSettingsRepository(session)

    with pytest.raises(NotificationSettingsRepositoryError) as captured:
        await repository.ensure_defaults(
            user_id=7,
            notification_types=TYPES,
            changed_at=NOW,
        )

    assert "sensitive database detail" not in str(captured.value)


async def test_list_maps_database_error() -> None:
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=SQLAlchemyError("sensitive database detail"))
    )
    repository = SQLAlchemyNotificationSettingsRepository(session)

    with pytest.raises(NotificationSettingsRepositoryError) as captured:
        await repository.list_for_user(
            7,
            notification_types=TYPES,
        )

    assert "sensitive database detail" not in str(captured.value)


async def test_explicit_update_maps_database_error() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=SQLAlchemyError("sensitive database detail"))
    )
    repository = SQLAlchemyNotificationSettingsRepository(session)

    with pytest.raises(NotificationSettingsRepositoryError) as captured:
        await repository.set_enabled(
            user_id=7,
            notification_type="NEW_SIGNAL",
            is_enabled=False,
            changed_at=NOW,
        )

    assert "sensitive database detail" not in str(captured.value)
