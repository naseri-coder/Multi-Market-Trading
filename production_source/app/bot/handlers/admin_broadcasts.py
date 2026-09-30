"""Administrator draft, preview, confirmation, delivery, and report handlers."""

from __future__ import annotations

import asyncio
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
from app.bot.handlers.admin_state import (
    BROADCAST_ACTION_KEY,
    clear_admin_input_state,
)
from app.bot.keyboards.admin import build_admin_menu
from app.bot.keyboards.broadcasts import (
    BROADCAST_CALLBACK_PATTERN,
    BROADCAST_CANCEL_INPUT_BUTTON,
    BROADCAST_CANCEL_PREFIX,
    BROADCAST_CONFIRM_PREFIX,
    BROADCAST_MANAGEMENT_BUTTON,
    build_broadcast_confirmation,
    build_broadcast_input_menu,
)
from app.bot.middlewares.admin import admin_required
from app.db.session import DatabaseManager
from app.integrations.telegram.broadcasts import TelegramBroadcastGateway
from app.modules.broadcasts.entities import (
    BroadcastRecord,
    BroadcastReport,
    CreateBroadcast,
)
from app.modules.broadcasts.errors import BroadcastError, InvalidBroadcastError
from app.modules.broadcasts.models import BroadcastContentType, BroadcastMediaType
from app.modules.broadcasts.repository import SQLAlchemyBroadcastRepository
from app.modules.broadcasts.service import BroadcastDeliveryService, BroadcastService

logger = logging.getLogger(__name__)
_AWAITING_CONTENT = "awaiting_content"


