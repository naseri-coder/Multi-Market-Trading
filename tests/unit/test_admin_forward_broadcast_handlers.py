"""Administrator forwarded-broadcast workflow and callback-security tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot.handlers import admin_forward_broadcasts
from app.bot.handlers.admin_input import admin_input_router
from app.bot.handlers.admin_state import (
    BROADCAST_ACTION_KEY,
    FORWARD_BROADCAST_ACTION_KEY,
)
from app.bot.keyboards.forward_broadcasts import (
    FORWARD_BROADCAST_CALLBACK_PATTERN,
    FORWARD_BROADCAST_CANCEL_PREFIX,
    FORWARD_BROADCAST_CONFIRM_PREFIX,
)
from app.modules.broadcasts.entities import BroadcastRecord
from app.modules.broadcasts.errors import BroadcastDeliveryError, InvalidBroadcastError
from app.modules.broadcasts.models import BroadcastContentType, BroadcastStatus


def record(*, status: str = BroadcastStatus.DRAFT.value) -> BroadcastRecord:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return BroadcastRecord(
        id=9,
        created_by_telegram_user_id=123456789,
        content_type=BroadcastContentType.FORWARD.value,
        text=None,
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
        source_chat_id=123456789,
        source_message_id=55,
    )


def message(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "chat_id": 123456789,
        "message_id": 55,
        "forward_origin": object(),
        "has_protected_content": False,
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
        update_id=10,
    )


def test_forward_source_references_received_admin_message() -> None:
    draft = admin_forward_broadcasts.extract_forward_broadcast(message(), 123456789)

    assert draft.content_type == BroadcastContentType.FORWARD.value
    assert draft.created_by_telegram_user_id == 123456789
    assert draft.source_chat_id == 123456789
    assert draft.source_message_id == 55


def test_original_and_protected_messages_are_rejected() -> None:
    with pytest.raises(InvalidBroadcastError, match="forwarded"):
        admin_forward_broadcasts.extract_forward_broadcast(
            message(forward_origin=None),
            123,
        )
    with pytest.raises(InvalidBroadcastError, match="Protected"):
        admin_forward_broadcasts.extract_forward_broadcast(
            message(has_protected_content=True),
            123,
        )


async def test_start_enters_forward_mode_and_cancel_clears_all_admin_state() -> None:
    ctx = context(user_data={BROADCAST_ACTION_KEY: "old"})
    current_update = update()

    await admin_forward_broadcasts.forward_broadcast_start_handler(current_update, ctx)

    assert ctx.user_data == {FORWARD_BROADCAST_ACTION_KEY: "awaiting_forward"}
    assert "Forward" in current_update.effective_message.reply_text.await_args.args[0]

    await admin_forward_broadcasts.forward_broadcast_input_cancel_handler(current_update, ctx)
    assert ctx.user_data == {}


async def test_forward_is_persisted_previewed_and_given_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_message = message()
    current_update = update(current_message)
    ctx = context(user_data={FORWARD_BROADCAST_ACTION_KEY: "awaiting_forward"})
    gateway = SimpleNamespace(send=AsyncMock())
    database = object()
    create = AsyncMock(return_value=record())
    monkeypatch.setattr(admin_forward_broadcasts, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_forward_broadcasts, "_create_draft", create)
    monkeypatch.setattr(
        admin_forward_broadcasts,
        "TelegramBroadcastGateway",
        lambda value: gateway,
    )

    await admin_forward_broadcasts.forward_broadcast_content_input_handler(
        current_update,
        ctx,
    )

    submitted = create.await_args.args[1]
    assert submitted.source_chat_id == 123456789
    assert submitted.source_message_id == 55
    gateway.send.assert_awaited_once_with(123456789, record())
    assert ctx.user_data == {}
    confirmation = current_message.reply_text.await_args_list[-1]
    callbacks = [
        button.callback_data
        for row in confirmation.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == [
        f"{FORWARD_BROADCAST_CONFIRM_PREFIX}9",
        f"{FORWARD_BROADCAST_CANCEL_PREFIX}9",
    ]


async def test_preview_failure_cancels_draft_and_keeps_forward_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_message = message()
    current_update = update(current_message)
    ctx = context(user_data={FORWARD_BROADCAST_ACTION_KEY: "awaiting_forward"})
    cancel = AsyncMock(return_value=record(status=BroadcastStatus.CANCELLED.value))
    gateway = SimpleNamespace(send=AsyncMock(side_effect=BroadcastDeliveryError()))
    monkeypatch.setattr(admin_forward_broadcasts, "get_database_manager", lambda value: object())
    monkeypatch.setattr(
        admin_forward_broadcasts,
        "_create_draft",
        AsyncMock(return_value=record()),
    )
    monkeypatch.setattr(admin_forward_broadcasts, "_cancel_draft", cancel)
    monkeypatch.setattr(
        admin_forward_broadcasts,
        "TelegramBroadcastGateway",
        lambda value: gateway,
    )

    await admin_forward_broadcasts.forward_broadcast_content_input_handler(
        current_update,
        ctx,
    )

    cancel.assert_awaited_once()
    assert ctx.user_data == {FORWARD_BROADCAST_ACTION_KEY: "awaiting_forward"}
    assert "معتبر نیست" in current_message.reply_text.await_args_list[-1].args[0]


async def test_confirmation_claims_forward_and_schedules_shared_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = SimpleNamespace(
        data=f"{FORWARD_BROADCAST_CONFIRM_PREFIX}9",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    current_update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123456789),
        update_id=11,
    )
    ctx = context()
    scheduled: list[object] = []

    def capture_task(coroutine: object, **kwargs: object) -> None:
        scheduled.append(coroutine)
        coroutine.close()  # type: ignore[attr-defined]

    ctx.application.create_task.side_effect = capture_task
    database = object()
    confirm = AsyncMock(return_value=record(status=BroadcastStatus.PROCESSING.value))
    monkeypatch.setattr(admin_forward_broadcasts, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_forward_broadcasts, "_confirm_draft", confirm)

    await admin_forward_broadcasts.forward_broadcast_callback_handler(current_update, ctx)

    confirm.assert_awaited_once_with(database, 9, 123456789)
    assert "2 کاربر" in query.edit_message_text.await_args.args[0]
    assert len(scheduled) == 1


async def test_cancel_callback_cancels_owned_forward_without_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = SimpleNamespace(
        data=f"{FORWARD_BROADCAST_CANCEL_PREFIX}9",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    current_update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123456789),
    )
    ctx = context()
    database = object()
    cancel = AsyncMock(return_value=record(status=BroadcastStatus.CANCELLED.value))
    monkeypatch.setattr(admin_forward_broadcasts, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_forward_broadcasts, "_cancel_draft", cancel)

    await admin_forward_broadcasts.forward_broadcast_callback_handler(current_update, ctx)

    cancel.assert_awaited_once_with(database, 9, 123456789)
    assert "لغو شد" in query.edit_message_text.await_args.args[0]
    ctx.application.create_task.assert_not_called()


@pytest.mark.parametrize(
    "callback",
    [
        "v1:forward:confirm:0",
        "v1:forward:confirm:-1",
        "v1:forward:confirm:9:extra",
        "v2:forward:confirm:9",
        "v1:forward:delete:9",
        "v1:forward:confirm:not-a-number",
    ],
)
def test_callback_pattern_rejects_tampered_payloads(callback: str) -> None:
    assert re.fullmatch(FORWARD_BROADCAST_CALLBACK_PATTERN, callback) is None


def test_registration_adds_four_guarded_forward_routes() -> None:
    application = SimpleNamespace(add_handler=Mock())

    admin_forward_broadcasts.register_admin_forward_broadcast_handlers(
        application,
        {123456789},
    )

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 4
    assert all(hasattr(handler.callback, "__wrapped__") for handler in handlers)


async def test_unified_input_router_dispatches_selected_forward_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = AsyncMock()
    monkeypatch.setattr(
        "app.bot.handlers.admin_input.forward_broadcast_content_input_handler",
        handler,
    )
    current_update = update()
    ctx = context(user_data={FORWARD_BROADCAST_ACTION_KEY: "awaiting_forward"})

    await admin_input_router(current_update, ctx)

    handler.assert_awaited_once_with(current_update, ctx)
