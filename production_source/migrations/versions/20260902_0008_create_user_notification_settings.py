"""Create user notification settings.

Revision ID: 20260902_0008
Revises: 20260901_0007
Create Date: 2026-09-02 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0008"
down_revision: str | None = "20260901_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create explicit, user-owned preferences for six notification types."""
    op.create_table(
        "user_notification_settings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("notification_type", sa.String(length=32), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
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
            "notification_type IN ("
            "'NEW_SIGNAL', 'TARGET_HIT', 'STOP_HIT', "
            "'SIGNAL_UPDATED', 'SIGNAL_CLOSED', 'SYSTEM_NOTIFICATION'"
            ")",
            name=op.f(
                "ck_user_notification_settings_notification_type"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f(
                "fk_user_notification_settings_user_id_users"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_user_notification_settings"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "notification_type",
            name="uq_user_notification_settings_user_type",
        ),
    )
    op.create_index(
        "ix_user_notification_settings_type_enabled_user",
        "user_notification_settings",
        ["notification_type", "is_enabled", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop notification preferences and their delivery lookup index."""
    op.drop_index(
        "ix_user_notification_settings_type_enabled_user",
        table_name="user_notification_settings",
    )
    op.drop_table("user_notification_settings")
