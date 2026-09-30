"""Public notification-settings module surface."""

from app.modules.notifications.entities import (
    NotificationPreference,
    NotificationPreferenceMutation,
)
from app.modules.notifications.errors import (
    InvalidNotificationPreferenceError,
    NotificationSettingsError,
    NotificationSettingsRepositoryError,
)
from app.modules.notifications.models import NotificationType, UserNotificationSetting
from app.modules.notifications.repository import (
    NotificationSettingsRepository,
    SQLAlchemyNotificationSettingsRepository,
)
from app.modules.notifications.service import (
    SUPPORTED_NOTIFICATION_TYPES,
    NotificationSettingsService,
)

__all__ = [
    "InvalidNotificationPreferenceError",
    "NotificationPreference",
    "NotificationPreferenceMutation",
    "NotificationSettingsError",
    "NotificationSettingsRepository",
    "NotificationSettingsRepositoryError",
    "NotificationSettingsService",
    "NotificationType",
    "SQLAlchemyNotificationSettingsRepository",
    "SUPPORTED_NOTIFICATION_TYPES",
    "UserNotificationSetting",
]
