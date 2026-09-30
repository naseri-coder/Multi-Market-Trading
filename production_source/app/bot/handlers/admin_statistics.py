"""Administrator presentation adapter for user statistics."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.dependencies import get_database_manager, get_report_timezone
from app.bot.keyboards.admin import build_admin_menu
from app.db.session import DatabaseManager
from app.modules.users.entities import UserStatistics
from app.modules.users.errors import UserStatisticsRepositoryError
from app.modules.users.statistics_repository import SQLAlchemyUserStatisticsRepository
from app.modules.users.statistics_service import UserStatisticsService

logger = logging.getLogger(__name__)


async def load_user_statistics(
    database: DatabaseManager,
    *,
    timezone_name: str,
) -> UserStatistics:
    """Run one read-only statistics query through the application service."""
    async with database.session() as session:
        repository = SQLAlchemyUserStatisticsRepository(session)
        service = UserStatisticsService(repository, timezone_name=timezone_name)
        return await service.get_dashboard_statistics()


def render_user_statistics(statistics: UserStatistics) -> str:
    """Render a plain-text administrator dashboard."""
    return "\n".join(
        (
            "📊 داشبورد کاربران",
            "",
            f"👥 کل کاربران: {statistics.total_users}",
            f"🟢 کاربران فعال ({statistics.active_window_days} روز اخیر): "
            f"{statistics.active_users}",
            f"⚪️ کاربران غیرفعال: {statistics.inactive_users}",
            "",
            "🆕 کاربران جدید",
            f"امروز: {statistics.new_users_today}",
            f"این هفته: {statistics.new_users_this_week}",
            f"این ماه: {statistics.new_users_this_month}",
            "",
            f"🕒 منطقه زمانی گزارش: {statistics.report_timezone}",
        )
    )


async def admin_dashboard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Load and display the user statistics dashboard."""
    message = update.effective_message
    if message is None:
        return

    try:
        statistics = await load_user_statistics(
            get_database_manager(context),
            timezone_name=get_report_timezone(context),
        )
    except UserStatisticsRepositoryError:
        logger.exception(
            "User statistics dashboard failed",
            extra={"event": "user_statistics_failed", "update_id": update.update_id},
        )
        await message.reply_text(
            "در حال حاضر دریافت آمار کاربران ممکن نیست. لطفاً کمی بعد دوباره تلاش کنید.",
            reply_markup=build_admin_menu(),
        )
        return

    await message.reply_text(
        render_user_statistics(statistics),
        reply_markup=build_admin_menu(),
    )