def has_pending_broadcast_action(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return whether the administrator is expected to send draft content."""
    return context.user_data.get(BROADCAST_ACTION_KEY) == _AWAITING_CONTENT


def extract_broadcast_content(message: Message, admin_telegram_id: int) -> CreateBroadcast:
    """Map an original Telegram text/media message into a Phase 8 draft."""
    if getattr(message, "forward_origin", None) is not None:
        raise InvalidBroadcastError("Use the separate Forward Broadcast workflow")

    if message.text is not None:
        return CreateBroadcast(
            created_by_telegram_user_id=admin_telegram_id,
            content_type=BroadcastContentType.TEXT.value,
            text=message.text,
        )

    media_type: str | None = None
    file_id: str | None = None
    if message.photo:
        media_type = BroadcastMediaType.PHOTO.value
        file_id = message.photo[-1].file_id
    elif message.video is not None:
        media_type = BroadcastMediaType.VIDEO.value
        file_id = message.video.file_id
    elif message.document is not None:
        media_type = BroadcastMediaType.DOCUMENT.value
        file_id = message.document.file_id
    elif message.animation is not None:
        media_type = BroadcastMediaType.ANIMATION.value
        file_id = message.animation.file_id
    elif message.audio is not None:
        media_type = BroadcastMediaType.AUDIO.value
        file_id = message.audio.file_id
    elif message.voice is not None:
        media_type = BroadcastMediaType.VOICE.value
        file_id = message.voice.file_id

    if media_type is None or file_id is None:
        raise InvalidBroadcastError(
            "Only text, photo, video, document, animation, audio, or voice is supported"
        )
    return CreateBroadcast(
        created_by_telegram_user_id=admin_telegram_id,
        content_type=BroadcastContentType.MEDIA.value,
        media_type=media_type,
        media_file_id=file_id,
        caption=message.caption,
    )


async def _create_draft(
    database: DatabaseManager,
    draft: CreateBroadcast,
) -> BroadcastRecord:
    async with database.session() as session, session.begin():
        return await BroadcastService(SQLAlchemyBroadcastRepository(session)).create_draft(draft)


async def _cancel_draft(
    database: DatabaseManager,
    broadcast_id: int,
    admin_telegram_id: int,
) -> BroadcastRecord:
    async with database.session() as session, session.begin():
        return await BroadcastService(SQLAlchemyBroadcastRepository(session)).cancel(
            broadcast_id,
            admin_telegram_id,
        )


async def _confirm_draft(
    database: DatabaseManager,
    broadcast_id: int,
    admin_telegram_id: int,
) -> BroadcastRecord:
    async with database.session() as session, session.begin():
        return await BroadcastService(SQLAlchemyBroadcastRepository(session)).confirm(
            broadcast_id,
            admin_telegram_id,
        )


def render_broadcast_report(
    report: BroadcastReport,
    *,
    title: str = "📊 گزارش ارسال همگانی",
) -> str:
    """Render a compact final delivery report."""
    return "\n".join(
        (
            title,
            "",
            f"شناسه ارسال: {report.broadcast_id}",
            f"کل گیرندگان: {report.total_recipients}",
            f"ارسال موفق: {report.sent_count}",
            f"ناموفق: {report.failed_count}",
            f"مسدودکننده ربات: {report.blocked_count}",
        )
    )


async def _run_and_report(
    application: Application,
    *,
    broadcast_id: int,
    admin_telegram_id: int,
    report_title: str = "📊 گزارش ارسال همگانی",
    failure_text: str = "ارسال همگانی با خطا متوقف شد. وضعیت در دیتابیس ثبت شد.",
) -> None:
    database = application.bot_data["database"]
    try:
        delivery = BroadcastDeliveryService(
            database,
            TelegramBroadcastGateway(application.bot),
            rate_per_second=application.bot_data["broadcast_rate_per_second"],
            batch_size=application.bot_data["broadcast_batch_size"],
            max_retries=application.bot_data["broadcast_max_retries"],
            retry_after_cap_seconds=application.bot_data["broadcast_retry_after_cap_seconds"],
        )
        report = await delivery.run(broadcast_id)
        await application.bot.send_message(
            chat_id=admin_telegram_id,
            text=render_broadcast_report(report, title=report_title),
            reply_markup=build_admin_menu(),
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "Broadcast worker could not complete",
            extra={"event": "broadcast_worker_failed", "broadcast_id": broadcast_id},
        )
        try:
            await application.bot.send_message(
                chat_id=admin_telegram_id,
                text=failure_text,
                reply_markup=build_admin_menu(),
            )
        except Exception:
            logger.exception(
                "Unable to notify administrator about failed broadcast",
                extra={"event": "broadcast_admin_notification_failed"},
            )


async def broadcast_start_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Enter original text/media input mode."""
    message = update.effective_message
    if message is None:
        return
    clear_admin_input_state(context)
    context.user_data[BROADCAST_ACTION_KEY] = _AWAITING_CONTENT
    await message.reply_text(
        "متن یا رسانه اصلی را ارسال کنید. برای Forward از گزینه جداگانه پنل استفاده کنید.",
        reply_markup=build_broadcast_input_menu(),
    )


async def broadcast_input_cancel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Leave input mode before a draft is persisted."""
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text("ارسال همگانی لغو شد.", reply_markup=build_admin_menu())


async def broadcast_content_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Persist original content, send a preview, and request confirmation."""
    if not has_pending_broadcast_action(context):
        return
    message = update.effective_message
    admin = update.effective_user
    if message is None or admin is None:
        return

    broadcast: BroadcastRecord | None = None
    try:
        draft = extract_broadcast_content(message, admin.id)
        broadcast = await _create_draft(get_database_manager(context), draft)
        await message.reply_text("👁 پیش‌نمایش ارسال همگانی:")
        await TelegramBroadcastGateway(context.bot).send(admin.id, broadcast)
        clear_admin_input_state(context)
    except BroadcastError as error:
        if broadcast is not None:
            try:
                await _cancel_draft(get_database_manager(context), broadcast.id, admin.id)
            except BroadcastError:
                logger.exception(
                    "Unable to cancel a draft after preview failure",
                    extra={"event": "broadcast_preview_cleanup_failed"},
                )
        context.user_data[BROADCAST_ACTION_KEY] = _AWAITING_CONTENT
        await message.reply_text(
            f"محتوای ارسال همگانی معتبر نیست: {error}",
            reply_markup=build_broadcast_input_menu(),
        )
        return

    await message.reply_text(
        f"پیش‌نمایش Broadcast #{broadcast.id} را تأیید می‌کنید؟",
        reply_markup=build_broadcast_confirmation(broadcast.id),
    )


async def broadcast_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Atomically confirm or cancel an owned draft from an exact callback."""
    query = update.callback_query
    admin = update.effective_user
    if query is None or admin is None or query.data is None:
        return
    await query.answer("در حال پردازش...")

    try:
        broadcast_id = int(query.data.rsplit(":", 1)[1])
        if query.data.startswith(BROADCAST_CANCEL_PREFIX):
            await _cancel_draft(
                get_database_manager(context),
                broadcast_id,
                admin.id,
            )
            await query.edit_message_text("ارسال همگانی لغو شد.")
            return
        if not query.data.startswith(BROADCAST_CONFIRM_PREFIX):
            return

        broadcast = await _confirm_draft(
            get_database_manager(context),
            broadcast_id,
            admin.id,
        )
    except (BroadcastError, ValueError) as error:
        await query.edit_message_text(f"عملیات Broadcast انجام نشد: {error}")
        return

    await query.edit_message_text(
        f"ارسال Broadcast #{broadcast.id} برای {broadcast.total_recipients} کاربر آغاز شد."
    )
    context.application.create_task(
        _run_and_report(
            context.application,
            broadcast_id=broadcast.id,
            admin_telegram_id=admin.id,
        ),
        update=update,
    )


def register_admin_broadcast_handlers(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    """Register Phase 8 routes behind administrator authorization."""
    guard = admin_required(admin_ids)
    private_chat = filters.ChatType.PRIVATE
    application.add_handler(
        CommandHandler("broadcast", guard(broadcast_start_handler), filters=private_chat)
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(BROADCAST_MANAGEMENT_BUTTON)}$"),
            guard(broadcast_start_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(BROADCAST_CANCEL_INPUT_BUTTON)}$"),
            guard(broadcast_input_cancel_handler),
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            guard(broadcast_callback_handler),
            pattern=BROADCAST_CALLBACK_PATTERN,
        )
    )
