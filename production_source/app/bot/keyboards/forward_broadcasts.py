"""Administrator forwarded-broadcast input and confirmation keyboards."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

FORWARD_BROADCAST_MANAGEMENT_BUTTON = "↪️ فوروارد همگانی"
FORWARD_BROADCAST_CANCEL_INPUT_BUTTON = "🔙 لغو فوروارد همگانی"
FORWARD_BROADCAST_CONFIRM_PREFIX = "v1:forward:confirm:"
FORWARD_BROADCAST_CANCEL_PREFIX = "v1:forward:cancel:"
FORWARD_BROADCAST_CALLBACK_PATTERN = r"^v1:forward:(?:confirm|cancel):[1-9]\d*$"


def build_forward_broadcast_input_menu() -> ReplyKeyboardMarkup:
    """Show one escape while waiting for a forwarded message."""
    return ReplyKeyboardMarkup(
        [[FORWARD_BROADCAST_CANCEL_INPUT_BUTTON]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="یک پیام را برای ربات Forward کنید",
    )


def build_forward_broadcast_confirmation(broadcast_id: int) -> InlineKeyboardMarkup:
    """Build exact versioned confirmation and cancellation callbacks."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ تأیید و فوروارد",
                    callback_data=f"{FORWARD_BROADCAST_CONFIRM_PREFIX}{broadcast_id}",
                ),
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data=f"{FORWARD_BROADCAST_CANCEL_PREFIX}{broadcast_id}",
                ),
            ]
        ]
    )
