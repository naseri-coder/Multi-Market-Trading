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
from app.modules.signal_intelligence.cold_start_integration import (
    evaluate_offline_cold_start_integration,
)
from app.modules.signal_intelligence.probability import HistoricalProbabilityEngine

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
        return candidate.stop_loss < candidate.entry_price and all(
            target > candidate.entry_price for target in candidate.targets
        )
    return candidate.stop_loss > candidate.entry_price and all(
        target < candidate.entry_price for target in candidate.targets
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
    passed = all(checks.values()) and contribution_sum == view["plan_rr"] and residual == 0
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
    engine = BrooksTrilogyFullCoreEngine(policy=BrooksFullCorePolicy(enable_trade_decisions=True))
    result = await engine.evaluate(snapshot)
    if result.decision not in {"LONG", "SHORT"}:
        raise RuntimeError("current engine produced no tradeable decision")
    candidate = candidate_from_engine_result(result, snapshot, source_signal_id)
    return candidate


async def main(*, fixture, output):
    document = json.loads(fixture.read_text(encoding="utf-8"))
    rows = []
    for number, historical in enumerate(document["candidates"], 1):
        candidate = await regenerate_from_snapshot(
            historical, source_signal_id="PHASE85_CURRENT_REGENERATED"
        )
        council = AICouncilService().evaluate(candidate)
        risk = RiskEngineService().evaluate(candidate)
        probability = HistoricalProbabilityEngine(()).assess(candidate)
        result = evaluate_offline_cold_start_integration(
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
        parity = current_parity(candidate, risk)
        rows.append(
            {
                "candidate_no": number,
                "historical_identity": historical["identity_sha256"],
                "historical_candidate_timestamp": historical["candidate_timestamp"],
                "current_snapshot_hash": candidate.market_snapshot_hash,
                "current_configuration_version": candidate.configuration_version,
                "symbol": candidate.symbol,
                "timeframe": candidate.timeframe,
                "direction": candidate.direction,
                "setup_type": candidate.setup_type,
                "hp_outcome_policy_id": probability.outcome_policy_id,
                "hp_statistics_contract_id": probability.statistics_contract_id,
                "hp_readiness_state": probability.readiness_state,
                "compatible_case_count": probability.compatible_case_count,
                "required_sample_size": probability.required_sample_size,
                "raw_final_failures": list(result.final_gate.metadata.get("failures", ())),
                "cold_start_pass": result.cold_start.approved,
                "cold_start_reason": result.cold_start.reason,
                "effective_approved": result.effective_approved,
                "admission_metadata": result.admission_metadata,
                "current_plan_parity": parity,
            }
        )
    report = {
        "phase": "4.2.41.85-current-contract",
        "historical_fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "historical_fixture_role": "IMMUTABLE_PROVENANCE_ONLY",
        "candidate_count": len(rows),
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("COUNT", len(rows), "PARITY", sum(r["current_plan_parity"]["pass"] for r in rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(fixture=args.fixture, output=args.output))
