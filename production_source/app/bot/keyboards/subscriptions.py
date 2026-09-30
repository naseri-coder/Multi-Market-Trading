"""Reply keyboards for user and administrator subscription features."""

from telegram import ReplyKeyboardMarkup

SUBSCRIPTION_STATUS_BUTTON = "💎 وضعیت اشتراک"
SUBSCRIPTION_MANAGEMENT_BUTTON = "💎 مدیریت اشتراک‌ها"
SUBSCRIPTION_PLAN_LIST_BUTTON = "📋 فهرست پلن‌ها"
SUBSCRIPTION_PLAN_CREATE_BUTTON = "➕ ایجاد پلن"
SUBSCRIPTION_PLAN_EDIT_BUTTON = "✏️ ویرایش پلن"
SUBSCRIPTION_PLAN_DELETE_BUTTON = "🗑 حذف پلن"
SUBSCRIPTION_ACTIVATE_BUTTON = "✅ فعال‌سازی اشتراک"
SUBSCRIPTION_EXPIRE_BUTTON = "⏳ پایان اشتراک"
SUBSCRIPTION_ADMIN_BACK_BUTTON = "🔙 بازگشت به پنل مدیریت"


def build_subscription_management_menu() -> ReplyKeyboardMarkup:
    """Return a guided administrator menu without pipe-separated commands."""
    return ReplyKeyboardMarkup(
        [
            [SUBSCRIPTION_PLAN_LIST_BUTTON],
            [SUBSCRIPTION_PLAN_CREATE_BUTTON, SUBSCRIPTION_PLAN_EDIT_BUTTON],
            [SUBSCRIPTION_ACTIVATE_BUTTON, SUBSCRIPTION_EXPIRE_BUTTON],
            [SUBSCRIPTION_PLAN_DELETE_BUTTON],
            [SUBSCRIPTION_ADMIN_BACK_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="مدیریت اشتراک‌ها",
    )
