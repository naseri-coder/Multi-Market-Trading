"""Telegram handlers for user registration and profile display."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from telegram import Update
from telegram import User as TelegramUser
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.dependencies import get_admin_ids, get_database_manager
from app.bot.handlers.channel_lock import ensure_channel_membership
from app.bot.keyboards.user import PROFILE_BUTTON, build_user_menu
from app.db.session import DatabaseManager
from app.modules.referrals.errors import ReferralError
from app.modules.referrals.repository import SQLAlchemyReferralRepository
from app.modules.referrals.service import ReferralService
from app.modules.users.entities import TelegramUserIdentity, UserProfile, UserRegistrationResult
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError
from app.modules.users.repository import SQLAlchemyUserRepository
from app.modules.users.service import UserService

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "ACTIVE": "فعال",
    "BLOCKED": "مسدود",
    "DEACTIVATED": "غیرفعال",
}


def telegram_user_to_identity(user: TelegramUser) -> TelegramUserIdentity:
    """Map the Telegram adapter object to a domain DTO."""
    return TelegramUserIdentity(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_bot=user.is_bot,
    )


async def sync_user(
    database: DatabaseManager,
    identity: TelegramUserIdentity,
) -> UserRegistrationResult:
    """Execute one user synchronization transaction."""
    async with database.session() as session, session.begin():
        repository = SQLAlchemyUserRepository(session)
        service = UserService(repository)
        return await service.register_or_update(identity)


def _format_utc(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def render_profile(profile: UserProfile) -> str:
    """Render a safe plain-text profile without parse-mode escaping concerns."""
    username = f"@{profile.username}" if profile.username else "ثبت نشده"
    language = profile.language_code or "نامشخص"
    status = _STATUS_LABELS.get(profile.status, profile.status)

    return "\n".join(
        (
            "👤 پروفایل من",
            "",
            f"نام: {profile.full_name}",
            f"نام کاربری: {username}",
            f"شناسه تلگرام: {profile.telegram_user_id}",
            f"زبان: {language}",
            f"وضعیت: {status}",
            f"تاریخ عضویت: {_format_utc(profile.created_at)}",
            f"آخرین فعالیت: {_format_utc(profile.last_activity)}",
        )
    )


async def _reply_temporary_error(update: Update) -> None:
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "در حال حاضر دسترسی به اطلاعات کاربری ممکن نیست. لطفاً کمی بعد دوباره تلاش کنید."
        )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register or refresh a Telegram user and display the base menu."""
    telegram_user = update.effective_user
    message = update.effective_message
    if telegram_user is None or message is None:
        return

    try:
        result = await sync_user(
            get_database_manager(context),
            telegram_user_to_identity(telegram_user),
        )
    except (InvalidUserIdentityError, UserRepositoryError):
        logger.exception(
            "User synchronization failed",
            extra={"event": "user_sync_failed", "telegram_user_id": telegram_user.id},
        )
        await _reply_temporary_error(update)
        return

    referral_note = None
    if result.created:
        referral_note = await _apply_start_referral(
            get_database_manager(context),
            result.profile.id,
            getattr(context, "args", None),
        )

    if not await ensure_channel_membership(update, context):
        return

    if result.created:
        text = (
            f"سلام {result.profile.first_name} 👋\n\n"
            "ثبت‌نام شما با موفقیت انجام شد. از منوی زیر می‌توانید پروفایل خود را مشاهده کنید."
        )
        if referral_note:
            text = f"{text}\n\n{referral_note}"
    else:
        text = (
            f"خوش آمدید {result.profile.first_name} 👋\n\n"
            "اطلاعات پروفایل و آخرین فعالیت شما به‌روزرسانی شد."
        )

    await message.reply_text(
        text,
        reply_markup=build_user_menu(is_admin=telegram_user.id in get_admin_ids(context)),
    )


async def _apply_start_referral(
    database: DatabaseManager,
    referred_user_id: int,
    args: object,
) -> str | None:
    """Apply one referral only on the first /start without blocking signup."""
    if not isinstance(args, (list, tuple)) or len(args) != 1:
        return None
    payload = args[0]
    if not isinstance(payload, str) or not payload.startswith("ref_"):
        return None
    referral_code = payload.removeprefix("ref_")
    try:
        async with database.session() as session, session.begin():
            service = ReferralService(SQLAlchemyReferralRepository(session))
            registration = await service.register_referral(
                referred_user_id,
                referral_code,
            )
    except ReferralError:
        logger.warning(
            "Referral start payload rejected",
            extra={
                "event": "referral_start_rejected",
                "referred_user_id": referred_user_id,
            },
        )
        return (
            "⚠️ کد دعوت معتبر نبود؛ "
            "ثبت‌نام شما بدون معرف انجام شد."
        )
    if registration.changed:
        return "🎉 دعوت شما با موفقیت برای معرف ثبت شد."
    return None


async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh and display the current Telegram user's profile."""
    telegram_user = update.effective_user
    message = update.effective_message
    if telegram_user is None or message is None:
        return

    if not await ensure_channel_membership(update, context):
        return

    try:
        result = await sync_user(
            get_database_manager(context),
            telegram_user_to_identity(telegram_user),
        )
    except (InvalidUserIdentityError, UserRepositoryError):
        logger.exception(
            "User profile lookup failed",
            extra={"event": "user_profile_failed", "telegram_user_id": telegram_user.id},
        )
        await _reply_temporary_error(update)
        return

    await message.reply_text(
        render_profile(result.profile),
        reply_markup=build_user_menu(is_admin=telegram_user.id in get_admin_ids(context)),
    )


def register_user_handlers(application: Application) -> None:
    """Register Phase 4 private-chat user handlers in deterministic order."""
    private_chat = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", start_handler, filters=private_chat))
    application.add_handler(CommandHandler("profile", profile_handler, filters=private_chat))
    application.add_handler(
        MessageHandler(
            private_chat & filters.Regex(rf"^{re.escape(PROFILE_BUTTON)}$"),
            profile_handler,
        )
    )
