"""Bot setting ORM model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin

if TYPE_CHECKING:
    from app.modules.admins.models import Admin


class BotSettingValueType(StrEnum):
    """Supported logical types stored in the JSONB value column."""

    STRING = "STRING"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    JSON = "JSON"


class BotSetting(BigIntIdentityMixin, TimestampMixin, Base):
    """Typed global setting that excludes environment-owned secrets."""

    __tablename__ = "bot_settings"
    __table_args__ = (
        UniqueConstraint("key", name="uq_bot_settings_key"),
        CheckConstraint(
            "value_type IN ('STRING', 'INTEGER', 'BOOLEAN', 'JSON')",
            name="value_type",
        ),
        Index("ix_bot_settings_updated_by_admin_id", "updated_by_admin_id"),
    )

    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=false(),
    )
    description: Mapped[str | None] = mapped_column(Text)
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admins.id", ondelete="SET NULL"),
    )

    updated_by: Mapped[Admin | None] = relationship(back_populates="updated_settings")
