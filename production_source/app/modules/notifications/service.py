"""Notification preference rules independent from Telegram and SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.notifications.entities import (
    NotificationPreference,
    NotificationPreferenceMutation,
)
from app.modules.notifications.errors import InvalidNotificationPreferenceError
from app.modules.notifications.models import NotificationType
from app.modules.notifications.repository import NotificationSettingsRepository

NotificationSettingsClock = Callable[[], datetime]
SUPPORTED_NOTIFICATION_TYPES = tuple(item.value for item in NotificationType)


def utc_now() -> datetime:
    return datetime.now(UTC)


class NotificationSettingsService:
    """Own supported types, default state, validation, and idempotent writes."""

    def __init__(
        self,
        repository: NotificationSettingsRepository,
        *,
        clock: NotificationSettingsClock = utc_now,
    ) -> None:
        self.repository = repository
        self.clock = clock

    async def get_preferences(
        self,
        user_id: int,
    ) -> tuple[NotificationPreference, ...]:
        self._validate_user_id(user_id)
        changed_at = self._now()
        await self.repository.ensure_defaults(
            user_id=user_id,
            notification_types=SUPPORTED_NOTIFICATION_TYPES,
            changed_at=changed_at,
        )
        preferences = await self.repository.list_for_user(
            user_id,
            notification_types=SUPPORTED_NOTIFICATION_TYPES,
        )
        actual_types = tuple(item.notification_type for item in preferences)
        if actual_types != SUPPORTED_NOTIFICATION_TYPES:
            raise RuntimeError(
                "Notification repository returned an incomplete preference set"
            )
        return preferences

    async def set_enabled(
        self,
        user_id: int,
        notification_type: NotificationType | str,
        *,
        is_enabled: bool,
    ) -> NotificationPreferenceMutation:
        self._validate_user_id(user_id)
        normalized_type = self._normalize_type(notification_type)
        if not isinstance(is_enabled, bool):
            raise InvalidNotificationPreferenceError(
                "Notification enabled state must be boolean"
            )
        changed = await self.repository.set_enabled(
            user_id=user_id,
            notification_type=normalized_type,
            is_enabled=is_enabled,
            changed_at=self._now(),
        )
        return NotificationPreferenceMutation(
            notification_type=normalized_type,
            is_enabled=is_enabled,
            changed=changed,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError(
                "NotificationSettingsService clock must return an aware datetime"
            )
        return value.astimezone(UTC)

    @staticmethod
    def _validate_user_id(user_id: int) -> None:
        if (
            not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            raise InvalidNotificationPreferenceError(
                "User identifier must be a positive integer"
            )

    @staticmethod
    def _normalize_type(notification_type: NotificationType | str) -> str:
        try:
            return NotificationType(notification_type).value
        except (TypeError, ValueError) as exc:
            raise InvalidNotificationPreferenceError(
                "Notification type is unsupported"
            ) from exc
