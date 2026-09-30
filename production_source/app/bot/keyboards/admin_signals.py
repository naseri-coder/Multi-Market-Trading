"""Reply and inline keyboards for advanced administrator signal management."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

SIGNAL_MANAGEMENT_BUTTON = "📡 مدیریت سیگنال‌ها"
SIGNAL_CREATE_BUTTON = "➕ ایجاد Signal"
SIGNAL_ACTIVE_BUTTON = "📋 Signalهای فعال"
SIGNAL_HISTORY_BUTTON = "📜 تاریخچه Signalها"
SIGNAL_EDIT_BUTTON = "✏️ ویرایش Signal"
SIGNAL_CLOSE_BUTTON = "❌ بستن Signal"
SIGNAL_CANCEL_BUTTON = "🚫 لغو Signal"
SIGNAL_TARGETS_BUTTON = "🎯 مدیریت Targetها"
SIGNAL_PUBLISH_BUTTON = "📢 انتشار Signal"
SIGNAL_ADMIN_BACK_BUTTON = "🔙 بازگشت به پنل مدیریت"
SIGNAL_ADMIN_CANCEL_INPUT_BUTTON = "🔙 لغو عملیات Signal"

ADMIN_SIGNAL_CALLBACK_PATTERN = (
    r"^v1:signals:admin:(?:"
    r"(?:panel|menu)|"
    r"create:(?:confirm|cancel)|"
    r"list:(?:active|history|drafts):[1-9]\d*|"
    r"view:(?:active|history|drafts):[1-9]\d*:[1-9]\d*:[1-9]\d*|"
    r"edit:(?:menu|symbol|direction|entry|stop|leverage|description):[1-9]\d*|"
    r"target:menu:[1-9]\d*:[1-9]\d*|"
    r"target:(?:add|stop):[1-9]\d*|"
    r"hit:[1-9]\d*:[1-9]\d*|"
    r"close:[1-9]\d*:(?:start|confirm)|"
    r"cancel:[1-9]\d*:(?:ask|confirm)|"
    r"publish:[1-9]\d*:(?:ask|confirm)"
    r")$"
)


def build_signal_management_menu() -> ReplyKeyboardMarkup:
    """Build the complete Phase 20 administrator signal menu."""
    return ReplyKeyboardMarkup(
        [
            [SIGNAL_CREATE_BUTTON],
            [SIGNAL_ACTIVE_BUTTON, SIGNAL_HISTORY_BUTTON],
            [SIGNAL_EDIT_BUTTON, SIGNAL_CLOSE_BUTTON],
            [SIGNAL_CANCEL_BUTTON, SIGNAL_TARGETS_BUTTON],
            [SIGNAL_PUBLISH_BUTTON],
            [SIGNAL_ADMIN_BACK_BUTTON],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="مدیریت سیگنال‌ها",
    )


def build_signal_input_cancel() -> ReplyKeyboardMarkup:
    """Limit free-form input mode to an explicit cancellation path."""
    return ReplyKeyboardMarkup(
        [[SIGNAL_ADMIN_CANCEL_INPUT_BUTTON]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="اطلاعات Signal را ارسال کنید",
    )


def build_admin_signal_list(
    signals: list[tuple[int, str]],
    *,
    mode: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build one bounded signal page with exact navigation callbacks."""
    rows = [
        [
            InlineKeyboardButton(
                label,
                callback_data=f"v1:signals:admin:view:{mode}:{page}:{signal_id}:1",
            )
        ]
        for signal_id, label in signals
    ]
    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                "◀️ قبلی",
                callback_data=f"v1:signals:admin:list:{mode}:{page - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data=f"v1:signals:admin:list:{mode}:{page}",
        )
    )
    if page < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "بعدی ▶️",
                callback_data=f"v1:signals:admin:list:{mode}:{page + 1}",
            )
        )
    rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به مدیریت Signal",
                callback_data="v1:signals:admin:menu",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_admin_signal_detail(
    signal_id: int,
    *,
    status: str,
    list_mode: str,
    list_page: int,
    target_page: int,
    total_target_pages: int,
) -> InlineKeyboardMarkup:
    """Build lifecycle actions allowed by the current signal state."""
    rows: list[list[InlineKeyboardButton]] = []
    if status == "DRAFT":
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        "✏️ ویرایش",
                        callback_data=f"v1:signals:admin:edit:menu:{signal_id}",
                    ),
                    InlineKeyboardButton(
                        "🎯 Targetها",
                        callback_data=(
                            f"v1:signals:admin:target:menu:{signal_id}:"
                            f"{target_page}"
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "📢 انتشار",
                        callback_data=f"v1:signals:admin:publish:{signal_id}:ask",
                    ),
                    InlineKeyboardButton(
                        "🚫 لغو",
                        callback_data=f"v1:signals:admin:cancel:{signal_id}:ask",
                    ),
                ],
            ]
        )
    elif status == "OPEN":
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        "✏️ ویرایش",
                        callback_data=f"v1:signals:admin:edit:menu:{signal_id}",
                    ),
                    InlineKeyboardButton(
                        "🎯 Targetها",
                        callback_data=(
                            f"v1:signals:admin:target:menu:{signal_id}:"
                            f"{target_page}"
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "❌ بستن",
                        callback_data=f"v1:signals:admin:close:{signal_id}:start",
                    ),
                    InlineKeyboardButton(
                        "🚫 لغو",
                        callback_data=f"v1:signals:admin:cancel:{signal_id}:ask",
                    ),
                ],
            ]
        )
    if total_target_pages > 1:
        target_navigation: list[InlineKeyboardButton] = []
        if target_page > 1:
            target_navigation.append(
                InlineKeyboardButton(
                    "◀️ اهداف قبلی",
                    callback_data=(
                        f"v1:signals:admin:view:{list_mode}:{list_page}:"
                        f"{signal_id}:{target_page - 1}"
                    ),
                )
            )
        target_navigation.append(
            InlineKeyboardButton(
                f"اهداف {target_page}/{total_target_pages}",
                callback_data=(
                    f"v1:signals:admin:view:{list_mode}:{list_page}:"
                    f"{signal_id}:{target_page}"
                ),
            )
        )
        if target_page < total_target_pages:
            target_navigation.append(
                InlineKeyboardButton(
                    "اهداف بعدی ▶️",
                    callback_data=(
                        f"v1:signals:admin:view:{list_mode}:{list_page}:"
                        f"{signal_id}:{target_page + 1}"
                    ),
                )
            )
        rows.append(target_navigation)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    "🔙 بازگشت به فهرست",
                    callback_data=(
                        f"v1:signals:admin:list:{list_mode}:{list_page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 مدیریت Signal",
                    callback_data="v1:signals:admin:menu",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_signal_edit_fields(
    signal_id: int,
    *,
    status: str,
) -> InlineKeyboardMarkup:
    """Expose only fields permitted by the SignalService state rules."""
    rows = [
        [
            InlineKeyboardButton(
                "💱 نماد",
                callback_data=f"v1:signals:admin:edit:symbol:{signal_id}",
            ),
            InlineKeyboardButton(
                "📝 توضیحات",
                callback_data=f"v1:signals:admin:edit:description:{signal_id}",
            ),
        ]
    ]
    if status == "DRAFT":
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        "📈 جهت",
                        callback_data=f"v1:signals:admin:edit:direction:{signal_id}",
                    ),
                    InlineKeyboardButton(
                        "🎯 ورود",
                        callback_data=f"v1:signals:admin:edit:entry:{signal_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🛑 حد ضرر",
                        callback_data=f"v1:signals:admin:edit:stop:{signal_id}",
                    ),
                    InlineKeyboardButton(
                        "⚡ اهرم",
                        callback_data=f"v1:signals:admin:edit:leverage:{signal_id}",
                    ),
                ],
            ]
        )
    elif status == "OPEN":
        rows.append(
            [
                InlineKeyboardButton(
                    "🛑 به‌روزرسانی حد ضرر",
                    callback_data=f"v1:signals:admin:edit:stop:{signal_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به Signal",
                callback_data=(
                    f"v1:signals:admin:view:{_mode_for_status(status)}:1:"
                    f"{signal_id}:1"
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_target_management(
    signal_id: int,
    pending_targets: list[tuple[int, int]],
    *,
    status: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build add, hit, stop-loss and target-page actions."""
    rows: list[list[InlineKeyboardButton]] = []
    if status in {"DRAFT", "OPEN"}:
        rows.append(
            [
                InlineKeyboardButton(
                    "➕ افزودن Target",
                    callback_data=f"v1:signals:admin:target:add:{signal_id}",
                )
            ]
        )
    if status == "OPEN":
        rows.append(
            [
                InlineKeyboardButton(
                    "🛑 تغییر حد ضرر",
                    callback_data=f"v1:signals:admin:target:stop:{signal_id}",
                )
            ]
        )
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        f"✅ ثبت برخورد Target {number}",
                        callback_data=(
                            f"v1:signals:admin:hit:{signal_id}:{target_id}"
                        ),
                    )
                ]
                for target_id, number in pending_targets
            ]
        )
    if total_pages > 1:
        navigation: list[InlineKeyboardButton] = []
        if page > 1:
            navigation.append(
                InlineKeyboardButton(
                    "◀️ قبلی",
                    callback_data=(
                        f"v1:signals:admin:target:menu:{signal_id}:{page - 1}"
                    ),
                )
            )
        navigation.append(
            InlineKeyboardButton(
                f"{page}/{total_pages}",
                callback_data=f"v1:signals:admin:target:menu:{signal_id}:{page}",
            )
        )
        if page < total_pages:
            navigation.append(
                InlineKeyboardButton(
                    "بعدی ▶️",
                    callback_data=(
                        f"v1:signals:admin:target:menu:{signal_id}:{page + 1}"
                    ),
                )
            )
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت به Signal",
                callback_data=(
                    f"v1:signals:admin:view:{_mode_for_status(status)}:1:"
                    f"{signal_id}:{page}"
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_signal_confirmation(
    *,
    action: str,
    signal_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Build explicit confirmation for create, close, cancel, or publish."""
    if action == "create":
        confirm_data = "v1:signals:admin:create:confirm"
        cancel_data = "v1:signals:admin:create:cancel"
    elif action in {"close", "cancel", "publish"} and signal_id is not None:
        confirm_data = f"v1:signals:admin:{action}:{signal_id}:confirm"
        cancel_data = "v1:signals:admin:menu"
    else:
        raise ValueError("Unsupported signal confirmation")
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ تأیید", callback_data=confirm_data),
                InlineKeyboardButton("🚫 انصراف", callback_data=cancel_data),
            ]
        ]
    )


def _mode_for_status(status: str) -> str:
    if status == "DRAFT":
        return "drafts"
    if status == "OPEN":
        return "active"
    return "history"
