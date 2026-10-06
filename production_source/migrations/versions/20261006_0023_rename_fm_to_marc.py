"""Rename the reserved FM second-core identity to MARC.

Revision ID: 20261006_0023
Revises: 20261004_0022
"""

from alembic import op

revision = "20261006_0023"
down_revision = "20261004_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_signal_strategy_configs_strategy_code"),
        "signal_strategy_configs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        type_="check",
    )

    op.execute(
        """
        UPDATE signal_strategy_configs
        SET strategy_code = 'MARC',
            display_name = 'MA 7/25/99 Regime Core (MARC)',
            engine_ready = false
        WHERE strategy_code = 'FM'
        """
    )
    op.execute(
        """
        UPDATE signal_automation_metadata
        SET producer = 'MARC'
        WHERE producer = 'FM'
        """
    )

    op.create_check_constraint(
        op.f("ck_signal_strategy_configs_strategy_code"),
        "signal_strategy_configs",
        "strategy_code IN ('BROOKS','MARC')",
    )
    op.create_check_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        "producer IN ('BROOKS','MARC')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_signal_strategy_configs_strategy_code"),
        "signal_strategy_configs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        type_="check",
    )

    op.execute(
        """
        UPDATE signal_strategy_configs
        SET strategy_code = 'FM',
            display_name = 'FM',
            engine_ready = false
        WHERE strategy_code = 'MARC'
        """
    )
    op.execute(
        """
        UPDATE signal_automation_metadata
        SET producer = 'FM'
        WHERE producer = 'MARC'
        """
    )

    op.create_check_constraint(
        op.f("ck_signal_strategy_configs_strategy_code"),
        "signal_strategy_configs",
        "strategy_code IN ('BROOKS','FM')",
    )
    op.create_check_constraint(
        op.f("ck_signal_automation_metadata_producer"),
        "signal_automation_metadata",
        "producer IN ('BROOKS','FM')",
    )
