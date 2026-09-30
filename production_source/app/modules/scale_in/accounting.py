"""Exactly-once multi-lot accounting using average-cost net-position semantics."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .entities import EntryFill, ExitFill, PositionState
from .risk import aggregate_risk


@dataclass(slots=True)
class LotState:
    execution_key: str
    fill_price: Decimal
    filled_qty: Decimal
    open_qty: Decimal
    risk_buffer_per_unit: Decimal
    scale_sequence_number: int
    entry_reason: str
    setup_type: str | None
    rule_id: str | None
    metadata: dict[str, object]


class PositionLedger:
    """Pure domain ledger; only confirmed fills change quantity or basis."""

    def __init__(self, *, position_id: int | str, direction: str,
                 initial_trade_risk_budget: Decimal, executable_stop: Decimal) -> None:
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if initial_trade_risk_budget <= 0 or executable_stop <= 0:
            raise ValueError("risk budget and stop must be positive")
        self.position_id = position_id
        self.direction = direction
        self.initial_trade_risk_budget = initial_trade_risk_budget
        self.executable_stop = executable_stop
        self.state = PositionState.OPEN
        self.open_qty = Decimal("0")
        self.avg_entry: Decimal | None = None
        self.realized_net_pnl = Decimal("0")
        self.fees_paid = Decimal("0")
        self.lots: list[LotState] = []
        self.entry_fill_keys: set[str] = set()
        self.exit_fill_keys: set[str] = set()

    @property
    def remaining_risk_budget(self) -> Decimal:
        return max(Decimal("0"), self.initial_trade_risk_budget - self.current_aggregate_risk)

    @property
    def current_aggregate_risk(self) -> Decimal:
        return aggregate_risk(direction=self.direction, lots=self.lots, stop=self.executable_stop)

    @property
    def realized_r(self) -> Decimal:
        return self.realized_net_pnl / self.initial_trade_risk_budget

    def unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        if self.open_qty <= 0 or self.avg_entry is None:
            return Decimal("0")
        gross = ((mark_price - self.avg_entry) if self.direction == "LONG"
                 else (self.avg_entry - mark_price)) * self.open_qty
        return gross

    def unrealized_r(self, mark_price: Decimal) -> Decimal:
        return self.unrealized_pnl(mark_price) / self.initial_trade_risk_budget

    def total_trade_r(self, mark_price: Decimal) -> Decimal:
        return (self.realized_net_pnl + self.unrealized_pnl(mark_price)) / self.initial_trade_risk_budget

    def apply_entry_fill(self, fill: EntryFill) -> bool:
        if fill.execution_key in self.entry_fill_keys:
            return False
        if self.state is not PositionState.OPEN:
            raise ValueError("cannot add to position that is not OPEN")
        if fill.position_id != self.position_id or fill.direction != self.direction:
            raise ValueError("fill does not belong to position/direction")
        old_qty = self.open_qty
        old_notional = (self.avg_entry or Decimal("0")) * old_qty
        new_qty = old_qty + fill.filled_qty
        new_avg = (old_notional + fill.fill_price * fill.filled_qty) / new_qty
        candidate = LotState(
            execution_key=fill.execution_key, fill_price=fill.fill_price,
            filled_qty=fill.filled_qty, open_qty=fill.filled_qty,
            risk_buffer_per_unit=fill.risk_buffer_per_unit,
            scale_sequence_number=fill.scale_sequence_number,
            entry_reason=fill.entry_reason, setup_type=fill.setup_type, rule_id=fill.rule_id,
            metadata=dict(fill.metadata),
        )
        post_risk = aggregate_risk(
            direction=self.direction, lots=(*self.lots, candidate), stop=self.executable_stop
        )
        if post_risk > self.initial_trade_risk_budget:
            raise ValueError("confirmed fill would exceed immutable trade risk budget")
        self.lots.append(candidate)
        self.open_qty = new_qty
        self.avg_entry = new_avg
        self.entry_fill_keys.add(fill.execution_key)
        self.fees_paid += fill.fee
        self.realized_net_pnl -= fill.fee
        self._assert_invariants()
        return True

    def apply_exit_fill(self, fill: ExitFill) -> bool:
        if fill.execution_key in self.exit_fill_keys:
            return False
        if fill.position_id != self.position_id:
            raise ValueError("exit does not belong to position")
        if fill.filled_qty > self.open_qty:
            raise ValueError("exit quantity exceeds open quantity")
        if self.avg_entry is None or self.open_qty <= 0:
            raise ValueError("cannot exit empty position")
        pre_qty = self.open_qty
        gross = ((fill.fill_price - self.avg_entry) if self.direction == "LONG"
                 else (self.avg_entry - fill.fill_price)) * fill.filled_qty
        self.realized_net_pnl += gross - fill.fee
        self.fees_paid += fill.fee
        open_lots = [lot for lot in self.lots if lot.open_qty > 0]
        target_open_qty = pre_qty - fill.filled_qty
        allocated_open = Decimal("0")
        for idx, lot in enumerate(open_lots):
            original_open = lot.open_qty
            if idx == len(open_lots) - 1:
                new_open = target_open_qty - allocated_open
            else:
                new_open = original_open * target_open_qty / pre_qty
                allocated_open += new_open
            if new_open < 0 or new_open > original_open:
                raise AssertionError("pro-rata exit allocation produced impossible lot quantity")
            lot.open_qty = new_open
        self.open_qty -= fill.filled_qty
        self.exit_fill_keys.add(fill.execution_key)
        if self.open_qty == 0:
            self.avg_entry = None
            self.state = PositionState.CLOSED
        else:
            self.state = PositionState.PARTIALLY_EXITED
        self._assert_invariants()
        return True

    def update_executable_stop(self, new_stop: Decimal) -> None:
        if new_stop <= 0:
            raise ValueError("stop must be positive")
        if self.direction == "LONG" and new_stop < self.executable_stop:
            raise ValueError("Scale-In architecture may not widen a LONG stop")
        if self.direction == "SHORT" and new_stop > self.executable_stop:
            raise ValueError("Scale-In architecture may not widen a SHORT stop")
        old = self.executable_stop
        self.executable_stop = new_stop
        if self.current_aggregate_risk > self.initial_trade_risk_budget:
            self.executable_stop = old
            raise ValueError("stop update would violate immutable risk budget")
        self._assert_invariants()

    def _assert_invariants(self) -> None:
        if self.open_qty < 0:
            raise AssertionError("negative open quantity")
        summed = sum((lot.open_qty for lot in self.lots), Decimal("0"))
        if summed != self.open_qty:
            raise AssertionError("lot quantities do not reconcile")
        if self.current_aggregate_risk > self.initial_trade_risk_budget:
            raise AssertionError("aggregate risk exceeds budget")
        if self.open_qty == 0 and self.avg_entry is not None:
            raise AssertionError("closed/empty position cannot retain average entry")
        if self.open_qty > 0 and (self.avg_entry is None or self.avg_entry <= 0):
            raise AssertionError("open position requires positive average entry")

    def open_lots(self) -> tuple[LotState, ...]:
        return tuple(lot for lot in self.lots if lot.open_qty > 0)
