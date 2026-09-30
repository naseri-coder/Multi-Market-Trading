"""Create signal database architecture.

Revision ID: 20260901_0005
Revises: 20260901_0004
Create Date: 2026-09-01 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0005"
down_revision: str | None = "20260901_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create signals, ordered targets, and immutable lifecycle events."""
    op.create_table(
        "signals",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("stop_loss", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("leverage", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("profit_loss", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('LONG', 'SHORT')",
            name=op.f("ck_signals_signal_direction"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'CLOSED', 'CANCELLED')",
            name=op.f("ck_signals_signal_status"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(symbol)) BETWEEN 1 AND 32 AND symbol = upper(symbol)",
            name=op.f("ck_signals_signal_symbol"),
        ),
        sa.CheckConstraint(
            "entry_price > 0 AND stop_loss > 0 AND leverage > 0",
            name=op.f("ck_signals_signal_positive_values"),
        ),
        sa.CheckConstraint(
            "(direction = 'LONG' AND stop_loss < entry_price) OR "
            "(direction = 'SHORT' AND stop_loss > entry_price)",
            name=op.f("ck_signals_signal_stop_loss_direction"),
        ),
        sa.CheckConstraint(
            "((status IN ('DRAFT', 'OPEN') AND closed_at IS NULL) OR "
            "(status IN ('CLOSED', 'CANCELLED') AND closed_at IS NOT NULL))",
            name=op.f("ck_signals_signal_closed_at_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signals")),
    )
    op.create_index(
        "ix_signals_status_created_at",
        "signals",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_signals_symbol_status",
        "signals",
        ["symbol", "status"],
        unique=False,
    )

    op.create_table(
        "signal_targets",
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("target_number", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profit_loss", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_number > 0",
            name=op.f("ck_signal_targets_signal_target_positive_number"),
        ),
        sa.CheckConstraint(
            "target_price > 0",
            name=op.f("ck_signal_targets_signal_target_positive_price"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'HIT', 'CANCELLED')",
            name=op.f("ck_signal_targets_signal_target_status"),
        ),
        sa.CheckConstraint(
            "((status = 'HIT' AND hit_at IS NOT NULL AND profit_loss IS NOT NULL) OR "
            "(status IN ('PENDING', 'CANCELLED') AND hit_at IS NULL "
            "AND profit_loss IS NULL))",
            name=op.f("ck_signal_targets_signal_target_hit_state"),
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_signal_targets_signal_id_signals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_targets")),
        sa.UniqueConstraint(
            "signal_id",
            "target_number",
            name=op.f("uq_signal_targets_signal_target_number"),
        ),
    )
    op.create_index(
        "ix_signal_targets_signal_status_number",
        "signal_targets",
        ["signal_id", "status", "target_number"],
        unique=False,
    )

    op.create_table(
        "signal_events",
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'UPDATED', 'PUBLISHED', 'TARGET_ADDED', "
            "'TARGET_HIT', 'STOP_LOSS_UPDATED', 'STOP_HIT', 'CLOSED', 'CANCELLED')",
            name=op.f("ck_signal_events_signal_event_type"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_signal_events_signal_event_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_signal_events_signal_id_signals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_events")),
    )
    op.create_index(
        "ix_signal_events_signal_created_id",
        "signal_events",
        ["signal_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_signal_events_type_created_at",
        "signal_events",
        ["event_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop signal persistence in reverse dependency order."""
    op.drop_index("ix_signal_events_type_created_at", table_name="signal_events")
    op.drop_index("ix_signal_events_signal_created_id", table_name="signal_events")
    op.drop_table("signal_events")
    op.drop_index(
        "ix_signal_targets_signal_status_number",
        table_name="signal_targets",
    )
    op.drop_table("signal_targets")
    op.drop_index("ix_signals_symbol_status", table_name="signals")
    op.drop_index("ix_signals_status_created_at", table_name="signals")
    op.drop_table("signals")
