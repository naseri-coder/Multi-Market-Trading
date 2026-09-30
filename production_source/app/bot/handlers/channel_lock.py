"""Multi-channel membership lock and verification callback."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.bot.dependencies import get_admin_ids, get_database_manager
from app.bot.keyboards.channels import (
    VERIFY_MEMBERSHIP_CALLBACK,
    build_membership_keyboard,
)
from app.bot.keyboards.user import build_user_menu
from app.db.session import DatabaseManager
from app.integrations.telegram.channels import TelegramChannelGateway
from app.modules.channels.entities import ChannelMembershipResult
from app.modules.channels.errors import ChannelError
from app.modules.channels.repository import SQLAlchemyChannelRepository
from app.modules.channels.service import ChannelService

logger = logging.getLogger(__name__)


async def load_membership_result(
    database: DatabaseManager,
    gateway: TelegramChannelGateway,
    *,
    telegram_user_id: int,
) -> ChannelMembershipResult:
    """Check one user against all active channels in one repository session."""
    async with database.session() as session:
        service = ChannelService(SQLAlchemyChannelRepository(session))
        return await service.check_membership(telegram_user_id, gateway)


def render_membership_prompt(result: ChannelMembershipResult) -> str:
    """Render the list of missing channel memberships."""
    titles = "\n".join(f"• {channel.title}" for channel in result.missing_channels)
    return (
        "🔐 عضویت اجباری\n\n"
        "برای استفاده از ربات باید عضو تمام کانال‌های زیر باشید:\n"
        f"{titles}\n\n"
        "پس از عضویت، دکمهٔ «بررسی عضویت» را بزنید."
    )


async def ensure_channel_membership(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Allow admins or users who belong to every active channel."""
    telegram_user = update.effective_user
    message = update.effective_message
    if telegram_user is None or message is None:
        return False
    if telegram_user.id in get_admin_ids(context):
        return True

    try:
        result = await load_membership_result(
            get_database_manager(context),
            TelegramChannelGateway(context.bot),
            telegram_user_id=telegram_user.id,
        )
    except ChannelError:
        logger.exception(
            "Channel membership verification failed closed",
            extra={
                "event": "channel_membership_failed",
                "telegram_user_id": telegram_user.id,
                "update_id": update.update_id,
            },
        )
        await message.reply_text(
            "در حال حاضر بررسی عضویت کانال‌ها ممکن نیست. لطفاً کمی بعد دوباره تلاش کنید."
        )
        return False

    if result.allowed:
        return True

    await message.reply_text(
        render_membership_prompt(result),
        reply_markup=build_membership_keyboard(result.missing_channels),
    )
    return False


async def verify_membership_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Recheck all active channels after the user presses the verify button."""
    query = update.callback_query
    telegram_user = update.effective_user
    if query is None or telegram_user is None:
        return

    await query.answer("در حال بررسی عضویت...")

    if telegram_user.id in get_admin_ids(context):
        result = ChannelMembershipResult(True, 0, ())
    else:
        try:
            result = await load_membership_result(
                get_database_manager(context),
                TelegramChannelGateway(context.bot),
                telegram_user_id=telegram_user.id,
            )
        except ChannelError:
            logger.exception(
                "Channel membership callback failed closed",
                extra={
                    "event": "channel_membership_callback_failed",
                    "telegram_user_id": telegram_user.id,
                    "update_id": update.update_id,
                },
            )
            message = query.message
            if message is not None and hasattr(message, "reply_text"):
                await message.reply_text("بررسی عضویت فعلاً ممکن نیست. کمی بعد دوباره تلاش کنید.")
            return

    if not result.allowed:
        try:
            await query.edit_message_text(
                render_membership_prompt(result),
                reply_markup=build_membership_keyboard(result.missing_channels),
            )
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
        return

    await query.edit_message_text("✅ عضویت شما در تمام کانال‌های فعال تأیید شد.")
    message = query.message
    if message is not None and hasattr(message, "reply_text"):
        await message.reply_text(
            "اکنون می‌توانید از امکانات ربات استفاده کنید.",
            reply_markup=build_user_menu(is_admin=telegram_user.id in get_admin_ids(context)),
        )


def register_channel_lock_handlers(application: Application) -> None:
    """Register the exact allow-listed membership verification callback."""
    application.add_handler(
        CallbackQueryHandler(
            verify_membership_handler,
            pattern=rf"^{VERIFY_MEMBERSHIP_CALLBACK}$",
        )
    )
