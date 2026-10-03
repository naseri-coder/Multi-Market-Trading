from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS

from app.modules.brooks_core.engine_contract import (
    ReversalOutcomeContext,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceIdentity,
)
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider, _dt
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.operations.approval_evidence import open_position_fraction
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.trade_management import weighted_close_return
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.risk_engine.service import RiskEngineService
from app.modules.signal_automation.entities import BrooksRuleEvidence

from research_layer.current_risk_contract import read_current_risk

ROOT = Path(__file__).resolve().parents[1]
D = Decimal


def dt(s):
    return datetime.fromisoformat(s)


def dec(s):
    return D(str(s))


def reconstruct(x):
    candles = tuple(
        Candle(
            dt(b["open_time"]),
            dt(b["close_time"]),
            dec(b["open"]),
            dec(b["high"]),
            dec(b["low"]),
            dec(b["close"]),
            dec(b["volume"]),
        )
        for b in x["snapshot"]["candles"]
    )
    snap = MarketSnapshot(
        x["snapshot"]["exchange"],
        x["snapshot"]["market_type"],
        x["snapshot"]["symbol"],
        x["snapshot"]["timeframe"],
        candles,
        dt(x["snapshot"]["captured_at"]),
        x["snapshot"]["source"],
    )
    ev = tuple(
        BrooksRuleEvidence(
            rule_id=e["rule_id"],
            status=e["status"],
            source_pages=tuple(e["source_pages"]),
            evidence=tuple(tuple(i) for i in e["evidence"]),
            failed_conditions=tuple(e["failed_conditions"]),
            confidence_components=tuple(tuple(i) for i in e["confidence_components"]),
        )
        for e in x["rule_evidence"]
    )
    return PaperSignalCandidate(
        source_signal_id="PHASE88C_FORWARD_CURRENT",
        symbol=x["symbol"],
        timeframe=x["timeframe"],
        direction=x["direction"],
        entry_price=dec(x["entry"]),
        stop_loss=dec(x["initial_stop"]),
        targets=tuple(dec(v) for v in x["targets"]),
        exchange=x["exchange"],
        market_type=x["market_type"],
        setup_type=x["setup_type"],
        market_snapshot_id=x["snapshot_id"],
        market_snapshot_hash=x["snapshot_hash"],
        engine_version=x["engine_version"],
        rule_set_version=x["rule_set_version"],
        configuration_version=x["configuration_version"],
        reasoning=tuple(x["reasoning"]),
        rule_ids=tuple(x["rule_ids"]),
        failed_rules=tuple(x["failed_rules"]),
        rule_evidence=ev,
        chart_path="NO_PUBLICATION",
        snapshot=snap,
        target_source_identities=tuple(
            TargetSourceIdentity.from_metadata(item) for item in x["target_source_identities"]
        ),
        stop_source_identity=(
            None
            if x.get("stop_source_identity") is None
            else StopSourceIdentity.from_metadata(x["stop_source_identity"])
        ),
        target_plan_lifecycle=TargetPlanLifecycle.from_metadata(x["target_plan_lifecycle"]),
        reversal_outcome_context=(
            None
            if x.get("reversal_outcome_context") is None
            else ReversalOutcomeContext.from_metadata(x["reversal_outcome_context"])
        ),
        semantic_cohort_id=x.get("semantic_cohort_id"),
    )


async def fetch_symbol(symbol, start, end):
    p = BinanceFuturesMarketDataProvider()
    out = []
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    try:
        while cursor <= end_ms:
            payload = await p.http.get_json(
                "/fapi/v1/klines",
                params={
                    "symbol": symbol,
                    "interval": "1m",
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": 1000,
                },
            )
            if not payload:
                break
            batch = [p._candle_from_row(row) for row in payload if _dt(int(row[6])) <= end]
            out.extend(batch)
            nxt = int(payload[-1][6]) + 1
            if nxt <= cursor:
                break
            cursor = nxt
            if len(payload) < 1000:
                break
        uniq = {c.open_time: c for c in out}
        return tuple(uniq[k] for k in sorted(uniq))
    finally:
        await p.aclose()


def r_at(direction, entry, price, initial_risk):
    return ((price - entry) if direction == "LONG" else (entry - price)) / initial_risk


