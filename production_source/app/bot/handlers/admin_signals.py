"""Advanced administrator signal lifecycle and target workflows."""

from __future__ import annotations

import logging
import re
from collections.abc import Collection
from decimal import Decimal, InvalidOperation

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

from app.bot.dependencies import get_database_manager, get_report_timezone
from app.bot.handlers.admin_state import (
    SIGNAL_ADMIN_ACTION_KEY,
    SIGNAL_ADMIN_LIST_KEY,
    clear_admin_input_state,
)
from app.bot.handlers.signals_user import render_signal_detail
from app.bot.handlers.support_state import clear_support_user_state
from app.bot.keyboards.admin import build_admin_menu
from app.bot.keyboards.admin_signals import (
    ADMIN_SIGNAL_CALLBACK_PATTERN,
    SIGNAL_ACTIVE_BUTTON,
    SIGNAL_ADMIN_BACK_BUTTON,
    SIGNAL_ADMIN_CANCEL_INPUT_BUTTON,
    SIGNAL_CANCEL_BUTTON,
    SIGNAL_CLOSE_BUTTON,
    SIGNAL_CREATE_BUTTON,
    SIGNAL_EDIT_BUTTON,
    SIGNAL_HISTORY_BUTTON,
    SIGNAL_MANAGEMENT_BUTTON,
    SIGNAL_PUBLISH_BUTTON,
    SIGNAL_TARGETS_BUTTON,
    build_admin_signal_detail,
    build_admin_signal_list,
    build_signal_confirmation,
    build_signal_edit_fields,
    build_signal_input_cancel,
    build_signal_management_menu,
    build_target_management,
)
from app.bot.middlewares.admin import admin_required
from app.db.session import DatabaseManager
from app.modules.signals.admin_query_service import AdminSignalQueryService
from app.modules.signals.entities import (
    AdminSignalDetail,
    AdminSignalListMode,
    AdminSignalPage,
    CreateSignal,
    SignalRecord,
    SignalTargetRecord,
    UpdateSignal,
)
from app.modules.signals.errors import (
    InvalidSignalError,
    SignalError,
    SignalNotFoundError,
    SignalStateError,
    SignalTargetNotFoundError,
)
from app.modules.signals.models import SignalStatus, SignalTargetStatus
from app.modules.signals.repository import SQLAlchemySignalRepository
from app.modules.signals.service import SignalService

logger = logging.getLogger(__name__)

_ACTION_CREATE = "create"
_ACTION_SELECT_EDIT = "select_edit"
_ACTION_SELECT_CLOSE = "select_close"
_ACTION_SELECT_CANCEL = "select_cancel"
_ACTION_SELECT_TARGETS = "select_targets"
_ACTION_EDIT = "edit"
_ACTION_CLOSE = "close"
_ACTION_ADD_TARGET = "add_target"
_ACTION_HIT_TARGET = "hit_target"
_ACTION_UPDATE_STOP = "update_stop"

_STATUS_LABELS = {
    SignalStatus.DRAFT.value: "پیش‌نویس",
    SignalStatus.OPEN.value: "باز",
    SignalStatus.CLOSED.value: "بسته",
    SignalStatus.CANCELLED.value: "لغوشده",
}
_STATUS_EMOJIS = {
    SignalStatus.DRAFT.value: "📝",
    SignalStatus.OPEN.value: "🟢",
    SignalStatus.CLOSED.value: "✅",
    SignalStatus.CANCELLED.value: "🚫",
}
_MODE_TITLES = {
    AdminSignalListMode.ACTIVE.value: "📋 Signalهای فعال",
    AdminSignalListMode.HISTORY.value: "📜 تاریخچه Signalها",
    AdminSignalListMode.DRAFTS.value: "📢 پیش‌نویس‌های آماده انتشار",
}


