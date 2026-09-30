"""Public Telegram adapter for per-user notification settings."""

from __future__ import annotations

import logging
import re

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

from app.bot.dependencies import get_admin_ids, get_database_manager
from app.bot.handlers.admin_state import clear_admin_input_state
from app.bot.handlers.channel_lock import ensure_channel_membership
from app.bot.handlers.support_state import clear_support_user_state
from app.bot.handlers.users import sync_user, telegram_user_to_identity
from app.bot.keyboards.notifications import (
    NOTIFICATION_LABELS,
    NOTIFICATION_SETTINGS_BUTTON,
    NOTIFICATION_SETTINGS_CALLBACK_PATTERN,
    build_notification_settings_keyboard,
)
from app.bot.keyboards.user import build_user_menu
from app.db.session import DatabaseManager
from app.modules.notifications.entities import NotificationPreference
from app.modules.notifications.errors import NotificationSettingsError
from app.modules.notifications.repository import (
    SQLAlchemyNotificationSettingsRepository,
)
from app.modules.notifications.service import NotificationSettingsService
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError

logger = logging.getLogger(__name__)


async def load_notification_preferences(
    database: DatabaseManager,
    user_id: int,
) -> tuple[NotificationPreference, ...]:
    async with database.session() as session, session.begin():
        service = NotificationSettingsService(
            SQLAlchemyNotificationSettingsRepository(session)
        )
        return await service.get_preferences(user_id)


async def set_notification_preference(
    database: DatabaseManager,
    user_id: int,
    notification_type: str,
    *,
    is_enabled: bool,
) -> tuple[NotificationPreference, ...]:
    async with database.session() as session, session.begin():
        service = NotificationSettingsService(
            SQLAlchemyNotificationSettingsRepository(session)
        )
        await service.set_enabled(
            user_id,
            notification_type,
            is_enabled=is_enabled,
        )
        return await service.get_preferences(user_id)


def render_notification_preferences(
    preferences: tuple[NotificationPreference, ...],
) -> tuple[str, InlineKeyboardMarkup]:
    """Render all six settings with a clear Persian state explanation."""
    lines = [
        "🔔 تنظیمات اعلان‌ها",
        "",
        "اعلان‌های موردنظر خود را فعال یا غیرفعال کنید.",
        "✅ فعال است | ⛔ غیرفعال است",
        "",
    ]
    for preference in preferences:
        state = "✅ فعال" if preference.is_enabled else "⛔ غیرفعال"
        lines.append(
            f"{NOTIFICATION_LABELS[preference.notification_type]}: {state}"
        )
    lines.extend(
        (
            "",
            "ℹ️ ارسال عملی این اعلان‌ها پس از فعال‌شدن "
            "سامانه اعلان انجام می‌شود.",
        )
    )
    return "\n".join(lines), build_notification_settings_keyboard(preferences)


async def notification_settings_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open all notification preferences for the current user."""
    clear_support_user_state(context)
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None:
        return
    user_id = await _prepare_notification_settings_access(update, context)
    if user_id is None:
        return
    try:
        preferences = await load_notification_preferences(
            get_database_manager(context),
            user_id,
        )
    except NotificationSettingsError:
        logger.exception(
            "Public notification settings load failed",
            extra={"event": "notification_settings_user_load_failed"},
        )
        await message.reply_text(
            "دریافت تنظیمات اعلان‌ها ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return
    text, reply_markup = render_notification_preferences(preferences)
    await message.reply_text(text, reply_markup=reply_markup)


async def notification_settings_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle exact, versioned notification preference callbacks."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer("در حال ذخیره...")
    user_id = await _prepare_notification_settings_access(update, context)
    if user_id is None:
        return

    try:
        parts = query.data.split(":")
        action = parts[3]
        if action == "menu":
            await _safe_edit_notification_message(
                query,
                "به منوی اصلی بازگشتید.",
            )
            message = query.message
            if message is not None and hasattr(message, "reply_text"):
                await message.reply_text(
                    "یک گزینه را انتخاب کنید.",
                    reply_markup=build_user_menu(
                        is_admin=user.id in get_admin_ids(context)
                    ),
                )
            return

        is_enabled = parts[4] == "enable"
        notification_type = parts[5]
        preferences = await set_notification_preference(
            get_database_manager(context),
            user_id,
            notification_type,
            is_enabled=is_enabled,
        )
        text, reply_markup = render_notification_preferences(preferences)
        await _safe_edit_notification_message(
            query,
            text,
            reply_markup=reply_markup,
        )
    except (IndexError, NotificationSettingsError, ValueError):
        logger.exception(
            "Public notification settings callback failed",
            extra={"event": "notification_settings_user_callback_failed"},
        )
        await _safe_edit_notification_message(
            query,
            "تنظیم اعلان نامعتبر است یا ذخیره آن ممکن نیست.",
        )


async def _prepare_notification_settings_access(
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
            "Notification settings user synchronization failed",
            extra={
                "event": "notification_settings_user_sync_failed",
                "telegram_user_id": user.id,
            },
        )
        await message.reply_text(
            "دسترسی به تنظیمات اعلان‌ها فعلاً ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return None
    return result.profile.id


async def _safe_edit_notification_message(
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


def register_notification_settings_user_handlers(
    application: Application,
) -> None:
    """Register one menu entry and one exact callback namespace."""
    private = filters.ChatType.PRIVATE
    application.add_handler(
        CommandHandler(
            "notifications",
            notification_settings_menu_handler,
            filters=private,
        )
    )
    application.add_handler(
        MessageHandler(
            private
            & filters.Regex(
                rf"^{re.escape(NOTIFICATION_SETTINGS_BUTTON)}$"
            ),
            notification_settings_menu_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            notification_settings_callback_handler,
            pattern=NOTIFICATION_SETTINGS_CALLBACK_PATTERN,
        )
    )
