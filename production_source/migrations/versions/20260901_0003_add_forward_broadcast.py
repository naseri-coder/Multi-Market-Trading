"""Add forwarded-message broadcast sources.

Revision ID: 20260901_0003
Revises: 20260901_0002
Create Date: 2026-09-01 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0003"
down_revision: str | None = "20260901_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow broadcasts to reference one forwardable Telegram message."""
    op.add_column(
        "broadcasts",
        sa.Column("source_chat_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "broadcasts",
        sa.Column("source_message_id", sa.Integer(), nullable=True),
    )
    op.drop_constraint(
        op.f("ck_broadcasts_broadcast_content_type"),
        "broadcasts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_broadcasts_broadcast_content_shape"),
        "broadcasts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_broadcasts_broadcast_content_type"),
        "broadcasts",
        "content_type IN ('TEXT', 'MEDIA', 'FORWARD')",
    )
    op.create_check_constraint(
        op.f("ck_broadcasts_broadcast_content_shape"),
        "broadcasts",
        "((content_type = 'TEXT' AND text IS NOT NULL AND media_type IS NULL "
        "AND media_file_id IS NULL AND caption IS NULL "
        "AND source_chat_id IS NULL AND source_message_id IS NULL) OR "
        "(content_type = 'MEDIA' AND text IS NULL AND media_type IS NOT NULL "
        "AND media_file_id IS NOT NULL AND source_chat_id IS NULL "
        "AND source_message_id IS NULL) OR "
        "(content_type = 'FORWARD' AND text IS NULL AND media_type IS NULL "
        "AND media_file_id IS NULL AND caption IS NULL "
        "AND source_chat_id IS NOT NULL AND source_chat_id <> 0 "
        "AND source_message_id IS NOT NULL AND source_message_id > 0))",
    )


def downgrade() -> None:
    """Remove Phase 9 forward rows and restore the Phase 8 content shape."""
    op.execute("DELETE FROM broadcasts WHERE content_type = 'FORWARD'")
    op.drop_constraint(
        op.f("ck_broadcasts_broadcast_content_shape"),
        "broadcasts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_broadcasts_broadcast_content_type"),
        "broadcasts",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_broadcasts_broadcast_content_type"),
        "broadcasts",
        "content_type IN ('TEXT', 'MEDIA')",
    )
    op.create_check_constraint(
        op.f("ck_broadcasts_broadcast_content_shape"),
        "broadcasts",
        "((content_type = 'TEXT' AND text IS NOT NULL AND media_type IS NULL "
        "AND media_file_id IS NULL AND caption IS NULL) OR "
        "(content_type = 'MEDIA' AND text IS NULL AND media_type IS NOT NULL "
        "AND media_file_id IS NOT NULL))",
    )
    op.drop_column("broadcasts", "source_message_id")
    op.drop_column("broadcasts", "source_chat_id")