def has_pending_signal_admin_action(
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Return whether the next admin text belongs to the signal workflow."""
    state = context.user_data.get(SIGNAL_ADMIN_ACTION_KEY)
    return (
        isinstance(state, dict)
        and state.get("action")
        in {
            _ACTION_CREATE,
            _ACTION_SELECT_EDIT,
            _ACTION_SELECT_CLOSE,
            _ACTION_SELECT_CANCEL,
            _ACTION_SELECT_TARGETS,
            _ACTION_EDIT,
            _ACTION_CLOSE,
            _ACTION_ADD_TARGET,
            _ACTION_HIT_TARGET,
            _ACTION_UPDATE_STOP,
        }
        and isinstance(state.get("step"), str)
        and isinstance(state.get("data"), dict)
    )


def _set_state(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
    step: str,
    data: dict[str, object] | None = None,
) -> None:
    clear_admin_input_state(context)
    context.user_data[SIGNAL_ADMIN_ACTION_KEY] = {
        "action": action,
        "step": step,
        "data": data or {},
    }


def _state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    state = context.user_data.get(SIGNAL_ADMIN_ACTION_KEY)
    if not isinstance(state, dict):
        raise InvalidSignalError("Signal administrator state is missing")
    return state


def _store_list_location(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    page: int,
) -> None:
    context.user_data[SIGNAL_ADMIN_LIST_KEY] = {
        "mode": mode,
        "page": page,
    }


def _list_location(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    status: str | None = None,
) -> tuple[str, int]:
    state = context.user_data.get(SIGNAL_ADMIN_LIST_KEY)
    valid_modes = {item.value for item in AdminSignalListMode}
    if isinstance(state, dict):
        mode = state.get("mode")
        page = state.get("page")
        if (
            mode in valid_modes
            and isinstance(page, int)
            and not isinstance(page, bool)
            and page > 0
        ):
            return str(mode), page
    if status == SignalStatus.DRAFT.value:
        return AdminSignalListMode.DRAFTS.value, 1
    if status == SignalStatus.OPEN.value:
        return AdminSignalListMode.ACTIVE.value, 1
    return AdminSignalListMode.HISTORY.value, 1


async def _load_admin_page(
    database: DatabaseManager,
    *,
    mode: str,
    page: int,
) -> AdminSignalPage:
    async with database.session() as session:
        service = AdminSignalQueryService(
            SQLAlchemySignalRepository(session)
        )
        return await service.get_page(mode, page=page)


async def _load_admin_detail(
    database: DatabaseManager,
    signal_id: int,
    *,
    target_page: int = 1,
) -> AdminSignalDetail:
    async with database.session() as session:
        service = AdminSignalQueryService(
            SQLAlchemySignalRepository(session)
        )
        return await service.get_detail(
            signal_id,
            target_page=target_page,
        )


async def _create_signal(
    database: DatabaseManager,
    command: CreateSignal,
) -> SignalRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).create_signal(command)


async def _update_signal(
    database: DatabaseManager,
    signal_id: int,
    command: UpdateSignal,
) -> SignalRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).update_signal(signal_id, command)


async def _publish_signal(
    database: DatabaseManager,
    signal_id: int,
) -> SignalRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).publish_signal(signal_id)


async def _close_signal(
    database: DatabaseManager,
    signal_id: int,
    profit_loss: Decimal,
) -> SignalRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).close_signal(signal_id, profit_loss=profit_loss)


async def _cancel_signal(
    database: DatabaseManager,
    signal_id: int,
) -> SignalRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).cancel_signal(signal_id)


async def _add_target(
    database: DatabaseManager,
    signal_id: int,
    target_price: Decimal,
) -> SignalTargetRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).add_target(signal_id, target_price=target_price)


async def _hit_target(
    database: DatabaseManager,
    signal_id: int,
    target_id: int,
    profit_loss: Decimal,
) -> SignalTargetRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).hit_target(
            signal_id,
            target_id,
            profit_loss=profit_loss,
        )


async def _update_stop_loss(
    database: DatabaseManager,
    signal_id: int,
    stop_loss: Decimal,
) -> SignalRecord:
    async with database.session() as session, session.begin():
        return await SignalService(
            SQLAlchemySignalRepository(session)
        ).update_stop_loss(signal_id, stop_loss=stop_loss)


def render_admin_signal_page(
    page: AdminSignalPage,
) -> tuple[str, InlineKeyboardMarkup]:
    """Render one compact administrator signal page."""
    lines = [
        _MODE_TITLES[page.mode],
        f"🔢 تعداد: {page.total_items} | 📄 صفحه {page.page} از {page.total_pages}",
        "",
    ]
    buttons: list[tuple[int, str]] = []
    if not page.signals:
        lines.append("ℹ️ سیگنالی در این بخش وجود ندارد.")
    for signal in page.signals:
        status = _STATUS_LABELS.get(signal.status, signal.status)
        emoji = _STATUS_EMOJIS.get(signal.status, "📌")
        lines.extend(
            (
                f"{emoji} Signal #{signal.id} — {signal.symbol}",
                f"📈 جهت: {signal.direction} | "
                f"🎯 ورود: {_decimal_text(signal.entry_price)}",
                f"وضعیت: {status}",
                "",
            )
        )
        buttons.append(
            (signal.id, f"{emoji} #{signal.id} — {signal.symbol} — {status}")
        )
    return "\n".join(lines).rstrip(), build_admin_signal_list(
        buttons,
        mode=page.mode,
        page=page.page,
        total_pages=page.total_pages,
    )


def render_create_preview(data: dict[str, object]) -> str:
    """Render a draft preview before any database mutation."""
    description = data.get("description") or "ندارد"
    return "\n".join(
        (
            "📝 پیش‌نمایش Signal جدید",
            "",
            f"💱 نماد: {data['symbol']}",
            f"📈 جهت: {data['direction']}",
            f"🎯 ورود: {data['entry_price']}",
            f"🛑 حد ضرر: {data['stop_loss']}",
            f"⚡ اهرم: {data['leverage']}x",
            f"📝 توضیحات: {description}",
            "",
            "Signal ابتدا به‌صورت پیش‌نویس ذخیره می‌شود و "
            "تا زمان انتشار برای کاربران قابل مشاهده نیست.",
        )
    )


def _target_management_markup(detail: AdminSignalDetail) -> InlineKeyboardMarkup:
    pending = [
        (target.id, target.target_number)
        for target in detail.targets
        if target.status == SignalTargetStatus.PENDING.value
    ]
    return build_target_management(
        detail.signal.id,
        pending,
        status=detail.signal.status,
        page=detail.target_page,
        total_pages=detail.total_target_pages,
    )


def _detail_markup(
    detail: AdminSignalDetail,
    *,
    mode: str,
    page: int,
) -> InlineKeyboardMarkup:
    return build_admin_signal_detail(
        detail.signal.id,
        status=detail.signal.status,
        list_mode=mode,
        list_page=page,
        target_page=detail.target_page,
        total_target_pages=detail.total_target_pages,
    )


def _positive_id(value: str) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise InvalidSignalError("Signal ID must be an integer") from exc
    if parsed <= 0:
        raise InvalidSignalError("Signal ID must be positive")
    return parsed


def _exact_decimal(value: str, *, positive: bool) -> Decimal:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, ValueError) as exc:
        raise InvalidSignalError("Value must be an exact decimal") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise InvalidSignalError("Decimal value is invalid")
    return parsed


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return "—"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _error_text(error: SignalError) -> str:
    if isinstance(error, SignalNotFoundError):
        return "Signal موردنظر پیدا نشد."
    if isinstance(error, SignalTargetNotFoundError):
        return "Target موردنظر پیدا نشد."
    if isinstance(error, SignalStateError):
        return f"این عملیات با وضعیت فعلی Signal مجاز نیست: {error}"
    if isinstance(error, InvalidSignalError):
        return f"اطلاعات Signal نامعتبر است: {error}"
    return "عملیات Signal انجام نشد. کمی بعد تلاش کنید."


async def signal_management_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_admin_input_state(context)
    clear_support_user_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "📡 مدیریت سیگنال‌ها",
            reply_markup=build_signal_management_menu(),
        )


async def signal_management_back_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "به پنل مدیریت بازگشتید.",
            reply_markup=build_admin_menu(),
        )


async def signal_input_cancel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "عملیات Signal لغو شد.",
            reply_markup=build_signal_management_menu(),
        )


async def _show_list_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None:
        return
    try:
        page = await _load_admin_page(
            get_database_manager(context),
            mode=mode,
            page=1,
        )
    except SignalError as error:
        logger.exception(
            "Administrator signal list failed",
            extra={"event": "signal_admin_list_failed", "mode": mode},
        )
        await message.reply_text(_error_text(error))
        return
    _store_list_location(context, mode=page.mode, page=page.page)
    text, markup = render_admin_signal_page(page)
    await message.reply_text(text, reply_markup=markup)


async def active_signals_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _show_list_message(
        update,
        context,
        mode=AdminSignalListMode.ACTIVE.value,
    )


async def signal_history_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _show_list_message(
        update,
        context,
        mode=AdminSignalListMode.HISTORY.value,
    )


async def signal_publish_list_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _show_list_message(
        update,
        context,
        mode=AdminSignalListMode.DRAFTS.value,
    )


async def signal_instruction_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    instructions = {
        SIGNAL_CREATE_BUTTON: (
            _ACTION_CREATE,
            "symbol",
            "نماد را ارسال کنید؛ نمونه: BTC/USDT",
        ),
        SIGNAL_EDIT_BUTTON: (
            _ACTION_SELECT_EDIT,
            "signal_id",
            "ID داخلی Signal موردنظر برای ویرایش را ارسال کنید.",
        ),
        SIGNAL_CLOSE_BUTTON: (
            _ACTION_SELECT_CLOSE,
            "signal_id",
            "ID داخلی Signal باز را برای بستن ارسال کنید.",
        ),
        SIGNAL_CANCEL_BUTTON: (
            _ACTION_SELECT_CANCEL,
            "signal_id",
            "ID داخلی Signal پیش‌نویس یا باز را برای لغو "
            "ارسال کنید.",
        ),
        SIGNAL_TARGETS_BUTTON: (
            _ACTION_SELECT_TARGETS,
            "signal_id",
            "ID داخلی Signal را برای مدیریت Targetها ارسال کنید.",
        ),
    }
    instruction = instructions.get(message.text)
    if instruction is None:
        clear_admin_input_state(context)
        return
    action, step, prompt = instruction
    _set_state(context, action=action, step=step)
    await message.reply_text(
        prompt,
        reply_markup=build_signal_input_cancel(),
    )


async def signal_admin_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Consume one explicitly selected signal-management text input."""
    message = update.effective_message
    if message is None or not message.text:
        return
    state = _state(context)
    data = state.get("data")
    if not isinstance(data, dict):
        clear_admin_input_state(context)
        return
    try:
        action = state["action"]
        if action == _ACTION_CREATE:
            await _consume_create_input(message, state, data, message.text)
        elif action in {
            _ACTION_SELECT_EDIT,
            _ACTION_SELECT_CLOSE,
            _ACTION_SELECT_CANCEL,
            _ACTION_SELECT_TARGETS,
        }:
            await _consume_signal_selection(
                message,
                context,
                action=str(action),
                signal_id=_positive_id(message.text),
            )
        elif action == _ACTION_EDIT:
            await _consume_edit_input(message, context, data)
        elif action == _ACTION_CLOSE:
            await _consume_close_input(message, state, data)
        elif action == _ACTION_ADD_TARGET:
            await _consume_add_target_input(message, context, data)
        elif action == _ACTION_HIT_TARGET:
            await _consume_hit_target_input(message, context, data)
        elif action == _ACTION_UPDATE_STOP:
            await _consume_stop_input(message, context, data)
        else:
            clear_admin_input_state(context)
    except SignalError as error:
        logger.warning(
            "Administrator signal input rejected",
            extra={
                "event": "signal_admin_input_rejected",
                "error_type": type(error).__name__,
            },
        )
        await message.reply_text(
            _error_text(error),
            reply_markup=build_signal_input_cancel(),
        )
    except (KeyError, TypeError, ValueError):
        logger.warning(
            "Administrator signal input state was invalid",
            extra={"event": "signal_admin_input_state_invalid"},
        )
        clear_admin_input_state(context)
        await message.reply_text(
            "این عملیات منقضی یا نامعتبر شده است؛ "
            "دوباره از منوی Signal شروع کنید.",
            reply_markup=build_signal_management_menu(),
        )


async def _consume_create_input(
    message,
    state: dict[str, object],
    data: dict[str, object],
    raw_value: str,
) -> None:
    value = raw_value.strip()
    step = state["step"]
    prompts = {
        "symbol": ("direction", "جهت را LONG یا SHORT ارسال کنید."),
        "direction": ("entry_price", "قیمت ورود را ارسال کنید."),
        "entry_price": ("stop_loss", "حد ضرر را ارسال کنید."),
        "stop_loss": ("leverage", "اهرم را ارسال کنید؛ نمونه: 5"),
        "leverage": (
            "description",
            "توضیحات را ارسال کنید؛ "
            "برای بدون توضیح «-» بفرستید.",
        ),
    }
    if step == "symbol":
        normalized = value.upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._:/-]{0,31}", normalized):
            raise InvalidSignalError("Signal symbol format is invalid")
        data["symbol"] = normalized
    elif step == "direction":
        normalized = value.upper()
        if normalized not in {"LONG", "SHORT"}:
            raise InvalidSignalError("Direction must be LONG or SHORT")
        data["direction"] = normalized
    elif step in {"entry_price", "stop_loss", "leverage"}:
        data[str(step)] = _exact_decimal(value, positive=True)
    elif step == "description":
        data["description"] = None if value == "-" else value
        state["step"] = "confirm"
        await message.reply_text(
            render_create_preview(data),
            reply_markup=build_signal_confirmation(action="create"),
        )
        return
    else:
        await message.reply_text(
            "برای ثبت از دکمه تأیید استفاده کنید.",
            reply_markup=build_signal_confirmation(action="create"),
        )
        return
    next_step, prompt = prompts[str(step)]
    state["step"] = next_step
    await message.reply_text(prompt, reply_markup=build_signal_input_cancel())


