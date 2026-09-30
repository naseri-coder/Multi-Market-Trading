"""Gateway-independent payment ORM model."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.subscriptions.models import Subscription, SubscriptionPlan
    from app.modules.users.models import User


class PaymentStatus(StrEnum):
    """Supported payment lifecycle states."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Payment(BigIntIdentityMixin, TimestampMixin, Base):
    """One auditable payment attempt, independent of any real gateway."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint(
            "payment_reference",
            name="uq_payments_payment_reference",
        ),
        UniqueConstraint(
            "subscription_id",
            name="uq_payments_subscription_id",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SUCCESS', 'FAILED', 'CANCELLED')",
            name="status",
        ),
        CheckConstraint(
            "payment_reference ~ '^[A-Z0-9_-]{12,64}$'",
            name="valid_payment_reference",
        ),
        CheckConstraint("telegram_user_id > 0", name="positive_telegram_user_id"),
        CheckConstraint(
            "char_length(btrim(plan_name)) BETWEEN 1 AND 100",
            name="valid_plan_name",
        ),
        CheckConstraint("duration_days > 0", name="positive_duration"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint(
            "currency ~ '^[A-Z0-9]{2,12}$'",
            name="valid_currency",
        ),
        CheckConstraint(
            "((status = 'PENDING' AND finalized_at IS NULL) OR "
            "(status IN ('SUCCESS', 'FAILED', 'CANCELLED') "
            "AND finalized_at IS NOT NULL))",
            name="status_finalized_state",
        ),
        CheckConstraint(
            "((status = 'FAILED' AND failure_reason IS NOT NULL) OR "
            "(status <> 'FAILED' AND failure_reason IS NULL))",
            name="failure_reason_state",
        ),
        CheckConstraint(
            "provider_reference IS NULL OR provider IS NOT NULL",
            name="provider_reference_state",
        ),
        CheckConstraint(
            "provider IS NULL OR provider ~ '^[A-Z0-9_-]{2,32}$'",
            name="valid_provider",
        ),
        CheckConstraint(
            "provider_reference IS NULL OR "
            "char_length(btrim(provider_reference)) BETWEEN 1 AND 128",
            name="valid_provider_reference",
        ),
        CheckConstraint(
            "failure_reason IS NULL OR "
            "char_length(btrim(failure_reason)) BETWEEN 1 AND 1000",
            name="valid_failure_reason",
        ),
        Index("ix_payments_user_created_id", "user_id", "created_at", "id"),
        Index("ix_payments_status_created_at", "status", "created_at"),
        Index(
            "uq_payments_provider_reference",
            "provider",
            "provider_reference",
            unique=True,
            postgresql_where=text("provider_reference IS NOT NULL"),
        ),
    )

    payment_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    plan_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
    )
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PaymentStatus.PENDING.value,
        server_default=text("'PENDING'"),
    )
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_reference: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User | None] = relationship(back_populates="payments")
    plan: Mapped[SubscriptionPlan | None] = relationship(back_populates="payments")
    subscription: Mapped[Subscription | None] = relationship(back_populates="payment")
