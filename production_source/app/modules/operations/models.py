"""Persistent operational state for production automation workers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SignalLifecycleState(Base):
    __tablename__ = "signal_lifecycle_states"
    __table_args__ = (
        CheckConstraint(
            "state IN ('WAITING_ENTRY','ACTIVE','COMPLETE','AMBIGUOUS')",
            name="state",
        ),
    )

    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("signals.id", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sql_text("'WAITING_ENTRY'")
    )
    entry_activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_processed_candle_close: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_market_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    last_message_event_id: Mapped[int | None] = mapped_column(BigInteger)
    ambiguous_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VipEntitlementState(Base):
    __tablename__ = "vip_entitlement_states"
    __table_args__ = (
        CheckConstraint(
            "membership_state IN ('UNKNOWN','MEMBER','INVITE_SENT','REMOVED','ADMIN_UNMANAGED','ERROR')",
            name="membership_state",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    desired_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    membership_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sql_text("'UNKNOWN'")
    )
    last_invite_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_invite_link: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PaymentSettlementState(Base):
    __tablename__ = "payment_settlement_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SETTLED','DEFERRED','FAILED')",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
    )

    payment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=sql_text("'PENDING'")
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RuntimeHealth(Base):
    __tablename__ = "runtime_health"
    __table_args__ = (
        CheckConstraint("status IN ('OK','DEGRADED','ERROR')", name="status"),
    )

    component: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
