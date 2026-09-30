"""Fail-closed authorization middleware for administrator handlers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Collection
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

AdminHandler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


def admin_required(admin_ids: Collection[int]) -> Callable[[AdminHandler], AdminHandler]:
    """Allow a handler to run only for configured Telegram administrator ids."""
    allowed_admin_ids = frozenset(admin_ids)

    def decorator(handler: AdminHandler) -> AdminHandler:
        @wraps(handler)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            user = update.effective_user
            if user is None or user.id not in allowed_admin_ids:
                logger.warning(
                    "Unauthorized admin access rejected",
                    extra={
                        "event": "admin_access_denied",
                        "telegram_user_id": user.id if user is not None else None,
                        "update_id": update.update_id,
                    },
                )
                message = update.effective_message
                if message is not None:
                    await message.reply_text("⛔️ شما اجازه دسترسی به پنل مدیریت را ندارید.")
                return

            await handler(update, context)

        return wrapped

    return decorator
