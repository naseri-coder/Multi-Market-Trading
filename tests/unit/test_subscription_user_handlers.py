"""User subscription-status Telegram adapter tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers import subscriptions_user
from app.modules.subscriptions.entities import SubscriptionRecord

NOW = datetime(2026, 9, 2, 2, tzinfo=UTC)


def active_subscription() -> SubscriptionRecord:
    return SubscriptionRecord(
        id=10,
        user_id=7,
        plan_id=3,
        status="ACTIVE",
        starts_at=NOW,
        expires_at=NOW + timedelta(days=30),
        ended_at=None,
        plan_name="VIP Monthly",
        duration_days=30,
        price=Decimal("19.50"),
        currency="USDT",
        created_at=NOW,
        updated_at=NOW,
    )


def context() -> SimpleNamespace:
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "database": object(),
                "admin_ids": frozenset(),
                "report_timezone": "Asia/Tehran",
            }
        ),
    )


def update() -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123456789,
            username="phase17",
            first_name="Phase",
            last_name="Seventeen",
            language_code="fa",
            is_bot=False,
        ),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )


def test_active_status_renderer_is_clear_and_includes_remaining_days() -> None:
    text = subscriptions_user.render_subscription_status(
        active_subscription(),
        now=NOW,
        timezone_name="Asia/Tehran",
    )

    assert "وضعیت: فعال ✅" in text
    assert "پلن: VIP Monthly" in text
    assert "زمان باقی‌مانده: 30 روز" in text
    assert "2026-09-02 05:30" in text


def test_free_status_renderer_does_not_claim_payment_support() -> None:
    text = subscriptions_user.render_subscription_status(
        None,
        now=NOW,
        timezone_name="Asia/Tehran",
    )

    assert "بدون اشتراک فعال" in text
    assert "توسط مدیریت" in text
    assert "پرداخت" not in text


async def test_status_handler_syncs_user_and_loads_subscription(monkeypatch) -> None:
    current_update = update()
    database = object()
    sync_result = SimpleNamespace(profile=SimpleNamespace(id=7))
    monkeypatch.setattr(
        subscriptions_user,
        "ensure_channel_membership",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        subscriptions_user,
        "get_database_manager",
        lambda current: database,
    )
    sync = AsyncMock(return_value=sync_result)
    load = AsyncMock(return_value=active_subscription())
    monkeypatch.setattr(subscriptions_user, "sync_user", sync)
    monkeypatch.setattr(subscriptions_user, "load_user_subscription", load)

    await subscriptions_user.subscription_status_handler(
        current_update,
        context(),
    )

    load.assert_awaited_once_with(database, 7)
    reply = current_update.effective_message.reply_text
    assert "وضعیت: فعال ✅" in reply.await_args.args[0]


async def test_membership_failure_stops_before_database_work(monkeypatch) -> None:
    current_update = update()
    sync = AsyncMock()
    monkeypatch.setattr(
        subscriptions_user,
        "ensure_channel_membership",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(subscriptions_user, "sync_user", sync)

    await subscriptions_user.subscription_status_handler(
        current_update,
        context(),
    )

    sync.assert_not_awaited()
    current_update.effective_message.reply_text.assert_not_awaited()
