"""ORM models for signal automation metadata and rule evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SignalAutomationMetadata(Base):
    __tablename__ = "signal_automation_metadata"
    __table_args__ = (
        CheckConstraint("producer IN ('BROOKS','MARC')", name="producer"),
        CheckConstraint(
            "generation_mode IN ('SHADOW','PAPER','LIVE')",
            name="generation_mode",
        ),
        CheckConstraint("jsonb_typeof(reasoning) = 'array'", name="reasoning_array"),
        CheckConstraint("jsonb_typeof(rule_ids) = 'array'", name="rule_ids_array"),
        CheckConstraint("jsonb_typeof(failed_rules) = 'array'", name="failed_rules_array"),
        CheckConstraint(
            "jsonb_typeof(analysis_metadata) = 'object'",
            name="analysis_metadata_object",
        ),
        UniqueConstraint(
            "producer",
            "source_signal_id",
            name="uq_signal_automation_metadata_producer_source_signal",
        ),
        UniqueConstraint(
            "producer",
            "idempotency_key",
            name="uq_signal_automation_metadata_producer_idempotency",
        ),
        Index(
            "uq_signal_automation_metadata_ii_opportunity",
            "producer",
            "generation_mode",
            "opportunity_variant",
            "opportunity_key",
            unique=True,
            postgresql_where=sql_text(
                "opportunity_variant = 'CH6_II_PAIR_STOP_V1' "
                "AND opportunity_key IS NOT NULL"
            ),
        ),
        Index(
            "ix_signal_automation_metadata_snapshot_hash",
            "market_snapshot_hash",
        ),
        Index(
            "ix_signal_automation_metadata_mode_created_at",
            "generation_mode",
            "created_at",
        ),
        Index(
            "ix_signal_automation_metadata_performance_mode",
            "counts_toward_performance",
            "generation_mode",
        ),
    )

    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("signals.id", ondelete="CASCADE"),
        primary_key=True,
    )
    producer: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    setup_type: Mapped[str | None] = mapped_column(String(64))
    source_signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    opportunity_variant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opportunity_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market_snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(128), nullable=False)
    configuration_version: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    rule_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    failed_rules: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    analysis_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    counts_toward_performance: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )



class SignalRuleEvidence(Base):
    __tablename__ = "signal_rule_evidence"
    __table_args__ = (
        CheckConstraint("ordinal > 0", name="ordinal"),
        CheckConstraint(
            "status IN ('PASS','FAIL','NOT_APPLICABLE','AMBIGUOUS')",
            name="status",
        ),
        CheckConstraint("jsonb_typeof(source_pages) = 'array'", name="source_pages_array"),
        CheckConstraint("jsonb_typeof(evidence) = 'array'", name="evidence_array"),
        CheckConstraint(
            "jsonb_typeof(failed_conditions) = 'array'",
            name="failed_conditions_array",
        ),
        CheckConstraint(
            "jsonb_typeof(confidence_components) = 'array'",
            name="confidence_components_array",
        ),
        UniqueConstraint(
            "signal_id",
            "ordinal",
            name="uq_signal_rule_evidence_signal_ordinal",
        ),
        Index("ix_signal_rule_evidence_signal_rule", "signal_id", "rule_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_pages: Mapped[list[int]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    evidence: Mapped[list[list[str]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    failed_conditions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    confidence_components: Mapped[list[list[str]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

