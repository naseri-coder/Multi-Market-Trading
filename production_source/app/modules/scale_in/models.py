"""Additive persistence for Scale-In/multi-lot architecture."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BrooksPosition(Base):
    __tablename__ = "brooks_positions"
    __table_args__ = (
        CheckConstraint("direction IN ('LONG','SHORT')", name="brooks_position_direction"),
        CheckConstraint("mode IN ('SHADOW','LIVE')", name="brooks_position_mode"),
        CheckConstraint("state IN ('OPEN','EXIT_PENDING','PARTIALLY_EXITED','CLOSED')", name="brooks_position_state"),
        CheckConstraint("initial_trade_risk_budget > 0", name="brooks_position_positive_budget"),
        CheckConstraint("open_qty >= 0", name="brooks_position_nonnegative_qty"),
        UniqueConstraint("mode", "initial_source_signal_id", name="uq_brooks_position_mode_source"),
        Index("ix_brooks_positions_market_state", "symbol", "direction", "state", "mode"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    signal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("signals.id", ondelete="SET NULL"))
    initial_source_signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, server_default=sql_text("'OPEN'"))
    initial_trade_risk_budget: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    executable_stop: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    open_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    avg_entry: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    realized_net_pnl: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    cumulative_fees: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    position_version: Mapped[str] = mapped_column(String(96), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BrooksPositionEntryLot(Base):
    __tablename__ = "brooks_position_entry_lots"
    __table_args__ = (
        UniqueConstraint("position_id", "execution_key", name="uq_brooks_entry_lot_execution"),
        CheckConstraint("requested_qty > 0 AND filled_qty > 0 AND open_qty >= 0", name="brooks_entry_lot_qty"),
        CheckConstraint("fill_price > 0 AND structural_stop_at_entry > 0", name="brooks_entry_lot_prices"),
        CheckConstraint("scale_sequence_number >= 0", name="brooks_entry_lot_sequence"),
        Index("ix_brooks_entry_lots_position_fill_time", "position_id", "fill_time"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    position_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False)
    execution_key: Mapped[str] = mapped_column(String(192), nullable=False)
    client_order_id: Mapped[str | None] = mapped_column(String(128))
    exchange_order_id: Mapped[str | None] = mapped_column(String(128))
    fill_id: Mapped[str | None] = mapped_column(String(128))
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    open_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_reason: Mapped[str] = mapped_column(String(96), nullable=False)
    setup_type: Mapped[str | None] = mapped_column(String(96))
    rule_id: Mapped[str | None] = mapped_column(String(96))
    scale_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    structural_stop_at_entry: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    risk_budget_at_entry: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    slippage: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    risk_buffer_per_unit: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    fill_source: Mapped[str] = mapped_column(String(24), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BrooksPositionExitFill(Base):
    __tablename__ = "brooks_position_exit_fills"
    __table_args__ = (
        UniqueConstraint("position_id", "execution_key", name="uq_brooks_exit_fill_execution"),
        CheckConstraint("filled_qty > 0 AND fill_price > 0", name="brooks_exit_fill_positive"),
        Index("ix_brooks_exit_fills_position_fill_time", "position_id", "fill_time"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    position_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False)
    execution_key: Mapped[str] = mapped_column(String(192), nullable=False)
    client_order_id: Mapped[str | None] = mapped_column(String(128))
    exchange_order_id: Mapped[str | None] = mapped_column(String(128))
    fill_id: Mapped[str | None] = mapped_column(String(128))
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    target_number: Mapped[int | None] = mapped_column(Integer)
    fee: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    realized_net_pnl: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BrooksPositionScaleEvent(Base):
    __tablename__ = "brooks_position_scale_events"
    __table_args__ = (
        UniqueConstraint("position_id", "event_key", name="uq_brooks_scale_event_key"),
        Index("ix_brooks_scale_events_intent", "position_id", "intent_id", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    position_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False)
    event_key: Mapped[str] = mapped_column(String(192), nullable=False)
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    desired_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    approved_qty: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    expected_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    structural_stop: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    client_order_id: Mapped[str | None] = mapped_column(String(128))
    exchange_order_id: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(160), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BrooksPositionRiskSnapshot(Base):
    __tablename__ = "brooks_position_risk_snapshots"
    __table_args__ = (UniqueConstraint("position_id", "snapshot_key", name="uq_brooks_risk_snapshot_key"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    position_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("brooks_positions.id", ondelete="CASCADE"), nullable=False)
    snapshot_key: Mapped[str] = mapped_column(String(192), nullable=False)
    reason: Mapped[str] = mapped_column(String(96), nullable=False)
    executable_stop: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    open_qty: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    avg_entry: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    current_aggregate_risk: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    remaining_risk_budget: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
