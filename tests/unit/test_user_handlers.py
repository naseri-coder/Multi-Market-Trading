"""Unit tests for user presentation and Telegram handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import User as TelegramUser

from app.bot.handlers import users as user_handlers
from app.bot.keyboards.admin import ADMIN_PANEL_BUTTON
from app.bot.keyboards.favorites import FAVORITES_BUTTON
from app.bot.keyboards.notifications import NOTIFICATION_SETTINGS_BUTTON
from app.bot.keyboards.referrals import REFERRALS_BUTTON
from app.bot.keyboards.signals import (
    LIVE_SIGNALS_BUTTON,
    OPEN_SIGNALS_BUTTON,
    SIGNAL_HISTORY_BUTTON,
)
from app.bot.keyboards.support import SUPPORT_BUTTON
from app.bot.keyboards.user import PROFILE_BUTTON, build_user_menu
from app.bot.keyboards.winrate import WIN_RATE_BUTTON
from app.modules.users.entities import UserProfile, UserRegistrationResult


def profile() -> UserProfile:
    created_at = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    return UserProfile(
        id=7,
        telegram_user_id=123456789,
        username="sample_user",
        first_name="عباس",
        last_name="ناصری",
        language_code="fa",
        is_bot=False,
        status="ACTIVE",
        last_activity=datetime(2026, 9, 1, 9, 30, tzinfo=UTC),
        created_at=created_at,
        updated_at=created_at,
    )


def fake_update() -> SimpleNamespace:
    telegram_user = TelegramUser(
        id=123456789,
        first_name="عباس",
        is_bot=False,
        last_name="ناصری",
        username="sample_user",
        language_code="fa",
    )
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_user=telegram_user, effective_message=message)


def fake_context(admin_ids: frozenset[int] = frozenset()) -> SimpleNamespace:
    return SimpleNamespace(application=SimpleNamespace(bot_data={"admin_ids": admin_ids}))


def test_telegram_user_maps_to_domain_identity() -> None:
    update = fake_update()

    identity = user_handlers.telegram_user_to_identity(update.effective_user)

    assert identity.telegram_user_id == 123456789
    assert identity.first_name == "عباس"
    assert identity.username == "sample_user"


def test_profile_renderer_contains_expected_plain_text_fields() -> None:
    text = user_handlers.render_profile(profile())

    assert "عباس ناصری" in text
    assert "@sample_user" in text
    assert "123456789" in text
    assert "فعال" in text
    assert "2026-09-01 09:30 UTC" in text


def test_base_menu_contains_signals_preferences_and_reports() -> None:
    keyboard = build_user_menu()

    assert keyboard.keyboard[0][0].text == LIVE_SIGNALS_BUTTON
    assert keyboard.keyboard[1][0].text == OPEN_SIGNALS_BUTTON
    assert keyboard.keyboard[1][1].text == SIGNAL_HISTORY_BUTTON
    assert keyboard.keyboard[2][0].text == FAVORITES_BUTTON
    assert keyboard.keyboard[2][1].text == NOTIFICATION_SETTINGS_BUTTON
    assert keyboard.keyboard[3][0].text == WIN_RATE_BUTTON
    assert keyboard.keyboard[4][0].text == PROFILE_BUTTON
    assert keyboard.keyboard[4][1].text == SUPPORT_BUTTON
    assert keyboard.keyboard[5][0].text == REFERRALS_BUTTON
    assert keyboard.resize_keyboard is True
    assert keyboard.is_persistent is True


def test_base_menu_exposes_admin_entry_only_when_authorized() -> None:
    normal_keyboard = build_user_menu()
    admin_keyboard = build_user_menu(is_admin=True)

    assert all(
        button.text != ADMIN_PANEL_BUTTON for row in normal_keyboard.keyboard for button in row
    )
    assert normal_keyboard.keyboard[4][1].text == SUPPORT_BUTTON
    assert admin_keyboard.keyboard[6][0].text == ADMIN_PANEL_BUTTON


@pytest.mark.usefixtures("monkeypatch")
async def test_start_handler_shows_registration_message_for_new_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    result = UserRegistrationResult(profile=profile(), created=True)
    sync_mock = AsyncMock(return_value=result)
    monkeypatch.setattr(user_handlers, "get_database_manager", lambda context: object())
    monkeypatch.setattr(user_handlers, "sync_user", sync_mock)
    monkeypatch.setattr(
        user_handlers,
        "ensure_channel_membership",
        AsyncMock(return_value=True),
    )

    await user_handlers.start_handler(update, fake_context())

    reply = update.effective_message.reply_text
    reply.assert_awaited_once()
    assert "ثبت‌نام شما با موفقیت انجام شد" in reply.await_args.args[0]
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == LIVE_SIGNALS_BUTTON


async def test_start_handler_shows_update_message_for_existing_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    result = UserRegistrationResult(profile=profile(), created=False)
    monkeypatch.setattr(user_handlers, "get_database_manager", lambda context: object())
    monkeypatch.setattr(user_handlers, "sync_user", AsyncMock(return_value=result))
    monkeypatch.setattr(
        user_handlers,
        "ensure_channel_membership",
        AsyncMock(return_value=True),
    )

    await user_handlers.start_handler(update, fake_context())

    reply = update.effective_message.reply_text
    assert "آخرین فعالیت شما به‌روزرسانی شد" in reply.await_args.args[0]


async def test_profile_handler_displays_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    update = fake_update()
    result = UserRegistrationResult(profile=profile(), created=False)
    monkeypatch.setattr(user_handlers, "get_database_manager", lambda context: object())
    monkeypatch.setattr(user_handlers, "sync_user", AsyncMock(return_value=result))
    monkeypatch.setattr(
        user_handlers,
        "ensure_channel_membership",
        AsyncMock(return_value=True),
    )

    await user_handlers.profile_handler(update, fake_context())

    reply = update.effective_message.reply_text
    assert "👤 پروفایل من" in reply.await_args.args[0]
    assert "عباس ناصری" in reply.await_args.args[0]


async def test_start_handler_shows_admin_entry_for_configured_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    result = UserRegistrationResult(profile=profile(), created=False)
    monkeypatch.setattr(user_handlers, "get_database_manager", lambda context: object())
    monkeypatch.setattr(user_handlers, "sync_user", AsyncMock(return_value=result))

    await user_handlers.start_handler(update, fake_context(frozenset({123456789})))

    keyboard = update.effective_message.reply_text.await_args.kwargs["reply_markup"]
    assert keyboard.keyboard[4][1].text == SUPPORT_BUTTON
    assert keyboard.keyboard[5][0].text == REFERRALS_BUTTON
    assert keyboard.keyboard[6][0].text == ADMIN_PANEL_BUTTON


async def test_new_user_start_payload_applies_referral_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    result = UserRegistrationResult(profile=profile(), created=True)
    apply_referral = AsyncMock(return_value="🎉 معرف ثبت شد.")
    database = object()
    monkeypatch.setattr(
        user_handlers,
        "get_database_manager",
        lambda context: database,
    )
    monkeypatch.setattr(user_handlers, "sync_user", AsyncMock(return_value=result))
    monkeypatch.setattr(user_handlers, "_apply_start_referral", apply_referral)
    monkeypatch.setattr(
        user_handlers,
        "ensure_channel_membership",
        AsyncMock(return_value=True),
    )
    current_context = fake_context()
    current_context.args = ["ref_RABCDEFGHJKL"]

    await user_handlers.start_handler(update, current_context)

    apply_referral.assert_awaited_once_with(
        database,
        7,
        ["ref_RABCDEFGHJKL"],
    )
    assert "معرف ثبت شد" in update.effective_message.reply_text.await_args.args[0]


async def test_existing_user_cannot_apply_start_referral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    result = UserRegistrationResult(profile=profile(), created=False)
    apply_referral = AsyncMock()
    monkeypatch.setattr(user_handlers, "get_database_manager", lambda context: object())
    monkeypatch.setattr(user_handlers, "sync_user", AsyncMock(return_value=result))
    monkeypatch.setattr(user_handlers, "_apply_start_referral", apply_referral)
    monkeypatch.setattr(
        user_handlers,
        "ensure_channel_membership",
        AsyncMock(return_value=True),
    )
    current_context = fake_context()
    current_context.args = ["ref_RABCDEFGHJKL"]

    await user_handlers.start_handler(update, current_context)

    apply_referral.assert_not_awaited()


async def test_start_stops_before_menu_when_channel_membership_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    result = UserRegistrationResult(profile=profile(), created=False)
    membership = AsyncMock(return_value=False)
    monkeypatch.setattr(user_handlers, "get_database_manager", lambda context: object())
    monkeypatch.setattr(user_handlers, "sync_user", AsyncMock(return_value=result))
    monkeypatch.setattr(user_handlers, "ensure_channel_membership", membership)

    await user_handlers.start_handler(update, fake_context())

    membership.assert_awaited_once()
    update.effective_message.reply_text.assert_not_awaited()
