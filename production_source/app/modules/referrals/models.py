"""Immutable referral ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin

if TYPE_CHECKING:
    from app.modules.users.models import User


class Referral(BigIntIdentityMixin, Base):
    """One immutable attribution from a referrer to a newly registered user."""

    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint(
            "referred_user_id",
            name="uq_referrals_referred_user_id",
        ),
        CheckConstraint(
            "referrer_user_id <> referred_user_id",
            name="different_users",
        ),
        CheckConstraint(
            "referral_code ~ '^R[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{11}$'",
            name="valid_referral_code",
        ),
        CheckConstraint(
            "reward_granted = false",
            name="reward_disabled",
        ),
        Index(
            "ix_referrals_referrer_created_id",
            "referrer_user_id",
            "created_at",
            "id",
        ),
    )

    referrer_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    referred_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    referral_code: Mapped[str] = mapped_column(String(12), nullable=False)
    reward_granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    referrer: Mapped[User] = relationship(
        back_populates="referrals_sent",
        foreign_keys=[referrer_user_id],
    )
    referred_user: Mapped[User] = relationship(
        back_populates="referral_received",
        foreign_keys=[referred_user_id],
    )
