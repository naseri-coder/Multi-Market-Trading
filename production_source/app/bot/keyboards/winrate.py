"""Public win-rate period selection and report navigation."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.modules.analytics.entities import WinRatePeriod

WIN_RATE_BUTTON = "📊 نرخ برد ( وین ریت )"
WIN_RATE_CALLBACK_PATTERN = (
    r"^v1:winrate:user:(?:"
    r"menu|periods|report:(?:daily|weekly|monthly|yearly)"
    r")$"
)

_PERIOD_BUTTONS = (
    (WinRatePeriod.DAILY, "📅 روزانه"),
    (WinRatePeriod.WEEKLY, "🗓 هفتگی"),
    (WinRatePeriod.MONTHLY, "📆 ماهانه"),
    (WinRatePeriod.YEARLY, "🧭 سالانه"),
)


def build_win_rate_period_menu() -> InlineKeyboardMarkup:
    """Return four allow-listed reports plus a stable main-menu action."""
    period_buttons = [
        InlineKeyboardButton(
            label,
            callback_data=f"v1:winrate:user:report:{period.value}",
        )
        for period, label in _PERIOD_BUTTONS
    ]
    return InlineKeyboardMarkup(
        [
            period_buttons[:2],
            period_buttons[2:],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت به منوی اصلی",
                    callback_data="v1:winrate:user:menu",
                )
            ],
        ]
    )


def build_win_rate_report_actions() -> InlineKeyboardMarkup:
    """Return report navigation without embedding untrusted state."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔙 انتخاب بازه دیگر",
                    callback_data="v1:winrate:user:periods",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 منوی اصلی",
                    callback_data="v1:winrate:user:menu",
                )
            ],
        ]
    )
