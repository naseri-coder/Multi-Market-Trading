"""R26: strict offline Brooks V5 decision-versus-modeled execution audit.

Validates an ORIGINAL Stage21A receipt hash and explicitly distinguishes a
frozen strategy decision from an assumed next-open market trade. This module
NEVER certifies broker fills, historical PnL, prospective OOS or live PAPER.
No broker, HTTP, secrets, background scheduler or database.
"""
from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal, InvalidOperation

from .brooks_causal_lifecycle_stage21_preflight_v1 import (
    Stage21StudyRefused,
    run_stage21_brooks_lifecycle_preflight,
)
from .brooks_replay import LEGACY_MANIFEST_SHA256

_MAX_REPORT = 131072
_KIND = "MMT_R26_FROZEN_BROOKS_DECISION_EXECUTION_PARITY_AUDIT_V1"


class R26ParityRefused(ValueError):
    """Static refusal codes only, never arbitrary input data."""


def _canon(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    output = {}
    for k, v in pairs:
        if k in output:
            raise R26ParityRefused("R26_DUPLICATE_REPORT_JSON_FIELD")
        output[k] = v
    return output


def _amount(value: object) -> Decimal:
    if type(value) is not str or not 1 <= len(value) <= 48:
        raise R26ParityRefused("R26_INVALID_HYPOTHETICAL_AMOUNT")
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise R26ParityRefused("R26_INVALID_HYPOTHETICAL_AMOUNT") from exc
    if not d.is_finite():
        raise R26ParityRefused("R26_INVALID_HYPOTHETICAL_AMOUNT")
    return d


def audit_original_stage21a_receipt(
    *, original_report_bytes: bytes, operator_ack: bool = False,
) -> dict:
    """Only original hash-consistent Stage21A evidence, not arbitrary PnL."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise R26ParityRefused("R26_EXPLICIT_NONPRODUCTION_RESEARCH_REQUIRED")
    if (type(original_report_bytes) is not bytes
            or not 2 <= len(original_report_bytes) <= _MAX_REPORT):
        raise R26ParityRefused("R26_BOUNDED_ORIGINAL_RECEIPT_REQUIRED")
    try:
        report = json.loads(
            original_report_bytes, object_pairs_hook=_unique,
            parse_constant=lambda _v: (_ for _ in ()).throw(
                R26ParityRefused("R26_NONFINITE_JSON_REFUSED")),
        )
    except R26ParityRefused:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise R26ParityRefused("R26_ORIGINAL_RECEIPT_JSON_INVALID") from exc
    if type(report) is not dict:
        raise R26ParityRefused("R26_ORIGINAL_RECEIPT_NOT_OBJECT")
    original_hash = report.get("report_sha256")
    payload = dict(report)
    payload.pop("report_sha256", None)
    if (type(original_hash) is not str or len(original_hash) != 64
            or _sha(_canon(payload)) != original_hash
            or _canon(report) != original_report_bytes):
        raise R26ParityRefused("R26_ORIGINAL_CANONICAL_SHA_MISMATCH")
    fixed = {
        "stage": "STAGE21_BROOKS_CAUSAL_LIFECYCLE_PREPARATION_V1",
        "status": "ACTUAL_FROZEN_DECISION_HYPOTHETICAL_TRADE_MODEL_ONLY",
        "source_manifest_sha256": LEGACY_MANIFEST_SHA256,
        "independent_dataset_archive_authentication": False,
        "exact_contract_fee_and_mark_verified": False,
        "prospective_holdout_untouched_attested": False,
        "real_brooks_strategy_execution_parity": False,
        "actual_realized_pnl": False,
        "paper_trading_enabled": False,
        "live_trading_authorized": False,
        "network_or_telegram_used": False,
        "production_modified": False,
    }
    if any(report.get(k) != v or type(report.get(k)) is not type(v) for k,v in fixed.items()):
        raise R26ParityRefused("R26_ORIGINAL_STAGE21A_TRUST_CLAIMS_DRIFT")
    decision = report.get("actual_frozen_brooks_decision")
    trade = report.get("hypothetical_trade")
    if decision not in ("NO_SIGNAL", "LONG", "SHORT") or type(trade) is not dict:
        raise R26ParityRefused("R26_INVALID_ORIGINAL_DECISION_TRADE_SHAPE")
    for k in ("historical_snapshot_sha256","decision_evidence_sha256",
              "decision_input_sha256","future_input_sha256"):
        value=report.get(k)
        if (type(value) is not str or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            raise R26ParityRefused("R26_ORIGINAL_EVIDENCE_HASH_MISSING")
    if (trade.get("broker_fill_verified") is not False
            or trade.get("hypothetical_order") is not (
                decision != "NO_SIGNAL"
                and trade.get("state") == "HYPOTHETICAL_CLOSED_POSITION"
            )):
        raise R26ParityRefused("R26_BROKER_FILL_OR_ORDER_FLAG_DRIFT")
    state=trade.get("state")
    if decision == "NO_SIGNAL":
        if (state != "NO_SIGNAL" or trade.get("net_scenario_quote") is not None):
            raise R26ParityRefused("R26_NO_SIGNAL_CANNOT_BOOK_PNL")
        net = None
    elif state == "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY":
        if trade.get("net_scenario_quote") is not None:
            raise R26ParityRefused("R26_REFUSED_ENTRY_CANNOT_BOOK_PNL")
        net = None
    elif state == "HYPOTHETICAL_CLOSED_POSITION":
        if (trade.get("entry_model") != "NEXT_CANDLE_OPEN_MARKET_ASSUMPTION"
                or trade.get("exit_model") != "NEAREST_TP_OR_STOP_FIRST_ADVERSE_GAP_PRIORITY"
                or trade.get("actual_signal_execution_parity_verified") is not False
                or trade.get("account_fee_tier_verified") is not False
                or trade.get("settlement_mark_is_exact") is not False
                or trade.get("market_impact_verified") is not False
                or type(trade.get("funding_event_count")) is not int
                or not 0 <= trade["funding_event_count"] <= 16):
            raise R26ParityRefused("R26_MODEL_ASSUMPTIONS_OR_VERIFICATION_DRIFT")
        if any(type(trade.get(k)) is not str or not trade[k] for k in (
            "entry_time","exit_assumed_bar_close_time","exit_reason",
            "economic_receipt_sha256","entry_reference_price",
            "exit_reference_price","quantity_contracts")):
            raise R26ParityRefused("R26_INCOMPLETE_MODELED_TRADE")
        for k in ("entry_reference_price","exit_reference_price","quantity_contracts"):
            if _amount(trade[k]) <= 0:
                raise R26ParityRefused("R26_INVALID_HYPOTHETICAL_PRICE_QUANTITY")
        net = str(_amount(trade.get("net_scenario_quote")))
    else:
        raise R26ParityRefused("R26_UNKNOWN_ORIGINAL_MODEL_STATE")
    result = {
        "protocol": _KIND,
        "original_stage21a_report_sha256": original_hash,
        "frozen_brooks_source_manifest_sha256": LEGACY_MANIFEST_SHA256,
        "decision": decision,
        "model_state": state,
        "modeled_net_quote_reference_not_actual_pnl": net,
        "original_frozen_decision_cryptographically_reexecuted_by_this_audit": False,
        "broker_fill_or_order_receipt_present": False,
        "strategy_order_type_equivalent_to_next_open_market_assumption": False,
        "exact_fill_spread_queue_slippage_and_funding_verified": False,
        "historical_or_prospective_trade_profitability_established": False,
        "connected_paper_mode_authorized": False,
        "live_order_authorized": False,
        "risk_review_required": True,
        "parity_disposition": (
            "NO_SIGNAL_NO_ORDER"
            if decision == "NO_SIGNAL" else
            "HYPOTHETICAL_ENTRY_REFUSED"
            if state == "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY" else
            "MODELED_LIFECYCLE_ONLY_ACTUAL_ORDER_PARITY_UNVERIFIED"
        ),
    }
    result["report_sha256"] = _sha(_canon(result))
    return result


def run_r26_genuine_brooks_model_and_audit(*, operator_ack: bool = False, **kwargs) -> dict:
    """Execute original frozen Stage21A worker FIRST; audit its exact receipt."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise R26ParityRefused("R26_EXPLICIT_NONPRODUCTION_RESEARCH_REQUIRED")
    try:
        original = run_stage21_brooks_lifecycle_preflight(
            **kwargs, operator_ack=True,
        )
    except Stage21StudyRefused as exc:
        raise R26ParityRefused("R26_ORIGINAL_BROOKS_CAUSAL_MODEL_REFUSED") from exc
    reviewed = audit_original_stage21a_receipt(
        original_report_bytes=_canon(original), operator_ack=True,
    )
    return {
        "original_stage21a_report": original,
        "r26_execution_parity_audit": reviewed,
    }


__all__ = ["R26ParityRefused", "audit_original_stage21a_receipt",
           "run_r26_genuine_brooks_model_and_audit"]
