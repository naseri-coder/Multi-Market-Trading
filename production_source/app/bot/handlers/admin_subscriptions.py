"""Guided administrator workflows for plans and subscriptions."""

from __future__ import annotations

import logging
import re
from collections.abc import Collection
from datetime import UTC
from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.dependencies import get_database_manager
from app.bot.handlers.admin_state import (
    SUBSCRIPTION_ADMIN_ACTION_KEY,
    clear_admin_input_state,
)
from app.bot.keyboards.admin import build_admin_menu
from app.bot.keyboards.subscriptions import (
    SUBSCRIPTION_ACTIVATE_BUTTON,
    SUBSCRIPTION_ADMIN_BACK_BUTTON,
    SUBSCRIPTION_EXPIRE_BUTTON,
    SUBSCRIPTION_MANAGEMENT_BUTTON,
    SUBSCRIPTION_PLAN_CREATE_BUTTON,
    SUBSCRIPTION_PLAN_DELETE_BUTTON,
    SUBSCRIPTION_PLAN_EDIT_BUTTON,
    SUBSCRIPTION_PLAN_LIST_BUTTON,
    build_subscription_management_menu,
)
from app.bot.middlewares.admin import admin_required
from app.db.session import DatabaseManager
from app.modules.subscriptions.entities import (
    CreateSubscriptionPlan,
    SubscriptionPlanRecord,
    SubscriptionRecord,
    UpdateSubscriptionPlan,
)
from app.modules.subscriptions.errors import (
    ActiveSubscriptionExistsError,
    ActiveSubscriptionNotFoundError,
    DuplicateSubscriptionPlanError,
    InvalidSubscriptionError,
    SubscriptionError,
    SubscriptionPlanInUseError,
    SubscriptionPlanNotFoundError,
    SubscriptionUserNotFoundError,
)
from app.modules.subscriptions.repository import SQLAlchemySubscriptionRepository
from app.modules.subscriptions.service import SubscriptionService

logger = logging.getLogger(__name__)
_ACTION_CREATE = "create"
_ACTION_EDIT = "edit"
_ACTION_DELETE = "delete"
_ACTION_ACTIVATE = "activate"
_ACTION_EXPIRE = "expire"


