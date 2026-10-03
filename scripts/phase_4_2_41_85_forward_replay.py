from __future__ import annotations
import argparse
import asyncio
import dataclasses
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS

from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider, _dt
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.signal_automation.entities import BrooksRuleEvidence
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.market_context import build_market_context
from app.modules.operations.trade_management import weighted_close_return
from research_layer.current_risk_contract import read_current_risk
from app.modules.operations.approval_evidence import open_position_fraction, open_runner_fraction
from app.modules.operations.lifecycle import LiveSignalLifecycleService

ROOT = Path(__file__).resolve().parents[1]
D=Decimal

def dt(s): return datetime.fromisoformat(s)
def dec(s): return D(str(s))
def snapshot_from_row(x):
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
    return MarketSnapshot(
        x["snapshot"]["exchange"],
        x["snapshot"]["market_type"],
        x["snapshot"]["symbol"],
        x["snapshot"]["timeframe"],
        candles,
        dt(x["snapshot"]["captured_at"]),
        x["snapshot"]["source"],
    )


async def regenerate_current_candidate(x):
    snap = snapshot_from_row(x)
    engine = BrooksTrilogyFullCoreEngine(
        policy=BrooksFullCorePolicy(enable_trade_decisions=True)
    )
    result = await engine.evaluate(snap)
    if result.decision not in {"LONG", "SHORT"}:
        raise RuntimeError("CURRENT_ENGINE_NO_SIGNAL")
    fields = {
        field.name: getattr(result, field.name)
        for field in dataclasses.fields(PaperSignalCandidate)
        if hasattr(result, field.name)
    }
    fields.update(
        source_signal_id="PHASE85_FORWARD_CURRENT",
        symbol=snap.symbol,
        timeframe=snap.timeframe,
        direction=result.decision,
        exchange=snap.exchange,
        market_type=snap.market_type,
        market_snapshot_id=snap.snapshot_id,
        market_snapshot_hash=snap.snapshot_hash,
        chart_path="NO_PUBLICATION",
        snapshot=snap,
    )
    return PaperSignalCandidate(**fields)

async def fetch_symbol(symbol,start,end):
    p=BinanceFuturesMarketDataProvider()
    out=[]; cursor=int(start.timestamp()*1000)
    end_ms=int(end.timestamp()*1000)
    try:
        while cursor<=end_ms:
            payload=await p.http.get_json('/fapi/v1/klines',params={'symbol':symbol,'interval':'1m','startTime':cursor,'endTime':end_ms,'limit':1000})
            if not payload: break
            batch=[p._candle_from_row(row) for row in payload if _dt(int(row[6]))<=end]
            out.extend(batch)
            nxt=int(payload[-1][6])+1
            if nxt<=cursor: break
            cursor=nxt
            if len(payload)<1000: break
        uniq={c.open_time:c for c in out}
        return tuple(uniq[k] for k in sorted(uniq))
    finally: await p.aclose()

def r_at(direction,entry,price,initial_risk):
    return ((price-entry) if direction=='LONG' else (entry-price))/initial_risk

