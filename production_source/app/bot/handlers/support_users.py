"""User-facing support ticket creation, messages, history, and closure."""

from __future__ import annotations

import logging
import re

from telegram import InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.dependencies import get_admin_ids, get_database_manager
from app.bot.handlers.admin_state import clear_admin_input_state
from app.bot.handlers.support_edit import safely_edit_support_message
from app.bot.handlers.support_state import (
    SUPPORT_USER_ACTION_KEY,
    SUPPORT_USER_LIST_PAGE_KEY,
    clear_support_user_state,
)
from app.bot.handlers.users import sync_user, telegram_user_to_identity
from app.bot.keyboards.support import (
    SUPPORT_BACK_BUTTON,
    SUPPORT_BUTTON,
    SUPPORT_CANCEL_INPUT_BUTTON,
    SUPPORT_MY_TICKETS_BUTTON,
    SUPPORT_NEW_TICKET_BUTTON,
    USER_SUPPORT_CALLBACK_PATTERN,
    build_admin_notification_actions,
    build_support_input_cancel,
    build_support_menu,
    build_user_ticket_actions,
    build_user_ticket_list,
)
from app.bot.keyboards.user import build_user_menu
from app.db.session import DatabaseManager
from app.modules.support.entities import (
    SupportMessageResult,
    SupportThread,
    SupportTicketRecord,
    UserSupportTicketPage,
)
from app.modules.support.errors import InvalidSupportMessageError, SupportError
from app.modules.support.models import SupportSenderRole, SupportTicketStatus
from app.modules.support.repository import SQLAlchemySupportRepository
from app.modules.support.service import SupportService
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError

logger = logging.getLogger(__name__)
_STATUS_LABELS = {
    SupportTicketStatus.OPEN.value: "باز",
    SupportTicketStatus.IN_PROGRESS.value: "در حال بررسی",
    SupportTicketStatus.CLOSED.value: "بسته",
}


def _render_ticket(ticket: SupportTicketRecord) -> str:
    return "\n".join(
        (
            f"🎫 تیکت #{ticket.id}",
            f"موضوع: {ticket.subject}",
            f"وضعیت: {_STATUS_LABELS.get(ticket.status, ticket.status)}",
        )
    )


def render_support_thread(thread: SupportThread) -> str:
    """Render one bounded, database-paginated ticket history page."""
    lines = [
        _render_ticket(thread.ticket),
        "",
        f"پیام‌ها: {thread.total_messages} | صفحه {thread.page} از {thread.total_pages}",
    ]
    for message in thread.messages:
        sender = "کاربر" if message.sender_role == SupportSenderRole.USER.value else "پشتیبانی"
        body = message.text if len(message.text) <= 300 else f"{message.text[:297]}..."
        lines.append(f"{sender}: {body}")
    return "\n".join(lines)


def _render_user_ticket_list(
    page: UserSupportTicketPage,
) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        "📋 تیکت‌های شما",
        f"تعداد: {page.total_items} | صفحه {page.page} از {page.total_pages}",
        "",
    ]
    buttons: list[tuple[int, str]] = []
    for ticket in page.tickets:
        status = _STATUS_LABELS.get(ticket.status, ticket.status)
        lines.append(f"#{ticket.id} | {status} | {ticket.subject}")
        buttons.append((ticket.id, f"🎫 #{ticket.id} — {status}"))
    lines.append("")
    lines.append("برای مشاهده جزئیات، تیکت موردنظر را انتخاب کنید.")
    return "\n".join(lines), build_user_ticket_list(
        buttons,
        page=page.page,
        total_pages=page.total_pages,
    )


def _user_list_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    page = context.user_data.get(SUPPORT_USER_LIST_PAGE_KEY)
    if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
        return 1
    return page


async def _create_ticket(
    database: DatabaseManager,
    *,
    user_id: int,
    user_telegram_id: int,
    subject: str,
    text: str,
) -> SupportMessageResult:
    async with database.session() as session, session.begin():
        return await SupportService(SQLAlchemySupportRepository(session)).create_ticket(
            user_id=user_id,
            user_telegram_id=user_telegram_id,
            subject=subject,
            text=text,
        )


async def _get_user_ticket_page(
    database: DatabaseManager,
    user_telegram_id: int,
    *,
    page: int,
) -> UserSupportTicketPage:
    async with database.session() as session:
        return await SupportService(SQLAlchemySupportRepository(session)).get_user_ticket_page(
            user_telegram_id,
            page=page,
        )


async def _get_user_thread(
    database: DatabaseManager,
    ticket_id: int,
    user_telegram_id: int,
    *,
    message_page: int = 1,
) -> SupportThread:
    async with database.session() as session:
        return await SupportService(SQLAlchemySupportRepository(session)).get_user_thread(
            ticket_id,
            user_telegram_id,
            message_page=message_page,
        )


async def _add_user_message(
    database: DatabaseManager,
    ticket_id: int,
    user_telegram_id: int,
    text: str,
) -> SupportMessageResult:
    async with database.session() as session, session.begin():
        return await SupportService(SQLAlchemySupportRepository(session)).add_user_message(
            ticket_id,
            user_telegram_id,
            text,
        )


