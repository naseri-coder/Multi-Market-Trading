"""Required Telegram channel ORM model."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin


class Channel(BigIntIdentityMixin, TimestampMixin, Base):
    """Telegram channel that can later participate in membership lock policy."""

    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("telegram_chat_id", name="uq_channels_telegram_chat_id"),
        CheckConstraint("sort_order >= 0", name="non_negative_sort_order"),
        Index("ix_channels_is_active_sort_order", "is_active", "sort_order"),
    )

    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    invite_link: Mapped[str | None] = mapped_column(String(2048))
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default=true(),
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
