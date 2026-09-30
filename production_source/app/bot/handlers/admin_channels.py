"""Administrator handlers for Phase 7 channel management."""

from __future__ import annotations

import logging
import re
from collections.abc import Collection

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.dependencies import get_database_manager
from app.bot.handlers.admin_state import CHANNEL_ACTION_KEY, clear_admin_input_state
from app.bot.keyboards.admin import build_admin_menu
from app.bot.keyboards.channels import (
    CHANNEL_ADD_BUTTON,
    CHANNEL_ADMIN_BACK_BUTTON,
    CHANNEL_DELETE_BUTTON,
    CHANNEL_EDIT_BUTTON,
    CHANNEL_LIST_BUTTON,
    CHANNEL_MANAGEMENT_BUTTON,
    CHANNEL_TOGGLE_BUTTON,
    build_channel_management_menu,
)
from app.bot.middlewares.admin import admin_required
from app.db.session import DatabaseManager
from app.integrations.telegram.channels import TelegramChannelGateway
from app.modules.channels.entities import (
    ChannelRecord,
    CreateChannel,
    ResolvedTelegramChannel,
)
from app.modules.channels.errors import (
    ChannelError,
    ChannelNotFoundError,
    DuplicateChannelError,
    InvalidChannelError,
    TelegramChannelGatewayError,
)
from app.modules.channels.repository import SQLAlchemyChannelRepository
from app.modules.channels.service import ChannelService

logger = logging.getLogger(__name__)
_TELEGRAM_SAFE_MESSAGE_LENGTH = 3800
_ACTION_ADD = "add"
_ACTION_EDIT = "edit"
_ACTION_DELETE = "delete"
_ACTION_TOGGLE = "toggle"


def _optional_field(value: str) -> str | None:
    normalized = value.strip()
    return None if normalized in {"", "-"} else normalized


def _positive_integer(value: str, *, field_name: str) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise InvalidChannelError(f"{field_name} must be an integer") from exc
    if parsed <= 0:
        raise InvalidChannelError(f"{field_name} must be positive")
    return parsed


def _sort_order(value: str) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise InvalidChannelError("Sort order must be an integer") from exc
    if parsed < 0:
        raise InvalidChannelError("Sort order must not be negative")
    return parsed


def _payload(update: Update) -> str:
    message = update.effective_message
    text = message.text if message is not None else None
    if not text:
        raise InvalidChannelError("Command payload is required")
    _, separator, payload = text.partition(" ")
    if not separator or not payload.strip():
        raise InvalidChannelError("Command payload is required")
    return payload.strip()


def _fields(payload: str, *, expected: int) -> list[str]:
    values = [value.strip() for value in payload.split("|")]
    if len(values) != expected:
        raise InvalidChannelError(f"Expected {expected} pipe-separated fields")
    return values


async def _create_channel(database: DatabaseManager, channel: CreateChannel) -> ChannelRecord:
    async with database.session() as session, session.begin():
        service = ChannelService(SQLAlchemyChannelRepository(session))
        return await service.create_channel(channel)


async def _refresh_channel(
    database: DatabaseManager,
    channel: ResolvedTelegramChannel,
) -> ChannelRecord:
    async with database.session() as session, session.begin():
        service = ChannelService(SQLAlchemyChannelRepository(session))
        return await service.refresh_channel(channel)


async def _delete_channel(database: DatabaseManager, channel_id: int) -> None:
    async with database.session() as session, session.begin():
        service = ChannelService(SQLAlchemyChannelRepository(session))
        await service.delete_channel(channel_id)


async def _get_channel(database: DatabaseManager, channel_id: int) -> ChannelRecord:
    async with database.session() as session:
        service = ChannelService(SQLAlchemyChannelRepository(session))
        return await service.get_channel(channel_id)


async def _toggle_channel(database: DatabaseManager, channel_id: int) -> ChannelRecord:
    async with database.session() as session, session.begin():
        service = ChannelService(SQLAlchemyChannelRepository(session))
        return await service.toggle_channel(channel_id)


async def _list_channels(database: DatabaseManager) -> tuple[ChannelRecord, ...]:
    async with database.session() as session:
        service = ChannelService(SQLAlchemyChannelRepository(session))
        return await service.list_channels()


