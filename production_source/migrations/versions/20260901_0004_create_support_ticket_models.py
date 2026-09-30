"""Create support tickets and messages.

Revision ID: 20260901_0004
Revises: 20260901_0003
Create Date: 2026-09-01 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0004"
down_revision: str | None = "20260901_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user-owned support threads and chronological text messages."""
    op.create_table(
        "support_tickets",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'OPEN'"),
            nullable=False,
        ),
        sa.Column("assigned_admin_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            "status IN ('OPEN', 'IN_PROGRESS', 'CLOSED')",
            name=op.f("ck_support_tickets_support_ticket_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_support_tickets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
    )
    op.create_index(
        "ix_support_tickets_status_last_message",
        "support_tickets",
        ["status", "last_message_at"],
        unique=False,
    )
    op.create_index(
        "ix_support_tickets_user_status",
        "support_tickets",
        ["user_id", "status"],
        unique=False,
    )

    op.create_table(
        "support_messages",
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_role", sa.String(length=16), nullable=False),
        sa.Column("sender_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
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
            "sender_role IN ('USER', 'ADMIN')",
            name=op.f("ck_support_messages_support_message_sender_role"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["support_tickets.id"],
            name=op.f("fk_support_messages_ticket_id_support_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_messages")),
    )
    op.create_index(
        "ix_support_messages_ticket_created",
        "support_messages",
        ["ticket_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop support tables in reverse dependency order."""
    op.drop_index("ix_support_messages_ticket_created", table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index("ix_support_tickets_user_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_status_last_message", table_name="support_tickets")
    op.drop_table("support_tickets")
