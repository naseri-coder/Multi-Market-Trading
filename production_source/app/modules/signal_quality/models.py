"""Persistent signal quality assessment model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin


class SignalQualityAssessment(
    BigIntIdentityMixin,
    Base,
):
    """
    Stores AI, Risk, Intelligence and Gate evaluation results.
    """

    __tablename__ = "signal_quality_assessments"

    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "signals.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    ai_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    risk_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    final_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )

    quality_grade: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )

    market_regime: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    gate_approved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )

    gate_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    extra_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
