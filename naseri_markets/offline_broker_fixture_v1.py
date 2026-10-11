"""Independent OFFLINE PAPER broker evidence source for Stage-4 failure tests.

Separate SQLite file and journal from the Stage-3 risk/order ledger.
No credentials, network access, exchange SDK, MetaTrader or order routing.
Evidence is a local *fixture*, never provider-authenticated truth.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from .execution_contract_v1 import OrderSpec, identity
from .risk_portfolio_manager_v1 import _order


class BrokerUnavailable(ValueError):
    """Offline fixture transport is disconnected or incomplete."""


class BrokerState(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


def _positive(value: Decimal | None, field: str) -> None:
    if (
        not isinstance(value, Decimal) or not value.is_finite() or value <= 0
    ):
        raise ValueError(f"INVALID_{field.upper()}")


def _nonnegative(value: Decimal, field: str) -> None:
    if (
        not isinstance(value, Decimal) or not value.is_finite() or value < 0
    ):
        raise ValueError(f"INVALID_{field.upper()}")


def _canon(value: dict) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def order_digest(spec: OrderSpec) -> str:
    if not isinstance(spec, OrderSpec):
        raise ValueError("PAPER_SPEC_REQUIRED")
    return hashlib.sha256(_canon(_order(spec)).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    order_id: str
    account_id: str
    spec_digest: str
    state: BrokerState
    remote_order_id: str | None
    requested_quantity: Decimal
    filled_quantity: Decimal
    average_fill_price: Decimal | None
    closed_quantity: Decimal = Decimal("0")
    average_close_price: Decimal | None = None

    def __post_init__(self) -> None:
        identity(self.order_id, "order_id")
        identity(self.account_id, "account_id")
        if not isinstance(self.spec_digest, str) or len(self.spec_digest) != 64 or any(
            c not in "0123456789abcdef" for c in self.spec_digest
        ):
            raise ValueError("INVALID_SPEC_DIGEST")
        if not isinstance(self.state, BrokerState):
            raise ValueError("INVALID_BROKER_STATE")
        if self.remote_order_id is not None:
            identity(self.remote_order_id, "remote_order_id")
        if self.state != BrokerState.REJECTED and self.remote_order_id is None:
            raise ValueError("REMOTE_ID_REQUIRED")
        _positive(self.requested_quantity, "requested_quantity")
        _nonnegative(self.filled_quantity, "filled_quantity")
        _nonnegative(self.closed_quantity, "closed_quantity")
        if not (
            self.closed_quantity <= self.filled_quantity <= self.requested_quantity
        ):
            raise ValueError("IMPOSSIBLE_BROKER_QUANTITIES")
        if self.filled_quantity > 0:
            _positive(self.average_fill_price, "average_fill_price")
        elif self.average_fill_price is not None:
            raise ValueError("UNEXPECTED_ENTRY_PRICE")
        if self.closed_quantity > 0:
            _positive(self.average_close_price, "average_close_price")
        elif self.average_close_price is not None:
            raise ValueError("UNEXPECTED_EXIT_PRICE")
        if self.state in {BrokerState.ACKNOWLEDGED, BrokerState.REJECTED} and (
            self.filled_quantity != 0 or self.closed_quantity != 0
        ):
            raise ValueError("INCONSISTENT_ZERO_FILL_STATE")
        if self.state == BrokerState.PARTIALLY_FILLED and not (
            0 < self.filled_quantity < self.requested_quantity
            and self.closed_quantity == 0
        ):
            raise ValueError("INVALID_PARTIAL_STATE")
        if self.state == BrokerState.FILLED and (
            self.filled_quantity != self.requested_quantity
        ):
            raise ValueError("INVALID_FULL_FILL_STATE")
        if self.state == BrokerState.CLOSED and not (
            self.filled_quantity > 0
            and self.closed_quantity == self.filled_quantity
        ):
            raise ValueError("INVALID_CLOSED_STATE")

    def wire(self) -> dict:
        return {
            "order_id": self.order_id, "account_id": self.account_id,
            "spec_digest": self.spec_digest, "state": self.state.value,
            "remote_order_id": self.remote_order_id,
            "requested_quantity": str(self.requested_quantity),
            "filled_quantity": str(self.filled_quantity),
            "average_fill_price": (
                str(self.average_fill_price) if self.average_fill_price is not None else None
            ),
            "closed_quantity": str(self.closed_quantity),
            "average_close_price": (
                str(self.average_close_price) if self.average_close_price is not None else None
            ),
        }

    @classmethod
    def from_wire(cls, wire: dict) -> BrokerOrder:
        return cls(
            order_id=wire["order_id"], account_id=wire["account_id"],
            spec_digest=wire["spec_digest"], state=BrokerState(wire["state"]),
            remote_order_id=wire["remote_order_id"],
            requested_quantity=Decimal(wire["requested_quantity"]),
            filled_quantity=Decimal(wire["filled_quantity"]),
            average_fill_price=(
                Decimal(wire["average_fill_price"])
                if wire["average_fill_price"] is not None else None
            ),
            closed_quantity=Decimal(wire["closed_quantity"]),
            average_close_price=(
                Decimal(wire["average_close_price"])
                if wire["average_close_price"] is not None else None
            ),
        )


@dataclass(frozen=True, slots=True)
class BrokerSnapshot:
    account_id: str
    revision: int
    captured_at: datetime
    complete: bool
    orders: tuple[BrokerOrder, ...]
    source: str = "OFFLINE_PAPER_BROKER_FIXTURE_V1"

    def __post_init__(self) -> None:
        identity(self.account_id, "account_id")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("INVALID_REVISION")
        if (
            not isinstance(self.captured_at, datetime)
            or self.captured_at.tzinfo is None
            or self.captured_at.utcoffset() is None
        ):
            raise ValueError("UTC_AWARE_CAPTURE_REQUIRED")
        if type(self.complete) is not bool:
            raise ValueError("COMPLETENESS_EXPLICITLY_REQUIRED")
        if not isinstance(self.orders, tuple) or any(
            not isinstance(item, BrokerOrder) for item in self.orders
        ):
            raise ValueError("BROKER_ORDER_TUPLE_REQUIRED")
        if self.source != "OFFLINE_PAPER_BROKER_FIXTURE_V1":
            raise ValueError("NO_LIVE_OR_UNKNOWN_PROVIDER_EVIDENCE")
        ids = [item.order_id for item in self.orders]
        remotes = [item.remote_order_id for item in self.orders
                   if item.remote_order_id is not None]
        if len(set(ids)) != len(ids) or len(set(remotes)) != len(remotes):
            raise ValueError("DUPLICATE_BROKER_IDENTITY")
        if any(item.account_id != self.account_id for item in self.orders):
            raise ValueError("CROSS_ACCOUNT_BROKER_SNAPSHOT")

    def wire(self) -> dict:
        return {
            "account_id": self.account_id, "revision": self.revision,
            "captured_at": self.captured_at.isoformat(),
            "complete": self.complete, "source": self.source,
            "orders": [o.wire() for o in sorted(self.orders, key=lambda o: o.order_id)],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canon(self.wire()).encode("utf-8")).hexdigest()


class IndependentPaperBrokerV1:
    """Persist simulated broker observations separately from Stage-3 SQLite."""

    def __init__(self, path: str | Path):
        p = Path(path)
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise BrokerUnavailable("NONREGULAR_BROKER_FIXTURE_PATH")
        p.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(p), isolation_level=None, timeout=5)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(
            "CREATE TABLE IF NOT EXISTS broker_account_revisions ("
            "account_id TEXT PRIMARY KEY, revision INTEGER NOT NULL);"
            "CREATE TABLE IF NOT EXISTS broker_orders ("
            "order_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, "
            "spec_digest TEXT NOT NULL, wire TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS broker_order_history ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "account_id TEXT NOT NULL, revision INTEGER NOT NULL, "
            "order_id TEXT NOT NULL, wire TEXT NOT NULL);"
        )
        self.connected = True

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> IndependentPaperBrokerV1:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def publish(self, spec: OrderSpec, observation: BrokerOrder) -> int:
        """Inject a mock provider outcome. Never invokes a real trade."""
        if not isinstance(spec, OrderSpec) or not isinstance(observation, BrokerOrder):
            raise ValueError("PAPER_FIXTURE_REQUIRED")
        if (
            observation.order_id != spec.order_id
            or observation.account_id != spec.account_id
            or observation.spec_digest != order_digest(spec)
            or observation.requested_quantity != spec.quantity
        ):
            raise ValueError("BROKER_FIXTURE_ORDER_IDENTITY_MISMATCH")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            old = self._db.execute(
                "SELECT account_id,spec_digest FROM broker_orders WHERE order_id=?",
                (spec.order_id,),
            ).fetchone()
            if old is not None and (
                old["account_id"] != spec.account_id
                or old["spec_digest"] != observation.spec_digest
            ):
                raise ValueError("BROKER_FIXTURE_IMMUTABLE_ORDER_IDENTITY")
            self._db.execute(
                "INSERT INTO broker_account_revisions VALUES (?,1) "
                "ON CONFLICT(account_id) DO UPDATE SET revision=revision+1",
                (spec.account_id,),
            )
            revision = self._db.execute(
                "SELECT revision FROM broker_account_revisions WHERE account_id=?",
                (spec.account_id,),
            ).fetchone()["revision"]
            wire = _canon(observation.wire())
            self._db.execute(
                "INSERT INTO broker_orders VALUES (?,?,?,?) "
                "ON CONFLICT(order_id) DO UPDATE SET wire=excluded.wire",
                (spec.order_id, spec.account_id, observation.spec_digest, wire),
            )
            self._db.execute(
                "INSERT INTO broker_order_history(account_id,revision,order_id,wire) "
                "VALUES (?,?,?,?)",
                (spec.account_id, revision, spec.order_id, wire),
            )
            self._db.execute("COMMIT")
            return revision
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def snapshot(
        self, account_id: str, *, captured_at: datetime | None = None,
        complete: bool = True,
    ) -> BrokerSnapshot:
        identity(account_id, "account_id")
        if not self.connected:
            raise BrokerUnavailable("PAPER_BROKER_DISCONNECTED")
        rev = self._db.execute(
            "SELECT revision FROM broker_account_revisions WHERE account_id=?",
            (account_id,),
        ).fetchone()
        records = [
            BrokerOrder.from_wire(json.loads(row["wire"]))
            for row in self._db.execute(
                "SELECT wire FROM broker_orders WHERE account_id=? ORDER BY order_id",
                (account_id,),
            )
        ]
        return BrokerSnapshot(
            account_id=account_id, revision=rev["revision"] if rev else 0,
            captured_at=captured_at or datetime.now(UTC), complete=complete,
            orders=tuple(records),
        )
