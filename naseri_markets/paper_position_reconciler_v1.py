"""Stage-4 OFFLINE broker-vs-internal reconciliation and crash recovery.

This uses an independent PAPER fixture, not a real venue data source.
Any ambiguity is quarantined. No broker send, cancel or network operations.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .execution_contract_v1 import identity
from .execution_position_core_v1 import PaperExecutionOrchestratorV1
from .offline_broker_fixture_v1 import (
    BrokerOrder,
    BrokerSnapshot,
    BrokerState,
    BrokerUnavailable,
    IndependentPaperBrokerV1,
)


class ReconciliationRefused(ValueError):
    """Account discrepancy cannot be safely resolved automatically."""


class PaperPositionReconcilerV1:
    """Per-account checkpoint, single-ledger replay and fail-closed fences.

    The local orchestrator owns each transaction. An account is explicitly
    enrolled before this module gates its new-risk authority. A different
    orchestrator instance must reconcile again after restart.
    """

    def __init__(
        self, core: PaperExecutionOrchestratorV1, *,
        clock: Callable[[], datetime] | None = None,
        max_age: timedelta = timedelta(minutes=5),
    ):
        if not isinstance(core, PaperExecutionOrchestratorV1):
            raise TypeError("STAGE3_CORE_REQUIRED")
        if not timedelta(0) < max_age <= timedelta(hours=1):
            raise ValueError("INVALID_SNAPSHOT_MAX_AGE")
        self._core = core
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_age = max_age
        db = self._core._db
        db.executescript(
            "CREATE TABLE IF NOT EXISTS paper_recovery_fences ("
            "account_id TEXT PRIMARY KEY, state TEXT NOT NULL "
            "CHECK(state IN ('BLOCKED','READY')), "
            "owner_instance TEXT, revision INTEGER, digest TEXT);"
            "CREATE TABLE IF NOT EXISTS paper_recovery_audit ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "account_id TEXT NOT NULL, revision INTEGER, "
            "status TEXT NOT NULL, detail TEXT NOT NULL);"
        )

    def install(self, account_id: str) -> dict:
        """Enroll a PAPER account; conservatively prevent new orders."""
        identity(account_id, "account_id")

        def installed() -> dict:
            self._core._risk._account(account_id)
            row = self._core._db.execute(
                "SELECT state FROM paper_recovery_fences WHERE account_id=?",
                (account_id,),
            ).fetchone()
            if row is None:
                self._core._db.execute(
                    "INSERT INTO paper_recovery_fences(account_id,state) "
                    "VALUES (?,'BLOCKED')", (account_id,),
                )
                self._audit(account_id, None, "ENROLLED", "RECONCILIATION_REQUIRED")
            return {"account_id": account_id, "state": "BLOCKED"
                    if row is None else row["state"],
                    "mode": "OFFLINE_PAPER_RECONCILIATION"}

        return self._core._transaction(installed)

    def fence(self, account_id: str) -> dict:
        identity(account_id, "account_id")
        row = self._core._db.execute(
            "SELECT * FROM paper_recovery_fences WHERE account_id=?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise ReconciliationRefused("ACCOUNT_NOT_ENROLLED")
        ready = row["state"] == "READY" and (
            row["owner_instance"] == self._core._recovery_instance_id
        )
        return {
            "account_id": account_id, "ready_for_new_paper_risk": ready,
            "state": row["state"] if ready else "BLOCKED",
            "last_revision": row["revision"],
        }

    def audit(self, account_id: str) -> list[dict]:
        identity(account_id, "account_id")
        return [
            {"seq": row["seq"], "revision": row["revision"],
             "status": row["status"], "detail": row["detail"]}
            for row in self._core._db.execute(
                "SELECT * FROM paper_recovery_audit WHERE account_id=? ORDER BY seq",
                (account_id,),
            )
        ]

    def _audit(
        self, account_id: str, revision: int | None, status: str, detail: str,
    ) -> None:
        self._core._db.execute(
            "INSERT INTO paper_recovery_audit(account_id,revision,status,detail) "
            "VALUES (?,?,?,?)", (account_id, revision, status, detail),
        )

    def _clock_now(self) -> datetime:
        now = self._clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None or now.utcoffset() is None
        ):
            raise ReconciliationRefused("UTC_AWARE_CLOCK_REQUIRED")
        return now.astimezone(UTC)

    def _quarantine(
        self, account_id: str, *, revision: int | None, reason: str,
    ) -> dict:
        """Commit account-wide halt even if the reconciliation batch rolled back."""
        def blocked() -> None:
            row = self._core._risk._account(account_id)
            fence = self._core._db.execute(
                "SELECT 1 FROM paper_recovery_fences WHERE account_id=?",
                (account_id,),
            ).fetchone()
            if not fence:
                raise ReconciliationRefused("ACCOUNT_NOT_ENROLLED")
            self._core._db.execute(
                "UPDATE paper_recovery_fences SET state='BLOCKED', "
                "owner_instance=NULL WHERE account_id=?", (account_id,),
            )
            self._core._db.execute(
                "UPDATE risk_accounts SET halted=1 WHERE account_id=?", (account_id,)
            )
            self._core._risk._audit(
                self._core._risk._touch(row["portfolio_id"]),
                "HALT", account_id,
                {"scope": "account", "cause": "PAPER_RECONCILIATION", "reason": reason},
            )
            self._audit(account_id, revision, "QUARANTINED", reason)

        self._core._transaction(blocked)
        return {
            "account_id": account_id, "status": "QUARANTINED",
            "reason": reason, "new_risk_halted": True,
            "mode": "OFFLINE_PAPER_RECONCILIATION",
        }

    def scan(
        self, account_id: str, broker: IndependentPaperBrokerV1,
    ) -> dict:
        """Request a complete simulated external account snapshot."""
        identity(account_id, "account_id")
        if not isinstance(broker, IndependentPaperBrokerV1):
            raise TypeError("OFFLINE_BROKER_FIXTURE_REQUIRED")
        try:
            snapshot = broker.snapshot(account_id)
        except BrokerUnavailable as exc:
            return self._quarantine(
                account_id, revision=None, reason=str(exc),
            )
        return self.reconcile(account_id, snapshot)

    def reconcile(
        self, account_id: str, snapshot: BrokerSnapshot,
    ) -> dict:
        """Atomically reconcile safe order transitions and commit one cursor.

        Contradictions, stale/incomplete snapshots and unexpected exposure
        roll the ENTIRE replay back then permanently halt new account risk.
        """
        identity(account_id, "account_id")
        if not isinstance(snapshot, BrokerSnapshot):
            return self._quarantine(
                account_id, revision=None, reason="BROKER_SNAPSHOT_REQUIRED",
            )
        revision = snapshot.revision
        try:
            return self._core._transaction(
                lambda: self._reconcile_locked(account_id, snapshot)
            )
        except (ValueError, TypeError, ArithmeticError, sqlite3.Error) as exc:
            # No intermediary ledger change survives a failed reconciliation.
            return self._quarantine(
                account_id, revision=revision,
                reason=str(exc) or type(exc).__name__,
            )

    def _reconcile_locked(
        self, account_id: str, snapshot: BrokerSnapshot,
    ) -> dict:
        self._core._risk._account(account_id)
        fence = self._core._db.execute(
            "SELECT * FROM paper_recovery_fences WHERE account_id=?",
            (account_id,),
        ).fetchone()
        if fence is None:
            raise ReconciliationRefused("ACCOUNT_NOT_ENROLLED")
        if snapshot.account_id != account_id:
            raise ReconciliationRefused("CROSS_ACCOUNT_SNAPSHOT")
        if not snapshot.complete:
            raise ReconciliationRefused("INCOMPLETE_BROKER_SNAPSHOT")
        now = self._clock_now()
        timestamp = snapshot.captured_at.astimezone(UTC)
        if now - timestamp > self._max_age or timestamp - now > timedelta(seconds=30):
            raise ReconciliationRefused("STALE_OR_FUTURE_BROKER_SNAPSHOT")
        if (
            fence["revision"] is not None
            and snapshot.revision < fence["revision"]
        ):
            raise ReconciliationRefused("BROKER_REVISION_ROLLBACK")
        if (
            fence["revision"] == snapshot.revision
            and fence["digest"] != snapshot.digest
        ):
            raise ReconciliationRefused("BROKER_SAME_REVISION_DIGEST_CONFLICT")
        observations = {item.order_id: item for item in snapshot.orders}
        local = {
            order["order_id"]: order
            for row in self._core._db.execute("SELECT snapshot FROM paper_orders")
            if (
                (order := json.loads(row["snapshot"]))["spec"]["account_id"]
                == account_id
            )
        }
        for order_id, ext in observations.items():
            if order_id not in local:
                raise ReconciliationRefused("UNTRACKED_BROKER_ORDER")
            if ext.spec_digest != hashlib.sha256(
                json.dumps(local[order_id]["spec"], sort_keys=True,
                           separators=(",", ":"), ensure_ascii=True).encode()
            ).hexdigest():
                raise ReconciliationRefused("BROKER_ORDER_SPEC_CONFLICT")
        for order_id, internal in local.items():
            if internal["status"] == "CREATED" and order_id not in observations:
                continue
            if order_id not in observations:
                raise ReconciliationRefused("SUBMITTED_ORDER_MISSING_FROM_SNAPSHOT")
            if internal["status"] == "CREATED":
                raise ReconciliationRefused("UNEXPECTED_BROKER_ORDER_BEFORE_SUBMIT")

        actions: list[dict] = []
        for order_id in sorted(local):
            if order_id in observations:
                actions.extend(self._repair(
                    account_id, snapshot.revision, local[order_id],
                    observations[order_id],
                ))
        self._core._db.execute(
            "UPDATE paper_recovery_fences SET state='READY', "
            "owner_instance=?, revision=?, digest=? WHERE account_id=?",
            (self._core._recovery_instance_id, snapshot.revision,
             snapshot.digest, account_id),
        )
        self._audit(
            account_id, snapshot.revision, "RECONCILED",
            f"actions={len(actions)};digest={snapshot.digest[:16]}",
        )
        return {
            "account_id": account_id,
            "mode": "OFFLINE_PAPER_RECONCILIATION",
            "status": "RECONCILED", "revision": snapshot.revision,
            "repaired": actions,
            "new_risk_permitted_by_recovery_fence": True,
            # Stage-2's independent hard halt is deliberately not relaxed.
            "account_hard_halted": bool(self._core._risk._account(account_id)["halted"]),
        }

    def _step(
        self, *, account_id: str, revision: int,
        order_id: str, event: str, step: int, **kwargs: str,
    ) -> dict:
        action_id = "paper-recon-" + hashlib.sha256(json.dumps(
            [account_id, revision, order_id, event, step],
            separators=(",", ":"),
        ).encode()).hexdigest()[:48]
        response = self._core.apply(
            order_id, action_id=action_id, event=event, **kwargs
        )
        return {"order_id": order_id, "event": event,
                "status": response["order"]["status"]}

    def _repair(
        self, account_id: str, revision: int,
        original: dict, external: BrokerOrder,
    ) -> list[dict]:
        order_id = original["order_id"]
        total = Decimal(original["spec"]["quantity"])
        if total != external.requested_quantity:
            raise ReconciliationRefused("BROKER_QUANTITY_CONFLICT")
        status = original["status"]
        broker_status = external.state.value
        active = self._core._db.execute(
            "SELECT status FROM paper_risk_reservations WHERE order_id=?",
            (order_id,),
        ).fetchone()
        if active is None:
            raise ReconciliationRefused("MISSING_INTERNAL_RISK_RESERVATION")
        if active["status"] == "RELEASED":
            local_filled = Decimal(original["filled_quantity"])
            local_closed = Decimal(original["closed_quantity"])
            if (
                status != broker_status
                or local_filled != external.filled_quantity
                or local_closed != external.closed_quantity
            ):
                raise ReconciliationRefused("RELEASED_ORDER_BROKER_DRIFT")
            if (
                original["remote_order_id"] is not None
                and original["remote_order_id"] != external.remote_order_id
            ):
                raise ReconciliationRefused("REMOTE_ORDER_ID_CONFLICT")
            return []
        if status == "CREATED":
            raise ReconciliationRefused("EXTERNAL_ORDER_UNEXPECTED_FOR_CREATED")
        if external.state == BrokerState.REJECTED:
            if status not in {"SENT_UNCONFIRMED", "SUBMISSION_UNKNOWN"}:
                raise ReconciliationRefused("LATE_BROKER_REJECTION_CONFLICT")
        elif (
            status not in {"SENT_UNCONFIRMED", "SUBMISSION_UNKNOWN"}
            and original["remote_order_id"] != external.remote_order_id
        ):
            raise ReconciliationRefused("REMOTE_ORDER_ID_CONFLICT")

        steps: list[dict] = []

        def step(event: str, **kwargs: str) -> None:
            steps.append(self._step(
                account_id=account_id, revision=revision,
                order_id=order_id, event=event, step=len(steps), **kwargs,
            ))

        evidence = f"OFFLINE_PAPER_ACCOUNT_REV_{revision}"
        if status in {"SENT_UNCONFIRMED", "SUBMISSION_UNKNOWN"}:
            if external.state == BrokerState.REJECTED:
                step(
                    "RECONCILE_REJECT" if status == "SUBMISSION_UNKNOWN" else "REJECT",
                    evidence=evidence,
                )
                return steps
            step(
                "RECONCILE_ACK" if status == "SUBMISSION_UNKNOWN" else "ACK",
                remote_order_id=external.remote_order_id, evidence=evidence,
            )
        updated = self._core.order_state(order_id)
        filled = Decimal(updated["filled_quantity"])
        closed = Decimal(updated["closed_quantity"])
        if external.filled_quantity < filled or external.closed_quantity < closed:
            raise ReconciliationRefused("BROKER_CUMULATIVE_QUANTITY_REGRESSION")
        if filled > 0 and external.filled_quantity == filled and (
            Decimal(updated["average_fill_price"]) != external.average_fill_price
        ):
            raise ReconciliationRefused("BROKER_ENTRY_PRICE_DRIFT")
        if external.filled_quantity > filled:
            if updated["status"] not in {"ACKNOWLEDGED", "PARTIALLY_FILLED"}:
                raise ReconciliationRefused("UNSUPPORTED_LATE_FILL_AFTER_CANCEL")
            difference = external.filled_quantity - filled
            total_notional = (
                external.filled_quantity * external.average_fill_price
            )
            delta_price = (
                total_notional - Decimal(updated["fill_notional"])
            ) / difference
            if not delta_price.is_finite() or delta_price <= 0:
                raise ReconciliationRefused("INVALID_CUMULATIVE_FILL_NOTIONAL")
            step("FILL", quantity=str(difference), price=str(delta_price))
            updated = self._core.order_state(order_id)
        if external.state == BrokerState.CANCELED:
            if updated["status"] in {"ACKNOWLEDGED", "PARTIALLY_FILLED"}:
                step("CANCEL")
            elif updated["status"] != "CANCELED":
                raise ReconciliationRefused("BROKER_CANCEL_STATE_CONFLICT")
        elif external.state == BrokerState.CLOSED:
            if external.closed_quantity > closed and (
                updated["status"] == "PARTIALLY_FILLED"
            ):
                step("CANCEL")
            if external.closed_quantity > closed:
                if closed != 0:
                    raise ReconciliationRefused("PRIOR_PARTIAL_EXIT_PRICE_UNPROVEN")
                step(
                    "CLOSE_FILL",
                    quantity=str(external.closed_quantity - closed),
                    price=str(external.average_close_price),
                )
        elif external.closed_quantity > closed:
            # Full-size order may have a broker-observed partial close.
            if closed != 0 or updated["status"] not in {"FILLED", "CANCELED"}:
                raise ReconciliationRefused("PARTIAL_EXIT_REPLAY_UNPROVEN")
            step(
                "CLOSE_FILL",
                quantity=str(external.closed_quantity),
                price=str(external.average_close_price),
            )

        updated = self._core.order_state(order_id)
        if (
            updated["status"] != broker_status
            or Decimal(updated["filled_quantity"]) != external.filled_quantity
            or Decimal(updated["closed_quantity"]) != external.closed_quantity
            or updated["remote_order_id"] != external.remote_order_id
        ):
            raise ReconciliationRefused("BROKER_LOCAL_STATE_DISAGREEMENT")
        return steps
