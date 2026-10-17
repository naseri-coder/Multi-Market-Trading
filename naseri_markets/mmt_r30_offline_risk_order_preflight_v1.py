"""R30 additive pre-order risk AUDIT over existing PAPER policies and receipts.

Pure calculation: it NEVER calls Stage3 reserve/create, any transport, broker,
market API, network or Telegram. Existing Stage3/8/9 remain sole risk/order
authorities. Input snapshots are operator-provided, NOT independent real venue
account evidence. A local PASS authorizes ZERO external side effects.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .contracts import Direction, EvidenceMode, Instrument
from .execution_contract_v1 import OrderSpec, OrderStatus, identity
from .risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy


class R30RiskRefused(ValueError):
    """Sanitized refusal: always halt new risk, never repair automatically."""


ACTIVE = frozenset({
    OrderStatus.CREATED, OrderStatus.ACKNOWLEDGED,
    OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
})
UNKNOWN = frozenset({
    OrderStatus.SENT_UNCONFIRMED, OrderStatus.SUBMISSION_UNKNOWN,
})
TERMINAL = frozenset({
    OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.CLOSED,
})
SNAPSHOT_KEYS = frozenset({
    "portfolio_id", "mode", "halted", "day", "active_orders",
    "reserved_risk", "reserved_notional", "modeled_margin",
    "daily_realized_loss_magnitude", "account_losses",
})
HEALTH_KEYS = frozenset({
    "mode", "counts", "manual_reconciliation_required",
    "background_poller", "telegram_sent", "broker_order_sent",
    "live_trading_enabled",
})


def _canon(v: object) -> bytes:
    return json.dumps(
        v, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _num(v: object, label: str) -> Decimal:
    if type(v) is not str or not 1 <= len(v) <= 64:
        raise R30RiskRefused("R30_" + label + "_DECIMAL_STRING_REQUIRED")
    try:
        n = Decimal(v)
    except InvalidOperation as exc:
        raise R30RiskRefused("R30_INVALID_" + label) from exc
    if not n.is_finite() or n < 0:
        raise R30RiskRefused("R30_NEGATIVE_OR_NONFINITE_" + label)
    return n


def _fail(condition: bool, code: str) -> None:
    if condition:
        raise R30RiskRefused(code)


def _wire_decimal(v: Decimal) -> str:
    return format(v.normalize(), "f")


@dataclass(frozen=True, slots=True)
class R30ActiveReservation:
    """Existing ACTIVE Stage3 reservation, *not* a second ledger or authority."""
    order_id: str
    account_id: str
    engine_id: str
    group_id: str
    instrument: Instrument
    direction: Direction
    order_status: OrderStatus
    risk: Decimal
    notional: Decimal
    margin: Decimal

    def __post_init__(self) -> None:
        for name in ("order_id", "account_id", "engine_id", "group_id"):
            identity(getattr(self, name), name)
        if (not isinstance(self.instrument, Instrument)
                or not isinstance(self.direction, Direction)
                or not isinstance(self.order_status, OrderStatus)):
            raise R30RiskRefused("R30_RESERVATION_CONTRACT_INVALID")
        for field in ("risk", "notional", "margin"):
            v = getattr(self, field)
            if type(v) is not Decimal or not v.is_finite() or v <= 0:
                raise R30RiskRefused("R30_ACTIVE_RESERVATION_AMOUNT_INVALID")


def evaluate_r30_offline_preorder_risk(
    *, proposal: OrderSpec,
    account_policy: AccountRiskPolicy,
    portfolio_policy: PortfolioRiskPolicy,
    group_id: str,
    active_reservations: tuple[R30ActiveReservation, ...],
    known_order_statuses: Mapping[str, OrderStatus],
    portfolio_snapshot: dict,
    account_recovery_fence: dict,
    runtime_health: dict,
    engine_halted: bool,
    account_halted: bool,
    order_switch_enabled: bool,
    operator_ack: bool = False,
) -> dict:
    """Independent arithmetic preflight, no durable reserve/order/send.

    The caller must obtain *complete consistent stopped-state* Stage3 portfolio
    reservations and Stage4/17 evidence; there is NO third-party provider proof.
    Even a clean result can race a subsequent writer, so any real order remains
    independently prohibited and requires atomic fresh Stage3/8/9 gates.
    """
    _fail(operator_ack is not True
          or os.environ.get("MMT_NONPRODUCTION") != "1"
          or "MMT_PRODUCTION" in os.environ,
          "R30_NONPRODUCTION_EXPLICIT_OPERATOR_ACK_REQUIRED")
    _fail(not isinstance(proposal, OrderSpec)
          or proposal.mode is not EvidenceMode.PAPER
          or not isinstance(account_policy, AccountRiskPolicy)
          or not isinstance(portfolio_policy, PortfolioRiskPolicy),
          "R30_EXISTING_PAPER_POLICY_CONTRACTS_REQUIRED")
    identity(group_id, "group_id")
    _fail(type(order_switch_enabled) is not bool or not order_switch_enabled
          or type(account_halted) is not bool or account_halted
          or type(engine_halted) is not bool or engine_halted,
          "R30_ONE_WAY_HALT_OR_SWITCH_DISABLED")
    _fail(proposal.account_id != account_policy.account_id
          or account_policy.portfolio_id != portfolio_policy.portfolio_id
          or account_policy.currency != portfolio_policy.currency
          or proposal.instrument.quote_currency != account_policy.currency
          or account_policy.external_exposure_cleared is not True,
          "R30_ACCOUNT_CURRENCY_OR_EXTERNAL_EXPOSURE_UNVERIFIED")

    _fail(type(portfolio_snapshot) is not dict
          or frozenset(portfolio_snapshot) != SNAPSHOT_KEYS
          or portfolio_snapshot.get("portfolio_id") != portfolio_policy.portfolio_id
          or portfolio_snapshot.get("mode") != "PAPER_ONLY"
          or portfolio_snapshot.get("halted") is not False,
          "R30_PORTFOLIO_SNAPSHOT_HALTED_OR_MALFORMED")
    observed_day = portfolio_snapshot["day"]
    try:
        _fail(type(observed_day) is not str
              or date.fromisoformat(observed_day).isoformat() != observed_day,
              "R30_DAY_NOT_CANONICAL")
    except ValueError as exc:
        raise R30RiskRefused("R30_DAY_NOT_CANONICAL") from exc

    _fail(type(account_recovery_fence) is not dict
          or account_recovery_fence.get("account_id") != proposal.account_id
          or account_recovery_fence.get("state") != "READY"
          or account_recovery_fence.get("ready_for_new_paper_risk") is not True
          or type(account_recovery_fence.get("last_revision")) is not int
          or account_recovery_fence["last_revision"] < 0,
          "R30_RESTART_ACCOUNT_RECOVERY_NOT_READY")
    _fail(type(runtime_health) is not dict
          or frozenset(runtime_health) != HEALTH_KEYS
          or runtime_health.get("mode") != "OFFLINE_OPERATOR_DRIVEN_SUPERVISOR"
          or runtime_health.get("manual_reconciliation_required") is not False
          or any(runtime_health.get(k) is not False for k in (
              "background_poller", "telegram_sent", "broker_order_sent",
              "live_trading_enabled",
          )), "R30_UNVERIFIED_RUNTIME_OR_SIDE_EFFECTS")
    counts = runtime_health["counts"]
    _fail(type(counts) is not dict
          or frozenset(counts) != {"PENDING", "CLAIMED", "DONE", "QUARANTINED"}
          or any(type(n) is not int or n < 0 for n in counts.values())
          or any(counts[k] != 0 for k in counts),
          "R30_PENDING_DONE_OR_UNKNOWN_RUNTIME_EFFECTS")

    _fail(type(active_reservations) is not tuple
          or not all(type(r) is R30ActiveReservation for r in active_reservations)
          or len(active_reservations) > 5000,
          "R30_COMPLETE_ACTIVE_RESERVATIONS_REQUIRED")
    _fail(not isinstance(known_order_statuses, Mapping)
          or len(known_order_statuses) > 5000
          or any(type(k) is not str or type(v) is not OrderStatus
                 for k, v in known_order_statuses.items()),
          "R30_CANONICAL_ORDER_STATE_SET_REQUIRED")
    _fail(any(state in UNKNOWN for state in known_order_statuses.values()),
          "R30_UNKNOWN_OR_UNCONFIRMED_ORDER_HARD_DENY")
    seen: set[str] = set()
    for item in active_reservations:
        _fail(item.order_id in seen
              or item.order_status not in ACTIVE
              or known_order_statuses.get(item.order_id) != item.order_status
              or item.instrument.quote_currency != portfolio_policy.currency,
              "R30_DUPLICATED_MISSING_OR_UNRECONCILED_RESERVATION")
        seen.add(item.order_id)
    _fail(proposal.order_id in known_order_statuses
          or proposal.order_id in seen,
          "R30_REUSED_ORDER_ID_DENIED")
    _fail(any(s in ACTIVE and k not in seen
              for k, s in known_order_statuses.items()),
          "R30_ACTIVE_ORDER_MISSING_FROM_RESERVATIONS")
    _fail(any(s in TERMINAL and k in seen
              for k, s in known_order_statuses.items()),
          "R30_TERMINAL_ORDER_HAS_ACTIVE_RISK")

    _fail(type(portfolio_snapshot["active_orders"]) is not int
          or portfolio_snapshot["active_orders"] != len(active_reservations),
          "R30_ACTIVE_ORDER_COUNT_MISMATCH")
    total_risk = sum((r.risk for r in active_reservations), Decimal(0))
    total_notional = sum((r.notional for r in active_reservations), Decimal(0))
    total_margin = sum((r.margin for r in active_reservations), Decimal(0))
    _fail(_num(portfolio_snapshot["reserved_risk"], "RISK") != total_risk
          or _num(portfolio_snapshot["reserved_notional"], "NOTIONAL") != total_notional
          or _num(portfolio_snapshot["modeled_margin"], "MARGIN") != total_margin,
          "R30_PORTFOLIO_RESERVATION_TOTAL_DRIFT")
    losses = portfolio_snapshot["account_losses"]
    _fail(type(losses) is not dict
          or len(losses) > 5000
          or any(type(k) is not str for k in losses),
          "R30_ACCOUNT_LOSS_SNAPSHOT_INVALID")
    loss_values = {k: _num(v, "LOSS") for k, v in losses.items()}
    loss = _num(portfolio_snapshot["daily_realized_loss_magnitude"], "DAILY_LOSS")
    _fail(sum(loss_values.values(), Decimal(0)) != loss,
          "R30_ACCOUNT_PORTFOLIO_DAILY_LOSS_DRIFT")
    account_loss = loss_values.get(proposal.account_id, Decimal(0))
    for res in active_reservations:
        _fail(res.account_id == proposal.account_id
              and res.instrument == proposal.instrument,
              "R30_SAME_INSTRUMENT_CONCURRENT_POSITION_DENIED")

    # Same deterministic fallback formula as existing Stage3 WITHOUT writing
    # a second risk reservation. This excludes venue-specific economics rules:
    # they must still be checked by Stage3 itself; a pass is *not permission*.
    quantity = proposal.quantity
    step = account_policy.quantity_step
    _fail(quantity % step != 0, "R30_QUANTITY_STEP_VIOLATION")
    notional = quantity * proposal.reference_entry * account_policy.contract_multiplier
    risk = quantity * account_policy.contract_multiplier * (
        abs(proposal.reference_entry - proposal.stop)
        + proposal.reference_entry * (
            account_policy.roundtrip_fee_fraction
            + account_policy.worst_slippage_fraction
        )
    )
    margin = notional / account_policy.max_leverage
    account_active = tuple(r for r in active_reservations
                           if r.account_id == proposal.account_id)
    acc_risk = sum((r.risk for r in account_active), Decimal(0))
    acc_notional = sum((r.notional for r in account_active), Decimal(0))
    acc_margin = sum((r.margin for r in account_active), Decimal(0))
    group_risk = sum((r.risk for r in active_reservations
                      if r.group_id == group_id), Decimal(0))
    engine_risk = sum((r.risk for r in active_reservations
                       if r.engine_id == proposal.engine_id), Decimal(0))
    equity = account_policy.equity
    _fail(account_loss >= equity * account_policy.max_daily_loss_fraction
          or loss >= portfolio_policy.max_daily_loss,
          "R30_DAILY_LOSS_CIRCUIT_BREAKER")
    bounds = (
        (risk, equity * account_policy.max_order_risk_fraction,
         "R30_PER_ORDER_RISK_LIMIT"),
        (acc_risk + risk, equity * account_policy.max_total_risk_fraction,
         "R30_ACCOUNT_ACCUMULATED_RISK_LIMIT"),
        (acc_risk + risk + account_loss,
         equity * account_policy.max_daily_loss_fraction,
         "R30_ACCOUNT_DAILY_WORST_CASE_LIMIT"),
        (acc_notional + notional, equity * account_policy.max_notional_fraction,
         "R30_ACCOUNT_NOTIONAL_LIMIT"),
        (acc_notional + notional, equity * account_policy.max_leverage,
         "R30_ACCOUNT_LEVERAGE_LIMIT"),
        (acc_margin + margin, equity * account_policy.max_margin_fraction,
         "R30_ACCOUNT_MODELED_MARGIN_LIMIT"),
        (total_risk + risk, portfolio_policy.max_reserved_risk,
         "R30_PORTFOLIO_RESERVED_RISK_LIMIT"),
        (total_risk + risk + loss, portfolio_policy.max_daily_loss,
         "R30_PORTFOLIO_DAILY_WORST_CASE_LIMIT"),
        (total_notional + notional, portfolio_policy.max_notional,
         "R30_PORTFOLIO_NOTIONAL_LIMIT"),
        (group_risk + risk, portfolio_policy.max_group_risk,
         "R30_CORRELATED_GROUP_LIMIT"),
        (engine_risk + risk, portfolio_policy.max_engine_risk,
         "R30_ENGINE_CONCENTRATION_LIMIT"),
    )
    for value, ceiling, code in bounds:
        _fail(value > ceiling, code)
    _fail(len(account_active) >= account_policy.max_active_orders
          or len(active_reservations) >= portfolio_policy.max_active_orders,
          "R30_ACTIVE_POSITION_LIMIT")
    report = {
        "protocol": "MMT_R30_EXISTING_PAPER_RISK_RESEARCH_GATE_V1",
        "verdict": "LOCAL_MODEL_PASS_NO_RESERVATION_OR_SEND_AUTHORITY",
        "portfolio_id": portfolio_policy.portfolio_id,
        "account_id": proposal.account_id,
        "engine_id": proposal.engine_id,
        "instrument": {
            "market": proposal.instrument.market.value,
            "provider": proposal.instrument.provider,
            "symbol": proposal.instrument.symbol,
            "quote_currency": proposal.instrument.quote_currency,
        },
        "proposal_order_id": proposal.order_id,
        "portfolio_day": observed_day,
        "modeled_incremental_risk": _wire_decimal(risk),
        "modeled_incremental_notional": _wire_decimal(notional),
        "modeled_incremental_margin": _wire_decimal(margin),
        "concurrent_portfolio_orders": len(active_reservations),
        "known_order_states_count": len(known_order_statuses),
        "external_exposure_independently_verified": False,
        "portfolio_snapshot_independently_attested": False,
        "broker_order_sent": False,
        "telegram_sent": False,
        "connected_paper_enabled": False,
        "live_trading_enabled": False,
        "order_reservation_created": False,
        "reconciliation_or_restart_resolved": False,
        "production_modified": False,
    }
    report["local_report_sha256"] = hashlib.sha256(_canon(report)).hexdigest()
    return report


__all__ = [
    "R30ActiveReservation", "R30RiskRefused",
    "evaluate_r30_offline_preorder_risk",
]
