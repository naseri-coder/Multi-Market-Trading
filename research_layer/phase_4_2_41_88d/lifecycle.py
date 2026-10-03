from __future__ import annotations

from decimal import Decimal as D
from types import SimpleNamespace as NS

from app.modules.operations.approval_evidence import open_position_fraction, open_runner_fraction
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.trade_management import TradeManagementPlan, weighted_close_return

D0 = D("0")
D1 = D("1")


def _r(direction, entry, price, risk):
    return ((price - entry) if direction == "LONG" else (entry - price)) / risk


def _targets(c, state):
    hit = set(state.get("targets_hit", []))
    return [
        NS(target_number=i, target_price=D(str(p)), status="HIT" if i in hit else "PENDING")
        for i, p in enumerate(c["targets"], 1)
    ]


def new_state(c):
    return {
        "status": "WAITING_ENTRY",
        "entry_activated_at": None,
        "last_processed_candle_close": c["candidate_timestamp"],
        "current_stop": c["initial_stop"],
        "targets_hit": [],
        "stop_updates": [],
        "runner_event": None,
        "mfe_r": "0",
        "mae_r": "0",
        "terminal_timestamp": None,
        "terminal_reason": None,
        "realized_r": None,
        "weighted_realized_pnl_pct_unlevered": None,
        "ambiguous_reason": None,
        "reconstruction_status": None,
    }


def runner_reversal_evidence(c, state, candle, evidence):
    if not state.get("entry_activated_at"):
        return None
    entry_at = state["entry_activated_at"]
    base = next((e for e in evidence if e["candidate_identity"] == c["candidate_identity"]), None)
    if (
        not base
        or base["direction"] != c["direction"]
        or base["always_in"] != c["direction"]
        or base["approved_at"] > entry_at
        or base["candle_closed_at"] > entry_at
    ):
        return None
    opp = "SHORT" if c["direction"] == "LONG" else "LONG"
    for e in evidence:
        if e["candidate_identity"] == c["candidate_identity"]:
            continue
        if (
            e["symbol"] == c["symbol"]
            and e["timeframe"] == c["timeframe"]
            and e["direction"] == opp
            and e["always_in"] == opp
            and e["approved_at"] > entry_at
            and e["candle_closed_at"] > entry_at
            and e["approved_at"] <= candle.open_time.isoformat()
            and e["candle_closed_at"] <= candle.open_time.isoformat()
        ):
            return e
    return None