async def _close_user_ticket(
    database: DatabaseManager,
    ticket_id: int,
    user_telegram_id: int,
) -> SupportTicketRecord:
    async with database.session() as session, session.begin():
        return await SupportService(SQLAlchemySupportRepository(session)).close_by_user(
            ticket_id,
            user_telegram_id,
        )


async def _notify_admins(
    context: ContextTypes.DEFAULT_TYPE,
    result: SupportMessageResult,
) -> None:
    full_name = (
        " ".join(
            part for part in (result.ticket.user_first_name, result.ticket.user_last_name) if part
        )
        or "ثبت نشده"
    )
    username = f"@{result.ticket.user_username}" if result.ticket.user_username else "ثبت نشده"
    message_preview = _notification_preview(result.message.text)
    text = (
        f"🎫 پیام جدید در تیکت #{result.ticket.id}\n"
        f"نام و نام خانوادگی: {full_name}\n"
        f"شناسه عددی: {result.ticket.user_telegram_id}\n"
        f"آیدی اکانت: {username}\n"
        f"موضوع: {result.ticket.subject}\n\n"
        f"{message_preview}"
    )
    reply_markup = build_admin_notification_actions(result.ticket.id)
    delivered = 0
    for admin_id in get_admin_ids(context):
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
            )
            delivered += 1
        except TelegramError:
            logger.warning(
                "Unable to notify one administrator about support message",
                extra={
                    "event": "support_admin_notification_failed",
                    "admin_telegram_user_id": admin_id,
                    "ticket_id": result.ticket.id,
                },
            )
    if delivered == 0:
        logger.warning(
            "No administrator received support notification",
            extra={"event": "support_admin_notifications_empty", "ticket_id": result.ticket.id},
        )


async def _notify_admins_ticket_closed(
    context: ContextTypes.DEFAULT_TYPE,
    ticket: SupportTicketRecord,
) -> None:
    text = f"✅ کاربر تیکت #{ticket.id} را بست.\nموضوع: {ticket.subject}"
    reply_markup = build_admin_notification_actions(ticket.id)
    for admin_id in get_admin_ids(context):
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
            )
        except TelegramError:
            logger.warning(
                "Unable to notify one administrator about closed support ticket",
                extra={
                    "event": "support_admin_status_notification_failed",
                    "admin_telegram_user_id": admin_id,
                    "ticket_id": ticket.id,
                },
            )


def _notification_preview(text: str, *, limit: int = 3000) -> str:
    """Keep Telegram alerts below the platform message limit."""
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


async def support_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    clear_support_user_state(context)
    clear_admin_input_state(context)
    try:
        await sync_user(get_database_manager(context), telegram_user_to_identity(user))
    except (InvalidUserIdentityError, UserRepositoryError):
        await message.reply_text("در حال حاضر دسترسی به پشتیبانی ممکن نیست.")
        return
    await message.reply_text(
        "🆘 پشتیبانی\n\nمی‌توانید تیکت جدید ایجاد کنید یا تیکت‌های قبلی را ببینید.",
        reply_markup=build_support_menu(),
    )


async def support_new_ticket_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None:
        return
    clear_support_user_state(context)
    clear_admin_input_state(context)
    context.user_data[SUPPORT_USER_ACTION_KEY] = {
        "action": "new_subject",
        "prompt_update_id": update.update_id,
    }
    await message.reply_text(
        "موضوع تیکت را در یک خط ارسال کنید.\nحداکثر ۱۲۰ کاراکتر.",
        reply_markup=build_support_input_cancel(),
    )


async def support_input_cancel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_support_user_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text("عملیات پشتیبانی لغو شد.", reply_markup=build_support_menu())


async def support_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    try:
        page = await _get_user_ticket_page(
            get_database_manager(context),
            user.id,
            page=1,
        )
    except SupportError:
        await message.reply_text("دریافت تیکت‌ها با خطا مواجه شد.")
        return
    if not page.tickets:
        await message.reply_text("هنوز تیکتی ندارید.", reply_markup=build_support_menu())
        return
    context.user_data[SUPPORT_USER_LIST_PAGE_KEY] = page.page
    text, reply_markup = _render_user_ticket_list(page)
    await message.reply_text(
        text,
        reply_markup=reply_markup,
    )


