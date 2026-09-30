"""ORM model for outbound signal delivery state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SignalDelivery(Base):
    __tablename__ = "signal_deliveries"
    __table_args__ = (
        CheckConstraint(
            "channel_kind IN ('TELEGRAM_PRIVATE_TEST','TELEGRAM_VIP')",
            name="channel_kind",
        ),
        CheckConstraint(
            "status IN ('PENDING','SENDING','SENT','FAILED','AMBIGUOUS')",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        UniqueConstraint(
            "signal_id",
            "channel_kind",
            "destination_id",
            name="uq_signal_deliveries_signal_destination",
        ),
        Index("ix_signal_deliveries_status_updated_at", "status", "updated_at"),
        Index("ix_signal_deliveries_signal_id", "signal_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    destination_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    external_message_id: Mapped[str | None] = mapped_column(String(128))
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
