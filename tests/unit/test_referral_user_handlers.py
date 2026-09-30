"""Referral Telegram rendering, callback, and registration tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler

from app.bot.handlers import referrals_user
from app.bot.keyboards.referrals import (
    REFERRALS_CALLBACK_PATTERN,
    build_invited_users_page,
    build_referral_dashboard,
)
from app.modules.referrals.entities import (
    InvitedUserRecord,
    InvitedUsersPage,
    ReferralDashboard,
    ReferralStatistics,
)

NOW = datetime(2026, 9, 2, 4, 30, tzinfo=UTC)


def dashboard() -> ReferralDashboard:
    return ReferralDashboard(
        referral_code="RABCDEFGHJKL",
        statistics=ReferralStatistics(
            total_invited=12,
            active_invited=10,
            inactive_invited=2,
        ),
    )


def page(*, current: int = 1, total_pages: int = 2) -> InvitedUsersPage:
    return InvitedUsersPage(
        users=(
            InvitedUserRecord(
                user_id=2,
                username="invited_user",
                first_name="کاربر",
                last_name="دعوت‌شده",
                status="ACTIVE",
                invited_at=NOW,
            ),
        ),
        page=current,
        page_size=10,
        total_items=12,
        total_pages=total_pages,
    )


def update(callback_data: str | None = None) -> SimpleNamespace:
    message = SimpleNamespace(reply_text=AsyncMock())
    query = None
    if callback_data is not None:
        query = SimpleNamespace(
            data=callback_data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123456789),
        effective_message=message,
        callback_query=query,
    )


def context() -> SimpleNamespace:
    return SimpleNamespace(
        user_data={},
        bot=SimpleNamespace(username="signal_crypto_bot"),
        application=SimpleNamespace(
            bot_data={
                "database": object(),
                "admin_ids": frozenset(),
            }
        ),
    )


def test_referral_callbacks_are_anchored_bounded_and_tamper_resistant() -> None:
    valid = (
        "v1:referrals:user:menu",
        "v1:referrals:user:dashboard",
        "v1:referrals:user:list:2",
    )
    assert all(re.fullmatch(REFERRALS_CALLBACK_PATTERN, item) for item in valid)
    assert re.fullmatch(REFERRALS_CALLBACK_PATTERN, f"{valid[-1]}:x") is None
    assert re.fullmatch(REFERRALS_CALLBACK_PATTERN, "v1:referrals:user:list:0") is None
    assert all(len(item.encode()) <= 64 for item in valid)


def test_referral_rendering_shows_link_statistics_and_disabled_rewards() -> None:
    text = referrals_user.render_referral_dashboard(
        dashboard(),
        bot_username="signal_crypto_bot",
    )
    invited_text = referrals_user.render_invited_users_page(page())

    assert "https://t.me/signal_crypto_bot?start=ref_RABCDEFGHJKL" in text
    assert "مجموع دعوت‌شده‌ها: 12" in text
    assert "پاداش" in text and "غیرفعال" in text
    assert "کاربر دعوت‌شده" in invited_text
    assert "@invited_user" in invited_text
    assert "123456789" not in invited_text


def test_referral_keyboards_include_pagination_and_both_back_paths() -> None:
    main = build_referral_dashboard()
    listing = build_invited_users_page(page=2, total_pages=3)
    main_callbacks = [
        item.callback_data for row in main.inline_keyboard for item in row
    ]
    list_callbacks = [
        item.callback_data for row in listing.inline_keyboard for item in row
    ]

    assert "v1:referrals:user:list:1" in main_callbacks
    assert "v1:referrals:user:menu" in main_callbacks
    assert "v1:referrals:user:list:1" in list_callbacks
    assert "v1:referrals:user:list:3" in list_callbacks
    assert "v1:referrals:user:dashboard" in list_callbacks
    assert "v1:referrals:user:menu" in list_callbacks


async def test_menu_loads_dashboard_and_real_bot_username(monkeypatch) -> None:
    current_update = update()
    current_context = context()
    database = object()
    loader = AsyncMock(return_value=dashboard())
    monkeypatch.setattr(
        referrals_user,
        "_prepare_referral_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(
        referrals_user,
        "get_database_manager",
        lambda value: database,
    )
    monkeypatch.setattr(referrals_user, "load_referral_dashboard", loader)

    await referrals_user.referrals_menu_handler(current_update, current_context)

    loader.assert_awaited_once_with(database, 42)
    reply = current_update.effective_message.reply_text
    assert "signal_crypto_bot" in reply.await_args.args[0]
    assert reply.await_args.kwargs["disable_web_page_preview"] is True


async def test_list_callback_edits_same_message_with_requested_page(monkeypatch) -> None:
    current_update = update("v1:referrals:user:list:2")
    database = object()
    loader = AsyncMock(return_value=page(current=2))
    monkeypatch.setattr(
        referrals_user,
        "_prepare_referral_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(
        referrals_user,
        "get_database_manager",
        lambda value: database,
    )
    monkeypatch.setattr(referrals_user, "load_invited_users_page", loader)

    await referrals_user.referrals_callback_handler(current_update, context())

    current_update.callback_query.answer.assert_awaited_once()
    loader.assert_awaited_once_with(database, 42, page=2)
    current_update.callback_query.edit_message_text.assert_awaited_once()


async def test_duplicate_callback_edit_is_harmless() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )
    )

    await referrals_user._safe_edit_referral_message(query, "same")

    query.edit_message_text.assert_awaited_once()


def test_registration_uses_one_anchored_referral_callback_handler() -> None:
    application = SimpleNamespace(add_handler=Mock())

    referrals_user.register_referrals_user_handlers(application)

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 3
    callback = handlers[-1]
    assert isinstance(callback, CallbackQueryHandler)
    assert callback.pattern.fullmatch("v1:referrals:user:list:1")
    assert callback.pattern.fullmatch("v1:referrals:user:list:1:x") is None
