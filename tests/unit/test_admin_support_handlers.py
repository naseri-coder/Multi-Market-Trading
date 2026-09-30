"""Administrator ticket panel, reply delivery, states, and security tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram.error import TelegramError

from app.bot.handlers import admin_support
from app.bot.handlers.admin_state import SUPPORT_ADMIN_ACTION_KEY, SUPPORT_ADMIN_LIST_KEY
from app.bot.keyboards.support import (
    ADMIN_SUPPORT_CALLBACK_PATTERN,
    build_admin_ticket_actions,
    build_user_notification_actions,
)
from app.modules.support.entities import (
    SupportMessageRecord,
    SupportMessageResult,
    SupportThread,
    SupportTicketFilter,
    SupportTicketPage,
    SupportTicketRecord,
)
from app.modules.support.models import SupportSenderRole, SupportTicketStatus

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def ticket(
    *,
    status: str = SupportTicketStatus.OPEN.value,
    last_sender_role: str = SupportSenderRole.USER.value,
) -> SupportTicketRecord:
    return SupportTicketRecord(
        id=7,
        user_id=1,
        user_telegram_id=123456789,
        subject="Problem",
        status=status,
        assigned_admin_telegram_user_id=987654321,
        last_message_at=NOW,
        closed_at=None,
        created_at=NOW,
        updated_at=NOW,
        user_username="abbas",
        user_first_name="Abbas",
        user_last_name="Naseri",
        last_sender_role=last_sender_role,
    )


def thread(*, status: str = SupportTicketStatus.OPEN.value) -> SupportThread:
    return SupportThread(
        ticket=ticket(status=status),
        messages=(
            SupportMessageRecord(
                id=6,
                ticket_id=7,
                sender_role=SupportSenderRole.USER.value,
                sender_telegram_user_id=123456789,
                text="Problem details",
                created_at=NOW,
            ),
        ),
    )


def ticket_page(
    *,
    filter_by: str = SupportTicketFilter.ALL.value,
    page_number: int = 1,
    total_pages: int = 1,
) -> SupportTicketPage:
    return SupportTicketPage(
        tickets=(ticket(),),
        filter=filter_by,
        page=page_number,
        page_size=10,
        total_items=21 if total_pages > 1 else 1,
        total_pages=total_pages,
    )


def result() -> SupportMessageResult:
    return SupportMessageResult(
        ticket=ticket(status=SupportTicketStatus.IN_PROGRESS.value),
        message=SupportMessageRecord(
            id=8,
            ticket_id=7,
            sender_role=SupportSenderRole.ADMIN.value,
            sender_telegram_user_id=987654321,
            text="Resolved",
            created_at=NOW,
        ),
    )


def context(*, state: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_data={} if state is None else state,
        bot=SimpleNamespace(send_message=AsyncMock()),
        application=SimpleNamespace(bot_data={"database": object()}),
    )


def update(*, text: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=987654321),
        effective_message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        callback_query=None,
        update_id=13,
    )


async def test_admin_panel_lists_ticket_actions(monkeypatch) -> None:
    current_update = update()
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: object())
    monkeypatch.setattr(
        admin_support,
        "_get_admin_ticket_page",
        AsyncMock(return_value=ticket_page()),
    )

    ctx = context()
    await admin_support.admin_support_panel_handler(current_update, ctx)

    reply = current_update.effective_message.reply_text.await_args
    assert current_update.effective_message.reply_text.await_count == 1
    assert "تعداد: 1 | صفحه 1 از 1" in reply.args[0]
    assert "Abbas Naseri | @abbas | 123456789" in reply.args[0]
    assert len(reply.kwargs["reply_markup"].inline_keyboard) == 5
    assert ctx.user_data[SUPPORT_ADMIN_LIST_KEY] == {"filter": "all", "page": 1}


async def test_admin_reply_is_persisted_and_delivered_to_ticket_user(monkeypatch) -> None:
    current_update = update(text="Resolved")
    ctx = context(state={SUPPORT_ADMIN_ACTION_KEY: {"action": "reply", "ticket_id": 7}})
    database = object()
    add = AsyncMock(return_value=result())
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_support, "_add_admin_message", add)

    await admin_support.admin_support_input_handler(current_update, ctx)

    add.assert_awaited_once_with(database, 7, 987654321, "Resolved")
    ctx.bot.send_message.assert_awaited_once_with(
        chat_id=123456789,
        text="🎫 پاسخ پشتیبانی برای تیکت #7:\n\nResolved",
        reply_markup=build_user_notification_actions(7),
    )
    assert ctx.user_data == {}


async def test_admin_is_told_when_persisted_reply_cannot_reach_user(monkeypatch) -> None:
    current_update = update(text="Resolved")
    ctx = context(state={SUPPORT_ADMIN_ACTION_KEY: {"action": "reply", "ticket_id": 7}})
    ctx.bot.send_message.side_effect = TelegramError("blocked")
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: object())
    monkeypatch.setattr(admin_support, "_add_admin_message", AsyncMock(return_value=result()))

    await admin_support.admin_support_input_handler(current_update, ctx)

    reply = current_update.effective_message.reply_text.await_args.args[0]
    assert "ارسال آن به کاربر با خطا" in reply


async def test_admin_status_callback_uses_exact_ticket_and_admin(monkeypatch) -> None:
    query = SimpleNamespace(
        data="v1:support:admin:progress:7",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=None,
    )
    current_update = update()
    current_update.callback_query = query
    database = object()
    change = AsyncMock(return_value=ticket(status=SupportTicketStatus.IN_PROGRESS.value))
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_support, "_set_ticket_status", change)
    monkeypatch.setattr(
        admin_support,
        "_get_admin_thread",
        AsyncMock(
            side_effect=(
                thread(status=SupportTicketStatus.OPEN.value),
                thread(status=SupportTicketStatus.IN_PROGRESS.value),
            )
        ),
    )

    ctx = context()
    await admin_support.admin_support_callback_handler(current_update, ctx)

    change.assert_awaited_once_with(
        database,
        7,
        987654321,
        SupportTicketStatus.IN_PROGRESS.value,
    )
    status_notification = ctx.bot.send_message.await_args.kwargs
    assert status_notification["chat_id"] == 123456789
    assert "در حال بررسی" in status_notification["text"]
    assert status_notification["reply_markup"] == build_user_notification_actions(7)


async def test_closed_ticket_can_enter_reply_mode_without_early_reopen(monkeypatch) -> None:
    query = SimpleNamespace(
        data="v1:support:admin:reply:7",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    current_update = update()
    current_update.callback_query = query
    database = object()
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: database)
    monkeypatch.setattr(
        admin_support,
        "_get_admin_thread",
        AsyncMock(return_value=thread(status=SupportTicketStatus.CLOSED.value)),
    )

    ctx = context()
    await admin_support.admin_support_callback_handler(current_update, ctx)

    assert ctx.user_data[SUPPORT_ADMIN_ACTION_KEY] == {"action": "reply", "ticket_id": 7}
    assert "پاسخ تیکت #7" in query.edit_message_text.await_args.args[0]


async def test_admin_filter_and_pagination_callback_edits_same_message(monkeypatch) -> None:
    query = SimpleNamespace(
        data="v1:support:admin:list:waiting:2",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=None,
    )
    current_update = update()
    current_update.callback_query = query
    database = object()
    requested = AsyncMock(
        return_value=ticket_page(
            filter_by=SupportTicketFilter.WAITING.value,
            page_number=2,
            total_pages=3,
        )
    )
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_support, "_get_admin_ticket_page", requested)

    ctx = context()
    await admin_support.admin_support_callback_handler(current_update, ctx)

    requested.assert_awaited_once_with(database, filter_by="waiting", page=2)
    assert "فیلتر: در انتظار پاسخ" in query.edit_message_text.await_args.args[0]
    markup = query.edit_message_text.await_args.kwargs["reply_markup"]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "v1:support:admin:list:waiting:1" in callbacks
    assert "v1:support:admin:list:waiting:3" in callbacks
    assert "v1:support:admin:panel" in callbacks


async def test_admin_history_callback_loads_requested_message_page(monkeypatch) -> None:
    query = SimpleNamespace(
        data="v1:support:admin:history:7:2",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=None,
    )
    current_update = update()
    current_update.callback_query = query
    database = object()
    paged_thread = SupportThread(
        ticket=ticket(),
        messages=thread().messages,
        total_messages=21,
        page=2,
        total_pages=3,
    )
    load = AsyncMock(return_value=paged_thread)
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_support, "_get_admin_thread", load)

    await admin_support.admin_support_callback_handler(current_update, context())

    load.assert_awaited_once_with(database, 7, message_page=2)
    assert "پیام‌ها: 21 | صفحه 2 از 3" in query.edit_message_text.await_args.args[0]
    callbacks = [
        button.callback_data
        for row in query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "v1:support:admin:history:7:1" in callbacks
    assert "v1:support:admin:history:7:3" in callbacks


async def test_repeated_status_callback_does_not_notify_user_again(monkeypatch) -> None:
    query = SimpleNamespace(
        data="v1:support:admin:progress:7",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=None,
    )
    current_update = update()
    current_update.callback_query = query
    database = object()
    change = AsyncMock()
    monkeypatch.setattr(admin_support, "get_database_manager", lambda value: database)
    monkeypatch.setattr(admin_support, "_set_ticket_status", change)
    monkeypatch.setattr(
        admin_support,
        "_get_admin_thread",
        AsyncMock(return_value=thread(status=SupportTicketStatus.IN_PROGRESS.value)),
    )
    ctx = context()

    await admin_support.admin_support_callback_handler(current_update, ctx)

    change.assert_not_awaited()
    ctx.bot.send_message.assert_not_awaited()


def test_long_admin_reply_preview_is_bounded() -> None:
    assert len(admin_support._notification_preview("x" * 4000)) == 3500


def test_closed_ticket_actions_include_reply_reopen_and_list_back() -> None:
    markup = build_admin_ticket_actions(
        7,
        status=SupportTicketStatus.CLOSED.value,
        list_filter=SupportTicketFilter.CLOSED.value,
        page=2,
    )
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert callbacks == [
        "v1:support:admin:reply:7",
        "v1:support:admin:open:7",
        "v1:support:admin:list:closed:2",
    ]


def test_admin_callback_pattern_rejects_tampered_payloads() -> None:
    for value in (
        "v1:support:admin:reply:0",
        "v1:support:admin:delete:7",
        "v1:support:user:reply:7",
        "v1:support:admin:close:7:extra",
        "v1:support:admin:list:unknown:1",
        "v1:support:admin:list:all:0",
    ):
        assert re.fullmatch(ADMIN_SUPPORT_CALLBACK_PATTERN, value) is None

    for value in (
        "v1:support:admin:reply:7",
        "v1:support:admin:list:all:1",
        "v1:support:admin:list:answered:12",
        "v1:support:admin:panel",
    ):
        assert re.fullmatch(ADMIN_SUPPORT_CALLBACK_PATTERN, value) is not None


def test_registration_adds_four_protected_admin_ticket_routes() -> None:
    application = SimpleNamespace(add_handler=Mock())

    admin_support.register_admin_support_handlers(application, {987654321})

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 4
    assert all(hasattr(handler.callback, "__wrapped__") for handler in handlers)
