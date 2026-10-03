"""Canonical multi-lot and Scale-In domain contracts.

No exchange I/O lives in this module.  Order intent and confirmed fills are
intentionally different types so an unfilled request can never change position
accounting.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ScaleInMode(StrEnum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class ScaleInCategory(StrEnum):
    ADD_TO_WINNER = "ADD_TO_WINNER"
    ADD_ON_PULLBACK = "ADD_ON_PULLBACK"
    ADD_AFTER_CONFIRMATION = "ADD_AFTER_CONFIRMATION"
    ADD_AT_BETTER_PRICE = "ADD_AT_BETTER_PRICE"
    AVERAGE_INTO_ADVERSE_MOVE = "AVERAGE_INTO_ADVERSE_MOVE"
    TRADING_RANGE_SCALE_IN = "TRADING_RANGE_SCALE_IN"
    COUNTERTREND_CHANNEL_SCALE_IN = "COUNTERTREND_CHANNEL_SCALE_IN"


class PositionState(StrEnum):
    OPEN = "OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    PARTIALLY_EXITED = "PARTIALLY_EXITED"
    CLOSED = "CLOSED"


class ScaleExecutionState(StrEnum):
    SCALE_IN_PROPOSED = "SCALE_IN_PROPOSED"
    SCALE_IN_APPROVED = "SCALE_IN_APPROVED"
    SCALE_IN_ORDER_PENDING = "SCALE_IN_ORDER_PENDING"
    SCALE_IN_PARTIALLY_FILLED = "SCALE_IN_PARTIALLY_FILLED"
    SCALE_IN_FILLED = "SCALE_IN_FILLED"
    SCALE_IN_CANCELLED = "SCALE_IN_CANCELLED"
    SCALE_IN_REJECTED = "SCALE_IN_REJECTED"
    SCALE_IN_FAILED = "SCALE_IN_FAILED"


class ReconciliationStatus(StrEnum):
    IN_SYNC = "IN_SYNC"
    EXCHANGE_AHEAD = "EXCHANGE_AHEAD"
    DB_AHEAD = "DB_AHEAD"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    CANCEL_MISMATCH = "CANCEL_MISMATCH"
    UNKNOWN_EXECUTION = "UNKNOWN_EXECUTION"
    RISK_BREACH = "RISK_BREACH"


@dataclass(frozen=True, slots=True)
class ScaleInOrderIntent:
    intent_id: str
    position_id: int | str
    category: ScaleInCategory
    direction: str
    desired_qty: Decimal
    expected_price: Decimal
    structural_stop: Decimal
    rule_id: str
    setup_type: str | None
    created_at: datetime
    client_order_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if self.desired_qty <= 0 or self.expected_price <= 0 or self.structural_stop <= 0:
            raise ValueError("scale-in intent quantity/prices must be positive")


@dataclass(frozen=True, slots=True)
class EntryFill:
    execution_key: str
    position_id: int | str
    direction: str
    filled_qty: Decimal
    fill_price: Decimal
    fill_time: datetime
    requested_qty: Decimal
    entry_reason: str
    scale_sequence_number: int
    structural_stop_at_entry: Decimal
    risk_budget_at_entry: Decimal
    fee: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    risk_buffer_per_unit: Decimal = Decimal("0")
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    fill_id: str | None = None
    setup_type: str | None = None
    rule_id: str | None = None
    fill_source: str = "EXCHANGE"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if self.filled_qty <= 0 or self.requested_qty <= 0 or self.fill_price <= 0:
            raise ValueError("confirmed fill quantity/price must be positive")
        if self.filled_qty > self.requested_qty:
            raise ValueError("filled quantity cannot exceed requested quantity")
        if self.structural_stop_at_entry <= 0:
            raise ValueError("structural stop must be positive")
        if self.risk_budget_at_entry < 0 or self.fee < 0 or self.risk_buffer_per_unit < 0:
            raise ValueError("risk/fee buffers cannot be negative")
        if self.scale_sequence_number < 0:
            raise ValueError("scale sequence cannot be negative")


@dataclass(frozen=True, slots=True)
class ExitFill:
    execution_key: str
    position_id: int | str
    filled_qty: Decimal
    fill_price: Decimal
    fill_time: datetime
    exit_reason: str
    fee: Decimal = Decimal("0")
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    fill_id: str | None = None
    target_number: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.filled_qty <= 0 or self.fill_price <= 0:
            raise ValueError("exit fill quantity/price must be positive")
        if self.fee < 0:
            raise ValueError("fee cannot be negative")


@dataclass(frozen=True, slots=True)
class AggregateRiskDecision:
    approved: bool
    requested_qty: Decimal
    approved_qty: Decimal
    max_safe_add_qty: Decimal
    current_aggregate_risk: Decimal
    post_scale_aggregate_risk: Decimal
    remaining_risk_budget: Decimal
    initial_trade_risk_budget: Decimal
    executable_stop: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    status: ReconciliationStatus
    missing_exchange_fill_keys: tuple[str, ...] = ()
    local_only_fill_keys: tuple[str, ...] = ()
    local_open_qty: Decimal = Decimal("0")
    exchange_open_qty: Decimal = Decimal("0")
    details: Mapping[str, Any] = field(default_factory=dict)
