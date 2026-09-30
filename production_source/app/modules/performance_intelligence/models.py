"""Persistent analytics snapshots. No signal generation dependencies."""

from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BigIntIdentityMixin, TimestampMixin


class PerformanceMetric(BigIntIdentityMixin, TimestampMixin, Base):
    __tablename__ = "performance_metrics"

    period: Mapped[str] = mapped_column(String(16), nullable=False)
    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    loss_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    average_rr: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    expectancy: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    profit_factor: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class PatternStatistic(BigIntIdentityMixin, TimestampMixin, Base):
    __tablename__ = "pattern_statistics"

    pattern: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str | None] = mapped_column(String(16))
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    average_rr: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    failure_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)


class FailureAnalysis(BigIntIdentityMixin, TimestampMixin, Base):
    __tablename__ = "failure_analysis"

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[str | None] = mapped_column(Text)


class DecisionQualityScore(BigIntIdentityMixin, TimestampMixin, Base):
    __tablename__ = "decision_quality_scores"

    signal_id: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
