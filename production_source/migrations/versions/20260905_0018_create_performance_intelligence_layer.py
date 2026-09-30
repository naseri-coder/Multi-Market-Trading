"""create performance intelligence layer tables

Revision ID: 20260905_0018
Revises: 20260902_0017
"""

from alembic import op
import sqlalchemy as sa

revision = "20260905_0018"
down_revision = "20260902_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("total_signals", sa.Integer(), server_default="0"),
        sa.Column("win_rate", sa.Numeric(8, 4), server_default="0"),
        sa.Column("loss_rate", sa.Numeric(8, 4), server_default="0"),
        sa.Column("average_rr", sa.Numeric(10, 4), server_default="0"),
        sa.Column("expectancy", sa.Numeric(10, 4), server_default="0"),
        sa.Column("profit_factor", sa.Numeric(10, 4), server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "pattern_statistics",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("pattern", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=16)),
        sa.Column("sample_count", sa.Integer(), server_default="0"),
        sa.Column("win_rate", sa.Numeric(8, 4), server_default="0"),
        sa.Column("average_rr", sa.Numeric(10, 4), server_default="0"),
        sa.Column("failure_rate", sa.Numeric(8, 4), server_default="0"),
        sa.Column("profile", sa.JSON()),
    )
    op.create_table(
        "failure_analysis",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0"),
        sa.Column("details", sa.Text()),
    )
    op.create_table(
        "decision_quality_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("signal_id", sa.Integer()),
        sa.Column("score", sa.Numeric(8, 4), server_default="0"),
        sa.Column("components", sa.JSON()),
    )


def downgrade() -> None:
    op.drop_table("decision_quality_scores")
    op.drop_table("failure_analysis")
    op.drop_table("pattern_statistics")
    op.drop_table("performance_metrics")