async def _consume_signal_selection(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
    signal_id: int,
) -> None:
    detail = await _load_admin_detail(
        get_database_manager(context),
        signal_id,
    )
    status = detail.signal.status
    mode, page = _list_location(context, status=status)
    _store_list_location(context, mode=mode, page=page)
    if action == _ACTION_SELECT_EDIT:
        if status not in {SignalStatus.DRAFT.value, SignalStatus.OPEN.value}:
            raise SignalStateError("Terminal signals cannot be edited")
        clear_admin_input_state(context)
        await message.reply_text(
            render_signal_detail(
                detail,
                timezone_name=get_report_timezone(context),
            ),
            reply_markup=build_signal_edit_fields(signal_id, status=status),
        )
        return
    if action == _ACTION_SELECT_CLOSE:
        if status != SignalStatus.OPEN.value:
            raise SignalStateError("Only an open signal can be closed")
        _set_state(
            context,
            action=_ACTION_CLOSE,
            step="profit_loss",
            data={"signal_id": signal_id},
        )
        await message.reply_text(
            "سود/زیان نهایی (P/L) را ارسال کنید؛ "
            "مقدار منفی مجاز است.",
            reply_markup=build_signal_input_cancel(),
        )
        return
    if action == _ACTION_SELECT_CANCEL:
        if status not in {SignalStatus.DRAFT.value, SignalStatus.OPEN.value}:
            raise SignalStateError("Terminal signals cannot be cancelled")
        clear_admin_input_state(context)
        await message.reply_text(
            render_signal_detail(
                detail,
                timezone_name=get_report_timezone(context),
            )
            + "\n\nآیا لغو این Signal را تأیید می‌کنید؟",
            reply_markup=build_signal_confirmation(
                action="cancel",
                signal_id=signal_id,
            ),
        )
        return
    if status not in {SignalStatus.DRAFT.value, SignalStatus.OPEN.value}:
        raise SignalStateError("Terminal signal targets cannot be managed")
    clear_admin_input_state(context)
    await message.reply_text(
        render_signal_detail(
            detail,
            timezone_name=get_report_timezone(context),
        ),
        reply_markup=_target_management_markup(detail),
    )