def outcome_one(x, candles, lifecycle):
    c = reconstruct(x)
    risk = RiskEngineService().evaluate(c)
    view = read_current_risk(c, assessment=risk, need_trade_plan=True)
    plan = view["trade_management_plan"]
    if plan is None or not all(view["invariants"].values()):
        raise RuntimeError("CURRENT_RISK_PLAN_INVALID")
    if dec(x["current_plan_rr"]) != view["plan_rr"]:
        raise RuntimeError("CURRENT_PLAN_RR_MISMATCH")
    if dec(x["v6_planned_reward_r"]) != view["plan_rr"]:
        raise RuntimeError("V6_COMPATIBILITY_ALIAS_MISMATCH")
    if x["management_plan"] != plan.to_metadata():
        raise RuntimeError("CURRENT_MANAGEMENT_PLAN_MISMATCH")
    if {str(k): str(v) for k, v in plan.target_exit_fractions} != x["target_exit_fractions"]:
        raise RuntimeError("CURRENT_TARGET_ALLOCATION_MISMATCH")
    if str(plan.runner_fraction) != x["runner_fraction"]:
        raise RuntimeError("CURRENT_RUNNER_FRACTION_MISMATCH")
    targets = [
        NS(target_number=i, target_price=t, status="PENDING") for i, t in enumerate(c.targets, 1)
    ]
    signal = NS(
        symbol=c.symbol,
        direction=c.direction,
        entry_price=c.entry_price,
        stop_loss=c.stop_loss,
        leverage=D("1"),
    )
    created = dt(x["candidate_timestamp"])
    available = tuple(k for k in candles if k.close_time > created)
    state = "WAITING_ENTRY"
    entry_at = None
    runner_event = None
    current_stop = c.stop_loss
    initial_risk = abs(c.entry_price - c.stop_loss)
    max_fav = D(0)
    max_adv = D(0)
    terminal_time = None
    terminal = None
    ambiguous_reason = None
    targets_hit = []
    stop_updates = []
    realized_r = None
    for candle in available:
        if state == "WAITING_ENTRY":
            if not (candle.low <= c.entry_price <= candle.high):
                continue
            entry_at = candle.close_time
            state = "ACTIVE"
            touched_target = any(
                lifecycle._target_touched(c.direction, t.target_price, candle) for t in targets
            )
            touched_stop = lifecycle._stop_touched(signal, candle)
            if c.direction == "LONG":
                max_fav = max(max_fav, candle.high - c.entry_price)
                max_adv = max(max_adv, c.entry_price - candle.low)
            else:
                max_fav = max(max_fav, c.entry_price - candle.low)
                max_adv = max(max_adv, candle.high - c.entry_price)
            if touched_target or touched_stop:
                terminal = "AMBIGUOUS"
                ambiguous_reason = "ENTRY_AND_EXIT_SAME_1M_CANDLE"
                terminal_time = candle.close_time
                state = "AMBIGUOUS"
                break
            continue
        if c.direction == "LONG":
            max_fav = max(max_fav, candle.high - c.entry_price)
            max_adv = max(max_adv, c.entry_price - candle.low)
        else:
            max_fav = max(max_fav, c.entry_price - candle.low)
            max_adv = max(max_adv, candle.high - c.entry_price)
        pending = [t for t in targets if t.status == "PENDING"]
        touched_targets = [
            t for t in pending if lifecycle._target_touched(c.direction, t.target_price, candle)
        ]
        touched_stop = lifecycle._stop_touched(signal, candle)
        if touched_stop and touched_targets:
            terminal = "AMBIGUOUS"
            ambiguous_reason = "STOP_AND_TARGET_SAME_1M_CANDLE"
            terminal_time = candle.close_time
            state = "AMBIGUOUS"
            break
        if touched_targets:
            for t in touched_targets:
                t.status = "HIT"
                targets_hit.append(t.target_number)
            if open_position_fraction(plan, targets, runner_event) == 0:
                tr = r_at(
                    c.direction, c.entry_price, touched_targets[-1].target_price, initial_risk
                )
                realized_r = weighted_close_return(
                    plan=plan,
                    targets=targets,
                    target_returns={
                        t.target_number: r_at(
                            c.direction, c.entry_price, t.target_price, initial_risk
                        )
                        for t in targets
                        if t.status == "HIT"
                    },
                    terminal_return=tr,
                )
                terminal = "TARGET_STAGED_COMPLETION"
                terminal_time = candle.close_time
                state = "COMPLETE"
                break
        elif touched_stop:
            tr = r_at(c.direction, c.entry_price, current_stop, initial_risk)
            realized_r = weighted_close_return(
                plan=plan,
                targets=targets,
                target_returns={
                    t.target_number: r_at(c.direction, c.entry_price, t.target_price, initial_risk)
                    for t in targets
                    if t.status == "HIT"
                },
                terminal_return=tr,
            )
            terminal = (
                "BREAKEVEN"
                if current_stop == c.entry_price
                else ("TRAILING_STOP_CLOSE" if stop_updates else "INITIAL_STOP_HIT")
            )
            terminal_time = candle.close_time
            state = "COMPLETE"
            break
        # Runner reversal is deliberately fail-closed: no durable final-gate-approved
        # opposite evidence is available before statistics validation.
        desired = None
        reason = None
        risk_side = (c.direction == "LONG" and current_stop < c.entry_price) or (
            c.direction == "SHORT" and current_stop > c.entry_price
        )
        if risk_side and lifecycle._breakeven_ready(tuple(targets), plan):
            desired = c.entry_price
            reason = "BREAKEVEN_AFTER_SCALE_OUT"
        elif risk_side and lifecycle._entry_tested_then_resumed(
            signal=signal, plan=plan, candles=available, candle=candle, entry_activated_at=entry_at
        ):
            desired = c.entry_price
            reason = "BREAKEVEN_STRUCTURE_CONFIRMED"
        structural = lifecycle._structural_trailing_stop(
            signal=signal, candles=available, candle=candle, entry_activated_at=entry_at
        )
        if structural is not None and (
            (
                c.direction == "LONG"
                and structural > current_stop
                and (desired is None or structural > desired)
            )
            or (
                c.direction == "SHORT"
                and structural < current_stop
                and (desired is None or structural < desired)
            )
        ):
            desired = structural
            reason = "STRUCTURAL_TRAIL"
        if desired is not None and (
            (c.direction == "LONG" and desired > current_stop)
            or (c.direction == "SHORT" and desired < current_stop)
        ):
            current_stop = desired
            signal.stop_loss = desired
            stop_updates.append(
                {"time": candle.close_time.isoformat(), "stop": str(desired), "reason": reason}
            )
    if terminal is None:
        terminal = "NEVER_ENTERED" if entry_at is None else "OPEN"
    valid = (
        terminal
        in {
            "INITIAL_STOP_HIT",
            "BREAKEVEN",
            "TRAILING_STOP_CLOSE",
            "TARGET_STAGED_COMPLETION",
            "RUNNER_REVERSAL",
        }
        and realized_r is not None
    )
    canon = (
        "VALID_REALIZED_R"
        if valid
        else (
            "AMBIGUOUS"
            if terminal == "AMBIGUOUS"
            else ("UNRECONSTRUCTABLE" if terminal not in {"NEVER_ENTERED", "OPEN"} else terminal)
        )
    )
    pnl_pct = (
        (realized_r * (initial_risk / c.entry_price) * D("100")) if realized_r is not None else None
    )
    return {
        "candidate_identity": x["candidate_identity"],
        "candidate_timestamp": x["candidate_timestamp"],
        "symbol": c.symbol,
        "timeframe": c.timeframe,
        "direction": c.direction,
        "setup_type": c.setup_type,
        "entry": str(c.entry_price),
        "initial_stop": str(c.stop_loss),
        "targets": list(map(str, c.targets)),
        "management_version": x["management_version"],
        "statistics_contract_version": x["statistics_contract_version"],
        "entry_activated": entry_at is not None,
        "entry_activation_timestamp": entry_at.isoformat() if entry_at else None,
        "terminal_timestamp": terminal_time.isoformat() if terminal_time else None,
        "terminal_lifecycle_reason": terminal,
        "canonicalization_status": canon,
        "ambiguous_reason": ambiguous_reason,
        "targets_hit": targets_hit,
        "stop_updates": stop_updates,
        "target_exit_fractions": x["target_exit_fractions"],
        "runner_fraction": x["runner_fraction"],
        "current_plan_rr": str(view["plan_rr"]),
        "v6_planned_reward_r": str(view["plan_rr"]),
        "management_plan": plan.to_metadata(),
        "current_plan_invariants": view["invariants"],
        "weighted_realized_pnl_pct_unlevered": str(pnl_pct) if pnl_pct is not None else None,
        "realized_r": str(realized_r) if realized_r is not None else None,
        "mfe_r": str(max_fav / initial_risk) if entry_at else None,
        "mae_r": str(max_adv / initial_risk) if entry_at else None,
        "runner_reversal_evidence_mode": "FAIL_CLOSED_NO_PRESTAT_FINAL_GATE_APPROVAL_EVIDENCE",
    }


