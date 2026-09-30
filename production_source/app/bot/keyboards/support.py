"""User and administrator support ticket keyboards."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

SUPPORT_BUTTON = "🆘 پشتیبانی"
SUPPORT_NEW_TICKET_BUTTON = "➕ تیکت جدید"
SUPPORT_MY_TICKETS_BUTTON = "📋 تیکت‌های من"
SUPPORT_BACK_BUTTON = "🔙 بازگشت به منوی اصلی"
SUPPORT_CANCEL_INPUT_BUTTON = "🔙 لغو پیام پشتیبانی"
ADMIN_SUPPORT_BUTTON = "🎫 تیکت‌های پشتیبانی"
ADMIN_SUPPORT_CANCEL_INPUT_BUTTON = "🔙 لغو پاسخ پشتیبانی"

USER_SUPPORT_CALLBACK_PATTERN = (
    r"^v1:support:user:(?:"
    r"(?:view|reply|close|list):[1-9]\d*|"
    r"history:[1-9]\d*:[1-9]\d*)$"
)
ADMIN_SUPPORT_CALLBACK_PATTERN = (
    r"^v1:support:admin:(?:"
    r"(?:view|reply|open|progress|close):[1-9]\d*|"
    r"history:[1-9]\d*:[1-9]\d*|"
    r"list:(?:all|open|closed|answered|waiting):[1-9]\d*|"
    r"panel)$"
)


def build_support_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [SUPPORT_NEW_TICKET_BUTTON],
            [SUPPORT_MY_TICKETS_BUTTON],
            [SUPPORT_BACK_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="پشتیبانی",
    )


def build_support_input_cancel(*, admin: bool = False) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[ADMIN_SUPPORT_CANCEL_INPUT_BUTTON if admin else SUPPORT_CANCEL_INPUT_BUTTON]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="پیام خود را بنویسید",
    )


def build_user_ticket_actions(
    ticket_id: int,
    *,
    closed: bool,
    list_page: int = 1,
    message_page: int = 1,
    total_message_pages: int = 1,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "✉️ پاسخ",
                callback_data=f"v1:support:user:reply:{ticket_id}",
            )
        ]
    ]
    if not closed:
        rows.append(
            [
                InlineKeyboardButton(
                    "✅ بستن تیکت",
                    callback_data=f"v1:support:user:close:{ticket_id}",
                ),
            ]
        )
    add_user_history_navigation(
        rows,
        ticket_id=ticket_id,
        page=message_page,
        total_pages=total_message_pages,
    )
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به فهرست",
                callback_data=f"v1:support:user:list:{list_page}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def add_user_history_navigation(
    rows: list[list[InlineKeyboardButton]],
    *,
    ticket_id: int,
    page: int,
    total_pages: int,
) -> None:
    if total_pages <= 1:
        return
    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                "◀️ جدیدتر",
                callback_data=f"v1:support:user:history:{ticket_id}:{page - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            f"پیام‌ها {page}/{total_pages}",
            callback_data=f"v1:support:user:history:{ticket_id}:{page}",
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "قدیمی‌تر ▶️",
                callback_data=f"v1:support:user:history:{ticket_id}:{page + 1}",
            )
        )
    rows.insert(0, navigation)


def build_user_ticket_list(
    tickets: list[tuple[int, str]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build one compact user ticket list with safe view-only callbacks."""
    rows = [
        [
            InlineKeyboardButton(
                label,
                callback_data=f"v1:support:user:view:{ticket_id}",
            )
        ]
        for ticket_id, label in tickets
    ]
    if total_pages > 1:
        navigation: list[InlineKeyboardButton] = []
        if page > 1:
            navigation.append(
                InlineKeyboardButton(
                    "◀️ قبلی",
                    callback_data=f"v1:support:user:list:{page - 1}",
                )
            )
        navigation.append(
            InlineKeyboardButton(
                f"{page}/{total_pages}",
                callback_data=f"v1:support:user:list:{page}",
            )
        )
        if page < total_pages:
            navigation.append(
                InlineKeyboardButton(
                    "بعدی ▶️",
                    callback_data=f"v1:support:user:list:{page + 1}",
                )
            )
        rows.append(navigation)
    return InlineKeyboardMarkup(rows)


