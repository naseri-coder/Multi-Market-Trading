from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.modules.ai_council.service import AICouncilService
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.risk_engine.service import RiskEngineService
from app.modules.signal_automation.entities import BrooksRuleEvidence
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.cold_start_integration import (
    evaluate_offline_cold_start_integration,
)
from app.modules.signal_intelligence.probability import HistoricalProbabilityEngine
from app.modules.signal_intelligence.service import SignalIntelligenceService
from research_layer.current_risk_contract import read_current_risk

ROOT = Path(__file__).resolve().parents[1]


def dt(value):
    return datetime.fromisoformat(value)


def dec(value):
    return Decimal(str(value))


def snapshot_from_row(row):
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
    return MarketSnapshot(
        raw["exchange"],
        raw["market_type"],
        raw["symbol"],
        raw["timeframe"],
        candles,
        dt(raw["captured_at"]),
        raw["source"],
    )


def candidate_from_engine_result(result, snapshot, source_signal_id):
    fields = {
        field.name: getattr(result, field.name)
        for field in dataclasses.fields(PaperSignalCandidate)
        if hasattr(result, field.name)
    }
    fields.update(
        source_signal_id=source_signal_id,
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
    return PaperSignalCandidate(**fields)


def geometry_valid(candidate):
    if candidate.direction == "LONG":
        return (
            candidate.stop_loss < candidate.entry_price
            and all(target > candidate.entry_price for target in candidate.targets)
        )
    return (
        candidate.stop_loss > candidate.entry_price
        and all(target < candidate.entry_price for target in candidate.targets)
    )


def current_parity(candidate, risk=None):
    risk = risk if risk is not None else RiskEngineService().evaluate(candidate)
    view = read_current_risk(candidate, assessment=risk, need_trade_plan=True)
    reward = view["plan_breakdown"]
    contribution_sum = sum(
        (dec(row["weighted_target_r"]) for row in reward["target_contributions"]),
        Decimal("0"),
    ) + dec(reward["weighted_runner_r"])
    allocation_sum = sum(
        (dec(row["allocation_fraction"]) for row in reward["target_contributions"]),
        Decimal("0"),
    ) + dec(reward["runner_fraction"])
    residual = allocation_sum - Decimal("1")
    checks = dict(view["invariants"])
    passed = (
        all(checks.values())
        and contribution_sum == view["plan_rr"]
        and residual == 0
    )
    return {
        "current_plan_rr": str(view["plan_rr"]),
        "v6_planned_reward_r": str(view["plan_rr"]),
        "contribution_sum_r": str(contribution_sum),
        "allocation_residual_r": str(residual),
        "checks": checks,
        "pass": passed,
        "management_plan": view["trade_management_plan"].to_metadata(),
        "risk_semantic_model": reward["mode"],
        "runner_policy": reward["runner_policy"],
    }


async def regenerate_from_snapshot(row, *, source_signal_id):
    snapshot = snapshot_from_row(row)
    engine = BrooksTrilogyFullCoreEngine(
        policy=BrooksFullCorePolicy(enable_trade_decisions=True)
    )
    result = await engine.evaluate(snapshot)
    if result.decision not in {"LONG", "SHORT"}:
        raise RuntimeError("current engine produced no tradeable decision")
    candidate = candidate_from_engine_result(result, snapshot, source_signal_id)
    return candidate

async def regenerate_exact14(row, *, allow_network):
    if not allow_network:
        raise RuntimeError("exact14 requires explicit --allow-network because the historical fixture has no snapshot")
    from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider

    clock = dt(row["timestamp"])
    provider = BinanceFuturesMarketDataProvider(clock=lambda: clock)
    try:
        snapshot = await provider.get_snapshot(
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            limit=120,
            market_type="futures",
        )
        snapshot = dataclasses.replace(
            snapshot,
            captured_at=snapshot.candles[-1].close_time,
            source="PHASE84_EXPLICIT_NETWORK_REPLAY",
        )
        engine = BrooksTrilogyFullCoreEngine(
            policy=BrooksFullCorePolicy(enable_trade_decisions=True)
        )
        result = await engine.evaluate(snapshot)
        if result.decision not in {"LONG", "SHORT"}:
            raise RuntimeError("current engine produced no tradeable decision")
        return candidate_from_engine_result(result, snapshot, "PHASE84_CURRENT_REPLAY")
    finally:
        await provider.aclose()


async def validate_one(row, *, allow_network):
    candidate = await regenerate_exact14(row, allow_network=allow_network)
    council = AICouncilService().evaluate(candidate)
    risk = RiskEngineService().evaluate(candidate)
    probability = HistoricalProbabilityEngine(()).assess(candidate)
    quality = SignalIntelligenceService().evaluate(
        candidate,
        ai_score=council.final_score,
        risk_score=risk.risk_score,
        council_confidence=council.confidence,
        probability=probability,
    )
    gate = SignalGateService().evaluate(quality)
    parity = current_parity(candidate, risk)
    cold = evaluate_offline_cold_start_integration(
        candidate=candidate,
        probability=probability,
        ai_score=council.final_score,
        risk_score=risk.risk_score,
        council_confidence=council.confidence,
        ai_approved=council.approved,
        risk_approved=risk.approved,
        geometry_valid=geometry_valid(candidate),
        structural_valid=not bool(candidate.failed_rules),
        absolute_brooks_veto=False,
        closed_native_compatible_count=0,
    )
    metadata = dict(quality.metadata)
    return {
        "candidate_no": row["candidate_no"],
        "historical_identity": row["identity_sha256"],
        "current_snapshot_hash": candidate.market_snapshot_hash,
        "symbol": candidate.symbol,
        "timeframe": candidate.timeframe,
        "direction": candidate.direction,
        "setup_type": candidate.setup_type,
        "timestamp": row["timestamp"],
        "current_configuration_version": candidate.configuration_version,
        "hp_outcome_policy_id": probability.outcome_policy_id,
        "hp_statistics_contract_id": probability.statistics_contract_id,
        "hp_readiness_state": probability.readiness_state,
        "compatible_case_count": probability.compatible_case_count,
        "required_sample_size": probability.required_sample_size,
        "qualitative": {
            key: metadata.get(key)
            for key in (
                "structure_quality", "context_quality", "entry_quality",
                "risk_quality", "brooks_certainty", "ai_score",
                "council_confidence", "evidence_conflicts",
            )
        },
        "current_plan_parity": parity,
        "ai_approved": council.approved,
        "risk_approved": risk.approved,
        "raw_final_gate_approved": gate.approved,
        "raw_final_failures": list(gate.metadata.get("failures", ())),
        "cold_start_pass": cold.cold_start.approved,
        "cold_start_reason": cold.cold_start.reason,
        "admission_metadata": cold.admission_metadata,
    }


async def main(*, fixture, output, allow_network):
    document = json.loads(fixture.read_text(encoding="utf-8"))
    results = [
        await validate_one(row, allow_network=allow_network)
        for row in document["candidates"]
    ]
    report = {
        "phase": "4.2.41.84-current-contract",
        "historical_fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "historical_fixture_role": "PROVENANCE_ONLY",
        "results": results,
        "summary": {
            "count": len(results),
            "parity_pass": sum(row["current_plan_parity"]["pass"] for row in results),
            "cold_start_pass": sum(row["cold_start_pass"] for row in results),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SUMMARY", json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(fixture=args.fixture, output=args.output, allow_network=args.allow_network))
