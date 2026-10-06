"""Persistent signal-strategy routing configuration."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin


class SignalStrategyConfig(BigIntIdentityMixin, TimestampMixin, Base):
    __tablename__ = "signal_strategy_configs"
    __table_args__ = (
        UniqueConstraint("strategy_code", name="uq_signal_strategy_configs_strategy_code"),
        CheckConstraint(
            "strategy_code IN ('BROOKS','MARC')",
            name="strategy_code",
        ),
        CheckConstraint(
            "private_channel_id IS NULL OR private_channel_id < 0",
            name="private_channel_negative",
        ),
        Index("ix_signal_strategy_configs_enabled", "enabled"),
    )

    strategy_code: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    engine_ready: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    private_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    private_channel_title: Mapped[str | None] = mapped_column(String(255))
    private_channel_username: Mapped[str | None] = mapped_column(String(64))
    updated_by_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