async def _consume_edit_input(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    data: dict[str, object],
) -> None:
    signal_id = int(data["signal_id"])
    field = str(data["field"])
    raw = message.text.strip()
    if field == "stop" and data.get("status") == SignalStatus.OPEN.value:
        updated = await _update_stop_loss(
            get_database_manager(context),
            signal_id,
            _exact_decimal(raw, positive=True),
        )
    else:
        values: dict[str, object] = {}
        if field == "symbol":
            values["symbol"] = raw
        elif field == "direction":
            values["direction"] = raw
        elif field == "entry":
            values["entry_price"] = _exact_decimal(raw, positive=True)
        elif field == "stop":
            values["stop_loss"] = _exact_decimal(raw, positive=True)
        elif field == "leverage":
            values["leverage"] = _exact_decimal(raw, positive=True)
        elif field == "description":
            if raw == "-":
                values["clear_description"] = True
            else:
                values["description"] = raw
        else:
            raise InvalidSignalError("Unsupported Signal field")
        updated = await _update_signal(
            get_database_manager(context),
            signal_id,
            UpdateSignal(**values),
        )
    clear_admin_input_state(context)
    await message.reply_text(
        f"✅ Signal #{updated.id} با موفقیت ویرایش شد.",
        reply_markup=build_signal_management_menu(),
    )


