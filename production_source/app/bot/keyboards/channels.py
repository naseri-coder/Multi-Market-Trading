"""Channel management and multi-channel lock keyboards."""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)

from app.modules.channels.entities import ChannelRecord

CHANNEL_MANAGEMENT_BUTTON = "🔐 مدیریت قفل کانال"
CHANNEL_LIST_BUTTON = "📋 فهرست کانال‌ها"
CHANNEL_ADD_BUTTON = "➕ افزودن کانال"
CHANNEL_EDIT_BUTTON = "✏️ ویرایش کانال"
CHANNEL_DELETE_BUTTON = "🗑 حذف کانال"
CHANNEL_TOGGLE_BUTTON = "🔄 فعال/غیرفعال"
CHANNEL_ADMIN_BACK_BUTTON = "🔙 بازگشت به پنل مدیریت"
VERIFY_MEMBERSHIP_CALLBACK = "v1:channel_lock:verify"


def build_channel_management_menu() -> ReplyKeyboardMarkup:
    """Return the Phase 7 channel administration menu."""
    return ReplyKeyboardMarkup(
        [
            [CHANNEL_LIST_BUTTON],
            [CHANNEL_ADD_BUTTON, CHANNEL_EDIT_BUTTON],
            [CHANNEL_TOGGLE_BUTTON, CHANNEL_DELETE_BUTTON],
            [CHANNEL_ADMIN_BACK_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="مدیریت قفل کانال",
    )


def build_membership_keyboard(
    missing_channels: tuple[ChannelRecord, ...],
) -> InlineKeyboardMarkup:
    """Build one join button per missing channel plus a versioned verify callback."""
    rows: list[list[InlineKeyboardButton]] = []
    for channel in missing_channels:
        if channel.join_url is not None:
            title = channel.title if len(channel.title) <= 48 else f"{channel.title[:45]}..."
            rows.append([InlineKeyboardButton(f"عضویت در {title}", url=channel.join_url)])
    rows.append(
        [
            InlineKeyboardButton(
                "✅ بررسی عضویت",
                callback_data=VERIFY_MEMBERSHIP_CALLBACK,
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
