"""Stage 3 — atomic, offline PAPER risk-to-order lifecycle orchestration.

The Stage-1 lifecycle and Stage-2 risk manager share ONE SQLite connection.
All order creation, risk reservation, state mutation, terminal release and
orchestrator receipts commit or roll back as a SINGLE write transaction.

No broker, authenticated API, terminal, Telegram publisher, or worker.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from .contracts import Instrument
from .execution_contract_v1 import OrderSpec, identity
from .position_lifecycle_simulator import PositionLifecycleSimulator
from .risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy
from .risk_portfolio_manager_v1 import PaperRiskPortfolioManager, _order

_T = TypeVar("_T")


class OrchestrationRefused(ValueError):
    """A new PAPER operation was denied; no state change was committed."""


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class PaperExecutionOrchestratorV1:
    """Single-database, fail-closed, synchronous PAPER-only coordinator.

    Construct on a dedicated simulated-state SQLite file, NOT the stage-1
    or stage-2 databases from an existing standalone install. Reconciliation
    events require explicit injected evidence, not a real provider lookup.
    """

    def __init__(self, path: str | Path, *, clock: Callable[[], date] | None = None):
        p = Path(path)
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise OrchestrationRefused("NONREGULAR_ORCHESTRATION_PATH")
        p.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(p), timeout=5, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        # Schema creation is done once, before beginning any shared transaction.
        self._risk = PaperRiskPortfolioManager(
            p, clock=clock, shared_connection=self._db
        )
        self._orders = PositionLifecycleSimulator(p, shared_connection=self._db)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS paper_execution_actions ("
            "action_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
            "receipt TEXT NOT NULL)"
        )

    def close(self) -> None:
        self._orders.close()
        self._risk.close()
        self._db.close()

    def __enter__(self) -> PaperExecutionOrchestratorV1:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _transaction(self, callback: Callable[[], _T]) -> _T:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            result = callback()
            self._db.execute("COMMIT")
            return result
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def _action(
        self, *, action_id: str, payload: Mapping[str, Any],
        callback: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        identity(action_id, "action_id")
        digest = _hash(payload)

        def execute() -> dict[str, Any]:
            row = self._db.execute(
                "SELECT request_digest,receipt FROM paper_execution_actions "
                "WHERE action_id=?", (action_id,)
            ).fetchone()
            if row:
                if row["request_digest"] != digest:
                    raise OrchestrationRefused("GLOBAL_ACTION_ID_CONFLICT")
                return json.loads(row["receipt"])
            receipt = callback()
            self._db.execute(
                "INSERT INTO paper_execution_actions VALUES (?,?,?)",
                (action_id, digest, _canonical(receipt)),
            )
            return receipt

        return self._transaction(execute)

    def configure_portfolio(self, policy: PortfolioRiskPolicy) -> None:
        self._transaction(lambda: self._risk.configure_portfolio(policy))

    def configure_account(self, policy: AccountRiskPolicy) -> None:
        self._transaction(lambda: self._risk.configure_account(policy))

    def register_instrument(
        self, *, portfolio_id: str, instrument: Instrument, group_id: str,
    ) -> None:
        self._transaction(
            lambda: self._risk.register_instrument(
                portfolio_id=portfolio_id, instrument=instrument, group_id=group_id
            )
        )

    def create(self, spec: OrderSpec, *, action_id: str) -> dict[str, Any]:
        """Create order and reserve full modeled risk in ONE durable commit."""
        if not isinstance(spec, OrderSpec):
            raise OrchestrationRefused("ORDER_SPEC_REQUIRED")
        payload = {"operation": "CREATE", "spec": _order(spec)}

        def create_atomically() -> dict[str, Any]:
            reservation = self._risk.reserve(spec, action_id=action_id)
            order = self._orders.create(spec, action_id=action_id)
            return {
                "mode": "PAPER_ONLY", "operation": "CREATE",
                "order": order, "risk_reservation": reservation,
            }

        return self._action(
            action_id=action_id, payload=payload, callback=create_atomically
        )

    def _reservation(self, order_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT contract_json,status,portfolio_id FROM paper_risk_reservations "
            "WHERE order_id=?", (order_id,)
        ).fetchone()
        if row is None or row["status"] != "ACTIVE":
            raise OrchestrationRefused("ACTIVE_RISK_RESERVATION_REQUIRED")
        return row

    def apply(
        self, order_id: str, *, action_id: str, event: str,
        quantity: str | None = None, price: str | None = None,
        stop: str | None = None, remote_order_id: str | None = None,
        evidence: str | None = None,
    ) -> dict[str, Any]:
        """Simulate a lifecycle event; release budget on *verified* terminal state.

        All actions are offline injections; ACK/FILL do not represent actual
        exchange/broker confirmations. No release on unknown/partial/open.
        """
        identity(order_id, "order_id")
        arguments = {
            "operation": "APPLY", "order_id": order_id, "event": event,
            "quantity": quantity, "price": price, "stop": stop,
            "remote_order_id": remote_order_id, "evidence": evidence,
        }

        def apply_atomically() -> dict[str, Any]:
            reservation = self._reservation(order_id)
            current = self._orders.state(order_id)
            if current is None:
                raise OrchestrationRefused("RESERVED_ORDER_STATE_MISSING")
            if current["spec"] != json.loads(reservation["contract_json"]):
                raise OrchestrationRefused("RESERVED_ORDER_SPEC_MISMATCH")
            updated = self._orders.apply(
                order_id, action_id=action_id, event=event,
                quantity=quantity, price=price, stop=stop,
                remote_order_id=remote_order_id, evidence=evidence,
            )
            filled = Decimal(updated["filled_quantity"])
            closed = Decimal(updated["closed_quantity"])
            paper_loss = Decimal("0")
            if event in {"CLOSE_FILL", "EMERGENCY_CLOSE"}:
                delta = closed - Decimal(current["closed_quantity"])
                if delta <= 0:
                    raise OrchestrationRefused("CLOSE_DELTA_REQUIRED")
                entry = Decimal(updated["average_fill_price"])
                exit_price = Decimal(price)
                policy = json.loads(self._risk._account(
                    current["spec"]["account_id"]
                )["policy"])
                multiplier = Decimal(policy["contract_multiplier"])
                friction = (
                    Decimal(policy["roundtrip_fee_fraction"])
                    + Decimal(policy["worst_slippage_fraction"])
                )
                direction = Decimal("1") if current["spec"]["direction"] == "long" else Decimal("-1")
                gross = direction * (exit_price - entry) * delta * multiplier
                modeled_cost = max(entry, exit_price) * delta * multiplier * friction
                paper_loss = max(Decimal("0"), modeled_cost - gross)
                if paper_loss > 0:
                    loss_action = "internal-loss-" + _hash({
                        "order": order_id, "action_id": action_id,
                    })[:40]
                    self._risk.record_loss(
                        current["spec"]["account_id"],
                        action_id=loss_action, amount=paper_loss,
                    )
            terminal = (
                (updated["status"] in {"CANCELED", "REJECTED"} and filled == 0)
                or (updated["status"] == "CLOSED" and filled == closed)
            )
            release: dict[str, Any] | None = None
            if terminal:
                release_action = "internal-release-" + _hash(
                    {"order": order_id, "action_id": action_id}
                )[:40]
                release = self._risk.release(
                    order_id, action_id=release_action,
                    lifecycle_snapshot=updated,
                    evidence="ATOMIC_STAGE3_PAPER_LEDGER",
                )
            return {
                "mode": "PAPER_ONLY", "operation": event, "order": updated,
                "risk_released": release is not None,
                "risk_release": release,
                "modeled_realized_loss": str(paper_loss),
            }

        return self._action(
            action_id=action_id, payload=arguments, callback=apply_atomically
        )

    def record_loss(self, account_id: str, *, action_id: str, amount: Any) -> dict[str, Any]:
        receipt = {
            "operation": "RECORD_LOSS", "account_id": account_id, "amount": str(amount)
        }
        return self._action(
            action_id=action_id, payload=receipt,
            callback=lambda: self._risk.record_loss(
                account_id, action_id=action_id, amount=amount
            ),
        )

    def halt(
        self, *, portfolio_id: str, scope: str, subject_id: str, action_id: str,
    ) -> dict[str, Any]:
        receipt = {"operation": "HALT", "portfolio_id": portfolio_id,
                   "scope": scope, "subject_id": subject_id}
        return self._action(
            action_id=action_id, payload=receipt,
            callback=lambda: self._risk.halt(
                portfolio_id=portfolio_id, scope=scope,
                subject_id=subject_id, action_id=action_id,
            ),
        )

    def order_state(self, order_id: str) -> dict[str, Any] | None:
        return self._orders.state(order_id)

    def order_events(self, order_id: str) -> list[dict[str, Any]]:
        return self._orders.events(order_id)

    def risk_snapshot(self, portfolio_id: str) -> dict[str, Any]:
        return self._risk.snapshot(portfolio_id)

    def risk_audit(self) -> list[dict[str, Any]]:
        return self._risk.audit()
