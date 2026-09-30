"""Create core users, admins, channels, and bot settings tables.

Revision ID: 20260901_0001
Revises: None
Create Date: 2026-09-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four Phase 3 core tables and their indexes."""
    op.create_table(
        "users",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("is_bot", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "last_activity",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
            "status IN ('ACTIVE', 'BLOCKED', 'DEACTIVATED')",
            name=op.f("ck_users_user_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("telegram_user_id", name=op.f("uq_users_telegram_user_id")),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"], unique=False)
    op.create_index(
        "ix_users_status_last_activity",
        "users",
        ["status", "last_activity"],
        unique=False,
    )

    op.create_table(
        "admins",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_admins_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admins")),
        sa.UniqueConstraint("user_id", name=op.f("uq_admins_user_id")),
    )

    op.create_table(
        "channels",
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("invite_link", sa.String(length=2048), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
            "sort_order >= 0",
            name=op.f("ck_channels_non_negative_sort_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("telegram_chat_id", name=op.f("uq_channels_telegram_chat_id")),
    )
    op.create_index(
        "ix_channels_is_active_sort_order",
        "channels",
        ["is_active", "sort_order"],
        unique=False,
    )

    op.create_table(
        "bot_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value_type", sa.String(length=16), nullable=False),
        sa.Column(
            "is_sensitive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by_admin_id", sa.BigInteger(), nullable=True),
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
            "value_type IN ('STRING', 'INTEGER', 'BOOLEAN', 'JSON')",
            name=op.f("ck_bot_settings_value_type"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_admin_id"],
            ["admins.id"],
            name=op.f("fk_bot_settings_updated_by_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bot_settings")),
        sa.UniqueConstraint("key", name=op.f("uq_bot_settings_key")),
    )
    op.create_index(
        "ix_bot_settings_updated_by_admin_id",
        "bot_settings",
        ["updated_by_admin_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop Phase 3 objects in reverse dependency order."""
    op.drop_index("ix_bot_settings_updated_by_admin_id", table_name="bot_settings")
    op.drop_table("bot_settings")
    op.drop_index("ix_channels_is_active_sort_order", table_name="channels")
    op.drop_table("channels")
    op.drop_table("admins")
    op.drop_index("ix_users_status_last_activity", table_name="users")
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_table("users")
