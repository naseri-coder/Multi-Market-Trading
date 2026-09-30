"""Telegram rendering, callbacks, and access tests for win-rate reports."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler

from app.bot.handlers import winrate_user
from app.bot.handlers.support_state import SUPPORT_USER_ACTION_KEY
from app.bot.keyboards.winrate import (
    WIN_RATE_BUTTON,
    WIN_RATE_CALLBACK_PATTERN,
    build_win_rate_period_menu,
    build_win_rate_report_actions,
)
from app.modules.analytics.entities import WinRateReport

NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


def report(*, populated: bool = False) -> WinRateReport:
    return WinRateReport(
        period="daily",
        window=timedelta(hours=24),
        started_at=NOW - timedelta(hours=24),
        ended_at=NOW,
        target_hit=2 if populated else 0,
        stop_hit=1 if populated else 0,
        evaluated_signals=3 if populated else 0,
        win_rate=Decimal("66.70") if populated else None,
        winning_trades=2 if populated else 0,
        losing_trades=1 if populated else 0,
        closed_trades=3 if populated else 0,
        gross_profit=Decimal("8") if populated else Decimal("0"),
        gross_loss=Decimal("-3") if populated else Decimal("0"),
        net_pnl=Decimal("5") if populated else Decimal("0"),
        average_win=Decimal("4") if populated else None,
        average_loss=Decimal("-3") if populated else None,
        profit_factor=Decimal("2.6667") if populated else None,
        expectancy=Decimal("1.6667") if populated else None,
        target_exits=1 if populated else 0,
        trailing_profit_exits=1 if populated else 0,
        stop_loss_exits=1 if populated else 0,
    )


def update(*, callback_data: str | None = None) -> SimpleNamespace:
    message = SimpleNamespace(text=WIN_RATE_BUTTON, reply_text=AsyncMock())
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
        update_id=77,
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


def test_period_menu_has_four_exact_report_callbacks() -> None:
    keyboard = build_win_rate_period_menu()
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert callbacks[:-1] == [
        "v1:winrate:user:report:daily",
        "v1:winrate:user:report:weekly",
        "v1:winrate:user:report:monthly",
        "v1:winrate:user:report:yearly",
    ]
    assert callbacks[-1] == "v1:winrate:user:menu"
    assert all(re.fullmatch(WIN_RATE_CALLBACK_PATTERN, item) for item in callbacks)


def test_report_actions_return_to_periods_or_main_menu() -> None:
    callbacks = [
        button.callback_data
        for row in build_win_rate_report_actions().inline_keyboard
        for button in row
    ]

    assert callbacks == ["v1:winrate:user:periods", "v1:winrate:user:menu"]


def test_empty_report_uses_na_instead_of_misleading_zero_percent() -> None:
    text = winrate_user.render_win_rate_report(
        report(),
        timezone_name="Asia/Tehran",
    )

    assert "📊 گزارش عملکرد معاملات" in text
    assert "🟢 سودده: 0" in text
    assert "🔴 زیان‌ده: 0" in text
    assert "🧮 کل معاملات بسته‌شده: 0" in text
    assert "🏆 نرخ برد: N/A" in text
    assert "سود یا زیان تحقق‌یافته نهایی" in text
    assert "هر معامله فقط یک‌بار در آمار محاسبه می‌شود" in text


def test_nonzero_report_formats_financial_metrics_and_exit_reasons() -> None:
    text = winrate_user.render_win_rate_report(
        report(populated=True),
        timezone_name="UTC",
    )

    assert "🏆 نرخ برد: 66.70%" in text
    assert "💵 خالص سود/زیان: +5.00%" in text
    assert "⚖️ ضریب سوددهی: 2.67" in text
    assert "🎯 بازده مورد انتظار هر معامله: +1.67%" in text
    assert "🔒 حد ضرر متحرک سودده: 1" in text
    assert "✅ خروج با هدف: 1" in text


def test_report_localizes_labels_and_places_each_metric_on_its_own_line() -> None:
    text = winrate_user.render_win_rate_report(
        report(populated=True),
        timezone_name="UTC",
    )
    lines = text.splitlines()
    metric_labels = (
        "🟢 سودده:",
        "🔴 زیان‌ده:",
        "⚪ سر‌به‌سر:",
        "⏳ باز:",
        "🧮 کل معاملات بسته‌شده:",
        "🏆 نرخ برد:",
        "📈 مجموع سود:",
        "📉 مجموع ضرر:",
        "💵 خالص سود/زیان:",
        "📊 میانگین سود معاملات سودده:",
        "📊 میانگین ضرر معاملات زیان‌ده:",
        "⚖️ ضریب سوددهی:",
        "🎯 بازده مورد انتظار هر معامله:",
        "🔥 بیشترین برد متوالی:",
        "❄️ بیشترین باخت متوالی:",
        "✅ خروج با هدف:",
        "🔒 حد ضرر متحرک سودده:",
        "🔻 حد ضرر متحرک زیان‌ده:",
        "🟢 حد ضرر سودده:",
        "🛑 حد ضرر زیان‌ده:",
        "⚪ خروج سر‌به‌سر:",
    )

    assert all(sum(label in line for label in metric_labels) <= 1 for line in lines)
    assert all(any(line.startswith(label) for line in lines) for label in metric_labels)
    for forbidden in (
        "Profit Factor",
        "Expectancy",
        "Target:",
        "Trailing Stop",
        "Stop سودده",
        "Stop زیان‌ده",
        "/ Trade",
        "امید ریاضی هر معامله",
    ):
        assert forbidden not in text


@pytest.mark.parametrize(
    ("expectancy", "expected"),
    (
        (Decimal("1.234"), "🎯 بازده مورد انتظار هر معامله: +1.23%"),
        (Decimal("-0.084"), "🎯 بازده مورد انتظار هر معامله: -0.08%"),
        (Decimal("0"), "🎯 بازده مورد انتظار هر معامله: 0.00%"),
    ),
)
def test_expectancy_value_is_unchanged_under_persian_label(
    expectancy: Decimal,
    expected: str,
) -> None:
    current = replace(report(populated=True), expectancy=expectancy)

    text = winrate_user.render_win_rate_report(current, timezone_name="UTC")

    assert expected in text


async def test_menu_clears_support_state_and_checks_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update()
    current_context = context(
        user_data={SUPPORT_USER_ACTION_KEY: {"action": "new_subject"}}
    )
    access = AsyncMock(return_value=True)
    monkeypatch.setattr(winrate_user, "_prepare_win_rate_access", access)

    await winrate_user.win_rate_menu_handler(current_update, current_context)

    assert SUPPORT_USER_ACTION_KEY not in current_context.user_data
    access.assert_awaited_once()
    reply = current_update.effective_message.reply_text
    reply.assert_awaited_once()
    assert "۲۴ ساعت اخیر" in reply.await_args.args[0]


async def test_failed_membership_stops_before_menu_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update()
    monkeypatch.setattr(
        winrate_user,
        "_prepare_win_rate_access",
        AsyncMock(return_value=False),
    )

    await winrate_user.win_rate_menu_handler(current_update, context())

    current_update.effective_message.reply_text.assert_not_awaited()


async def test_report_callback_loads_selected_period_and_edits_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update(callback_data="v1:winrate:user:report:daily")
    database = object()
    loader = AsyncMock(return_value=report())
    monkeypatch.setattr(
        winrate_user,
        "_prepare_win_rate_access",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(winrate_user, "get_database_manager", lambda value: database)
    monkeypatch.setattr(winrate_user, "load_win_rate_report", loader)

    await winrate_user.win_rate_callback_handler(current_update, context())

    current_update.callback_query.answer.assert_awaited_once()
    loader.assert_awaited_once_with(database, "daily")
    edit = current_update.callback_query.edit_message_text
    edit.assert_awaited_once()
    assert "🏆 نرخ برد: N/A" in edit.await_args.args[0]


async def test_periods_callback_does_not_query_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_update = update(callback_data="v1:winrate:user:periods")
    loader = AsyncMock()
    monkeypatch.setattr(
        winrate_user,
        "_prepare_win_rate_access",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(winrate_user, "load_win_rate_report", loader)

    await winrate_user.win_rate_callback_handler(current_update, context())

    loader.assert_not_awaited()
    assert "بازه زمانی" in (
        current_update.callback_query.edit_message_text.await_args.args[0]
    )


async def test_duplicate_callback_edit_is_harmless() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )
    )

    await winrate_user._safe_edit_win_rate_message(query, "same")

    query.edit_message_text.assert_awaited_once()


def test_registration_uses_one_anchored_callback_handler() -> None:
    application = SimpleNamespace(add_handler=Mock())

    winrate_user.register_win_rate_user_handlers(application)

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 3
    callback = handlers[-1]
    assert isinstance(callback, CallbackQueryHandler)
    assert callback.pattern.fullmatch("v1:winrate:user:report:yearly")
    assert callback.pattern.fullmatch("v1:winrate:user:report:yearly:tampered") is None