async def support_user_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer("در حال پردازش...")
    try:
        parts = query.data.split(":")
        action = parts[3]
        if action == "list":
            requested_page = int(parts[4])
            page = await _get_user_ticket_page(
                get_database_manager(context),
                user.id,
                page=requested_page,
            )
            if not page.tickets:
                await safely_edit_support_message(query, "هنوز تیکتی ندارید.")
                return
            context.user_data[SUPPORT_USER_LIST_PAGE_KEY] = page.page
            text, reply_markup = _render_user_ticket_list(page)
            await safely_edit_support_message(
                query,
                text,
                reply_markup=reply_markup,
            )
            return
        ticket_id = int(parts[4])
        if action in {"view", "history"}:
            message_page = int(parts[5]) if action == "history" else 1
            thread = await _get_user_thread(
                get_database_manager(context),
                ticket_id,
                user.id,
                message_page=message_page,
            )
            await safely_edit_support_message(
                query,
                render_support_thread(thread),
                reply_markup=build_user_ticket_actions(
                    ticket_id,
                    closed=thread.ticket.status == SupportTicketStatus.CLOSED.value,
                    list_page=_user_list_page(context),
                    message_page=thread.page,
                    total_message_pages=thread.total_pages,
                ),
            )
            return
        if action == "reply":
            await _get_user_thread(
                get_database_manager(context),
                ticket_id,
                user.id,
            )
            clear_admin_input_state(context)
            context.user_data[SUPPORT_USER_ACTION_KEY] = {
                "action": "reply",
                "ticket_id": ticket_id,
            }
            await safely_edit_support_message(
                query,
                f"پیام جدید برای تیکت #{ticket_id} را ارسال کنید.",
            )
            return
        if action == "close":
            ticket = await _close_user_ticket(
                get_database_manager(context),
                ticket_id,
                user.id,
            )
            clear_support_user_state(context)
            await safely_edit_support_message(
                query,
                f"تیکت #{ticket_id} بسته شد.",
                reply_markup=build_user_ticket_actions(
                    ticket_id,
                    closed=True,
                    list_page=_user_list_page(context),
                ),
            )
            await _notify_admins_ticket_closed(context, ticket)
            return
    except (IndexError, SupportError, ValueError):
        await safely_edit_support_message(
            query,
            "عملیات تیکت انجام نشد یا تیکت در دسترس نیست.",
        )


async def support_user_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    state = context.user_data.get(SUPPORT_USER_ACTION_KEY)
    if not isinstance(state, dict):
        return
    prompt_update_id = state.get("prompt_update_id")
    if isinstance(prompt_update_id, int) and prompt_update_id == update.update_id:
        return
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if message.text is None:
        await message.reply_text("در این مرحله پیام پشتیبانی باید متنی باشد.")
        return

    try:
        if state.get("action") == "new_subject":
            try:
                subject = SupportService.normalize_subject(message.text)
            except InvalidSupportMessageError:
                await message.reply_text(
                    "موضوع باید یک خط و بین ۱ تا ۱۲۰ کاراکتر باشد. دوباره ارسال کنید.",
                    reply_markup=build_support_input_cancel(),
                )
                return
            context.user_data[SUPPORT_USER_ACTION_KEY] = {
                "action": "new_message",
                "subject": subject,
            }
            await message.reply_text(
                f"موضوع ثبت شد: {subject}\n\nاکنون متن کامل درخواست را ارسال کنید.",
                reply_markup=build_support_input_cancel(),
            )
            return
        if state.get("action") == "new_message" and isinstance(state.get("subject"), str):
            registration = await sync_user(
                get_database_manager(context),
                telegram_user_to_identity(user),
            )
            result = await _create_ticket(
                get_database_manager(context),
                user_id=registration.profile.id,
                user_telegram_id=user.id,
                subject=state["subject"],
                text=message.text,
            )
            success = f"تیکت #{result.ticket.id} با موفقیت ایجاد شد."
        elif state.get("action") == "reply" and isinstance(state.get("ticket_id"), int):
            result = await _add_user_message(
                get_database_manager(context),
                state["ticket_id"],
                user.id,
                message.text,
            )
            success = f"پیام شما در تیکت #{result.ticket.id} ثبت شد."
        else:
            clear_support_user_state(context)
            return
    except (SupportError, InvalidUserIdentityError, UserRepositoryError) as error:
        logger.warning(
            "Unable to persist user support input",
            extra={"event": "support_user_input_failed", "error_type": type(error).__name__},
        )
        await message.reply_text("ثبت پیام پشتیبانی انجام نشد. دوباره تلاش کنید.")
        return

    clear_support_user_state(context)
    await message.reply_text(success, reply_markup=build_support_menu())
    await _notify_admins(context, result)


async def support_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_support_user_state(context)
    clear_admin_input_state(context)
    user = update.effective_user
    message = update.effective_message
    if user is not None and message is not None:
        await message.reply_text(
            "به منوی اصلی بازگشتید.",
            reply_markup=build_user_menu(is_admin=user.id in get_admin_ids(context)),
        )


def register_support_user_handlers(application: Application) -> None:
    """Register Phase 10 user routes and a group-one stateful text input."""
    private = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("support", support_menu_handler, filters=private))
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUPPORT_BUTTON)}$"),
            support_menu_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUPPORT_NEW_TICKET_BUTTON)}$"),
            support_new_ticket_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUPPORT_MY_TICKETS_BUTTON)}$"),
            support_list_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUPPORT_CANCEL_INPUT_BUTTON)}$"),
            support_input_cancel_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUPPORT_BACK_BUTTON)}$"),
            support_back_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            support_user_callback_handler,
            pattern=USER_SUPPORT_CALLBACK_PATTERN,
        )
    )
    application.add_handler(
        MessageHandler(private & ~filters.COMMAND, support_user_input_handler),
        group=1,
    )
