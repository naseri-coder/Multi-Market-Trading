"""Referral dashboard and invited-user pagination keyboards."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

REFERRALS_BUTTON = "🎁 دعوت دوستان"
REFERRALS_CALLBACK_PATTERN = (
    r"^v1:referrals:user:(?:menu|dashboard|list:[1-9]\d*)$"
)


def build_referral_dashboard() -> InlineKeyboardMarkup:
    """Build referral statistics navigation and main-menu return."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👥 کاربران دعوت‌شده",
                    callback_data="v1:referrals:user:list:1",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت به منوی اصلی",
                    callback_data="v1:referrals:user:menu",
                )
            ],
        ]
    )


def build_invited_users_page(
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build bounded pagination plus dashboard and main-menu navigation."""
    if min(page, total_pages) <= 0 or page > total_pages:
        raise ValueError("Invalid referral pagination")
    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                "◀️ قبلی",
                callback_data=f"v1:referrals:user:list:{page - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data=f"v1:referrals:user:list:{page}",
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "بعدی ▶️",
                callback_data=f"v1:referrals:user:list:{page + 1}",
            )
        )
    return InlineKeyboardMarkup(
        [
            navigation,
            [
                InlineKeyboardButton(
                    "🔙 بازگشت به دعوت دوستان",
                    callback_data="v1:referrals:user:dashboard",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 منوی اصلی",
                    callback_data="v1:referrals:user:menu",
                )
            ],
        ]
    )