async def _consume_close_input(
    message,
    state: dict[str, object],
    data: dict[str, object],
) -> None:
    profit_loss = _exact_decimal(message.text, positive=False)
    data["profit_loss"] = profit_loss
    state["step"] = "confirm"
    await message.reply_text(
        f"P/L نهایی: {_decimal_text(profit_loss)}\n"
        "بستن Signal را تأیید می‌کنید؟",
        reply_markup=build_signal_confirmation(
            action="close",
            signal_id=int(data["signal_id"]),
        ),
    )


async def _consume_add_target_input(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    data: dict[str, object],
) -> None:
    target = await _add_target(
        get_database_manager(context),
        int(data["signal_id"]),
        _exact_decimal(message.text, positive=True),
    )
    clear_admin_input_state(context)
    await message.reply_text(
        f"✅ Target {target.target_number} با قیمت "
        f"{_decimal_text(target.target_price)} اضافه شد.",
        reply_markup=build_signal_management_menu(),
    )


async def _consume_hit_target_input(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    data: dict[str, object],
) -> None:
    target = await _hit_target(
        get_database_manager(context),
        int(data["signal_id"]),
        int(data["target_id"]),
        _exact_decimal(message.text, positive=False),
    )
    clear_admin_input_state(context)
    await message.reply_text(
        f"✅ برخورد Target {target.target_number} ثبت شد.",
        reply_markup=build_signal_management_menu(),
    )


