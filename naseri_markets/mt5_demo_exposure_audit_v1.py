"""Read-only Stage-5 diagnostic comparison with the Stage-3 PAPER ledger.

No MT5 observation is allowed to become Stage-4 OFFLINE_PAPER_BROKER_FIXTURE
evidence, mutate Stage-3/Stage-4 SQLite, release risk or unlock an account.
Historical order/deal truth and contract sizing are NOT assumed.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .execution_contract_v1 import identity, positive
from .mt5_demo_readonly_adapter_v1 import MT5DemoActiveSnapshot


class MT5ComparisonRefused(ValueError):
    """Local PAPER ledger or account identity cannot be verified."""


@dataclass(frozen=True, slots=True)
class DemoTicketBinding:
    """Manually verified *diagnostic* tickets, never an order permission.

    Stage-3 quantity is linear model units. MT5 positions are in lots:
    conversion is explicitly provided if a quantity comparison is desired.
    """

    order_id: str
    position_ticket: int | None = None
    pending_order_ticket: int | None = None
    mt5_lots_per_paper_unit: Decimal | None = None

    def __post_init__(self) -> None:
        identity(self.order_id, "order_id")
        for name in ("position_ticket", "pending_order_ticket"):
            val = getattr(self, name)
            if val is not None and (type(val) is not int or val <= 0):
                raise ValueError("INVALID_MANUAL_MT5_TICKET")
        if self.mt5_lots_per_paper_unit is not None:
            positive(self.mt5_lots_per_paper_unit, "mt5_lots_per_paper_unit")
            if self.position_ticket is None:
                raise ValueError("LOT_CONVERSION_REQUIRES_POSITION_TICKET")


def compare_demo_to_paper(
    snapshot: MT5DemoActiveSnapshot, *, ledger: str | Path,
    account_id: str, bindings: tuple[DemoTicketBinding, ...] = (),
) -> dict[str, Any]:
    """Pure read-only diagnosis. There is intentionally NO apply() pathway."""
    identity(account_id, "account_id")
    if not isinstance(snapshot, MT5DemoActiveSnapshot):
        raise MT5ComparisonRefused("DEMO_SNAPSHOT_REQUIRED")
    if snapshot.source != "MT5_DEMO_ACTIVE_ONLY_READONLY_V1":
        raise MT5ComparisonRefused("INVALID_SNAPSHOT_PROVENANCE")
    if snapshot.account_id != account_id:
        raise MT5ComparisonRefused("LOCAL_ACCOUNT_IDENTITY_MISMATCH")
    if not isinstance(bindings, tuple) or any(
        not isinstance(b, DemoTicketBinding) for b in bindings
    ):
        raise MT5ComparisonRefused("VERIFIED_BINDING_TUPLE_REQUIRED")
    if len({b.order_id for b in bindings}) != len(bindings):
        raise MT5ComparisonRefused("DUPLICATE_BINDING_ORDER_ID")
    for field in ("position_ticket", "pending_order_ticket"):
        values = [getattr(b, field) for b in bindings if getattr(b, field) is not None]
        if len(values) != len(set(values)):
            raise MT5ComparisonRefused("DUPLICATE_BINDING_TICKET")
    path = Path(ledger)
    if path.is_symlink() or not path.is_file():
        raise MT5ComparisonRefused("PAPER_LEDGER_NOT_REGULAR_FILE")
    # SQLite is opened with *mode=ro*; no schema writes and no mutating PRAGMA.
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=2) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute("SELECT snapshot FROM paper_orders").fetchall()
    except sqlite3.Error as exc:
        raise MT5ComparisonRefused("UNREADABLE_PAPER_LEDGER") from exc
    try:
        local = {
            entry["order_id"]: entry
            for row in rows
            if (entry := json.loads(row["snapshot"]))["spec"]["account_id"] == account_id
        }
    except (ValueError, TypeError, KeyError) as exc:
        raise MT5ComparisonRefused("CORRUPTED_LOCAL_ORDER_SNAPSHOT") from exc

    by_pos = {item.ticket: item for item in snapshot.positions}
    by_pending = {item.ticket: item for item in snapshot.pending_orders}
    associated_pos: set[int] = set()
    associated_pending: set[int] = set()
    issues: list[dict[str, Any]] = []

    def issue(code: str, *, order_id: str | None = None, ticket: int | None = None) -> None:
        issues.append({"code": code, "order_id": order_id, "ticket": ticket})

    for binding in bindings:
        if binding.order_id not in local:
            issue("BINDING_ORDER_NOT_IN_LOCAL_ACCOUNT", order_id=binding.order_id)
            continue
        state = local[binding.order_id]
        spec = state["spec"]
        open_qty = Decimal(state["open_position_quantity"])
        if binding.position_ticket is not None:
            associated_pos.add(binding.position_ticket)
            observed = by_pos.get(binding.position_ticket)
            if observed is None:
                issue("BOUND_POSITION_NOT_ACTIVE", order_id=binding.order_id,
                      ticket=binding.position_ticket)
            elif (
                observed.symbol != spec["instrument"]["symbol"]
                or observed.type_code != (0 if spec["direction"] == "long" else 1)
            ):
                issue("BOUND_POSITION_INSTRUMENT_OR_DIRECTION_MISMATCH",
                      order_id=binding.order_id, ticket=binding.position_ticket)
            elif open_qty <= 0:
                issue("DEMO_POSITION_WITHOUT_LOCAL_OPEN_EXPOSURE",
                      order_id=binding.order_id, ticket=binding.position_ticket)
            elif binding.mt5_lots_per_paper_unit is None:
                issue("VOLUME_UNIT_CONVERSION_UNVERIFIED",
                      order_id=binding.order_id, ticket=binding.position_ticket)
            elif open_qty * binding.mt5_lots_per_paper_unit != observed.volume:
                issue("BOUND_POSITION_LOT_VOLUME_MISMATCH",
                      order_id=binding.order_id, ticket=binding.position_ticket)
        if binding.pending_order_ticket is not None:
            associated_pending.add(binding.pending_order_ticket)
            observed_order = by_pending.get(binding.pending_order_ticket)
            if observed_order is None:
                issue("BOUND_PENDING_ORDER_NOT_ACTIVE", order_id=binding.order_id,
                      ticket=binding.pending_order_ticket)
            elif observed_order.symbol != spec["instrument"]["symbol"]:
                issue("BOUND_PENDING_SYMBOL_MISMATCH",
                      order_id=binding.order_id, ticket=binding.pending_order_ticket)
    binding_ids = {binding.order_id for binding in bindings}
    for order_id, state in local.items():
        if Decimal(state["open_position_quantity"]) > 0 and order_id not in binding_ids:
            issue("LOCAL_POSITION_REQUIRES_MANUAL_TICKET_BINDING", order_id=order_id)
        if state["status"] in {
            "SENT_UNCONFIRMED", "SUBMISSION_UNKNOWN", "ACKNOWLEDGED",
            "PARTIALLY_FILLED", "FILLED", "CANCELED",
        }:
            # Active-only MT5 calls cannot prove historical terminal order states.
            if state["status"] in {"SENT_UNCONFIRMED", "SUBMISSION_UNKNOWN"}:
                issue("HISTORICAL_ORDER_EVIDENCE_REQUIRED", order_id=order_id)
    for ticket in by_pos.keys() - associated_pos:
        issue("UNASSOCIATED_DEMO_OPEN_POSITION", ticket=ticket)
    for ticket in by_pending.keys() - associated_pending:
        issue("UNASSOCIATED_DEMO_PENDING_ORDER", ticket=ticket)
    return {
        "mode": "MT5_DEMO_DIAGNOSTICS_ONLY",
        "account_id": account_id, "login": snapshot.login,
        "server": snapshot.server, "currency": snapshot.currency,
        "local_paper_order_count": len(local),
        "demo_position_count": len(snapshot.positions),
        "demo_pending_order_count": len(snapshot.pending_orders),
        "discrepancies": sorted(
            issues, key=lambda value: (
                value["code"], value["order_id"] or "", value["ticket"] or 0
            )
        ),
        "needs_review": bool(issues),
        "history_complete": False, "may_release_paper_risk": False,
        "may_unlock_paper_recovery": False, "may_execute_trades": False,
    }
