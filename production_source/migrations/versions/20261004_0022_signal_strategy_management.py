"""Add independent signal-strategy routing configuration.

Revision ID: 20261004_0022
Revises: 20260928_0021
"""

import sqlalchemy as sa
from alembic import op

revision = "20261004_0022"
down_revision = "20260928_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_strategy_configs",
        sa.Column("strategy_code", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "engine_ready", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("private_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("private_channel_title", sa.String(length=255), nullable=True),
        sa.Column("private_channel_username", sa.String(length=64), nullable=True),
        sa.Column("updated_by_telegram_user_id", sa.BigInteger(), nullable=True),
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
            "strategy_code IN ('BROOKS','FM')",
            name=op.f("ck_signal_strategy_configs_strategy_code"),
        ),
        sa.CheckConstraint(
            "private_channel_id IS NULL OR private_channel_id < 0",
            name=op.f("ck_signal_strategy_configs_private_channel_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_strategy_configs")),
        sa.UniqueConstraint(
            "strategy_code", name=op.f("uq_signal_strategy_configs_strategy_code")
        ),
    )
    op.create_index(
        "ix_signal_strategy_configs_enabled",
        "signal_strategy_configs",
        ["enabled"],
        unique=False,
    )
    strategy_table = sa.table(
        "signal_strategy_configs",
        sa.column("strategy_code", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("engine_ready", sa.Boolean()),
    )
    op.bulk_insert(
        strategy_table,
        [
            {
                "strategy_code": "BROOKS",
                "display_name": "Price Action (Al Brooks)",
                "enabled": False,
                "engine_ready": True,
            },
            {
                "strategy_code": "FM",
                "display_name": "FM",
                "enabled": False,
                "engine_ready": False,
            },
        ],
    )

    op.drop_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        "producer IN ('BROOKS','FM')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        "producer IN ('BROOKS')",
    )
    op.drop_index(
        "ix_signal_strategy_configs_enabled",
        table_name="signal_strategy_configs",
    )
    op.drop_table("signal_strategy_configs")
