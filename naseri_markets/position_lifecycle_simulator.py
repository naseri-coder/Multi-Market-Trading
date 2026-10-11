"""Durable, deterministic PAPER order and position lifecycle simulator.

No broker, MetaTrader, HTTP, Telegram, scheduler or live execution path.
External order outcomes are *injected evidence*, never assumed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from .execution_contract_v1 import OrderSpec, OrderStatus, identity, positive


class LifecycleRefused(ValueError):
    """Fail-closed invalid transition or identity mismatch."""


def _canonical(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _spec_dict(spec: OrderSpec) -> dict[str, Any]:
    raw = asdict(spec)
    raw["instrument"]["market"] = spec.instrument.market.value
    raw["direction"] = spec.direction.value
    raw["kind"] = spec.kind.value
    raw["mode"] = spec.mode.value
    for name in ("quantity", "reference_entry", "stop", "target"):
        raw[name] = str(getattr(spec, name))
    return raw


def _decimal(value: Any, name: str) -> Decimal:
    if not isinstance(value, (str, Decimal)) or isinstance(value, bool):
        raise LifecycleRefused(f"INVALID_{name.upper()}")
    try:
        result = Decimal(value)
    except ArithmeticError as exc:
        raise LifecycleRefused(f"INVALID_{name.upper()}") from exc
    try:
        positive(result, name)
    except ValueError as exc:
        raise LifecycleRefused(f"INVALID_{name.upper()}") from exc
    return result


class PositionLifecycleSimulator:
    """One durable SQLite journal per nonproduction testing scope.

    Each action requires an idempotency key; identical retries replay the original
    receipt, altered retries are refused. All state changes and journal entries
    commit in one transaction. Unknown sends can ONLY be resolved with explicit
    reconciliation evidence, not retransmitted.
    """

    def __init__(
        self, path: str | Path, *, shared_connection: sqlite3.Connection | None = None,
    ) -> None:
        p = Path(path)
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise LifecycleRefused("NONREGULAR_SIMULATOR_PATH")
        p.parent.mkdir(parents=True, exist_ok=True)
        self._owns_connection = shared_connection is None
        self._db = shared_connection or sqlite3.connect(
            str(p), isolation_level=None, timeout=5
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("CREATE TABLE IF NOT EXISTS paper_orders ("
                         "order_id TEXT PRIMARY KEY, spec_digest TEXT NOT NULL, "
                         "snapshot TEXT NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS paper_order_events ("
                         "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "order_id TEXT NOT NULL, action_id TEXT NOT NULL, "
                         "request_digest TEXT NOT NULL, event_type TEXT NOT NULL, "
                         "snapshot TEXT NOT NULL, UNIQUE(order_id, action_id), "
                         "FOREIGN KEY(order_id) REFERENCES paper_orders(order_id))")
        self._db.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        if self._owns_connection:
            self._db.close()

    def __enter__(self) -> PositionLifecycleSimulator:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def state(self, order_id: str) -> dict[str, Any] | None:
        identity(order_id, "order_id")
        row = self._db.execute(
            "SELECT snapshot FROM paper_orders WHERE order_id=?", (order_id,)
        ).fetchone()
        return json.loads(row["snapshot"]) if row else None

    def events(self, order_id: str) -> list[dict[str, Any]]:
        identity(order_id, "order_id")
        return [
            {"seq": row["seq"], "action_id": row["action_id"],
             "event": row["event_type"], "snapshot": json.loads(row["snapshot"])}
            for row in self._db.execute(
                "SELECT seq,action_id,event_type,snapshot FROM paper_order_events "
                "WHERE order_id=? ORDER BY seq", (order_id,)
            )
        ]

    def _begin(self) -> None:
        if self._owns_connection:
            self._db.execute("BEGIN IMMEDIATE")
        elif not self._db.in_transaction:
            raise LifecycleRefused("SHARED_TRANSACTION_REQUIRED")

    def _commit(self) -> None:
        if self._owns_connection:
            self._db.execute("COMMIT")

    def _rollback(self) -> None:
        if self._owns_connection:
            self._db.execute("ROLLBACK")

    def _receipt(self, order_id: str, action_id: str, digest: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT request_digest,snapshot FROM paper_order_events "
            "WHERE order_id=? AND action_id=?", (order_id, action_id)
        ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != digest:
            raise LifecycleRefused("IDEMPOTENCY_KEY_PAYLOAD_CONFLICT")
        return json.loads(row["snapshot"])

    def _write_event(
        self, order_id: str, action_id: str, digest: str, event: str,
        snapshot: dict[str, Any],
    ) -> None:
        self._db.execute(
            "INSERT INTO paper_order_events "
            "(order_id,action_id,request_digest,event_type,snapshot) VALUES (?,?,?,?,?)",
            (order_id, action_id, digest, event, _canonical(snapshot)),
        )

    def create(self, spec: OrderSpec, *, action_id: str) -> dict[str, Any]:
        if not isinstance(spec, OrderSpec):
            raise LifecycleRefused("PAPER_ORDER_SPEC_REQUIRED")
        identity(action_id, "action_id")
        wire = _spec_dict(spec)
        digest = hashlib.sha256(_canonical({"event": "CREATE", "spec": wire}).encode()).hexdigest()
        self._begin()
        try:
            old = self._receipt(spec.order_id, action_id, digest)
            if old is not None:
                self._commit()
                return old
            existing = self._db.execute(
                "SELECT spec_digest FROM paper_orders WHERE order_id=?", (spec.order_id,)
            ).fetchone()
            if existing is not None:
                raise LifecycleRefused("ORDER_ID_ALREADY_EXISTS")
            snapshot = {
                "order_id": spec.order_id, "spec": wire,
                "status": OrderStatus.CREATED.value, "revision": 0,
                "remote_order_id": None,
                "filled_quantity": "0", "closed_quantity": "0",
                "fill_notional": "0", "average_fill_price": None,
                "current_stop": str(spec.stop),
                "open_position_quantity": "0",
            }
            self._db.execute(
                "INSERT INTO paper_orders VALUES (?,?,?)",
                (spec.order_id, digest, _canonical(snapshot)),
            )
            self._write_event(spec.order_id, action_id, digest, "CREATE", snapshot)
            self._commit()
            return snapshot
        except BaseException:
            self._rollback()
            raise

    def apply(
        self, order_id: str, *, action_id: str, event: str,
        quantity: str | Decimal | None = None,
        price: str | Decimal | None = None,
        stop: str | Decimal | None = None,
        remote_order_id: str | None = None,
        evidence: str | None = None,
    ) -> dict[str, Any]:
        identity(order_id, "order_id")
        identity(action_id, "action_id")
        allowed_events = {
            "SUBMIT", "MARK_UNKNOWN", "RECONCILE_ACK", "RECONCILE_REJECT",
            "ACK", "REJECT", "FILL", "CANCEL", "AMEND_STOP",
            "CLOSE_FILL", "EMERGENCY_CLOSE",
        }
        if event not in allowed_events:
            raise LifecycleRefused("UNKNOWN_EVENT")
        request = {
            "event": event, "quantity": str(quantity) if quantity is not None else None,
            "price": str(price) if price is not None else None,
            "stop": str(stop) if stop is not None else None,
            "remote_order_id": remote_order_id, "evidence": evidence,
        }
        digest = hashlib.sha256(_canonical(request).encode()).hexdigest()
        self._begin()
        try:
            previous = self._receipt(order_id, action_id, digest)
            if previous is not None:
                self._commit()
                return previous
            row = self._db.execute(
                "SELECT snapshot FROM paper_orders WHERE order_id=?", (order_id,)
            ).fetchone()
            if row is None:
                raise LifecycleRefused("UNKNOWN_ORDER")
            state = json.loads(row["snapshot"])
            self._transition(
                state, event=event, quantity=quantity, price=price, stop=stop,
                remote_order_id=remote_order_id, evidence=evidence,
            )
            state["revision"] += 1
            self._db.execute(
                "UPDATE paper_orders SET snapshot=? WHERE order_id=?",
                (_canonical(state), order_id),
            )
            self._write_event(order_id, action_id, digest, event, state)
            self._commit()
            return state
        except BaseException:
            self._rollback()
            raise

    @staticmethod
    def _transition(
        state: dict[str, Any], *, event: str,
        quantity: str | Decimal | None, price: str | Decimal | None,
        stop: str | Decimal | None, remote_order_id: str | None,
        evidence: str | None,
    ) -> None:
        status = OrderStatus(state["status"])
        total = Decimal(state["spec"]["quantity"])
        filled = Decimal(state["filled_quantity"])
        closed = Decimal(state["closed_quantity"])
        open_qty = filled - closed

        if event == "SUBMIT":
            if status is not OrderStatus.CREATED:
                raise LifecycleRefused("SUBMIT_RETRY_FORBIDDEN")
            state["status"] = OrderStatus.SENT_UNCONFIRMED.value
        elif event == "MARK_UNKNOWN":
            if status is not OrderStatus.SENT_UNCONFIRMED:
                raise LifecycleRefused("UNKNOWN_REQUIRES_SENT_ORDER")
            state["status"] = OrderStatus.SUBMISSION_UNKNOWN.value
        elif event in {"ACK", "RECONCILE_ACK"}:
            expected = (
                OrderStatus.SUBMISSION_UNKNOWN if event == "RECONCILE_ACK"
                else OrderStatus.SENT_UNCONFIRMED
            )
            if status is not expected:
                raise LifecycleRefused("ACK_INVALID_SOURCE_STATE")
            identity(remote_order_id, "remote_order_id")
            if event == "RECONCILE_ACK" and not evidence:
                raise LifecycleRefused("RECONCILIATION_EVIDENCE_REQUIRED")
            state["remote_order_id"] = remote_order_id
            state["status"] = OrderStatus.ACKNOWLEDGED.value
        elif event in {"REJECT", "RECONCILE_REJECT"}:
            expected = (
                OrderStatus.SUBMISSION_UNKNOWN if event == "RECONCILE_REJECT"
                else OrderStatus.SENT_UNCONFIRMED
            )
            if status is not expected:
                raise LifecycleRefused("REJECT_INVALID_SOURCE_STATE")
            if event == "RECONCILE_REJECT" and not evidence:
                raise LifecycleRefused("RECONCILIATION_EVIDENCE_REQUIRED")
            state["status"] = OrderStatus.REJECTED.value
        elif event == "FILL":
            if status not in {OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED}:
                raise LifecycleRefused("FILL_REQUIRES_ACKNOWLEDGEMENT")
            delta = _decimal(quantity, "quantity")
            fill_price = _decimal(price, "price")
            if filled + delta > total:
                raise LifecycleRefused("OVERFILL")
            # Fail closed if a gap would leave the simulated position outside
            # the original protective-stop geometry.
            protective_stop = Decimal(state["current_stop"])
            if state["spec"]["direction"] == "long" and fill_price <= protective_stop:
                raise LifecycleRefused("UNPROTECTED_LONG_FILL")
            if state["spec"]["direction"] == "short" and fill_price >= protective_stop:
                raise LifecycleRefused("UNPROTECTED_SHORT_FILL")
            cost = Decimal(state["fill_notional"]) + delta * fill_price
            filled += delta
            state["fill_notional"] = str(cost)
            state["filled_quantity"] = str(filled)
            state["average_fill_price"] = str(cost / filled)
            state["status"] = (
                OrderStatus.FILLED.value if filled == total
                else OrderStatus.PARTIALLY_FILLED.value
            )
        elif event == "CANCEL":
            if status not in {
                OrderStatus.CREATED, OrderStatus.ACKNOWLEDGED,
                OrderStatus.PARTIALLY_FILLED,
            }:
                raise LifecycleRefused("CANCEL_INVALID_SOURCE_STATE")
            state["status"] = OrderStatus.CANCELED.value
        elif event == "AMEND_STOP":
            if status not in {
                OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELED,
            } or open_qty <= 0:
                raise LifecycleRefused("NO_OPEN_POSITION_TO_PROTECT")
            next_stop = _decimal(stop, "stop")
            current = Decimal(state["current_stop"])
            if state["spec"]["direction"] == "long" and next_stop < current:
                raise LifecycleRefused("STOP_WIDENING_FORBIDDEN")
            if state["spec"]["direction"] == "short" and next_stop > current:
                raise LifecycleRefused("STOP_WIDENING_FORBIDDEN")
            state["current_stop"] = str(next_stop)
        elif event == "CLOSE_FILL":
            if status not in {OrderStatus.FILLED, OrderStatus.CANCELED}:
                raise LifecycleRefused("CANCEL_REMAINDER_BEFORE_CLOSE")
            delta = _decimal(quantity, "quantity")
            _decimal(price, "price")  # an actual simulated close fill price is mandatory
            if delta > open_qty:
                raise LifecycleRefused("OVERCLOSE")
            closed += delta
            state["closed_quantity"] = str(closed)
            if closed == filled:
                state["status"] = OrderStatus.CLOSED.value
        elif event == "EMERGENCY_CLOSE":
            if status not in {
                OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELED,
            } or open_qty <= 0:
                raise LifecycleRefused("NO_POSITION_TO_EMERGENCY_CLOSE")
            _decimal(price, "price")
            # SIMULATOR ONLY: an actual broker would require confirmed cancel
            # and separately confirmed protective/flatten executions.
            state["closed_quantity"] = str(filled)
            state["status"] = OrderStatus.CLOSED.value
        else:
            raise LifecycleRefused("UNSUPPORTED_EVENT")
        state["open_position_quantity"] = str(
            Decimal(state["filled_quantity"]) - Decimal(state["closed_quantity"])
        )
