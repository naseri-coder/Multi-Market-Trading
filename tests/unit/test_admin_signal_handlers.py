"""Advanced administrator signal handler and callback tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler

from app.bot.handlers import admin_signals
from app.bot.handlers.admin_state import SIGNAL_ADMIN_ACTION_KEY
from app.bot.keyboards.admin_signals import (
    ADMIN_SIGNAL_CALLBACK_PATTERN,
    SIGNAL_ACTIVE_BUTTON,
    SIGNAL_CANCEL_BUTTON,
    SIGNAL_CLOSE_BUTTON,
    SIGNAL_CREATE_BUTTON,
    SIGNAL_EDIT_BUTTON,
    SIGNAL_HISTORY_BUTTON,
    SIGNAL_PUBLISH_BUTTON,
    SIGNAL_TARGETS_BUTTON,
    build_admin_signal_detail,
    build_signal_management_menu,
    build_target_management,
)
from app.modules.signals.entities import (
    AdminSignalDetail,
    AdminSignalPage,
    SignalRecord,
    SignalTargetRecord,
)
from app.modules.signals.models import SignalStatus, SignalTargetStatus

NOW = datetime(2026, 9, 2, 9, tzinfo=UTC)


def signal_record(
    signal_id: int = 7,
    *,
    status: str = SignalStatus.DRAFT.value,
) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
        leverage=Decimal("5"),
        status=status,
        description="Setup",
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
        closed_at=None,
    )


def target_record(
    target_id: int = 11,
    *,
    number: int = 1,
) -> SignalTargetRecord:
    return SignalTargetRecord(
        id=target_id,
        signal_id=7,
        target_number=number,
        target_price=Decimal("110"),
        status=SignalTargetStatus.PENDING.value,
        hit_at=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
    )


def detail(*, status: str = SignalStatus.DRAFT.value) -> AdminSignalDetail:
    return AdminSignalDetail(
        signal=signal_record(status=status),
        targets=(target_record(),),
        target_page=1,
        target_page_size=10,
        total_targets=1,
        total_target_pages=1,
    )


def update(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        effective_message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        callback_query=None,
        update_id=20,
    )


def context() -> SimpleNamespace:
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={"database": object(), "report_timezone": "Asia/Tehran"}
        ),
    )


def callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def test_signal_management_menu_exposes_all_phase_twenty_actions() -> None:
    markup = build_signal_management_menu()
    labels = {button.text for row in markup.keyboard for button in row}

    assert {
        SIGNAL_CREATE_BUTTON,
        SIGNAL_ACTIVE_BUTTON,
        SIGNAL_HISTORY_BUTTON,
        SIGNAL_EDIT_BUTTON,
        SIGNAL_CLOSE_BUTTON,
        SIGNAL_CANCEL_BUTTON,
        SIGNAL_TARGETS_BUTTON,
        SIGNAL_PUBLISH_BUTTON,
    } <= labels


def test_all_generated_callbacks_are_anchored_and_telegram_safe() -> None:
    values: list[str] = []
    values.extend(
        callbacks(
            build_admin_signal_detail(
                7,
                status=SignalStatus.DRAFT.value,
                list_mode="drafts",
                list_page=2,
                target_page=1,
                total_target_pages=2,
            )
        )
    )
    values.extend(
        callbacks(
            build_admin_signal_detail(
                7,
                status=SignalStatus.OPEN.value,
                list_mode="active",
                list_page=1,
                target_page=2,
                total_target_pages=2,
            )
        )
    )
    values.extend(
        callbacks(
            build_target_management(
                7,
                [(11, 1), (12, 2)],
                status=SignalStatus.OPEN.value,
                page=1,
                total_pages=2,
            )
        )
    )

    assert values
    assert all(re.fullmatch(ADMIN_SIGNAL_CALLBACK_PATTERN, value) for value in values)
    assert all(len(value.encode("utf-8")) <= 64 for value in values)
    assert re.fullmatch(
        ADMIN_SIGNAL_CALLBACK_PATTERN,
        "v1:signals:admin:publish:7:confirm:tampered",
    ) is None
    assert re.fullmatch(
        ADMIN_SIGNAL_CALLBACK_PATTERN,
        "v1:signals:admin:list:active:0",
    ) is None


def test_admin_signal_page_is_compact_and_contains_internal_ids() -> None:
    page = AdminSignalPage(
        signals=(signal_record(7), signal_record(8)),
        mode="drafts",
        page=1,
        page_size=10,
        total_items=2,
        total_pages=1,
    )

    text, markup = admin_signals.render_admin_signal_page(page)

    assert "Signal #7" in text
    assert "Signal #8" in text
    assert len(callbacks(markup)) == 4


async def test_guided_create_collects_exact_values_and_requires_confirmation() -> None:
    current_context = context()
    current_update = update(SIGNAL_CREATE_BUTTON)

    await admin_signals.signal_instruction_handler(current_update, current_context)
    for value in ("btc/usdt", "long", "100.25", "90", "5", "-"):
        current_update.effective_message.text = value
        await admin_signals.signal_admin_input_handler(current_update, current_context)

    state = current_context.user_data[SIGNAL_ADMIN_ACTION_KEY]
    assert state["step"] == "confirm"
    assert state["data"] == {
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "entry_price": Decimal("100.25"),
        "stop_loss": Decimal("90"),
        "leverage": Decimal("5"),
        "description": None,
    }
    last_reply = current_update.effective_message.reply_text.await_args
    assert "پیش‌نمایش" in last_reply.args[0]
    assert callbacks(last_reply.kwargs["reply_markup"]) == [
        "v1:signals:admin:create:confirm",
        "v1:signals:admin:create:cancel",
    ]


async def test_invalid_create_value_keeps_the_current_step() -> None:
    current_context = context()
    current_context.user_data[SIGNAL_ADMIN_ACTION_KEY] = {
        "action": "create",
        "step": "direction",
        "data": {"symbol": "BTC/USDT"},
    }
    current_update = update("SIDEWAYS")

    await admin_signals.signal_admin_input_handler(current_update, current_context)

    assert current_context.user_data[SIGNAL_ADMIN_ACTION_KEY]["step"] == "direction"
    assert "نامعتبر" in current_update.effective_message.reply_text.await_args.args[0]


async def test_corrupt_input_state_is_cleared_without_unhandled_error() -> None:
    current_context = context()
    current_context.user_data[SIGNAL_ADMIN_ACTION_KEY] = {
        "action": "edit",
        "step": "value",
        "data": {},
    }
    current_update = update("BTC/USDT")

    await admin_signals.signal_admin_input_handler(current_update, current_context)

    assert SIGNAL_ADMIN_ACTION_KEY not in current_context.user_data
    assert "نامعتبر" in current_update.effective_message.reply_text.await_args.args[0]


async def test_publish_confirmation_calls_service_once_and_clears_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_context = context()
    query = SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        edit_message_text=AsyncMock(),
    )
    published = signal_record(status=SignalStatus.OPEN.value)
    monkeypatch.setattr(admin_signals, "_load_admin_detail", AsyncMock(return_value=detail()))
    publish = AsyncMock(return_value=published)
    monkeypatch.setattr(admin_signals, "_publish_signal", publish)
    database = current_context.application.bot_data["database"]
    monkeypatch.setattr(
        admin_signals,
        "get_database_manager",
        lambda current: database,
    )

    await admin_signals._callback_terminal_action(
        query,
        current_context,
        action="publish",
        signal_id=7,
        operation="confirm",
    )

    publish.assert_awaited_once_with(database, 7)
    assert SIGNAL_ADMIN_ACTION_KEY not in current_context.user_data
    assert "منتشر شد" in query.edit_message_text.await_args.args[0]


async def test_duplicate_callback_edit_is_harmless() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=BadRequest("Message is not modified"))
    )

    await admin_signals._safe_edit_signal_message(query, "same")

    query.edit_message_text.assert_awaited_once()


def test_registration_adds_nine_fail_closed_admin_routes() -> None:
    application = SimpleNamespace(add_handler=Mock())

    admin_signals.register_admin_signal_handlers(application, {123456789})

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 9
    assert all(hasattr(handler.callback, "__wrapped__") for handler in handlers)
    assert isinstance(handlers[-1], CallbackQueryHandler)
    assert handlers[-1].pattern.fullmatch("v1:signals:admin:publish:7:confirm")
    assert handlers[-1].pattern.fullmatch(
        "v1:signals:admin:publish:7:confirm:tampered"
    ) is None
