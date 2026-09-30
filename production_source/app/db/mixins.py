"""Reusable persistence fields shared by ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, func
from sqlalchemy.orm import Mapped, mapped_column


class BigIntIdentityMixin:
    """Provide a database-generated internal bigint primary key."""

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)


class TimestampMixin:
    """Provide timezone-aware creation and modification timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
