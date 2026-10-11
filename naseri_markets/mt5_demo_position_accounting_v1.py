"""Stage 7: history-only MT5 DEMO hedging/netting diagnostic accounting.

DEAL_ENTRY_IN/OUT/INOUT/OUT_BY are distinct broker semantics. The reducer
does not invent opening history or promote a reconstructed position to a
broker-confirmed current exposure. Unsupported, absent or conflicting
evidence is flagged, never sent to a trade/risk gate.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .mt5_demo_history_readonly_v1 import MT5HistoricalDeal

ZERO = Decimal("0")
MODE_HEDGING = "HEDGING"
MODE_NETTING = "NETTING"


class AccountingRefused(ValueError):
    """Invalid historical accounting input or unsupported account mode."""


def diagnose_position_history(
    deals: tuple[MT5HistoricalDeal, ...], *, margin_mode: str,
) -> dict[str, Any]:
    """Reconstruct a *window-only* ledger by position (hedging) or symbol (netting).

    Non-trade transactions are retained as a separate monetary aggregate.
    Missing prior deals cannot be ruled out; every result is diagnostic only.
    """
    if margin_mode not in {MODE_HEDGING, MODE_NETTING}:
        raise AccountingRefused("ACCOUNT_MARGIN_MODE_NOT_SUPPORTED")
    if not isinstance(deals, tuple) or any(
        not isinstance(d, MT5HistoricalDeal) for d in deals
    ):
        raise AccountingRefused("HISTORY_DEAL_TUPLE_REQUIRED")
    if len({d.ticket for d in deals}) != len(deals):
        raise AccountingRefused("DUPLICATE_TRADE_DEAL_TICKET")
    positions: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    nontrade_cash = ZERO
    trade_cash = ZERO

    def flag(code: str, deal: MT5HistoricalDeal) -> None:
        issues.append({"code": code, "deal_ticket": str(deal.ticket)})

    for deal in sorted(deals, key=lambda d: (d.time_msc, d.ticket)):
        cash = deal.profit + deal.commission + deal.swap + deal.fee
        if deal.type_code not in (0, 1):
            nontrade_cash += cash
            continue
        trade_cash += cash
        key = str(deal.position_id) if margin_mode == MODE_HEDGING else deal.symbol
        current = positions.setdefault(key, {
            "symbol": deal.symbol, "position_ids": set(),
            "signed_lots": ZERO, "entry_lots": ZERO, "exit_lots": ZERO,
            "entry_notional": ZERO, "exit_notional": ZERO,
            "net_cash": ZERO, "reversal_count": 0,
        })
        current["net_cash"] += cash
        if (
            margin_mode == MODE_NETTING and current["signed_lots"] != ZERO
            and current["position_ids"]
            and deal.position_id not in current["position_ids"]
        ):
            flag("NETTING_POSITION_ID_CHANGED_WITH_OPEN_EXPOSURE", deal)
        current["position_ids"].add(deal.position_id)
        if current["symbol"] != deal.symbol:
            flag("POSITION_ID_SYMBOL_CONFLICT", deal)
        sign = Decimal(1) if deal.type_code == 0 else Decimal(-1)
        prior = current["signed_lots"]
        qty = deal.volume
        if not qty.is_finite() or qty <= ZERO:
            raise AccountingRefused("TRADE_VOLUME_NOT_POSITIVE")
        if deal.entry_code == 0:  # entry/add; same direction as exposure
            if prior != ZERO and (prior > ZERO) != (sign > ZERO):
                flag("IN_ENTRY_OPPOSITE_EXISTING_EXPOSURE", deal)
                continue
            current["signed_lots"] = prior + sign * qty
            current["entry_lots"] += qty
            current["entry_notional"] += qty * deal.price
        elif deal.entry_code == 1:  # close/reduce, opposite side of prior
            if prior == ZERO:
                flag("OUT_WITHOUT_PRIOR_IN_WINDOW_ENTRY", deal)
                continue
            if (prior > ZERO) == (sign > ZERO):
                flag("OUT_DIRECTION_MISMATCH", deal)
                continue
            if qty > abs(prior):
                flag("OUT_EXCEEDS_RECORDED_POSITION", deal)
                continue
            current["signed_lots"] = prior + sign * qty
            current["exit_lots"] += qty
            current["exit_notional"] += qty * deal.price
        elif deal.entry_code == 2:  # netting reversal (INOUT)
            if margin_mode == MODE_HEDGING:
                flag("HEDGING_INOUT_UNSUPPORTED", deal)
                continue
            if prior == ZERO:
                flag("INOUT_MISSING_OPEN_POSITION", deal)
                continue
            if (prior > ZERO) == (sign > ZERO) or qty <= abs(prior):
                flag("INOUT_NOT_A_REVERSAL", deal)
                continue
            current["exit_lots"] += abs(prior)
            current["exit_notional"] += abs(prior) * deal.price
            incoming = qty - abs(prior)
            current["entry_lots"] += incoming
            current["entry_notional"] += incoming * deal.price
            current["signed_lots"] = sign * incoming
            current["reversal_count"] += 1
        elif deal.entry_code == 3:  # OUT_BY: counterpart position needed
            flag("CLOSE_BY_COUNTERPART_EVIDENCE_REQUIRED", deal)
        else:
            flag("UNKNOWN_DEAL_ENTRY_CODE", deal)
    rows = []
    for key, entry in sorted(positions.items()):
        rows.append({
            "key": key, "symbol": entry["symbol"],
            "position_ids": sorted(entry["position_ids"]),
            "signed_lots_window_only": str(entry["signed_lots"]),
            "entry_lots_window_only": str(entry["entry_lots"]),
            "exit_lots_window_only": str(entry["exit_lots"]),
            "entry_vwap_window_only": (
                str(entry["entry_notional"] / entry["entry_lots"])
                if entry["entry_lots"] else None
            ),
            "exit_vwap_window_only": (
                str(entry["exit_notional"] / entry["exit_lots"])
                if entry["exit_lots"] else None
            ),
            "reported_trade_cash_window_only": str(entry["net_cash"]),
            "reversal_count": entry["reversal_count"],
        })
    return {
        "mode": "MT5_DEMO_HISTORY_DIAGNOSTICS_ONLY",
        "margin_mode": margin_mode,
        "positions": rows,
        "issues": issues,
        "trade_cash_window_only": str(trade_cash),
        "nontrade_cash_window_only": str(nontrade_cash),
        "all_time_position_reconstruction_proven": False,
        "may_mutate_paper_risk": False,
        "may_unlock_recovery": False,
        "may_send_order": False,
    }
