"""Create delivery tracking for safe PAPER Telegram publishing.

Revision ID: 20260902_0013
Revises: 20260902_0012
Create Date: 2026-09-02 08:30:00
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260902_0013"
down_revision: str | None = "20260902_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey("signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_kind", sa.String(length=24), nullable=False),
        sa.Column("destination_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_message_id", sa.String(length=128), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "channel_kind IN ('TELEGRAM_PRIVATE_TEST')",
            name=op.f("ck_signal_deliveries_channel_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','SENDING','SENT','FAILED','AMBIGUOUS')",
            name=op.f("ck_signal_deliveries_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_signal_deliveries_attempt_count"),
        ),
        sa.UniqueConstraint(
            "signal_id",
            "channel_kind",
            "destination_id",
            name="uq_signal_deliveries_signal_destination",
        ),
    )
    op.create_index(
        "ix_signal_deliveries_status_updated_at",
        "signal_deliveries",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_signal_deliveries_signal_id",
        "signal_deliveries",
        ["signal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signal_deliveries_signal_id", table_name="signal_deliveries")
    op.drop_index("ix_signal_deliveries_status_updated_at", table_name="signal_deliveries")
    op.drop_table("signal_deliveries")
