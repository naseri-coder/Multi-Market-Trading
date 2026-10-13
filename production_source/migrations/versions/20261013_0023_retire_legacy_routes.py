"""Reconcile retired strategy routes while retaining old operator evidence.

Revision ID: 20261013_0023
Revises: 20261004_0022

The predecessor may have been applied on older databases with a broader
strategy allowlist. Its source is narrowed for fresh installs; this follow-up
also brings previously upgraded installations to the same active state.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261013_0023"
down_revision = "20261004_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve old rows in an audit archive before removing them from runtime
    # tables. PostgreSQL/Alembic runs this DDL and DML in one transaction.
    op.create_table(
        "retired_strategy_evidence_archive",
        sa.Column("source_table", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("source_table", "source_id"),
    )
    op.execute("""
        INSERT INTO retired_strategy_evidence_archive (source_table, source_id, snapshot)
        SELECT 'signal_strategy_configs', id, to_jsonb(c)
        FROM signal_strategy_configs AS c
        WHERE strategy_code <> 'BROOKS'
    """)
    op.execute("""
        INSERT INTO retired_strategy_evidence_archive (source_table, source_id, snapshot)
        SELECT 'signal_automation_metadata', signal_id, to_jsonb(m)
        FROM signal_automation_metadata AS m
        WHERE producer <> 'BROOKS'
    """)
    op.execute("DELETE FROM signal_strategy_configs WHERE strategy_code <> 'BROOKS'")
    op.execute("DELETE FROM signal_automation_metadata WHERE producer <> 'BROOKS'")

    # The same named constraints exist on both old-upgraded and fresh databases.
    op.drop_constraint(
        op.f("ck_signal_strategy_configs_strategy_code"),
        "signal_strategy_configs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_strategy_configs_strategy_code"),
        "signal_strategy_configs",
        "strategy_code IN ('BROOKS')",
    )
    op.drop_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        "producer IN ('BROOKS')",
    )


def downgrade() -> None:
    # A restored old database may contain archived historical signals.
    # Refuse destructive downgrade rather than silently discarding evidence.
    bind = op.get_bind()
    count = bind.execute(
        sa.text("SELECT count(*) FROM retired_strategy_evidence_archive")
    ).scalar_one()
    if count:
        raise RuntimeError("NONEMPTY_STRATEGY_ARCHIVE_DOWNGRADE_REFUSED")
    op.drop_table("retired_strategy_evidence_archive")
