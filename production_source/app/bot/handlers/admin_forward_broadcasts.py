"""Administrator forwarded-message preview, confirmation, and delivery handlers."""

from __future__ import annotations

import logging
import re
from collections.abc import Collection

from telegram import Message, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.dependencies import get_database_manager
from app.bot.handlers.admin_broadcasts import (
    _cancel_draft,
    _confirm_draft,
    _create_draft,
    _run_and_report,
)
from app.bot.handlers.admin_state import (
    FORWARD_BROADCAST_ACTION_KEY,
    clear_admin_input_state,
)
from app.bot.keyboards.admin import build_admin_menu
from app.bot.keyboards.forward_broadcasts import (
    FORWARD_BROADCAST_CALLBACK_PATTERN,
    FORWARD_BROADCAST_CANCEL_INPUT_BUTTON,
    FORWARD_BROADCAST_CANCEL_PREFIX,
    FORWARD_BROADCAST_CONFIRM_PREFIX,
    FORWARD_BROADCAST_MANAGEMENT_BUTTON,
    build_forward_broadcast_confirmation,
    build_forward_broadcast_input_menu,
)
from app.bot.middlewares.admin import admin_required
from app.integrations.telegram.broadcasts import TelegramBroadcastGateway
from app.modules.broadcasts.entities import BroadcastRecord, CreateBroadcast
from app.modules.broadcasts.errors import BroadcastError, InvalidBroadcastError
from app.modules.broadcasts.models import BroadcastContentType

logger = logging.getLogger(__name__)
_AWAITING_FORWARD = "awaiting_forward"


def has_pending_forward_broadcast_action(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return whether an administrator must provide one forwarded message."""
    return context.user_data.get(FORWARD_BROADCAST_ACTION_KEY) == _AWAITING_FORWARD


def extract_forward_broadcast(message: Message, admin_telegram_id: int) -> CreateBroadcast:
    """Reference the administrator's received forwarded copy for later forwarding."""
    if getattr(message, "forward_origin", None) is None:
        raise InvalidBroadcastError("A forwarded Telegram message is required")
    if getattr(message, "has_protected_content", False):
        raise InvalidBroadcastError("Protected content cannot be forwarded")

    source_chat_id = getattr(message, "chat_id", None)
    source_message_id = getattr(message, "message_id", None)
    return CreateBroadcast(
        created_by_telegram_user_id=admin_telegram_id,
        content_type=BroadcastContentType.FORWARD.value,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
    )


async def forward_broadcast_start_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Enter forwarded-message input mode."""
    message = update.effective_message
    if message is None:
        return
    clear_admin_input_state(context)
    context.user_data[FORWARD_BROADCAST_ACTION_KEY] = _AWAITING_FORWARD
    await message.reply_text(
        "یک پیام را از کانال، گروه یا گفت‌وگو برای ربات Forward کنید.",
        reply_markup=build_forward_broadcast_input_menu(),
    )


async def forward_broadcast_input_cancel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Leave forward input mode before persisting a draft."""
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text("فوروارد همگانی لغو شد.", reply_markup=build_admin_menu())


async def forward_broadcast_content_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Persist and preview exactly one forwarded message."""
    if not has_pending_forward_broadcast_action(context):
        return
    message = update.effective_message
    admin = update.effective_user
    if message is None or admin is None:
        return

    broadcast: BroadcastRecord | None = None
    try:
        draft = extract_forward_broadcast(message, admin.id)
        broadcast = await _create_draft(get_database_manager(context), draft)
        await message.reply_text("👁 پیش‌نمایش فوروارد همگانی:")
        await TelegramBroadcastGateway(context.bot).send(admin.id, broadcast)
        clear_admin_input_state(context)
    except BroadcastError as error:
        if broadcast is not None:
            try:
                await _cancel_draft(get_database_manager(context), broadcast.id, admin.id)
            except BroadcastError:
                logger.exception(
                    "Unable to cancel a forward draft after preview failure",
                    extra={"event": "forward_broadcast_preview_cleanup_failed"},
                )
        context.user_data[FORWARD_BROADCAST_ACTION_KEY] = _AWAITING_FORWARD
        await message.reply_text(
            f"پیام Forward معتبر نیست: {error}",
            reply_markup=build_forward_broadcast_input_menu(),
        )
        return

    await message.reply_text(
        f"پیش‌نمایش Forward Broadcast #{broadcast.id} را تأیید می‌کنید؟",
        reply_markup=build_forward_broadcast_confirmation(broadcast.id),
    )


async def forward_broadcast_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Atomically confirm or cancel an owned forward draft."""
    query = update.callback_query
    admin = update.effective_user
    if query is None or admin is None or query.data is None:
        return
    await query.answer("در حال پردازش...")

    try:
        broadcast_id = int(query.data.rsplit(":", 1)[1])
        if query.data.startswith(FORWARD_BROADCAST_CANCEL_PREFIX):
            await _cancel_draft(get_database_manager(context), broadcast_id, admin.id)
            await query.edit_message_text("فوروارد همگانی لغو شد.")
            return
        if not query.data.startswith(FORWARD_BROADCAST_CONFIRM_PREFIX):
            return
        broadcast = await _confirm_draft(
            get_database_manager(context),
            broadcast_id,
            admin.id,
        )
    except (BroadcastError, ValueError) as error:
        await query.edit_message_text(f"عملیات Forward Broadcast انجام نشد: {error}")
        return

    await query.edit_message_text(
        f"فوروارد #{broadcast.id} برای {broadcast.total_recipients} کاربر آغاز شد."
    )
    context.application.create_task(
        _run_and_report(
            context.application,
            broadcast_id=broadcast.id,
            admin_telegram_id=admin.id,
            report_title="📊 گزارش فوروارد همگانی",
            failure_text="فوروارد همگانی با خطا متوقف شد. وضعیت در دیتابیس ثبت شد.",
        ),
        update=update,
    )


def register_admin_forward_broadcast_handlers(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    """Register Phase 9 routes behind administrator authorization."""
    guard = admin_required(admin_ids)
    private_chat = filters.ChatType.PRIVATE
    application.add_handler(
        CommandHandler(
            "forward_broadcast",
            guard(forward_broadcast_start_handler),
            filters=private_chat,
        )
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(FORWARD_BROADCAST_MANAGEMENT_BUTTON)}$"),
            guard(forward_broadcast_start_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(FORWARD_BROADCAST_CANCEL_INPUT_BUTTON)}$"),
            guard(forward_broadcast_input_cancel_handler),
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            guard(forward_broadcast_callback_handler),
            pattern=FORWARD_BROADCAST_CALLBACK_PATTERN,
        )
    )
