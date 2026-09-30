"""Allow durable LIVE VIP Telegram delivery tracking.

Revision ID: 20260902_0015
Revises: 20260902_0014
Create Date: 2026-09-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260902_0015"
down_revision = "20260902_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_signal_deliveries_channel_kind"),
        "signal_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_deliveries_channel_kind"),
        "signal_deliveries",
        "channel_kind IN ('TELEGRAM_PRIVATE_TEST','TELEGRAM_VIP')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    vip_rows = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM signal_deliveries
            WHERE channel_kind = 'TELEGRAM_VIP'
            """
        )
    ).scalar_one()
    if vip_rows:
        raise RuntimeError(
            "Cannot downgrade while TELEGRAM_VIP delivery rows exist."
        )

    op.drop_constraint(
        op.f("ck_signal_deliveries_channel_kind"),
        "signal_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_deliveries_channel_kind"),
        "signal_deliveries",
        "channel_kind IN ('TELEGRAM_PRIVATE_TEST')",
    )
