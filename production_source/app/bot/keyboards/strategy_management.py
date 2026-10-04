"""Administrator strategy-routing keyboards."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

STRATEGY_MANAGEMENT_BUTTON = "🎛 مدیریت سیگنال‌دهی"
BROOKS_STRATEGY_BUTTON = "📈 پرایس اکشن البروکس"
FM_STRATEGY_BUTTON = "🧩 استراتژی FM"
STRATEGY_ADMIN_BACK_BUTTON = "🔙 بازگشت به پنل مدیریت"
STRATEGY_CALLBACK_PATTERN = r"^v1:strategy:(BROOKS|FM):(toggle|set_channel|clear_channel|refresh)$"


def build_strategy_management_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BROOKS_STRATEGY_BUTTON],
            [FM_STRATEGY_BUTTON],
            [STRATEGY_ADMIN_BACK_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="مدیریت هسته‌های سیگنال‌دهی",
    )


def build_strategy_actions(strategy_code: str, *, enabled: bool) -> InlineKeyboardMarkup:
    toggle = "⏸ غیرفعال‌کردن" if enabled else "▶️ فعال‌کردن"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    toggle,
                    callback_data=f"v1:strategy:{strategy_code}:toggle",
                )
            ],
            [
                InlineKeyboardButton(
                    "📡 تعیین کانال خصوصی",
                    callback_data=f"v1:strategy:{strategy_code}:set_channel",
                )
            ],
            [
                InlineKeyboardButton(
                    "🧹 حذف کانال",
                    callback_data=f"v1:strategy:{strategy_code}:clear_channel",
                ),
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data=f"v1:strategy:{strategy_code}:refresh",
                ),
            ],
        ]
    )
