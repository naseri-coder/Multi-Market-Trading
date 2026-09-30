"""Public Telegram adapter for user subscription status."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.dependencies import get_admin_ids, get_database_manager, get_report_timezone
from app.bot.handlers.admin_state import clear_admin_input_state
from app.bot.handlers.channel_lock import ensure_channel_membership
from app.bot.handlers.support_state import clear_support_user_state
from app.bot.handlers.users import sync_user, telegram_user_to_identity
from app.bot.keyboards.subscriptions import SUBSCRIPTION_STATUS_BUTTON
from app.bot.keyboards.user import build_user_menu
from app.db.session import DatabaseManager
from app.modules.subscriptions.entities import SubscriptionRecord
from app.modules.subscriptions.errors import SubscriptionError
from app.modules.subscriptions.repository import SQLAlchemySubscriptionRepository
from app.modules.subscriptions.service import SubscriptionService
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError

logger = logging.getLogger(__name__)


async def load_user_subscription(
    database: DatabaseManager,
    user_id: int,
) -> SubscriptionRecord | None:
    """Load status and persist automatic expiry in one transaction."""
    async with database.session() as session, session.begin():
        service = SubscriptionService(SQLAlchemySubscriptionRepository(session))
        return await service.get_user_subscription(user_id)


def _format_time(value: datetime, timezone_name: str) -> str:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = UTC
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(timezone).strftime("%Y-%m-%d %H:%M")


def render_subscription_status(
    subscription: SubscriptionRecord | None,
    *,
    now: datetime,
    timezone_name: str,
) -> str:
    """Render a concise, auditable user entitlement status."""
    if subscription is None:
        return "\n".join(
            (
                "💎 وضعیت اشتراک",
                "",
                "وضعیت: عادی (بدون اشتراک فعال)",
                "",
                "ℹ️ فعال‌سازی پلن در حال حاضر توسط مدیریت انجام می‌شود.",
            )
        )
    remaining_days = subscription.remaining_days(at=now.astimezone(UTC))
    return "\n".join(
        (
            "💎 وضعیت اشتراک",
            "",
            "وضعیت: فعال ✅",
            f"پلن: {subscription.plan_name}",
            f"مدت پلن: {subscription.duration_days} روز",
            f"شروع: {_format_time(subscription.starts_at, timezone_name)}",
            f"پایان: {_format_time(subscription.expires_at, timezone_name)}",
            f"زمان باقی‌مانده: {remaining_days} روز",
        )
    )


async def subscription_status_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Synchronize the Telegram user and display current entitlement."""
    clear_support_user_state(context)
    clear_admin_input_state(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not await ensure_channel_membership(update, context):
        return
    database = get_database_manager(context)
    try:
        result = await sync_user(database, telegram_user_to_identity(user))
        subscription = await load_user_subscription(database, result.profile.id)
    except (
        InvalidUserIdentityError,
        UserRepositoryError,
        SubscriptionError,
    ):
        logger.exception(
            "Public subscription status failed",
            extra={"event": "subscription_user_status_failed"},
        )
        await message.reply_text(
            "دریافت وضعیت اشتراک ممکن نیست. کمی بعد دوباره تلاش کنید."
        )
        return
    await message.reply_text(
        render_subscription_status(
            subscription,
            now=datetime.now(UTC),
            timezone_name=get_report_timezone(context),
        ),
        reply_markup=build_user_menu(is_admin=user.id in get_admin_ids(context)),
    )


def register_subscription_user_handlers(application: Application) -> None:
    """Register the command and exact private-chat menu entry."""
    private = filters.ChatType.PRIVATE
    application.add_handler(
        CommandHandler("subscription", subscription_status_handler, filters=private)
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUBSCRIPTION_STATUS_BUTTON)}$"),
            subscription_status_handler,
        )
    )
