"""User-facing signal list, detail, and pagination keyboards."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.favorites import build_favorite_toggle_button
from app.modules.signals.entities import SignalListMode

LIVE_SIGNALS_BUTTON = "📡 سیگنال‌های لحظه‌ای"
OPEN_SIGNALS_BUTTON = "🟢 سیگنال‌های باز"
SIGNAL_HISTORY_BUTTON = "📜 تاریخچه سیگنال‌ها"

USER_SIGNAL_CALLBACK_PATTERN = (
    r"^v1:signals:user:(?:"
    r"menu|"
    r"list:(?:live|open|history):[1-9]\d*|"
    r"view:(?:live|open|history):[1-9]\d*:[1-9]\d*:[1-9]\d*"
    r")$"
)


def build_signal_list(
    signals: list[tuple[int, str]],
    *,
    mode: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build a bounded list with database-page navigation."""
    safe_mode = SignalListMode(mode).value
    rows = [
        [
            InlineKeyboardButton(
                label,
                callback_data=f"v1:signals:user:view:{safe_mode}:{page}:{signal_id}:1",
            )
        ]
        for signal_id, label in signals
    ]
    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                "◀️ قبلی",
                callback_data=f"v1:signals:user:list:{safe_mode}:{page - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data=f"v1:signals:user:list:{safe_mode}:{page}",
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "بعدی ▶️",
                callback_data=f"v1:signals:user:list:{safe_mode}:{page + 1}",
            )
        )
    rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به منوی اصلی",
                callback_data="v1:signals:user:menu",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_signal_detail_actions(
    signal_id: int,
    *,
    mode: str,
    list_page: int,
    target_page: int,
    total_target_pages: int,
    is_favorite: bool = False,
) -> InlineKeyboardMarkup:
    """Build target-page navigation and a stable return to the source list."""
    safe_mode = SignalListMode(mode).value
    rows: list[list[InlineKeyboardButton]] = [
        [
            build_favorite_toggle_button(
                signal_id,
                is_favorite=is_favorite,
                source=safe_mode,
                list_page=list_page,
                target_page=target_page,
            )
        ]
    ]
    if total_target_pages > 1:
        navigation: list[InlineKeyboardButton] = []
        if target_page > 1:
            navigation.append(
                InlineKeyboardButton(
                    "◀️ اهداف قبلی",
                    callback_data=(
                        f"v1:signals:user:view:{safe_mode}:{list_page}:"
                        f"{signal_id}:{target_page - 1}"
                    ),
                )
            )
        navigation.append(
            InlineKeyboardButton(
                f"اهداف {target_page}/{total_target_pages}",
                callback_data=(
                    f"v1:signals:user:view:{safe_mode}:{list_page}:"
                    f"{signal_id}:{target_page}"
                ),
            )
        )
        if target_page < total_target_pages:
            navigation.append(
                InlineKeyboardButton(
                    "اهداف بعدی ▶️",
                    callback_data=(
                        f"v1:signals:user:view:{safe_mode}:{list_page}:"
                        f"{signal_id}:{target_page + 1}"
                    ),
                )
            )
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به فهرست",
                callback_data=f"v1:signals:user:list:{safe_mode}:{list_page}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