def advance(c, state, candles, evidence=()):
    life = LiveSignalLifecycleService(
        database=None,
        provider=None,
        bot=None,
        vip_channel_id=0,
        cutover_at=candles[0].open_time if candles else None,
        candle_limit=999999,
    )
    entry = D(c["entry"])
    initial_stop = D(c["initial_stop"])
    risk = abs(entry - initial_stop)
    plan = TradeManagementPlan.from_metadata(c["management_plan"])
    direction = c["direction"]
    current_stop = D(state["current_stop"])
    targets = _targets(c, state)
    runner_event = state.get("runner_event")
    runner_obj = NS(metadata=runner_event) if runner_event else None
    signal = NS(
        symbol=c["symbol"],
        direction=direction,
        entry_price=entry,
        stop_loss=current_stop,
        leverage=D1,
    )
    mfe = D(state.get("mfe_r", "0"))
    mae = D(state.get("mae_r", "0"))
    floor = state.get("last_processed_candle_close")
    available = [x for x in candles if x.close_time.isoformat() > floor]
    for candle in available:
        if state["status"] in {"COMPLETE", "AMBIGUOUS", "UNRECONSTRUCTABLE"}:
            break
        signal.stop_loss = current_stop
        if state["status"] == "WAITING_ENTRY":
            if not (candle.low <= entry <= candle.high):
                state["last_processed_candle_close"] = candle.close_time.isoformat()
                continue
            state["status"] = "ACTIVE"
            state["entry_activated_at"] = candle.close_time.isoformat()
            touched_t = any(
                life._target_touched(direction, t.target_price, candle) for t in targets
            )
            touched_s = life._stop_touched(signal, candle)
            mfe = max(
                mfe, ((candle.high - entry) if direction == "LONG" else (entry - candle.low)) / risk
            )
            mae = max(
                mae, ((entry - candle.low) if direction == "LONG" else (candle.high - entry)) / risk
            )
            if touched_t or touched_s:
                state.update(
                    status="AMBIGUOUS",
                    terminal_timestamp=candle.close_time.isoformat(),
                    terminal_reason="OUTCOME_AMBIGUOUS",
                    ambiguous_reason="ENTRY_AND_EXIT_SAME_1M_CANDLE",
                    reconstruction_status="AMBIGUOUS",
                )
                break
            state["last_processed_candle_close"] = candle.close_time.isoformat()
            continue
        mfe = max(
            mfe, ((candle.high - entry) if direction == "LONG" else (entry - candle.low)) / risk
        )
        mae = max(
            mae, ((entry - candle.low) if direction == "LONG" else (candle.high - entry)) / risk
        )
        pending = [t for t in targets if t.status == "PENDING"]
        touched = [t for t in pending if life._target_touched(direction, t.target_price, candle)]
        touched_s = life._stop_touched(signal, candle)
        if touched_s and touched:
            state.update(
                status="AMBIGUOUS",
                terminal_timestamp=candle.close_time.isoformat(),
                terminal_reason="OUTCOME_AMBIGUOUS",
                ambiguous_reason="STOP_AND_TARGET_SAME_1M_CANDLE",
                reconstruction_status="AMBIGUOUS",
            )
            break
        if touched:
            for t in touched:
                t.status = "HIT"
                state["targets_hit"].append(t.target_number)
            if open_position_fraction(plan, targets, runner_obj) == 0:
                tr = _r(direction, entry, touched[-1].target_price, risk)
                rr = weighted_close_return(
                    plan=plan,
                    targets=targets,
                    target_returns={
                        t.target_number: _r(direction, entry, t.target_price, risk)
                        for t in targets
                        if t.status == "HIT"
                    },
                    terminal_return=tr,
                )
                state.update(
                    status="COMPLETE",
                    terminal_timestamp=candle.close_time.isoformat(),
                    terminal_reason="TARGET_STAGED_COMPLETION",
                    realized_r=str(rr),
                    reconstruction_status="VALID_REALIZED_R",
                )
                break
        elif touched_s:
            tr = _r(direction, entry, current_stop, risk)
            rr = weighted_close_return(
                plan=plan,
                targets=targets,
                target_returns={
                    t.target_number: _r(direction, entry, t.target_price, risk)
                    for t in targets
                    if t.status == "HIT"
                },
                terminal_return=tr,
            )
            reason = (
                "BREAKEVEN"
                if current_stop == entry
                else ("TRAILING_STOP_CLOSE" if state["stop_updates"] else "INITIAL_STOP_HIT")
            )
            state.update(
                status="COMPLETE",
                terminal_timestamp=candle.close_time.isoformat(),
                terminal_reason=reason,
                realized_r=str(rr),
                reconstruction_status="VALID_REALIZED_R",
            )
            break
        ev = runner_reversal_evidence(c, state, candle, evidence)
        if ev is not None and open_runner_fraction(plan, targets, runner_obj) > 0:
            frac = open_runner_fraction(plan, targets, runner_obj)
            tr = _r(direction, entry, candle.close, risk)
            runner_event = {
                "exit_fraction": str(frac),
                "exit_price": str(candle.close),
                "return_pct": str(tr),
                "weighted_return_pct": str(frac * tr),
                "evidence_source_signal_id": ev["candidate_identity"],
            }
            runner_obj = NS(metadata=runner_event)
            state["runner_event"] = runner_event
            rr = weighted_close_return(
                plan=plan,
                targets=targets,
                target_returns={
                    t.target_number: _r(direction, entry, t.target_price, risk)
                    for t in targets
                    if t.status == "HIT"
                },
                terminal_return=tr,
            )
            state.update(
                status="COMPLETE",
                terminal_timestamp=candle.close_time.isoformat(),
                terminal_reason="RUNNER_REVERSAL",
                realized_r=str(rr),
                reconstruction_status="VALID_REALIZED_R",
            )
            break
        desired = None
        reason = None
        risk_side = (direction == "LONG" and current_stop < entry) or (
            direction == "SHORT" and current_stop > entry
        )
        if risk_side and life._breakeven_ready(tuple(targets), plan):
            desired = entry
            reason = "BREAKEVEN_AFTER_SCALE_OUT"
        elif risk_side and life._entry_tested_then_resumed(
            signal=signal,
            plan=plan,
            candles=tuple(candles),
            candle=candle,
            entry_activated_at=__import__("datetime").datetime.fromisoformat(
                state["entry_activated_at"]
            ),
        ):
            desired = entry
            reason = "BREAKEVEN_STRUCTURE_CONFIRMED"
        structural = life._structural_trailing_stop(
            signal=signal,
            candles=tuple(candles),
            candle=candle,
            entry_activated_at=__import__("datetime").datetime.fromisoformat(
                state["entry_activated_at"]
            ),
        )
        if structural is not None and (
            (
                direction == "LONG"
                and structural > current_stop
                and (desired is None or structural > desired)
            )
            or (
                direction == "SHORT"
                and structural < current_stop
                and (desired is None or structural < desired)
            )
        ):
            desired = structural
            reason = "STRUCTURAL_TRAIL"
        if desired is not None and (
            (direction == "LONG" and desired > current_stop)
            or (direction == "SHORT" and desired < current_stop)
        ):
            current_stop = desired
            state["current_stop"] = str(desired)
            state["stop_updates"].append(
                {"time": candle.close_time.isoformat(), "stop": str(desired), "reason": reason}
            )
        state["last_processed_candle_close"] = candle.close_time.isoformat()
    state["mfe_r"] = str(mfe)
    state["mae_r"] = str(mae)
    if state.get("realized_r") is not None:
        state["weighted_realized_pnl_pct_unlevered"] = str(
            D(state["realized_r"]) * (risk / entry) * D("100")
        )
    return state
