"""Support ticket business validation and workflow transitions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.support.entities import (
    SupportMessageResult,
    SupportThread,
    SupportTicketFilter,
    SupportTicketPage,
    SupportTicketRecord,
    UserSupportTicketPage,
)
from app.modules.support.errors import InvalidSupportMessageError
from app.modules.support.models import SupportTicketStatus
from app.modules.support.repository import SupportRepository

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class SupportService:
    """Own support validation independently from Telegram handlers."""

    def __init__(self, repository: SupportRepository, *, clock: Clock = utc_now) -> None:
        self.repository = repository
        self.clock = clock

    async def create_ticket(
        self,
        *,
        user_id: int,
        user_telegram_id: int,
        text: str,
        subject: str | None = None,
    ) -> SupportMessageResult:
        self._validate_positive_ids(user_id, user_telegram_id)
        normalized = self._normalize_text(text)
        normalized_subject = (
            self.normalize_subject(subject)
            if subject is not None
            else normalized.splitlines()[0].strip()[:120]
        )
        return await self.repository.create_ticket(
            user_id=user_id,
            user_telegram_id=user_telegram_id,
            subject=normalized_subject,
            text=normalized,
            created_at=self._now(),
        )

    async def list_user_tickets(
        self,
        user_telegram_id: int,
        *,
        limit: int = 20,
    ) -> tuple[SupportTicketRecord, ...]:
        self._validate_list_input(user_telegram_id, limit)
        return await self.repository.list_user_tickets(user_telegram_id, limit=limit)

    async def get_user_ticket_page(
        self,
        user_telegram_id: int,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> UserSupportTicketPage:
        """Return a validated page from one user's complete ticket archive."""
        self._validate_positive_ids(user_telegram_id)
        self._validate_page(page, page_size)
        total_items = await self.repository.count_user_tickets(user_telegram_id)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        tickets = await self.repository.list_user_ticket_page(
            user_telegram_id,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        return UserSupportTicketPage(
            tickets=tickets,
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    async def list_admin_tickets(self, *, limit: int = 30) -> tuple[SupportTicketRecord, ...]:
        if not 1 <= limit <= 100:
            raise InvalidSupportMessageError("Ticket list limit is invalid")
        return await self.repository.list_admin_tickets(limit=limit)

    async def get_admin_ticket_page(
        self,
        *,
        filter_by: str = SupportTicketFilter.ALL.value,
        page: int = 1,
        page_size: int = 10,
    ) -> SupportTicketPage:
        """Return a validated and clamped administrator ticket page."""
        if filter_by not in {item.value for item in SupportTicketFilter}:
            raise InvalidSupportMessageError("Unsupported support ticket filter")
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise InvalidSupportMessageError("Ticket page must be a positive integer")
        if page_size != 10:
            raise InvalidSupportMessageError("Administrator ticket page size must be 10")

        total_items = await self.repository.count_admin_tickets(filter_by=filter_by)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        tickets = await self.repository.list_admin_ticket_page(
            filter_by=filter_by,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        return SupportTicketPage(
            tickets=tickets,
            filter=filter_by,
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    async def get_user_thread(
        self,
        ticket_id: int,
        user_telegram_id: int,
        *,
        message_page: int = 1,
    ) -> SupportThread:
        self._validate_positive_ids(ticket_id, user_telegram_id)
        self._validate_page(message_page, 10)
        return await self.repository.get_thread(
            ticket_id,
            user_telegram_id=user_telegram_id,
            message_page=message_page,
            message_page_size=10,
        )

    async def get_admin_thread(
        self,
        ticket_id: int,
        *,
        message_page: int = 1,
    ) -> SupportThread:
        self._validate_positive_ids(ticket_id)
        self._validate_page(message_page, 10)
        return await self.repository.get_thread(
            ticket_id,
            message_page=message_page,
            message_page_size=10,
        )

    async def add_user_message(
        self,
        ticket_id: int,
        user_telegram_id: int,
        text: str,
    ) -> SupportMessageResult:
        self._validate_positive_ids(ticket_id, user_telegram_id)
        return await self.repository.add_user_message(
            ticket_id,
            user_telegram_id,
            text=self._normalize_text(text),
            created_at=self._now(),
        )

    async def add_admin_message(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        text: str,
    ) -> SupportMessageResult:
        self._validate_positive_ids(ticket_id, admin_telegram_id)
        return await self.repository.add_admin_message(
            ticket_id,
            admin_telegram_id,
            text=self._normalize_text(text),
            created_at=self._now(),
        )

    async def close_by_user(
        self,
        ticket_id: int,
        user_telegram_id: int,
    ) -> SupportTicketRecord:
        self._validate_positive_ids(ticket_id, user_telegram_id)
        return await self.repository.close_by_user(
            ticket_id,
            user_telegram_id,
            closed_at=self._now(),
        )

    async def set_status(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        status: str,
    ) -> SupportTicketRecord:
        self._validate_positive_ids(ticket_id, admin_telegram_id)
        if status not in {item.value for item in SupportTicketStatus}:
            raise InvalidSupportMessageError("Unsupported support ticket status")
        return await self.repository.set_status(
            ticket_id,
            admin_telegram_id,
            status=status,
            changed_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("SupportService clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = text.strip() if isinstance(text, str) else ""
        if not normalized or len(normalized) > 4000:
            raise InvalidSupportMessageError("Support message must contain 1 to 4000 characters")
        return normalized

    @staticmethod
    def normalize_subject(subject: str) -> str:
        """Validate and normalize an explicitly supplied ticket subject."""
        normalized = subject.strip() if isinstance(subject, str) else ""
        if not normalized or len(normalized) > 120 or "\n" in normalized or "\r" in normalized:
            raise InvalidSupportMessageError(
                "Support subject must contain 1 to 120 characters on one line"
            )
        return normalized

    @staticmethod
    def _validate_positive_ids(*values: int) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values
        ):
            raise InvalidSupportMessageError("Support identifiers must be positive integers")

    @staticmethod
    def _validate_list_input(user_telegram_id: int, limit: int) -> None:
        SupportService._validate_positive_ids(user_telegram_id)
        if not 1 <= limit <= 100:
            raise InvalidSupportMessageError("Ticket list limit is invalid")

    @staticmethod
    def _validate_page(page: int, page_size: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise InvalidSupportMessageError("Support page must be a positive integer")
        if page_size != 10:
            raise InvalidSupportMessageError("Support page size must be 10")
