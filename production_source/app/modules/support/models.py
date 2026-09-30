"""Persistent support tickets and chronological messages."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin


class SupportTicketStatus(StrEnum):
    """Supported ticket workflow states."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class SupportSenderRole(StrEnum):
    """Author role for one support message."""

    USER = "USER"
    ADMIN = "ADMIN"


class SupportTicket(BigIntIdentityMixin, TimestampMixin, Base):
    """One user-owned support conversation."""

    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'CLOSED')",
            name="support_ticket_status",
        ),
        Index("ix_support_tickets_status_last_message", "status", "last_message_at"),
        Index("ix_support_tickets_user_status", "user_id", "status"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SupportTicketStatus.OPEN.value,
        server_default=sql_text("'OPEN'"),
    )
    assigned_admin_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportMessage(BigIntIdentityMixin, TimestampMixin, Base):
    """One immutable text message inside a support ticket."""

    __tablename__ = "support_messages"
    __table_args__ = (
        CheckConstraint(
            "sender_role IN ('USER', 'ADMIN')",
            name="support_message_sender_role",
        ),
        Index("ix_support_messages_ticket_created", "ticket_id", "created_at"),
    )

    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_role: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
