"""Public Telegram signal collections, details, and target pagination."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

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
from app.bot.handlers.support_state import clear_support_user_state
from app.bot.handlers.users import sync_user, telegram_user_to_identity
from app.bot.keyboards.signals import (
    LIVE_SIGNALS_BUTTON,
    OPEN_SIGNALS_BUTTON,
    SIGNAL_HISTORY_BUTTON,
    USER_SIGNAL_CALLBACK_PATTERN,
    build_signal_detail_actions,
    build_signal_list,
)
from app.bot.keyboards.user import build_user_menu
from app.db.session import DatabaseManager
from app.modules.favorites.errors import FavoriteError
from app.modules.favorites.repository import SQLAlchemyFavoriteRepository
from app.modules.favorites.service import FavoriteService
from app.modules.signals.entities import (
    AdminSignalDetail,
    SignalDetail,
    SignalListMode,
    SignalPage,
)
from app.modules.signals.errors import SignalError
from app.modules.signals.models import SignalDirection, SignalStatus, SignalTargetStatus
from app.modules.signals.query_service import SignalQueryService
from app.modules.signals.repository import SQLAlchemySignalRepository
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError

logger = logging.getLogger(__name__)

_MODE_TITLES = {
    SignalListMode.LIVE.value: "📡 سیگنال‌های لحظه‌ای",
    SignalListMode.OPEN.value: "🟢 سیگنال‌های باز",
    SignalListMode.HISTORY.value: "📜 تاریخچه سیگنال‌ها",
}
_STATUS_LABELS = {
    SignalStatus.DRAFT.value: "پیش‌نویس",
    SignalStatus.OPEN.value: "باز",
    SignalStatus.CLOSED.value: "بسته",
    SignalStatus.CANCELLED.value: "لغوشده",
}
_STATUS_EMOJIS = {
    SignalStatus.DRAFT.value: "📝",
    SignalStatus.OPEN.value: "🟢",
    SignalStatus.CLOSED.value: "✅",
    SignalStatus.CANCELLED.value: "🚫",
}
_DIRECTION_LABELS = {
    SignalDirection.LONG.value: "خرید (LONG)",
    SignalDirection.SHORT.value: "فروش (SHORT)",
}
_DIRECTION_EMOJIS = {
    SignalDirection.LONG.value: "🟩",
    SignalDirection.SHORT.value: "🟥",
}
_TARGET_STATUS_LABELS = {
    SignalTargetStatus.PENDING.value: "در انتظار",
    SignalTargetStatus.HIT.value: "هدف خورده",
    SignalTargetStatus.CANCELLED.value: "لغوشده",
}
_TARGET_STATUS_EMOJIS = {
    SignalTargetStatus.PENDING.value: "⏳",
    SignalTargetStatus.HIT.value: "✅",
    SignalTargetStatus.CANCELLED.value: "🚫",
}


async def load_signal_page(
    database: DatabaseManager,
    mode: str,
    *,
    page: int,
) -> SignalPage:
    async with database.session() as session:
        return await SignalQueryService(SQLAlchemySignalRepository(session)).get_page(
            mode,
            page=page,
        )


async def load_signal_detail(
    database: DatabaseManager,
    signal_id: int,
    *,
    target_page: int,
) -> SignalDetail:
    async with database.session() as session:
        return await SignalQueryService(SQLAlchemySignalRepository(session)).get_detail(
            signal_id,
            target_page=target_page,
        )


async def load_favorite_status(
    database: DatabaseManager,
    user_id: int,
    signal_id: int,
) -> bool:
    async with database.session() as session:
        service = FavoriteService(SQLAlchemyFavoriteRepository(session))
        return await service.is_favorite(user_id, signal_id)


def render_signal_page(page: SignalPage) -> tuple[str, InlineKeyboardMarkup]:
    """Render one bounded signal collection and its exact callback allowlist."""
    title = _MODE_TITLES[page.mode]
    lines = [
        title,
        f"🔢 تعداد: {page.total_items} | 📄 صفحه {page.page} از {page.total_pages}",
        "",
    ]
    buttons: list[tuple[int, str]] = []
    if not page.signals:
        lines.append(
            "ℹ️ در حال حاضر سیگنالی در این بخش وجود ندارد."
        )
    for signal in page.signals:
        direction = _DIRECTION_LABELS.get(signal.direction, signal.direction)
        direction_emoji = _DIRECTION_EMOJIS.get(signal.direction, "🧭")
        status = _STATUS_LABELS.get(signal.status, signal.status)
        status_emoji = _STATUS_EMOJIS.get(signal.status, "📌")
        lines.extend(
            (
                f"🆔 سیگنال #{signal.id}",
                f"💱 نماد: {signal.symbol} | {direction_emoji} جهت: {direction}",
                f"{status_emoji} وضعیت: {status} "
                f"| 🎯 ورود: {_format_decimal(signal.entry_price)}",
                f"📈 سود/زیان (P/L): {_format_decimal(signal.profit_loss)}",
                "",
            )
        )
        buttons.append(
            (signal.id, f"{status_emoji} #{signal.id} — {signal.symbol} — {status}")
        )
    lines.append(
        "👁 برای مشاهده جزئیات، "
        "سیگنال موردنظر را انتخاب کنید."
    )
    return "\n".join(lines), build_signal_list(
        buttons,
        mode=page.mode,
        page=page.page,
        total_pages=page.total_pages,
    )


def render_signal_detail(
    detail: SignalDetail | AdminSignalDetail,
    *,
    timezone_name: str,
) -> str:
    """Render complete signal fields with one bounded page of targets."""
    signal = detail.signal
    direction = _DIRECTION_LABELS.get(signal.direction, signal.direction)
    direction_emoji = _DIRECTION_EMOJIS.get(signal.direction, "🧭")
    status = _STATUS_LABELS.get(signal.status, signal.status)
    status_emoji = _STATUS_EMOJIS.get(signal.status, "📌")
    lines = [
        f"📡 جزئیات سیگنال #{signal.id}",
        "",
        f"💱 نماد: {signal.symbol}",
        f"{direction_emoji} جهت: {direction}",
        f"{status_emoji} وضعیت: {status}",
        f"🎯 قیمت ورود: {_format_decimal(signal.entry_price)}",
        f"🛡️ حد ضرر: {_format_decimal(signal.stop_loss)}",
        f"⚡ اهرم: {_format_decimal(signal.leverage)}x",
        f"📈 سود/زیان (P/L): {_format_decimal(signal.profit_loss)}",
        f"🕒 ایجاد: {_format_datetime(signal.created_at, timezone_name)}",
    ]
    if signal.closed_at is not None:
        lines.append(
            f"🏁 بسته‌شدن: {_format_datetime(signal.closed_at, timezone_name)}"
        )
    if signal.description:
        description = (
            signal.description
            if len(signal.description) <= 1000
            else f"{signal.description[:997]}..."
        )
        lines.extend(("", f"📝 توضیحات: {description}"))
    lines.extend(
        (
            "",
            "🎯 اهداف",
            (
                f"🔢 تعداد: {detail.total_targets} | 📄 صفحه {detail.target_page} "
                f"از {detail.total_target_pages}"
            ),
        )
    )
    if not detail.targets:
        lines.append("ℹ️ هدفی برای این سیگنال ثبت نشده است.")
    for target in detail.targets:
        target_status = _TARGET_STATUS_LABELS.get(target.status, target.status)
        target_status_emoji = _TARGET_STATUS_EMOJIS.get(target.status, "📌")
        lines.append(
            f"🎯 هدف {target.target_number}: {_format_decimal(target.target_price)} "
            f"| {target_status_emoji} {target_status} "
            f"| 📈 سود/زیان: {_format_decimal(target.profit_loss)}"
        )
        if target.hit_at is not None:
            lines.append(
                f"🕒 زمان برخورد: {_format_datetime(target.hit_at, timezone_name)}"
            )
    return "\n".join(lines)


async def signal_list_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
) -> None:
    """Validate user access and send the first page for one collection."""
    clear_support_user_state(context)
    clear_admin_input_state(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if await _prepare_user_access(update, context) is None:
        return
    try:
        page = await load_signal_page(get_database_manager(context), mode, page=1)
    except SignalError:
        logger.exception(
            "Public signal list failed",
            extra={"event": "signal_user_list_failed", "mode": mode},
        )
        await message.reply_text(
            "دریافت سیگنال‌ها با خطا مواجه شد. "
            "کمی بعد تلاش کنید."
        )
        return
    text, reply_markup = render_signal_page(page)
    await message.reply_text(text, reply_markup=reply_markup)


async def live_signals_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await signal_list_handler(update, context, mode=SignalListMode.LIVE.value)


async def open_signals_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await signal_list_handler(update, context, mode=SignalListMode.OPEN.value)


async def signal_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await signal_list_handler(update, context, mode=SignalListMode.HISTORY.value)


async def signal_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle only versioned, anchored, allow-listed public signal callbacks."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer("در حال پردازش...")
    user_id = await _prepare_user_access(update, context)
    if user_id is None:
        return
    try:
        parts = query.data.split(":")
        action = parts[3]
        if action == "menu":
            await _safe_edit_signal_message(query, "به منوی اصلی بازگشتید.")
            message = query.message
            if message is not None and hasattr(message, "reply_text"):
                await message.reply_text(
                    "یک گزینه را انتخاب کنید.",
                    reply_markup=build_user_menu(is_admin=user.id in get_admin_ids(context)),
                )
            return
        mode = SignalListMode(parts[4]).value
        list_page = int(parts[5])
        if action == "list":
            page = await load_signal_page(
                get_database_manager(context),
                mode,
                page=list_page,
            )
            text, reply_markup = render_signal_page(page)
            await _safe_edit_signal_message(query, text, reply_markup=reply_markup)
            return
        signal_id = int(parts[6])
        target_page = int(parts[7])
        detail = await load_signal_detail(
            get_database_manager(context),
            signal_id,
            target_page=target_page,
        )
        is_favorite = await load_favorite_status(
            get_database_manager(context),
            user_id,
            signal_id,
        )
        await _safe_edit_signal_message(
            query,
            render_signal_detail(
                detail,
                timezone_name=get_report_timezone(context),
            ),
            reply_markup=build_signal_detail_actions(
                signal_id,
                mode=mode,
                list_page=list_page,
                target_page=detail.target_page,
                total_target_pages=detail.total_target_pages,
                is_favorite=is_favorite,
            ),
        )
    except (FavoriteError, IndexError, SignalError, ValueError):
        await _safe_edit_signal_message(
            query,
            "سیگنال در دسترس نیست یا درخواست نامعتبر است.",
        )


async def _prepare_user_access(
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
            "Signal interface user synchronization failed",
            extra={"event": "signal_user_sync_failed", "telegram_user_id": user.id},
        )
        await message.reply_text(
            "دسترسی به سیگنال‌ها فعلاً ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return None
    return result.profile.id


async def _safe_edit_signal_message(
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


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    formatted = format(value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


def _format_datetime(value: datetime, timezone_name: str) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M")


def register_signal_user_handlers(application: Application) -> None:
    """Register three public collections and one exact callback surface."""
    private = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("signals", live_signals_handler, filters=private))
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(LIVE_SIGNALS_BUTTON)}$"),
            live_signals_handler,
        )
    )
    application.add_handler(
        CommandHandler("open_signals", open_signals_handler, filters=private)
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(OPEN_SIGNALS_BUTTON)}$"),
            open_signals_handler,
        )
    )
    application.add_handler(
        CommandHandler("signal_history", signal_history_handler, filters=private)
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SIGNAL_HISTORY_BUTTON)}$"),
            signal_history_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            signal_callback_handler,
            pattern=USER_SIGNAL_CALLBACK_PATTERN,
        )
    )
