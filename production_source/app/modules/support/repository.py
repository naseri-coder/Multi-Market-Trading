"""Support ticket persistence port and PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.support.entities import (
    SupportMessageRecord,
    SupportMessageResult,
    SupportThread,
    SupportTicketFilter,
    SupportTicketRecord,
)
from app.modules.support.errors import (
    SupportRepositoryError,
    SupportTicketNotFoundError,
    SupportTicketStateError,
)
from app.modules.support.models import (
    SupportMessage,
    SupportSenderRole,
    SupportTicket,
    SupportTicketStatus,
)
from app.modules.users.models import User


class SupportRepository(Protocol):
    """Persistence operations consumed by SupportService."""

    async def create_ticket(
        self,
        *,
        user_id: int,
        user_telegram_id: int,
        subject: str,
        text: str,
        created_at: datetime,
    ) -> SupportMessageResult: ...

    async def list_user_tickets(
        self,
        user_telegram_id: int,
        *,
        limit: int,
    ) -> tuple[SupportTicketRecord, ...]: ...

    async def count_user_tickets(self, user_telegram_id: int) -> int: ...

    async def list_user_ticket_page(
        self,
        user_telegram_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SupportTicketRecord, ...]: ...

    async def list_admin_tickets(self, *, limit: int) -> tuple[SupportTicketRecord, ...]: ...

    async def count_admin_tickets(self, *, filter_by: str) -> int: ...

    async def list_admin_ticket_page(
        self,
        *,
        filter_by: str,
        limit: int,
        offset: int,
    ) -> tuple[SupportTicketRecord, ...]: ...

    async def get_thread(
        self,
        ticket_id: int,
        *,
        user_telegram_id: int | None = None,
        message_page: int = 1,
        message_page_size: int = 10,
    ) -> SupportThread: ...

    async def add_user_message(
        self,
        ticket_id: int,
        user_telegram_id: int,
        *,
        text: str,
        created_at: datetime,
    ) -> SupportMessageResult: ...

    async def add_admin_message(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        *,
        text: str,
        created_at: datetime,
    ) -> SupportMessageResult: ...

    async def close_by_user(
        self,
        ticket_id: int,
        user_telegram_id: int,
        *,
        closed_at: datetime,
    ) -> SupportTicketRecord: ...

    async def set_status(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        *,
        status: str,
        changed_at: datetime,
    ) -> SupportTicketRecord: ...


def _to_ticket(
    ticket: SupportTicket,
    user_telegram_id: int,
    user_username: str | None = None,
    user_first_name: str = "",
    user_last_name: str | None = None,
    last_sender_role: str | None = None,
) -> SupportTicketRecord:
    return SupportTicketRecord(
        id=ticket.id,
        user_id=ticket.user_id,
        user_telegram_id=user_telegram_id,
        subject=ticket.subject,
        status=ticket.status,
        assigned_admin_telegram_user_id=ticket.assigned_admin_telegram_user_id,
        last_message_at=ticket.last_message_at,
        closed_at=ticket.closed_at,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        user_username=user_username,
        user_first_name=user_first_name,
        user_last_name=user_last_name,
        last_sender_role=last_sender_role,
    )


def _to_message(message: SupportMessage) -> SupportMessageRecord:
    return SupportMessageRecord(
        id=message.id,
        ticket_id=message.ticket_id,
        sender_role=message.sender_role,
        sender_telegram_user_id=message.sender_telegram_user_id,
        text=message.text,
        created_at=message.created_at,
    )


class SQLAlchemySupportRepository:
    """PostgreSQL support repository bound to a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_ticket(
        self,
        *,
        user_id: int,
        user_telegram_id: int,
        subject: str,
        text: str,
        created_at: datetime,
    ) -> SupportMessageResult:
        try:
            ticket = (
                await self.session.execute(
                    insert(SupportTicket)
                    .values(
                        user_id=user_id,
                        subject=subject,
                        status=SupportTicketStatus.OPEN.value,
                        last_message_at=created_at,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                    .returning(SupportTicket)
                )
            ).scalar_one()
            message = await self._insert_message(
                ticket.id,
                SupportSenderRole.USER.value,
                user_telegram_id,
                text,
                created_at,
            )
            identity = await self._get_user_identity(user_id)
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to create support ticket") from exc
        return SupportMessageResult(
            ticket=_to_ticket(
                ticket,
                *identity,
                last_sender_role=SupportSenderRole.USER.value,
            ),
            message=_to_message(message),
        )

    async def list_user_tickets(
        self,
        user_telegram_id: int,
        *,
        limit: int,
    ) -> tuple[SupportTicketRecord, ...]:
        statement = (
            self._ticket_select()
            .where(User.telegram_user_id == user_telegram_id)
            .order_by(SupportTicket.last_message_at.desc(), SupportTicket.id.desc())
            .limit(limit)
        )
        return await self._list_tickets(statement)

    async def count_user_tickets(self, user_telegram_id: int) -> int:
        statement = (
            select(func.count(SupportTicket.id))
            .join(User, User.id == SupportTicket.user_id)
            .where(User.telegram_user_id == user_telegram_id)
        )
        try:
            return int((await self.session.scalar(statement)) or 0)
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to count user support tickets") from exc

    async def list_user_ticket_page(
        self,
        user_telegram_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SupportTicketRecord, ...]:
        statement = (
            self._ticket_select()
            .where(User.telegram_user_id == user_telegram_id)
            .order_by(SupportTicket.last_message_at.desc(), SupportTicket.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return await self._list_tickets(statement)

    async def list_admin_tickets(self, *, limit: int) -> tuple[SupportTicketRecord, ...]:
        statement = (
            self._ticket_select()
            .order_by(
                SupportTicket.status == SupportTicketStatus.CLOSED.value,
                SupportTicket.last_message_at.desc(),
                SupportTicket.id.desc(),
            )
            .limit(limit)
        )
        return await self._list_tickets(statement)

    async def count_admin_tickets(self, *, filter_by: str) -> int:
        statement = select(func.count(SupportTicket.id))
        condition = self._admin_filter_condition(filter_by)
        if condition is not None:
            statement = statement.where(condition)
        try:
            return int((await self.session.scalar(statement)) or 0)
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to count support tickets") from exc

    async def list_admin_ticket_page(
        self,
        *,
        filter_by: str,
        limit: int,
        offset: int,
    ) -> tuple[SupportTicketRecord, ...]:
        statement = self._ticket_select()
        condition = self._admin_filter_condition(filter_by)
        if condition is not None:
            statement = statement.where(condition)
        statement = (
            statement.order_by(
                SupportTicket.status == SupportTicketStatus.CLOSED.value,
                SupportTicket.last_message_at.desc(),
                SupportTicket.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return await self._list_tickets(statement)

    async def _list_tickets(self, statement: object) -> tuple[SupportTicketRecord, ...]:
        try:
            rows = (await self.session.execute(statement)).all()
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to list support tickets") from exc
        return tuple(_to_ticket(*row) for row in rows)

    async def get_thread(
        self,
        ticket_id: int,
        *,
        user_telegram_id: int | None = None,
        message_page: int = 1,
        message_page_size: int = 10,
    ) -> SupportThread:
        statement = self._ticket_select().where(SupportTicket.id == ticket_id)
        if user_telegram_id is not None:
            statement = statement.where(User.telegram_user_id == user_telegram_id)
        try:
            row = (await self.session.execute(statement)).one_or_none()
            if row is None:
                raise SupportTicketNotFoundError("Support ticket does not exist")
            total_messages = int(
                (
                    await self.session.scalar(
                        select(func.count(SupportMessage.id)).where(
                            SupportMessage.ticket_id == ticket_id
                        )
                    )
                )
                or 0
            )
            total_pages = max(1, (total_messages + message_page_size - 1) // message_page_size)
            current_page = min(message_page, total_pages)
            messages_desc = (
                (
                    await self.session.execute(
                        select(SupportMessage)
                        .where(SupportMessage.ticket_id == ticket_id)
                        .order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc())
                        .offset((current_page - 1) * message_page_size)
                        .limit(message_page_size)
                    )
                )
                .scalars()
                .all()
            )
        except SupportTicketNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to load support thread") from exc
        ticket, telegram_id, username, first_name, last_name, last_sender_role = row
        return SupportThread(
            ticket=_to_ticket(
                ticket,
                telegram_id,
                username,
                first_name,
                last_name,
                last_sender_role,
            ),
            messages=tuple(_to_message(message) for message in reversed(messages_desc)),
            total_messages=total_messages,
            page=current_page,
            total_pages=total_pages,
        )

    async def add_user_message(
        self,
        ticket_id: int,
        user_telegram_id: int,
        *,
        text: str,
        created_at: datetime,
    ) -> SupportMessageResult:
        user_id = select(User.id).where(User.telegram_user_id == user_telegram_id).scalar_subquery()
        statement = (
            update(SupportTicket)
            .where(
                SupportTicket.id == ticket_id,
                SupportTicket.user_id == user_id,
            )
            .values(
                status=SupportTicketStatus.OPEN.value,
                last_message_at=created_at,
                closed_at=None,
                updated_at=created_at,
            )
            .returning(SupportTicket)
        )
        try:
            ticket = (await self.session.execute(statement)).scalar_one_or_none()
            if ticket is None:
                await self._raise_user_transition_error(ticket_id, user_telegram_id)
            message = await self._insert_message(
                ticket_id,
                SupportSenderRole.USER.value,
                user_telegram_id,
                text,
                created_at,
            )
            identity = await self._get_user_identity(ticket.user_id)
        except (SupportTicketNotFoundError, SupportTicketStateError):
            raise
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to add user support message") from exc
        return SupportMessageResult(
            ticket=_to_ticket(
                ticket,
                *identity,
                last_sender_role=SupportSenderRole.USER.value,
            ),
            message=_to_message(message),
        )

    async def add_admin_message(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        *,
        text: str,
        created_at: datetime,
    ) -> SupportMessageResult:
        statement = (
            update(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .values(
                status=SupportTicketStatus.IN_PROGRESS.value,
                assigned_admin_telegram_user_id=admin_telegram_id,
                last_message_at=created_at,
                closed_at=None,
                updated_at=created_at,
            )
            .returning(SupportTicket)
        )
        try:
            ticket = (await self.session.execute(statement)).scalar_one_or_none()
            if ticket is None:
                raise SupportTicketNotFoundError("Support ticket does not exist")
            identity = await self._get_user_identity(ticket.user_id)
            message = await self._insert_message(
                ticket_id,
                SupportSenderRole.ADMIN.value,
                admin_telegram_id,
                text,
                created_at,
            )
        except (SupportTicketNotFoundError, SupportTicketStateError):
            raise
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to add admin support message") from exc
        return SupportMessageResult(
            ticket=_to_ticket(
                ticket,
                *identity,
                last_sender_role=SupportSenderRole.ADMIN.value,
            ),
            message=_to_message(message),
        )

    async def close_by_user(
        self,
        ticket_id: int,
        user_telegram_id: int,
        *,
        closed_at: datetime,
    ) -> SupportTicketRecord:
        user_id = select(User.id).where(User.telegram_user_id == user_telegram_id).scalar_subquery()
        statement = (
            update(SupportTicket)
            .where(
                SupportTicket.id == ticket_id,
                SupportTicket.user_id == user_id,
                SupportTicket.status != SupportTicketStatus.CLOSED.value,
            )
            .values(
                status=SupportTicketStatus.CLOSED.value,
                closed_at=closed_at,
                updated_at=closed_at,
            )
            .returning(SupportTicket)
        )
        try:
            ticket = (await self.session.execute(statement)).scalar_one_or_none()
            if ticket is None:
                await self._raise_user_transition_error(ticket_id, user_telegram_id)
            identity = await self._get_user_identity(ticket.user_id)
        except (SupportTicketNotFoundError, SupportTicketStateError):
            raise
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to close support ticket") from exc
        return _to_ticket(ticket, *identity)

    async def set_status(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        *,
        status: str,
        changed_at: datetime,
    ) -> SupportTicketRecord:
        closed_at = changed_at if status == SupportTicketStatus.CLOSED.value else None
        statement = (
            update(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .values(
                status=status,
                assigned_admin_telegram_user_id=admin_telegram_id,
                closed_at=closed_at,
                updated_at=changed_at,
            )
            .returning(SupportTicket)
        )
        try:
            ticket = (await self.session.execute(statement)).scalar_one_or_none()
            if ticket is None:
                raise SupportTicketNotFoundError("Support ticket does not exist")
            identity = await self._get_user_identity(ticket.user_id)
        except SupportTicketNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise SupportRepositoryError("Unable to update support ticket status") from exc
        return _to_ticket(ticket, *identity)

    async def _insert_message(
        self,
        ticket_id: int,
        sender_role: str,
        sender_telegram_user_id: int,
        text: str,
        created_at: datetime,
    ) -> SupportMessage:
        return (
            await self.session.execute(
                insert(SupportMessage)
                .values(
                    ticket_id=ticket_id,
                    sender_role=sender_role,
                    sender_telegram_user_id=sender_telegram_user_id,
                    text=text,
                    created_at=created_at,
                    updated_at=created_at,
                )
                .returning(SupportMessage)
            )
        ).scalar_one()

    async def _get_user_identity(
        self,
        user_id: int,
    ) -> tuple[int, str | None, str, str | None]:
        row = (
            await self.session.execute(
                select(
                    User.telegram_user_id,
                    User.username,
                    User.first_name,
                    User.last_name,
                ).where(User.id == user_id)
            )
        ).one_or_none()
        if row is None:
            raise SupportTicketNotFoundError("Ticket user does not exist")
        return row.tuple()

    async def _raise_user_transition_error(
        self,
        ticket_id: int,
        user_telegram_id: int,
    ) -> None:
        row = (
            await self.session.execute(
                self._ticket_select().where(
                    SupportTicket.id == ticket_id,
                    User.telegram_user_id == user_telegram_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise SupportTicketNotFoundError("Support ticket does not exist")
        raise SupportTicketStateError("Support ticket is closed")

    @staticmethod
    def _latest_sender_role():
        return (
            select(SupportMessage.sender_role)
            .where(SupportMessage.ticket_id == SupportTicket.id)
            .order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc())
            .limit(1)
            .correlate(SupportTicket)
            .scalar_subquery()
        )

    @classmethod
    def _admin_filter_condition(cls, filter_by: str):
        latest_sender = cls._latest_sender_role()
        if filter_by == SupportTicketFilter.OPEN.value:
            return SupportTicket.status == SupportTicketStatus.OPEN.value
        if filter_by == SupportTicketFilter.CLOSED.value:
            return SupportTicket.status == SupportTicketStatus.CLOSED.value
        if filter_by == SupportTicketFilter.ANSWERED.value:
            return latest_sender == SupportSenderRole.ADMIN.value
        if filter_by == SupportTicketFilter.WAITING.value:
            return (SupportTicket.status != SupportTicketStatus.CLOSED.value) & (
                latest_sender == SupportSenderRole.USER.value
            )
        return None

    @classmethod
    def _ticket_select(cls):
        return select(
            SupportTicket,
            User.telegram_user_id,
            User.username,
            User.first_name,
            User.last_name,
            cls._latest_sender_role().label("last_sender_role"),
        ).join(
            User,
            User.id == SupportTicket.user_id,
        )
