"""Guided administrator subscription workflow tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers import admin_subscriptions
from app.bot.handlers.admin_state import SUBSCRIPTION_ADMIN_ACTION_KEY
from app.bot.keyboards.subscriptions import SUBSCRIPTION_PLAN_CREATE_BUTTON
from app.modules.subscriptions.entities import SubscriptionPlanRecord

NOW = datetime(2026, 9, 2, 2, tzinfo=UTC)


def plan(plan_id: int, *, active: bool = True) -> SubscriptionPlanRecord:
    return SubscriptionPlanRecord(
        id=plan_id,
        name=f"VIP {plan_id}",
        duration_days=30,
        price=Decimal("10.00"),
        currency="USDT",
        description=None,
        is_active=active,
        created_at=NOW,
        updated_at=NOW,
    )


def update(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        effective_message=SimpleNamespace(text=text, reply_text=AsyncMock())
    )


def context() -> SimpleNamespace:
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"database": object()}),
    )


def test_plan_list_is_split_into_bounded_pages() -> None:
    pages = admin_subscriptions.render_plan_pages(
        tuple(plan(index) for index in range(1, 18))
    )

    assert len(pages) == 3
    assert pages[0].count("💎 پلن #") == 8
    assert pages[1].count("💎 پلن #") == 8
    assert pages[2].count("💎 پلن #") == 1


async def test_create_button_starts_guided_name_step() -> None:
    current_update = update(SUBSCRIPTION_PLAN_CREATE_BUTTON)
    current_context = context()

    await admin_subscriptions.subscription_instruction_handler(
        current_update,
        current_context,
    )

    state = current_context.user_data[SUBSCRIPTION_ADMIN_ACTION_KEY]
    assert state == {"action": "create", "step": "name", "data": {}}
    assert "نام پلن" in current_update.effective_message.reply_text.await_args.args[0]


async def test_guided_create_collects_five_inputs_and_clears_state(monkeypatch) -> None:
    current_context = context()
    current_update = update(SUBSCRIPTION_PLAN_CREATE_BUTTON)
    await admin_subscriptions.subscription_instruction_handler(
        current_update,
        current_context,
    )
    creator = AsyncMock(return_value=plan(9))
    monkeypatch.setattr(admin_subscriptions, "_create_plan", creator)
    monkeypatch.setattr(
        admin_subscriptions,
        "get_database_manager",
        lambda current: object(),
    )

    for value in ("VIP Gold", "30", "25.50", "usdt", "-"):
        current_update.effective_message.text = value
        await admin_subscriptions.subscription_admin_input_handler(
            current_update,
            current_context,
        )

    request = creator.await_args.args[1]
    assert request.name == "VIP Gold"
    assert request.duration_days == 30
    assert request.price == Decimal("25.50")
    assert request.currency == "usdt"
    assert request.description is None
    assert SUBSCRIPTION_ADMIN_ACTION_KEY not in current_context.user_data


async def test_invalid_guided_integer_keeps_current_step(monkeypatch) -> None:
    current_context = context()
    current_context.user_data[SUBSCRIPTION_ADMIN_ACTION_KEY] = {
        "action": "create",
        "step": "duration_days",
        "data": {"name": "VIP"},
    }
    current_update = update("not-a-number")
    monkeypatch.setattr(
        admin_subscriptions,
        "get_database_manager",
        lambda current: object(),
    )

    await admin_subscriptions.subscription_admin_input_handler(
        current_update,
        current_context,
    )

    state = current_context.user_data[SUBSCRIPTION_ADMIN_ACTION_KEY]
    assert state["step"] == "duration_days"
    assert "نامعتبر" in current_update.effective_message.reply_text.await_args.args[0]
