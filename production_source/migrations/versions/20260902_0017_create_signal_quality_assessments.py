"""create signal quality assessments

Revision ID: 20260902_0017
Revises: 20260902_0016
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_0017"
down_revision = "20260902_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_quality_assessments",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "signals.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "ai_score",
            sa.Numeric(5, 2),
            nullable=False,
        ),
        sa.Column(
            "risk_score",
            sa.Numeric(5, 2),
            nullable=False,
        ),
        sa.Column(
            "final_score",
            sa.Numeric(5, 2),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Numeric(5, 4),
            nullable=False,
        ),
        sa.Column(
            "quality_grade",
            sa.String(8),
            nullable=False,
        ),
        sa.Column(
            "market_regime",
            sa.String(32),
            nullable=True,
        ),
        sa.Column(
            "gate_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "gate_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table(
        "signal_quality_assessments"
    )
