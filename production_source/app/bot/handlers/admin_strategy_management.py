"""Administrator controls for independent signal-strategy routing."""

from __future__ import annotations

import re
from collections.abc import Collection

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.bot.dependencies import get_database_manager
from app.bot.handlers.admin_state import (
    STRATEGY_ADMIN_ACTION_KEY,
    clear_admin_input_state,
)
from app.bot.keyboards.admin import build_admin_menu
from app.bot.keyboards.strategy_management import (
    BROOKS_STRATEGY_BUTTON,
    FM_STRATEGY_BUTTON,
    STRATEGY_ADMIN_BACK_BUTTON,
    STRATEGY_CALLBACK_PATTERN,
    STRATEGY_MANAGEMENT_BUTTON,
    build_strategy_actions,
    build_strategy_management_menu,
)
from app.bot.middlewares.admin import admin_required
from app.integrations.telegram.channels import TelegramChannelGateway
from app.modules.signal_strategies.entities import (
    BROOKS_STRATEGY_CODE,
    FM_STRATEGY_CODE,
    SignalStrategyRecord,
)
from app.modules.signal_strategies.errors import SignalStrategyError
from app.modules.signal_strategies.repository import SQLAlchemySignalStrategyRepository
from app.modules.signal_strategies.service import SignalStrategyService

_BUTTON_TO_CODE = {
    BROOKS_STRATEGY_BUTTON: BROOKS_STRATEGY_CODE,
    FM_STRATEGY_BUTTON: FM_STRATEGY_CODE,
}


def has_pending_strategy_admin_action(context: ContextTypes.DEFAULT_TYPE) -> bool:
    state = context.user_data.get(STRATEGY_ADMIN_ACTION_KEY)
    return (
        isinstance(state, dict)
        and state.get("action") == "set_channel"
        and state.get("strategy_code") in {BROOKS_STRATEGY_CODE, FM_STRATEGY_CODE}
    )


async def _list(context: ContextTypes.DEFAULT_TYPE) -> tuple[SignalStrategyRecord, ...]:
    database = get_database_manager(context)
    async with database.session() as session:
        return await SignalStrategyService(
            SQLAlchemySignalStrategyRepository(session)
        ).list_all()


async def _get(
    context: ContextTypes.DEFAULT_TYPE, strategy_code: str
) -> SignalStrategyRecord:
    database = get_database_manager(context)
    async with database.session() as session:
        return await SignalStrategyService(
            SQLAlchemySignalStrategyRepository(session)
        ).get(strategy_code)


async def _toggle(
    context: ContextTypes.DEFAULT_TYPE, strategy_code: str, admin_id: int
) -> SignalStrategyRecord:
    database = get_database_manager(context)
    async with database.session() as session, session.begin():
        return await SignalStrategyService(
            SQLAlchemySignalStrategyRepository(session)
        ).toggle(strategy_code, updated_by_telegram_user_id=admin_id)


async def _clear_channel(
    context: ContextTypes.DEFAULT_TYPE, strategy_code: str, admin_id: int
) -> SignalStrategyRecord:
    database = get_database_manager(context)
    async with database.session() as session, session.begin():
        return await SignalStrategyService(
            SQLAlchemySignalStrategyRepository(session)
        ).clear_channel(strategy_code, updated_by_telegram_user_id=admin_id)


async def _set_channel(
    context: ContextTypes.DEFAULT_TYPE,
    strategy_code: str,
    *,
    reference: str,
    admin_id: int,
) -> SignalStrategyRecord:
    resolved = await TelegramChannelGateway(context.bot).resolve_channel(
        reference,
        ensure_invite_link=False,
    )
    database = get_database_manager(context)
    async with database.session() as session, session.begin():
        return await SignalStrategyService(
            SQLAlchemySignalStrategyRepository(session)
        ).set_channel(
            strategy_code,
            chat_id=resolved.telegram_chat_id,
            title=resolved.title,
            username=resolved.username,
            updated_by_telegram_user_id=admin_id,
        )


def _detail(item: SignalStrategyRecord) -> str:
    desired = "فعال ✅" if item.enabled else "غیرفعال ⏸"
    engine = "آماده ✅" if item.engine_ready else "هسته هنوز متصل نشده 🧱"
    effective = "فعال ✅" if item.effective_enabled else "غیرفعال ⏸"
    channel = (
        f"{item.private_channel_title} ({item.private_channel_id})"
        if item.private_channel_id is not None
        else "تعیین نشده"
    )
    return (
        f"🎛 {item.display_name}\n\n"
        f"وضعیت انتخابی: {desired}\n"
        f"هسته: {engine}\n"
        f"سیگنال‌دهی مؤثر: {effective}\n"
        f"کانال خصوصی: {channel}"
    )


