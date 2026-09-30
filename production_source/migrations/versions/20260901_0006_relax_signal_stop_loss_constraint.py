"""Allow profitable stop-loss movement on open signals.

Revision ID: 20260901_0006
Revises: 20260901_0005
Create Date: 2026-09-01 19:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260901_0006"
down_revision: str | None = "20260901_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Move directional stop validation to the lifecycle-aware service layer."""
    op.drop_constraint(
        op.f("ck_signals_signal_stop_loss_direction"),
        "signals",
        type_="check",
    )


def downgrade() -> None:
    """Restore the original entry-relative stop constraint."""
    op.create_check_constraint(
        op.f("ck_signals_signal_stop_loss_direction"),
        "signals",
        "(direction = 'LONG' AND stop_loss < entry_price) OR "
        "(direction = 'SHORT' AND stop_loss > entry_price)",
    )
