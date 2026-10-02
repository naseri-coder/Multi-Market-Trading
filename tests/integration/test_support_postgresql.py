"""Transactional Phase 10 support workflow against real PostgreSQL."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.support.entities import SupportTicketFilter
from app.modules.support.errors import SupportTicketNotFoundError
from app.modules.support.models import (
    SupportMessage,
    SupportSenderRole,
    SupportTicket,
    SupportTicketStatus,
)
from app.modules.support.repository import SQLAlchemySupportRepository
from app.modules.support.service import SupportService
from app.modules.users.models import User, UserStatus

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real support integration test",
)


async def test_real_support_ownership_messages_and_status_lifecycle(
    valid_token: str,
) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    base_id = 500_000_000_000_000_000 + uuid4().int % 100_000_000_000_000
    owner_telegram_id = base_id + 1
    other_telegram_id = base_id + 2
    admin_telegram_id = base_id + 3
    opened_at = datetime(2026, 9, 1, 12, tzinfo=UTC)
    user_reply_at = opened_at + timedelta(minutes=1)
    admin_reply_at = opened_at + timedelta(minutes=2)
    closed_at = opened_at + timedelta(minutes=3)
    reopened_at = opened_at + timedelta(minutes=4)

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                owner_id, other_id = (
                    (
                        await session.execute(
                            insert(User)
                            .values(
                                [
                                    {
                                        "telegram_user_id": owner_telegram_id,
                                        "username": "phase10_owner",
                                        "first_name": "Ticket Owner",
                                        "last_name": "Example",
                                        "is_bot": False,
                                        "status": UserStatus.ACTIVE.value,
                                        "last_activity": opened_at,
                                    },
                                    {
                                        "telegram_user_id": other_telegram_id,
                                        "username": "phase10_other",
                                        "first_name": "Other User",
                                        "last_name": None,
                                        "is_bot": False,
                                        "status": UserStatus.ACTIVE.value,
                                        "last_activity": opened_at,
                                    },
                                ]
                            )
                            .returning(User.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert owner_id != other_id

                repository = SQLAlchemySupportRepository(session)
                service = SupportService(repository, clock=lambda: opened_at)
                created = await service.create_ticket(
                    user_id=owner_id,
                    user_telegram_id=owner_telegram_id,
                    subject="Signal access",
                    text="Cannot access signals\nPlease investigate.",
                )

                assert created.ticket.status == SupportTicketStatus.OPEN.value
                assert created.ticket.subject == "Signal access"
                assert created.ticket.user_username == "phase10_owner"
                assert created.ticket.user_first_name == "Ticket Owner"
                assert created.ticket.user_last_name == "Example"
                assert created.message.sender_role == SupportSenderRole.USER.value

                waiting_page = await service.get_admin_ticket_page(
                    filter_by=SupportTicketFilter.WAITING.value,
                )
                assert created.ticket.id in {item.id for item in waiting_page.tickets}

                owned = await service.list_user_tickets(owner_telegram_id)
                admin_list = await service.list_admin_tickets()
                assert [item.id for item in owned] == [created.ticket.id]
                assert created.ticket.id in {item.id for item in admin_list}
                assert await service.list_user_tickets(other_telegram_id) == ()

                thread = await service.get_user_thread(created.ticket.id, owner_telegram_id)
                assert [message.text for message in thread.messages] == [
                    "Cannot access signals\nPlease investigate."
                ]
                with pytest.raises(SupportTicketNotFoundError):
                    await service.get_user_thread(created.ticket.id, other_telegram_id)
                with pytest.raises(SupportTicketNotFoundError):
                    await service.add_user_message(
                        created.ticket.id,
                        other_telegram_id,
                        "Unauthorized reply",
                    )

                service.clock = lambda: user_reply_at
                user_reply = await service.add_user_message(
                    created.ticket.id,
                    owner_telegram_id,
                    "Additional details",
                )
                assert user_reply.message.sender_role == SupportSenderRole.USER.value

                service.clock = lambda: admin_reply_at
                admin_reply = await service.add_admin_message(
                    created.ticket.id,
                    admin_telegram_id,
                    "We are checking this.",
                )
                assert admin_reply.ticket.status == SupportTicketStatus.IN_PROGRESS.value
                assert admin_reply.ticket.assigned_admin_telegram_user_id == admin_telegram_id
                assert admin_reply.message.sender_role == SupportSenderRole.ADMIN.value

                answered_page = await service.get_admin_ticket_page(
                    filter_by=SupportTicketFilter.ANSWERED.value,
                )
                assert created.ticket.id in {item.id for item in answered_page.tickets}

                thread = await service.get_admin_thread(created.ticket.id)
                assert [message.text for message in thread.messages] == [
                    "Cannot access signals\nPlease investigate.",
                    "Additional details",
                    "We are checking this.",
                ]

                service.clock = lambda: closed_at
                closed = await service.set_status(
                    created.ticket.id,
                    admin_telegram_id,
                    SupportTicketStatus.CLOSED.value,
                )
                assert closed.status == SupportTicketStatus.CLOSED.value
                assert closed.closed_at == closed_at
                service.clock = lambda: closed_at + timedelta(seconds=15)
                reopened_by_user = await service.add_user_message(
                    created.ticket.id,
                    owner_telegram_id,
                    "Reply after close",
                )
                assert reopened_by_user.ticket.status == SupportTicketStatus.OPEN.value
                assert reopened_by_user.ticket.closed_at is None

                service.clock = lambda: closed_at + timedelta(seconds=20)
                await service.set_status(
                    created.ticket.id,
                    admin_telegram_id,
                    SupportTicketStatus.CLOSED.value,
                )

                closed_page = await service.get_admin_ticket_page(
                    filter_by=SupportTicketFilter.CLOSED.value,
                )
                assert created.ticket.id in {item.id for item in closed_page.tickets}

                service.clock = lambda: closed_at + timedelta(seconds=30)
                replied_to_closed = await service.add_admin_message(
                    created.ticket.id,
                    admin_telegram_id,
                    "Admin reply after close",
                )
                assert replied_to_closed.ticket.status == SupportTicketStatus.IN_PROGRESS.value
                assert replied_to_closed.ticket.closed_at is None

                service.clock = lambda: reopened_at
                reopened = await service.set_status(
                    created.ticket.id,
                    admin_telegram_id,
                    SupportTicketStatus.OPEN.value,
                )
                assert reopened.status == SupportTicketStatus.OPEN.value
                assert reopened.closed_at is None

                service.clock = lambda: reopened_at + timedelta(minutes=1)
                user_closed = await service.close_by_user(
                    created.ticket.id,
                    owner_telegram_id,
                )
                assert user_closed.status == SupportTicketStatus.CLOSED.value
                with pytest.raises(SupportTicketNotFoundError):
                    await service.close_by_user(created.ticket.id, other_telegram_id)

                service.clock = lambda: reopened_at + timedelta(minutes=2)
                history_ticket = await service.create_ticket(
                    user_id=owner_id,
                    user_telegram_id=owner_telegram_id,
                    subject="Long history",
                    text="history-0",
                )
                for index in range(1, 15):
                    service.clock = lambda index=index: reopened_at + timedelta(
                        minutes=2,
                        seconds=index,
                    )
                    if index % 2:
                        await service.add_admin_message(
                            history_ticket.ticket.id,
                            admin_telegram_id,
                            f"history-{index}",
                        )
                    else:
                        await service.add_user_message(
                            history_ticket.ticket.id,
                            owner_telegram_id,
                            f"history-{index}",
                        )

                newest_history = await service.get_user_thread(
                    history_ticket.ticket.id,
                    owner_telegram_id,
                )
                older_history = await service.get_admin_thread(
                    history_ticket.ticket.id,
                    message_page=2,
                )
                assert newest_history.total_messages == 15
                assert newest_history.total_pages == 2
                assert [item.text for item in newest_history.messages] == [
                    f"history-{index}" for index in range(5, 15)
                ]
                assert [item.text for item in older_history.messages] == [
                    f"history-{index}" for index in range(5)
                ]

                for index in range(11):
                    service.clock = lambda index=index: reopened_at + timedelta(
                        minutes=3,
                        seconds=index,
                    )
                    await service.create_ticket(
                        user_id=owner_id,
                        user_telegram_id=owner_telegram_id,
                        subject=f"Archive {index}",
                        text=f"archive-{index}",
                    )
                first_user_page = await service.get_user_ticket_page(owner_telegram_id)
                second_user_page = await service.get_user_ticket_page(
                    owner_telegram_id,
                    page=2,
                )
                assert first_user_page.total_items == 13
                assert first_user_page.total_pages == 2
                assert len(first_user_page.tickets) == 10
                assert len(second_user_page.tickets) == 3

                message_count = await session.scalar(
                    select(func.count(SupportMessage.id)).where(
                        SupportMessage.ticket_id == created.ticket.id
                    )
                )
                assert message_count == 5
            finally:
                await transaction.rollback()

        async with database.session() as verification_session:
            ticket_count = await verification_session.scalar(
                select(func.count(SupportTicket.id)).where(
                    SupportTicket.user_id.in_((owner_id, other_id))
                )
            )
            user_count = await verification_session.scalar(
                select(func.count(User.id)).where(
                    User.telegram_user_id.in_((owner_telegram_id, other_telegram_id))
                )
            )
            assert ticket_count == 0
            assert user_count == 0
    finally:
        await database.dispose()
