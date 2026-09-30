"""Public Telegram adapter for rolling win-rate reports."""

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
from app.bot.keyboards.user import build_user_menu
from app.bot.keyboards.winrate import (
    WIN_RATE_BUTTON,
    WIN_RATE_CALLBACK_PATTERN,
    build_win_rate_period_menu,
    build_win_rate_report_actions,
)
from app.db.session import DatabaseManager
from app.modules.analytics.entities import WinRatePeriod, WinRateReport
from app.modules.analytics.errors import AnalyticsError
from app.modules.analytics.repository import SQLAlchemyWinRateRepository
from app.modules.analytics.service import WinRateService
from app.modules.users.errors import InvalidUserIdentityError, UserRepositoryError

logger = logging.getLogger(__name__)

_PERIOD_LABELS = {
    WinRatePeriod.DAILY.value: "روزانه — ۲۴ ساعت اخیر",
    WinRatePeriod.WEEKLY.value: "هفتگی — ۷ روز اخیر",
    WinRatePeriod.MONTHLY.value: "ماهانه — ۳۰ روز اخیر",
    WinRatePeriod.YEARLY.value: "سالانه — ۳۶۵ روز اخیر",
}


async def load_win_rate_report(
    database: DatabaseManager,
    period: str,
) -> WinRateReport:
    """Load one read-only rolling report through the analytics service."""
    async with database.session() as session:
        repository = SQLAlchemyWinRateRepository(session)
        return await WinRateService(repository).get_report(period)


def render_win_rate_period_menu() -> str:
    return "\n".join(
        (
            "📊 گزارش نرخ برد",
            "",
            "بازه زمانی موردنظر را انتخاب کنید:",
            "",
            "📅 روزانه: ۲۴ ساعت اخیر",
            "🗓 هفتگی: ۷ روز اخیر",
            "📆 ماهانه: ۳۰ روز اخیر",
            "🧭 سالانه: ۳۶۵ روز اخیر",
        )
    )


def render_win_rate_report(
    report: WinRateReport,
    *,
    timezone_name: str,
) -> str:
    """Render financial outcome separately from the recorded exit mechanism."""
    lines = [
        "📊 گزارش عملکرد معاملات",
        f"🗓 بازه: {_PERIOD_LABELS[report.period]}",
        "",
        "📌 معاملات",
        "",
        f"🟢 سودده: {report.winning_trades}",
        f"🔴 زیان‌ده: {report.losing_trades}",
        f"⚪ سر‌به‌سر: {report.breakeven_trades}",
        f"⏳ باز: {report.open_trades}",
        "",
        f"🧮 کل معاملات بسته‌شده: {report.closed_trades}",
        f"🏆 نرخ برد: {_format_optional_percentage(report.win_rate)}",
        "",
        "💰 عملکرد مالی (درصد تحقق‌یافته هر معامله)",
        "",
        f"📈 مجموع سود: {_format_signed_percentage(report.gross_profit)}",
        f"📉 مجموع ضرر: {_format_signed_percentage(report.gross_loss)}",
        f"💵 خالص سود/زیان: {_format_signed_percentage(report.net_pnl)}",
        "",
        f"📊 میانگین سود معاملات سودده: {_format_optional_signed(report.average_win)}",
        f"📊 میانگین ضرر معاملات زیان‌ده: {_format_optional_signed(report.average_loss)}",
        "",
        f"⚖️ ضریب سوددهی: {_format_ratio(report.profit_factor)}",
        f"🎯 بازده مورد انتظار هر معامله: {_format_optional_signed(report.expectancy)}",
        "",
        f"🔥 بیشترین برد متوالی: {report.longest_win_streak}",
        f"❄️ بیشترین باخت متوالی: {report.longest_loss_streak}",
        "",
        "🎯 نوع خروج",
        "",
        f"✅ خروج با هدف: {report.target_exits}",
        f"🔒 حد ضرر متحرک سودده: {report.trailing_profit_exits}",
        f"🔻 حد ضرر متحرک زیان‌ده: {report.trailing_loss_exits}",
        f"🟢 حد ضرر سودده: {report.stop_profit_exits}",
        f"🛑 حد ضرر زیان‌ده: {report.stop_loss_exits}",
        (
            "⚪ خروج سر‌به‌سر: "
            f"{report.breakeven_exits + report.trailing_breakeven_exits}"
        ),
    ]
    if report.unknown_trades:
        lines.append(f"⚠️ معاملات با داده ناکافی: {report.unknown_trades}")
    if report.other_exits or report.runner_reversal:
        lines.append(f"ℹ️ سایر خروج‌ها: {report.other_exits}")
        lines.append(f"🏁 خروج با بازگشت روند: {report.runner_reversal}")
    lines.extend([
        "",
        f"🕒 از: {_format_datetime(report.started_at, timezone_name)}",
        f"🕒 تا: {_format_datetime(report.ended_at, timezone_name)}",
        "",
        "ℹ️ مبنای محاسبه:",
        "",
        (
            "نتیجه هر معامله بر اساس سود یا زیان تحقق‌یافته نهایی "
            "آن تعیین می‌شود."
        ),
        (
            "فعال شدن حد ضرر یا حد ضرر متحرک الزاماً به معنی "
            "زیان‌ده بودن معامله نیست."
        ),
        "هر معامله فقط یک‌بار در آمار محاسبه می‌شود.",
        (
            "درصدهای مالی نشان‌دهنده مجموع و میانگین نتایج معاملات هستند و "
            "بازده واقعی کل پرتفوی محسوب نمی‌شوند."
        ),
    ])
    return "\n".join(lines)


