"""Safe notification-settings exception hierarchy."""


class NotificationSettingsError(Exception):
    """Base error safe for adapter-level handling."""


class InvalidNotificationPreferenceError(NotificationSettingsError):
    """Raised when a preference command is malformed or unsupported."""


class NotificationSettingsRepositoryError(NotificationSettingsError):
    """Raised when preference persistence cannot complete safely."""
