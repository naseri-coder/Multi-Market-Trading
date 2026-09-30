"""Subscription plan and user subscription ORM models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.payments.models import Payment
    from app.modules.users.models import User


class SubscriptionStatus(StrEnum):
    """Supported subscription lifecycle states."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class SubscriptionPlan(BigIntIdentityMixin, TimestampMixin, Base):
    """Editable commercial plan definition without payment integration."""

    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100",
            name="valid_name",
        ),
        CheckConstraint("duration_days > 0", name="positive_duration"),
        CheckConstraint("price >= 0", name="non_negative_price"),
        CheckConstraint(
            "currency ~ '^[A-Z0-9]{2,12}$'",
            name="valid_currency",
        ),
        Index("uq_subscription_plans_name_ci", text("lower(name)"), unique=True),
        Index("ix_subscription_plans_active_id", "is_active", "id"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="plan",
        passive_deletes=True,
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="plan",
        passive_deletes=True,
    )


class Subscription(BigIntIdentityMixin, TimestampMixin, Base):
    """One time-bounded user entitlement with immutable plan terms."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'EXPIRED')",
            name="status",
        ),
        CheckConstraint("expires_at > starts_at", name="valid_period"),
        CheckConstraint(
            "((status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status = 'EXPIRED' AND ended_at IS NOT NULL))",
            name="status_end_state",
        ),
        CheckConstraint("duration_days > 0", name="positive_duration"),
        CheckConstraint("price >= 0", name="non_negative_price"),
        CheckConstraint(
            "char_length(btrim(plan_name)) BETWEEN 1 AND 100",
            name="valid_plan_name",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z0-9]{2,12}$'",
            name="valid_currency",
        ),
        Index(
            "uq_subscriptions_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "ix_subscriptions_user_status_expires",
            "user_id",
            "status",
            "expires_at",
        ),
        Index("ix_subscriptions_plan_status", "plan_id", "status"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SubscriptionStatus.ACTIVE.value,
        server_default=text("'ACTIVE'"),
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")
    plan: Mapped[SubscriptionPlan] = relationship(back_populates="subscriptions")
    payment: Mapped[Payment | None] = relationship(
        back_populates="subscription",
        uselist=False,
        passive_deletes=True,
    )
