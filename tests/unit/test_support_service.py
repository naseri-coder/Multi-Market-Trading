"""Support ticket business rules and transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.support.entities import (
    SupportMessageRecord,
    SupportMessageResult,
    SupportThread,
    SupportTicketFilter,
    SupportTicketRecord,
)
from app.modules.support.errors import InvalidSupportMessageError
from app.modules.support.models import SupportSenderRole, SupportTicketStatus
from app.modules.support.service import SupportService

NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


def ticket(*, status: str = SupportTicketStatus.OPEN.value) -> SupportTicketRecord:
    return SupportTicketRecord(
        id=7,
        user_id=1,
        user_telegram_id=123456789,
        subject="Problem",
        status=status,
        assigned_admin_telegram_user_id=None,
        last_message_at=NOW,
        closed_at=NOW if status == SupportTicketStatus.CLOSED.value else None,
        created_at=NOW,
        updated_at=NOW,
    )


def message(*, role: str = SupportSenderRole.USER.value) -> SupportMessageRecord:
    return SupportMessageRecord(
        id=9,
        ticket_id=7,
        sender_role=role,
        sender_telegram_user_id=123456789,
        text="Problem",
        created_at=NOW,
    )


def result() -> SupportMessageResult:
    return SupportMessageResult(ticket=ticket(), message=message())


def repository() -> SimpleNamespace:
    return SimpleNamespace(
        create_ticket=AsyncMock(return_value=result()),
        list_user_tickets=AsyncMock(return_value=(ticket(),)),
        count_user_tickets=AsyncMock(return_value=23),
        list_user_ticket_page=AsyncMock(return_value=(ticket(),)),
        list_admin_tickets=AsyncMock(return_value=(ticket(),)),
        count_admin_tickets=AsyncMock(return_value=23),
        list_admin_ticket_page=AsyncMock(return_value=(ticket(),)),
        get_thread=AsyncMock(return_value=SupportThread(ticket(), (message(),))),
        add_user_message=AsyncMock(return_value=result()),
        add_admin_message=AsyncMock(return_value=result()),
        close_by_user=AsyncMock(return_value=ticket(status=SupportTicketStatus.CLOSED.value)),
        set_status=AsyncMock(return_value=ticket(status=SupportTicketStatus.IN_PROGRESS.value)),
    )


async def test_create_ticket_normalizes_text_and_derives_bounded_subject() -> None:
    repo = repository()
    service = SupportService(repo, clock=lambda: NOW)
    first_line = "x" * 130

    await service.create_ticket(
        user_id=1,
        user_telegram_id=123456789,
        text=f"  {first_line}\nmore details  ",
    )

    submitted = repo.create_ticket.await_args.kwargs
    assert submitted["subject"] == "x" * 120
    assert submitted["text"] == f"{first_line}\nmore details"
    assert submitted["created_at"] == NOW


async def test_create_ticket_uses_explicit_normalized_subject() -> None:
    repo = repository()

    await SupportService(repo, clock=lambda: NOW).create_ticket(
        user_id=1,
        user_telegram_id=123456789,
        subject="  Account access  ",
        text="Login problem",
    )

    assert repo.create_ticket.await_args.kwargs["subject"] == "Account access"


@pytest.mark.parametrize("subject", ["", "   ", "x" * 121, "line one\nline two"])
async def test_invalid_explicit_subject_is_rejected(subject: str) -> None:
    repo = repository()

    with pytest.raises(InvalidSupportMessageError):
        await SupportService(repo).create_ticket(
            user_id=1,
            user_telegram_id=2,
            subject=subject,
            text="Valid ticket message",
        )

    repo.create_ticket.assert_not_awaited()


@pytest.mark.parametrize("text", ["", "   ", "x" * 4001])
async def test_invalid_ticket_text_is_rejected_before_persistence(text: str) -> None:
    repo = repository()

    with pytest.raises(InvalidSupportMessageError):
        await SupportService(repo).create_ticket(
            user_id=1,
            user_telegram_id=2,
            text=text,
        )

    repo.create_ticket.assert_not_awaited()


async def test_user_and_admin_messages_delegate_with_aware_timestamp() -> None:
    repo = repository()
    service = SupportService(repo, clock=lambda: NOW)

    await service.add_user_message(7, 123456789, " user reply ")
    await service.add_admin_message(7, 987654321, " admin reply ")

    repo.add_user_message.assert_awaited_once_with(
        7,
        123456789,
        text="user reply",
        created_at=NOW,
    )
    repo.add_admin_message.assert_awaited_once_with(
        7,
        987654321,
        text="admin reply",
        created_at=NOW,
    )


async def test_admin_ticket_page_is_ten_items_and_clamps_excessive_page() -> None:
    repo = repository()
    service = SupportService(repo)

    page = await service.get_admin_ticket_page(
        filter_by=SupportTicketFilter.WAITING.value,
        page=99,
    )

    repo.count_admin_tickets.assert_awaited_once_with(filter_by="waiting")
    repo.list_admin_ticket_page.assert_awaited_once_with(
        filter_by="waiting",
        limit=10,
        offset=20,
    )
    assert page.page == 3
    assert page.page_size == 10
    assert page.total_items == 23
    assert page.total_pages == 3


async def test_user_ticket_page_is_ten_items_and_clamps_excessive_page() -> None:
    repo = repository()
    service = SupportService(repo)

    page = await service.get_user_ticket_page(123456789, page=99)

    repo.count_user_tickets.assert_awaited_once_with(123456789)
    repo.list_user_ticket_page.assert_awaited_once_with(
        123456789,
        limit=10,
        offset=20,
    )
    assert page.page == 3
    assert page.page_size == 10
    assert page.total_items == 23
    assert page.total_pages == 3


async def test_thread_history_is_always_requested_in_ten_message_pages() -> None:
    repo = repository()
    service = SupportService(repo)

    await service.get_user_thread(7, 123456789, message_page=2)
    repo.get_thread.assert_awaited_once_with(
        7,
        user_telegram_id=123456789,
        message_page=2,
        message_page_size=10,
    )

    repo.get_thread.reset_mock()
    await service.get_admin_thread(7, message_page=3)
    repo.get_thread.assert_awaited_once_with(
        7,
        message_page=3,
        message_page_size=10,
    )


@pytest.mark.parametrize(
    ("filter_by", "page", "page_size"),
    [
        ("unknown", 1, 10),
        (SupportTicketFilter.ALL.value, 0, 10),
        (SupportTicketFilter.ALL.value, True, 10),
        (SupportTicketFilter.ALL.value, 1, 20),
    ],
)
async def test_invalid_admin_ticket_page_input_is_rejected(
    filter_by: str,
    page: int,
    page_size: int,
) -> None:
    repo = repository()

    with pytest.raises(InvalidSupportMessageError):
        await SupportService(repo).get_admin_ticket_page(
            filter_by=filter_by,
            page=page,
            page_size=page_size,
        )

    repo.count_admin_tickets.assert_not_awaited()


@pytest.mark.parametrize("status", [item.value for item in SupportTicketStatus])
async def test_admin_can_set_each_supported_status(status: str) -> None:
    repo = repository()
    service = SupportService(repo, clock=lambda: NOW)

    await service.set_status(7, 987654321, status)

    repo.set_status.assert_awaited_once_with(
        7,
        987654321,
        status=status,
        changed_at=NOW,
    )


async def test_unknown_status_and_invalid_identifiers_are_rejected() -> None:
    repo = repository()
    service = SupportService(repo)

    with pytest.raises(InvalidSupportMessageError):
        await service.set_status(7, 9, "UNKNOWN")
    with pytest.raises(InvalidSupportMessageError):
        await service.get_user_thread(0, 123)
    with pytest.raises(InvalidSupportMessageError):
        await service.list_user_tickets(123, limit=0)
    with pytest.raises(InvalidSupportMessageError):
        await service.get_user_ticket_page(123, page=0)
    with pytest.raises(InvalidSupportMessageError):
        await service.get_admin_thread(7, message_page=True)


async def test_naive_clock_is_rejected() -> None:
    service = SupportService(repository(), clock=lambda: datetime(2026, 9, 1))

    with pytest.raises(RuntimeError, match="aware"):
        await service.close_by_user(7, 123456789)
