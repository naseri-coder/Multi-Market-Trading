"""Public Telegram adapter for referral links and statistics."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from telegram import CallbackQuery, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
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
from app.bot.handlers.channel_lock import ensure_channel_membership
from app.bot.handlers.support_state import clear_support_user_state
from app.bot.handlers.users import sync_user, telegram_user_to_identity
from app.bot.keyboards.referrals import (
    REFERRALS_BUTTON,
    REFERRALS_CALLBACK_PATTERN,
    build_invited_users_page,
    build_referral_dashboard,
)
from app.bot.keyboards.user import build_user_menu
from app.db.session import DatabaseManager
from app.modules.referrals.entities import (
    InvitedUsersPage,
    ReferralDashboard,
)
from app.modules.referrals.errors import ReferralError
from app.modules.referrals.repository import SQLAlchemyReferralRepository
from app.modules.referrals.service import ReferralService
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "ACTIVE": "فعال",
    "BLOCKED": "مسدود",
    "DEACTIVATED": "غیرفعال",
}


async def load_referral_dashboard(
    database: DatabaseManager,
    user_id: int,
) -> ReferralDashboard:
    """Load or create the user's code and aggregate statistics atomically."""
    async with database.session() as session, session.begin():
        service = ReferralService(SQLAlchemyReferralRepository(session))
        return await service.get_dashboard(user_id)


async def load_invited_users_page(
    database: DatabaseManager,
    user_id: int,
    *,
    page: int,
) -> InvitedUsersPage:
    """Load one database-paginated invited-user collection."""
    async with database.session() as session:
        service = ReferralService(SQLAlchemyReferralRepository(session))
        return await service.get_invited_page(user_id, page=page)


def render_referral_dashboard(
    dashboard: ReferralDashboard,
    *,
    bot_username: str,
) -> str:
    """Render a shareable referral link and transparent disabled reward state."""
    stats = dashboard.statistics
    referral_link = f"https://t.me/{bot_username}?start=ref_{dashboard.referral_code}"
    return "\n".join(
        (
            "🎁 دعوت دوستان",
            "",
            f"🔑 کد دعوت شما: {dashboard.referral_code}",
            "🔗 لینک اختصاصی دعوت:",
            referral_link,
            "",
            "📊 آمار دعوت",
            f"👥 مجموع دعوت‌شده‌ها: {stats.total_invited}",
            f"✅ کاربران فعال: {stats.active_invited}",
            f"⏸ کاربران غیرفعال: {stats.inactive_invited}",
            "🎉 پاداش ثبت‌شده: ۰",
            "",
            "ℹ️ سیستم پاداش در حال حاضر غیرفعال است؛ "
            "دعوت‌ها ثبت می‌شوند اما "
            "پاداشی محاسبه نمی‌شود.",
        )
    )


def render_invited_users_page(page: InvitedUsersPage) -> str:
    """Render ten invited users without exposing private Telegram ids."""
    lines = [
        "👥 کاربران دعوت‌شده",
        f"🔢 تعداد: {page.total_items} | 📄 صفحه {page.page} از {page.total_pages}",
        "",
    ]
    if not page.users:
        lines.append(
            "ℹ️ هنوز کاربری با لینک دعوت شما "
            "ثبت‌نام نکرده است."
        )
    first_index = (page.page - 1) * page.page_size + 1
    for index, user in enumerate(page.users, start=first_index):
        username = f"@{user.username}" if user.username else "بدون نام کاربری"
        status = _STATUS_LABELS.get(user.status, user.status)
        lines.extend(
            (
                f"{index}. 👤 {user.full_name}",
                f"   🆔 {username} | وضعیت: {status}",
                f"   📅 تاریخ دعوت: {_format_utc(user.invited_at)}",
                "",
            )
        )
    return "\n".join(lines).rstrip()


async def referrals_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open the current user's referral dashboard."""
    clear_support_user_state(context)
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None:
        return
    user_id = await _prepare_referral_access(update, context)
    if user_id is None:
        return
    try:
        dashboard = await load_referral_dashboard(
            get_database_manager(context),
            user_id,
        )
        bot_username = await _get_bot_username(context)
    except (ReferralError, TelegramError):
        logger.exception(
            "Referral dashboard failed",
            extra={"event": "referrals_user_dashboard_failed"},
        )
        await message.reply_text(
            "دریافت لینک دعوت فعلاً ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return
    await message.reply_text(
        render_referral_dashboard(dashboard, bot_username=bot_username),
        reply_markup=build_referral_dashboard(),
        disable_web_page_preview=True,
    )


async def referrals_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle exact referral dashboard and pagination callbacks."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer("در حال پردازش...")
    user_id = await _prepare_referral_access(update, context)
    if user_id is None:
        return
    try:
        action = query.data.split(":")[3]
        if action == "menu":
            await _safe_edit_referral_message(query, "به منوی اصلی بازگشتید.")
            message = query.message
            if message is not None and hasattr(message, "reply_text"):
                await message.reply_text(
                    "یک گزینه را انتخاب کنید.",
                    reply_markup=build_user_menu(
                        is_admin=user.id in get_admin_ids(context)
                    ),
                )
            return
        if action == "dashboard":
            dashboard = await load_referral_dashboard(
                get_database_manager(context),
                user_id,
            )
            await _safe_edit_referral_message(
                query,
                render_referral_dashboard(
                    dashboard,
                    bot_username=await _get_bot_username(context),
                ),
                reply_markup=build_referral_dashboard(),
                disable_web_page_preview=True,
            )
            return
        page = int(query.data.split(":")[4])
        invited = await load_invited_users_page(
            get_database_manager(context),
            user_id,
            page=page,
        )
        await _safe_edit_referral_message(
            query,
            render_invited_users_page(invited),
            reply_markup=build_invited_users_page(
                page=invited.page,
                total_pages=invited.total_pages,
            ),
        )
    except (ReferralError, TelegramError, IndexError, ValueError):
        logger.exception(
            "Referral callback failed",
            extra={"event": "referrals_user_callback_failed"},
        )
        await _safe_edit_referral_message(
            query,
            "اطلاعات دعوت در دسترس نیست یا "
            "درخواست نامعتبر است.",
        )


async def _prepare_referral_access(
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
            "Referral interface user synchronization failed",
            extra={
                "event": "referrals_user_sync_failed",
                "telegram_user_id": user.id,
            },
        )
        await message.reply_text(
            "دسترسی به دعوت دوستان فعلاً ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return None
    return result.profile.id


async def _get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    username = context.bot.username
    if not username:
        username = (await context.bot.get_me()).username
    if not username or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise TelegramError("Bot username is unavailable")
    return username


def _format_utc(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).strftime("%Y-%m-%d")


async def _safe_edit_referral_message(
    query: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    disable_web_page_preview: bool | None = None,
) -> None:
    try:
        kwargs: dict[str, object] = {"reply_markup": reply_markup}
        if disable_web_page_preview is not None:
            kwargs["disable_web_page_preview"] = disable_web_page_preview
        await query.edit_message_text(text, **kwargs)
    except BadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


def register_referrals_user_handlers(application: Application) -> None:
    """Register the referral entry surface and one exact callback handler."""
    private = filters.ChatType.PRIVATE
    application.add_handler(
        CommandHandler("referral", referrals_menu_handler, filters=private)
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(REFERRALS_BUTTON)}$"),
            referrals_menu_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            referrals_callback_handler,
            pattern=REFERRALS_CALLBACK_PATTERN,
        )
    )
