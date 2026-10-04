"""Administrator panel and navigation tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers.admins import admin_back_handler, admin_panel_handler
from app.bot.keyboards.admin import (
    ADMIN_BACK_BUTTON,
    ADMIN_DASHBOARD_BUTTON,
    ADMIN_PANEL_BUTTON,
)
from app.bot.keyboards.broadcasts import BROADCAST_MANAGEMENT_BUTTON
from app.bot.keyboards.channels import CHANNEL_MANAGEMENT_BUTTON
from app.bot.keyboards.favorites import FAVORITES_BUTTON
from app.bot.keyboards.forward_broadcasts import FORWARD_BROADCAST_MANAGEMENT_BUTTON
from app.bot.keyboards.notifications import NOTIFICATION_SETTINGS_BUTTON
from app.bot.keyboards.referrals import REFERRALS_BUTTON
from app.bot.keyboards.admin_signals import SIGNAL_MANAGEMENT_BUTTON
from app.bot.keyboards.signals import LIVE_SIGNALS_BUTTON
from app.bot.keyboards.support import ADMIN_SUPPORT_BUTTON, SUPPORT_BUTTON
from app.bot.keyboards.strategy_management import STRATEGY_MANAGEMENT_BUTTON
from app.bot.keyboards.subscriptions import (
    SUBSCRIPTION_MANAGEMENT_BUTTON,
    SUBSCRIPTION_STATUS_BUTTON,
)
from app.bot.keyboards.user import PROFILE_BUTTON
from app.bot.keyboards.winrate import WIN_RATE_BUTTON


def fake_update() -> SimpleNamespace:
    return SimpleNamespace(effective_message=SimpleNamespace(reply_text=AsyncMock()))


async def test_admin_panel_exposes_dashboard_channel_management_and_back_navigation() -> None:
    update = fake_update()

    await admin_panel_handler(update, SimpleNamespace())

    reply = update.effective_message.reply_text
    assert "پنل مدیریت" in reply.await_args.args[0]
    keyboard = reply.await_args.kwargs["reply_markup"]
    assert len(keyboard.keyboard) == 9
    assert keyboard.keyboard[0][0].text == ADMIN_DASHBOARD_BUTTON
    assert keyboard.keyboard[1][0].text == BROADCAST_MANAGEMENT_BUTTON
    assert keyboard.keyboard[2][0].text == FORWARD_BROADCAST_MANAGEMENT_BUTTON
    assert keyboard.keyboard[3][0].text == ADMIN_SUPPORT_BUTTON
    assert keyboard.keyboard[4][0].text == CHANNEL_MANAGEMENT_BUTTON
    assert keyboard.keyboard[5][0].text == SIGNAL_MANAGEMENT_BUTTON
    assert keyboard.keyboard[6][0].text == STRATEGY_MANAGEMENT_BUTTON
    assert keyboard.keyboard[7][0].text == SUBSCRIPTION_MANAGEMENT_BUTTON
    assert keyboard.keyboard[8][0].text == ADMIN_BACK_BUTTON


async def test_admin_back_navigation_restores_authorized_user_menu() -> None:
    update = fake_update()

    await admin_back_handler(update, SimpleNamespace())

    keyboard = update.effective_message.reply_text.await_args.kwargs["reply_markup"]
    assert keyboard.keyboard[0][0].text == LIVE_SIGNALS_BUTTON
    assert keyboard.keyboard[2][0].text == FAVORITES_BUTTON
    assert keyboard.keyboard[2][1].text == NOTIFICATION_SETTINGS_BUTTON
    assert keyboard.keyboard[3][0].text == WIN_RATE_BUTTON
    assert keyboard.keyboard[3][1].text == SUBSCRIPTION_STATUS_BUTTON
    assert keyboard.keyboard[4][0].text == PROFILE_BUTTON
    assert keyboard.keyboard[4][1].text == SUPPORT_BUTTON
    assert keyboard.keyboard[5][0].text == REFERRALS_BUTTON
    assert keyboard.keyboard[6][0].text == ADMIN_PANEL_BUTTON
