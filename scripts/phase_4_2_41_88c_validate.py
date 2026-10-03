"""Validate 4.2.41.88C closed cases against the current realized-R probability contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.modules.brooks_core.engine_contract import (
    ReversalOutcomeContext,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceIdentity,
)
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BROOKS_HP_STATISTICS_CONTRACT_ID,
    BrooksRuleEvidence,
)
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
)

ARTIFACT_SCHEMA_VERSION = "brooks-research-current-risk-v1"
RISK_SEMANTIC_MODEL = "PLAN_WEIGHTED_PRETRADE"
RUNNER_POLICY = "UNDEFINED_OBJECTIVE_ZERO_CONSERVATIVE"


def dt(value):
    return datetime.fromisoformat(value)


def dec(value):
    return Decimal(str(value))


def reconstruct(row):
    raw = row["snapshot"]
    snapshot = MarketSnapshot(
        raw["exchange"],
        raw["market_type"],
        raw["symbol"],
        raw["timeframe"],
        tuple(
            Candle(
                dt(bar["open_time"]),
                dt(bar["close_time"]),
                dec(bar["open"]),
                dec(bar["high"]),
                dec(bar["low"]),
                dec(bar["close"]),
                dec(bar["volume"]),
            )
            for bar in raw["candles"]
        ),
        dt(raw["captured_at"]),
        raw["source"],
    )
    evidence = tuple(
        BrooksRuleEvidence(
            item["rule_id"],
            item["status"],
            tuple(item["source_pages"]),
            tuple(tuple(value) for value in item["evidence"]),
            tuple(item["failed_conditions"]),
            tuple(tuple(value) for value in item["confidence_components"]),
        )
        for item in row["rule_evidence"]
    )
    return PaperSignalCandidate(
        source_signal_id="4.2.41.88C_VALIDATE_CURRENT",
        symbol=row["symbol"],
        timeframe=row["timeframe"],
        direction=row["direction"],
        entry_price=dec(row["entry"]),
        stop_loss=dec(row["initial_stop"]),
        targets=tuple(dec(value) for value in row["targets"]),
        exchange=row["exchange"],
        market_type=row["market_type"],
        setup_type=row["setup_type"],
        market_snapshot_id=row["snapshot_id"],
        market_snapshot_hash=row["snapshot_hash"],
        engine_version=row["engine_version"],
        rule_set_version=row["rule_set_version"],
        configuration_version=row["configuration_version"],
        reasoning=tuple(row["reasoning"]),
        rule_ids=tuple(row["rule_ids"]),
        failed_rules=tuple(row["failed_rules"]),
        rule_evidence=evidence,
        chart_path="NO_PUBLICATION",
        snapshot=snapshot,
        target_source_identities=tuple(
            TargetSourceIdentity.from_metadata(item) for item in row["target_source_identities"]
        ),
        stop_source_identity=(
            None
            if row.get("stop_source_identity") is None
            else StopSourceIdentity.from_metadata(row["stop_source_identity"])
        ),
        target_plan_lifecycle=TargetPlanLifecycle.from_metadata(row["target_plan_lifecycle"]),
        reversal_outcome_context=(
            None
            if row.get("reversal_outcome_context") is None
            else ReversalOutcomeContext.from_metadata(row["reversal_outcome_context"])
        ),
        semantic_cohort_id=row.get("semantic_cohort_id"),
    )


def validate_current_schema(row):
    if row["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ValueError("ARTIFACT_SCHEMA_MISMATCH")
    if row["risk_semantic_model"] != RISK_SEMANTIC_MODEL:
        raise ValueError("RISK_SEMANTIC_MODEL_MISMATCH")
    if row["runner_policy"] != RUNNER_POLICY:
        raise ValueError("RUNNER_POLICY_MISMATCH")
    if dec(row["current_plan_rr"]) != dec(row["v6_planned_reward_r"]):
        raise ValueError("V6_COMPATIBILITY_ALIAS_MISMATCH")
    if not all(dict(row["current_plan_invariants"]).values()):
        raise ValueError("CURRENT_PLAN_INVARIANTS_FAIL")
    if not isinstance(row.get("management_plan"), dict):
        raise ValueError("CURRENT_MANAGEMENT_PLAN_MISSING")


def fingerprint(row):
    return hashlib.sha256(
        json.dumps(
            {
                "candidate_identity": row["candidate_identity"],
                "current_plan_rr": row["current_plan_rr"],
                "management_plan": row["management_plan"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def historical_case(row, signal_id):
    value = float(dec(row["realized_r"]))
    return HistoricalCase(
        signal_id=signal_id,
        setup_type=row["setup_type"],
        timeframe=row["timeframe"],
        direction=row["direction"],
        structure_quality=0.0,
        context_quality=0.0,
        entry_quality=0.0,
        risk_feature=float(dec(row["current_plan_rr"])),
        outcome=1 if value > 0 else 0,
        rule_ids=tuple(row["rule_ids"]),
        semantic_cohort_id=row.get("semantic_cohort_id"),
        generation_mode="RESEARCH",
        economic_opportunity_id=row["candidate_identity"],
        symbol=row["symbol"],
        realized_r=value,
        payoff_input_fingerprint=fingerprint(row),
        outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    )


def main(*, candidates_path, forward_path, canonical_output, report_output):
    candidate_doc = json.loads(candidates_path.read_text(encoding="utf-8"))
    forward_doc = json.loads(forward_path.read_text(encoding="utf-8"))
    candidates = candidate_doc["candidates"]
    candidate_by_id = {row["candidate_identity"]: row for row in candidates}
    for row in candidates:
        validate_current_schema(row)

    cases = []
    for outcome in forward_doc["rows"]:
        if outcome.get("canonicalization_status") != "VALID_REALIZED_R":
            continue
        source = candidate_by_id[outcome["candidate_identity"]]
        case = {
            "candidate_identity": source["candidate_identity"],
            "snapshot_hash": source["snapshot_hash"],
            "candidate_timestamp": source["candidate_timestamp"],
            "terminal_timestamp": outcome["terminal_timestamp"],
            "symbol": source["symbol"],
            "timeframe": source["timeframe"],
            "direction": source["direction"],
            "setup_type": source["setup_type"],
            "entry": source["entry"],
            "initial_stop": source["initial_stop"],
            "targets": source["targets"],
            "current_plan_rr": source["current_plan_rr"],
            "v6_planned_reward_r": source["v6_planned_reward_r"],
            "management_plan": source["management_plan"],
            "risk_semantic_breakdown": source["risk_semantic_breakdown"],
            "artifact_schema_version": source["artifact_schema_version"],
            "risk_semantic_model": source["risk_semantic_model"],
            "runner_policy": source["runner_policy"],
            "target_source_identities": source["target_source_identities"],
            "stop_source_identity": source["stop_source_identity"],
            "target_plan_lifecycle": source["target_plan_lifecycle"],
            "reversal_outcome_context": source["reversal_outcome_context"],
            "semantic_cohort_id": source.get("semantic_cohort_id"),
            "terminal_lifecycle_reason": outcome["terminal_lifecycle_reason"],
            "weighted_realized_pnl_pct_unlevered": outcome["weighted_realized_pnl_pct_unlevered"],
            "realized_r": outcome["realized_r"],
            "mfe_r": outcome["mfe_r"],
            "mae_r": outcome["mae_r"],
            "engine_version": source["engine_version"],
            "rule_set_version": source["rule_set_version"],
            "configuration_version": source["configuration_version"],
            "exchange": source["exchange"],
            "market_type": source["market_type"],
            "management_version": source["management_version"],
            "rule_ids": source["rule_ids"],
            "canonicalization_status": "VALID_REALIZED_R",
        }
        validate_current_schema(case)
        cases.append(case)
    cases.sort(key=lambda row: (row["terminal_timestamp"], row["candidate_identity"]))

    canonical = {
        "phase": "4.2.41.88C-current-contract",
        "purpose": "CANONICAL_VALID_CLOSED_REALIZED_R_CASES",
        "candidate_fixture_sha256": hashlib.sha256(candidates_path.read_bytes()).hexdigest(),
        "forward_outcome_artifact_sha256": hashlib.sha256(forward_path.read_bytes()).hexdigest(),
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "risk_semantic_model": RISK_SEMANTIC_MODEL,
        "runner_policy": RUNNER_POLICY,
        "outcome_policy_id": BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        "statistics_contract_id": BROOKS_HP_STATISTICS_CONTRACT_ID,
        "case_count": len(cases),
        "cases": cases,
    }
    canonical_output.parent.mkdir(parents=True, exist_ok=True)
    canonical_output.write_text(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    case_objects = [
        (dt(row["terminal_timestamp"]), historical_case(row, index))
        for index, row in enumerate(cases, 1)
    ]
    rows = []
    for number, source in enumerate(
        sorted(
            candidates,
            key=lambda row: (
                row["candidate_timestamp"],
                row["symbol"],
                row["timeframe"],
            ),
        ),
        1,
    ):
        candidate = reconstruct(source)
        now = dt(source["candidate_timestamp"])
        prior = tuple(case for terminal, case in case_objects if terminal < now)
        assessment = HistoricalProbabilityEngine(prior).assess(candidate)
        rows.append(
            {
                "candidate_no": number,
                "candidate_identity": source["candidate_identity"],
                "candidate_timestamp": source["candidate_timestamp"],
                "symbol": source["symbol"],
                "timeframe": source["timeframe"],
                "direction": source["direction"],
                "setup_type": source["setup_type"],
                "available_compatible_closed_count": (assessment.compatible_case_count),
                "required_sample_size": assessment.required_sample_size,
                "selected_scope": assessment.scope,
                "calibrated": assessment.calibrated,
                "readiness_state": assessment.readiness_state,
                "outcome_policy_id": assessment.outcome_policy_id,
                "statistics_contract_id": assessment.statistics_contract_id,
                "sample_mean_r": assessment.mean_realized_r,
                "sample_median_r": assessment.median_realized_r,
                "bootstrap_t_lower95": assessment.ci95_lower_r,
                "bootstrap_t_upper95": assessment.ci95_upper_r,
                "positive_fraction": assessment.positive_fraction,
                "wilson_lower": assessment.positive_fraction_wilson_lower,
                "history_case_set_hash": assessment.history_case_set_hash,
                "current_plan_rr": source["current_plan_rr"],
                "v6_planned_reward_r": source["v6_planned_reward_r"],
            }
        )

    report = {
        "phase": "4.2.41.88C-current-contract",
        "candidate_fixture_sha256": hashlib.sha256(candidates_path.read_bytes()).hexdigest(),
        "raw_forward_artifact_sha256": hashlib.sha256(forward_path.read_bytes()).hexdigest(),
        "canonical_closed_fixture_sha256": hashlib.sha256(
            canonical_output.read_bytes()
        ).hexdigest(),
        "rows": rows,
        "decision_summary": {
            state: sum(row["readiness_state"] == state for row in rows)
            for state in sorted({row["readiness_state"] for row in rows})
        },
        "admission_guards": {
            "realized_r_current_contract": True,
            "terminal_strictly_before_candidate": True,
            "all_selected_scope_cases_used": True,
            "wilson_controls_admission": False,
            "legacy_similarity_controls_admission": False,
        },
    }
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("CASES", len(cases), "ROWS", len(rows))
    print("REPORT_SHA256", hashlib.sha256(report_output.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--forward", type=Path, required=True)
    parser.add_argument("--canonical-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    main(
        candidates_path=args.candidates,
        forward_path=args.forward,
        canonical_output=args.canonical_output,
        report_output=args.report_output,
    )