async def main(*, candidates_path, raw_output, closed_output, end_time, allow_network):
    if not allow_network:
        raise RuntimeError("88C replay requires explicit --allow-network")
    fixture = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates = fixture["candidates"]
    start = min(dt(x["candidate_timestamp"]) for x in candidates) - timedelta(minutes=2)
    end = dt(end_time).replace(second=0, microsecond=0)
    symbols = sorted({x["symbol"] for x in candidates})
    print("FETCH_WINDOW", start.isoformat(), end.isoformat(), flush=True)
    t0 = time.perf_counter()
    fetched = await asyncio.gather(*(fetch_symbol(symbol, start, end) for symbol in symbols))
    data = dict(zip(symbols, fetched, strict=True))
    print(
        "CANDLE_COUNTS",
        {symbol: len(data[symbol]) for symbol in symbols},
        "FETCH_S",
        round(time.perf_counter() - t0, 3),
        flush=True,
    )
    lifecycle = LiveSignalLifecycleService(
        database=None,
        provider=None,
        bot=None,
        vip_channel_id=0,
        cutover_at=start,
        candle_limit=999999,
    )
    rows = []
    errors = []
    for source in candidates:
        try:
            rows.append(outcome_one(source, data[source["symbol"]], lifecycle))
        except Exception as exc:
            errors.append(
                {
                    "candidate_identity": source["candidate_identity"],
                    "error_type": type(exc).__name__,
                }
            )
            rows.append(
                {
                    "candidate_identity": source["candidate_identity"],
                    "candidate_timestamp": source["candidate_timestamp"],
                    "symbol": source["symbol"],
                    "timeframe": source["timeframe"],
                    "direction": source["direction"],
                    "setup_type": source["setup_type"],
                    "entry_activated": False,
                    "terminal_lifecycle_reason": "UNRECONSTRUCTABLE",
                    "canonicalization_status": "UNRECONSTRUCTABLE",
                    "realized_r": None,
                    "error_type": type(exc).__name__,
                }
            )
    candidate_sha = hashlib.sha256(candidates_path.read_bytes()).hexdigest()
    raw = {
        "phase": "4.2.41.88C-current-contract",
        "candidate_fixture_sha256": candidate_sha,
        "market_data": "binance_futures_1m_only_explicit",
        "fetch_window_utc": [start.isoformat(), end.isoformat()],
        "runner_reversal_evidence_mode": ("FAIL_CLOSED_NO_PRESTAT_FINAL_GATE_APPROVAL_EVIDENCE"),
        "candidate_count": len(rows),
        "rows": rows,
        "errors": errors,
    }
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    valid = [row for row in rows if row["canonicalization_status"] == "VALID_REALIZED_R"]
    closed = {
        "phase": "4.2.41.88C-current-contract",
        "purpose": "VALID_CLOSED_REALIZED_R_ONLY",
        "candidate_fixture_sha256": candidate_sha,
        "raw_forward_artifact_sha256": hashlib.sha256(raw_output.read_bytes()).hexdigest(),
        "case_count": len(valid),
        "cases": valid,
    }
    closed_output.parent.mkdir(parents=True, exist_ok=True)
    closed_output.write_text(
        json.dumps(closed, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("VALID_CLOSED", len(valid), "ERRORS", len(errors))
    print("RAW_SHA256", hashlib.sha256(raw_output.read_bytes()).hexdigest())
    print("CLOSED_SHA256", hashlib.sha256(closed_output.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--closed-output", type=Path, required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        main(
            candidates_path=args.candidates,
            raw_output=args.raw_output,
            closed_output=args.closed_output,
            end_time=args.end_time,
            allow_network=args.allow_network,
        )
    )
