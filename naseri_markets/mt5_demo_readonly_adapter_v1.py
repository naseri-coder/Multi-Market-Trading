"""Stage 5: opt-in MT5 DEMO observation from an already initialized terminal.

This module never initializes, logs into, trades on, or shuts down a terminal.
The injected provider exposes only read methods; DEMO account identity is
checked before and after enumeration. No PAPER risk/order ledger is changed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from .execution_contract_v1 import identity


class MT5ReadRefused(ValueError):
    """Cannot prove correct DEMO account or complete active exposure view."""


class MT5ReadProvider(Protocol):
    ACCOUNT_TRADE_MODE_DEMO: int

    def terminal_info(self) -> Any: ...
    def account_info(self) -> Any: ...
    def positions_get(self) -> Any: ...
    def orders_get(self) -> Any: ...


def _field(source: Any, name: str) -> Any:
    if source is None:
        raise MT5ReadRefused("MT5_MISSING_INFORMATION")
    try:
        value = getattr(source, name)
    except (AttributeError, TypeError) as exc:
        raise MT5ReadRefused(f"MT5_MISSING_{name.upper()}") from exc
    if value is None:
        raise MT5ReadRefused(f"MT5_MISSING_{name.upper()}")
    return value


def _amount(source: Any, name: str, *, zero: bool = False) -> Decimal:
    value = _field(source, name)
    if isinstance(value, bool):
        raise MT5ReadRefused(f"MT5_INVALID_{name.upper()}")
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise MT5ReadRefused(f"MT5_INVALID_{name.upper()}") from exc
    if not result.is_finite() or result < 0 or (result == 0 and not zero):
        raise MT5ReadRefused(f"MT5_INVALID_{name.upper()}")
    return result


def _ticket(source: Any, name: str) -> int:
    result = _field(source, name)
    if type(result) is not int or result <= 0:
        raise MT5ReadRefused(f"MT5_INVALID_{name.upper()}")
    return result


def _name(source: Any, name: str) -> str:
    value = _field(source, name)
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise MT5ReadRefused(f"MT5_INVALID_{name.upper()}")
    return value


@dataclass(frozen=True, slots=True)
class DemoAccountExpectation:
    """Operator-pinned identity; numeric login is NEVER read from env by code."""

    account_id: str
    login: int
    server: str

    def __post_init__(self) -> None:
        identity(self.account_id, "account_id")
        if type(self.login) is not int or self.login <= 0:
            raise ValueError("EXPECTED_DEMO_LOGIN_REQUIRED")
        if not isinstance(self.server, str) or not self.server.strip():
            raise ValueError("EXPECTED_DEMO_SERVER_REQUIRED")


@dataclass(frozen=True, slots=True)
class MT5ActiveRecord:
    ticket: int
    symbol: str
    type_code: int
    volume: Decimal
    price_open: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    kind: str

    @classmethod
    def from_mt5(cls, source: Any, *, kind: str) -> MT5ActiveRecord:
        if kind not in {"POSITION", "PENDING_ORDER"}:
            raise MT5ReadRefused("UNKNOWN_ACTIVE_RECORD")
        code = _field(source, "type")
        if type(code) is not int or code < 0:
            raise MT5ReadRefused("MT5_INVALID_POSITION_OR_ORDER_TYPE")
        initial = _amount(source, "volume_initial") if kind == "PENDING_ORDER" else None
        current = _amount(source, "volume_current" if kind == "PENDING_ORDER" else "volume")
        if initial is not None and current > initial:
            raise MT5ReadRefused("MT5_ORDER_VOLUME_INCREASE_CONTRADICTION")
        return cls(
            ticket=_ticket(source, "ticket"),
            symbol=_name(source, "symbol"),
            type_code=code, volume=current,
            price_open=_amount(source, "price_open"),
            stop_loss=_amount(source, "sl", zero=True),
            take_profit=_amount(source, "tp", zero=True),
            kind=kind,
        )

    def wire(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket, "symbol": self.symbol,
            "type_code": self.type_code, "volume": str(self.volume),
            "price_open": str(self.price_open), "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit), "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class MT5DemoActiveSnapshot:
    account_id: str
    login: int
    server: str
    currency: str
    equity: Decimal
    free_margin: Decimal
    observed_at: datetime
    positions: tuple[MT5ActiveRecord, ...]
    pending_orders: tuple[MT5ActiveRecord, ...]
    source: str = "MT5_DEMO_ACTIVE_ONLY_READONLY_V1"

    def wire(self) -> dict[str, Any]:
        return {
            "mode": "DEMO_READ_ONLY", "account_id": self.account_id,
            "login": self.login, "server": self.server,
            "currency": self.currency, "equity": str(self.equity),
            "free_margin": str(self.free_margin),
            "observed_at": self.observed_at.isoformat(),
            "positions": [x.wire() for x in self.positions],
            "pending_orders": [x.wire() for x in self.pending_orders],
            "history_complete": False, "risk_authority": False,
            "broker_execution_authority": False, "source": self.source,
        }


class MT5DemoReadOnlyAdapterV1:
    """Snapshot active positions/orders from a pinned, connected DEMO account.

    Requires a provider already attached to the target terminal. No calls to
    initialize(), login(), shutdown(), order_send(), symbol_select(), etc.
    """

    def __init__(self, provider: MT5ReadProvider, expected: DemoAccountExpectation):
        if not isinstance(expected, DemoAccountExpectation):
            raise TypeError("EXPECTED_DEMO_IDENTITY_REQUIRED")
        self._provider = provider
        self._expected = expected

    def _guard(self) -> tuple[Any, Any]:
        # No trust is granted by server branding ('Demo') alone.
        terminal = self._provider.terminal_info()
        if _field(terminal, "connected") is not True:
            raise MT5ReadRefused("MT5_TERMINAL_DISCONNECTED")
        account = self._provider.account_info()
        mode = _field(account, "trade_mode")
        demo_constant = getattr(self._provider, "ACCOUNT_TRADE_MODE_DEMO", None)
        if type(demo_constant) is not int or type(mode) is not int:
            raise MT5ReadRefused("MT5_TRADE_MODE_UNVERIFIED")
        if mode != demo_constant:
            raise MT5ReadRefused("MT5_REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN")
        if _ticket(account, "login") != self._expected.login:
            raise MT5ReadRefused("MT5_DEMO_LOGIN_MISMATCH")
        if _name(account, "server") != self._expected.server:
            raise MT5ReadRefused("MT5_DEMO_SERVER_MISMATCH")
        return terminal, account

    def capture(self, *, observed_at: datetime | None = None) -> MT5DemoActiveSnapshot:
        self._guard()
        try:
            positions = self._provider.positions_get()
            pending = self._provider.orders_get()
        except Exception as exc:
            raise MT5ReadRefused("MT5_ACTIVE_QUERY_EXCEPTION") from exc
        if not isinstance(positions, (tuple, list)) or not isinstance(pending, (tuple, list)):
            raise MT5ReadRefused("MT5_ACTIVE_QUERY_INCOMPLETE")
        parsed_positions = tuple(
            MT5ActiveRecord.from_mt5(value, kind="POSITION") for value in positions
        )
        parsed_pending = tuple(
            MT5ActiveRecord.from_mt5(value, kind="PENDING_ORDER") for value in pending
        )
        for items in (parsed_positions, parsed_pending):
            if len({x.ticket for x in items}) != len(items):
                raise MT5ReadRefused("MT5_DUPLICATE_ACTIVE_TICKET")
        _, account = self._guard()  # detect account switch during the read
        observed = observed_at or datetime.now(UTC)
        if (
            not isinstance(observed, datetime)
            or observed.tzinfo is None
            or observed.utcoffset() is None
        ):
            raise MT5ReadRefused("MT5_OBSERVATION_TIMESTAMP_REQUIRED")
        return MT5DemoActiveSnapshot(
            account_id=self._expected.account_id, login=self._expected.login,
            server=self._expected.server, currency=_name(account, "currency"),
            equity=_amount(account, "equity", zero=True),
            free_margin=_amount(account, "margin_free", zero=True),
            observed_at=observed.astimezone(UTC),
            positions=tuple(sorted(parsed_positions, key=lambda x: x.ticket)),
            pending_orders=tuple(sorted(parsed_pending, key=lambda x: x.ticket)),
        )
