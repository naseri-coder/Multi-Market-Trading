"""R33: hard-deny LIVE readiness and illustrative 1-position risk caps.

No exchange, broker, HTTP, MT5, Telegram, token, database, scheduler or order
creation. All evidence is OPERATOR-PROVIDED and independently unauthenticated.
Never treat any report or pilot simulation as authorization to place an order.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

PROTO = "MMT_R33_LIVE_READINESS_HARD_DENY_V1"
_STUDY_END = datetime(2026, 11, 3, tzinfo=UTC)
_SHA = re.compile(r"[a-f0-9]{40}\Z")
_EXPECTED_PRS = (321, 322, 323, 324, 325)
_UNKNOWN_ORDER_STATES = frozenset({
    "SUBMISSION_UNKNOWN", "SENT_UNCONFIRMED", "CLAIMED", "QUARANTINED",
})
# Conservative illustrative research caps, NOT an approved live policy.
MAX_TRADE_RISK_FRACTION = Decimal("0.0025")  # 0.25% of assumed equity
MAX_DAY_LOSS_FRACTION = Decimal("0.005")      # 0.50% of assumed equity
MAX_NOTIONAL_FRACTION = Decimal("0.10")       # 10% of assumed equity
MAX_LEVERAGE = Decimal("1")
LIVE_ORDERS_IMPLEMENTED = False


class R33ReadinessRefused(ValueError):
    """Static non-secret refusal code."""


@dataclass(frozen=True, slots=True)
class R33PRObservation:
    number: int
    head_sha: str
    state: str
    draft: bool
    merged: bool

    def __post_init__(self) -> None:
        if (type(self.number) is not int or self.number not in _EXPECTED_PRS
                or type(self.head_sha) is not str
                or _SHA.fullmatch(self.head_sha) is None
                or self.state not in ("open", "closed")
                or type(self.draft) is not bool or type(self.merged) is not bool):
            raise R33ReadinessRefused("R33_PR_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class R33Evidence:
    """External claims; this type does NOT authenticate independent reports."""
    prs: tuple[R33PRObservation, ...]
    review_time_utc: datetime
    r29_prospective_complete: bool = False
    r29_original_data_authenticity_attested: bool = False
    r29_independent_oos_risk_review_passed: bool = False
    r30_fault_injection_passed: bool = False
    r31_private_admin_acl_passed: bool = False
    r32_security_release_signed_and_verified: bool = False
    r32_independent_cold_restore_passed: bool = False
    full_test_and_security_suite_passed: bool = False
    venue_jurisdiction_and_api_permission_verified: bool = False
    live_account_balances_and_positions_reconciled: bool = False
    native_live_execution_adapter_independently_reviewed: bool = False
    live_kill_switch_rehearsal_passed: bool = False
    order_unknown_resolution_independently_verified: bool = False
    no_unresolved_orders: bool = False
    no_unreconciled_side_effects: bool = False
    manual_specific_live_permission_provided: bool = False

    def __post_init__(self) -> None:
        if (type(self.prs) is not tuple or len(self.prs) != len(_EXPECTED_PRS)
                or any(type(p) is not R33PRObservation for p in self.prs)
                or tuple(p.number for p in self.prs) != _EXPECTED_PRS):
            raise R33ReadinessRefused("R33_COMPLETE_ORDERED_PR_INVENTORY_REQUIRED")
        now = self.review_time_utc
        if (type(now) is not datetime or now.tzinfo is None
                or now.utcoffset() is None or now.utcoffset().total_seconds() != 0
                or now.year < 2026 or now.year > 2100):
            raise R33ReadinessRefused("R33_UTC_REVIEW_CLOCK_REQUIRED")
        for name in _EVIDENCE_FLAG_FIELDS:
            if type(getattr(self, name)) is not bool:
                raise R33ReadinessRefused("R33_TYPED_EVIDENCE_FLAGS_REQUIRED")


_EVIDENCE_FLAG_FIELDS = (
    "r29_prospective_complete",
    "r29_original_data_authenticity_attested",
    "r29_independent_oos_risk_review_passed",
    "r30_fault_injection_passed",
    "r31_private_admin_acl_passed",
    "r32_security_release_signed_and_verified",
    "r32_independent_cold_restore_passed",
    "full_test_and_security_suite_passed",
    "venue_jurisdiction_and_api_permission_verified",
    "live_account_balances_and_positions_reconciled",
    "native_live_execution_adapter_independently_reviewed",
    "live_kill_switch_rehearsal_passed",
    "order_unknown_resolution_independently_verified",
    "no_unresolved_orders",
    "no_unreconciled_side_effects",
    "manual_specific_live_permission_provided",
)


def _gate(ack: bool) -> None:
    if (ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise R33ReadinessRefused("R33_EXPLICIT_NONPRODUCTION_REVIEW_ONLY")


def _canon(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def review_r33_live_readiness(
    evidence: R33Evidence, *, operator_ack: bool = False,
) -> dict:
    """Deterministic blocker inventory; always denies live orders.

    All booleans and timestamps are unverifiable caller assertions. A forged
    "complete" payload CANNOT produce a LIVE authorization. The exact current
    Stage 28-32 GitHub state is separate verified evidence of OPEN/DRAFT PRs.
    """
    _gate(operator_ack)
    if type(evidence) is not R33Evidence:
        raise R33ReadinessRefused("R33_TYPED_COMPLETE_EVIDENCE_REQUIRED")
    blockers: list[str] = []
    for p in evidence.prs:
        if p.state != "closed" or p.draft or not p.merged:
            blockers.append("PR_%d_NOT_MERGED_AND_ACCEPTED" % p.number)
    if evidence.review_time_utc < _STUDY_END:
        blockers.append("R29_PROSPECTIVE_WINDOW_NOT_ELAPSED")
    for field in _EVIDENCE_FLAG_FIELDS:
        if not getattr(evidence, field):
            blockers.append(field.upper() + "_UNVERIFIED")
    # Deliberately unconditional: an operator-asserted TRUE or local hash
    # cannot establish independent signatures, approval, actual exchange
    # connectivity safety, legal access, no latent side effects or venue truth.
    blockers.append("R33_NO_INDEPENDENT_LIVE_RELEASE_AUTHORITY_IMPLEMENTED")
    blockers.append("R33_NO_LIVE_ORDER_ROUTE_IN_THIS_STAGE")
    result = {
        "protocol": PROTO,
        "decision": "LIVE_HARD_DENY",
        "review_window_end_utc": _STUDY_END.isoformat(),
        "operator_supplied_time_utc": evidence.review_time_utc.isoformat(),
        "observed_pr_count": len(evidence.prs),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "operator_assertions_independently_authenticated": False,
        "release_cryptographic_signatures_independently_verified": False,
        "live_gateway_exists": False,
        "live_api_credentials_loaded": False,
        "can_route_order": False,
        "can_enable_live": False,
        "can_unhalt_order_switch": False,
        "can_send_telegram_signals": False,
        "can_change_production": False,
        "auto_retry_unknown": False,
        "paper_or_live_trade_executed": False,
    }
    result["report_sha256"] = hashlib.sha256(_canon(result)).hexdigest()
    return result


@dataclass(frozen=True, slots=True)
class R33ReferencePilotEnvelope:
    """Unapproved example research limits for future independent review."""
    assumed_equity: Decimal
    per_trade_risk_fraction: Decimal
    max_daily_loss_fraction: Decimal
    max_notional_fraction: Decimal
    max_leverage: Decimal
    max_concurrent_positions: int

    def __post_init__(self) -> None:
        for name in (
            "assumed_equity", "per_trade_risk_fraction",
            "max_daily_loss_fraction", "max_notional_fraction", "max_leverage",
        ):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite() or value <= 0:
                raise R33ReadinessRefused("R33_EXACT_FINITE_POSITIVE_DECIMAL_REQUIRED")
        if (self.per_trade_risk_fraction > MAX_TRADE_RISK_FRACTION
                or self.max_daily_loss_fraction > MAX_DAY_LOSS_FRACTION
                or self.max_notional_fraction > MAX_NOTIONAL_FRACTION
                or self.max_leverage > MAX_LEVERAGE
                or type(self.max_concurrent_positions) is not int
                or self.max_concurrent_positions != 1):
            raise R33ReadinessRefused("R33_REFERENCE_CAP_EXCEEDED")


def simulate_r33_reference_position(
    *, envelope: R33ReferencePilotEnvelope,
    entry: Decimal, stop: Decimal, quantity: Decimal,
    multiplier: Decimal, roundtrip_fee_fraction: Decimal,
    adverse_slippage_fraction: Decimal,
    already_lost_today: Decimal, current_open_positions: int,
    operator_ack: bool = False,
) -> dict:
    """Offline linear-contract arithmetic, never exchange sizing/approval."""
    _gate(operator_ack)
    if type(envelope) is not R33ReferencePilotEnvelope:
        raise R33ReadinessRefused("R33_REFERENCE_ENVELOPE_REQUIRED")
    for value in (entry, stop, quantity, multiplier):
        if type(value) is not Decimal or not value.is_finite() or value <= 0:
            raise R33ReadinessRefused("R33_POSITIVE_LINEAR_REFERENCE_REQUIRED")
    for value in (roundtrip_fee_fraction, adverse_slippage_fraction,
                  already_lost_today):
        if type(value) is not Decimal or not value.is_finite() or value < 0:
            raise R33ReadinessRefused("R33_NONNEGATIVE_FRICTION_OR_LOSS_REQUIRED")
    if (roundtrip_fee_fraction >= 1 or adverse_slippage_fraction >= 1
            or entry == stop
            or type(current_open_positions) is not int
            or current_open_positions < 0):
        raise R33ReadinessRefused("R33_INVALID_REFERENCE_GEOMETRY")
    notional = quantity * entry * multiplier
    risk = quantity * multiplier * (
        abs(entry - stop)
        + entry * (roundtrip_fee_fraction + adverse_slippage_fraction)
    )
    limits = {
        "reference_trade_risk_cap": (
            envelope.assumed_equity * envelope.per_trade_risk_fraction
        ),
        "reference_notional_cap": (
            envelope.assumed_equity * envelope.max_notional_fraction
        ),
        "reference_day_loss_cap": (
            envelope.assumed_equity * envelope.max_daily_loss_fraction
        ),
    }
    if current_open_positions >= envelope.max_concurrent_positions:
        raise R33ReadinessRefused("R33_REFERENCE_CONCURRENT_POSITION_CAP")
    if already_lost_today >= limits["reference_day_loss_cap"]:
        raise R33ReadinessRefused("R33_REFERENCE_DAILY_STOP_TRIGGERED")
    if (risk > limits["reference_trade_risk_cap"]
            or already_lost_today + risk > limits["reference_day_loss_cap"]):
        raise R33ReadinessRefused("R33_REFERENCE_RISK_CAP_EXCEEDED")
    if (notional > limits["reference_notional_cap"]
            or notional > envelope.assumed_equity * envelope.max_leverage):
        raise R33ReadinessRefused("R33_REFERENCE_NOTIONAL_CAP_EXCEEDED")
    result = {
        "protocol": "MMT_R33_NONEXECUTABLE_REFERENCE_RISK_SIMULATION_V1",
        "mode": "HYPOTHETICAL_LINEAR_ONLY",
        "modeled_notional": format(notional.normalize(), "f"),
        "modeled_stop_risk_including_friction": format(risk.normalize(), "f"),
        "modeled_maximum_leverage_margin_proxy": format(
            (notional / envelope.max_leverage).normalize(), "f"
        ),
        "actual_fee_schedule_authenticated": False,
        "actual_funding_liquidation_and_fill_proven": False,
        "venue_lot_size_or_margin_rules_verified": False,
        "live_trading_approved": False,
        "broker_order_sent": False,
        "paper_order_sent": False,
        "production_modified": False,
    }
    result["report_sha256"] = hashlib.sha256(_canon(result)).hexdigest()
    return result


__all__ = [
    "R33ReadinessRefused", "R33PRObservation", "R33Evidence",
    "R33ReferencePilotEnvelope", "review_r33_live_readiness",
    "simulate_r33_reference_position",
]
