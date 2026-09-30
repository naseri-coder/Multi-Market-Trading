"""Administrator broadcast input and confirmation keyboards."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

BROADCAST_MANAGEMENT_BUTTON = "📢 ارسال همگانی"
BROADCAST_CANCEL_INPUT_BUTTON = "🔙 لغو ارسال همگانی"
BROADCAST_CONFIRM_PREFIX = "v1:broadcast:confirm:"
BROADCAST_CANCEL_PREFIX = "v1:broadcast:cancel:"
BROADCAST_CALLBACK_PATTERN = r"^v1:broadcast:(?:confirm|cancel):[1-9]\d*$"


def build_broadcast_input_menu() -> ReplyKeyboardMarkup:
    """Show a single unambiguous escape from draft input mode."""
    return ReplyKeyboardMarkup(
        [[BROADCAST_CANCEL_INPUT_BUTTON]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="متن یا رسانه را ارسال کنید",
    )


def build_broadcast_confirmation(broadcast_id: int) -> InlineKeyboardMarkup:
    """Build exact versioned confirmation and cancellation callbacks."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ تأیید و ارسال",
                    callback_data=f"{BROADCAST_CONFIRM_PREFIX}{broadcast_id}",
                ),
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data=f"{BROADCAST_CANCEL_PREFIX}{broadcast_id}",
                ),
            ]
        ]
    )
