from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal as D
from types import SimpleNamespace as NS
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.trade_management import TradeManagementPlan, weighted_close_return
from app.modules.operations.approval_evidence import open_position_fraction, open_runner_fraction
D0=D("0"); D1=D("1")
@dataclass(frozen=True)
class PollResult:
    state: dict
    poll_status: str
    processed_candles: int

def _r(direction,entry,price,risk): return ((price-entry) if direction=="LONG" else (entry-price))/risk
def _targets(c,state):
    hit=set(state.get("targets_hit",[])); return [NS(target_number=i,target_price=D(str(p)),status="HIT" if i in hit else "PENDING") for i,p in enumerate(c["targets"],1)]
def new_state(c):
    return {"status":"WAITING_ENTRY","entry_activated_at":None,"last_processed_candle_close":c["candidate_timestamp"],"current_stop":c["initial_stop"],"targets_hit":[],"stop_updates":[],"runner_event":None,"mfe_r":"0","mae_r":"0","terminal_timestamp":None,"terminal_reason":None,"realized_r":None,"weighted_realized_pnl_pct_unlevered":None,"ambiguous_reason":None,"reconstruction_status":None}
def runner_reversal_evidence(c,state,candle,evidence):
    if not state.get("entry_activated_at"): return None
    entry_at=state["entry_activated_at"]; base=next((e for e in evidence if e["candidate_identity"]==c["candidate_identity"]),None)
    if not base or base["direction"]!=c["direction"] or base["always_in"]!=c["direction"] or base["approved_at"]>entry_at or base["candle_closed_at"]>entry_at:return None
    opp="SHORT" if c["direction"]=="LONG" else "LONG"
    for e in evidence:
        if e["candidate_identity"]==c["candidate_identity"]: continue
        if e["symbol"]==c["symbol"] and e["timeframe"]==c["timeframe"] and e["direction"]==opp and e["always_in"]==opp and e["approved_at"]>entry_at and e["candle_closed_at"]>entry_at and e["approved_at"]<=candle.open_time.isoformat() and e["candle_closed_at"]<=candle.open_time.isoformat(): return e
    return None

def _require_aware(value: datetime, name: str) -> datetime:
    if value is None or value.tzinfo is None: raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)

