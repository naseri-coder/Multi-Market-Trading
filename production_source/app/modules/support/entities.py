"""Framework-independent support ticket records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SupportTicketFilter(StrEnum):
    """Administrator ticket-list filters."""

    ALL = "all"
    OPEN = "open"
    CLOSED = "closed"
    ANSWERED = "answered"
    WAITING = "waiting"


@dataclass(frozen=True, slots=True)
class SupportTicketRecord:
    """Stable support ticket read model."""

    id: int
    user_id: int
    user_telegram_id: int
    subject: str
    status: str
    assigned_admin_telegram_user_id: int | None
    last_message_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    user_username: str | None = None
    user_first_name: str = ""
    user_last_name: str | None = None
    last_sender_role: str | None = None


@dataclass(frozen=True, slots=True)
class SupportMessageRecord:
    """Stable chronological support message."""

    id: int
    ticket_id: int
    sender_role: str
    sender_telegram_user_id: int
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SupportThread:
    """One ticket with its ordered messages."""

    ticket: SupportTicketRecord
    messages: tuple[SupportMessageRecord, ...]
    total_messages: int = 0
    page: int = 1
    total_pages: int = 1


@dataclass(frozen=True, slots=True)
class SupportMessageResult:
    """Ticket and newly persisted message returned to adapters."""

    ticket: SupportTicketRecord
    message: SupportMessageRecord


@dataclass(frozen=True, slots=True)
class SupportTicketPage:
    """One bounded administrator ticket-list page."""

    tickets: tuple[SupportTicketRecord, ...]
    filter: str
    page: int
    page_size: int
    total_items: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class UserSupportTicketPage:
    """One bounded page from a user's complete ticket archive."""

    tickets: tuple[SupportTicketRecord, ...]
    page: int
    page_size: int
    total_items: int
    total_pages: int
