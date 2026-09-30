"""Public Telegram adapter for user signal favorites."""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from telegram import CallbackQuery, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.dependencies import get_admin_ids, get_database_manager, get_report_timezone
from app.bot.handlers.admin_state import clear_admin_input_state
from app.bot.handlers.channel_lock import ensure_channel_membership
from app.bot.handlers.signals_user import load_signal_detail, render_signal_detail
from app.bot.handlers.support_state import clear_support_user_state
from app.bot.handlers.users import sync_user, telegram_user_to_identity
from app.bot.keyboards.favorites import (
    FAVORITES_BUTTON,
    FAVORITES_CALLBACK_PATTERN,
    build_favorite_detail_actions,
    build_favorites_list,
)
from app.bot.keyboards.signals import build_signal_detail_actions
from app.bot.keyboards.user import build_user_menu
from app.db.session import DatabaseManager
from app.modules.favorites.entities import FavoriteMutation, FavoritePage
from app.modules.favorites.errors import FavoriteError
from app.modules.favorites.repository import SQLAlchemyFavoriteRepository
from app.modules.favorites.service import FavoriteService
from app.modules.signals.entities import SignalListMode
from app.modules.signals.errors import SignalError
from app.modules.signals.models import SignalStatus
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    SignalStatus.OPEN.value: "باز",
    SignalStatus.CLOSED.value: "بسته",
    SignalStatus.CANCELLED.value: "لغوشده",
}
_STATUS_EMOJIS = {
    SignalStatus.OPEN.value: "🟢",
    SignalStatus.CLOSED.value: "✅",
    SignalStatus.CANCELLED.value: "🚫",
}


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


async def load_favorite_page(
    database: DatabaseManager,
    user_id: int,
    *,
    page: int,
) -> FavoritePage:
    async with database.session() as session:
        service = FavoriteService(SQLAlchemyFavoriteRepository(session))
        return await service.get_page(user_id, page=page)


async def load_favorite_status(
    database: DatabaseManager,
    user_id: int,
    signal_id: int,
) -> bool:
    async with database.session() as session:
        service = FavoriteService(SQLAlchemyFavoriteRepository(session))
        return await service.is_favorite(user_id, signal_id)


async def mutate_favorite(
    database: DatabaseManager,
    user_id: int,
    signal_id: int,
    *,
    action: str,
) -> FavoriteMutation:
    async with database.session() as session, session.begin():
        service = FavoriteService(SQLAlchemyFavoriteRepository(session))
        if action == "add":
            return await service.add(user_id, signal_id)
        if action == "remove":
            return await service.remove(user_id, signal_id)
        raise ValueError("Unsupported favorite mutation")


def render_favorite_page(page: FavoritePage) -> tuple[str, InlineKeyboardMarkup]:
    """Render one bounded favorites collection."""
    lines = [
        "⭐ علاقه‌مندی‌های من",
        f"🔢 تعداد: {page.total_items} | 📄 صفحه {page.page} از {page.total_pages}",
        "",
    ]
    buttons: list[tuple[int, str]] = []
    if not page.signals:
        lines.extend(
            (
                "ℹ️ هنوز سیگنالی به علاقه‌مندی‌ها "
                "اضافه نکرده‌اید.",
                "از صفحه جزئیات Signal روی «افزودن به "
                "علاقه‌مندی‌ها» بزنید.",
            )
        )
    for signal in page.signals:
        status = _STATUS_LABELS.get(signal.status, signal.status)
        status_emoji = _STATUS_EMOJIS.get(signal.status, "📌")
        lines.extend(
            (
                f"🆔 سیگنال #{signal.id}",
                f"💱 نماد: {signal.symbol}",
                f"{status_emoji} وضعیت: {status} | "
                f"🎯 ورود: {_format_decimal(signal.entry_price)}",
                "",
            )
        )
        buttons.append(
            (signal.id, f"{status_emoji} #{signal.id} — {signal.symbol} — {status}")
        )
    return "\n".join(lines), build_favorites_list(
        buttons,
        page=page.page,
        total_pages=page.total_pages,
    )


