"""Safe Telegram message editing shared by Phase 10 support callbacks."""

from telegram import CallbackQuery, InlineKeyboardMarkup
from telegram.error import BadRequest


async def safely_edit_support_message(
    query: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Ignore Telegram's harmless duplicate-edit rejection and re-raise other errors."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as error:
        if "Message is not modified" not in str(error):
            raise