def outcome_one(x, c, candles, accepted_evidence, lifecycle, policy_by):
    policy = policy_by[x["identity_sha256"]]
    accepted = bool(policy["cold_start_pass"])
    view = read_current_risk(c, need_trade_plan=True)
    plan = view["trade_management_plan"]
    if plan is None or not all(view["invariants"].values()):
        raise RuntimeError("CURRENT_RISK_PLAN_INVALID")
    targets=[NS(target_number=i,target_price=t,status='PENDING') for i,t in enumerate(c.targets,1)]
    signal=NS(symbol=c.symbol,direction=c.direction,entry_price=c.entry_price,stop_loss=c.stop_loss,leverage=D('1'))
    created=dt(x['candidate_timestamp']); available=tuple(k for k in candles if k.close_time>created)
    state='WAITING_ENTRY'; entry_at=None; runner_event=None; current_stop=c.stop_loss
    initial_risk=abs(c.entry_price-c.stop_loss); sign=D(1) if c.direction=='LONG' else D(-1)
    max_fav=D(0); max_adv=D(0); terminal_time=None; terminal=None; ambiguous_reason=None; targets_hit=[]; stop_updates=[]; runner_closed=False; realized_r=None
    context=build_market_context(c.snapshot)
    baseline_ok=accepted and context.always_in==c.direction
    def opposite_evidence_before(candle):
        if not baseline_ok or entry_at is None: return None
        opp='SHORT' if c.direction=='LONG' else 'LONG'
        items=[]
        for e in accepted_evidence:
            if e['identity']==x['identity_sha256']: continue
            if e['symbol']!=c.symbol or e['timeframe']!=c.timeframe or e['direction']!=opp or e['always_in']!=opp: continue
            if e['approved_at']<=entry_at or e['candle_closed_at']<=entry_at: continue
            if e['approved_at']<=candle.open_time and e['candle_closed_at']<=candle.open_time: items.append(e)
        return min(items,key=lambda z:(z['approved_at'],z['identity'])) if items else None
    for candle in available:
        if state=='WAITING_ENTRY':
            if not (candle.low<=c.entry_price<=candle.high): continue
            entry_at=candle.close_time; state='ACTIVE'
            touched_target=any(lifecycle._target_touched(c.direction,t.target_price,candle) for t in targets)
            touched_stop=lifecycle._stop_touched(signal,candle)
            # Excursions begin with the activation candle.
            if c.direction=='LONG': max_fav=max(max_fav,candle.high-c.entry_price); max_adv=max(max_adv,c.entry_price-candle.low)
            else: max_fav=max(max_fav,c.entry_price-candle.low); max_adv=max(max_adv,candle.high-c.entry_price)
            if touched_target or touched_stop:
                terminal='AMBIGUOUS';ambiguous_reason='ENTRY_AND_EXIT_SAME_1M_CANDLE';terminal_time=candle.close_time;state='AMBIGUOUS';break
            continue
        if c.direction=='LONG': max_fav=max(max_fav,candle.high-c.entry_price); max_adv=max(max_adv,c.entry_price-candle.low)
        else: max_fav=max(max_fav,c.entry_price-candle.low); max_adv=max(max_adv,candle.high-c.entry_price)
        pending=[t for t in targets if t.status=='PENDING']
        touched_targets=[t for t in pending if lifecycle._target_touched(c.direction,t.target_price,candle)]
        touched_stop=lifecycle._stop_touched(signal,candle)
        if touched_stop and touched_targets:
            terminal='AMBIGUOUS';ambiguous_reason='STOP_AND_TARGET_SAME_1M_CANDLE';terminal_time=candle.close_time;state='AMBIGUOUS';break
        if touched_targets:
            for t in touched_targets: t.status='HIT'; targets_hit.append(t.target_number)
            if open_position_fraction(plan,targets,runner_event)==0:
                tr=r_at(c.direction,c.entry_price,touched_targets[-1].target_price,initial_risk)
                realized_r=weighted_close_return(plan=plan,targets=targets,target_returns={t.target_number:r_at(c.direction,c.entry_price,t.target_price,initial_risk) for t in targets},terminal_return=tr)
                terminal='TARGET_HIT';terminal_time=candle.close_time;state='COMPLETE';break
        elif touched_stop:
            tr=r_at(c.direction,c.entry_price,current_stop,initial_risk)
            realized_r=weighted_close_return(plan=plan,targets=targets,target_returns={t.target_number:r_at(c.direction,c.entry_price,t.target_price,initial_risk) for t in targets},terminal_return=tr)
            terminal='BREAKEVEN' if current_stop==c.entry_price else ('TRAILING_STOP_HIT' if (current_stop-c.entry_price)*sign>0 else 'STOP_HIT')
            terminal_time=candle.close_time;state='COMPLETE';break
        # Same causal durable-approved-evidence rule as production runner exit.
        opp=opposite_evidence_before(candle)
        frac=open_runner_fraction(plan,targets,runner_event)
        if opp is not None and frac>0:
            rr=r_at(c.direction,c.entry_price,candle.close,initial_risk)
            runner_event=NS(metadata={'exit_fraction':str(frac),'return_r':str(rr)})
            runner_closed=True
            if open_position_fraction(plan,targets,runner_event)==0:
                target_real=sum(plan.fraction_for_target(t.target_number)*r_at(c.direction,c.entry_price,t.target_price,initial_risk) for t in targets if t.status=='HIT')
                realized_r=target_real+frac*rr
                terminal='RUNNER_REVERSAL';terminal_time=candle.close_time;state='COMPLETE';break
        # Production stop-management helpers, applied after target/runner handling.
        desired=None;reason=None
        risk_side=(c.direction=='LONG' and current_stop<c.entry_price) or (c.direction=='SHORT' and current_stop>c.entry_price)
        if risk_side and lifecycle._breakeven_ready(tuple(targets),plan): desired=c.entry_price;reason='BREAKEVEN_AFTER_SCALE_OUT'
        elif risk_side and lifecycle._entry_tested_then_resumed(signal=signal,plan=plan,candles=available,candle=candle,entry_activated_at=entry_at): desired=c.entry_price;reason='BREAKEVEN_STRUCTURE_CONFIRMED'
        structural=lifecycle._structural_trailing_stop(signal=signal,candles=available,candle=candle,entry_activated_at=entry_at)
        if structural is not None:
            if c.direction=='LONG' and structural>current_stop and (desired is None or structural>desired): desired=structural;reason='STRUCTURAL_TRAIL'
            elif c.direction=='SHORT' and structural<current_stop and (desired is None or structural<desired): desired=structural;reason='STRUCTURAL_TRAIL'
        if desired is not None and ((c.direction=='LONG' and desired>current_stop) or (c.direction=='SHORT' and desired<current_stop)):
            current_stop=desired;signal.stop_loss=desired;stop_updates.append({'time':candle.close_time.isoformat(),'stop':str(desired),'reason':reason})
    if terminal is None:
        if entry_at is None: terminal='NEVER_ENTERED'
        else: terminal='OPEN'
    return {
      'identity':x['identity_sha256'],'timestamp':x['candidate_timestamp'],'symbol':c.symbol,'timeframe':c.timeframe,'direction':c.direction,'setup_type':c.setup_type,'cold_start_pass':accepted,
      'entry_activated':entry_at is not None,'entry_activated_at':entry_at.isoformat() if entry_at else None,'terminal_status':terminal,'terminal_time':terminal_time.isoformat() if terminal_time else None,'ambiguous_reason':ambiguous_reason,
      'targets_hit':targets_hit,'runner_closed_on_approved_reversal':runner_closed,'stop_updates':stop_updates,
      'mfe_r':str(max_fav/initial_risk) if entry_at else None,'mae_r':str(max_adv/initial_risk) if entry_at else None,'realized_r':str(realized_r) if realized_r is not None else None,
      'plan_context':plan.context_class,'target_exit_fractions':{str(k):str(v) for k,v in plan.target_exit_fractions},'runner_fraction':str(plan.runner_fraction),'baseline_always_in':context.always_in,'runner_baseline_eligible':baseline_ok,
      'current_plan_rr':str(view["plan_rr"]),'v6_planned_reward_r':str(view["plan_rr"]),
      'risk_semantic_model':view["plan_breakdown"]["mode"],'runner_policy':view["plan_breakdown"]["runner_policy"],
      'management_plan':plan.to_metadata(),'current_plan_invariants':view["invariants"],
    }

