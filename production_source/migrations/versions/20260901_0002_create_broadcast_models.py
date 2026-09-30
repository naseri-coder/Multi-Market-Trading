"""Create broadcasts and broadcast recipients.

Revision ID: 20260901_0002
Revises: 20260901_0001
Create Date: 2026-09-01 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0002"
down_revision: str | None = "20260901_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent broadcast drafts and per-user delivery outcomes."""
    op.create_table(
        "broadcasts",
        sa.Column("created_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=16), nullable=True),
        sa.Column("media_file_id", sa.String(length=512), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column(
            "total_recipients",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("sent_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("blocked_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "content_type IN ('TEXT', 'MEDIA')",
            name=op.f("ck_broadcasts_broadcast_content_type"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PROCESSING', 'COMPLETED', 'CANCELLED', 'FAILED')",
            name=op.f("ck_broadcasts_broadcast_status"),
        ),
        sa.CheckConstraint(
            "media_type IS NULL OR media_type IN "
            "('PHOTO', 'VIDEO', 'DOCUMENT', 'ANIMATION', 'AUDIO', 'VOICE')",
            name=op.f("ck_broadcasts_broadcast_media_type"),
        ),
        sa.CheckConstraint(
            "((content_type = 'TEXT' AND text IS NOT NULL AND media_type IS NULL "
            "AND media_file_id IS NULL AND caption IS NULL) OR "
            "(content_type = 'MEDIA' AND text IS NULL AND media_type IS NOT NULL "
            "AND media_file_id IS NOT NULL))",
            name=op.f("ck_broadcasts_broadcast_content_shape"),
        ),
        sa.CheckConstraint(
            "total_recipients >= 0 AND sent_count >= 0 AND failed_count >= 0 "
            "AND blocked_count >= 0 AND "
            "sent_count + failed_count + blocked_count <= total_recipients",
            name=op.f("ck_broadcasts_broadcast_non_negative_counts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broadcasts")),
    )
    op.create_index(
        "ix_broadcasts_created_by_status",
        "broadcasts",
        ["created_by_telegram_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_broadcasts_status_created_at",
        "broadcasts",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "broadcast_recipients",
        sa.Column("broadcast_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('PENDING', 'SENT', 'FAILED', 'BLOCKED')",
            name=op.f("ck_broadcast_recipients_broadcast_recipient_status"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_broadcast_recipients_broadcast_recipient_attempts"),
        ),
        sa.ForeignKeyConstraint(
            ["broadcast_id"],
            ["broadcasts.id"],
            name=op.f("fk_broadcast_recipients_broadcast_id_broadcasts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_broadcast_recipients_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broadcast_recipients")),
        sa.UniqueConstraint(
            "broadcast_id",
            "user_id",
            name=op.f("uq_broadcast_recipients_broadcast_user"),
        ),
    )
    op.create_index(
        "ix_broadcast_recipients_broadcast_status_id",
        "broadcast_recipients",
        ["broadcast_id", "status", "id"],
        unique=False,
    )
    op.create_index(
        "ix_broadcast_recipients_user_id",
        "broadcast_recipients",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop broadcast delivery state in reverse dependency order."""
    op.drop_index(
        "ix_broadcast_recipients_user_id",
        table_name="broadcast_recipients",
    )
    op.drop_index(
        "ix_broadcast_recipients_broadcast_status_id",
        table_name="broadcast_recipients",
    )
    op.drop_table("broadcast_recipients")
    op.drop_index("ix_broadcasts_status_created_at", table_name="broadcasts")
    op.drop_index("ix_broadcasts_created_by_status", table_name="broadcasts")
    op.drop_table("broadcasts")
