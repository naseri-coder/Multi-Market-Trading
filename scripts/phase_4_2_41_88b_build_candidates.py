"""Build PHASE88B current-contract candidates with explicit network access."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from app.modules.ai_council.service import AICouncilService
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.operations.trade_management import POLICY_VERSION as MANAGEMENT_VERSION
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.risk_engine.service import RiskEngineService
from research_layer.current_risk_contract import read_current_risk


def evidence_metadata(item):
    return {
        "rule_id": item.rule_id,
        "status": item.status,
        "source_pages": list(item.source_pages),
        "evidence": [list(value) for value in item.evidence],
        "failed_conditions": list(item.failed_conditions),
        "confidence_components": [list(value) for value in item.confidence_components],
    }


def geometry(row):
    return (
        row["symbol"],
        row["timeframe"],
        row["direction"],
        str(row.get("entry", row.get("entry_price"))),
        str(row.get("stop", row.get("initial_stop", row.get("stop_loss")))),
        tuple(str(value) for value in row["targets"]),
    )


def serialize(candidate, snapshot, clock, council, risk, view):
    plan = view["trade_management_plan"]
    if plan is None or not all(view["invariants"].values()):
        raise RuntimeError("CURRENT_RISK_PLAN_INVALID")
    lifecycle = candidate.target_plan_lifecycle
    if lifecycle is None:
        raise RuntimeError("CURRENT_TARGET_PLAN_LIFECYCLE_MISSING")
    return {
        "candidate_identity": candidate.market_snapshot_hash,
        "snapshot_hash": candidate.market_snapshot_hash,
        "snapshot_id": candidate.market_snapshot_id,
        "candidate_timestamp": clock.isoformat(),
        "snapshot_captured_at": snapshot.captured_at.isoformat(),
        "symbol": candidate.symbol,
        "timeframe": candidate.timeframe,
        "direction": candidate.direction,
        "setup_type": candidate.setup_type,
        "engine_version": candidate.engine_version,
        "rule_set_version": candidate.rule_set_version,
        "configuration_version": candidate.configuration_version,
        "exchange": candidate.exchange,
        "market_type": candidate.market_type,
        "management_version": MANAGEMENT_VERSION,
        "entry": str(candidate.entry_price),
        "initial_stop": str(candidate.stop_loss),
        "targets": [str(value) for value in candidate.targets],
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
        "risk_planned_reward_r": str(view["plan_rr"]),
        "section_c_parity": all(view["invariants"].values()),
        "current_plan_invariants": view["invariants"],
        "risk_semantic_breakdown": view["breakdown"],
        "management_plan": plan.to_metadata(),
        "target_exit_fractions": {
            str(number): str(fraction) for number, fraction in plan.target_exit_fractions
        },
        "runner_fraction": str(plan.runner_fraction),
        "breakeven_mode": plan.breakeven_mode,
        "plan_context": plan.context_class,
        "artifact_schema_version": "brooks-research-current-risk-v1",
        "risk_semantic_model": view["plan_breakdown"]["mode"],
        "runner_policy": view["plan_breakdown"]["runner_policy"],
        "ai_result": {
            "approved": bool(council.approved),
            "score": float(council.final_score),
            "confidence": float(council.confidence),
            "summary": council.summary,
        },
        "risk_result": {
            "approved": bool(risk.approved),
            "score": float(risk.risk_score),
            "reasons": list(risk.reasons),
        },
        "reasoning": list(candidate.reasoning),
        "rule_ids": list(candidate.rule_ids),
        "failed_rules": list(candidate.failed_rules),
        "rule_evidence": [evidence_metadata(item) for item in candidate.rule_evidence],
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
    }


async def build(
    *,
    start,
    end,
    symbols,
    prior_ids,
    prior_times,
    prior_geometry,
    source_label,
):
    policy = BrooksFullCorePolicy(enable_trade_decisions=True)
    engine = BrooksTrilogyFullCoreEngine(policy=policy)
    semaphore = asyncio.Semaphore(6)
    stage = Counter()
    points = []
    cursor = start
    while cursor <= end:
        points.extend((symbol, "15m", cursor) for symbol in symbols)
        if cursor.minute == 0:
            points.extend((symbol, "1h", cursor) for symbol in symbols)
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
                    source=source_label,
                )
                result = await engine.evaluate(snapshot)
                stage["scanned"] += 1
                if result.decision not in {"LONG", "SHORT"}:
                    stage["core_no_signal"] += 1
                    return None
                fields = {
                    field.name: getattr(result, field.name)
                    for field in dataclasses.fields(PaperSignalCandidate)
                    if hasattr(result, field.name)
                }
                fields.update(
                    source_signal_id="PHASE88B_CURRENT",
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
                if not council.approved:
                    stage["ai_rejected"] += 1
                    return None
                risk = RiskEngineService().evaluate(candidate)
                if not risk.approved:
                    stage["risk_rejected"] += 1
                    return None
                view = read_current_risk(candidate, assessment=risk, need_trade_plan=True)
                candidate_geometry = (
                    candidate.symbol,
                    candidate.timeframe,
                    candidate.direction,
                    str(candidate.entry_price),
                    str(candidate.stop_loss),
                    tuple(str(value) for value in candidate.targets),
                )
                if (
                    candidate.market_snapshot_hash in prior_ids
                    or clock.isoformat() in prior_times
                    or candidate_geometry in prior_geometry
                ):
                    raise RuntimeError("PRIOR_COHORT_OVERLAP")
                stage["risk_approved"] += 1
                return serialize(candidate, snapshot, clock, council, risk, view)
            finally:
                await provider.aclose()

    results = []
    for task in asyncio.as_completed([asyncio.create_task(one(*point)) for point in points]):
        row = await task
        if row is not None:
            results.append(row)
    results.sort(
        key=lambda row: (
            row["candidate_timestamp"],
            row["symbol"],
            row["timeframe"],
        )
    )
    unique = []
    seen = set()
    for row in results:
        if row["candidate_identity"] in seen:
            continue
        seen.add(row["candidate_identity"])
        unique.append(row)
    return points, stage, unique


async def main(*, output, allow_network):
    if not allow_network:
        raise RuntimeError("88B build requires explicit --allow-network")
    start = datetime.fromisoformat("2026-09-09T00:00:05+00:00")
    end = datetime.fromisoformat("2026-09-09T23:45:05+00:00")
    symbols = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT")
    points, stage, rows = await build(
        start=start,
        end=end,
        symbols=symbols,
        prior_ids=set(),
        prior_times=set(),
        prior_geometry=set(),
        source_label="PHASE88B_CURRENT_CANDIDATE_FREEZE",
    )
    payload = {
        "phase": "4.2.41.88B-current-contract",
        "purpose": "CURRENT_CANDIDATE_UNIVERSE_FROZEN_BEFORE_FORWARD_REPLAY",
        "source_window_utc": [start.isoformat(), end.isoformat()],
        "scan_points": len(points),
        "symbols": list(symbols),
        "stage_counts": dict(stage),
        "candidate_count": len(rows),
        "outcomes_observed_before_candidate_freeze": False,
        "candidates": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("COUNT", len(rows), "PARITY", sum(row["section_c_parity"] for row in rows))
    print("SHA256", hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(output=args.output, allow_network=args.allow_network))
