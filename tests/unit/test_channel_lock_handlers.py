"""Unit tests for the user-facing multi-channel lock."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler

from app.bot.handlers import channel_lock
from app.bot.keyboards.channels import (
    VERIFY_MEMBERSHIP_CALLBACK,
    build_membership_keyboard,
)
from app.modules.channels.entities import ChannelMembershipResult, ChannelRecord
from app.modules.channels.errors import ChannelMembershipCheckError


def record(
    channel_id: int,
    *,
    username: str | None = "channelname",
    invite_link: str | None = None,
) -> ChannelRecord:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return ChannelRecord(
        id=channel_id,
        telegram_chat_id=-1000 - channel_id,
        username=username,
        title=f"Channel {channel_id}",
        invite_link=invite_link,
        is_active=True,
        sort_order=channel_id,
        created_at=timestamp,
        updated_at=timestamp,
    )


def fake_context(admin_ids: frozenset[int] = frozenset()) -> SimpleNamespace:
    return SimpleNamespace(
        bot=object(),
        application=SimpleNamespace(bot_data={"admin_ids": admin_ids, "database": object()}),
    )


def fake_update(*, with_query: bool = False) -> SimpleNamespace:
    message = SimpleNamespace(reply_text=AsyncMock())
    query = None
    if with_query:
        query = SimpleNamespace(
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123456789),
        effective_message=message,
        callback_query=query,
        update_id=500,
    )


def configure_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    result: ChannelMembershipResult | Exception,
) -> AsyncMock:
    load = AsyncMock(side_effect=result if isinstance(result, Exception) else None)
    if not isinstance(result, Exception):
        load.return_value = result
    monkeypatch.setattr(channel_lock, "load_membership_result", load)
    monkeypatch.setattr(channel_lock, "get_database_manager", lambda context: object())
    monkeypatch.setattr(
        channel_lock,
        "TelegramChannelGateway",
        lambda bot: SimpleNamespace(),
    )
    return load


def test_membership_keyboard_contains_all_missing_channels_and_exact_callback() -> None:
    public = record(1)
    private = record(2, username=None, invite_link="https://t.me/+private-token")

    keyboard = build_membership_keyboard((public, private))

    rows = keyboard.inline_keyboard
    assert rows[0][0].url == "https://t.me/channelname"
    assert rows[1][0].url == "https://t.me/+private-token"
    assert rows[2][0].callback_data == VERIFY_MEMBERSHIP_CALLBACK


async def test_membership_guard_allows_user_when_every_active_channel_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    configure_dependencies(monkeypatch, ChannelMembershipResult(True, 2, ()))

    assert await channel_lock.ensure_channel_membership(update, fake_context()) is True
    update.effective_message.reply_text.assert_not_awaited()


async def test_membership_guard_lists_every_missing_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    missing = (record(1), record(2))
    configure_dependencies(
        monkeypatch,
        ChannelMembershipResult(False, 3, missing),
    )

    assert await channel_lock.ensure_channel_membership(update, fake_context()) is False
    reply = update.effective_message.reply_text
    assert "Channel 1" in reply.await_args.args[0]
    assert "Channel 2" in reply.await_args.args[0]
    assert len(reply.await_args.kwargs["reply_markup"].inline_keyboard) == 3


async def test_membership_guard_fails_closed_on_check_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    configure_dependencies(
        monkeypatch,
        ChannelMembershipCheckError("Telegram unavailable"),
    )

    assert await channel_lock.ensure_channel_membership(update, fake_context()) is False
    assert "بررسی عضویت" in update.effective_message.reply_text.await_args.args[0]


async def test_administrator_bypasses_channel_lock_without_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update()
    database_accessor = AsyncMock()
    monkeypatch.setattr(channel_lock, "get_database_manager", database_accessor)

    allowed = await channel_lock.ensure_channel_membership(
        update,
        fake_context(frozenset({123456789})),
    )

    assert allowed is True
    database_accessor.assert_not_awaited()


async def test_verify_callback_confirms_membership_and_restores_user_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update(with_query=True)
    configure_dependencies(monkeypatch, ChannelMembershipResult(True, 2, ()))

    await channel_lock.verify_membership_handler(update, fake_context())

    query = update.callback_query
    query.edit_message_text.assert_awaited_once()
    assert "تأیید شد" in query.edit_message_text.await_args.args[0]
    query.answer.assert_awaited_once_with("در حال بررسی عضویت...")
    query.message.reply_text.assert_awaited_once()


async def test_verify_callback_keeps_join_buttons_for_missing_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update(with_query=True)
    missing = (record(1), record(2))
    configure_dependencies(
        monkeypatch,
        ChannelMembershipResult(False, 2, missing),
    )

    await channel_lock.verify_membership_handler(update, fake_context())

    query = update.callback_query
    assert len(query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard) == 3
    query.answer.assert_awaited_once_with("در حال بررسی عضویت...")
    query.message.reply_text.assert_not_awaited()


async def test_verify_callback_handles_unchanged_prompt_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update(with_query=True)
    configure_dependencies(
        monkeypatch,
        ChannelMembershipResult(False, 1, (record(1),)),
    )
    update.callback_query.edit_message_text.side_effect = BadRequest("Message is not modified")

    await channel_lock.verify_membership_handler(update, fake_context())

    update.callback_query.answer.assert_awaited_once()


async def test_verify_callback_answers_once_when_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update(with_query=True)
    configure_dependencies(
        monkeypatch,
        ChannelMembershipCheckError("Telegram unavailable"),
    )

    await channel_lock.verify_membership_handler(update, fake_context())

    update.callback_query.answer.assert_awaited_once()
    update.callback_query.message.reply_text.assert_awaited_once()
    update.callback_query.edit_message_text.assert_not_awaited()


def test_callback_handler_uses_exact_allow_listed_pattern() -> None:
    application = SimpleNamespace(add_handler=Mock())

    channel_lock.register_channel_lock_handlers(application)

    handler = application.add_handler.call_args.args[0]
    assert isinstance(handler, CallbackQueryHandler)
    assert handler.pattern.fullmatch(VERIFY_MEMBERSHIP_CALLBACK)
    assert handler.pattern.fullmatch(f"{VERIFY_MEMBERSHIP_CALLBACK}:tampered") is None
    assert handler.pattern.fullmatch("channel_lock:verify") is None
