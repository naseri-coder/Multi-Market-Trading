"""Stage21E read-only OPTIONAL retrospective funding/PAPER scenario reconciliation.

Uses already-captured public funding SETTLEMENT rates, but not settlement-time
mark prices (unavailable from this source). An *entry-notional* funding proxy
is explicitly unverified and is NEVER inserted into the Stage3/9 risk ledger.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from .paper_contract_audit_stage21d_v1 import audit_paper_contract_economics
from .paper_contract_economics_stage21d_v1 import PaperContractEconomics


class FundingPaperRefused(ValueError):
    """No extrapolated fills or funding charged to missing/untrusted trades."""


def estimate_ledger_funding(
    paper_path: Path, *,
    policies: tuple[PaperContractEconomics, ...],
    settlements: tuple[tuple, ...],
) -> dict:
    """No writes, account credentials or real PnL claim.

    Each supported order must have one fill and exactly one terminal exit;
    partial exits require position-at-settlement reconstruction and are
    deliberately UNKNOWN. For every settlement strictly after the entry-bar
    close and no later than the exit bar close, sign=LONG pays positive rate.
    Fees are a *hypothetical entry-notional* proxy, not actual settlement PnL.
    """
    if (not isinstance(paper_path, Path) or paper_path.is_symlink()
            or not paper_path.is_file() or type(policies) is not tuple
            or len(policies) != 2 or len({p.symbol for p in policies}) != 2
            or type(settlements) is not tuple or len(settlements) != 2):
        raise FundingPaperRefused("EXACT_READONLY_PAPER_EVIDENCE_REQUIRED")
    uri = "file:" + quote(str(paper_path.absolute()), safe="/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, isolation_level=None) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            try:
                orders = db.execute(
                    "SELECT order_id FROM paper_core_orders ORDER BY order_id").fetchall()
                attestation = audit_paper_contract_economics(
                    paper_path, expected=policies, expected_orders=len(orders))
                if attestation.state != "LOCAL_PER_CONTRACT_ECONOMICS_COHERENT_UNATTESTED":
                    raise FundingPaperRefused("UNATTESTED_PAPER_ECONOMICS")
                by_symbol = {p.symbol: (p, settlements[i])
                             for i, p in enumerate(policies)}
                result = []
                for order in orders:
                    order_id = order["order_id"]
                    reservation = db.execute(
                        "SELECT contract_json FROM paper_risk_reservations "
                        "WHERE order_id=?", (order_id,)).fetchone()
                    snap_row = db.execute(
                        "SELECT snapshot FROM paper_orders WHERE order_id=?",
                        (order_id,)).fetchone()
                    plan = db.execute(
                        "SELECT entry_bar_close FROM paper_stage9_plans "
                        "WHERE order_id=?", (order_id,)).fetchone()
                    if reservation is None or snap_row is None or plan is None:
                        raise FundingPaperRefused("INCOMPLETE_PAPER_POSITION_EVIDENCE")
                    spec = json.loads(reservation["contract_json"])
                    snap = json.loads(snap_row["snapshot"])
                    symbol = spec["instrument"]["symbol"]
                    if symbol not in by_symbol:
                        raise FundingPaperRefused("UNTRUSTED_PAPER_SYMBOL")
                    policy, entries = by_symbol[symbol]
                    exits = db.execute(
                        "SELECT ex.net,b.bar_close,ex.quantity FROM paper_stage9_exits ex "
                        "JOIN paper_stage9_bars b ON b.order_id=ex.order_id "
                        "AND b.bar_digest=ex.evidence_digest "
                        "WHERE ex.order_id=? ORDER BY b.bar_close", (order_id,)
                    ).fetchall()
                    amount = Decimal(snap["filled_quantity"])
                    if (plan["entry_bar_close"] is None or snap["status"] != "CLOSED"
                            or len(exits) != 1 or Decimal(exits[0]["quantity"]) != amount
                            or amount <= 0):
                        result.append({
                            "order_id": order_id, "symbol": symbol,
                            "funding_scenario": "UNKNOWN_OPEN_OR_PARTIAL_POSITION",
                            "entry_notional_proxy": None, "estimated_funding_cashflow": None,
                        })
                        continue
                    from datetime import datetime
                    start = datetime.fromisoformat(plan["entry_bar_close"])
                    end = datetime.fromisoformat(exits[0]["bar_close"])
                    if end <= start:
                        raise FundingPaperRefused("INVALID_EXIT_CHRONOLOGY")
                    entry_price = Decimal(snap["average_fill_price"])
                    notional = policy.notional(amount, entry_price)
                    side = 1 if spec["direction"] == "long" else -1
                    accrued = sum(
                        (-Decimal(side) * event.rate * notional
                         for event in entries if start < event.settled_at <= end),
                        Decimal(0))
                    result.append({
                        "order_id": order_id, "symbol": symbol,
                        "entry_bar_close": start.isoformat(),
                        "exit_bar_close": end.isoformat(),
                        "funding_scenario": "ENTRY_NOTIONAL_PROXY_UNATTESTED",
                        "entry_notional_proxy": str(notional),
                        "estimated_funding_cashflow": str(accrued),
                        "estimated_net_including_proxy": str(
                            Decimal(exits[0]["net"]) + accrued),
                    })
                return {
                    "mode": "RETROSPECTIVE_FUNDING_SENSITIVITY_ONLY",
                    "audit_state": attestation.state,
                    "orders": result,
                    "funding_events_complete": False,
                    "funding_settlement_mark_prices_verified": False,
                    "stage3_stage9_accounting_unchanged": True,
                    "realized_exchange_pnl_proven": False,
                }
            finally:
                db.execute("ROLLBACK")
    except FundingPaperRefused:
        raise
    except (sqlite3.DatabaseError, ValueError, KeyError, TypeError,
            ArithmeticError) as exc:
        raise FundingPaperRefused("UNREADABLE_PAPER_FUNDING_EVIDENCE") from exc


__all__ = ["FundingPaperRefused", "estimate_ledger_funding"]
