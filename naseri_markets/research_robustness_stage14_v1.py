"""Stage-14 fixed trial-inventory and cost robustness; NONPRODUCTION ONLY.

Runs the existing Stage-13 executable fixture for a predeclared stress grid.
Uses the existing Stage-5 PBO/DSR calculator ONLY for a separate, complete,
synchronized, operator-provided multiple-candidate NET return matrix. Those
external diagnostics are NEVER attributed to the single Stage-13 fixture.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import replace
from decimal import Decimal

from ._contract_acceptance_fixture_v1 import OfflineContractFixture
from .core_api_v1 import content_digest
from .executable_walk_forward_stage13_v1 import (
    FrozenExecutionPlan,
    execute_frozen_walk_forward,
)
from .historical_data_loader_a1 import HistoricalFileSpec
from .research_overfit_diagnostics_v1 import analyze_overfit_fixture

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{1,79}\Z")
_MAX_PROTOCOL = 16384
_MAX_MATRIX = 2_000_000
_CASES = (
    ("baseline", Decimal(1), Decimal(1)),
    ("fee_2x", Decimal(2), Decimal(1)),
    ("slippage_2x", Decimal(1), Decimal(2)),
    ("joint_2x", Decimal(2), Decimal(2)),
)
_CASE_NAMES = [case[0] for case in _CASES]
_KEYS = frozenset({
    "schema_version", "experiment_id", "core_id", "core_version",
    "dataset_sha256", "execution_plan_sha256",
    "baseline_execution_evidence_sha256", "claimed_preoutcome_freeze",
    "stress_case_ids", "external_candidate_ids",
    "selected_external_candidate_id", "external_matrix_sha256",
    "claimed_complete_external_trial_inventory",
})


class Stage14Refused(ValueError):
    """Stable refusal codes never reflect untrusted dataset or strategy data."""


def _unique(items: list[tuple[str, object]]) -> dict:
    found = {}
    for key, value in items:
        if key in found:
            raise Stage14Refused("DUPLICATE_FROZEN_PROTOCOL_FIELD")
        found[key] = value
    return found


def _reject_number(_value: str) -> object:
    raise Stage14Refused("NONCANONICAL_PROTOCOL_NUMBER")


def _decode(raw: bytes, pin: str) -> dict:
    if (type(raw) is not bytes or not 1 <= len(raw) <= _MAX_PROTOCOL
            or type(pin) is not str or not _HASH.fullmatch(pin)):
        raise Stage14Refused("PINNED_FROZEN_PROTOCOL_REQUIRED")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), pin):
        raise Stage14Refused("PROTOCOL_DIGEST_MISMATCH")
    try:
        val = json.loads(
            raw, object_pairs_hook=_unique,
            parse_constant=_reject_number, parse_float=_reject_number,
        )
    except Stage14Refused:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise Stage14Refused("INVALID_FROZEN_PROTOCOL") from exc
    if (type(val) is not dict or set(val) != _KEYS
            or type(val["schema_version"]) is not int
            or val["schema_version"] != 1
            or type(val["experiment_id"]) is not str
            or not _ID.fullmatch(val["experiment_id"])
            or val["claimed_preoutcome_freeze"] is not True):
        raise Stage14Refused("INCOMPLETE_FROZEN_PROTOCOL")
    for key in ("dataset_sha256", "execution_plan_sha256",
                "baseline_execution_evidence_sha256"):
        if type(val[key]) is not str or not _HASH.fullmatch(val[key]):
            raise Stage14Refused("INVALID_DECLARED_EVIDENCE_DIGEST")
    if (type(val["stress_case_ids"]) is not list
            or val["stress_case_ids"] != _CASE_NAMES):
        raise Stage14Refused("INCOMPLETE_OR_REORDERED_STRESS_INVENTORY")
    ids = val["external_candidate_ids"]
    if type(ids) is not list or ids != sorted(set(ids)) or any(
        type(x) is not str or not _ID.fullmatch(x) for x in ids
    ):
        raise Stage14Refused("INVALID_EXTERNAL_TRIAL_INVENTORY")
    selected = val["selected_external_candidate_id"]
    matrix = val["external_matrix_sha256"]
    complete = val["claimed_complete_external_trial_inventory"]
    if not ids:
        if selected is not None or matrix is not None or complete is not False:
            raise Stage14Refused("EXTERNAL_TRIALS_MUST_BE_EXPLICIT")
    elif (not 3 <= len(ids) <= 16 or type(selected) is not str
          or selected not in ids or type(matrix) is not str
          or not _HASH.fullmatch(matrix) or complete is not True):
        raise Stage14Refused("COMPLETE_EXTERNAL_TRIAL_EVIDENCE_REQUIRED")
    return val


def _wire(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _case_summary(run: dict) -> dict:
    """All folds and holdout are evaluated, not cherry-picked."""
    tests = [f["test"] for f in run["folds"]]
    segments = [*tests, run["reserved_final_holdout"]]
    return {
        "execution_evidence_sha256": run["evidence_sha256"],
        "validation_fold_test_receipts": [{
            "index": i, "trade_sha256": fold["trade_digest"],
            "closed": fold["closed"], "pending": fold["pending_unfilled_at_end"],
            "unresolved": fold["open_unresolved_at_end"],
            "net_pnl": fold["net_pnl"], "mean_net_r": fold["mean_net_r"],
            "blockers": fold["blockers"],
        } for i, fold in enumerate(tests)],
        "validation_net_pnl": str(sum(
            (Decimal(r["net_pnl"]) for r in tests), Decimal(0),
        )),
        "validation_closed": sum(r["closed"] for r in tests),
        "final_holdout": {
            "trade_sha256": run["reserved_final_holdout"]["trade_digest"],
            "closed": run["reserved_final_holdout"]["closed"],
            "pending": run["reserved_final_holdout"]["pending_unfilled_at_end"],
            "unresolved": run["reserved_final_holdout"]["open_unresolved_at_end"],
            "blockers": run["reserved_final_holdout"]["blockers"],
        },
        "execution_blockers": run["blockers"],
        "has_unresolved": any(r["blockers"] for r in segments),
    }


def _external_stats(raw: bytes, digest: str, scope: dict) -> dict:
    if (type(raw) is not bytes or not 1 <= len(raw) <= _MAX_MATRIX
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest)):
        raise Stage14Refused("EXTERNAL_MATRIX_PIN_MISMATCH")
    # Delegate all parsing, time alignment, CSCV/DSR and duplicate/holdout
    # checks to the EXISTING, tested Stage-5 multi-candidate implementation.
    calc = analyze_overfit_fixture(raw)
    # analyze_overfit_fixture checks candidate count but intentionally does
    # not put the full candidate list in its output. Re-read ONLY after its
    # complete validation, to bind the exact predeclared inventory and choice.
    parsed = json.loads(raw)
    if (parsed["candidate_ids"] != scope["external_candidate_ids"]
            or parsed["selected_candidate_id"] != scope["selected_external_candidate_id"]
            or parsed["declared_total_trials"] != len(scope["external_candidate_ids"])
            or parsed["trial_inventory_complete"] is not True):
        raise Stage14Refused("EXTERNAL_MATRIX_SCOPE_DRIFT")
    return {
        "origin": "SEPARATE_OPERATOR_DECLARED_MULTICANDIDATE_MATRIX",
        "stage13_fixture_attribution_allowed": False,
        "source_authenticated": False,
        "independent_trial_inventory_attested": False,
        "selection_independently_preregistered": False,
        "serial_dependence_adjusted": False,
        "ready_for_profit_claim": False,
        "diagnostics": calc,
    }


def run_stage14_robustness(
    path,
    spec: HistoricalFileSpec,
    *,
    receipt_bytes: bytes,
    trusted_receipt_sha256: str,
    plan: FrozenExecutionPlan,
    protocol_bytes: bytes,
    trusted_protocol_sha256: str,
    external_matrix_bytes: bytes | None = None,
    operator_ack: bool = False,
) -> dict:
    """Mandatory full, fixed cost grid + optional unlinked PBO/DSR diagnostics.

    No historical strategy parameters optimized or selected; external matrix
    cannot be synthesized from Stage-13 trades or its mean R statistics.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise Stage14Refused("NONPRODUCTION_OPERATOR_ACK_REQUIRED")
    if type(plan) is not FrozenExecutionPlan or type(spec) is not HistoricalFileSpec:
        raise Stage14Refused("EXACT_STAGE13_PLAN_AND_DATA_SPEC_REQUIRED")
    protocol = _decode(protocol_bytes, trusted_protocol_sha256)
    manifest = OfflineContractFixture().manifest
    if (protocol["core_id"] != manifest.core_id
            or protocol["core_version"] != manifest.core_version
            or protocol["dataset_sha256"] != spec.expected_sha256
            or protocol["execution_plan_sha256"] != content_digest(plan)):
        raise Stage14Refused("BASELINE_CORE_DATA_PLAN_SCOPE_DRIFT")
    if (plan.fee_bps_per_side > Decimal(50)
            or plan.slippage_bps_per_side > Decimal(50)):
        raise Stage14Refused("STRESS_MODEL_BASIS_POINT_CAP_EXCEEDED")
    ids = protocol["external_candidate_ids"]
    if (not ids) != (external_matrix_bytes is None):
        raise Stage14Refused("EXTERNAL_TRIAL_MATRIX_REQUIRED_OR_FORBIDDEN")
    # All cases are predeclared and evaluated; a hidden losing stress case
    # cannot be excluded based on its PnL or exit-count change.
    results = []
    for name, fee_mult, slip_mult in _CASES:
        shocked = replace(
            plan, fee_bps_per_side=plan.fee_bps_per_side * fee_mult,
            slippage_bps_per_side=plan.slippage_bps_per_side * slip_mult,
        )
        execution = execute_frozen_walk_forward(
            path, spec, receipt_bytes=receipt_bytes,
            trusted_receipt_sha256=trusted_receipt_sha256,
            plan=shocked, operator_ack=True,
        )
        results.append({
            "case_id": name,
            "fee_bps_per_side": str(shocked.fee_bps_per_side),
            "slippage_bps_per_side": str(shocked.slippage_bps_per_side),
            **_case_summary(execution),
        })
    if (results[0]["execution_evidence_sha256"]
            != protocol["baseline_execution_evidence_sha256"]):
        raise Stage14Refused("FROZEN_BASELINE_EXECUTION_DIGEST_MISMATCH")
    baseline = results[0]
    blockers = []
    for row in results:
        if row["execution_blockers"]:
            blockers.append(row["case_id"] + "_EXECUTION_EVIDENCE_BLOCKED")
        if row["validation_closed"] != baseline["validation_closed"]:
            blockers.append(row["case_id"] + "_VALIDATION_OUTCOME_COUNT_DRIFT")
        if Decimal(row["validation_net_pnl"]) > Decimal(baseline["validation_net_pnl"]):
            # Never silently promote an economically suspicious cost result.
            blockers.append(row["case_id"] + "_HIGHER_COST_IMPROVED_PNL_REVIEW")
    extra = (_external_stats(external_matrix_bytes,
                             protocol["external_matrix_sha256"], protocol)
             if external_matrix_bytes is not None else None)
    result = {
        "stage": "STAGE14_OFFLINE_COST_ROBUSTNESS_AND_SEPARATE_OVERFIT_DIAGNOSTICS",
        "study_id": protocol["experiment_id"],
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "dataset_sha256": spec.expected_sha256,
        "frozen_execution_plan_sha256": protocol["execution_plan_sha256"],
        "actual_executable_core_trial_count": 1,
        "scenario_inventory": _CASE_NAMES,
        "case_count": len(results),
        "cases": results,
        "blockers": sorted(set(blockers)),
        "external_matrix_overfit_diagnostics": extra,
        "stage13_single_core_pbo_dsr_applicable": False,
        "pbo_dsr_computed_from_stage13_trades": False,
        "multiple_parameter_variants_executed": False,
        "external_stats_attributable_to_stage13_core": False,
        "claimed_protocol_freeze_independently_attested": False,
        "trial_inventory_independently_attested": False,
        "holdout_exposed_during_repeated_stress_runs": True,
        "blind_final_holdout_preserved": False,
        "historical_source_authenticated": False,
        "real_strategy_backtested": False,
        "profitability_proven": False,
        "broker_orders_authorized": False,
        "telegram_sent": False,
        "live_trading_authorized": False,
        "verdict": ("OFFLINE_COST_STRESS_DESCRIPTIVE_ONLY"
                    if not blockers else "OFFLINE_COST_STRESS_REVIEW_BLOCKED"),
    }
    result["report_sha256"] = hashlib.sha256(_wire(result)).hexdigest()
    return result


__all__ = ["Stage14Refused", "run_stage14_robustness"]
