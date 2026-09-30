"""Notification settings service business-rule tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.notifications.entities import NotificationPreference
from app.modules.notifications.errors import InvalidNotificationPreferenceError
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import (
    SUPPORTED_NOTIFICATION_TYPES,
    NotificationSettingsService,
)

NOW = datetime(2026, 9, 2, 1, tzinfo=UTC)


class FakeNotificationSettingsRepository:
    def __init__(self) -> None:
        self.states: dict[tuple[int, str], bool] = {}
        self.ensure_calls = 0

    async def ensure_defaults(
        self,
        *,
        user_id: int,
        notification_types: tuple[str, ...],
        changed_at: datetime,
    ) -> None:
        assert changed_at == NOW
        self.ensure_calls += 1
        for notification_type in notification_types:
            self.states.setdefault((user_id, notification_type), True)

    async def list_for_user(
        self,
        user_id: int,
        *,
        notification_types: tuple[str, ...],
    ) -> tuple[NotificationPreference, ...]:
        return tuple(
            NotificationPreference(
                notification_type=notification_type,
                is_enabled=self.states[(user_id, notification_type)],
                created_at=NOW,
                updated_at=NOW,
            )
            for notification_type in notification_types
            if (user_id, notification_type) in self.states
        )

    async def set_enabled(
        self,
        *,
        user_id: int,
        notification_type: str,
        is_enabled: bool,
        changed_at: datetime,
    ) -> bool:
        assert changed_at == NOW
        key = (user_id, notification_type)
        changed = self.states.get(key) != is_enabled
        self.states[key] = is_enabled
        return changed


async def test_first_load_creates_all_six_enabled_defaults_in_order() -> None:
    repository = FakeNotificationSettingsRepository()
    service = NotificationSettingsService(repository, clock=lambda: NOW)

    preferences = await service.get_preferences(7)

    assert tuple(item.notification_type for item in preferences) == (
        SUPPORTED_NOTIFICATION_TYPES
    )
    assert len(preferences) == 6
    assert all(item.is_enabled for item in preferences)
    assert repository.ensure_calls == 1


async def test_existing_disabled_state_is_preserved_when_defaults_are_ensured() -> None:
    repository = FakeNotificationSettingsRepository()
    repository.states[(7, NotificationType.STOP_HIT.value)] = False
    service = NotificationSettingsService(repository, clock=lambda: NOW)

    preferences = await service.get_preferences(7)
    by_type = {item.notification_type: item for item in preferences}

    assert by_type[NotificationType.STOP_HIT.value].is_enabled is False
    assert len(preferences) == 6


async def test_explicit_set_is_idempotent_and_isolated_by_user() -> None:
    repository = FakeNotificationSettingsRepository()
    service = NotificationSettingsService(repository, clock=lambda: NOW)
    await service.get_preferences(7)
    await service.get_preferences(8)

    first = await service.set_enabled(
        7,
        NotificationType.NEW_SIGNAL,
        is_enabled=False,
    )
    repeated = await service.set_enabled(
        7,
        NotificationType.NEW_SIGNAL.value,
        is_enabled=False,
    )
    user_two = await service.get_preferences(8)

    assert first.changed is True
    assert repeated.changed is False
    assert first.is_enabled is False
    assert all(item.is_enabled for item in user_two)


@pytest.mark.parametrize("user_id", (0, -1, True, "7"))
async def test_user_identifier_must_be_a_positive_integer(user_id: object) -> None:
    service = NotificationSettingsService(FakeNotificationSettingsRepository())

    with pytest.raises(InvalidNotificationPreferenceError):
        await service.get_preferences(user_id)  # type: ignore[arg-type]


async def test_unsupported_type_and_non_boolean_state_are_rejected() -> None:
    service = NotificationSettingsService(FakeNotificationSettingsRepository())

    with pytest.raises(InvalidNotificationPreferenceError, match="unsupported"):
        await service.set_enabled(7, "EMAIL", is_enabled=True)
    with pytest.raises(InvalidNotificationPreferenceError, match="boolean"):
        await service.set_enabled(
            7,
            NotificationType.NEW_SIGNAL,
            is_enabled=1,  # type: ignore[arg-type]
        )


async def test_clock_must_be_timezone_aware() -> None:
    service = NotificationSettingsService(
        FakeNotificationSettingsRepository(),
        clock=lambda: datetime(2026, 9, 2, 1),
    )

    with pytest.raises(RuntimeError, match="aware datetime"):
        await service.get_preferences(7)


async def test_incomplete_repository_result_is_rejected() -> None:
    repository = FakeNotificationSettingsRepository()
    service = NotificationSettingsService(repository, clock=lambda: NOW)

    async def incomplete_list(
        user_id: int,
        *,
        notification_types: tuple[str, ...],
    ) -> tuple[NotificationPreference, ...]:
        return ()

    repository.list_for_user = incomplete_list  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="incomplete"):
        await service.get_preferences(7)