def _clear_pending_action(context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_admin_input_state(context)


def has_pending_channel_action(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return whether the next administrator text belongs to channel management."""
    return CHANNEL_ACTION_KEY in context.user_data


async def _resolve_and_create_channel(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    reference: str,
    invite_link: str | None = None,
    sort_order: int = 0,
) -> ChannelRecord:
    resolved = await TelegramChannelGateway(context.bot).resolve_channel(
        reference,
        supplied_invite_link=invite_link,
    )
    return await _create_channel(
        get_database_manager(context),
        CreateChannel(
            telegram_chat_id=resolved.telegram_chat_id,
            username=resolved.username,
            title=resolved.title,
            invite_link=resolved.invite_link,
            sort_order=sort_order,
        ),
    )


async def _resolve_and_refresh_channel(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    reference: str,
) -> ChannelRecord:
    database = get_database_manager(context)
    normalized = reference.strip()
    if normalized.isdigit():
        existing = await _get_channel(
            database,
            _positive_integer(normalized, field_name="Channel ID"),
        )
        normalized = str(existing.telegram_chat_id)
    resolved = await TelegramChannelGateway(context.bot).resolve_channel(normalized)
    return await _refresh_channel(database, resolved)


def render_channel_list(channels: tuple[ChannelRecord, ...]) -> str:
    """Render configured channels with internal ids needed by management commands."""
    if not channels:
        return "📋 هنوز هیچ کانالی ثبت نشده است."

    sections = ["📋 فهرست کانال‌ها"]
    for channel in channels:
        username = f"@{channel.username}" if channel.username else "خصوصی"
        state = "فعال ✅" if channel.is_active else "غیرفعال ⏸"
        sections.append(
            "\n".join(
                (
                    "",
                    f"ID: {channel.id}",
                    f"عنوان: {channel.title}",
                    f"Chat ID: {channel.telegram_chat_id}",
                    f"Username: {username}",
                    f"وضعیت: {state}",
                    f"ترتیب: {channel.sort_order}",
                )
            )
        )
    return "\n".join(sections)


def render_channel_list_pages(channels: tuple[ChannelRecord, ...]) -> tuple[str, ...]:
    """Split a potentially large channel list below Telegram's message limit."""
    if not channels:
        return (render_channel_list(channels),)

    pages: list[str] = []
    current: list[ChannelRecord] = []
    for channel in channels:
        candidate = render_channel_list((*current, channel))
        if current and len(candidate) > _TELEGRAM_SAFE_MESSAGE_LENGTH:
            pages.append(render_channel_list(tuple(current)))
            current = [channel]
        else:
            current.append(channel)
    pages.append(render_channel_list(tuple(current)))
    return tuple(pages)


async def _reply_channel_error(update: Update, error: ChannelError) -> None:
    message = update.effective_message
    if message is None:
        return

    if isinstance(error, ChannelNotFoundError):
        text = "کانال موردنظر پیدا نشد."
    elif isinstance(error, DuplicateChannelError):
        text = "این کانال قبلاً ثبت شده است."
    elif isinstance(error, (InvalidChannelError, TelegramChannelGatewayError)):
        text = f"اطلاعات کانال نامعتبر است: {error}"
    else:
        logger.exception(
            "Channel administration failed",
            extra={"event": "channel_admin_failed", "update_id": update.update_id},
        )
        text = "عملیات کانال انجام نشد. لطفاً کمی بعد دوباره تلاش کنید."

    await message.reply_text(text, reply_markup=build_channel_management_menu())


async def channel_management_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open the channel-lock administration menu."""
    _clear_pending_action(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "🔐 مدیریت قفل چندکاناله",
            reply_markup=build_channel_management_menu(),
        )


async def channel_management_back_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Return to the administrator panel."""
    _clear_pending_action(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text("به پنل مدیریت بازگشتید.", reply_markup=build_admin_menu())


async def channel_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List every configured channel in deterministic order."""
    _clear_pending_action(context)
    message = update.effective_message
    if message is None:
        return
    try:
        channels = await _list_channels(get_database_manager(context))
    except ChannelError as error:
        await _reply_channel_error(update, error)
        return
    pages = render_channel_list_pages(channels)
    for index, page in enumerate(pages):
        reply_markup = build_channel_management_menu() if index == len(pages) - 1 else None
        await message.reply_text(page, reply_markup=reply_markup)


async def channel_instruction_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show exact safe command syntax for the selected operation."""
    message = update.effective_message
    if message is None:
        return
    instructions = {
        CHANNEL_ADD_BUTTON: "شناسه عمومی مانند @channelname یا شناسه عددی کانال را بفرستید.",
        CHANNEL_EDIT_BUTTON: "ID یا @username کانال را بفرستید.",
        CHANNEL_DELETE_BUTTON: "ID داخلی کانالی را که می‌خواهید حذف شود بفرستید.",
        CHANNEL_TOGGLE_BUTTON: "ID داخلی کانال را برای فعال/غیرفعال‌کردن بفرستید.",
    }
    actions = {
        CHANNEL_ADD_BUTTON: _ACTION_ADD,
        CHANNEL_EDIT_BUTTON: _ACTION_EDIT,
        CHANNEL_DELETE_BUTTON: _ACTION_DELETE,
        CHANNEL_TOGGLE_BUTTON: _ACTION_TOGGLE,
    }
    action = actions.get(message.text)
    if action is None:
        _clear_pending_action(context)
    else:
        clear_admin_input_state(context)
        context.user_data[CHANNEL_ACTION_KEY] = action
    await message.reply_text(
        instructions.get(message.text, "دستور مدیریت کانال نامعتبر است."),
        reply_markup=build_channel_management_menu(),
    )


async def channel_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resolve a Telegram channel, validate bot admin access, and persist it."""
    message = update.effective_message
    if message is None:
        return
    try:
        payload = _payload(update)
        if "|" in payload:
            reference, invite_value, sort_value = _fields(payload, expected=3)
            invite_link = _optional_field(invite_value)
            sort_order = _sort_order(sort_value)
        else:
            reference = payload
            invite_link = None
            sort_order = 0
        channel = await _resolve_and_create_channel(
            context,
            reference=reference,
            invite_link=invite_link,
            sort_order=sort_order,
        )
    except ChannelError as error:
        await _reply_channel_error(update, error)
        return

    await message.reply_text(
        f"کانال «{channel.title}» با ID داخلی {channel.id} اضافه شد.",
        reply_markup=build_channel_management_menu(),
    )


async def channel_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh a configured channel using only its Telegram reference."""
    message = update.effective_message
    if message is None:
        return
    try:
        channel = await _resolve_and_refresh_channel(
            context,
            reference=_payload(update),
        )
    except ChannelError as error:
        await _reply_channel_error(update, error)
        return

    await message.reply_text(
        f"کانال «{channel.title}» ویرایش شد.",
        reply_markup=build_channel_management_menu(),
    )


async def channel_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete the exact internal channel id supplied by an administrator."""
    message = update.effective_message
    if message is None:
        return
    try:
        channel_id = _positive_integer(_payload(update), field_name="Channel ID")
        await _delete_channel(get_database_manager(context), channel_id)
    except ChannelError as error:
        await _reply_channel_error(update, error)
        return

    await message.reply_text(
        f"کانال با ID داخلی {channel_id} حذف شد.",
        reply_markup=build_channel_management_menu(),
    )


async def channel_pending_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Consume the next simple value requested by a channel management button."""
    action = context.user_data.get(CHANNEL_ACTION_KEY)
    message = update.effective_message
    if action is None or message is None or not message.text:
        return

    value = message.text.strip()
    try:
        if action == _ACTION_ADD:
            channel = await _resolve_and_create_channel(context, reference=value)
            response = f"کانال «{channel.title}» با ID داخلی {channel.id} اضافه شد."
        elif action == _ACTION_EDIT:
            channel = await _resolve_and_refresh_channel(context, reference=value)
            response = f"اطلاعات کانال «{channel.title}» به‌روزرسانی شد."
        elif action == _ACTION_DELETE:
            channel_id = _positive_integer(value, field_name="Channel ID")
            await _delete_channel(get_database_manager(context), channel_id)
            response = f"کانال با ID داخلی {channel_id} حذف شد."
        elif action == _ACTION_TOGGLE:
            channel_id = _positive_integer(value, field_name="Channel ID")
            channel = await _toggle_channel(get_database_manager(context), channel_id)
            state = "فعال" if channel.is_active else "غیرفعال"
            response = f"کانال «{channel.title}» {state} شد."
        else:
            _clear_pending_action(context)
            return
    except ChannelError as error:
        await _reply_channel_error(update, error)
        return

    _clear_pending_action(context)
    await message.reply_text(response, reply_markup=build_channel_management_menu())


async def channel_toggle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Atomically enable or disable a configured channel."""
    message = update.effective_message
    if message is None:
        return
    try:
        channel_id = _positive_integer(_payload(update), field_name="Channel ID")
        channel = await _toggle_channel(get_database_manager(context), channel_id)
    except ChannelError as error:
        await _reply_channel_error(update, error)
        return

    state = "فعال" if channel.is_active else "غیرفعال"
    await message.reply_text(
        f"کانال «{channel.title}» {state} شد.",
        reply_markup=build_channel_management_menu(),
    )


def register_admin_channel_handlers(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    """Register every channel-management route behind admin authorization."""
    private_chat = filters.ChatType.PRIVATE
    guard = admin_required(admin_ids)
    instruction_pattern = (
        "^(?:"
        + "|".join(
            re.escape(value)
            for value in (
                CHANNEL_ADD_BUTTON,
                CHANNEL_EDIT_BUTTON,
                CHANNEL_DELETE_BUTTON,
                CHANNEL_TOGGLE_BUTTON,
            )
        )
        + ")$"
    )

    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(CHANNEL_MANAGEMENT_BUTTON)}$"),
            guard(channel_management_handler),
        )
    )
    application.add_handler(
        CommandHandler("channels", guard(channel_list_handler), filters=private_chat)
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(CHANNEL_LIST_BUTTON)}$"),
            guard(channel_list_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(instruction_pattern),
            guard(channel_instruction_handler),
        )
    )
    application.add_handler(
        CommandHandler("channel_add", guard(channel_add_handler), filters=private_chat)
    )
    application.add_handler(
        CommandHandler("channel_edit", guard(channel_edit_handler), filters=private_chat)
    )
    application.add_handler(
        CommandHandler("channel_delete", guard(channel_delete_handler), filters=private_chat)
    )
    application.add_handler(
        CommandHandler("channel_toggle", guard(channel_toggle_handler), filters=private_chat)
    )
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(CHANNEL_ADMIN_BACK_BUTTON)}$"),
            guard(channel_management_back_handler),
        )
    )