def has_pending_subscription_admin_action(
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Return whether the next administrator text belongs to this workflow."""
    state = context.user_data.get(SUBSCRIPTION_ADMIN_ACTION_KEY)
    return (
        isinstance(state, dict)
        and state.get("action") in {
            _ACTION_CREATE,
            _ACTION_EDIT,
            _ACTION_DELETE,
            _ACTION_ACTIVATE,
            _ACTION_EXPIRE,
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
    context.user_data[SUBSCRIPTION_ADMIN_ACTION_KEY] = {
        "action": action,
        "step": step,
        "data": data or {},
    }


def _state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    state = context.user_data.get(SUBSCRIPTION_ADMIN_ACTION_KEY)
    if not isinstance(state, dict):
        raise InvalidSubscriptionError("Subscription action state is missing")
    return state


def _positive_integer(value: str, label: str) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise InvalidSubscriptionError(f"{label} must be an integer") from exc
    if parsed <= 0:
        raise InvalidSubscriptionError(f"{label} must be positive")
    return parsed


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except InvalidOperation as exc:
        raise InvalidSubscriptionError("Plan price must be a decimal") from exc


async def _list_plans(database: DatabaseManager) -> tuple[SubscriptionPlanRecord, ...]:
    async with database.session() as session:
        return await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).list_plans()


async def _get_plan(database: DatabaseManager, plan_id: int) -> SubscriptionPlanRecord:
    async with database.session() as session:
        return await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).get_plan(plan_id)


async def _create_plan(
    database: DatabaseManager,
    request: CreateSubscriptionPlan,
) -> SubscriptionPlanRecord:
    async with database.session() as session, session.begin():
        return await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).create_plan(request)


async def _update_plan(
    database: DatabaseManager,
    plan_id: int,
    request: UpdateSubscriptionPlan,
) -> SubscriptionPlanRecord:
    async with database.session() as session, session.begin():
        return await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).update_plan(plan_id, request)


async def _delete_plan(database: DatabaseManager, plan_id: int) -> None:
    async with database.session() as session, session.begin():
        await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).delete_plan(plan_id)


async def _resolve_user(database: DatabaseManager, telegram_user_id: int) -> int:
    async with database.session() as session:
        return await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).resolve_user_id(telegram_user_id)


async def _activate(
    database: DatabaseManager,
    user_id: int,
    plan_id: int,
) -> SubscriptionRecord:
    async with database.session() as session, session.begin():
        return await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).activate_subscription(user_id, plan_id)


async def _expire(database: DatabaseManager, user_id: int) -> SubscriptionRecord:
    async with database.session() as session, session.begin():
        return await SubscriptionService(
            SQLAlchemySubscriptionRepository(session)
        ).expire_user_subscription(user_id)


def render_plan(plan: SubscriptionPlanRecord) -> str:
    """Render one plan with its stable internal identifier."""
    state = "فعال ✅" if plan.is_active else "غیرفعال ⏸"
    description = plan.description or "ندارد"
    return "\n".join(
        (
            f"💎 پلن #{plan.id}: {plan.name}",
            f"مدت: {plan.duration_days} روز",
            f"قیمت: {plan.price:.2f} {plan.currency}",
            f"وضعیت: {state}",
            f"توضیحات: {description}",
        )
    )


def render_plan_pages(
    plans: tuple[SubscriptionPlanRecord, ...],
) -> tuple[str, ...]:
    """Bound plan-list messages to eight records per Telegram message."""
    if not plans:
        return ("📋 هنوز هیچ پلنی تعریف نشده است.",)
    return tuple(
        "📋 فهرست پلن‌ها\n\n"
        + "\n\n".join(render_plan(plan) for plan in plans[offset : offset + 8])
        for offset in range(0, len(plans), 8)
    )


def _error_text(error: SubscriptionError) -> str:
    if isinstance(error, SubscriptionPlanNotFoundError):
        return "پلن موردنظر پیدا نشد."
    if isinstance(error, DuplicateSubscriptionPlanError):
        return "پلنی با این نام قبلاً ثبت شده است."
    if isinstance(error, SubscriptionPlanInUseError):
        return "این پلن سابقه اشتراک دارد و قابل حذف نیست؛ آن را غیرفعال کنید."
    if isinstance(error, SubscriptionUserNotFoundError):
        return "کاربری با این شناسه تلگرام در ربات ثبت نشده است."
    if isinstance(error, ActiveSubscriptionExistsError):
        return "این کاربر از قبل اشتراک فعال دارد."
    if isinstance(error, ActiveSubscriptionNotFoundError):
        return "این کاربر اشتراک فعالی ندارد."
    if isinstance(error, InvalidSubscriptionError):
        return f"اطلاعات نامعتبر است: {error}"
    return "عملیات اشتراک انجام نشد. کمی بعد دوباره تلاش کنید."


async def subscription_management_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text(
            "💎 مدیریت پلن‌ها و اشتراک کاربران",
            reply_markup=build_subscription_management_menu(),
        )


async def subscription_management_back_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text("به پنل مدیریت بازگشتید.", reply_markup=build_admin_menu())


async def subscription_plan_list_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None:
        return
    try:
        pages = render_plan_pages(await _list_plans(get_database_manager(context)))
    except SubscriptionError as error:
        logger.exception(
            "Subscription plan list failed",
            extra={"event": "subscription_admin_list_failed"},
        )
        await message.reply_text(
            _error_text(error),
            reply_markup=build_subscription_management_menu(),
        )
        return
    for index, page in enumerate(pages):
        await message.reply_text(
            page,
            reply_markup=(
                build_subscription_management_menu()
                if index == len(pages) - 1
                else None
            ),
        )


async def subscription_instruction_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None:
        return
    selected = message.text
    instructions = {
        SUBSCRIPTION_PLAN_CREATE_BUTTON: (
            _ACTION_CREATE,
            "name",
            "نام پلن را بفرستید.",
        ),
        SUBSCRIPTION_PLAN_EDIT_BUTTON: (
            _ACTION_EDIT,
            "plan_id",
            "ID داخلی پلنی را که می‌خواهید ویرایش شود بفرستید.",
        ),
        SUBSCRIPTION_PLAN_DELETE_BUTTON: (
            _ACTION_DELETE,
            "plan_id",
            "ID داخلی پلن استفاده‌نشده را برای حذف بفرستید.",
        ),
        SUBSCRIPTION_ACTIVATE_BUTTON: (
            _ACTION_ACTIVATE,
            "telegram_user_id",
            "شناسه عددی تلگرام کاربر را بفرستید.",
        ),
        SUBSCRIPTION_EXPIRE_BUTTON: (
            _ACTION_EXPIRE,
            "telegram_user_id",
            "شناسه عددی تلگرام کاربر را برای پایان اشتراک بفرستید.",
        ),
    }
    instruction = instructions.get(selected)
    if instruction is None:
        clear_admin_input_state(context)
        return
    action, step, text = instruction
    _set_state(context, action=action, step=step)
    await message.reply_text(text, reply_markup=build_subscription_management_menu())


async def subscription_admin_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Consume one guided plan/subscription input without command syntax."""
    message = update.effective_message
    if message is None or not message.text:
        return
    state = _state(context)
    action = state["action"]
    step = state["step"]
    data = state["data"]
    if not isinstance(data, dict):
        clear_admin_input_state(context)
        return
    value = message.text.strip()
    database = get_database_manager(context)
    final_step = False
    try:
        if action == _ACTION_CREATE:
            final_step = await _consume_create(message, state, data, value, database)
        elif action == _ACTION_EDIT:
            final_step = await _consume_edit(message, state, data, value, database)
        elif action == _ACTION_DELETE:
            final_step = True
            plan_id = _positive_integer(value, "Plan ID")
            await _delete_plan(database, plan_id)
            await message.reply_text(f"پلن #{plan_id} حذف شد.")
        elif action == _ACTION_ACTIVATE:
            final_step = await _consume_activate(message, state, data, value, database)
        elif action == _ACTION_EXPIRE:
            final_step = True
            telegram_user_id = _positive_integer(value, "Telegram user ID")
            user_id = await _resolve_user(database, telegram_user_id)
            expired = await _expire(database, user_id)
            await message.reply_text(
                f"اشتراک #{expired.id} کاربر {telegram_user_id} پایان یافت."
            )
        else:
            clear_admin_input_state(context)
            return
    except SubscriptionError as error:
        if final_step:
            clear_admin_input_state(context)
        await message.reply_text(
            _error_text(error),
            reply_markup=build_subscription_management_menu(),
        )
        return
    if final_step:
        clear_admin_input_state(context)
        await message.reply_text(
            "عملیات با موفقیت انجام شد.",
            reply_markup=build_subscription_management_menu(),
        )


async def _consume_create(message, state, data, value, database) -> bool:
    step = state["step"]
    prompts = {
        "name": ("duration_days", "مدت پلن را به روز بفرستید."),
        "duration_days": ("price", "قیمت پلن را بفرستید."),
        "price": ("currency", "واحد قیمت مانند USDT را بفرستید."),
        "currency": (
            "description",
            "توضیحات پلن را بفرستید؛ برای بدون توضیح «-» ارسال کنید.",
        ),
    }
    if step in prompts:
        if step == "duration_days":
            data[step] = _positive_integer(value, "Duration")
        elif step == "price":
            data[step] = _decimal(value)
        else:
            data[step] = value
        next_step, prompt = prompts[step]
        state["step"] = next_step
        await message.reply_text(prompt)
        return False
    request = CreateSubscriptionPlan(
        name=str(data["name"]),
        duration_days=int(data["duration_days"]),
        price=data["price"],
        currency=str(data["currency"]),
        description=None if value == "-" else value,
    )
    created = await _create_plan(database, request)
    await message.reply_text(f"پلن #{created.id} «{created.name}» ایجاد شد.")
    return True


async def _consume_edit(message, state, data, value, database) -> bool:
    step = state["step"]
    if step == "plan_id":
        plan = await _get_plan(database, _positive_integer(value, "Plan ID"))
        data.update(
            {
                "plan_id": plan.id,
                "name": plan.name,
                "duration_days": plan.duration_days,
                "price": plan.price,
                "currency": plan.currency,
                "description": plan.description,
                "is_active": plan.is_active,
            }
        )
        state["step"] = "name"
        await message.reply_text(
            render_plan(plan)
            + "\n\nنام جدید را بفرستید؛ برای حفظ مقدار فعلی «-» ارسال کنید."
        )
        return False
    prompts = {
        "name": ("duration_days", "مدت جدید یا «-» را بفرستید."),
        "duration_days": ("price", "قیمت جدید یا «-» را بفرستید."),
        "price": ("currency", "واحد قیمت جدید یا «-» را بفرستید."),
        "currency": (
            "description",
            "توضیحات جدید، «-» برای حفظ، یا «حذف» برای پاک‌کردن را بفرستید.",
        ),
        "description": (
            "is_active",
            "وضعیت را «فعال»، «غیرفعال» یا «-» بفرستید.",
        ),
    }
    if step in prompts:
        if value != "-":
            if step == "duration_days":
                data[step] = _positive_integer(value, "Duration")
            elif step == "price":
                data[step] = _decimal(value)
            elif step == "description":
                data[step] = None if value == "حذف" else value
            else:
                data[step] = value
        next_step, prompt = prompts[step]
        state["step"] = next_step
        await message.reply_text(prompt)
        return False
    if value != "-":
        if value not in {"فعال", "غیرفعال"}:
            raise InvalidSubscriptionError(
                "Plan state must be فعال, غیرفعال, or -"
            )
        data["is_active"] = value == "فعال"
    updated = await _update_plan(
        database,
        int(data["plan_id"]),
        UpdateSubscriptionPlan(
            name=str(data["name"]),
            duration_days=int(data["duration_days"]),
            price=data["price"],
            currency=str(data["currency"]),
            description=data["description"],
            is_active=bool(data["is_active"]),
        ),
    )
    await message.reply_text(f"پلن #{updated.id} «{updated.name}» ویرایش شد.")
    return True


async def _consume_activate(message, state, data, value, database) -> bool:
    if state["step"] == "telegram_user_id":
        telegram_user_id = _positive_integer(value, "Telegram user ID")
        data["telegram_user_id"] = telegram_user_id
        data["user_id"] = await _resolve_user(database, telegram_user_id)
        plans = tuple(plan for plan in await _list_plans(database) if plan.is_active)
        if not plans:
            raise InvalidSubscriptionError("No active plan is available")
        state["step"] = "plan_id"
        await message.reply_text(
            "پلن فعال را با ID انتخاب کنید:\n\n"
            + "\n\n".join(render_plan(plan) for plan in plans)
        )
        return False
    plan_id = _positive_integer(value, "Plan ID")
    activated = await _activate(database, int(data["user_id"]), plan_id)
    await message.reply_text(
        "\n".join(
            (
                f"اشتراک #{activated.id} فعال شد.",
                f"کاربر: {data['telegram_user_id']}",
                f"پلن: {activated.plan_name}",
                f"پایان: {activated.expires_at.astimezone(UTC):%Y-%m-%d %H:%M UTC}",
            )
        )
    )
    return True


def register_admin_subscription_handlers(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    """Register every subscription admin route behind fail-closed authorization."""
    private = filters.ChatType.PRIVATE
    guard = admin_required(admin_ids)
    actions_pattern = (
        "^(?:"
        + "|".join(
            re.escape(item)
            for item in (
                SUBSCRIPTION_PLAN_CREATE_BUTTON,
                SUBSCRIPTION_PLAN_EDIT_BUTTON,
                SUBSCRIPTION_PLAN_DELETE_BUTTON,
                SUBSCRIPTION_ACTIVATE_BUTTON,
                SUBSCRIPTION_EXPIRE_BUTTON,
            )
        )
        + ")$"
    )
    application.add_handler(
        CommandHandler(
            "subscriptions_admin",
            guard(subscription_management_handler),
            filters=private,
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUBSCRIPTION_MANAGEMENT_BUTTON)}$"),
            guard(subscription_management_handler),
        )
    )
    application.add_handler(
        CommandHandler(
            "subscription_plans",
            guard(subscription_plan_list_handler),
            filters=private,
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUBSCRIPTION_PLAN_LIST_BUTTON)}$"),
            guard(subscription_plan_list_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(actions_pattern),
            guard(subscription_instruction_handler),
        )
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(SUBSCRIPTION_ADMIN_BACK_BUTTON)}$"),
            guard(subscription_management_back_handler),
        )
    )