async def _consume_stop_input(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    data: dict[str, object],
) -> None:
    signal = await _update_stop_loss(
        get_database_manager(context),
        int(data["signal_id"]),
        _exact_decimal(message.text, positive=True),
    )
    clear_admin_input_state(context)
    await message.reply_text(
        f"✅ حد ضرر Signal #{signal.id} به "
        f"{_decimal_text(signal.stop_loss)} تغییر کرد.",
        reply_markup=build_signal_management_menu(),
    )


async def signal_admin_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle exact, authorized signal-management callbacks."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer("در حال پردازش...")
    try:
        parts = query.data.split(":")
        action = parts[3]
        if action in {"menu", "panel"}:
            await _callback_navigation(query, context, action=action)
        elif action == "list":
            await _callback_list(
                query,
                context,
                mode=parts[4],
                page=int(parts[5]),
            )
        elif action == "view":
            await _callback_view(
                query,
                context,
                mode=parts[4],
                page=int(parts[5]),
                signal_id=int(parts[6]),
                target_page=int(parts[7]),
            )
        elif action == "create":
            await _callback_create(query, context, operation=parts[4])
        elif action == "edit":
            await _callback_edit(
                query,
                context,
                field=parts[4],
                signal_id=int(parts[5]),
            )
        elif action == "target":
            await _callback_target(
                query,
                context,
                operation=parts[4],
                signal_id=int(parts[5]),
                target_page=int(parts[6]) if parts[4] == "menu" else 1,
            )
        elif action == "hit":
            await _callback_hit_target(
                query,
                context,
                signal_id=int(parts[4]),
                target_id=int(parts[5]),
            )
        elif action == "close":
            await _callback_close(
                query,
                context,
                signal_id=int(parts[4]),
                operation=parts[5],
            )
        elif action in {"cancel", "publish"}:
            await _callback_terminal_action(
                query,
                context,
                action=action,
                signal_id=int(parts[4]),
                operation=parts[5],
            )
    except (IndexError, SignalError, ValueError) as error:
        logger.warning(
            "Administrator signal callback rejected",
            extra={
                "event": "signal_admin_callback_rejected",
                "error_type": type(error).__name__,
            },
        )
        text = _error_text(error) if isinstance(error, SignalError) else (
            "درخواست مدیریت Signal نامعتبر است."
        )
        await _safe_edit_signal_message(query, text)


async def _callback_navigation(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
) -> None:
    clear_admin_input_state(context)
    await _safe_edit_signal_message(query, "بازگشت انجام شد.")
    if query.message is not None:
        await query.message.reply_text(
            (
                "🛡 پنل مدیریت"
                if action == "panel"
                else "📡 مدیریت سیگنال‌ها"
            ),
            reply_markup=(
                build_admin_menu()
                if action == "panel"
                else build_signal_management_menu()
            ),
        )


async def _callback_list(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    page: int,
) -> None:
    clear_admin_input_state(context)
    result = await _load_admin_page(
        get_database_manager(context),
        mode=mode,
        page=page,
    )
    _store_list_location(context, mode=result.mode, page=result.page)
    text, markup = render_admin_signal_page(result)
    await _safe_edit_signal_message(query, text, reply_markup=markup)


async def _callback_view(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    page: int,
    signal_id: int,
    target_page: int,
) -> None:
    clear_admin_input_state(context)
    detail = await _load_admin_detail(
        get_database_manager(context),
        signal_id,
        target_page=target_page,
    )
    _store_list_location(context, mode=mode, page=page)
    await _safe_edit_signal_message(
        query,
        render_signal_detail(
            detail,
            timezone_name=get_report_timezone(context),
        ),
        reply_markup=_detail_markup(detail, mode=mode, page=page),
    )


async def _callback_create(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    operation: str,
) -> None:
    if operation == "cancel":
        await _callback_navigation(query, context, action="menu")
        return
    state = _state(context)
    data = state.get("data")
    if (
        state.get("action") != _ACTION_CREATE
        or state.get("step") != "confirm"
        or not isinstance(data, dict)
    ):
        raise InvalidSignalError("Create confirmation has expired")
    created = await _create_signal(
        get_database_manager(context),
        CreateSignal(
            symbol=str(data["symbol"]),
            direction=str(data["direction"]),
            entry_price=data["entry_price"],
            stop_loss=data["stop_loss"],
            leverage=data["leverage"],
            description=(
                str(data["description"])
                if data.get("description") is not None
                else None
            ),
            as_draft=True,
        ),
    )
    clear_admin_input_state(context)
    _store_list_location(
        context,
        mode=AdminSignalListMode.DRAFTS.value,
        page=1,
    )
    detail = await _load_admin_detail(
        get_database_manager(context),
        created.id,
    )
    await _safe_edit_signal_message(
        query,
        "✅ Signal به‌صورت پیش‌نویس ایجاد شد.\n\n"
        + render_signal_detail(
            detail,
            timezone_name=get_report_timezone(context),
        ),
        reply_markup=_detail_markup(
            detail,
            mode=AdminSignalListMode.DRAFTS.value,
            page=1,
        ),
    )
    if query.message is not None:
        await query.message.reply_text(
            "📡 منوی مدیریت Signal آماده است.",
            reply_markup=build_signal_management_menu(),
        )


