"""TM_V6 quantity adapter for multi-lot positions.

Each confirmed entry lot carries its own frozen TM_V6 plan metadata. Aggregate
target/runner quantities are additive across lots, matching Brooks' separate-
trade guidance without changing the existing single-entry TradeManagementPlan.
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Protocol

from app.modules.operations.trade_management import TradeManagementPlan


class ManagedLot(Protocol):
    open_qty: Decimal
    filled_qty: Decimal
    metadata: dict[str, object]


class ManagedExit(Protocol):
    filled_qty: Decimal
    target_number: int | None
    exit_reason: str


def _plan(lot: ManagedLot) -> TradeManagementPlan | None:
    raw = lot.metadata.get("tm_plan")
    if not isinstance(raw, dict):
        return None
    return TradeManagementPlan.from_metadata(raw)


def planned_target_qty(lots: Iterable[ManagedLot], target_number: int) -> Decimal:
    total = Decimal("0")
    for lot in lots:
        plan = _plan(lot)
        if plan is not None:
            total += lot.filled_qty * plan.fraction_for_target(target_number)
    return total


def planned_runner_qty(lots: Iterable[ManagedLot]) -> Decimal:
    total = Decimal("0")
    for lot in lots:
        plan = _plan(lot)
        if plan is not None:
            total += lot.filled_qty * plan.runner_fraction
    return total


def remaining_target_qty(lots: Iterable[ManagedLot], exits: Iterable[ManagedExit], target_number: int) -> Decimal:
    planned = planned_target_qty(lots, target_number)
    exited = sum((e.filled_qty for e in exits if e.target_number == target_number), Decimal("0"))
    return max(Decimal("0"), planned - exited)


def remaining_runner_qty(lots: Iterable[ManagedLot], exits: Iterable[ManagedExit]) -> Decimal:
    planned = planned_runner_qty(lots)
    exited = sum((e.filled_qty for e in exits if e.exit_reason == "RUNNER"), Decimal("0"))
    return max(Decimal("0"), planned - exited)


def stop_order_qty(open_qty: Decimal) -> Decimal:
    if open_qty < 0:
        raise ValueError("open quantity cannot be negative")
    return open_qty