async def win_rate_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Open the public rolling-period selector."""
    clear_support_user_state(context)
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None or not await _prepare_win_rate_access(update, context):
        return
    await message.reply_text(
        render_win_rate_period_menu(),
        reply_markup=build_win_rate_period_menu(),
    )


async def win_rate_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle only anchored, versioned win-rate callback actions."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return
    await query.answer("در حال پردازش...")
    if not await _prepare_win_rate_access(update, context):
        return

    parts = query.data.split(":")
    action = parts[3]
    if action == "menu":
        await _safe_edit_win_rate_message(query, "به منوی اصلی بازگشتید.")
        message = query.message
        if message is not None and hasattr(message, "reply_text"):
            await message.reply_text(
                "یک گزینه را انتخاب کنید.",
                reply_markup=build_user_menu(
                    is_admin=user.id in get_admin_ids(context)
                ),
            )
        return
    if action == "periods":
        await _safe_edit_win_rate_message(
            query,
            render_win_rate_period_menu(),
            reply_markup=build_win_rate_period_menu(),
        )
        return

    try:
        period = WinRatePeriod(parts[4]).value
        report = await load_win_rate_report(
            get_database_manager(context),
            period,
        )
    except (AnalyticsError, IndexError, ValueError):
        logger.exception(
            "Public win-rate report failed",
            extra={"event": "win_rate_user_report_failed"},
        )
        await _safe_edit_win_rate_message(
            query,
            (
                "دریافت گزارش نرخ برد ممکن نیست. "
                "کمی بعد تلاش کنید."
            ),
            reply_markup=build_win_rate_period_menu(),
        )
        return

    await _safe_edit_win_rate_message(
        query,
        render_win_rate_report(
            report,
            timezone_name=get_report_timezone(context),
        ),
        reply_markup=build_win_rate_report_actions(),
    )


async def _prepare_win_rate_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return False
    if not await ensure_channel_membership(update, context):
        return False
    try:
        await sync_user(
            get_database_manager(context),
            telegram_user_to_identity(user),
        )
    except (InvalidUserIdentityError, UserRepositoryError):
        logger.exception(
            "Win-rate interface user synchronization failed",
            extra={
                "event": "win_rate_user_sync_failed",
                "telegram_user_id": user.id,
            },
        )
        await message.reply_text(
            "دسترسی به گزارش نرخ برد فعلاً ممکن نیست. "
            "کمی بعد تلاش کنید."
        )
        return False
    return True


async def _safe_edit_win_rate_message(
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


def _format_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), ".2f")


def _format_optional_percentage(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{_format_decimal(value)}%"


def _format_signed_percentage(value: Decimal) -> str:
    prefix = "+" if value > 0 else ""
    return f"{prefix}{_format_decimal(value)}%"


def _format_optional_signed(
    value: Decimal | None,
    *,
    suffix: str = "",
) -> str:
    if value is None:
        return "N/A"
    prefix = "+" if value > 0 else ""
    return f"{prefix}{_format_decimal(value)}%{suffix}"


def _format_ratio(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    if value.is_infinite():
        return "∞"
    return _format_decimal(value)


def _format_datetime(value: datetime, timezone_name: str) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M")


def register_win_rate_user_handlers(application: Application) -> None:
    """Register one entry surface and one exact callback allowlist."""
    private = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("winrate", win_rate_menu_handler, filters=private))
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(WIN_RATE_BUTTON)}$"),
            win_rate_menu_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            win_rate_callback_handler,
            pattern=WIN_RATE_CALLBACK_PATTERN,
        )
    )
