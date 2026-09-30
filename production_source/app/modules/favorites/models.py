"""Persistent user-to-signal favorite association."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin

if TYPE_CHECKING:
    from app.modules.signals.models import Signal
    from app.modules.users.models import User


class UserFavorite(BigIntIdentityMixin, Base):
    """One unique user bookmark for one public signal."""

    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "signal_id",
            name="uq_user_favorites_user_signal",
        ),
        Index(
            "ix_user_favorites_user_created_id",
            "user_id",
            "created_at",
            "id",
        ),
        Index("ix_user_favorites_signal_id", "signal_id"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="favorites")
    signal: Mapped[Signal] = relationship(back_populates="favorites")
