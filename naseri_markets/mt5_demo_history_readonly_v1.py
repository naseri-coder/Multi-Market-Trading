"""Stage 6 — bounded MT5 DEMO history observation, never order execution.

history_orders_get/history_deals_get are *date-range* read endpoints.
Capture is window-complete only when both endpoint counts agree for every
bounded slice, but it is NEVER proof of all-time broker history.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from .mt5_demo_readonly_adapter_v1 import (
    DemoAccountExpectation,
    MT5DemoReadOnlyAdapterV1,
    MT5ReadRefused,
    _amount,
    _field,
    _name,
    _ticket,
)


class MT5HistoryRefused(MT5ReadRefused):
    """An incomplete, ambiguous, or non-DEMO history read is refused."""


class MT5HistoryProvider(Protocol):
    def history_orders_get(self, date_from: datetime, date_to: datetime) -> Any: ...
    def history_deals_get(self, date_from: datetime, date_to: datetime) -> Any: ...
    def history_orders_total(self, date_from: datetime, date_to: datetime) -> int: ...
    def history_deals_total(self, date_from: datetime, date_to: datetime) -> int: ...


def _int(source: Any, field: str, *, zero: bool = True) -> int:
    value = _field(source, field)
    if type(value) is not int or value < 0 or (value == 0 and not zero):
        raise MT5HistoryRefused(f"MT5_INVALID_{field.upper()}")
    return value


def _signed(source: Any, field: str) -> Decimal:
    value = _field(source, field)
    if isinstance(value, bool):
        raise MT5HistoryRefused(f"MT5_INVALID_{field.upper()}")
    try:
        result = Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:
        raise MT5HistoryRefused(f"MT5_INVALID_{field.upper()}") from exc
    if not result.is_finite():
        raise MT5HistoryRefused(f"MT5_INVALID_{field.upper()}")
    return result


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MT5HistoryRefused(f"{label}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class MT5HistoricalOrder:
    ticket: int
    position_id: int
    symbol: str
    type_code: int
    state_code: int
    time_setup_msc: int
    time_done_msc: int
    volume_initial: Decimal
    volume_current: Decimal
    price_open: Decimal

    @classmethod
    def parse(cls, source: Any) -> MT5HistoricalOrder:
        initial = _amount(source, "volume_initial")
        remaining = _amount(source, "volume_current", zero=True)
        if remaining > initial:
            raise MT5HistoryRefused("ORDER_REMAINING_EXCEEDS_INITIAL_VOLUME")
        return cls(
            ticket=_ticket(source, "ticket"), position_id=_int(source, "position_id"),
            symbol=_name(source, "symbol"), type_code=_int(source, "type"),
            state_code=_int(source, "state"),
            time_setup_msc=_int(source, "time_setup_msc"),
            time_done_msc=_int(source, "time_done_msc"),
            volume_initial=initial, volume_current=remaining,
            price_open=_amount(source, "price_open", zero=True),
        )

    def wire(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket, "position_id": self.position_id,
            "symbol": self.symbol, "type_code": self.type_code,
            "state_code": self.state_code, "time_setup_msc": self.time_setup_msc,
            "time_done_msc": self.time_done_msc,
            "volume_initial": str(self.volume_initial),
            "volume_current": str(self.volume_current),
            "price_open": str(self.price_open),
        }


@dataclass(frozen=True, slots=True)
class MT5HistoricalDeal:
    ticket: int
    order_ticket: int
    position_id: int
    symbol: str
    type_code: int
    entry_code: int
    time_msc: int
    volume: Decimal
    price: Decimal
    profit: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal

    @classmethod
    def parse(cls, source: Any) -> MT5HistoricalDeal:
        kind = _int(source, "type")
        entry = _int(source, "entry")
        is_trade = kind in (0, 1)
        symbol = _name(source, "symbol") if is_trade else _field(source, "symbol")
        if not is_trade and not isinstance(symbol, str):
            raise MT5HistoryRefused("INVALID_NONTRADE_SYMBOL")
        if is_trade and entry not in (0, 1, 2, 3):
            raise MT5HistoryRefused("UNSUPPORTED_TRADE_ENTRY_CODE")
        volume = _amount(source, "volume", zero=not is_trade)
        price = _amount(source, "price", zero=not is_trade)
        order_id = _int(source, "order")
        position_id = _int(source, "position_id")
        if is_trade and (order_id == 0 or position_id == 0):
            raise MT5HistoryRefused("TRADE_DEAL_MISSING_ORDER_OR_POSITION")
        return cls(
            ticket=_ticket(source, "ticket"), order_ticket=order_id,
            position_id=position_id, symbol=symbol, type_code=kind,
            entry_code=entry, time_msc=_int(source, "time_msc"),
            volume=volume, price=price,
            profit=_signed(source, "profit"),
            commission=_signed(source, "commission"),
            swap=_signed(source, "swap"), fee=_signed(source, "fee"),
        )

    def wire(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket, "order_ticket": self.order_ticket,
            "position_id": self.position_id, "symbol": self.symbol,
            "type_code": self.type_code, "entry_code": self.entry_code,
            "time_msc": self.time_msc, "volume": str(self.volume),
            "price": str(self.price), "profit": str(self.profit),
            "commission": str(self.commission), "swap": str(self.swap),
            "fee": str(self.fee),
        }


@dataclass(frozen=True, slots=True)
class MT5DemoHistorySnapshot:
    account_id: str
    login: int
    server: str
    start_utc: datetime
    end_utc: datetime
    captured_at: datetime
    orders: tuple[MT5HistoricalOrder, ...]
    deals: tuple[MT5HistoricalDeal, ...]
    slices: int
    source: str = "MT5_DEMO_BOUNDED_HISTORY_READONLY_V1"

    def wire(self) -> dict[str, Any]:
        return {
            "mode": "DEMO_HISTORY_READ_ONLY", "source": self.source,
            "account_id": self.account_id, "login": self.login, "server": self.server,
            "start_utc": self.start_utc.isoformat(), "end_utc": self.end_utc.isoformat(),
            "captured_at": self.captured_at.isoformat(), "slices": self.slices,
            "window_complete": True, "all_time_history_complete": False,
            "orders": [o.wire() for o in self.orders],
            "deals": [d.wire() for d in self.deals],
            "risk_authority": False, "execution_authority": False,
            "stage4_reconciliation_authority": False,
        }

    @property
    def digest(self) -> str:
        value = self.wire()
        value.pop("captured_at")  # repeated observation of same window is stable
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()


class MT5DemoHistoryReaderV1:
    """Pull bounded DEMO history using *only* read methods on injected provider.

    No automatic retries on partial failure: repeated snapshots must be
    independently validated, and no incomplete slice is returned.
    """

    def __init__(
        self, provider: MT5HistoryProvider, expected: DemoAccountExpectation,
        *, slice_span: timedelta = timedelta(days=1), max_slices: int = 31,
        max_rows: int = 50000,
    ):
        if not timedelta(0) < slice_span <= timedelta(days=1):
            raise ValueError("INVALID_HISTORY_SLICE_SPAN")
        if type(max_slices) is not int or not 1 <= max_slices <= 366:
            raise ValueError("INVALID_HISTORY_MAX_SLICES")
        if type(max_rows) is not int or not 1 <= max_rows <= 200000:
            raise ValueError("INVALID_HISTORY_MAX_ROWS")
        self._provider = provider
        self._guard = MT5DemoReadOnlyAdapterV1(provider, expected)
        self._expected = expected
        self._span = slice_span
        self._max_slices = max_slices
        self._max_rows = max_rows

    def capture(
        self, start: datetime, end: datetime,
        *, captured_at: datetime | None = None,
    ) -> MT5DemoHistorySnapshot:
        a, b = _utc(start, "START"), _utc(end, "END")
        if b <= a or b - a > self._span * self._max_slices:
            raise MT5HistoryRefused("HISTORY_RANGE_OUT_OF_BOUNDS")
        self._guard._guard()
        orders: dict[int, MT5HistoricalOrder] = {}
        deals: dict[int, MT5HistoricalDeal] = {}
        parts = 0
        cursor = a
        while cursor < b:
            last = min(cursor + self._span, b)
            self._guard._guard()
            try:
                order_result = self._provider.history_orders_get(cursor, last)
                deal_result = self._provider.history_deals_get(cursor, last)
                order_total = self._provider.history_orders_total(cursor, last)
                deal_total = self._provider.history_deals_total(cursor, last)
            except Exception as exc:
                raise MT5HistoryRefused("MT5_HISTORY_QUERY_FAILURE") from exc
            # Detect terminal switching before accepting any queried rows.
            self._guard._guard()
            if not isinstance(order_result, (tuple, list)) or not isinstance(
                deal_result, (tuple, list)
            ):
                raise MT5HistoryRefused("MT5_HISTORY_INCOMPLETE_RESPONSE")
            if (
                type(order_total) is not int or type(deal_total) is not int
                or order_total < 0 or deal_total < 0
                or len(order_result) != order_total or len(deal_result) != deal_total
            ):
                raise MT5HistoryRefused("MT5_HISTORY_TOTAL_MISMATCH")
            if len(order_result) + len(deal_result) > self._max_rows:
                raise MT5HistoryRefused("MT5_HISTORY_SLICE_TOO_LARGE")
            for raw, factory, target in (
                (order_result, MT5HistoricalOrder.parse, orders),
                (deal_result, MT5HistoricalDeal.parse, deals),
            ):
                for entry in raw:
                    item = factory(entry)
                    previous = target.get(item.ticket)
                    if previous is not None and previous != item:
                        raise MT5HistoryRefused("MT5_HISTORY_TICKET_REPLAY_CONFLICT")
                    target[item.ticket] = item
            if len(orders) + len(deals) > self._max_rows:
                raise MT5HistoryRefused("MT5_HISTORY_TOO_MANY_ROWS")
            parts += 1
            cursor = last
        self._guard._guard()
        return MT5DemoHistorySnapshot(
            account_id=self._expected.account_id, login=self._expected.login,
            server=self._expected.server, start_utc=a, end_utc=b,
            captured_at=_utc(captured_at or datetime.now(UTC), "CAPTURE"),
            orders=tuple(sorted(orders.values(), key=lambda v: v.ticket)),
            deals=tuple(sorted(deals.values(), key=lambda v: v.ticket)),
            slices=parts,
        )
