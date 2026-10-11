"""Stage-6 immutable DEMO history diagnostics and optional READ-ONLY PAPER audit.

History completeness is strictly scoped to the queried UTC time window.
Even a clean report cannot release reserves or authorize Stage-4 recovery.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .execution_contract_v1 import identity, positive
from .mt5_demo_history_readonly_v1 import MT5DemoHistorySnapshot


class MT5HistoryAuditRefused(ValueError):
    """Invalid comparison request, ledger or historical snapshot."""


@dataclass(frozen=True, slots=True)
class HistoricalTicketBinding:
    """Explicit operator-proven identity and lot conversion, diagnostic only."""

    paper_order_id: str
    mt5_entry_order_ticket: int
    mt5_position_id: int
    mt5_lots_per_paper_unit: Decimal

    def __post_init__(self) -> None:
        identity(self.paper_order_id, "paper_order_id")
        for name in ("mt5_entry_order_ticket", "mt5_position_id"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError("INVALID_VERIFIED_MT5_TICKET")
        positive(self.mt5_lots_per_paper_unit, "mt5_lots_per_paper_unit")


def _local_orders(path: str | Path, account_id: str) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise MT5HistoryAuditRefused("PAPER_LEDGER_NOT_REGULAR_FILE")
    uri = "file:" + quote(p.resolve().as_posix(), safe="/:") + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            rows = db.execute("SELECT snapshot FROM paper_orders").fetchall()
        local = {}
        for row in rows:
            state = json.loads(row["snapshot"])
            if state["spec"]["account_id"] == account_id:
                local[state["order_id"]] = state
        return local
    except (sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        raise MT5HistoryAuditRefused("UNREADABLE_OR_CORRUPT_PAPER_LEDGER") from exc


def audit_demo_history(
    snapshot: MT5DemoHistorySnapshot,
    *, paper_ledger: str | Path | None = None,
    account_id: str | None = None,
    bindings: tuple[HistoricalTicketBinding, ...] = (),
) -> dict[str, Any]:
    if not isinstance(snapshot, MT5DemoHistorySnapshot):
        raise MT5HistoryAuditRefused("DEMO_HISTORY_SNAPSHOT_REQUIRED")
    if snapshot.source != "MT5_DEMO_BOUNDED_HISTORY_READONLY_V1":
        raise MT5HistoryAuditRefused("UNKNOWN_HISTORY_PROVENANCE")
    if not isinstance(bindings, tuple) or any(
        not isinstance(binding, HistoricalTicketBinding) for binding in bindings
    ):
        raise MT5HistoryAuditRefused("VERIFIED_HISTORY_BINDINGS_REQUIRED")
    if len({b.paper_order_id for b in bindings}) != len(bindings) or len({
        b.mt5_entry_order_ticket for b in bindings
    }) != len(bindings) or len({b.mt5_position_id for b in bindings}) != len(bindings):
        raise MT5HistoryAuditRefused("DUPLICATE_HISTORY_BINDING")
    if bindings and paper_ledger is None:
        raise MT5HistoryAuditRefused("BINDINGS_REQUIRE_PAPER_LEDGER")
    if paper_ledger is not None:
        if account_id != snapshot.account_id:
            raise MT5HistoryAuditRefused("PAPER_ACCOUNT_IDENTITY_MISMATCH")
        local = _local_orders(paper_ledger, snapshot.account_id)
    else:
        local = {}
        if account_id is not None and account_id != snapshot.account_id:
            raise MT5HistoryAuditRefused("ACCOUNT_IDENTITY_MISMATCH")

    orders = {o.ticket: o for o in snapshot.orders}
    deals = {d.ticket: d for d in snapshot.deals}
    issues: list[dict[str, Any]] = []
    positions: dict[int, dict[str, Any]] = {}

    def issue(code: str, reference: str | int | None = None) -> None:
        issues.append({"code": code, "reference": str(reference) if reference is not None else None})

    for deal in deals.values():
        if deal.type_code not in (0, 1):
            # Balance/credit/correction transactions are NOT position fills.
            continue
        if deal.order_ticket not in orders:
            issue("DEAL_ORDER_OUTSIDE_CAPTURED_WINDOW", deal.ticket)
        if deal.entry_code in (2, 3):
            issue("REVERSAL_OR_CLOSE_BY_REQUIRES_INDEPENDENT_REVIEW", deal.ticket)
        if deal.entry_code == 0 and deal.type_code not in (0, 1):
            issue("UNRECOGNIZED_ENTRY_DEAL", deal.ticket)
        bucket = positions.setdefault(deal.position_id, {
            "symbol": deal.symbol,
            "entry_lots": Decimal("0"), "exit_lots": Decimal("0"),
            "entry_notional": Decimal("0"), "exit_notional": Decimal("0"),
            "realized_proceeds_less_costs": Decimal("0"),
            "entry_orders": set(), "exit_orders": set(),
            "unknown_entry_codes": False,
        })
        if bucket["symbol"] != deal.symbol:
            issue("POSITION_SYMBOL_CHANGED_WITHIN_WINDOW", deal.position_id)
        bucket["realized_proceeds_less_costs"] += (
            deal.profit + deal.commission + deal.swap + deal.fee
        )
        if deal.entry_code == 0:
            bucket["entry_lots"] += deal.volume
            bucket["entry_notional"] += deal.volume * deal.price
            bucket["entry_orders"].add(deal.order_ticket)
        elif deal.entry_code == 1:
            bucket["exit_lots"] += deal.volume
            bucket["exit_notional"] += deal.volume * deal.price
            bucket["exit_orders"].add(deal.order_ticket)
        else:
            bucket["unknown_entry_codes"] = True
    for pos_id, bucket in positions.items():
        if bucket["exit_lots"] > bucket["entry_lots"]:
            issue("ENTRY_DEALS_OUTSIDE_WINDOW_OR_REVERSED_POSITION", pos_id)
        if bucket["entry_lots"] == 0 and bucket["exit_lots"] > 0:
            issue("POSITION_ENTRY_OUTSIDE_CAPTURED_WINDOW", pos_id)
    bound_ids: set[str] = set()
    for binding in bindings:
        bound_ids.add(binding.paper_order_id)
        local_state = local.get(binding.paper_order_id)
        if local_state is None:
            issue("BOUND_PAPER_ORDER_NOT_FOUND", binding.paper_order_id)
            continue
        entry_order = orders.get(binding.mt5_entry_order_ticket)
        bucket = positions.get(binding.mt5_position_id)
        if entry_order is None:
            issue("BOUND_ENTRY_ORDER_OUTSIDE_WINDOW", binding.paper_order_id)
        else:
            symbol = local_state["spec"]["instrument"]["symbol"]
            if entry_order.symbol != symbol:
                issue("BOUND_SYMBOL_MISMATCH", binding.paper_order_id)
            if entry_order.position_id not in (0, binding.mt5_position_id):
                issue("BOUND_POSITION_ID_MISMATCH", binding.paper_order_id)
        if bucket is None or binding.mt5_entry_order_ticket not in bucket["entry_orders"]:
            issue("BOUND_ENTRY_DEALS_NOT_PROVEN", binding.paper_order_id)
            continue
        if bucket["unknown_entry_codes"]:
            issue("BOUND_REVERSAL_UNSUPPORTED", binding.paper_order_id)
        units = binding.mt5_lots_per_paper_unit
        if bucket["entry_lots"] != (
            Decimal(local_state["filled_quantity"]) * units
        ):
            issue("BOUND_CUMULATIVE_ENTRY_LOTS_MISMATCH", binding.paper_order_id)
        if bucket["exit_lots"] != (
            Decimal(local_state["closed_quantity"]) * units
        ):
            issue("BOUND_CUMULATIVE_EXIT_LOTS_MISMATCH", binding.paper_order_id)
        # Stage-3 PAPER and MT5 numbers are different unit models.
        # Exit "net profit" is reported, not posted to the PAPER ledger.
        if bucket["symbol"] != local_state["spec"]["instrument"]["symbol"]:
            issue("BOUND_DEAL_SYMBOL_MISMATCH", binding.paper_order_id)
    for order_id, state in local.items():
        if order_id not in bound_ids and (
            Decimal(state["filled_quantity"]) > 0
            or state["status"] in {"SUBMISSION_UNKNOWN", "SENT_UNCONFIRMED"}
        ):
            issue("PAPER_ORDER_REQUIRES_OPERATOR_HISTORY_BINDING", order_id)
    return {
        "mode": "MT5_DEMO_HISTORY_DIAGNOSTIC_ONLY",
        "account_id": snapshot.account_id,
        "login": snapshot.login, "server": snapshot.server,
        "start_utc": snapshot.start_utc.isoformat(),
        "end_utc": snapshot.end_utc.isoformat(),
        "window_digest": snapshot.digest,
        "window_complete": True, "all_time_history_complete": False,
        "historical_orders": len(orders), "deals": len(deals),
        "position_summaries": [
            {
                "position_id": pid, "symbol": bucket["symbol"],
                "window_entry_lots": str(bucket["entry_lots"]),
                "window_exit_lots": str(bucket["exit_lots"]),
                "entry_vwap": (
                    str(bucket["entry_notional"] / bucket["entry_lots"])
                    if bucket["entry_lots"] else None
                ),
                "exit_vwap": (
                    str(bucket["exit_notional"] / bucket["exit_lots"])
                    if bucket["exit_lots"] else None
                ),
                "reported_net_cashflows": str(bucket["realized_proceeds_less_costs"]),
            }
            for pid, bucket in sorted(positions.items())
        ],
        "issues": sorted(issues, key=lambda item: (item["code"], item["reference"] or "")),
        "needs_review": bool(issues),
        "may_release_paper_risk": False,
        "may_unlock_stage4_fence": False,
        "may_execute_trades": False,
        "may_publish_signal": False,
    }