async def main(*, fixture_path, policy_path, output_path, end_time, allow_network):
    if not allow_network:
        raise RuntimeError("forward replay requires explicit --allow-network")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    policy_doc = json.loads(policy_path.read_text(encoding="utf-8"))
    policy_by = {}
    for row in policy_doc["rows"]:
        identity = row.get("historical_identity", row.get("identity"))
        if not identity:
            raise ValueError("policy result row missing historical identity")
        policy_by[identity] = row
    candidates = fixture["candidates"]
    current = {}
    for row in candidates:
        current[row["identity_sha256"]] = await regenerate_current_candidate(row)
    start = min(dt(x["candidate_timestamp"]) for x in candidates) - timedelta(minutes=2)
    end = dt(end_time).replace(second=0, microsecond=0)
    symbols = sorted({candidate.symbol for candidate in current.values()})
    fetched = await asyncio.gather(*(fetch_symbol(symbol, start, end) for symbol in symbols))
    data = dict(zip(symbols, fetched, strict=True))
    accepted = []
    for x in candidates:
        if not policy_by[x["identity_sha256"]]["cold_start_pass"]:
            continue
        c = current[x["identity_sha256"]]
        ctx = build_market_context(c.snapshot)
        accepted.append({
            "identity": x["identity_sha256"],
            "symbol": c.symbol,
            "timeframe": c.timeframe,
            "direction": c.direction,
            "always_in": ctx.always_in,
            "approved_at": dt(x["candidate_timestamp"]),
            "candle_closed_at": c.snapshot.candles[-1].close_time,
        })
    lifecycle = LiveSignalLifecycleService(
        database=None, provider=None, bot=None, vip_channel_id=0,
        cutover_at=start, candle_limit=999,
    )
    rows = [
        outcome_one(
            x, current[x["identity_sha256"]], data[current[x["identity_sha256"]].symbol],
            accepted, lifecycle, policy_by,
        )
        for x in candidates
    ]
    out = {
        "phase": "4.2.41.85-current-contract",
        "data_window_utc": [start.isoformat(), end.isoformat()],
        "candidate_count": len(rows),
        "input_fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "policy_results_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        "rows": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ARTIFACT", output_path, "SHA256", hashlib.sha256(output_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--policy-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        main(
            fixture_path=args.fixture,
            policy_path=args.policy_results,
            output_path=args.output,
            end_time=args.end_time,
            allow_network=args.allow_network,
        )
    )
