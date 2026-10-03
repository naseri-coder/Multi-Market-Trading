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

async def exact14_rows(fixture, *, allow_network):
    if not allow_network:
        return []
    from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider

    document = json.loads(fixture.read_text(encoding="utf-8"))
    rows = []
    engine = BrooksTrilogyFullCoreEngine(
        policy=BrooksFullCorePolicy(enable_trade_decisions=True)
    )
    for historical in document["candidates"]:
        clock = dt(historical["timestamp"])
        provider = BinanceFuturesMarketDataProvider(clock=lambda: clock)
        try:
            snapshot = await provider.get_snapshot(
                symbol=historical["symbol"],
                timeframe=historical["timeframe"],
                limit=120,
                market_type="futures",
            )
            snapshot = dataclasses.replace(
                snapshot,
                captured_at=snapshot.candles[-1].close_time,
                source="CURRENT_PARITY_EXPLICIT_NETWORK",
            )
            result = await engine.evaluate(snapshot)
            candidate = candidate_from_engine_result(
                result, snapshot, "CURRENT_PARITY_EXACT14"
            )
            row = current_parity(candidate)
            row["historical_identity"] = historical["identity_sha256"]
            row["current_snapshot_hash"] = candidate.market_snapshot_hash
            rows.append(row)
        finally:
            await provider.aclose()
    return rows


async def frozen_rows(fixture, source):
    document = json.loads(fixture.read_text(encoding="utf-8"))
    rows = []
    for historical in document["candidates"]:
        candidate = await regenerate_from_snapshot(
            historical, source_signal_id=source
        )
        row = current_parity(candidate)
        row["historical_identity"] = historical["identity_sha256"]
        row["current_snapshot_hash"] = candidate.market_snapshot_hash
        rows.append(row)
    return rows


async def main(*, exact14, holdout, bootstrap, output, allow_network):
    exact = await exact14_rows(exact14, allow_network=allow_network)
    hrows = await frozen_rows(holdout, "CURRENT_PARITY_HOLDOUT")
    brows = await frozen_rows(bootstrap, "CURRENT_PARITY_BOOTSTRAP")
    groups = {"exact14": exact, "holdout67": hrows, "bootstrap86": brows}
    summary = {
        name: [sum(row["pass"] for row in rows), len(rows)]
        for name, rows in groups.items()
    }
    report = {
        "phase": "4.2.41.88D-R1-current-contract",
        "assertion_contract": "CURRENT_PLAN_ALLOCATION_INVARIANTS",
        **groups,
        "summary": summary,
        "exact14_network_skipped": not allow_network,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SUMMARY", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exact14", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(
        exact14=args.exact14,
        holdout=args.holdout,
        bootstrap=args.bootstrap,
        output=args.output,
        allow_network=args.allow_network,
    ))
