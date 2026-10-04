"""Phase 5 administrator keyboards."""

from telegram import ReplyKeyboardMarkup

from app.bot.keyboards.broadcasts import BROADCAST_MANAGEMENT_BUTTON
from app.bot.keyboards.channels import CHANNEL_MANAGEMENT_BUTTON
from app.bot.keyboards.forward_broadcasts import FORWARD_BROADCAST_MANAGEMENT_BUTTON
from app.bot.keyboards.admin_signals import SIGNAL_MANAGEMENT_BUTTON
from app.bot.keyboards.support import ADMIN_SUPPORT_BUTTON
from app.bot.keyboards.subscriptions import SUBSCRIPTION_MANAGEMENT_BUTTON
from app.bot.keyboards.strategy_management import STRATEGY_MANAGEMENT_BUTTON

ADMIN_PANEL_BUTTON = "🛡 پنل مدیریت"
ADMIN_DASHBOARD_BUTTON = "📊 آمار کاربران"
ADMIN_BACK_BUTTON = "🔙 بازگشت به منوی اصلی"


def build_admin_menu() -> ReplyKeyboardMarkup:
    """Return the minimal admin menu without future-phase features."""
    return ReplyKeyboardMarkup(
        [
            [ADMIN_DASHBOARD_BUTTON],
            [BROADCAST_MANAGEMENT_BUTTON],
            [FORWARD_BROADCAST_MANAGEMENT_BUTTON],
            [ADMIN_SUPPORT_BUTTON],
            [CHANNEL_MANAGEMENT_BUTTON],
            [SIGNAL_MANAGEMENT_BUTTON],
            [STRATEGY_MANAGEMENT_BUTTON],
            [SUBSCRIPTION_MANAGEMENT_BUTTON],
            [ADMIN_BACK_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="پنل مدیریت",
    )
