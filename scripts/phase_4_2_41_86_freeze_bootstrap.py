"""Freeze closed bootstrap cases from current-contract candidates and explicit outcomes."""

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
from app.modules.signal_automation.entities import BrooksRuleEvidence
from research_layer.current_risk_contract import read_current_risk


def dt(value):
    return datetime.fromisoformat(value)


def dec(value):
    return Decimal(str(value))


def reconstruct(row):
    raw = row["snapshot"]
    candles = tuple(
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
    )
    snapshot = MarketSnapshot(
        raw["exchange"],
        raw["market_type"],
        raw["symbol"],
        raw["timeframe"],
        candles,
        dt(raw["captured_at"]),
        raw["source"],
    )
    evidence = tuple(
        BrooksRuleEvidence(
            rule_id=item["rule_id"],
            status=item["status"],
            source_pages=tuple(item["source_pages"]),
            evidence=tuple(tuple(value) for value in item["evidence"]),
            failed_conditions=tuple(item["failed_conditions"]),
            confidence_components=tuple(
                tuple(value) for value in item["confidence_components"]
            ),
        )
        for item in row["rule_evidence"]
    )
    return PaperSignalCandidate(
        source_signal_id="PHASE86_FREEZE_CURRENT",
        symbol=row["symbol"],
        timeframe=row["timeframe"],
        direction=row["direction"],
        entry_price=dec(row["entry"]),
        stop_loss=dec(row["stop"]),
        targets=tuple(dec(value) for value in row["targets"]),
        exchange=row["exchange"],
        market_type=row["market_type"],
        setup_type=row["setup_type"],
        market_snapshot_id=row["snapshot_id"],
        market_snapshot_hash=row["identity_sha256"],
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
            TargetSourceIdentity.from_metadata(item)
            for item in row["target_source_identities"]
        ),
        stop_source_identity=(
            None
            if row.get("stop_source_identity") is None
            else StopSourceIdentity.from_metadata(row["stop_source_identity"])
        ),
        target_plan_lifecycle=TargetPlanLifecycle.from_metadata(
            row["target_plan_lifecycle"]
        ),
        reversal_outcome_context=(
            None
            if row.get("reversal_outcome_context") is None
            else ReversalOutcomeContext.from_metadata(
                row["reversal_outcome_context"]
            )
        ),
        semantic_cohort_id=row.get("semantic_cohort_id"),
    )


def main(*, candidates_path, outcomes_path, output_path):
    candidates_doc = json.loads(candidates_path.read_text(encoding="utf-8"))
    outcomes_doc = json.loads(outcomes_path.read_text(encoding="utf-8"))
    outcomes = {row["identity"]: row for row in outcomes_doc["rows"]}
    rows = []
    for source in candidates_doc["candidates"]:
        outcome = outcomes[source["identity_sha256"]]
        if outcome["terminal_status"] in {"NEVER_ENTERED", "AMBIGUOUS", "OPEN"}:
            continue
        candidate = reconstruct(source)
        risk = RiskEngineService().evaluate(candidate)
        view = read_current_risk(candidate, assessment=risk, need_trade_plan=True)
        plan = view["trade_management_plan"]
        if plan is None or not all(view["invariants"].values()):
            raise RuntimeError("CURRENT_RISK_PLAN_INVALID")
        if dec(source["current_plan_rr"]) != view["plan_rr"]:
            raise RuntimeError("CURRENT_PLAN_RR_MISMATCH")
        if dec(source["v6_planned_reward_r"]) != view["plan_rr"]:
            raise RuntimeError("V6_COMPATIBILITY_ALIAS_MISMATCH")
        if source["management_plan"] != plan.to_metadata():
            raise RuntimeError("CURRENT_MANAGEMENT_PLAN_MISMATCH")

        terminal = outcome["terminal_status"]
        realized_r = dec(outcome["realized_r"])
        event_binary = (
            1
            if terminal == "TARGET_STAGED_COMPLETION"
            else (None if terminal == "RUNNER_REVERSAL" else 0)
        )
        economic_binary = 1 if realized_r > 0 else (0 if realized_r < 0 else None)
        rows.append(
            {
                "candidate_identity": source["identity_sha256"],
                "snapshot_hash": source["identity_sha256"],
                "snapshot_id": source["snapshot_id"],
                "candidate_timestamp": source["candidate_timestamp"],
                "symbol": source["symbol"],
                "timeframe": source["timeframe"],
                "direction": source["direction"],
                "setup_type": source["setup_type"],
                "entry": source["entry"],
                "stop": source["stop"],
                "targets": source["targets"],
                "management_plan": plan.to_metadata(),
                "current_plan_rr": str(view["plan_rr"]),
                "v6_planned_reward_r": str(view["plan_rr"]),
                "risk_semantic_breakdown": view["breakdown"],
                "artifact_schema_version": source["artifact_schema_version"],
                "risk_semantic_model": source["risk_semantic_model"],
                "runner_policy": source["runner_policy"],
                "target_source_identities": source["target_source_identities"],
                "stop_source_identity": source["stop_source_identity"],
                "target_plan_lifecycle": source["target_plan_lifecycle"],
                "reversal_outcome_context": source["reversal_outcome_context"],
                "semantic_cohort_id": source.get("semantic_cohort_id"),
                "entry_activated": outcome["entry_activated"],
                "entry_activated_at": outcome["entry_activated_at"],
                "terminal_event": terminal,
                "terminal_timestamp": outcome["terminal_time"],
                "realized_r": outcome["realized_r"],
                "current_hp_binary_outcome": event_binary,
                "economic_sign_binary_outcome": economic_binary,
                "engine_version": source["engine_version"],
                "rule_set_version": source["rule_set_version"],
                "configuration_version": source["configuration_version"],
                "management_version": source["management_version"],
                "exchange": source["exchange"],
                "market_type": source["market_type"],
                "rule_ids": source["rule_ids"],
                "rule_evidence": source["rule_evidence"],
                "snapshot": source["snapshot"],
                "mfe_r": outcome["mfe_r"],
                "mae_r": outcome["mae_r"],
                "stop_updates": outcome["stop_updates"],
                "targets_hit": outcome["targets_hit"],
            }
        )
    rows.sort(
        key=lambda row: (
            row["candidate_timestamp"],
            row["symbol"],
            row["timeframe"],
        )
    )
    payload = {
        "phase": "4.2.41.86-current-contract",
        "purpose": "FROZEN_CLOSED_BOOTSTRAP_DATASET",
        "source_candidate_fixture_sha256": hashlib.sha256(
            candidates_path.read_bytes()
        ).hexdigest(),
        "forward_outcome_artifact_sha256": hashlib.sha256(
            outcomes_path.read_bytes()
        ).hexdigest(),
        "case_count": len(rows),
        "non_futures_cases": sum(row["market_type"] != "futures" for row in rows),
        "cases": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("CASES", len(rows), "SHA256", hashlib.sha256(output_path.read_bytes()).hexdigest())
    print("TERMINALS", dict(Counter(row["terminal_event"] for row in rows)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(
        candidates_path=args.candidates,
        outcomes_path=args.outcomes,
        output_path=args.output,
    )
