"""User ORM model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.admins.models import Admin
    from app.modules.favorites.models import UserFavorite
    from app.modules.notifications.models import UserNotificationSetting
    from app.modules.payments.models import Payment
    from app.modules.referrals.models import Referral
    from app.modules.subscriptions.models import Subscription


class UserStatus(StrEnum):
    """Persistence-level user lifecycle values."""

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    DEACTIVATED = "DEACTIVATED"


class User(BigIntIdentityMixin, TimestampMixin, Base):
    """Telegram user identity and profile snapshot."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        UniqueConstraint("referral_code", name="uq_users_referral_code"),
        CheckConstraint(
            "status IN ('ACTIVE', 'BLOCKED', 'DEACTIVATED')",
            name="user_status",
        ),
        CheckConstraint(
            "referral_code IS NULL OR "
            "referral_code ~ '^R[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{11}$'",
            name="valid_referral_code",
        ),
        Index("ix_users_status_last_activity", "status", "last_activity"),
        Index("ix_users_created_at", "created_at"),
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(16))
    is_bot: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=false(),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserStatus.ACTIVE.value,
        server_default=text("'ACTIVE'"),
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    referral_code: Mapped[str | None] = mapped_column(String(12))

    admin: Mapped[Admin | None] = relationship(back_populates="user", uselist=False)
    favorites: Mapped[list[UserFavorite]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notification_settings: Mapped[list[UserNotificationSetting]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )
    referrals_sent: Mapped[list[Referral]] = relationship(
        back_populates="referrer",
        foreign_keys="Referral.referrer_user_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    referral_received: Mapped[Referral | None] = relationship(
        back_populates="referred_user",
        foreign_keys="Referral.referred_user_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
