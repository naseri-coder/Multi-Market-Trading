"""Tests for administrator user-statistics presentation."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import admin_statistics as statistics_handler
from app.bot.keyboards.admin import ADMIN_DASHBOARD_BUTTON
from app.modules.users.entities import UserStatistics
from app.modules.users.errors import UserStatisticsRepositoryError


def statistics() -> UserStatistics:
    return UserStatistics(
        total_users=100,
        active_users=61,
        inactive_users=39,
        new_users_today=3,
        new_users_this_week=12,
        new_users_this_month=44,
        active_window_days=30,
        report_timezone="Asia/Tehran",
        generated_at=datetime(2026, 9, 16, 8, 30, tzinfo=UTC),
    )


def fake_update() -> SimpleNamespace:
    return SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
        update_id=88,
    )


def test_dashboard_renderer_contains_every_required_statistic() -> None:
    text = statistics_handler.render_user_statistics(statistics())

    assert "کل کاربران: 100" in text
    assert "فعال (30 روز اخیر): 61" in text
    assert "غیرفعال: 39" in text
    assert "امروز: 3" in text
    assert "این هفته: 12" in text
    assert "این ماه: 44" in text
    assert "Asia/Tehran" in text


async def test_dashboard_handler_displays_service_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    load_mock = AsyncMock(return_value=statistics())
    database = object()
    monkeypatch.setattr(statistics_handler, "get_database_manager", lambda context: database)
    monkeypatch.setattr(
        statistics_handler,
        "get_report_timezone",
        lambda context: "Asia/Tehran",
    )
    monkeypatch.setattr(statistics_handler, "load_user_statistics", load_mock)

    await statistics_handler.admin_dashboard_handler(update, SimpleNamespace())

    load_mock.assert_awaited_once_with(database, timezone_name="Asia/Tehran")
    reply = update.effective_message.reply_text
    assert "کل کاربران: 100" in reply.await_args.args[0]
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == (ADMIN_DASHBOARD_BUTTON)


async def test_dashboard_handler_returns_safe_error_for_database_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    monkeypatch.setattr(statistics_handler, "get_database_manager", lambda context: object())
    monkeypatch.setattr(
        statistics_handler,
        "get_report_timezone",
        lambda context: "Asia/Tehran",
    )
    monkeypatch.setattr(
        statistics_handler,
        "load_user_statistics",
        AsyncMock(side_effect=UserStatisticsRepositoryError("sensitive database detail")),
    )

    await statistics_handler.admin_dashboard_handler(update, SimpleNamespace())

    reply_text = update.effective_message.reply_text.await_args.args[0]
    assert "دریافت آمار کاربران ممکن نیست" in reply_text
    assert "sensitive database detail" not in reply_text
