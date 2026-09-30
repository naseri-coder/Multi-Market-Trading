"""Persistent broadcast drafts, delivery runs, and recipient outcomes."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin


class BroadcastContentType(StrEnum):
    """Supported broadcast content families."""

    TEXT = "TEXT"
    MEDIA = "MEDIA"
    FORWARD = "FORWARD"


class BroadcastMediaType(StrEnum):
    """Telegram media types sent without forwarding the source message."""

    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    DOCUMENT = "DOCUMENT"
    ANIMATION = "ANIMATION"
    AUDIO = "AUDIO"
    VOICE = "VOICE"


class BroadcastStatus(StrEnum):
    """Lifecycle of a persisted broadcast."""

    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class BroadcastRecipientStatus(StrEnum):
    """Delivery outcome for one snapshot recipient."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class Broadcast(BigIntIdentityMixin, TimestampMixin, Base):
    """Immutable message content plus aggregate delivery counters."""

    __tablename__ = "broadcasts"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('TEXT', 'MEDIA', 'FORWARD')",
            name="broadcast_content_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PROCESSING', 'COMPLETED', 'CANCELLED', 'FAILED')",
            name="broadcast_status",
        ),
        CheckConstraint(
            "media_type IS NULL OR media_type IN "
            "('PHOTO', 'VIDEO', 'DOCUMENT', 'ANIMATION', 'AUDIO', 'VOICE')",
            name="broadcast_media_type",
        ),
        CheckConstraint(
            "((content_type = 'TEXT' AND text IS NOT NULL AND media_type IS NULL "
            "AND media_file_id IS NULL AND caption IS NULL "
            "AND source_chat_id IS NULL AND source_message_id IS NULL) OR "
            "(content_type = 'MEDIA' AND text IS NULL AND media_type IS NOT NULL "
            "AND media_file_id IS NOT NULL AND source_chat_id IS NULL "
            "AND source_message_id IS NULL) OR "
            "(content_type = 'FORWARD' AND text IS NULL AND media_type IS NULL "
            "AND media_file_id IS NULL AND caption IS NULL "
            "AND source_chat_id IS NOT NULL AND source_chat_id <> 0 "
            "AND source_message_id IS NOT NULL AND source_message_id > 0))",
            name="broadcast_content_shape",
        ),
        CheckConstraint(
            "total_recipients >= 0 AND sent_count >= 0 AND failed_count >= 0 "
            "AND blocked_count >= 0 AND "
            "sent_count + failed_count + blocked_count <= total_recipients",
            name="broadcast_non_negative_counts",
        ),
        Index("ix_broadcasts_status_created_at", "status", "created_at"),
        Index(
            "ix_broadcasts_created_by_status",
            "created_by_telegram_user_id",
            "status",
        ),
    )

    created_by_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(16))
    media_file_id: Mapped[str | None] = mapped_column(String(512))
    caption: Mapped[str | None] = mapped_column(Text)
    source_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    source_message_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=BroadcastStatus.DRAFT.value,
        server_default=sql_text("'DRAFT'"),
    )
    total_recipients: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    sent_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    blocked_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BroadcastRecipient(BigIntIdentityMixin, TimestampMixin, Base):
    """Snapshot of one eligible user and the final Telegram delivery outcome."""

    __tablename__ = "broadcast_recipients"
    __table_args__ = (
        UniqueConstraint(
            "broadcast_id",
            "user_id",
            name="uq_broadcast_recipients_broadcast_user",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED', 'BLOCKED')",
            name="broadcast_recipient_status",
        ),
        CheckConstraint("attempts >= 0", name="broadcast_recipient_attempts"),
        Index(
            "ix_broadcast_recipients_broadcast_status_id",
            "broadcast_id",
            "status",
            "id",
        ),
        Index("ix_broadcast_recipients_user_id", "user_id"),
    )

    broadcast_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("broadcasts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=BroadcastRecipientStatus.PENDING.value,
        server_default=sql_text("'PENDING'"),
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