def build_admin_ticket_actions(
    ticket_id: int,
    *,
    status: str,
    list_filter: str = "all",
    page: int = 1,
    message_page: int = 1,
    total_message_pages: int = 1,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status != "CLOSED":
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        "✉️ پاسخ",
                        callback_data=f"v1:support:admin:reply:{ticket_id}",
                    ),
                    InlineKeyboardButton(
                        "🛠 در حال بررسی",
                        callback_data=f"v1:support:admin:progress:{ticket_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "✅ بستن",
                        callback_data=f"v1:support:admin:close:{ticket_id}",
                    )
                ],
            ]
        )
    else:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        "✉️ پاسخ",
                        callback_data=f"v1:support:admin:reply:{ticket_id}",
                    ),
                    InlineKeyboardButton(
                        "🔓 بازگشایی",
                        callback_data=f"v1:support:admin:open:{ticket_id}",
                    ),
                ]
            ]
        )
    if total_message_pages > 1:
        navigation: list[InlineKeyboardButton] = []
        if message_page > 1:
            navigation.append(
                InlineKeyboardButton(
                    "◀️ جدیدتر",
                    callback_data=(
                        f"v1:support:admin:history:{ticket_id}:{message_page - 1}"
                    ),
                )
            )
        navigation.append(
            InlineKeyboardButton(
                f"پیام‌ها {message_page}/{total_message_pages}",
                callback_data=f"v1:support:admin:history:{ticket_id}:{message_page}",
            )
        )
        if message_page < total_message_pages:
            navigation.append(
                InlineKeyboardButton(
                    "قدیمی‌تر ▶️",
                    callback_data=(
                        f"v1:support:admin:history:{ticket_id}:{message_page + 1}"
                    ),
                )
            )
        rows.insert(0, navigation)
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به فهرست",
                callback_data=f"v1:support:admin:list:{list_filter}:{page}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_admin_ticket_list(
    tickets: list[tuple[int, str]],
    *,
    filter_by: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build filters, a compact page, navigation, and panel return."""
    rows = [
        [
            InlineKeyboardButton("همه", callback_data="v1:support:admin:list:all:1"),
            InlineKeyboardButton("باز", callback_data="v1:support:admin:list:open:1"),
            InlineKeyboardButton("بسته", callback_data="v1:support:admin:list:closed:1"),
        ],
        [
            InlineKeyboardButton(
                "پاسخ داده‌شده",
                callback_data="v1:support:admin:list:answered:1",
            ),
            InlineKeyboardButton(
                "در انتظار پاسخ",
                callback_data="v1:support:admin:list:waiting:1",
            ),
        ],
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"v1:support:admin:view:{ticket_id}",
                )
            ]
            for ticket_id, label in tickets
        ]
    )
    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                "◀️ قبلی",
                callback_data=f"v1:support:admin:list:{filter_by}:{page - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data=f"v1:support:admin:list:{filter_by}:{page}",
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "بعدی ▶️",
                callback_data=f"v1:support:admin:list:{filter_by}:{page + 1}",
            )
        )
    rows.append(navigation)
    rows.append(
        [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="v1:support:admin:panel")]
    )
    return InlineKeyboardMarkup(rows)


def build_admin_notification_actions(ticket_id: int) -> InlineKeyboardMarkup:
    """Offer direct viewing and replying from an administrator alert."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✉️ پاسخ سریع",
                    callback_data=f"v1:support:admin:reply:{ticket_id}",
                ),
                InlineKeyboardButton(
                    "👁 مشاهده تیکت",
                    callback_data=f"v1:support:admin:view:{ticket_id}",
                ),
            ]
        ]
    )


def build_user_notification_actions(ticket_id: int) -> InlineKeyboardMarkup:
    """Offer direct viewing and replying from a user notification."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✉️ پاسخ",
                    callback_data=f"v1:support:user:reply:{ticket_id}",
                ),
                InlineKeyboardButton(
                    "👁 مشاهده تیکت",
                    callback_data=f"v1:support:user:view:{ticket_id}",
                ),
            ]
        ]
    )
