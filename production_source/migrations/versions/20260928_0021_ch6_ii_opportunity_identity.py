"""Variant-scoped Chapter-6 ii opportunity barrier (isolated candidate).

Revision ID: 20260928_0021
Revises: 20260914_0020
"""

import sqlalchemy as sa
from alembic import op

revision = "20260928_0021"
down_revision = "20260914_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signal_automation_metadata",
        sa.Column("opportunity_variant", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "signal_automation_metadata",
        sa.Column("opportunity_key", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_signal_automation_metadata_ii_opportunity",
        "signal_automation_metadata",
        ["producer", "generation_mode", "opportunity_variant", "opportunity_key"],
        unique=True,
        postgresql_where=sa.text(
            "opportunity_variant = 'CH6_II_PAIR_STOP_V1' "
            "AND opportunity_key IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_signal_automation_metadata_ii_opportunity",
        table_name="signal_automation_metadata",
    )
    op.drop_column("signal_automation_metadata", "opportunity_key")
    op.drop_column("signal_automation_metadata", "opportunity_variant")