def advance(c,state,candles,evidence=(),*,cutover_at: datetime|None,as_of: datetime):
    """Advance only on causally closed candles; empty polls are explicit no-ops."""
    as_of=_require_aware(as_of,"as_of")
    work=deepcopy(state)
    floor=datetime.fromisoformat(work["last_processed_candle_close"])
    if floor.tzinfo is None: raise ValueError("last_processed_candle_close must be timezone-aware")
    visible=tuple(x for x in candles if x.close_time < as_of)
    available=tuple(x for x in visible if x.close_time > floor)
    if not available:
        return PollResult(work,"NO_NEW_ELIGIBLE_CLOSED_CANDLE",0)
    cutover=_require_aware(cutover_at,"cutover_at")
    life=LiveSignalLifecycleService(database=None,provider=None,bot=None,vip_channel_id=0,cutover_at=cutover,candle_limit=999999)
    entry=D(c["entry"]); initial_stop=D(c["initial_stop"]); risk=abs(entry-initial_stop); plan=TradeManagementPlan.from_metadata(c["management_plan"]); direction=c["direction"]; current_stop=D(work["current_stop"])
    targets=_targets(c,work); runner_event=work.get("runner_event"); runner_obj=NS(metadata=runner_event) if runner_event else None
    signal=NS(symbol=c["symbol"],direction=direction,entry_price=entry,stop_loss=current_stop,leverage=D1)
    mfe=D(work.get("mfe_r","0")); mae=D(work.get("mae_r","0"))
    for candle in available:
        if work["status"] in {"COMPLETE","AMBIGUOUS","UNRECONSTRUCTABLE"}: break
        signal.stop_loss=current_stop
        if work["status"]=="WAITING_ENTRY":
            if not (candle.low<=entry<=candle.high): work["last_processed_candle_close"]=candle.close_time.isoformat(); continue
            work["status"]="ACTIVE"; work["entry_activated_at"]=candle.close_time.isoformat()
            touched_t=any(life._target_touched(direction,t.target_price,candle) for t in targets); touched_s=life._stop_touched(signal,candle)
            mfe=max(mfe,((candle.high-entry) if direction=="LONG" else (entry-candle.low))/risk); mae=max(mae,((entry-candle.low) if direction=="LONG" else (candle.high-entry))/risk)
            if touched_t or touched_s:
                work.update(status="AMBIGUOUS",terminal_timestamp=candle.close_time.isoformat(),terminal_reason="OUTCOME_AMBIGUOUS",ambiguous_reason="ENTRY_AND_EXIT_SAME_1M_CANDLE",reconstruction_status="AMBIGUOUS"); break
            work["last_processed_candle_close"]=candle.close_time.isoformat(); continue
        mfe=max(mfe,((candle.high-entry) if direction=="LONG" else (entry-candle.low))/risk); mae=max(mae,((entry-candle.low) if direction=="LONG" else (candle.high-entry))/risk)
        pending=[t for t in targets if t.status=="PENDING"]; touched=[t for t in pending if life._target_touched(direction,t.target_price,candle)]; touched_s=life._stop_touched(signal,candle)
        if touched_s and touched:
            work.update(status="AMBIGUOUS",terminal_timestamp=candle.close_time.isoformat(),terminal_reason="OUTCOME_AMBIGUOUS",ambiguous_reason="STOP_AND_TARGET_SAME_1M_CANDLE",reconstruction_status="AMBIGUOUS"); break
        if touched:
            for t in touched:
                t.status="HIT"; work["targets_hit"].append(t.target_number)
            if open_position_fraction(plan,targets,runner_obj)==0:
                tr=_r(direction,entry,touched[-1].target_price,risk); rr=weighted_close_return(plan=plan,targets=targets,target_returns={t.target_number:_r(direction,entry,t.target_price,risk) for t in targets if t.status=="HIT"},terminal_return=tr)
                work.update(status="COMPLETE",terminal_timestamp=candle.close_time.isoformat(),terminal_reason="TARGET_STAGED_COMPLETION",realized_r=str(rr),reconstruction_status="VALID_REALIZED_R"); break
        elif touched_s:
            tr=_r(direction,entry,current_stop,risk); rr=weighted_close_return(plan=plan,targets=targets,target_returns={t.target_number:_r(direction,entry,t.target_price,risk) for t in targets if t.status=="HIT"},terminal_return=tr)
            reason="BREAKEVEN" if current_stop==entry else ("TRAILING_STOP_CLOSE" if work["stop_updates"] else "INITIAL_STOP_HIT")
            work.update(status="COMPLETE",terminal_timestamp=candle.close_time.isoformat(),terminal_reason=reason,realized_r=str(rr),reconstruction_status="VALID_REALIZED_R"); break
        ev=runner_reversal_evidence(c,work,candle,evidence)
        if ev is not None and open_runner_fraction(plan,targets,runner_obj)>0:
            frac=open_runner_fraction(plan,targets,runner_obj); tr=_r(direction,entry,candle.close,risk); runner_event={"exit_fraction":str(frac),"exit_price":str(candle.close),"return_pct":str(tr),"weighted_return_pct":str(frac*tr),"evidence_source_signal_id":ev["candidate_identity"]}; runner_obj=NS(metadata=runner_event); work["runner_event"]=runner_event
            rr=weighted_close_return(plan=plan,targets=targets,target_returns={t.target_number:_r(direction,entry,t.target_price,risk) for t in targets if t.status=="HIT"},terminal_return=tr)
            work.update(status="COMPLETE",terminal_timestamp=candle.close_time.isoformat(),terminal_reason="RUNNER_REVERSAL",realized_r=str(rr),reconstruction_status="VALID_REALIZED_R"); break
        desired=None; reason=None; risk_side=(direction=="LONG" and current_stop<entry) or (direction=="SHORT" and current_stop>entry)
        if risk_side and life._breakeven_ready(tuple(targets),plan): desired=entry; reason="BREAKEVEN_AFTER_SCALE_OUT"
        elif risk_side and life._entry_tested_then_resumed(signal=signal,plan=plan,candles=visible,candle=candle,entry_activated_at=datetime.fromisoformat(work["entry_activated_at"])): desired=entry; reason="BREAKEVEN_STRUCTURE_CONFIRMED"
        structural=life._structural_trailing_stop(signal=signal,candles=visible,candle=candle,entry_activated_at=datetime.fromisoformat(work["entry_activated_at"]))
        if structural is not None and ((direction=="LONG" and structural>current_stop and (desired is None or structural>desired)) or (direction=="SHORT" and structural<current_stop and (desired is None or structural<desired))): desired=structural; reason="STRUCTURAL_TRAIL"
        if desired is not None and ((direction=="LONG" and desired>current_stop) or (direction=="SHORT" and desired<current_stop)):
            current_stop=desired; work["current_stop"]=str(desired); work["stop_updates"].append({"time":candle.close_time.isoformat(),"stop":str(desired),"reason":reason})
        work["last_processed_candle_close"]=candle.close_time.isoformat()
    work["mfe_r"]=str(mfe); work["mae_r"]=str(mae)
    if work.get("realized_r") is not None: work["weighted_realized_pnl_pct_unlevered"]=str(D(work["realized_r"])*(risk/entry)*D("100"))
    return PollResult(work,"PROCESSED",len(available))
