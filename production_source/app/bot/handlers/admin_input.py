"""Single free-form administrator input router for current feature workflows."""

from __future__ import annotations

from collections.abc import Collection

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from app.bot.handlers.admin_broadcasts import (
    broadcast_content_input_handler,
    has_pending_broadcast_action,
)
from app.bot.handlers.admin_channels import (
    channel_pending_input_handler,
    has_pending_channel_action,
)
from app.bot.handlers.admin_forward_broadcasts import (
    forward_broadcast_content_input_handler,
    has_pending_forward_broadcast_action,
)
from app.bot.handlers.admin_support import (
    admin_support_input_handler,
    has_pending_admin_support_action,
)
from app.bot.handlers.admin_subscriptions import (
    has_pending_subscription_admin_action,
    subscription_admin_input_handler,
)
from app.bot.handlers.admin_signals import (
    has_pending_signal_admin_action,
    signal_admin_input_handler,
)
from app.bot.handlers.admin_strategy_management import (
    has_pending_strategy_admin_action,
    strategy_admin_input_handler,
)
from app.bot.middlewares.admin import admin_required


async def admin_input_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Route one free-form update to the explicitly selected admin workflow."""
    if has_pending_channel_action(context):
        await channel_pending_input_handler(update, context)
    elif has_pending_broadcast_action(context):
        await broadcast_content_input_handler(update, context)
    elif has_pending_forward_broadcast_action(context):
        await forward_broadcast_content_input_handler(update, context)
    elif has_pending_admin_support_action(context):
        await admin_support_input_handler(update, context)
    elif has_pending_strategy_admin_action(context):
        await strategy_admin_input_handler(update, context)
    elif has_pending_signal_admin_action(context):
        await signal_admin_input_handler(update, context)
    elif has_pending_subscription_admin_action(context):
        await subscription_admin_input_handler(update, context)


def register_admin_input_handler(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    """Register the only broad private-chat administrator message handler."""
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.User(user_id=set(admin_ids)) & ~filters.COMMAND,
            admin_required(admin_ids)(admin_input_router),
        )
    )
