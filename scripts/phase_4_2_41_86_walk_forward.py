"""Causal walk-forward diagnostics over the current realized-R probability contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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
from app.modules.risk_engine.service import RiskEngineService
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BrooksRuleEvidence,
)
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
)
from research_layer.current_risk_contract import read_current_risk


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
        "PHASE86_WALK_FORWARD_CURRENT",
        row["symbol"],
        row["timeframe"],
        row["direction"],
        dec(row["entry"]),
        dec(row["stop"]),
        tuple(dec(value) for value in row["targets"]),
        row["exchange"],
        row["market_type"],
        row["setup_type"],
        row["snapshot_id"],
        row["identity_sha256"],
        row["engine_version"],
        row["rule_set_version"],
        row["configuration_version"],
        tuple(row["reasoning"]),
        tuple(row["rule_ids"]),
        tuple(row["failed_rules"]),
        evidence,
        "NO_PUBLICATION",
        snapshot,
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


def case_fingerprint(row):
    material = {
        "candidate_identity": row["candidate_identity"],
        "current_plan_rr": row["current_plan_rr"],
        "management_plan": row["management_plan"],
        "realized_r": row["realized_r"],
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def historical_case(row, candidate, signal_id, outcome):
    return HistoricalCase(
        signal_id=signal_id,
        setup_type=candidate.setup_type or "UNKNOWN",
        timeframe=candidate.timeframe,
        direction=candidate.direction,
        structure_quality=0.0,
        context_quality=0.0,
        entry_quality=0.0,
        risk_feature=float(dec(row["current_plan_rr"])),
        outcome=outcome,
        rule_ids=tuple(candidate.rule_ids),
        semantic_cohort_id=candidate.semantic_cohort_id,
        generation_mode="RESEARCH",
        economic_opportunity_id=row["candidate_identity"],
        symbol=candidate.symbol,
        realized_r=float(dec(row["realized_r"])),
        payoff_input_fingerprint=case_fingerprint(row),
        outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    )


def run(label, candidate_rows, stream):
    rows = []
    ordered = sorted(
        candidate_rows,
        key=lambda row: (
            row["candidate_timestamp"],
            row["symbol"],
            row["timeframe"],
        ),
    )
    for number, source in enumerate(ordered, 1):
        candidate = reconstruct(source)
        risk = RiskEngineService().evaluate(candidate)
        view = read_current_risk(candidate, assessment=risk)
        if dec(source["current_plan_rr"]) != view["plan_rr"]:
            raise RuntimeError("CURRENT_PLAN_RR_MISMATCH")
        now = dt(source["candidate_timestamp"])
        prior = tuple(case for terminal, case in stream if terminal < now)
        assessment = HistoricalProbabilityEngine(prior).assess(candidate)
        rows.append(
            {
                "candidate_no": number,
                "identity": source["identity_sha256"],
                "timestamp": source["candidate_timestamp"],
                "symbol": candidate.symbol,
                "timeframe": candidate.timeframe,
                "direction": candidate.direction,
                "setup_type": candidate.setup_type,
                "prior_closed_total": len(prior),
                "compatible_case_count": assessment.compatible_case_count,
                "required_sample_size": assessment.required_sample_size,
                "scope": assessment.scope,
                "calibrated": assessment.calibrated,
                "readiness_state": assessment.readiness_state,
                "outcome_policy_id": assessment.outcome_policy_id,
                "statistics_contract_id": assessment.statistics_contract_id,
                "probability": assessment.probability,
                "empirical_win_rate": assessment.empirical_win_rate,
                "wilson_lower": assessment.lower_bound,
                "wilson_upper": assessment.upper_bound,
                "current_plan_rr": str(view["plan_rr"]),
                "v6_planned_reward_r": str(view["plan_rr"]),
                "mean_realized_r": assessment.mean_realized_r,
                "ci95_lower_r": assessment.ci95_lower_r,
                "ci95_upper_r": assessment.ci95_upper_r,
            }
        )
    print(
        label,
        "READY",
        sum(row["calibrated"] for row in rows),
        "/",
        len(rows),
        "SCOPES",
        dict(Counter((row["scope"], row["required_sample_size"]) for row in rows)),
    )
    return rows


def main(*, candidates_path, closed_path, output_path):
    candidates_doc = json.loads(candidates_path.read_text(encoding="utf-8"))
    closed_doc = json.loads(closed_path.read_text(encoding="utf-8"))
    candidate_by_id = {
        row["identity_sha256"]: reconstruct(row) for row in candidates_doc["candidates"]
    }
    current_stream = []
    economic_stream = []
    for index, row in enumerate(closed_doc["cases"], 1):
        candidate = candidate_by_id[row["candidate_identity"]]
        terminal = dt(row["terminal_timestamp"])
        if row["current_hp_binary_outcome"] is not None:
            current_stream.append(
                (
                    terminal,
                    historical_case(row, candidate, index, int(row["current_hp_binary_outcome"])),
                )
            )
        if row["economic_sign_binary_outcome"] is not None:
            economic_stream.append(
                (
                    terminal,
                    historical_case(
                        row,
                        candidate,
                        1000 + index,
                        int(row["economic_sign_binary_outcome"]),
                    ),
                )
            )
    current = run(
        "CURRENT_EVENT_TELEMETRY",
        candidates_doc["candidates"],
        current_stream,
    )
    economic = run(
        "ECONOMIC_R_SIGN_DIAGNOSTIC",
        candidates_doc["candidates"],
        economic_stream,
    )
    payload = {
        "phase": "4.2.41.86-current-contract",
        "bootstrap_fixture_sha256": hashlib.sha256(closed_path.read_bytes()).hexdigest(),
        "current_repository_event_semantics": current,
        "economic_r_sign_diagnostic": economic,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("ARTIFACT", output_path, hashlib.sha256(output_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--closed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(
        candidates_path=args.candidates,
        closed_path=args.closed,
        output_path=args.output,
    )