async def _callback_edit(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    field: str,
    signal_id: int,
) -> None:
    detail = await _load_admin_detail(
        get_database_manager(context),
        signal_id,
    )
    if detail.signal.status not in {
        SignalStatus.DRAFT.value,
        SignalStatus.OPEN.value,
    }:
        raise SignalStateError("Terminal signals cannot be edited")
    if field == "menu":
        clear_admin_input_state(context)
        await _safe_edit_signal_message(
            query,
            render_signal_detail(
                detail,
                timezone_name=get_report_timezone(context),
            ),
            reply_markup=build_signal_edit_fields(
                signal_id,
                status=detail.signal.status,
            ),
        )
        return
    allowed = {"symbol", "description", "stop"}
    if detail.signal.status == SignalStatus.DRAFT.value:
        allowed.update({"direction", "entry", "leverage"})
    if field not in allowed:
        raise SignalStateError("This field cannot be edited in the current state")
    _set_state(
        context,
        action=_ACTION_EDIT,
        step="value",
        data={
            "signal_id": signal_id,
            "field": field,
            "status": detail.signal.status,
        },
    )
    prompts = {
        "symbol": "نماد جدید را ارسال کنید.",
        "direction": "جهت جدید را LONG یا SHORT ارسال کنید.",
        "entry": "قیمت ورود جدید را ارسال کنید.",
        "stop": "حد ضرر جدید را ارسال کنید.",
        "leverage": "اهرم جدید را ارسال کنید.",
        "description": (
            "توضیحات جدید یا «-» برای حذف را ارسال کنید."
        ),
    }
    await _safe_edit_signal_message(query, prompts[field])
    if query.message is not None:
        await query.message.reply_text(
            "مقدار جدید را ارسال کنید.",
            reply_markup=build_signal_input_cancel(),
        )


async def _callback_target(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    operation: str,
    signal_id: int,
    target_page: int,
) -> None:
    detail = await _load_admin_detail(
        get_database_manager(context),
        signal_id,
        target_page=target_page,
    )
    if detail.signal.status not in {
        SignalStatus.DRAFT.value,
        SignalStatus.OPEN.value,
    }:
        raise SignalStateError("Terminal signal targets cannot be managed")
    if operation == "menu":
        clear_admin_input_state(context)
        await _safe_edit_signal_message(
            query,
            render_signal_detail(
                detail,
                timezone_name=get_report_timezone(context),
            ),
            reply_markup=_target_management_markup(detail),
        )
        return
    if operation not in {"add", "stop"}:
        raise InvalidSignalError("Unsupported target operation")
    action = _ACTION_ADD_TARGET if operation == "add" else _ACTION_UPDATE_STOP
    if operation == "stop" and detail.signal.status != SignalStatus.OPEN.value:
        raise SignalStateError("Draft stop loss must be changed through edit")
    _set_state(
        context,
        action=action,
        step="value",
        data={"signal_id": signal_id},
    )
    prompt = (
        "قیمت Target جدید را ارسال کنید."
        if operation == "add"
        else "حد ضرر جدید را ارسال کنید."
    )
    await _safe_edit_signal_message(query, prompt)
    if query.message is not None:
        await query.message.reply_text(
            prompt,
            reply_markup=build_signal_input_cancel(),
        )


async def _callback_hit_target(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    signal_id: int,
    target_id: int,
) -> None:
    detail = await _load_admin_detail(
        get_database_manager(context),
        signal_id,
    )
    if detail.signal.status != SignalStatus.OPEN.value:
        raise SignalStateError("Targets can be hit only on open signals")
    _set_state(
        context,
        action=_ACTION_HIT_TARGET,
        step="profit_loss",
        data={"signal_id": signal_id, "target_id": target_id},
    )
    await _safe_edit_signal_message(
        query,
        "سود/زیان (P/L) این Target را ارسال کنید؛ "
        "مقدار منفی مجاز است.",
    )
    if query.message is not None:
        await query.message.reply_text(
            "مقدار P/L را ارسال کنید.",
            reply_markup=build_signal_input_cancel(),
        )


