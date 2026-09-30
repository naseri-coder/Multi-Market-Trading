"""Public favorites list, detail, mutation, and pagination keyboards."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

FAVORITES_BUTTON = "⭐ علاقه‌مندی‌ها"
FAVORITES_CALLBACK_PATTERN = (
    r"^v1:favorites:user:(?:"
    r"menu|"
    r"list:[1-9]\d*|"
    r"view:[1-9]\d*:[1-9]\d*:[1-9]\d*|"
    r"toggle:(?:add|remove):(?:live|open|history|favorites):"
    r"[1-9]\d*:[1-9]\d*:[1-9]\d*"
    r")$"
)
_FAVORITE_SOURCES = frozenset(("live", "open", "history", "favorites"))


def build_favorite_toggle_button(
    signal_id: int,
    *,
    is_favorite: bool,
    source: str,
    list_page: int,
    target_page: int,
) -> InlineKeyboardButton:
    """Build one bounded idempotent favorite mutation action."""
    if source not in _FAVORITE_SOURCES:
        raise ValueError("Unsupported favorite source")
    if min(signal_id, list_page, target_page) <= 0:
        raise ValueError("Favorite callback identifiers must be positive")
    action = "remove" if is_favorite else "add"
    label = (
        "⭐ حذف از علاقه‌مندی‌ها"
        if is_favorite
        else "☆ افزودن به علاقه‌مندی‌ها"
    )
    return InlineKeyboardButton(
        label,
        callback_data=(
            f"v1:favorites:user:toggle:{action}:{source}:"
            f"{list_page}:{signal_id}:{target_page}"
        ),
    )


def build_favorites_list(
    signals: list[tuple[int, str]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build a bounded favorite list with database-page navigation."""
    rows = [
        [
            InlineKeyboardButton(
                label,
                callback_data=f"v1:favorites:user:view:{page}:{signal_id}:1",
            )
        ]
        for signal_id, label in signals
    ]
    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                "◀️ قبلی",
                callback_data=f"v1:favorites:user:list:{page - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data=f"v1:favorites:user:list:{page}",
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "بعدی ▶️",
                callback_data=f"v1:favorites:user:list:{page + 1}",
            )
        )
    rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به منوی اصلی",
                callback_data="v1:favorites:user:menu",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_favorite_detail_actions(
    signal_id: int,
    *,
    list_page: int,
    target_page: int,
    total_target_pages: int,
    is_favorite: bool,
) -> InlineKeyboardMarkup:
    """Build favorite mutation, target pagination, and list navigation."""
    rows = [
        [
            build_favorite_toggle_button(
                signal_id,
                is_favorite=is_favorite,
                source="favorites",
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
                        f"v1:favorites:user:view:{list_page}:"
                        f"{signal_id}:{target_page - 1}"
                    ),
                )
            )
        navigation.append(
            InlineKeyboardButton(
                f"اهداف {target_page}/{total_target_pages}",
                callback_data=(
                    f"v1:favorites:user:view:{list_page}:"
                    f"{signal_id}:{target_page}"
                ),
            )
        )
        if target_page < total_target_pages:
            navigation.append(
                InlineKeyboardButton(
                    "اهداف بعدی ▶️",
                    callback_data=(
                        f"v1:favorites:user:view:{list_page}:"
                        f"{signal_id}:{target_page + 1}"
                    ),
                )
            )
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به علاقه‌مندی‌ها",
                callback_data=f"v1:favorites:user:list:{list_page}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
