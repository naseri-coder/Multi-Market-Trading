"""Add Brooks multi-lot Scale-In persistence without changing live execution.

Revision ID: 20260914_0020
Revises: 20260912_0019
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260914_0020"
down_revision = "20260912_0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "brooks_positions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("signal_id", sa.BigInteger(), sa.ForeignKey("signals.id", ondelete="SET NULL")),
        sa.Column("initial_source_signal_id", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="OPEN"),
        sa.Column("initial_trade_risk_budget", sa.Numeric(38,18), nullable=False),
        sa.Column("executable_stop", sa.Numeric(38,18), nullable=False),
        sa.Column("open_qty", sa.Numeric(38,18), nullable=False, server_default="0"),
        sa.Column("avg_entry", sa.Numeric(38,18)),
        sa.Column("realized_net_pnl", sa.Numeric(38,18), nullable=False, server_default="0"),
        sa.Column("cumulative_fees", sa.Numeric(38,18), nullable=False, server_default="0"),
        sa.Column("position_version", sa.String(96), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("direction IN ('LONG','SHORT')", name=op.f("ck_brooks_positions_brooks_position_direction")),
        sa.CheckConstraint("mode IN ('SHADOW','LIVE')", name=op.f("ck_brooks_positions_brooks_position_mode")),
        sa.CheckConstraint("state IN ('OPEN','EXIT_PENDING','PARTIALLY_EXITED','CLOSED')", name=op.f("ck_brooks_positions_brooks_position_state")),
        sa.CheckConstraint("initial_trade_risk_budget > 0", name=op.f("ck_brooks_positions_brooks_position_positive_budget")),
        sa.CheckConstraint("open_qty >= 0", name=op.f("ck_brooks_positions_brooks_position_nonnegative_qty")),
        sa.UniqueConstraint("mode", "initial_source_signal_id", name="uq_brooks_position_mode_source"),
    )
    op.create_index("ix_brooks_positions_market_state", "brooks_positions", ["symbol","direction","state","mode"])

    op.create_table(
        "brooks_position_entry_lots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("position_id", sa.BigInteger(), sa.ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_key", sa.String(192), nullable=False),
        sa.Column("client_order_id", sa.String(128)), sa.Column("exchange_order_id", sa.String(128)), sa.Column("fill_id", sa.String(128)),
        sa.Column("requested_qty", sa.Numeric(38,18), nullable=False), sa.Column("filled_qty", sa.Numeric(38,18), nullable=False),
        sa.Column("open_qty", sa.Numeric(38,18), nullable=False), sa.Column("fill_price", sa.Numeric(38,18), nullable=False),
        sa.Column("fill_time", sa.DateTime(timezone=True), nullable=False), sa.Column("entry_reason", sa.String(96), nullable=False),
        sa.Column("setup_type", sa.String(96)), sa.Column("rule_id", sa.String(96)), sa.Column("scale_sequence_number", sa.Integer(), nullable=False),
        sa.Column("structural_stop_at_entry", sa.Numeric(38,18), nullable=False), sa.Column("risk_budget_at_entry", sa.Numeric(38,18), nullable=False),
        sa.Column("fee", sa.Numeric(38,18), nullable=False, server_default="0"), sa.Column("slippage", sa.Numeric(38,18), nullable=False, server_default="0"),
        sa.Column("risk_buffer_per_unit", sa.Numeric(38,18), nullable=False, server_default="0"), sa.Column("fill_source", sa.String(24), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("requested_qty > 0 AND filled_qty > 0 AND open_qty >= 0", name=op.f("ck_brooks_position_entry_lots_brooks_entry_lot_qty")),
        sa.CheckConstraint("fill_price > 0 AND structural_stop_at_entry > 0", name=op.f("ck_brooks_position_entry_lots_brooks_entry_lot_prices")),
        sa.CheckConstraint("scale_sequence_number >= 0", name=op.f("ck_brooks_position_entry_lots_brooks_entry_lot_sequence")),
        sa.UniqueConstraint("position_id", "execution_key", name="uq_brooks_entry_lot_execution"),
    )
    op.create_index("ix_brooks_entry_lots_position_fill_time", "brooks_position_entry_lots", ["position_id","fill_time"])

    op.create_table(
        "brooks_position_exit_fills",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("position_id", sa.BigInteger(), sa.ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_key", sa.String(192), nullable=False), sa.Column("client_order_id", sa.String(128)),
        sa.Column("exchange_order_id", sa.String(128)), sa.Column("fill_id", sa.String(128)),
        sa.Column("filled_qty", sa.Numeric(38,18), nullable=False), sa.Column("fill_price", sa.Numeric(38,18), nullable=False),
        sa.Column("fill_time", sa.DateTime(timezone=True), nullable=False), sa.Column("exit_reason", sa.String(64), nullable=False),
        sa.Column("target_number", sa.Integer()), sa.Column("fee", sa.Numeric(38,18), nullable=False, server_default="0"),
        sa.Column("realized_net_pnl", sa.Numeric(38,18), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("filled_qty > 0 AND fill_price > 0", name=op.f("ck_brooks_position_exit_fills_brooks_exit_fill_positive")),
        sa.UniqueConstraint("position_id", "execution_key", name="uq_brooks_exit_fill_execution"),
    )
    op.create_index("ix_brooks_exit_fills_position_fill_time", "brooks_position_exit_fills", ["position_id","fill_time"])

    op.create_table(
        "brooks_position_scale_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("position_id", sa.BigInteger(), sa.ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(192), nullable=False), sa.Column("intent_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(40), nullable=False), sa.Column("category", sa.String(48), nullable=False),
        sa.Column("desired_qty", sa.Numeric(38,18), nullable=False), sa.Column("approved_qty", sa.Numeric(38,18)),
        sa.Column("expected_price", sa.Numeric(38,18), nullable=False), sa.Column("structural_stop", sa.Numeric(38,18), nullable=False),
        sa.Column("client_order_id", sa.String(128)), sa.Column("exchange_order_id", sa.String(128)),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("position_id", "event_key", name="uq_brooks_scale_event_key"),
    )
    op.create_index("ix_brooks_scale_events_intent", "brooks_position_scale_events", ["position_id","intent_id","id"])

    op.create_table(
        "brooks_position_risk_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("position_id", sa.BigInteger(), sa.ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_key", sa.String(192), nullable=False), sa.Column("reason", sa.String(96), nullable=False),
        sa.Column("executable_stop", sa.Numeric(38,18), nullable=False), sa.Column("open_qty", sa.Numeric(38,18), nullable=False),
        sa.Column("avg_entry", sa.Numeric(38,18)), sa.Column("current_aggregate_risk", sa.Numeric(38,18), nullable=False),
        sa.Column("remaining_risk_budget", sa.Numeric(38,18), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("position_id", "snapshot_key", name="uq_brooks_risk_snapshot_key"),
    )


def downgrade():
    bind = op.get_bind()
    for table in (
        "brooks_position_entry_lots", "brooks_position_exit_fills",
        "brooks_position_scale_events", "brooks_position_risk_snapshots", "brooks_positions",
    ):
        if bind.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)")):
            raise RuntimeError("Scale-In/multi-lot evidence exists; downgrade would destroy execution/accounting history")
    op.drop_table("brooks_position_risk_snapshots")
    op.drop_index("ix_brooks_scale_events_intent", table_name="brooks_position_scale_events")
    op.drop_table("brooks_position_scale_events")
    op.drop_index("ix_brooks_exit_fills_position_fill_time", table_name="brooks_position_exit_fills")
    op.drop_table("brooks_position_exit_fills")
    op.drop_index("ix_brooks_entry_lots_position_fill_time", table_name="brooks_position_entry_lots")
    op.drop_table("brooks_position_entry_lots")
    op.drop_index("ix_brooks_positions_market_state", table_name="brooks_positions")
    op.drop_table("brooks_positions")
