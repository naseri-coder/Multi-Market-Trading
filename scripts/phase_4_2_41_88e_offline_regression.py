"""Offline current-contract regression checks for
4.2.41.88E-current-contract; no production inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research_layer.phase_4_2_41_88e.contract import (
    ARTIFACT_SCHEMA_VERSION,
    CONTRACT_SHA,
    RISK_SEMANTIC_MODEL,
    RUNNER_POLICY,
    STAT,
    assert_contract,
)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_parity(document):
    if document.get("assertion_contract") != "CURRENT_PLAN_ALLOCATION_INVARIANTS":
        raise ValueError("CURRENT_PARITY_CONTRACT_MISSING")
    groups = {}
    for name in ("exact14", "holdout67", "bootstrap86"):
        rows = document.get(name, [])
        if not isinstance(rows, list):
            raise ValueError("CURRENT_PARITY_GROUP_INVALID")
        if not all(row.get("pass") is True for row in rows):
            raise ValueError("CURRENT_PARITY_ROW_FAILED")
        for row in rows:
            checks = row.get("checks")
            if not isinstance(checks, dict) or not checks or not all(checks.values()):
                raise ValueError("CURRENT_PARITY_DETAILED_CHECK_FAILED")
            if row.get("risk_semantic_model") not in {None, RISK_SEMANTIC_MODEL}:
                raise ValueError("CURRENT_PARITY_RISK_MODEL_MISMATCH")
            if row.get("runner_policy") not in {None, RUNNER_POLICY}:
                raise ValueError("CURRENT_PARITY_RUNNER_POLICY_MISMATCH")
        summary = document.get("summary", {}).get(name)
        if summary is not None and summary != [len(rows), len(rows)]:
            raise ValueError("CURRENT_PARITY_SUMMARY_MISMATCH")
        groups[name] = {
            "rows": len(rows),
            "all_pass": True,
        }
    return groups


def validate_probability_report(document):
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError("PROBABILITY_REPORT_ROWS_MISSING")
    readiness = {}
    for row in rows:
        if "calibration_status" in row:
            raise ValueError("LEGACY_CALIBRATION_STATUS_FORBIDDEN")
        state = row.get("readiness_state")
        if not state:
            raise ValueError("CURRENT_READINESS_STATE_MISSING")
        readiness[state] = readiness.get(state, 0) + 1
        if row.get("current_plan_rr") != row.get("v6_planned_reward_r"):
            raise ValueError("CURRENT_PLAN_COMPATIBILITY_ALIAS_MISMATCH")
    recomputed = {
        state: sum(row["readiness_state"] == state for row in rows) for state in sorted(readiness)
    }
    if document.get("decision_summary") != recomputed:
        raise ValueError("PROBABILITY_SUMMARY_MISMATCH")
    guards = document.get("admission_guards", {})
    required_guards = (
        "realized_r_current_contract",
        "terminal_strictly_before_candidate",
        "all_selected_scope_cases_used",
    )
    if not all(guards.get(key) is True for key in required_guards):
        raise ValueError("CURRENT_ADMISSION_GUARD_MISSING")
    if guards.get("wilson_controls_admission") is not False:
        raise ValueError("WILSON_MUST_REMAIN_TELEMETRY_ONLY")
    return {
        "rows": len(rows),
        "readiness": readiness,
        "current_contract": True,
    }


def main(*, parity_path, phase88b_path, phase88c_path, output_path):
    assert_contract()
    parity = validate_parity(load(parity_path))
    phase88b = validate_probability_report(load(phase88b_path))
    phase88c = validate_probability_report(load(phase88c_path))
    result = {
        "phase": "4.2.41.88E-current-contract",
        "assertion_contract": "CURRENT_PLAN_ALLOCATION_INVARIANTS",
        "historical_performance_claims": False,
        "parity": parity,
        "phase88b": phase88b,
        "phase88c": phase88c,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "risk_semantic_model": RISK_SEMANTIC_MODEL,
        "runner_policy": RUNNER_POLICY,
        "statistics_contract_version": STAT,
        "source_frozen_contract_sha": CONTRACT_SHA,
        "input_sha256": {
            "parity": hashlib.sha256(parity_path.read_bytes()).hexdigest(),
            "phase88b": hashlib.sha256(phase88b_path.read_bytes()).hexdigest(),
            "phase88c": hashlib.sha256(phase88c_path.read_bytes()).hexdigest(),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print("SHA256", hashlib.sha256(output_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parity", type=Path, required=True)
    parser.add_argument("--phase88b", type=Path, required=True)
    parser.add_argument("--phase88c", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(
        parity_path=args.parity,
        phase88b_path=args.phase88b,
        phase88c_path=args.phase88c,
        output_path=args.output,
    )
