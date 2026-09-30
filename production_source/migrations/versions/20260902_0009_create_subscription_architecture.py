"""Create VIP subscription plans and subscription history.

Revision ID: 20260902_0009
Revises: 20260902_0008
Create Date: 2026-09-02 01:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0009"
down_revision: str | None = "20260902_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create editable plans and immutable user entitlement snapshots."""
    op.create_table(
        "subscription_plans",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=12), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
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
            "char_length(btrim(name)) BETWEEN 1 AND 100",
            name=op.f("ck_subscription_plans_valid_name"),
        ),
        sa.CheckConstraint(
            "duration_days > 0",
            name=op.f("ck_subscription_plans_positive_duration"),
        ),
        sa.CheckConstraint(
            "price >= 0",
            name=op.f("ck_subscription_plans_non_negative_price"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z0-9]{2,12}$'",
            name=op.f("ck_subscription_plans_valid_currency"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_plans")),
    )
    op.create_index(
        "uq_subscription_plans_name_ci",
        "subscription_plans",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "ix_subscription_plans_active_id",
        "subscription_plans",
        ["is_active", "id"],
        unique=False,
    )

    op.create_table(
        "subscriptions",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_name", sa.String(length=100), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=12), nullable=False),
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
            "status IN ('ACTIVE', 'EXPIRED')",
            name=op.f("ck_subscriptions_status"),
        ),
        sa.CheckConstraint(
            "expires_at > starts_at",
            name=op.f("ck_subscriptions_valid_period"),
        ),
        sa.CheckConstraint(
            "((status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status = 'EXPIRED' AND ended_at IS NOT NULL))",
            name=op.f("ck_subscriptions_status_end_state"),
        ),
        sa.CheckConstraint(
            "duration_days > 0",
            name=op.f("ck_subscriptions_positive_duration"),
        ),
        sa.CheckConstraint(
            "price >= 0",
            name=op.f("ck_subscriptions_non_negative_price"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(plan_name)) BETWEEN 1 AND 100",
            name=op.f("ck_subscriptions_valid_plan_name"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z0-9]{2,12}$'",
            name=op.f("ck_subscriptions_valid_currency"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["subscription_plans.id"],
            name=op.f("fk_subscriptions_plan_id_subscription_plans"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
    )
    op.create_index(
        "uq_subscriptions_one_active_per_user",
        "subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_subscriptions_user_status_expires",
        "subscriptions",
        ["user_id", "status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_subscriptions_plan_status",
        "subscriptions",
        ["plan_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop subscriptions before their referenced plan definitions."""
    op.drop_index(
        "ix_subscriptions_plan_status",
        table_name="subscriptions",
    )
    op.drop_index(
        "ix_subscriptions_user_status_expires",
        table_name="subscriptions",
    )
    op.drop_index(
        "uq_subscriptions_one_active_per_user",
        table_name="subscriptions",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_table("subscriptions")
    op.drop_index(
        "ix_subscription_plans_active_id",
        table_name="subscription_plans",
    )
    op.drop_index(
        "uq_subscription_plans_name_ci",
        table_name="subscription_plans",
    )
    op.drop_table("subscription_plans")
