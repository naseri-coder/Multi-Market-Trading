"""Telegram application factory and global update error handling."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.ext import Application, ContextTypes

from app.bot.handlers.admins import register_admin_handlers
from app.bot.handlers.channel_lock import register_channel_lock_handlers
from app.bot.handlers.favorites_user import register_favorites_user_handlers
from app.bot.handlers.notification_settings_user import (
    register_notification_settings_user_handlers,
)
from app.bot.handlers.referrals_user import register_referrals_user_handlers
from app.bot.handlers.signals_user import register_signal_user_handlers
from app.bot.handlers.support_users import register_support_user_handlers
from app.bot.handlers.subscriptions_user import register_subscription_user_handlers
from app.bot.handlers.users import register_user_handlers
from app.bot.handlers.winrate_user import register_win_rate_user_handlers
from app.core.config import Settings

logger = logging.getLogger(__name__)

LifecycleCallback = Callable[[Application], Awaitable[None]]


async def handle_update_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log unexpected Telegram update failures without exposing user payloads."""
    error = context.error
    exception_info = None
    if isinstance(error, BaseException):
        exception_info = (type(error), error, error.__traceback__)

    update_id = update.update_id if isinstance(update, Update) else None
    logger.error(
        "Unhandled Telegram update error",
        exc_info=exception_info,
        extra={"event": "telegram_update_failed", "update_id": update_id},
    )


def build_application(
    settings: Settings,
    *,
    post_init: LifecycleCallback | None = None,
    post_shutdown: LifecycleCallback | None = None,
) -> Application:
    """Build the Telegram application and register current feature handlers."""
    builder = Application.builder().token(settings.telegram_bot_token.get_secret_value())
    if post_init is not None:
        builder.post_init(post_init)
    if post_shutdown is not None:
        builder.post_shutdown(post_shutdown)

    application = builder.build()
    application.bot_data["admin_ids"] = settings.admin_ids
    application.bot_data["report_timezone"] = settings.report_timezone
    application.bot_data["broadcast_rate_per_second"] = settings.broadcast_rate_per_second
    application.bot_data["broadcast_batch_size"] = settings.broadcast_batch_size
    application.bot_data["broadcast_max_retries"] = settings.broadcast_max_retries
    application.bot_data["broadcast_retry_after_cap_seconds"] = (
        settings.broadcast_retry_after_cap_seconds
    )
    register_user_handlers(application)
    register_signal_user_handlers(application)
    register_favorites_user_handlers(application)
    register_notification_settings_user_handlers(application)
    register_subscription_user_handlers(application)
    register_referrals_user_handlers(application)
    register_win_rate_user_handlers(application)
    register_support_user_handlers(application)
    register_admin_handlers(application, settings.admin_ids)
    register_channel_lock_handlers(application)
    application.add_error_handler(handle_update_error)
    return application
