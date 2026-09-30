"""Telegram rendering, access, and callback tests for Phase 13 signals."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler

from app.bot.handlers import signals_user
from app.bot.handlers.support_state import SUPPORT_USER_ACTION_KEY
from app.bot.keyboards.favorites import FAVORITES_CALLBACK_PATTERN
from app.bot.keyboards.signals import (
    LIVE_SIGNALS_BUTTON,
    USER_SIGNAL_CALLBACK_PATTERN,
    build_signal_detail_actions,
    build_signal_list,
)
from app.modules.signals.entities import (
    SignalDetail,
    SignalListMode,
    SignalPage,
    SignalRecord,
    SignalTargetRecord,
)
from app.modules.signals.models import (
    SignalDirection,
    SignalStatus,
    SignalTargetStatus,
)

NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


def signal_record(
    *,
    signal_id: int = 7,
    status: str = SignalStatus.OPEN.value,
    profit_loss: Decimal | None = None,
) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=Decimal("100.000000000000000000"),
        stop_loss=Decimal("95.500000000000000000"),
        leverage=Decimal("5.00"),
        status=status,
        description="Breakout confirmation",
        profit_loss=profit_loss,
        created_at=NOW,
        updated_at=NOW,
        closed_at=NOW if status != SignalStatus.OPEN.value else None,
    )


def target_record(number: int, *, status: str) -> SignalTargetRecord:
    return SignalTargetRecord(
        id=100 + number,
        signal_id=7,
        target_number=number,
        target_price=Decimal(100 + number),
        status=status,
        hit_at=NOW if status == SignalTargetStatus.HIT.value else None,
        profit_loss=Decimal("2.50") if status == SignalTargetStatus.HIT.value else None,
        created_at=NOW,
        updated_at=NOW,
    )


def page(*signals: SignalRecord, mode: str = SignalListMode.OPEN.value) -> SignalPage:
    return SignalPage(
        signals=signals,
        mode=mode,
        page=1,
        page_size=10,
        total_items=len(signals),
        total_pages=1,
    )


def detail() -> SignalDetail:
    return SignalDetail(
        signal=signal_record(),
        targets=(
            target_record(1, status=SignalTargetStatus.HIT.value),
            target_record(2, status=SignalTargetStatus.PENDING.value),
        ),
        target_page=1,
        target_page_size=10,
        total_targets=12,
        total_target_pages=2,
    )


def update(*, callback_data: str | None = None) -> SimpleNamespace:
    message = SimpleNamespace(text=LIVE_SIGNALS_BUTTON, reply_text=AsyncMock())
    query = None
    if callback_data is not None:
        query = SimpleNamespace(
            data=callback_data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123456789,
            username="user",
            first_name="User",
            last_name=None,
            language_code="fa",
            is_bot=False,
        ),
        effective_message=message,
        callback_query=query,
        update_id=55,
    )


def context(*, user_data: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_data={} if user_data is None else user_data,
        application=SimpleNamespace(
            bot_data={
                "database": object(),
                "admin_ids": frozenset(),
                "report_timezone": "Asia/Tehran",
            }
        ),
    )


def test_signal_page_renderer_is_bounded_and_contains_required_fields() -> None:
    text, keyboard = signals_user.render_signal_page(page(signal_record()))

    assert "🟢 سیگنال‌های باز" in text
    assert "💱 نماد: BTC/USDT" in text
    assert "🟩 جهت: خرید (LONG)" in text
    assert "🟢 وضعیت: باز" in text
    assert "🎯 ورود: 100" in text
    assert "📈 سود/زیان (P/L): —" in text
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "v1:signals:user:view:open:1:7:1" in callbacks
    assert callbacks[-1] == "v1:signals:user:menu"


def test_detail_renderer_contains_stop_leverage_pl_and_target_status() -> None:
    text = signals_user.render_signal_detail(detail(), timezone_name="Asia/Tehran")

    assert "💱 نماد: BTC/USDT" in text
    assert "🟩 جهت: خرید (LONG)" in text
    assert "🟢 وضعیت: باز" in text
    assert "🎯 قیمت ورود: 100" in text
    assert "🛡️ حد ضرر: 95.5" in text
    assert "⚡ اهرم: 5x" in text
    assert "📈 سود/زیان (P/L): —" in text
    assert "🎯 هدف 1: 101 | ✅ هدف خورده | 📈 سود/زیان: 2.5" in text
    assert "🎯 هدف 2: 102 | ⏳ در انتظار | 📈 سود/زیان: —" in text
    assert "🔢 تعداد: 12 | 📄 صفحه 1 از 2" in text


@pytest.mark.parametrize(
    ("status", "expected_text", "expected_button"),
    (
        (SignalStatus.OPEN.value, "🟢 وضعیت: باز", "🟢 #7"),
        (SignalStatus.CLOSED.value, "✅ وضعیت: بسته", "✅ #7"),
        (SignalStatus.CANCELLED.value, "🚫 وضعیت: لغوشده", "🚫 #7"),
    ),
)
def test_signal_status_emojis_are_consistent_in_text_and_buttons(
    status: str,
    expected_text: str,
    expected_button: str,
) -> None:
    text, keyboard = signals_user.render_signal_page(
        page(signal_record(status=status), mode=SignalListMode.LIVE.value)
    )

    assert expected_text in text
    assert expected_button in keyboard.inline_keyboard[0][0].text


def test_short_direction_and_cancelled_target_have_distinct_emojis() -> None:
    current = detail()
    cancelled_target = target_record(3, status=SignalTargetStatus.CANCELLED.value)
    current = replace(
        current,
        signal=replace(current.signal, direction=SignalDirection.SHORT.value),
        targets=(cancelled_target,),
        total_targets=1,
        total_target_pages=1,
    )

    text = signals_user.render_signal_detail(current, timezone_name="Asia/Tehran")

    assert "🟥 جهت: فروش (SHORT)" in text
    assert "🎯 هدف 3: 103 | 🚫 لغوشده | 📈 سود/زیان: —" in text


def test_decimal_formatter_never_removes_integer_zeroes() -> None:
    assert signals_user._format_decimal(Decimal("100")) == "100"
    assert signals_user._format_decimal(Decimal("110.000000")) == "110"
    assert signals_user._format_decimal(Decimal("0.001200")) == "0.0012"


def test_description_is_truncated_to_keep_telegram_detail_bounded() -> None:
    current = detail()
    long_description = "x" * 4000
    current = replace(
        current,
        signal=replace(current.signal, description=long_description),
        targets=(),
        total_targets=0,
        total_target_pages=1,
    )

    text = signals_user.render_signal_detail(current, timezone_name="UTC")

    assert long_description not in text
    assert "x" * 997 + "..." in text
    assert len(text) < 4096


def test_signal_keyboards_generate_only_exact_versioned_callbacks() -> None:
    list_keyboard = build_signal_list(
        [(7, "Signal")],
        mode="history",
        page=2,
        total_pages=3,
    )
    detail_keyboard = build_signal_detail_actions(
        7,
        mode="history",
        list_page=2,
        target_page=2,
        total_target_pages=3,
    )
    callbacks = [
        button.callback_data
        for keyboard in (list_keyboard, detail_keyboard)
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert all(callback is not None and len(callback.encode()) <= 64 for callback in callbacks)
    assert all(
        re.fullmatch(USER_SIGNAL_CALLBACK_PATTERN, callback)
        or re.fullmatch(FAVORITES_CALLBACK_PATTERN, callback)
        for callback in callbacks
    )


async def test_list_button_clears_support_state_checks_access_and_loads_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update()
    ctx = context(user_data={SUPPORT_USER_ACTION_KEY: {"action": "new_subject"}})
    database = object()
    access = AsyncMock(return_value=42)
    load = AsyncMock(return_value=page(signal_record(), mode=SignalListMode.LIVE.value))
    monkeypatch.setattr(signals_user, "_prepare_user_access", access)
    monkeypatch.setattr(signals_user, "get_database_manager", lambda value: database)
    monkeypatch.setattr(signals_user, "load_signal_page", load)

    await signals_user.live_signals_handler(current_update, ctx)

    assert SUPPORT_USER_ACTION_KEY not in ctx.user_data
    access.assert_awaited_once()
    load.assert_awaited_once_with(database, SignalListMode.LIVE.value, page=1)
    reply_text = current_update.effective_message.reply_text.await_args.args[0]
    assert "سیگنال‌های لحظه‌ای" in reply_text


async def test_missing_membership_stops_before_signal_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update()
    load = AsyncMock()
    monkeypatch.setattr(
        signals_user,
        "_prepare_user_access",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(signals_user, "load_signal_page", load)

    await signals_user.open_signals_handler(current_update, context())

    load.assert_not_awaited()
    current_update.effective_message.reply_text.assert_not_awaited()


async def test_list_callback_answers_once_and_edits_same_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update(callback_data="v1:signals:user:list:open:2")
    database = object()
    load = AsyncMock(
        return_value=SignalPage(
            signals=(signal_record(),),
            mode="open",
            page=2,
            page_size=10,
            total_items=11,
            total_pages=2,
        )
    )
    monkeypatch.setattr(
        signals_user,
        "_prepare_user_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(signals_user, "get_database_manager", lambda value: database)
    monkeypatch.setattr(signals_user, "load_signal_page", load)

    await signals_user.signal_callback_handler(current_update, context())

    current_update.callback_query.answer.assert_awaited_once_with("در حال پردازش...")
    load.assert_awaited_once_with(database, "open", page=2)
    current_update.callback_query.edit_message_text.assert_awaited_once()


async def test_detail_callback_loads_requested_target_page_and_return_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update(callback_data="v1:signals:user:view:history:3:7:2")
    database = object()
    monkeypatch.setattr(
        signals_user,
        "_prepare_user_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(signals_user, "get_database_manager", lambda value: database)
    load = AsyncMock(return_value=detail())
    monkeypatch.setattr(signals_user, "load_signal_detail", load)
    favorite_status = AsyncMock(return_value=True)
    monkeypatch.setattr(signals_user, "load_favorite_status", favorite_status)

    await signals_user.signal_callback_handler(current_update, context())

    load.assert_awaited_once_with(database, 7, target_page=2)
    favorite_status.assert_awaited_once_with(database, 42, 7)
    edit = current_update.callback_query.edit_message_text.await_args
    callbacks = [
        button.callback_data
        for row in edit.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks[-1] == "v1:signals:user:list:history:3"


async def test_duplicate_page_callback_is_harmless() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=BadRequest("Message is not modified"))
    )

    await signals_user._safe_edit_signal_message(query, "same")

    query.edit_message_text.assert_awaited_once()


async def test_menu_callback_restores_reply_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    current_update = update(callback_data="v1:signals:user:menu")
    monkeypatch.setattr(
        signals_user,
        "_prepare_user_access",
        AsyncMock(return_value=42),
    )

    await signals_user.signal_callback_handler(current_update, context())

    current_update.callback_query.edit_message_text.assert_awaited_once()
    reply = current_update.callback_query.message.reply_text
    reply.assert_awaited_once()
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == LIVE_SIGNALS_BUTTON


def test_registration_uses_one_anchored_signal_callback_handler() -> None:
    application = SimpleNamespace(add_handler=Mock())

    signals_user.register_signal_user_handlers(application)

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 7
    callback = handlers[-1]
    assert isinstance(callback, CallbackQueryHandler)
    assert callback.pattern.fullmatch("v1:signals:user:list:open:1")
    assert callback.pattern.fullmatch("v1:signals:user:view:live:1:7:1")
    assert callback.pattern.fullmatch("v1:signals:user:view:live:1:7:1:tampered") is None
