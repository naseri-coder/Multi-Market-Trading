"""Add Brooks automation metadata, rule evidence, and publication scope.

Revision ID: 20260902_0012
Revises: 20260902_0011
Create Date: 2026-09-02 10:00:00
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0012"
down_revision: str | None = "20260902_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve all existing/manual signal behavior by default.
    op.add_column(
        "signals",
        sa.Column(
            "publication_scope",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PUBLIC'"),
        ),
    )
    op.create_check_constraint(
        "signal_publication_scope",
        "signals",
        "publication_scope IN ('INTERNAL','PRIVATE_TEST','PUBLIC','VIP','PUBLIC_VIP')",
    )
    op.create_index(
        "ix_signals_scope_status_created_at",
        "signals",
        ["publication_scope", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "signal_automation_metadata",
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey("signals.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("producer", sa.String(length=32), nullable=False),
        sa.Column("generation_mode", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("market_type", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("setup_type", sa.String(length=64), nullable=True),
        sa.Column("source_signal_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("market_snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("market_snapshot_hash", sa.String(length=128), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("rule_set_version", sa.String(length=128), nullable=False),
        sa.Column("configuration_version", sa.String(length=128), nullable=False),
        sa.Column(
            "reasoning",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "rule_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "failed_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "analysis_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "counts_toward_performance",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "producer IN ('BROOKS')",
            name=op.f("ck_signal_automation_metadata_producer"),
        ),
        sa.CheckConstraint(
            "generation_mode IN ('SHADOW','PAPER','LIVE')",
            name=op.f("ck_signal_automation_metadata_generation_mode"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reasoning) = 'array'",
            name=op.f("ck_signal_automation_metadata_reasoning_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(rule_ids) = 'array'",
            name=op.f("ck_signal_automation_metadata_rule_ids_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(failed_rules) = 'array'",
            name=op.f("ck_signal_automation_metadata_failed_rules_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(analysis_metadata) = 'object'",
            name=op.f("ck_signal_automation_metadata_analysis_metadata_object"),
        ),
        sa.UniqueConstraint(
            "producer",
            "source_signal_id",
            name="uq_signal_automation_metadata_producer_source_signal",
        ),
        sa.UniqueConstraint(
            "producer",
            "idempotency_key",
            name="uq_signal_automation_metadata_producer_idempotency",
        ),
    )
    op.create_index(
        "ix_signal_automation_metadata_snapshot_hash",
        "signal_automation_metadata",
        ["market_snapshot_hash"],
        unique=False,
    )
    op.create_index(
        "ix_signal_automation_metadata_mode_created_at",
        "signal_automation_metadata",
        ["generation_mode", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_signal_automation_metadata_performance_mode",
        "signal_automation_metadata",
        ["counts_toward_performance", "generation_mode"],
        unique=False,
    )

    op.create_table(
        "signal_rule_evidence",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey("signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "source_pages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "failed_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "confidence_components",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("ordinal > 0", name=op.f("ck_signal_rule_evidence_ordinal")),
        sa.CheckConstraint(
            "status IN ('PASS','FAIL','NOT_APPLICABLE','AMBIGUOUS')",
            name=op.f("ck_signal_rule_evidence_status"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_pages) = 'array'",
            name=op.f("ck_signal_rule_evidence_source_pages_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array'",
            name=op.f("ck_signal_rule_evidence_evidence_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(failed_conditions) = 'array'",
            name=op.f("ck_signal_rule_evidence_failed_conditions_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(confidence_components) = 'array'",
            name=op.f("ck_signal_rule_evidence_confidence_components_array"),
        ),
        sa.UniqueConstraint(
            "signal_id",
            "ordinal",
            name="uq_signal_rule_evidence_signal_ordinal",
        ),
    )
    op.create_index(
        "ix_signal_rule_evidence_signal_rule",
        "signal_rule_evidence",
        ["signal_id", "rule_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signal_rule_evidence_signal_rule", table_name="signal_rule_evidence")
    op.drop_table("signal_rule_evidence")

    op.drop_index(
        "ix_signal_automation_metadata_performance_mode",
        table_name="signal_automation_metadata",
    )
    op.drop_index(
        "ix_signal_automation_metadata_mode_created_at",
        table_name="signal_automation_metadata",
    )
    op.drop_index(
        "ix_signal_automation_metadata_snapshot_hash",
        table_name="signal_automation_metadata",
    )
    op.drop_table("signal_automation_metadata")

    op.drop_index("ix_signals_scope_status_created_at", table_name="signals")
    op.drop_constraint("signal_publication_scope", "signals", type_="check")
    op.drop_column("signals", "publication_scope")