async def favorites_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open the first page of the current user's favorites."""
    clear_support_user_state(context)
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None:
        return
    user_id = await _prepare_favorite_access(update, context)
    if user_id is None:
        return
    try:
        page = await load_favorite_page(
            get_database_manager(context),
            user_id,
            page=1,
        )
    except FavoriteError:
        logger.exception(
            "Public favorites list failed",
            extra={"event": "favorites_user_list_failed"},
        )
        await message.reply_text(
            "دریافت علاقه‌مندی‌ها ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return
    text, reply_markup = render_favorite_page(page)
    await message.reply_text(text, reply_markup=reply_markup)


async def favorites_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle exact favorite list, detail, and mutation callbacks."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer("در حال پردازش...")
    user_id = await _prepare_favorite_access(update, context)
    if user_id is None:
        return

    try:
        parts = query.data.split(":")
        action = parts[3]
        if action == "menu":
            await _safe_edit_favorite_message(query, "به منوی اصلی بازگشتید.")
            message = query.message
            if message is not None and hasattr(message, "reply_text"):
                await message.reply_text(
                    "یک گزینه را انتخاب کنید.",
                    reply_markup=build_user_menu(
                        is_admin=user.id in get_admin_ids(context)
                    ),
                )
            return
        if action == "list":
            await _show_favorite_page(
                query,
                get_database_manager(context),
                user_id,
                page=int(parts[4]),
            )
            return
        if action == "view":
            await _show_favorite_detail(
                query,
                context,
                user_id=user_id,
                list_page=int(parts[4]),
                signal_id=int(parts[5]),
                target_page=int(parts[6]),
            )
            return
        await _toggle_favorite(
            query,
            context,
            user_id=user_id,
            mutation=parts[4],
            source=parts[5],
            list_page=int(parts[6]),
            signal_id=int(parts[7]),
            target_page=int(parts[8]),
        )
    except (FavoriteError, IndexError, SignalError, ValueError):
        logger.exception(
            "Public favorite callback failed",
            extra={"event": "favorites_user_callback_failed"},
        )
        await _safe_edit_favorite_message(
            query,
            "علاقه‌مندی یا Signal در دسترس نیست یا "
            "درخواست نامعتبر است.",
        )


async def _show_favorite_page(
    query: CallbackQuery,
    database: DatabaseManager,
    user_id: int,
    *,
    page: int,
) -> None:
    favorite_page = await load_favorite_page(database, user_id, page=page)
    text, reply_markup = render_favorite_page(favorite_page)
    await _safe_edit_favorite_message(query, text, reply_markup=reply_markup)


async def _show_favorite_detail(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    list_page: int,
    signal_id: int,
    target_page: int,
) -> None:
    database = get_database_manager(context)
    detail = await load_signal_detail(
        database,
        signal_id,
        target_page=target_page,
    )
    is_favorite = await load_favorite_status(database, user_id, signal_id)
    await _safe_edit_favorite_message(
        query,
        render_signal_detail(
            detail,
            timezone_name=get_report_timezone(context),
        ),
        reply_markup=build_favorite_detail_actions(
            signal_id,
            list_page=list_page,
            target_page=detail.target_page,
            total_target_pages=detail.total_target_pages,
            is_favorite=is_favorite,
        ),
    )


async def _toggle_favorite(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    mutation: str,
    source: str,
    list_page: int,
    signal_id: int,
    target_page: int,
) -> None:
    database = get_database_manager(context)
    await mutate_favorite(
        database,
        user_id,
        signal_id,
        action=mutation,
    )
    detail = await load_signal_detail(
        database,
        signal_id,
        target_page=target_page,
    )
    is_favorite = await load_favorite_status(database, user_id, signal_id)
    if source == "favorites":
        reply_markup = build_favorite_detail_actions(
            signal_id,
            list_page=list_page,
            target_page=detail.target_page,
            total_target_pages=detail.total_target_pages,
            is_favorite=is_favorite,
        )
    else:
        mode = SignalListMode(source).value
        reply_markup = build_signal_detail_actions(
            signal_id,
            mode=mode,
            list_page=list_page,
            target_page=detail.target_page,
            total_target_pages=detail.total_target_pages,
            is_favorite=is_favorite,
        )
    await _safe_edit_favorite_message(
        query,
        render_signal_detail(
            detail,
            timezone_name=get_report_timezone(context),
        ),
        reply_markup=reply_markup,
    )


async def _prepare_favorite_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int | None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return None
    if not await ensure_channel_membership(update, context):
        return None
    try:
        result = await sync_user(
            get_database_manager(context),
            telegram_user_to_identity(user),
        )
    except (InvalidUserIdentityError, UserRepositoryError):
        logger.exception(
            "Favorites interface user synchronization failed",
            extra={
                "event": "favorites_user_sync_failed",
                "telegram_user_id": user.id,
            },
        )
        await message.reply_text(
            "دسترسی به علاقه‌مندی‌ها فعلاً ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return None
    return result.profile.id


async def _safe_edit_favorite_message(
    query: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


def register_favorites_user_handlers(application: Application) -> None:
    """Register one favorites entry surface and one exact callback handler."""
    private = filters.ChatType.PRIVATE
    application.add_handler(
        CommandHandler("favorites", favorites_menu_handler, filters=private)
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(FAVORITES_BUTTON)}$"),
            favorites_menu_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            favorites_callback_handler,
            pattern=FAVORITES_CALLBACK_PATTERN,
        )
    )
