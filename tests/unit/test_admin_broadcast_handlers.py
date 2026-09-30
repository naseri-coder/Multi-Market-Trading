"""Administrator broadcast workflow and callback-security tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot.handlers import admin_broadcasts
from app.bot.handlers.admin_input import admin_input_router
from app.bot.handlers.admin_state import BROADCAST_ACTION_KEY, CHANNEL_ACTION_KEY
from app.bot.keyboards.broadcasts import (
    BROADCAST_CALLBACK_PATTERN,
    BROADCAST_CANCEL_PREFIX,
    BROADCAST_CONFIRM_PREFIX,
)
from app.modules.broadcasts.entities import BroadcastRecord
from app.modules.broadcasts.errors import BroadcastDeliveryError, InvalidBroadcastError
from app.modules.broadcasts.models import (
    BroadcastContentType,
    BroadcastMediaType,
    BroadcastStatus,
)


def record(*, status: str = BroadcastStatus.DRAFT.value) -> BroadcastRecord:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return BroadcastRecord(
        id=7,
        created_by_telegram_user_id=123456789,
        content_type=BroadcastContentType.TEXT.value,
        text="Announcement",
        media_type=None,
        media_file_id=None,
        caption=None,
        status=status,
        total_recipients=2,
        sent_count=0,
        failed_count=0,
        blocked_count=0,
        confirmed_at=None,
        completed_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def message(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "text": None,
        "caption": None,
        "photo": (),
        "video": None,
        "document": None,
        "animation": None,
        "audio": None,
        "voice": None,
        "forward_origin": None,
        "reply_text": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def context(*, user_data: dict[str, object] | None = None) -> SimpleNamespace:
    application = SimpleNamespace(bot_data={}, create_task=Mock())
    return SimpleNamespace(
        user_data={} if user_data is None else user_data,
        bot=SimpleNamespace(),
        application=application,
    )


def update(msg: SimpleNamespace | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        effective_message=msg or message(),
        effective_user=SimpleNamespace(id=123456789),
        callback_query=None,
        update_id=8,
    )


def test_original_text_and_photo_are_extracted_without_forwarding() -> None:
    text = admin_broadcasts.extract_broadcast_content(message(text="Announcement"), 123)
    photo = admin_broadcasts.extract_broadcast_content(
        message(
            photo=(SimpleNamespace(file_id="small"), SimpleNamespace(file_id="large")),
            caption="Caption",
        ),
        123,
    )

    assert text.content_type == BroadcastContentType.TEXT.value
    assert text.text == "Announcement"
    assert photo.content_type == BroadcastContentType.MEDIA.value
    assert photo.media_type == BroadcastMediaType.PHOTO.value
    assert photo.media_file_id == "large"
    assert photo.caption == "Caption"


def test_forwarded_and_unsupported_messages_use_separate_workflow() -> None:
    with pytest.raises(InvalidBroadcastError, match="separate Forward"):
        admin_broadcasts.extract_broadcast_content(
            message(text="Forward", forward_origin=object()),
            123,
        )
    with pytest.raises(InvalidBroadcastError, match="Only text"):
        admin_broadcasts.extract_broadcast_content(message(), 123)


async def test_start_enters_input_mode_and_cancel_clears_it() -> None:
    ctx = context(user_data={CHANNEL_ACTION_KEY: "old"})
    current_update = update(message())

    await admin_broadcasts.broadcast_start_handler(current_update, ctx)

    assert ctx.user_data == {BROADCAST_ACTION_KEY: "awaiting_content"}
    assert "Forward" in current_update.effective_message.reply_text.await_args.args[0]

    await admin_broadcasts.broadcast_input_cancel_handler(current_update, ctx)
    assert ctx.user_data == {}


async def test_content_creates_draft_previews_and_requests_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_message = message(text="Announcement")
    current_update = update(current_message)
    ctx = context(user_data={BROADCAST_ACTION_KEY: "awaiting_content"})
    gateway = SimpleNamespace(send=AsyncMock())
    monkeypatch.setattr(admin_broadcasts, "get_database_manager", lambda value: object())
    monkeypatch.setattr(admin_broadcasts, "_create_draft", AsyncMock(return_value=record()))
    monkeypatch.setattr(
        admin_broadcasts,
        "TelegramBroadcastGateway",
        lambda value: gateway,
    )

    await admin_broadcasts.broadcast_content_input_handler(current_update, ctx)

    gateway.send.assert_awaited_once_with(123456789, record())
    assert ctx.user_data == {}
    confirmation = current_message.reply_text.await_args_list[-1]
    assert "#7" in confirmation.args[0]
    callbacks = [
        button.callback_data
        for row in confirmation.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == [f"{BROADCAST_CONFIRM_PREFIX}7", f"{BROADCAST_CANCEL_PREFIX}7"]


async def test_preview_failure_cancels_draft_and_keeps_input_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_message = message(text="Announcement")
    current_update = update(current_message)
    ctx = context(user_data={BROADCAST_ACTION_KEY: "awaiting_content"})
    cancel = AsyncMock(return_value=record(status=BroadcastStatus.CANCELLED.value))
    gateway = SimpleNamespace(send=AsyncMock(side_effect=BroadcastDeliveryError()))
    monkeypatch.setattr(admin_broadcasts, "get_database_manager", lambda value: object())
    monkeypatch.setattr(admin_broadcasts, "_create_draft", AsyncMock(return_value=record()))
    monkeypatch.setattr(admin_broadcasts, "_cancel_draft", cancel)
    monkeypatch.setattr(admin_broadcasts, "TelegramBroadcastGateway", lambda value: gateway)

    await admin_broadcasts.broadcast_content_input_handler(current_update, ctx)

    cancel.assert_awaited_once()
    assert ctx.user_data == {BROADCAST_ACTION_KEY: "awaiting_content"}
    assert "معتبر نیست" in current_message.reply_text.await_args_list[-1].args[0]


async def test_confirmation_claims_exact_draft_and_schedules_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = SimpleNamespace(
        data=f"{BROADCAST_CONFIRM_PREFIX}7",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    current_update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123456789),
        update_id=9,
    )
    ctx = context()
    scheduled: list[object] = []

    def capture_task(coroutine: object, **kwargs: object) -> None:
        scheduled.append(coroutine)
        coroutine.close()  # type: ignore[attr-defined]

    ctx.application.create_task.side_effect = capture_task
    confirm = AsyncMock(return_value=record(status=BroadcastStatus.PROCESSING.value))
    database = object()
    monkeypatch.setattr(admin_broadcasts, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_broadcasts, "_confirm_draft", confirm)

    await admin_broadcasts.broadcast_callback_handler(current_update, ctx)

    confirm.assert_awaited_once_with(database, 7, 123456789)
    assert "2 کاربر" in query.edit_message_text.await_args.args[0]
    assert len(scheduled) == 1


@pytest.mark.parametrize(
    "callback",
    [
        "v1:broadcast:confirm:0",
        "v1:broadcast:confirm:-1",
        "v1:broadcast:confirm:7:extra",
        "v2:broadcast:confirm:7",
        "v1:broadcast:delete:7",
        "v1:broadcast:confirm:not-a-number",
    ],
)
def test_callback_pattern_rejects_tampered_payloads(callback: str) -> None:
    assert re.fullmatch(BROADCAST_CALLBACK_PATTERN, callback) is None


def test_registration_adds_four_guarded_broadcast_routes() -> None:
    application = SimpleNamespace(add_handler=Mock())

    admin_broadcasts.register_admin_broadcast_handlers(application, {123456789})

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 4
    assert all(hasattr(handler.callback, "__wrapped__") for handler in handlers)


async def test_unified_admin_input_router_prefers_selected_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel_handler = AsyncMock()
    broadcast_handler = AsyncMock()
    monkeypatch.setattr(
        "app.bot.handlers.admin_input.channel_pending_input_handler",
        channel_handler,
    )
    monkeypatch.setattr(
        "app.bot.handlers.admin_input.broadcast_content_input_handler",
        broadcast_handler,
    )
    current_update = update(message(text="value"))
    ctx = context(user_data={BROADCAST_ACTION_KEY: "awaiting_content"})

    await admin_input_router(current_update, ctx)

    broadcast_handler.assert_awaited_once_with(current_update, ctx)
    channel_handler.assert_not_awaited()
