"""Stage21D read-only integrity check on immutable per-order PAPER economics.

Checks against the SAME Stage3/8/9 SQLite ledger after all writers close.
A local digest is not a signed source attestation or a guarantee of real fills.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from .paper_contract_economics_stage21d_v1 import (
    PaperContractEconomics, ContractEconomicsRefused,
)


class ContractAuditRefused(ValueError):
    """Local accounting evidence is inconsistent; refuse publication or release."""


@dataclass(frozen=True, slots=True)
class ContractAudit:
    orders: int
    modeled_exits: int
    total_gross: str
    total_cost: str
    total_net: str
    state: str = "LOCAL_PER_CONTRACT_ECONOMICS_COHERENT_UNATTESTED"
    real_venue_verified: bool = False


def audit_paper_contract_economics(
        path: Path, *, expected: tuple[PaperContractEconomics, ...],
        expected_orders: int) -> ContractAudit:
    if (not isinstance(path, Path) or path.is_symlink() or not path.is_file()
            or type(expected) is not tuple or len(expected) != 2
            or any(type(e) is not PaperContractEconomics for e in expected)
            or len({e.symbol for e in expected}) != 2
            or type(expected_orders) is not int or expected_orders < 0):
        raise ContractAuditRefused("EXACT_PRIVATE_LEDGER_EXPECTED")
    try:
        uri = "file:" + quote(str(path.absolute()), safe="/") + "?mode=ro"
        with sqlite3.connect(uri, uri=True, isolation_level=None) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            try:
                rows = db.execute(
                    "SELECT r.order_id,r.risk,r.notional,r.contract_json,"
                    "s.policy,s.digest FROM paper_order_economics s "
                    "JOIN paper_risk_reservations r ON s.order_id=r.order_id "
                    "ORDER BY r.order_id").fetchall()
                count = db.execute("SELECT COUNT(*) FROM paper_core_orders").fetchone()[0]
                if len(rows) != expected_orders or count != expected_orders:
                    raise ContractAuditRefused("ECONOMIC_ORDER_COUNT_DRIFT")
                by_symbol = {e.symbol: e for e in expected}
                exits = 0
                total_gross, total_cost = Decimal(0), Decimal(0)
                for row in rows:
                    policy = PaperContractEconomics.from_wire(json.loads(row["policy"]))
                    spec = json.loads(row["contract_json"])
                    if (row["digest"] != policy.digest
                            or policy != by_symbol.get(policy.symbol)
                            or spec["instrument"]["symbol"] != policy.symbol
                            or spec["instrument"]["provider"] != policy.provider
                            or spec["instrument"]["quote_currency"] != "USDT"):
                        raise ContractAuditRefused("ORDER_INSTRUMENT_ECONOMICS_DRIFT")
                    qty = Decimal(spec["quantity"])
                    entry = Decimal(spec["reference_entry"])
                    stop = Decimal(spec["stop"])
                    if (Decimal(row["notional"]) != policy.notional(qty, entry)
                            or Decimal(row["risk"]) != policy.reserved_risk(
                                qty, entry, stop)):
                        raise ContractAuditRefused("RISK_RESERVATION_ECONOMICS_DRIFT")
                    state = db.execute(
                        "SELECT snapshot FROM paper_orders WHERE order_id=?",
                        (row["order_id"],)).fetchone()
                    if state is None:
                        raise ContractAuditRefused("ORDER_STATE_MISSING")
                    snap = json.loads(state["snapshot"])
                    avg = Decimal(snap["average_fill_price"])
                    for ex in db.execute(
                            "SELECT * FROM paper_stage9_exits WHERE order_id=? "
                            "ORDER BY rowid", (row["order_id"],)):
                        gross, cost = policy.modeled_exit(
                            quantity=Decimal(ex["quantity"]), entry=avg,
                            exit_price=Decimal(ex["price"]),
                            direction=spec["direction"])
                        if (gross != Decimal(ex["gross"])
                                or cost != Decimal(ex["modeled_cost"])
                                or gross - cost != Decimal(ex["net"])):
                            raise ContractAuditRefused("REALIZED_EXIT_PNL_DRIFT")
                        total_gross += gross
                        total_cost += cost
                        exits += 1
                return ContractAudit(
                    len(rows), exits, str(total_gross), str(total_cost),
                    str(total_gross - total_cost))
            finally:
                db.execute("ROLLBACK")
    except ContractAuditRefused:
        raise
    except (sqlite3.DatabaseError, ValueError, TypeError, KeyError,
            ContractEconomicsRefused, ArithmeticError) as exc:
        raise ContractAuditRefused("UNREADABLE_OR_INVALID_ECONOMIC_EVIDENCE") from exc


__all__ = ["ContractAudit", "ContractAuditRefused",
           "audit_paper_contract_economics"]