def _summary(items: tuple[SignalStrategyRecord, ...]) -> str:
    lines = ["🎛 مدیریت سیگنال‌دهی", ""]
    for item in items:
        state = "✅ فعال" if item.effective_enabled else "⏸ غیرفعال"
        channel = item.private_channel_title or "بدون کانال"
        lines.append(f"• {item.display_name}: {state} — {channel}")
    lines.extend(("", "هر هسته کانال خصوصی و وضعیت مستقل دارد."))
    return "\n".join(lines)


async def strategy_management_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        _summary(await _list(context)),
        reply_markup=build_strategy_management_menu(),
    )


async def strategy_choice_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is None or message.text not in _BUTTON_TO_CODE:
        return
    item = await _get(context, _BUTTON_TO_CODE[message.text])
    await message.reply_text(
        _detail(item),
        reply_markup=build_strategy_actions(item.strategy_code, enabled=item.enabled),
    )


async def strategy_management_back_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    clear_admin_input_state(context)
    message = update.effective_message
    if message is not None:
        await message.reply_text("به پنل مدیریت بازگشتید.", reply_markup=build_admin_menu())


async def strategy_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or not query.data:
        return
    await query.answer()
    _, _, strategy_code, action = query.data.split(":", 3)
    try:
        if action == "toggle":
            item = await _toggle(context, strategy_code, user.id)
        elif action == "clear_channel":
            item = await _clear_channel(context, strategy_code, user.id)
        elif action == "set_channel":
            clear_admin_input_state(context)
            context.user_data[STRATEGY_ADMIN_ACTION_KEY] = {
                "action": "set_channel",
                "strategy_code": strategy_code,
            }
            if query.message is not None:
                await query.message.reply_text(
                    "شناسه عددی کانال خصوصی (مثل -100...) یا @username را بفرستید. "
                    "ربات باید Administrator کانال باشد."
                )
            return
        else:
            item = await _get(context, strategy_code)
    except SignalStrategyError as exc:
        if query.message is not None:
            await query.message.reply_text(f"⚠️ {exc}")
        return

    if query.message is not None:
        await query.message.reply_text(
            _detail(item),
            reply_markup=build_strategy_actions(item.strategy_code, enabled=item.enabled),
        )


async def strategy_admin_input_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    state = context.user_data.get(STRATEGY_ADMIN_ACTION_KEY)
    message = update.effective_message
    user = update.effective_user
    if (
        not isinstance(state, dict)
        or state.get("action") != "set_channel"
        or message is None
        or not message.text
        or user is None
    ):
        return
    strategy_code = str(state.get("strategy_code", ""))
    try:
        item = await _set_channel(
            context,
            strategy_code,
            reference=message.text.strip(),
            admin_id=user.id,
        )
    except Exception:
        await message.reply_text(
            "کانال قابل تأیید نبود. شناسه را بررسی کنید و مطمئن شوید ربات Administrator است."
        )
        return
    clear_admin_input_state(context)
    await message.reply_text(
        "✅ کانال خصوصی ذخیره شد.\n\n" + _detail(item),
        reply_markup=build_strategy_management_menu(),
    )


def register_admin_strategy_management_handlers(
    application: Application,
    admin_ids: Collection[int],
) -> None:
    private = filters.ChatType.PRIVATE
    guard = admin_required(admin_ids)
    choice_pattern = (
        "^(?:"
        + "|".join(re.escape(x) for x in (BROOKS_STRATEGY_BUTTON, FM_STRATEGY_BUTTON))
        + ")$"
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(STRATEGY_MANAGEMENT_BUTTON)}$"),
            guard(strategy_management_handler),
        )
    )
    application.add_handler(
        MessageHandler(private & filters.Regex(choice_pattern), guard(strategy_choice_handler))
    )
    application.add_handler(
        MessageHandler(
            private & filters.Regex(rf"^{re.escape(STRATEGY_ADMIN_BACK_BUTTON)}$"),
            guard(strategy_management_back_handler),
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            guard(strategy_callback_handler),
            pattern=STRATEGY_CALLBACK_PATTERN,
        )
    )
