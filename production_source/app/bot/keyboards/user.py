"""Base user menu keyboard."""

from telegram import ReplyKeyboardMarkup

from app.bot.keyboards.admin import ADMIN_PANEL_BUTTON
from app.bot.keyboards.favorites import FAVORITES_BUTTON
from app.bot.keyboards.notifications import NOTIFICATION_SETTINGS_BUTTON
from app.bot.keyboards.referrals import REFERRALS_BUTTON
from app.bot.keyboards.signals import (
    LIVE_SIGNALS_BUTTON,
    OPEN_SIGNALS_BUTTON,
    SIGNAL_HISTORY_BUTTON,
)
from app.bot.keyboards.support import SUPPORT_BUTTON
from app.bot.keyboards.subscriptions import SUBSCRIPTION_STATUS_BUTTON
from app.bot.keyboards.winrate import WIN_RATE_BUTTON

PROFILE_BUTTON = "👤 پروفایل من"


def build_user_menu(*, is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Return the base menu with an admin entry only for authorized users."""
    rows = [
        [LIVE_SIGNALS_BUTTON],
        [OPEN_SIGNALS_BUTTON, SIGNAL_HISTORY_BUTTON],
        [FAVORITES_BUTTON, NOTIFICATION_SETTINGS_BUTTON],
        [WIN_RATE_BUTTON, SUBSCRIPTION_STATUS_BUTTON],
        [PROFILE_BUTTON, SUPPORT_BUTTON],
        [REFERRALS_BUTTON],
    ]
    if is_admin:
        rows.append([ADMIN_PANEL_BUTTON])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="یک گزینه را انتخاب کنید",
    )
