"""Administrator support ticket panel, status controls, and replies."""

from __future__ import annotations

import logging
import re
from collections.abc import Collection

from telegram import Update
from telegram.error import TelegramError
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
    SUPPORT_ADMIN_ACTION_KEY,
    SUPPORT_ADMIN_LIST_KEY,
    clear_admin_input_state,
)
from app.bot.handlers.support_edit import safely_edit_support_message
from app.bot.handlers.support_state import clear_support_user_state
from app.bot.keyboards.admin import build_admin_menu
from app.bot.keyboards.support import (
    ADMIN_SUPPORT_BUTTON,
    ADMIN_SUPPORT_CALLBACK_PATTERN,
    ADMIN_SUPPORT_CANCEL_INPUT_BUTTON,
    build_admin_ticket_actions,
    build_admin_ticket_list,
    build_support_input_cancel,
    build_user_notification_actions,
)
from app.bot.middlewares.admin import admin_required
from app.db.session import DatabaseManager
from app.modules.support.entities import (
    SupportMessageResult,
    SupportThread,
    SupportTicketFilter,
    SupportTicketPage,
    SupportTicketRecord,
)
from app.modules.support.errors import SupportError
from app.modules.support.models import SupportSenderRole, SupportTicketStatus
from app.modules.support.repository import SQLAlchemySupportRepository
from app.modules.support.service import SupportService

logger = logging.getLogger(__name__)
_STATUS_LABELS = {
    SupportTicketStatus.OPEN.value: "باز",
    SupportTicketStatus.IN_PROGRESS.value: "در حال بررسی",
    SupportTicketStatus.CLOSED.value: "بسته",
}
_FILTER_LABELS = {
    SupportTicketFilter.ALL.value: "همه",
    SupportTicketFilter.OPEN.value: "باز",
    SupportTicketFilter.CLOSED.value: "بسته",
    SupportTicketFilter.ANSWERED.value: "پاسخ داده‌شده",
    SupportTicketFilter.WAITING.value: "در انتظار پاسخ",
}


