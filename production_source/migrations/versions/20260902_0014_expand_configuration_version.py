"""Expand Brooks configuration_version storage.

Revision ID: 20260902_0014
Revises: 20260902_0013
Create Date: 2026-09-02

Brooks Full Core v3 carries a deterministic, human-readable configuration
fingerprint that can legitimately exceed 128 characters.  The value participates
in idempotency hashing but is not indexed directly, so PostgreSQL TEXT is the
correct storage type and preserves the full version string without truncation.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260902_0014"
down_revision = "20260902_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "signal_automation_metadata",
        "configuration_version",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    too_long = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM signal_automation_metadata
            WHERE length(configuration_version) > 128
            """
        )
    ).scalar_one()
    if too_long:
        raise RuntimeError(
            "Cannot downgrade configuration_version to VARCHAR(128): "
            f"{too_long} row(s) exceed 128 characters."
        )

    op.alter_column(
        "signal_automation_metadata",
        "configuration_version",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
        existing_nullable=False,
        postgresql_using="configuration_version::varchar(128)",
    )