async def _callback_close(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    signal_id: int,
    operation: str,
) -> None:
    if operation == "start":
        detail = await _load_admin_detail(
            get_database_manager(context),
            signal_id,
        )
        if detail.signal.status != SignalStatus.OPEN.value:
            raise SignalStateError("Only an open signal can be closed")
        _set_state(
            context,
            action=_ACTION_CLOSE,
            step="profit_loss",
            data={"signal_id": signal_id},
        )
        await _safe_edit_signal_message(
            query,
            "سود/زیان نهایی (P/L) را ارسال کنید؛ "
            "مقدار منفی مجاز است.",
        )
        if query.message is not None:
            await query.message.reply_text(
                "مقدار P/L نهایی را ارسال کنید.",
                reply_markup=build_signal_input_cancel(),
            )
        return
    state = _state(context)
    data = state.get("data")
    if (
        state.get("action") != _ACTION_CLOSE
        or state.get("step") != "confirm"
        or not isinstance(data, dict)
        or int(data.get("signal_id", 0)) != signal_id
    ):
        raise InvalidSignalError("Close confirmation has expired")
    profit_loss = data.get("profit_loss")
    if not isinstance(profit_loss, Decimal):
        raise InvalidSignalError("Close confirmation has expired")
    closed = await _close_signal(
        get_database_manager(context),
        signal_id,
        profit_loss,
    )
    clear_admin_input_state(context)
    await _safe_edit_signal_message(
        query,
        f"✅ Signal #{closed.id} بسته شد.\n"
        f"P/L نهایی: {_decimal_text(closed.profit_loss)}",
    )
    if query.message is not None:
        await query.message.reply_text(
            "📡 مدیریت سیگنال‌ها",
            reply_markup=build_signal_management_menu(),
        )


async def _callback_terminal_action(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
    signal_id: int,
    operation: str,
) -> None:
    detail = await _load_admin_detail(
        get_database_manager(context),
        signal_id,
    )
    expected_status = (
        SignalStatus.DRAFT.value
        if action == "publish"
        else None
    )
    if expected_status and detail.signal.status != expected_status:
        raise SignalStateError("Only a draft signal can be published")
    if action == "cancel" and detail.signal.status not in {
        SignalStatus.DRAFT.value,
        SignalStatus.OPEN.value,
    }:
        raise SignalStateError("Terminal signals cannot be cancelled")
    if operation == "ask":
        verb = "انتشار" if action == "publish" else "لغو"
        await _safe_edit_signal_message(
            query,
            render_signal_detail(
                detail,
                timezone_name=get_report_timezone(context),
            )
            + f"\n\nآیا {verb} این Signal را تأیید می‌کنید؟",
            reply_markup=build_signal_confirmation(
                action=action,
                signal_id=signal_id,
            ),
        )
        return
    changed = (
        await _publish_signal(get_database_manager(context), signal_id)
        if action == "publish"
        else await _cancel_signal(get_database_manager(context), signal_id)
    )
    clear_admin_input_state(context)
    verb = "منتشر" if action == "publish" else "لغو"
    await _safe_edit_signal_message(
        query,
        f"✅ Signal #{changed.id} با موفقیت {verb} شد.",
    )
    if query.message is not None:
        await query.message.reply_text(
            "📡 مدیریت سیگنال‌ها",
            reply_markup=build_signal_management_menu(),
        )


async def _safe_edit_signal_message(
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


def register_admin_signal_handlers(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    """Register all Phase 20 signal routes behind fail-closed authorization."""
    guard = admin_required(admin_ids)
    private = filters.ChatType.PRIVATE
    instruction_pattern = (
        "^(?:"
        + "|".join(
            re.escape(item)
            for item in (
                SIGNAL_CREATE_BUTTON,
                SIGNAL_EDIT_BUTTON,
                SIGNAL_CLOSE_BUTTON,
                SIGNAL_CANCEL_BUTTON,
                SIGNAL_TARGETS_BUTTON,
            )
        )
        + ")$"
    )
    application.add_handler(
        CommandHandler(
            "signals_admin",
            guard(signal_management_handler),
            filters=private,
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SIGNAL_MANAGEMENT_BUTTON)}$"),
            guard(signal_management_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SIGNAL_ACTIVE_BUTTON)}$"),
            guard(active_signals_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SIGNAL_HISTORY_BUTTON)}$"),
            guard(signal_history_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SIGNAL_PUBLISH_BUTTON)}$"),
            guard(signal_publish_list_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(instruction_pattern),
            guard(signal_instruction_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private
            & filters.Regex(rf"^{re.escape(SIGNAL_ADMIN_CANCEL_INPUT_BUTTON)}$"),
            guard(signal_input_cancel_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SIGNAL_ADMIN_BACK_BUTTON)}$"),
            guard(signal_management_back_handler),
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            guard(signal_admin_callback_handler),
            pattern=ADMIN_SIGNAL_CALLBACK_PATTERN,
        )
    )
