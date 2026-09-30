"""Persistent signal, target, and immutable lifecycle-event models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.favorites.models import UserFavorite


class SignalDirection(StrEnum):
    """Supported market directions."""

    LONG = "LONG"
    SHORT = "SHORT"


class SignalStatus(StrEnum):
    """Persistence lifecycle available to future signal services."""

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class SignalPublicationScope(StrEnum):
    """Audience scope for one persisted signal."""

    INTERNAL = "INTERNAL"
    PRIVATE_TEST = "PRIVATE_TEST"
    PUBLIC = "PUBLIC"
    VIP = "VIP"
    PUBLIC_VIP = "PUBLIC_VIP"


class SignalTargetStatus(StrEnum):
    """Lifecycle of one ordered take-profit target."""

    PENDING = "PENDING"
    HIT = "HIT"
    CANCELLED = "CANCELLED"


class SignalEventType(StrEnum):
    """Audit events reserved for future signal business operations."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    PUBLISHED = "PUBLISHED"
    ENTRY_ACTIVATED = "ENTRY_ACTIVATED"
    TARGET_ADDED = "TARGET_ADDED"
    TARGET_HIT = "TARGET_HIT"
    STOP_LOSS_UPDATED = "STOP_LOSS_UPDATED"
    STOP_HIT = "STOP_HIT"
    RUNNER_CLOSED_ALWAYS_IN_REVERSAL = "RUNNER_CLOSED_ALWAYS_IN_REVERSAL"
    OUTCOME_AMBIGUOUS = "OUTCOME_AMBIGUOUS"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class Signal(BigIntIdentityMixin, TimestampMixin, Base):
    """One manually managed trading signal; no generation logic is present."""

    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint("direction IN ('LONG', 'SHORT')", name="signal_direction"),
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'CLOSED', 'CANCELLED')",
            name="signal_status",
        ),
        CheckConstraint(
            "char_length(btrim(symbol)) BETWEEN 1 AND 32 AND symbol = upper(symbol)",
            name="signal_symbol",
        ),
        CheckConstraint(
            "entry_price > 0 AND stop_loss > 0 AND leverage > 0",
            name="signal_positive_values",
        ),
        CheckConstraint(
            "publication_scope IN ('INTERNAL','PRIVATE_TEST','PUBLIC','VIP','PUBLIC_VIP')",
            name="signal_publication_scope",
        ),
        CheckConstraint(
            "((status IN ('DRAFT', 'OPEN') AND closed_at IS NULL) OR "
            "(status IN ('CLOSED', 'CANCELLED') AND closed_at IS NOT NULL))",
            name="signal_closed_at_status",
        ),
        Index("ix_signals_status_created_at", "status", "created_at"),
        Index("ix_signals_symbol_status", "symbol", "status"),
        Index(
            "ix_signals_scope_status_created_at",
            "publication_scope",
            "status",
            "created_at",
        ),
    )

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    leverage: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SignalStatus.DRAFT.value,
        server_default=sql_text("'DRAFT'"),
    )
    description: Mapped[str | None] = mapped_column(Text)
    publication_scope: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SignalPublicationScope.PUBLIC.value,
        server_default=sql_text("'PUBLIC'"),
    )
    profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    targets: Mapped[list[SignalTarget]] = relationship(
        back_populates="signal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SignalTarget.target_number",
    )
    events: Mapped[list[SignalEvent]] = relationship(
        back_populates="signal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SignalEvent.id",
    )
    favorites: Mapped[list[UserFavorite]] = relationship(
        back_populates="signal",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SignalTarget(BigIntIdentityMixin, TimestampMixin, Base):
    """One ordered and independently tracked take-profit target."""

    __tablename__ = "signal_targets"
    __table_args__ = (
        UniqueConstraint(
            "signal_id",
            "target_number",
            name="uq_signal_targets_signal_target_number",
        ),
        CheckConstraint("target_number > 0", name="signal_target_positive_number"),
        CheckConstraint("target_price > 0", name="signal_target_positive_price"),
        CheckConstraint(
            "status IN ('PENDING', 'HIT', 'CANCELLED')",
            name="signal_target_status",
        ),
        CheckConstraint(
            "((status = 'HIT' AND hit_at IS NOT NULL AND profit_loss IS NOT NULL) OR "
            "(status IN ('PENDING', 'CANCELLED') AND hit_at IS NULL "
            "AND profit_loss IS NULL))",
            name="signal_target_hit_state",
        ),
        Index(
            "ix_signal_targets_signal_status_number",
            "signal_id",
            "status",
            "target_number",
        ),
    )

    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SignalTargetStatus.PENDING.value,
        server_default=sql_text("'PENDING'"),
    )
    hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    signal: Mapped[Signal] = relationship(back_populates="targets")


class SignalEvent(BigIntIdentityMixin, Base):
    """Append-only audit event used by future services and notifications."""

    __tablename__ = "signal_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CREATED', 'UPDATED', 'PUBLISHED', 'ENTRY_ACTIVATED', "
            "'TARGET_ADDED', 'TARGET_HIT', 'STOP_LOSS_UPDATED', 'STOP_HIT', "
            "'OUTCOME_AMBIGUOUS', 'CLOSED', 'CANCELLED', 'RUNNER_CLOSED_ALWAYS_IN_REVERSAL')",
            name="signal_event_type",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="signal_event_metadata_object",
        ),
        Index("ix_signal_events_signal_created_id", "signal_id", "created_at", "id"),
        Index("ix_signal_events_type_created_at", "event_type", "created_at"),
    )

    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    signal: Mapped[Signal] = relationship(back_populates="events")
