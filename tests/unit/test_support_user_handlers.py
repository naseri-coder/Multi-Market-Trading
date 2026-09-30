"""User support menu, ticket input, ownership, and callback tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.bot.handlers import support_users
from app.bot.handlers.support_state import SUPPORT_USER_ACTION_KEY, SUPPORT_USER_LIST_PAGE_KEY
from app.bot.keyboards.support import (
    SUPPORT_BUTTON,
    SUPPORT_NEW_TICKET_BUTTON,
    USER_SUPPORT_CALLBACK_PATTERN,
    build_admin_notification_actions,
    build_user_ticket_actions,
)
from app.modules.support.entities import (
    SupportMessageRecord,
    SupportMessageResult,
    SupportThread,
    SupportTicketRecord,
    UserSupportTicketPage,
)
from app.modules.support.models import SupportSenderRole, SupportTicketStatus
from app.modules.users.entities import UserProfile, UserRegistrationResult

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def ticket(*, status: str = SupportTicketStatus.OPEN.value) -> SupportTicketRecord:
    return SupportTicketRecord(
        id=7,
        user_id=1,
        user_telegram_id=123456789,
        subject="Login problem",
        status=status,
        assigned_admin_telegram_user_id=None,
        last_message_at=NOW,
        closed_at=None,
        created_at=NOW,
        updated_at=NOW,
        user_username="user",
        user_first_name="User",
        user_last_name="Example",
        last_sender_role=SupportSenderRole.USER.value,
    )


def support_message() -> SupportMessageRecord:
    return SupportMessageRecord(
        id=8,
        ticket_id=7,
        sender_role=SupportSenderRole.USER.value,
        sender_telegram_user_id=123456789,
        text="Login problem",
        created_at=NOW,
    )


def result() -> SupportMessageResult:
    return SupportMessageResult(ticket=ticket(), message=support_message())


def user_page(
    *tickets: SupportTicketRecord,
    page: int = 1,
    total_items: int | None = None,
    total_pages: int = 1,
) -> UserSupportTicketPage:
    return UserSupportTicketPage(
        tickets=tickets,
        page=page,
        page_size=10,
        total_items=len(tickets) if total_items is None else total_items,
        total_pages=total_pages,
    )


def registration() -> UserRegistrationResult:
    return UserRegistrationResult(
        profile=UserProfile(
            id=1,
            telegram_user_id=123456789,
            username="user",
            first_name="User",
            last_name=None,
            language_code="fa",
            is_bot=False,
            status="ACTIVE",
            last_activity=NOW,
            created_at=NOW,
            updated_at=NOW,
        ),
        created=False,
    )


def update(*, text: str | None = None, update_id: int = 12) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=123456789,
            username="user",
            first_name="User",
            last_name=None,
            language_code="fa",
            is_bot=False,
        ),
        effective_message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        callback_query=None,
        update_id=update_id,
    )


def context(*, state: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_data={} if state is None else state,
        bot=SimpleNamespace(send_message=AsyncMock()),
        application=SimpleNamespace(
            bot_data={
                "database": object(),
                "admin_ids": frozenset({987654321}),
            }
        ),
    )


async def test_support_menu_registers_user_and_shows_ticket_actions(monkeypatch) -> None:
    current_update = update(text=SUPPORT_BUTTON)
    sync = AsyncMock(return_value=registration())
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: object())
    monkeypatch.setattr(support_users, "sync_user", sync)

    await support_users.support_menu_handler(current_update, context())

    sync.assert_awaited_once()
    assert "پشتیبانی" in current_update.effective_message.reply_text.await_args.args[0]


async def test_new_ticket_subject_then_text_is_persisted_and_notifies_admin(
    monkeypatch,
) -> None:
    subject_update = update(text="Account access", update_id=13)
    message_update = update(text="Login problem", update_id=14)
    ctx = context(state={SUPPORT_USER_ACTION_KEY: {"action": "new_subject"}})
    create = AsyncMock(return_value=result())
    database = object()
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: database)
    monkeypatch.setattr(support_users, "sync_user", AsyncMock(return_value=registration()))
    monkeypatch.setattr(support_users, "_create_ticket", create)

    await support_users.support_user_input_handler(subject_update, ctx)

    assert ctx.user_data[SUPPORT_USER_ACTION_KEY] == {
        "action": "new_message",
        "subject": "Account access",
    }
    create.assert_not_awaited()

    await support_users.support_user_input_handler(message_update, ctx)

    create.assert_awaited_once_with(
        database,
        user_id=1,
        user_telegram_id=123456789,
        subject="Account access",
        text="Login problem",
    )
    ctx.bot.send_message.assert_awaited_once()
    notification = ctx.bot.send_message.await_args.kwargs["text"]
    assert "نام و نام خانوادگی: User Example" in notification
    assert "شناسه عددی: 123456789" in notification
    assert "آیدی اکانت: @user" in notification
    callbacks = [
        button.callback_data
        for row in ctx.bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["v1:support:admin:reply:7", "v1:support:admin:view:7"]
    assert ctx.user_data == {}
    assert "#7" in message_update.effective_message.reply_text.await_args.args[0]


async def test_new_ticket_button_update_is_not_consumed_as_ticket_text(monkeypatch) -> None:
    current_update = update(text=SUPPORT_NEW_TICKET_BUTTON)
    ctx = context()
    create = AsyncMock(return_value=result())
    monkeypatch.setattr(support_users, "_create_ticket", create)

    await support_users.support_new_ticket_handler(current_update, ctx)
    await support_users.support_user_input_handler(current_update, ctx)

    assert ctx.user_data[SUPPORT_USER_ACTION_KEY] == {
        "action": "new_subject",
        "prompt_update_id": current_update.update_id,
    }
    create.assert_not_awaited()
    assert current_update.effective_message.reply_text.await_count == 1


async def test_invalid_ticket_subject_keeps_subject_step_active() -> None:
    current_update = update(text="x" * 121, update_id=13)
    ctx = context(state={SUPPORT_USER_ACTION_KEY: {"action": "new_subject"}})

    await support_users.support_user_input_handler(current_update, ctx)

    assert ctx.user_data[SUPPORT_USER_ACTION_KEY] == {"action": "new_subject"}
    assert "۱۲۰" in current_update.effective_message.reply_text.await_args.args[0]


async def test_existing_ticket_reply_is_persisted(monkeypatch) -> None:
    current_update = update(text="More information")
    ctx = context(state={SUPPORT_USER_ACTION_KEY: {"action": "reply", "ticket_id": 7}})
    add = AsyncMock(return_value=result())
    database = object()
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: database)
    monkeypatch.setattr(support_users, "_add_user_message", add)

    await support_users.support_user_input_handler(current_update, ctx)

    add.assert_awaited_once_with(database, 7, 123456789, "More information")
    assert ctx.user_data == {}


async def test_ticket_list_renders_status_and_owned_actions(monkeypatch) -> None:
    current_update = update()
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: object())
    monkeypatch.setattr(
        support_users,
        "_get_user_ticket_page",
        AsyncMock(
            return_value=user_page(
                ticket(),
                ticket(status=SupportTicketStatus.CLOSED.value),
            )
        ),
    )

    await support_users.support_list_handler(current_update, context())

    reply = current_update.effective_message.reply_text.await_args
    assert current_update.effective_message.reply_text.await_count == 1
    assert "تعداد: 2 | صفحه 1 از 1" in reply.args[0]
    assert "#7 | باز | Login problem" in reply.args[0]
    assert "#7 | بسته | Login problem" in reply.args[0]
    assert len(reply.kwargs["reply_markup"].inline_keyboard) == 2


async def test_user_callback_view_and_close_use_telegram_owner(monkeypatch) -> None:
    database = object()
    thread = SupportThread(ticket=ticket(), messages=(support_message(),))
    get_thread = AsyncMock(return_value=thread)
    close = AsyncMock(return_value=ticket(status=SupportTicketStatus.CLOSED.value))
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: database)
    monkeypatch.setattr(support_users, "_get_user_thread", get_thread)
    monkeypatch.setattr(support_users, "_close_user_ticket", close)

    view_query = SimpleNamespace(
        data="v1:support:user:view:7",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    close_query = SimpleNamespace(
        data="v1:support:user:close:7",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    base = update()
    base.callback_query = view_query
    await support_users.support_user_callback_handler(base, context())
    base.callback_query = close_query
    await support_users.support_user_callback_handler(base, context())

    get_thread.assert_awaited_once_with(database, 7, 123456789, message_page=1)
    close.assert_awaited_once_with(database, 7, 123456789)


async def test_closed_user_ticket_can_enter_reply_mode(monkeypatch) -> None:
    database = object()
    closed_thread = SupportThread(
        ticket=ticket(status=SupportTicketStatus.CLOSED.value),
        messages=(support_message(),),
    )
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: database)
    monkeypatch.setattr(
        support_users,
        "_get_user_thread",
        AsyncMock(return_value=closed_thread),
    )
    query = SimpleNamespace(
        data="v1:support:user:reply:7",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    current_update = update()
    current_update.callback_query = query
    ctx = context()

    await support_users.support_user_callback_handler(current_update, ctx)

    assert ctx.user_data[SUPPORT_USER_ACTION_KEY] == {"action": "reply", "ticket_id": 7}
    assert "پیام جدید برای تیکت #7" in query.edit_message_text.await_args.args[0]


async def test_user_ticket_list_callback_returns_to_compact_list(monkeypatch) -> None:
    database = object()
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: database)
    listed = AsyncMock(
        return_value=user_page(ticket(), page=2, total_items=11, total_pages=2)
    )
    monkeypatch.setattr(support_users, "_get_user_ticket_page", listed)
    query = SimpleNamespace(
        data="v1:support:user:list:2",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    current_update = update()
    current_update.callback_query = query

    ctx = context()
    await support_users.support_user_callback_handler(current_update, ctx)

    listed.assert_awaited_once_with(database, 123456789, page=2)
    assert "تعداد: 11 | صفحه 2 از 2" in query.edit_message_text.await_args.args[0]
    assert ctx.user_data[SUPPORT_USER_LIST_PAGE_KEY] == 2


def test_closed_user_ticket_actions_are_reply_and_back_without_view() -> None:
    markup = build_user_ticket_actions(7, closed=True)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert callbacks == ["v1:support:user:reply:7", "v1:support:user:list:1"]
    assert "👁 مشاهده" not in labels
    assert re.fullmatch(USER_SUPPORT_CALLBACK_PATTERN, "v1:support:user:list:7")


async def test_user_history_callback_loads_requested_page_and_keeps_list_location(
    monkeypatch,
) -> None:
    database = object()
    paged_thread = SupportThread(
        ticket=ticket(),
        messages=(support_message(),),
        total_messages=21,
        page=2,
        total_pages=3,
    )
    load = AsyncMock(return_value=paged_thread)
    monkeypatch.setattr(support_users, "get_database_manager", lambda value: database)
    monkeypatch.setattr(support_users, "_get_user_thread", load)
    query = SimpleNamespace(
        data="v1:support:user:history:7:2",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    current_update = update()
    current_update.callback_query = query
    ctx = context(state={SUPPORT_USER_LIST_PAGE_KEY: 4})

    await support_users.support_user_callback_handler(current_update, ctx)

    load.assert_awaited_once_with(database, 7, 123456789, message_page=2)
    assert "پیام‌ها: 21 | صفحه 2 از 3" in query.edit_message_text.await_args.args[0]
    callbacks = [
        button.callback_data
        for row in query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "v1:support:user:history:7:1" in callbacks
    assert "v1:support:user:history:7:3" in callbacks
    assert "v1:support:user:list:4" in callbacks


def test_admin_notification_actions_are_guarded_callback_payloads() -> None:
    markup = build_admin_notification_actions(7)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert callbacks == ["v1:support:admin:reply:7", "v1:support:admin:view:7"]


def test_long_support_notification_preview_is_bounded() -> None:
    assert len(support_users._notification_preview("x" * 4000)) == 3000


def test_registration_adds_seven_group_zero_and_one_group_one_routes() -> None:
    application = SimpleNamespace(add_handler=Mock())

    support_users.register_support_user_handlers(application)

    calls = application.add_handler.call_args_list
    assert len(calls) == 8
    assert [call.kwargs.get("group", 0) for call in calls].count(0) == 7
    assert [call.kwargs.get("group", 0) for call in calls].count(1) == 1
