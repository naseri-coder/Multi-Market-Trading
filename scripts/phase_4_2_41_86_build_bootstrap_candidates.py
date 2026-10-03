"""Build a disjoint current-contract bootstrap candidate set with explicit network access."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.modules.ai_council.service import AICouncilService
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.operations.trade_management import POLICY_VERSION as MANAGEMENT_VERSION
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.risk_engine.service import RiskEngineService
from app.modules.signal_intelligence.probability import HistoricalProbabilityEngine

from research_layer.current_risk_contract import read_current_risk

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT")
START = datetime(2026, 9, 11, 0, 0, 5, tzinfo=UTC)
END = datetime(2026, 9, 11, 23, 59, 59, tzinfo=UTC)


def geometry(row):
    return (
        row["symbol"],
        row["timeframe"],
        row["direction"],
        row["entry"],
        row["stop"],
        tuple(row["targets"]),
    )


def evidence_metadata(item):
    return {
        "rule_id": item.rule_id,
        "status": item.status,
        "source_pages": list(item.source_pages),
        "evidence": [list(value) for value in item.evidence],
        "failed_conditions": list(item.failed_conditions),
        "confidence_components": [list(value) for value in item.confidence_components],
    }


def serialize_candidate(candidate, snapshot, clock, council, risk, view):
    plan = view["trade_management_plan"]
    if plan is None or not all(view["invariants"].values()):
        raise RuntimeError("CURRENT_RISK_PLAN_INVALID")
    lifecycle = candidate.target_plan_lifecycle
    if lifecycle is None:
        raise RuntimeError("CURRENT_TARGET_PLAN_LIFECYCLE_MISSING")
    return {
        "identity_sha256": candidate.market_snapshot_hash,
        "snapshot_id": candidate.market_snapshot_id,
        "candidate_timestamp": clock.isoformat(),
        "snapshot_captured_at": snapshot.captured_at.isoformat(),
        "symbol": candidate.symbol,
        "timeframe": candidate.timeframe,
        "direction": candidate.direction,
        "setup_type": candidate.setup_type,
        "entry": str(candidate.entry_price),
        "stop": str(candidate.stop_loss),
        "targets": [str(value) for value in candidate.targets],
        "engine_version": candidate.engine_version,
        "rule_set_version": candidate.rule_set_version,
        "management_version": MANAGEMENT_VERSION,
        "configuration_version": candidate.configuration_version,
        "exchange": candidate.exchange,
        "market_type": candidate.market_type,
        "reasoning": list(candidate.reasoning),
        "rule_ids": list(candidate.rule_ids),
        "failed_rules": list(candidate.failed_rules),
        "rule_evidence": [evidence_metadata(item) for item in candidate.rule_evidence],
        "target_source_identities": [
            item.to_metadata() for item in candidate.target_source_identities
        ],
        "stop_source_identity": (
            None
            if candidate.stop_source_identity is None
            else candidate.stop_source_identity.to_metadata()
        ),
        "target_plan_lifecycle": lifecycle.to_metadata(),
        "reversal_outcome_context": (
            None
            if candidate.reversal_outcome_context is None
            else candidate.reversal_outcome_context.to_metadata()
        ),
        "semantic_cohort_id": candidate.semantic_cohort_id,
        "current_plan_rr": str(view["plan_rr"]),
        "v6_planned_reward_r": str(view["plan_rr"]),
        "risk_semantic_breakdown": view["breakdown"],
        "management_plan": plan.to_metadata(),
        "artifact_schema_version": "brooks-research-current-risk-v1",
        "risk_semantic_model": view["plan_breakdown"]["mode"],
        "runner_policy": view["plan_breakdown"]["runner_policy"],
        "current_plan_invariants": view["invariants"],
        "snapshot": {
            "exchange": snapshot.exchange,
            "market_type": snapshot.market_type,
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "captured_at": snapshot.captured_at.isoformat(),
            "source": snapshot.source,
            "candles": [
                {
                    "open_time": bar.open_time.isoformat(),
                    "close_time": bar.close_time.isoformat(),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(bar.volume),
                }
                for bar in snapshot.candles
            ],
        },
        "upstream": {
            "ai_approved": council.approved,
            "ai_score": council.final_score,
            "council_confidence": council.confidence,
            "risk_approved": risk.approved,
            "risk_score": risk.risk_score,
        },
    }


async def main(*, phase84, phase85, output, allow_network):
    if not allow_network:
        raise RuntimeError("candidate build requires explicit --allow-network")
    original = json.loads(phase84.read_text(encoding="utf-8"))
    holdout = json.loads(phase85.read_text(encoding="utf-8"))
    original_hashes = {row["identity_sha256"] for row in original["candidates"]}
    original_times = {row["timestamp"] for row in original["candidates"]}
    original_geometry = {geometry(row) for row in original["candidates"]}
    holdout_hashes = {row["identity_sha256"] for row in holdout["candidates"]}
    holdout_times = {row["candidate_timestamp"] for row in holdout["candidates"]}
    holdout_geometry = {geometry(row) for row in holdout["candidates"]}

    policy = BrooksFullCorePolicy(enable_trade_decisions=True)
    engine = BrooksTrilogyFullCoreEngine(policy=policy)
    semaphore = asyncio.Semaphore(6)
    points = []
    cursor = START
    while cursor <= END:
        points.extend((symbol, "15m", cursor) for symbol in SYMBOLS)
        if cursor.minute == 0:
            points.extend((symbol, "1h", cursor) for symbol in SYMBOLS)
        cursor += timedelta(minutes=15)

    async def one(symbol, timeframe, clock):
        async with semaphore:
            provider = BinanceFuturesMarketDataProvider(clock=lambda clock=clock: clock)
            try:
                snapshot = await provider.get_snapshot(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=120,
                    market_type="futures",
                )
                snapshot = dataclasses.replace(
                    snapshot,
                    captured_at=snapshot.candles[-1].close_time,
                    source="PHASE86_BOOTSTRAP_CURRENT_REPLAY",
                )
                result = await engine.evaluate(snapshot)
                if result.decision not in {"LONG", "SHORT"}:
                    return None
                fields = {
                    field.name: getattr(result, field.name)
                    for field in dataclasses.fields(PaperSignalCandidate)
                    if hasattr(result, field.name)
                }
                fields.update(
                    source_signal_id="PHASE86_BOOTSTRAP_CURRENT",
                    symbol=snapshot.symbol,
                    timeframe=snapshot.timeframe,
                    direction=result.decision,
                    exchange=snapshot.exchange,
                    market_type=snapshot.market_type,
                    market_snapshot_id=snapshot.snapshot_id,
                    market_snapshot_hash=snapshot.snapshot_hash,
                    chart_path="NO_PUBLICATION",
                    snapshot=snapshot,
                )
                candidate = PaperSignalCandidate(**fields)
                council = AICouncilService().evaluate(candidate)
                risk = RiskEngineService().evaluate(candidate)
                if not council.approved or not risk.approved:
                    return None
                view = read_current_risk(candidate, assessment=risk, need_trade_plan=True)
                current_geometry = (
                    candidate.symbol,
                    candidate.timeframe,
                    candidate.direction,
                    str(candidate.entry_price),
                    str(candidate.stop_loss),
                    tuple(str(value) for value in candidate.targets),
                )
                if (
                    candidate.market_snapshot_hash in original_hashes
                    or clock.isoformat() in original_times
                    or current_geometry in original_geometry
                    or candidate.market_snapshot_hash in holdout_hashes
                    or clock.isoformat() in holdout_times
                    or current_geometry in holdout_geometry
                ):
                    raise RuntimeError("FORENSIC_DATASET_OVERLAP")
                probability = HistoricalProbabilityEngine(()).assess(candidate)
                row = serialize_candidate(candidate, snapshot, clock, council, risk, view)
                row["empty_history_diagnostic"] = {
                    "hp_outcome_policy_id": probability.outcome_policy_id,
                    "hp_statistics_contract_id": probability.statistics_contract_id,
                    "hp_readiness_state": probability.readiness_state,
                    "compatible_case_count": probability.compatible_case_count,
                    "required_sample_size": probability.required_sample_size,
                }
                return row
            finally:
                await provider.aclose()

    tasks = [asyncio.create_task(one(*point)) for point in points]
    results = []
    for task in asyncio.as_completed(tasks):
        row = await task
        if row is not None:
            results.append(row)
    results.sort(key=lambda row: (row["candidate_timestamp"], row["symbol"], row["timeframe"]))
    unique = []
    seen = set()
    for row in results:
        if row["identity_sha256"] in seen:
            continue
        seen.add(row["identity_sha256"])
        unique.append(row)

    payload = {
        "phase": "4.2.41.86-current-contract",
        "purpose": "CURRENT_BOOTSTRAP_CANDIDATES_BEFORE_OUTCOME_REPLAY",
        "source_window_utc": [START.isoformat(), END.isoformat()],
        "candidate_count": len(unique),
        "excluded_phase84_fixture_sha256": hashlib.sha256(phase84.read_bytes()).hexdigest(),
        "excluded_phase85_fixture_sha256": hashlib.sha256(phase85.read_bytes()).hexdigest(),
        "forensic_dataset_exclusion": {
            "phase84_snapshot_hash_overlap": 0,
            "phase84_timestamp_overlap": 0,
            "phase84_exact_geometry_overlap": 0,
            "phase85_snapshot_hash_overlap": 0,
            "phase85_timestamp_overlap": 0,
            "phase85_exact_geometry_overlap": 0,
        },
        "outcomes_observed_before_candidate_freeze": False,
        "candidates": unique,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("SURVIVORS", len(unique))
    print("BY_SYMBOL", dict(Counter(row["symbol"] for row in unique)))
    print("BY_TF", dict(Counter(row["timeframe"] for row in unique)))
    print("BY_DIR", dict(Counter(row["direction"] for row in unique)))
    print("SHA256", hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase84", type=Path, required=True)
    parser.add_argument("--phase85", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        main(
            phase84=args.phase84,
            phase85=args.phase85,
            output=args.output,
            allow_network=args.allow_network,
        )
    )
