"""Create user favorites.

Revision ID: 20260901_0007
Revises: 20260901_0006
Create Date: 2026-09-01 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0007"
down_revision: str | None = "20260901_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create a unique, cascade-safe user-to-signal bookmark table."""
    op.create_table(
        "user_favorites",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_user_favorites_signal_id_signals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_favorites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_favorites")),
        sa.UniqueConstraint(
            "user_id",
            "signal_id",
            name="uq_user_favorites_user_signal",
        ),
    )
    op.create_index(
        "ix_user_favorites_signal_id",
        "user_favorites",
        ["signal_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_favorites_user_created_id",
        "user_favorites",
        ["user_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop user favorites and its supporting indexes."""
    op.drop_index(
        "ix_user_favorites_user_created_id",
        table_name="user_favorites",
    )
    op.drop_index(
        "ix_user_favorites_signal_id",
        table_name="user_favorites",
    )
    op.drop_table("user_favorites")
