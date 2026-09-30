"""Administrator panel entry and navigation handlers."""

from __future__ import annotations

import re
from collections.abc import Collection

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.handlers.admin_broadcasts import register_admin_broadcast_handlers
from app.bot.handlers.admin_channels import register_admin_channel_handlers
from app.bot.handlers.admin_forward_broadcasts import register_admin_forward_broadcast_handlers
from app.bot.handlers.admin_input import register_admin_input_handler
from app.bot.handlers.admin_statistics import admin_dashboard_handler
from app.bot.handlers.admin_signals import register_admin_signal_handlers
from app.bot.handlers.admin_support import register_admin_support_handlers
from app.bot.handlers.admin_subscriptions import register_admin_subscription_handlers
from app.bot.keyboards.admin import (
    ADMIN_BACK_BUTTON,
    ADMIN_DASHBOARD_BUTTON,
    ADMIN_PANEL_BUTTON,
    build_admin_menu,
)
from app.bot.keyboards.user import build_user_menu
from app.bot.middlewares.admin import admin_required


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the Phase 5 administrator panel."""
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "🛡 پنل مدیریت\n\n"
        "دسترسی مدیریتی شما تأیید شد. قابلیت‌های مدیریتی در مراحل بعد به این پنل افزوده می‌شوند.",
        reply_markup=build_admin_menu(),
    )


async def admin_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return an authorized administrator to the base user menu."""
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "به منوی اصلی بازگشتید.",
        reply_markup=build_user_menu(is_admin=True),
    )


def register_admin_handlers(application: Application, admin_ids: Collection[int]) -> None:
    """Register every admin route behind the same fail-closed guard."""
    private_chat = filters.ChatType.PRIVATE
    guard = admin_required(admin_ids)

    application.add_handler(
        CommandHandler("admin", guard(admin_panel_handler), filters=private_chat)
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(ADMIN_PANEL_BUTTON)}$"),
            guard(admin_panel_handler),
        )
    )
    application.add_handler(
        CommandHandler("dashboard", guard(admin_dashboard_handler), filters=private_chat)
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(ADMIN_DASHBOARD_BUTTON)}$"),
            guard(admin_dashboard_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(ADMIN_BACK_BUTTON)}$"),
            guard(admin_back_handler),
        )
    )
    register_admin_channel_handlers(application, admin_ids)
    register_admin_broadcast_handlers(application, admin_ids)
    register_admin_forward_broadcast_handlers(application, admin_ids)
    register_admin_support_handlers(application, admin_ids)
    register_admin_signal_handlers(application, admin_ids)
    register_admin_subscription_handlers(application, admin_ids)
    register_admin_input_handler(application, admin_ids)
