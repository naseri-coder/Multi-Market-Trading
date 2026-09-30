"""Create referral code and attribution architecture.

Revision ID: 20260902_0011
Revises: 20260902_0010
Create Date: 2026-09-02 04:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0011"
down_revision: str | None = "20260902_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add non-guessable user codes and immutable referral attribution."""
    op.add_column(
        "users",
        sa.Column("referral_code", sa.String(length=12), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_users_valid_referral_code"),
        "users",
        "referral_code IS NULL OR "
        "referral_code ~ '^R[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{11}$'",
    )
    op.create_unique_constraint(
        "uq_users_referral_code",
        "users",
        ["referral_code"],
    )

    op.create_table(
        "referrals",
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_code", sa.String(length=12), nullable=False),
        sa.Column(
            "reward_granted",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "referrer_user_id <> referred_user_id",
            name=op.f("ck_referrals_different_users"),
        ),
        sa.CheckConstraint(
            "referral_code ~ '^R[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{11}$'",
            name=op.f("ck_referrals_valid_referral_code"),
        ),
        sa.CheckConstraint(
            "reward_granted = false",
            name=op.f("ck_referrals_reward_disabled"),
        ),
        sa.ForeignKeyConstraint(
            ["referrer_user_id"],
            ["users.id"],
            name=op.f("fk_referrals_referrer_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["referred_user_id"],
            ["users.id"],
            name=op.f("fk_referrals_referred_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referrals")),
        sa.UniqueConstraint(
            "referred_user_id",
            name="uq_referrals_referred_user_id",
        ),
    )
    op.create_index(
        "ix_referrals_referrer_created_id",
        "referrals",
        ["referrer_user_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop referral attribution and user referral codes."""
    op.drop_index("ix_referrals_referrer_created_id", table_name="referrals")
    op.drop_table("referrals")
    op.drop_constraint("uq_users_referral_code", "users", type_="unique")
    op.drop_constraint(
        op.f("ck_users_valid_referral_code"),
        "users",
        type_="check",
    )
    op.drop_column("users", "referral_code")
