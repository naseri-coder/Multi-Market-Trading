"""Persistent per-user notification preferences."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.users.models import User


class NotificationType(StrEnum):
    """Notification categories exposed to users and future delivery workers."""

    NEW_SIGNAL = "NEW_SIGNAL"
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    SIGNAL_UPDATED = "SIGNAL_UPDATED"
    SIGNAL_CLOSED = "SIGNAL_CLOSED"
    SYSTEM_NOTIFICATION = "SYSTEM_NOTIFICATION"


class UserNotificationSetting(BigIntIdentityMixin, TimestampMixin, Base):
    """One explicit notification-category preference for one user."""

    __tablename__ = "user_notification_settings"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "notification_type",
            name="uq_user_notification_settings_user_type",
        ),
        CheckConstraint(
            "notification_type IN ("
            "'NEW_SIGNAL', 'TARGET_HIT', 'STOP_HIT', "
            "'SIGNAL_UPDATED', 'SIGNAL_CLOSED', 'SYSTEM_NOTIFICATION'"
            ")",
            name="notification_type",
        ),
        Index(
            "ix_user_notification_settings_type_enabled_user",
            "notification_type",
            "is_enabled",
            "user_id",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    user: Mapped[User] = relationship(back_populates="notification_settings")
