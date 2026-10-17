"""R26: one REAL frozen Brooks V5 decision, two HYPOTHETICAL post-cutoff paths.

The source-pinned worker runs once BEFORE either future is admitted. The
independent Decimal cashflow cross-check can refuse the existing model but
cannot turn modeled next-open/stop/TP into a broker fill, a proven market
edge, or a signed futures fee account statement.
No network, Telegram, broker, database, PAPER or production writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .brooks_causal_lifecycle_stage21_preflight_v1 import (
    FrozenGeometry,
    _model_next_open,
    _source,
    _validated_continuation,
)
from .futures_economic_scenario_stage16_v1 import (
    FundingMarkScenario,
    model_linear_usdm_research_scenario,
)

_ID = re.compile(r"[a-z][a-z0-9_-]{1,39}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_DEC = re.compile(r"-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,12})?\Z")


class R26AttributionRefused(ValueError):
    """Constant non-sensitive refusal codes; never reflect input data."""


@dataclass(frozen=True, slots=True)
class R26CounterfactualPath:
    """Hypothetical future context, NOT a real prospective held-out tape."""

    label: str
    post_signal_closed_candles: tuple[dict, ...]
    expected_funding_instants: tuple[datetime, ...]
    funding_mark_events: tuple[FundingMarkScenario, ...]


def _canon(data: object) -> bytes:
    return json.dumps(
        data, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _decimal(raw: object, *, nonnegative: bool = False) -> Decimal:
    if type(raw) is not str or not _DEC.fullmatch(raw):
        raise R26AttributionRefused("R26_STRICT_DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise R26AttributionRefused("R26_INVALID_DECIMAL") from exc
    if not number.is_finite() or (nonnegative and number < 0):
        raise R26AttributionRefused("R26_FINITE_NONNEGATIVE_DECIMAL_REQUIRED")
    return number


def _metadata(payload: bytes, pin: str) -> dict:
    if (type(payload) is not bytes or not 1 <= len(payload) <= 4096
            or type(pin) is not str or not _SHA.fullmatch(pin)
            or _sha256(payload) != pin):
        raise R26AttributionRefused("R26_ORIGINAL_PINNED_ECONOMICS_REQUIRED")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise R26AttributionRefused("R26_DUPLICATE_ECONOMIC_KEY")
            result[key] = value
        return result
    try:
        parsed = json.loads(
            payload.decode("ascii"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, TypeError, UnicodeError) as exc:
        raise R26AttributionRefused("R26_INVALID_ECONOMIC_JSON") from exc
    if type(parsed) is not dict:
        raise R26AttributionRefused("R26_ECONOMIC_OBJECT_REQUIRED")
    return parsed


def _independent_cashflows(
    *, model: dict, decision: str, metadata: dict,
    metadata_bytes: bytes, metadata_sha256: str,
    quantity: str, funding: tuple[FundingMarkScenario, ...],
) -> dict:
    """Separate exact arithmetic from Stage16; checks but cannot certify fees.

    Stage16 already enforces contract schema, fee caps, price/lot grids,
    every funding instant and stop-first exits before this audit is reached.
    """
    if model.get("broker_fill_verified") is not False:
        raise R26AttributionRefused("R26_MODEL_CANNOT_CLAIM_REAL_FILL")
    if model.get("state") != "HYPOTHETICAL_CLOSED_POSITION":
        if (model.get("state") not in (
                "NO_SIGNAL", "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY")
                or model.get("hypothetical_order") is not False
                or model.get("net_scenario_quote") is not None):
            raise R26AttributionRefused("R26_NONTRADE_SHALL_HAVE_NO_CASHFLOW")
        return {
            "verdict": "NO_HYPOTHETICAL_POSITION_NO_PNL",
            "model_state": model["state"],
            "independent_arithmetic_parity": None,
            "reported_modeled_net_quote": None,
            "broker_fill_verified": False,
        }
    if model.get("hypothetical_order") is not True or decision not in ("LONG", "SHORT"):
        raise R26AttributionRefused("R26_HYPOTHETICAL_FILL_SEMANTICS_DRIFT")
    if (model.get("entry_model") != "NEXT_CANDLE_OPEN_MARKET_ASSUMPTION"
            or model.get("exit_model") != "NEAREST_TP_OR_STOP_FIRST_ADVERSE_GAP_PRIORITY"
            or model.get("actual_signal_execution_parity_verified") is not False
            or model.get("settlement_mark_is_exact") is not False
            or model.get("account_fee_tier_verified") is not False
            or model.get("market_impact_verified") is not False):
        raise R26AttributionRefused("R26_MODEL_OR_REALITY_LABEL_DRIFT")
    side = Decimal(1) if decision == "LONG" else Decimal(-1)
    qty = _decimal(quantity, nonnegative=True)
    mult = _decimal(metadata.get("base_units_per_contract"), nonnegative=True)
    fee = _decimal(metadata.get("taker_fee_fraction"), nonnegative=True)
    slip = _decimal(metadata.get("worst_slippage_fraction"), nonnegative=True)
    if qty <= 0 or mult <= 0 or fee > Decimal("0.01") or slip > Decimal("0.01"):
        raise R26AttributionRefused("R26_INDEPENDENT_FEE_OR_QUANTITY_BOUNDS")
    entry = _decimal(model.get("entry_reference_price"), nonnegative=True)
    exit_price = _decimal(model.get("exit_reference_price"), nonnegative=True)
    if entry <= 0 or exit_price <= 0:
        raise R26AttributionRefused("R26_INVALID_MODELED_PRICE")
    try:
        entry_at = datetime.fromisoformat(model["entry_time"])
        exit_at = datetime.fromisoformat(model["exit_assumed_bar_close_time"])
    except (KeyError, TypeError, ValueError) as exc:
        raise R26AttributionRefused("R26_INVALID_MODELED_EVENT_TIMES") from exc
    if (entry_at.tzinfo is None or exit_at.tzinfo is None
            or entry_at.utcoffset().total_seconds() != 0
            or exit_at.utcoffset().total_seconds() != 0
            or not entry_at < exit_at):
        raise R26AttributionRefused("R26_UTC_AND_CAUSAL_EVENT_TIMES_REQUIRED")
    gross = side * qty * mult * (exit_price-entry)
    fees = qty * mult * (entry+exit_price) * fee
    adverse_slip = qty * mult * (entry+exit_price) * slip
    funding_quote = Decimal(0)
    charged = 0
    for event in funding:
        if type(event) is not FundingMarkScenario:
            raise R26AttributionRefused("R26_FUNDING_SCENARIO_TYPE_REQUIRED")
        if entry_at < event.at <= exit_at:
            rate = _decimal(event.funding_rate)
            mark = _decimal(event.referenced_mark_price, nonnegative=True)
            if abs(rate) > Decimal("0.01") or mark <= 0:
                raise R26AttributionRefused("R26_UNTRUSTED_FUNDING_PARAMETER")
            funding_quote += -side * qty * mult * mark * rate
            charged += 1
    independent_net = gross-fees-adverse_slip+funding_quote
    reported_net = _decimal(model.get("net_scenario_quote"))
    if independent_net != reported_net or charged != model.get("funding_event_count"):
        raise R26AttributionRefused("R26_ST16_MODEL_DISAGREES_WITH_INDEPENDENT_DECIMAL")
    # Attribution requires the original Stage16 economic receipt SHA to
    # agree too; a forged SHA is not rescued by accidentally correct net PnL.
    try:
        original_receipt = model_linear_usdm_research_scenario(
            metadata_bytes, expected_metadata_sha256=metadata_sha256,
            side="long" if decision == "LONG" else "short",
            quantity_contracts=quantity,
            entry_price=str(entry), exit_price=str(exit_price),
            entry_at=entry_at, exit_at=exit_at,
            funding_mark_events=tuple(
                event for event in funding if entry_at < event.at <= exit_at
            ),
            operator_ack=True,
        )
    except ValueError as exc:
        raise R26AttributionRefused("R26_ORIGINAL_STAGE16_CASHFLOW_UNREPRODUCIBLE") from exc
    if (original_receipt["evidence_sha256"] != model.get("economic_receipt_sha256")
            or _decimal(original_receipt["net_scenario_quote"]) != independent_net):
        raise R26AttributionRefused("R26_ORIGINAL_ECONOMIC_RECEIPT_SHA_OR_NET_DRIFT")
    return {
        "verdict": "MODELED_CASHFLOW_ARITHMETIC_RECONCILED_ONLY",
        "model_state": model["state"],
        "independent_arithmetic_parity": True,
        "gross_quote": str(gross),
        "two_sided_taker_fee_quote": str(fees),
        "two_sided_adverse_slippage_proxy_quote": str(adverse_slip),
        "funding_quote": str(funding_quote),
        "charged_funding_instants": charged,
        "independent_net_quote": str(independent_net),
        "reported_modeled_net_quote": str(reported_net),
        "broker_fill_verified": False,
        "actual_order_id_available": False,
        "liquidation_and_real_orderbook_modeled": False,
    }


def r26_audit_frozen_brooks_two_paths(
    *, original_replay_bytes: bytes,
    legacy_source: Path,
    counterfactuals: tuple[R26CounterfactualPath, R26CounterfactualPath],
    economic_metadata_bytes: bytes,
    economic_metadata_sha256: str,
    quantity_contracts: str,
    operator_ack: bool = False,
) -> dict:
    """Frozen decision exactly once, independently varied *later* price paths.

    No original 2024 historical source or original October 2026 signed plan is
    modified. Future paths are operator-supplied what-if examples, NOT a
    prospective dataset, even if the unchanged worker actually ran.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise R26AttributionRefused("R26_NONPRODUCTION_OFFLINE_ONLY")
    if (type(counterfactuals) is not tuple or len(counterfactuals) != 2
            or any(type(x) is not R26CounterfactualPath for x in counterfactuals)):
        raise R26AttributionRefused("R26_EXACT_TWO_COUNTERFACTUAL_PATHS_REQUIRED")
    if (any(not _ID.fullmatch(p.label) for p in counterfactuals)
            or counterfactuals[0].label == counterfactuals[1].label
            or any(type(p.post_signal_closed_candles) is not tuple
                   or not 1 <= len(p.post_signal_closed_candles) <= 32
                   or type(p.expected_funding_instants) is not tuple
                   or type(p.funding_mark_events) is not tuple
                   for p in counterfactuals)):
        raise R26AttributionRefused("R26_UNIQUE_BOUNDED_RESEARCH_PATHS_REQUIRED")
    try:
        future_bytes = [_canon(p.post_signal_closed_candles) for p in counterfactuals]
    except (ValueError, TypeError) as exc:
        raise R26AttributionRefused("R26_FUTURE_PRICE_PATH_NOT_CANONICAL") from exc
    if future_bytes[0] == future_bytes[1]:
        raise R26AttributionRefused("R26_COUNTERFACTUAL_PATHS_MUST_DIFFER")
    metadata = _metadata(economic_metadata_bytes, economic_metadata_sha256)
    # This is the only path to the actual, pinned original worker. Neither
    # post-signal scenario can enter this call's arguments or worker process.
    frozen = _source(original_replay_bytes, legacy_source)
    if type(frozen) is not FrozenGeometry:
        raise R26AttributionRefused("R26_FROZEN_WORKER_GEOMETRY_REQUIRED")
    if (frozen.decision not in ("LONG", "SHORT", "NO_SIGNAL")
            or frozen.source_manifest_sha256 is None):
        raise R26AttributionRefused("R26_FROZEN_DECISION_NOT_SUPPORTED")
    decision_before = {
        "decision": frozen.decision,
        "entry_intent": frozen.entry,
        "stop_intent": frozen.stop,
        "targets_intent": list(frozen.targets),
        "causal_cutoff_utc": frozen.signal_close_at.isoformat(),
        "input_sha256": frozen.input_sha256,
        "original_frozen_source_manifest_sha256": frozen.source_manifest_sha256,
        "decision_evidence_sha256": frozen.decision_evidence_sha256,
        "snapshot_sha256": frozen.snapshot_sha256,
        "cutoff_prior_to_both_futures": True,
    }
    result_paths = []
    for path, raw in zip(counterfactuals, future_bytes, strict=True):
        future = _validated_continuation(
            original_replay_bytes, path.post_signal_closed_candles,
            frozen.signal_close_at,
        )
        model = _model_next_open(
            frozen, future=future,
            quantity=quantity_contracts,
            metadata=economic_metadata_bytes,
            metadata_sha256=economic_metadata_sha256,
            expected_funding_instants=path.expected_funding_instants,
            funding_events=path.funding_mark_events,
        )
        economics = _independent_cashflows(
            model=model, decision=frozen.decision, metadata=metadata,
            metadata_bytes=economic_metadata_bytes,
            metadata_sha256=economic_metadata_sha256,
            quantity=quantity_contracts, funding=path.funding_mark_events,
        )
        result_paths.append({
            "label": path.label,
            "hypothetical_future_path_sha256": _sha256(raw),
            "hypothetical_path_bar_count": len(future),
            "unchanged_original_frozen_decision_sha256": _sha256(_canon(decision_before)),
            "counterfactual_hypothetical_order_model": model,
            "independent_economic_accounting": economics,
            "observed_market_response_issuer_signed": False,
            "actual_broker_fill_reconciled": False,
            "noncausal_worker_future_input_provided": False,
        })
    result = {
        "protocol": "MMT_R26_BROOKS_FROZEN_DECISION_TWO_PATH_PARITY_RESEARCH_V1",
        "status": "GENUINE_FROZEN_DECISION_TWO_HYPOTHETICAL_LIFECYCLES_ONLY",
        "frozen_original_decision": decision_before,
        "actual_frozen_worker_invocations": 1,
        "economic_metadata_operator_asserted_sha256": economic_metadata_sha256,
        "independent_accounting_reconciled_where_modeled": True,
        "counterfactuals": result_paths,
        "historical_data_source_independently_authenticated": False,
        "counterfactuals_real_market_observations": False,
        "original_exchange_execution_order_ids_present": False,
        "historical_fee_tier_independently_attested": False,
        "funding_mark_settlement_independently_authenticated": False,
        "true_prospective_oos_performance_verified": False,
        "backtest_trading_edge_demonstrated": False,
        "connected_paper_started": False,
        "live_order_authorized": False,
        "telegram_sent": False,
        "network_used": False,
        "production_modified": False,
    }
    result["report_sha256"] = _sha256(_canon(result))
    return result


__all__ = [
    "R26AttributionRefused", "R26CounterfactualPath",
    "r26_audit_frozen_brooks_two_paths",
]