def has_pending_admin_support_action(context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = context.user_data.get(SUPPORT_ADMIN_ACTION_KEY)
    return (
        isinstance(state, dict)
        and state.get("action") == "reply"
        and isinstance(state.get("ticket_id"), int)
    )


def _render_admin_ticket(ticket: SupportTicketRecord) -> str:
    full_name = (
        " ".join(part for part in (ticket.user_first_name, ticket.user_last_name) if part)
        or "ثبت نشده"
    )
    username = f"@{ticket.user_username}" if ticket.user_username else "ثبت نشده"
    return "\n".join(
        (
            f"🎫 تیکت #{ticket.id}",
            f"نام و نام خانوادگی: {full_name}",
            f"شناسه عددی: {ticket.user_telegram_id}",
            f"آیدی اکانت: {username}",
            f"موضوع: {ticket.subject}",
            f"وضعیت: {_STATUS_LABELS.get(ticket.status, ticket.status)}",
        )
    )


def _render_admin_thread(thread: SupportThread) -> str:
    lines = [
        _render_admin_ticket(thread.ticket),
        "",
        f"پیام‌ها: {thread.total_messages} | صفحه {thread.page} از {thread.total_pages}",
    ]
    for message in thread.messages:
        sender = "کاربر" if message.sender_role == SupportSenderRole.USER.value else "پشتیبانی"
        body = message.text if len(message.text) <= 300 else f"{message.text[:297]}..."
        lines.append(f"{sender}: {body}")
    return "\n".join(lines)


def _render_admin_page(page: SupportTicketPage) -> str:
    filter_label = _FILTER_LABELS[page.filter]
    lines = [
        "🎫 مدیریت تیکت‌های پشتیبانی",
        f"فیلتر: {filter_label}",
        f"تعداد: {page.total_items} | صفحه {page.page} از {page.total_pages}",
        "",
    ]
    if not page.tickets:
        lines.append("در این فیلتر تیکتی وجود ندارد.")
        return "\n".join(lines)
    for ticket in page.tickets:
        status = _STATUS_LABELS.get(ticket.status, ticket.status)
        full_name = " ".join(
            part for part in (ticket.user_first_name, ticket.user_last_name) if part
        ) or str(ticket.user_telegram_id)
        username = f"@{ticket.user_username}" if ticket.user_username else "بدون آیدی"
        flow = (
            "در انتظار پاسخ"
            if ticket.status != SupportTicketStatus.CLOSED.value
            and ticket.last_sender_role == SupportSenderRole.USER.value
            else "پاسخ داده‌شده"
            if ticket.last_sender_role == SupportSenderRole.ADMIN.value
            else status
        )
        lines.append(
            f"#{ticket.id} | {status} | {flow}\n"
            f"{full_name} | {username} | {ticket.user_telegram_id}\n"
            f"موضوع: {ticket.subject}\n"
        )
    lines.append("برای مشاهده و مدیریت، تیکت موردنظر را انتخاب کنید.")
    return "\n".join(lines)


def _admin_list_location(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, int]:
    state = context.user_data.get(SUPPORT_ADMIN_LIST_KEY)
    if not isinstance(state, dict):
        return SupportTicketFilter.ALL.value, 1
    filter_by = state.get("filter")
    page = state.get("page")
    if filter_by not in {item.value for item in SupportTicketFilter}:
        return SupportTicketFilter.ALL.value, 1
    if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
        return SupportTicketFilter.ALL.value, 1
    return filter_by, page


def _store_admin_list_location(
    context: ContextTypes.DEFAULT_TYPE,
    page: SupportTicketPage,
) -> None:
    context.user_data[SUPPORT_ADMIN_LIST_KEY] = {
        "filter": page.filter,
        "page": page.page,
    }


def _admin_page_keyboard(page: SupportTicketPage):
    buttons = [
        (ticket.id, f"🎫 #{ticket.id} — {_STATUS_LABELS.get(ticket.status, ticket.status)}")
        for ticket in page.tickets
    ]
    return build_admin_ticket_list(
        buttons,
        filter_by=page.filter,
        page=page.page,
        total_pages=page.total_pages,
    )


async def _get_admin_ticket_page(
    database: DatabaseManager,
    *,
    filter_by: str,
    page: int,
) -> SupportTicketPage:
    async with database.session() as session:
        return await SupportService(SQLAlchemySupportRepository(session)).get_admin_ticket_page(
            filter_by=filter_by,
            page=page,
        )


async def _get_admin_thread(
    database: DatabaseManager,
    ticket_id: int,
    *,
    message_page: int = 1,
) -> SupportThread:
    async with database.session() as session:
        return await SupportService(SQLAlchemySupportRepository(session)).get_admin_thread(
            ticket_id,
            message_page=message_page,
        )


async def _add_admin_message(
    database: DatabaseManager,
    ticket_id: int,
    admin_telegram_id: int,
    text: str,
) -> SupportMessageResult:
    async with database.session() as session, session.begin():
        return await SupportService(SQLAlchemySupportRepository(session)).add_admin_message(
            ticket_id,
            admin_telegram_id,
            text,
        )


async def _set_ticket_status(
    database: DatabaseManager,
    ticket_id: int,
    admin_telegram_id: int,
    status: str,
) -> SupportTicketRecord:
    async with database.session() as session, session.begin():
        return await SupportService(SQLAlchemySupportRepository(session)).set_status(
            ticket_id,
            admin_telegram_id,
            status,
        )


def _notification_preview(text: str, *, limit: int = 3500) -> str:
    """Keep a delivered support reply below Telegram's message limit."""
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


async def _notify_user_status(
    context: ContextTypes.DEFAULT_TYPE,
    ticket: SupportTicketRecord,
) -> None:
    try:
        await context.bot.send_message(
            chat_id=ticket.user_telegram_id,
            text=(
                f"🔔 وضعیت تیکت #{ticket.id} تغییر کرد.\n"
                f"وضعیت جدید: {_STATUS_LABELS.get(ticket.status, ticket.status)}"
            ),
            reply_markup=build_user_notification_actions(ticket.id),
        )
    except TelegramError:
        logger.warning(
            "Support status was persisted but could not be delivered to user",
            extra={"event": "support_status_notification_failed", "ticket_id": ticket.id},
        )


async def admin_support_panel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None:
        return
    clear_admin_input_state(context)
    clear_support_user_state(context)
    try:
        page = await _get_admin_ticket_page(
            get_database_manager(context),
            filter_by=SupportTicketFilter.ALL.value,
            page=1,
        )
    except SupportError:
        await message.reply_text("دریافت تیکت‌های پشتیبانی با خطا مواجه شد.")
        return
    _store_admin_list_location(context, page)
    await message.reply_text(
        _render_admin_page(page),
        reply_markup=_admin_page_keyboard(page),
    )


async def admin_support_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    admin = update.effective_user
    if query is None or admin is None or query.data is None:
        return
    await query.answer("در حال پردازش...")
    try:
        parts = query.data.split(":")
        action = parts[3]
        if action == "panel":
            clear_admin_input_state(context)
            await safely_edit_support_message(query, "به پنل مدیریت بازگشتید.")
            if query.message is not None:
                await query.message.reply_text("🛡 پنل مدیریت", reply_markup=build_admin_menu())
            return
        if action == "list":
            filter_by = parts[4]
            requested_page = int(parts[5])
            page = await _get_admin_ticket_page(
                get_database_manager(context),
                filter_by=filter_by,
                page=requested_page,
            )
            _store_admin_list_location(context, page)
            clear_admin_input_state(context)
            await safely_edit_support_message(
                query,
                _render_admin_page(page),
                reply_markup=_admin_page_keyboard(page),
            )
            return

        ticket_id = int(parts[4])
        list_filter, list_page = _admin_list_location(context)
        if action in {"view", "history"}:
            message_page = int(parts[5]) if action == "history" else 1
            thread = await _get_admin_thread(
                get_database_manager(context),
                ticket_id,
                message_page=message_page,
            )
            await safely_edit_support_message(
                query,
                _render_admin_thread(thread),
                reply_markup=build_admin_ticket_actions(
                    ticket_id,
                    status=thread.ticket.status,
                    list_filter=list_filter,
                    page=list_page,
                    message_page=thread.page,
                    total_message_pages=thread.total_pages,
                ),
            )
            return
        if action == "reply":
            await _get_admin_thread(
                get_database_manager(context),
                ticket_id,
            )
            clear_admin_input_state(context)
            clear_support_user_state(context)
            context.user_data[SUPPORT_ADMIN_ACTION_KEY] = {
                "action": "reply",
                "ticket_id": ticket_id,
            }
            await safely_edit_support_message(
                query,
                f"حالت پاسخ تیکت #{ticket_id} فعال شد.",
            )
            if query.message is not None:
                await query.message.reply_text(
                    "پاسخ متنی را ارسال کنید.",
                    reply_markup=build_support_input_cancel(admin=True),
                )
            return

        status_by_action = {
            "open": SupportTicketStatus.OPEN.value,
            "progress": SupportTicketStatus.IN_PROGRESS.value,
            "close": SupportTicketStatus.CLOSED.value,
        }
        status = status_by_action.get(action)
        if status is None:
            return
        current_thread = await _get_admin_thread(
            get_database_manager(context),
            ticket_id,
        )
        status_changed = current_thread.ticket.status != status
        if status_changed:
            ticket = await _set_ticket_status(
                get_database_manager(context),
                ticket_id,
                admin.id,
                status,
            )
            await _notify_user_status(context, ticket)
        else:
            ticket = current_thread.ticket
        clear_admin_input_state(context)
        thread = (
            await _get_admin_thread(get_database_manager(context), ticket.id)
            if status_changed
            else current_thread
        )
        await safely_edit_support_message(
            query,
            _render_admin_thread(thread),
            reply_markup=build_admin_ticket_actions(
                ticket.id,
                status=ticket.status,
                list_filter=list_filter,
                page=list_page,
                message_page=thread.page,
                total_message_pages=thread.total_pages,
            ),
        )
    except (IndexError, SupportError, ValueError):
        await safely_edit_support_message(query, "عملیات مدیریتی تیکت انجام نشد.")


async def admin_support_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    state = context.user_data.get(SUPPORT_ADMIN_ACTION_KEY)
    if not has_pending_admin_support_action(context):
        return
    message = update.effective_message
    admin = update.effective_user
    if message is None or admin is None:
        return
    if message.text is None:
        await message.reply_text("در این مرحله پاسخ پشتیبانی باید متنی باشد.")
        return

    try:
        result = await _add_admin_message(
            get_database_manager(context),
            state["ticket_id"],
            admin.id,
            message.text,
        )
    except SupportError as error:
        logger.warning(
            "Unable to persist administrator support reply",
            extra={"event": "support_admin_reply_failed", "error_type": type(error).__name__},
        )
        await message.reply_text("ثبت پاسخ انجام نشد. دوباره تلاش کنید.")
        return

    clear_admin_input_state(context)
    try:
        await context.bot.send_message(
            chat_id=result.ticket.user_telegram_id,
            text=(
                f"🎫 پاسخ پشتیبانی برای تیکت #{result.ticket.id}:\n\n"
                f"{_notification_preview(result.message.text)}"
            ),
            reply_markup=build_user_notification_actions(result.ticket.id),
        )
    except TelegramError:
        logger.warning(
            "Persisted support reply could not be delivered to user",
            extra={"event": "support_user_delivery_failed", "ticket_id": result.ticket.id},
        )
        await message.reply_text(
            "پاسخ ثبت شد، اما ارسال آن به کاربر با خطا مواجه شد.",
            reply_markup=build_admin_menu(),
        )
        return
    await message.reply_text(
        f"پاسخ تیکت #{result.ticket.id} ثبت و برای کاربر ارسال شد.",
        reply_markup=build_admin_menu(),
    )


async def admin_support_input_cancel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text("پاسخ پشتیبانی لغو شد.", reply_markup=build_admin_menu())


def register_admin_support_handlers(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    """Register Phase 10 administrative ticket routes."""
    guard = admin_required(admin_ids)
    private = filters.ChatType.PRIVATE
    application.add_handler(
        CommandHandler("admin_tickets", guard(admin_support_panel_handler), filters=private)
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(ADMIN_SUPPORT_BUTTON)}$"),
            guard(admin_support_panel_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(ADMIN_SUPPORT_CANCEL_INPUT_BUTTON)}$"),
            guard(admin_support_input_cancel_handler),
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            guard(admin_support_callback_handler),
            pattern=ADMIN_SUPPORT_CALLBACK_PATTERN,
        )
    )
