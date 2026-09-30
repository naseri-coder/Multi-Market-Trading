"""Tests for administrator channel management handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot.handlers import admin_channels
from app.bot.keyboards.channels import (
    CHANNEL_ADD_BUTTON,
    CHANNEL_ADMIN_BACK_BUTTON,
    CHANNEL_DELETE_BUTTON,
    CHANNEL_EDIT_BUTTON,
    CHANNEL_LIST_BUTTON,
    CHANNEL_MANAGEMENT_BUTTON,
    CHANNEL_TOGGLE_BUTTON,
)
from app.modules.channels.entities import ChannelRecord, ResolvedTelegramChannel


def record(channel_id: int = 1, *, is_active: bool = True) -> ChannelRecord:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return ChannelRecord(
        id=channel_id,
        telegram_chat_id=-1_001_234_567_890 - channel_id,
        username=f"channel{channel_id}",
        title=f"Channel {channel_id}",
        invite_link=None,
        is_active=is_active,
        sort_order=channel_id,
        created_at=timestamp,
        updated_at=timestamp,
    )


def fake_update(text: str = CHANNEL_MANAGEMENT_BUTTON) -> SimpleNamespace:
    return SimpleNamespace(
        effective_message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        update_id=77,
    )


def fake_context() -> SimpleNamespace:
    return SimpleNamespace(
        bot=object(),
        application=SimpleNamespace(bot_data={}),
        user_data={},
    )


async def test_channel_management_menu_exposes_crud_and_back_navigation() -> None:
    update = fake_update()

    await admin_channels.channel_management_handler(update, fake_context())

    keyboard = update.effective_message.reply_text.await_args.kwargs["reply_markup"]
    button_texts = {button.text for row in keyboard.keyboard for button in row}
    assert CHANNEL_LIST_BUTTON in button_texts
    assert CHANNEL_ADD_BUTTON in button_texts
    assert CHANNEL_ADMIN_BACK_BUTTON in button_texts


def test_channel_list_renderer_includes_ids_order_and_state() -> None:
    rendered = admin_channels.render_channel_list((record(1), record(2, is_active=False)))

    assert "ID: 1" in rendered
    assert "ID: 2" in rendered
    assert "فعال ✅" in rendered
    assert "غیرفعال ⏸" in rendered
    assert rendered.index("ID: 1") < rendered.index("ID: 2")


def test_large_channel_list_is_split_below_telegram_limit() -> None:
    channels = tuple(record(channel_id) for channel_id in range(1, 101))

    pages = admin_channels.render_channel_list_pages(channels)

    assert len(pages) > 1
    assert all(len(page) <= 3800 for page in pages)
    assert sum(page.count("Chat ID:") for page in pages) == 100


async def test_channel_list_handler_uses_repository_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update(CHANNEL_LIST_BUTTON)
    monkeypatch.setattr(admin_channels, "get_database_manager", lambda context: object())
    monkeypatch.setattr(
        admin_channels,
        "_list_channels",
        AsyncMock(return_value=(record(1), record(2))),
    )

    await admin_channels.channel_list_handler(update, fake_context())

    assert "Channel 1" in update.effective_message.reply_text.await_args.args[0]
    assert "Channel 2" in update.effective_message.reply_text.await_args.args[0]


async def test_channel_add_resolves_telegram_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update("/channel_add @publicchannel | - | 4")
    gateway = SimpleNamespace(
        resolve_channel=AsyncMock(
            return_value=ResolvedTelegramChannel(
                telegram_chat_id=-1_001_234_567_890,
                username="publicchannel",
                title="Public Channel",
                invite_link=None,
            )
        )
    )
    created = record(7)
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(admin_channels, "TelegramChannelGateway", lambda bot: gateway)
    monkeypatch.setattr(admin_channels, "get_database_manager", lambda context: object())
    monkeypatch.setattr(admin_channels, "_create_channel", create)

    await admin_channels.channel_add_handler(update, fake_context())

    gateway.resolve_channel.assert_awaited_once_with(
        "@publicchannel",
        supplied_invite_link=None,
    )
    submitted = create.await_args.args[1]
    assert submitted.telegram_chat_id == -1_001_234_567_890
    assert submitted.sort_order == 4
    assert "اضافه شد" in update.effective_message.reply_text.await_args.args[0]


async def test_channel_add_command_accepts_only_public_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update("/channel_add @publicchannel")
    create = AsyncMock(return_value=record(7))
    monkeypatch.setattr(admin_channels, "_resolve_and_create_channel", create)

    await admin_channels.channel_add_handler(update, fake_context())

    create.assert_awaited_once()
    assert create.await_args.kwargs == {
        "reference": "@publicchannel",
        "invite_link": None,
        "sort_order": 0,
    }


async def test_channel_edit_command_accepts_only_telegram_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update("/channel_edit @publicchannel")
    refresh = AsyncMock(return_value=record(7))
    monkeypatch.setattr(admin_channels, "_resolve_and_refresh_channel", refresh)

    await admin_channels.channel_edit_handler(update, fake_context())

    refresh.assert_awaited_once()
    assert refresh.await_args.kwargs["reference"] == "@publicchannel"
    assert "ویرایش شد" in update.effective_message.reply_text.await_args.args[0]


async def test_refresh_helper_accepts_positive_internal_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = fake_context()
    database = object()
    stored = record(7)
    resolved = ResolvedTelegramChannel(
        telegram_chat_id=stored.telegram_chat_id,
        username=stored.username,
        title=stored.title,
        invite_link=None,
    )
    gateway = SimpleNamespace(resolve_channel=AsyncMock(return_value=resolved))
    get_channel = AsyncMock(return_value=stored)
    refresh = AsyncMock(return_value=stored)
    monkeypatch.setattr(admin_channels, "get_database_manager", lambda context: database)
    monkeypatch.setattr(admin_channels, "_get_channel", get_channel)
    monkeypatch.setattr(admin_channels, "_refresh_channel", refresh)
    monkeypatch.setattr(admin_channels, "TelegramChannelGateway", lambda bot: gateway)

    result = await admin_channels._resolve_and_refresh_channel(context, reference="7")

    assert result == stored
    get_channel.assert_awaited_once_with(database, 7)
    gateway.resolve_channel.assert_awaited_once_with(str(stored.telegram_chat_id))
    refresh.assert_awaited_once_with(database, resolved)


async def test_channel_delete_accepts_only_internal_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update("/channel_delete 7")
    delete = AsyncMock()
    database = object()
    monkeypatch.setattr(admin_channels, "get_database_manager", lambda context: database)
    monkeypatch.setattr(admin_channels, "_delete_channel", delete)

    await admin_channels.channel_delete_handler(update, fake_context())

    delete.assert_awaited_once_with(database, 7)
    assert "حذف شد" in update.effective_message.reply_text.await_args.args[0]


async def test_add_button_then_plain_username_creates_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = fake_context()
    instruction = fake_update(CHANNEL_ADD_BUTTON)
    create = AsyncMock(return_value=record(7))
    monkeypatch.setattr(admin_channels, "_resolve_and_create_channel", create)

    await admin_channels.channel_instruction_handler(instruction, context)
    assert "@channelname" in instruction.effective_message.reply_text.await_args.args[0]

    value_update = fake_update("@publicchannel")
    await admin_channels.channel_pending_input_handler(value_update, context)

    create.assert_awaited_once_with(context, reference="@publicchannel")
    assert "اضافه شد" in value_update.effective_message.reply_text.await_args.args[0]
    assert context.user_data == {}


async def test_delete_button_then_plain_id_deletes_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = fake_context()
    database = object()
    delete = AsyncMock()
    monkeypatch.setattr(admin_channels, "get_database_manager", lambda context: database)
    monkeypatch.setattr(admin_channels, "_delete_channel", delete)

    instruction = fake_update(CHANNEL_DELETE_BUTTON)
    await admin_channels.channel_instruction_handler(instruction, context)
    assert "ID داخلی" in instruction.effective_message.reply_text.await_args.args[0]

    value_update = fake_update("7")
    await admin_channels.channel_pending_input_handler(value_update, context)

    delete.assert_awaited_once_with(database, 7)
    assert "حذف شد" in value_update.effective_message.reply_text.await_args.args[0]
    assert context.user_data == {}


async def test_edit_button_then_plain_reference_refreshes_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = fake_context()
    refresh = AsyncMock(return_value=record(7))
    monkeypatch.setattr(admin_channels, "_resolve_and_refresh_channel", refresh)

    instruction = fake_update(CHANNEL_EDIT_BUTTON)
    await admin_channels.channel_instruction_handler(instruction, context)
    assert "@username" in instruction.effective_message.reply_text.await_args.args[0]

    value_update = fake_update("@publicchannel")
    await admin_channels.channel_pending_input_handler(value_update, context)

    refresh.assert_awaited_once_with(context, reference="@publicchannel")
    assert "به‌روزرسانی شد" in value_update.effective_message.reply_text.await_args.args[0]
    assert context.user_data == {}


async def test_toggle_button_then_plain_id_changes_channel_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = fake_context()
    database = object()
    toggle = AsyncMock(return_value=record(7, is_active=False))
    monkeypatch.setattr(admin_channels, "get_database_manager", lambda context: database)
    monkeypatch.setattr(admin_channels, "_toggle_channel", toggle)

    await admin_channels.channel_instruction_handler(
        fake_update(CHANNEL_TOGGLE_BUTTON),
        context,
    )
    value_update = fake_update("7")
    await admin_channels.channel_pending_input_handler(value_update, context)

    toggle.assert_awaited_once_with(database, 7)
    assert "غیرفعال شد" in value_update.effective_message.reply_text.await_args.args[0]


async def test_channel_toggle_rejects_non_positive_internal_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = fake_update("/channel_toggle 0")
    toggle = AsyncMock()
    monkeypatch.setattr(admin_channels, "get_database_manager", lambda context: object())
    monkeypatch.setattr(admin_channels, "_toggle_channel", toggle)

    await admin_channels.channel_toggle_handler(update, fake_context())

    toggle.assert_not_awaited()
    assert "نامعتبر" in update.effective_message.reply_text.await_args.args[0]


def test_registration_adds_nine_admin_guarded_channel_routes() -> None:
    application = SimpleNamespace(add_handler=Mock())

    admin_channels.register_admin_channel_handlers(application, {123456789})

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 9
    assert all(hasattr(handler.callback, "__wrapped__") for handler in handlers)
