"""User notification-settings inline and reply-keyboard constants."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.modules.notifications.entities import NotificationPreference
from app.modules.notifications.models import NotificationType

NOTIFICATION_SETTINGS_BUTTON = "🔔 تنظیمات اعلان‌ها"
NOTIFICATION_SETTINGS_CALLBACK_PATTERN = (
    r"^v1:notifications:user:(?:"
    r"menu|"
    r"set:(?:enable|disable):(?:"
    r"NEW_SIGNAL|TARGET_HIT|STOP_HIT|SIGNAL_UPDATED|SIGNAL_CLOSED|"
    r"SYSTEM_NOTIFICATION"
    r")"
    r")$"
)

NOTIFICATION_LABELS = {
    NotificationType.NEW_SIGNAL.value: "📡 سیگنال جدید",
    NotificationType.TARGET_HIT.value: "🎯 برخورد به هدف",
    NotificationType.STOP_HIT.value: "🛑 برخورد به حد ضرر",
    NotificationType.SIGNAL_UPDATED.value: "✏️ تغییر سیگنال",
    NotificationType.SIGNAL_CLOSED.value: "🏁 بسته‌شدن سیگنال",
    NotificationType.SYSTEM_NOTIFICATION.value: "📣 اعلان سیستمی",
}


def build_notification_settings_keyboard(
    preferences: tuple[NotificationPreference, ...],
) -> InlineKeyboardMarkup:
    """Build explicit enable/disable actions for all supported preferences."""
    rows: list[list[InlineKeyboardButton]] = []
    for preference in preferences:
        label = NOTIFICATION_LABELS[preference.notification_type]
        action = "disable" if preference.is_enabled else "enable"
        state = "✅" if preference.is_enabled else "⛔"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{state} {label}",
                    callback_data=(
                        f"v1:notifications:user:set:{action}:"
                        f"{preference.notification_type}"
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به منوی اصلی",
                callback_data="v1:notifications:user:menu",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
