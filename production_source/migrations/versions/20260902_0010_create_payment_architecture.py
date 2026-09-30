"""Create gateway-independent payment architecture.

Revision ID: 20260902_0010
Revises: 20260902_0009
Create Date: 2026-09-02 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0010"
down_revision: str | None = "20260902_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create auditable payment attempts without a real gateway."""
    op.create_table(
        "payments",
        sa.Column("payment_reference", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=True),
        sa.Column("subscription_id", sa.BigInteger(), nullable=True),
        sa.Column("plan_name", sa.String(length=100), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=12), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_reference", sa.String(length=128), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('PENDING', 'SUCCESS', 'FAILED', 'CANCELLED')",
            name=op.f("ck_payments_status"),
        ),
        sa.CheckConstraint(
            "payment_reference ~ '^[A-Z0-9_-]{12,64}$'",
            name=op.f("ck_payments_valid_payment_reference"),
        ),
        sa.CheckConstraint(
            "telegram_user_id > 0",
            name=op.f("ck_payments_positive_telegram_user_id"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(plan_name)) BETWEEN 1 AND 100",
            name=op.f("ck_payments_valid_plan_name"),
        ),
        sa.CheckConstraint(
            "duration_days > 0",
            name=op.f("ck_payments_positive_duration"),
        ),
        sa.CheckConstraint(
            "amount > 0",
            name=op.f("ck_payments_positive_amount"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z0-9]{2,12}$'",
            name=op.f("ck_payments_valid_currency"),
        ),
        sa.CheckConstraint(
            "((status = 'PENDING' AND finalized_at IS NULL) OR "
            "(status IN ('SUCCESS', 'FAILED', 'CANCELLED') "
            "AND finalized_at IS NOT NULL))",
            name=op.f("ck_payments_status_finalized_state"),
        ),
        sa.CheckConstraint(
            "((status = 'FAILED' AND failure_reason IS NOT NULL) OR "
            "(status <> 'FAILED' AND failure_reason IS NULL))",
            name=op.f("ck_payments_failure_reason_state"),
        ),
        sa.CheckConstraint(
            "provider_reference IS NULL OR provider IS NOT NULL",
            name=op.f("ck_payments_provider_reference_state"),
        ),
        sa.CheckConstraint(
            "provider IS NULL OR provider ~ '^[A-Z0-9_-]{2,32}$'",
            name=op.f("ck_payments_valid_provider"),
        ),
        sa.CheckConstraint(
            "provider_reference IS NULL OR "
            "char_length(btrim(provider_reference)) BETWEEN 1 AND 128",
            name=op.f("ck_payments_valid_provider_reference"),
        ),
        sa.CheckConstraint(
            "failure_reason IS NULL OR "
            "char_length(btrim(failure_reason)) BETWEEN 1 AND 1000",
            name=op.f("ck_payments_valid_failure_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_payments_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["subscription_plans.id"],
            name=op.f("fk_payments_plan_id_subscription_plans"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_payments_subscription_id_subscriptions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint(
            "payment_reference",
            name="uq_payments_payment_reference",
        ),
        sa.UniqueConstraint(
            "subscription_id",
            name="uq_payments_subscription_id",
        ),
    )
    op.create_index(
        "ix_payments_user_created_id",
        "payments",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_payments_status_created_at",
        "payments",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_payments_provider_reference",
        "payments",
        ["provider", "provider_reference"],
        unique=True,
        postgresql_where=sa.text("provider_reference IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the standalone payment architecture."""
    op.drop_index(
        "uq_payments_provider_reference",
        table_name="payments",
        postgresql_where=sa.text("provider_reference IS NOT NULL"),
    )
    op.drop_index("ix_payments_status_created_at", table_name="payments")
    op.drop_index("ix_payments_user_created_id", table_name="payments")
    op.drop_table("payments")
