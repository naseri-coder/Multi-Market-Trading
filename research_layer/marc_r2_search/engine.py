"""Causal MARC R2 experiments derived from the R1 diagnostic.

Only a small pre-registered variant set is permitted here. The purpose is to
turn descriptive R1 observations into rules that could actually have been
executed without future knowledge.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
from app.modules.marc_core.entities import MARCDecision, MARCState
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_backtest.engine import (
    BacktestConfig,
    _chandelier_level,
    _costed_r,
    _wilder_atr,
    backtest_window,
)
from research_layer.marc_backtest.entities import (
    BacktestTrade,
    BacktestWindowResult,
    TradeFill,
)

D = Decimal


class R2Variant(StrEnum):
    R1_BASELINE = "R1_BASELINE"
    EARLY_MA99_LOSS_3 = "EARLY_MA99_LOSS_3"
    EARLY_OPPOSITE_BAND_3 = "EARLY_OPPOSITE_BAND_3"
    HOLD_MA99_3_THEN_ENTER = "HOLD_MA99_3_THEN_ENTER"


@dataclass(frozen=True, slots=True)
class _ExperimentCandidate:
    symbol: str
    timeframe: str
    direction: str
    source_signal_id: str
    entry_price: Decimal
    stop_loss: Decimal
    targets: tuple[Decimal, Decimal]


def _failure_on_close(
    *,
    variant: R2Variant,
    direction: str,
    close: Decimal,
    ma99: Decimal,
    atr14: Decimal,
    policy: MARCPolicy,
) -> bool:
    if variant == R2Variant.EARLY_MA99_LOSS_3:
        return close < ma99 if direction == "LONG" else close > ma99
    if variant == R2Variant.EARLY_OPPOSITE_BAND_3:
        band = policy.ma99_band_atr * atr14
        return (
            close < ma99 - band
            if direction == "LONG"
            else close > ma99 + band
        )
    return False


def _simulate_with_early_failure(
    *,
    candles: tuple[Candle, ...],
    frames,
    atr22: tuple[Decimal | None, ...],
    candidate,
    entry_index: int,
    last_index: int,
    config: BacktestConfig,
    policy: MARCPolicy,
    variant: R2Variant,
) -> tuple[BacktestTrade, int]:
    if variant not in {
        R2Variant.EARLY_MA99_LOSS_3,
        R2Variant.EARLY_OPPOSITE_BAND_3,
    }:
        raise ValueError("early-failure simulator requires an early-exit variant")

    direction = candidate.direction
    entry = candidate.entry_price
    stop = candidate.stop_loss
    tp1, tp2 = candidate.targets
    tp1_fraction = D(str(config.tp1_fraction))
    tp2_fraction = D(str(config.tp2_fraction))
    remaining = D("1")
    tp1_hit = False
    tp2_hit = False
    runner_active = False
    trail: Decimal | None = None
    pending_thesis_exit = False
    fills_raw: list[tuple[Decimal, Decimal]] = []
    fills: list[TradeFill] = []
    terminal_reason = "WINDOW_END"
    exit_index = last_index

    def fill(
        candle: Candle,
        price: Decimal,
        fraction: Decimal,
        reason: str,
        *,
        at_open: bool = False,
    ) -> None:
        nonlocal remaining
        if fraction <= 0 or fraction > remaining:
            raise RuntimeError("invalid MARC R2 fill fraction")
        fills_raw.append((fraction, price))
        fills.append(
            TradeFill(
                time=candle.open_time if at_open else candle.close_time,
                price=float(price),
                fraction=float(fraction),
                reason=reason,
            )
        )
        remaining -= fraction

    def target_fill(
        candle: Candle,
        price: Decimal,
        fraction: Decimal,
        reason: str,
        *,
        at_open: bool = False,
    ) -> None:
        nonlocal tp1_hit, tp2_hit
        actual_fraction = min(fraction, remaining)
        fill(candle, price, actual_fraction, reason, at_open=at_open)
        if reason == "TP1":
            tp1_hit = True
        elif reason == "TP2":
            tp2_hit = True
        else:
            raise RuntimeError("unknown MARC R2 target fill")

    for index in range(entry_index, last_index + 1):
        candle = candles[index]

        if pending_thesis_exit:
            fill(candle, candle.open, remaining, "EARLY_THESIS_EXIT", at_open=True)
            terminal_reason = "EARLY_THESIS_EXIT"
            exit_index = index
            break

        effective_stop = stop
        if runner_active and trail is not None:
            if direction == "LONG":
                effective_stop = max(effective_stop, trail)
            else:
                effective_stop = min(effective_stop, trail)

        if direction == "LONG":
            if candle.open <= effective_stop:
                fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                terminal_reason = "STOP_GAP"
                exit_index = index
                break
            gap_targets = []
            if not tp1_hit and candle.open >= tp1:
                gap_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.open >= tp2:
                gap_targets.append((tp2, tp2_fraction, "TP2"))
        else:
            if candle.open >= effective_stop:
                fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                terminal_reason = "STOP_GAP"
                exit_index = index
                break
            gap_targets = []
            if not tp1_hit and candle.open <= tp1:
                gap_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.open <= tp2:
                gap_targets.append((tp2, tp2_fraction, "TP2"))

        for price, fraction, reason in gap_targets:
            target_fill(candle, price, fraction, reason, at_open=True)

        if tp2_hit and not runner_active:
            runner_active = True
            if trail is not None:
                if direction == "LONG":
                    effective_stop = max(effective_stop, trail)
                    breached = candle.open <= effective_stop
                else:
                    effective_stop = min(effective_stop, trail)
                    breached = candle.open >= effective_stop
                if breached:
                    fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                    terminal_reason = "STOP_GAP"
                    exit_index = index
                    break

        pending_targets = []
        if direction == "LONG":
            if not tp1_hit and candle.high >= tp1:
                pending_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.high >= tp2:
                pending_targets.append((tp2, tp2_fraction, "TP2"))
            stop_touched = candle.low <= effective_stop
        else:
            if not tp1_hit and candle.low <= tp1:
                pending_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.low <= tp2:
                pending_targets.append((tp2, tp2_fraction, "TP2"))
            stop_touched = candle.high >= effective_stop

        if stop_touched and pending_targets:
            fill(candle, effective_stop, remaining, "STOP_FIRST_AMBIGUOUS")
            terminal_reason = "STOP_FIRST_AMBIGUOUS"
            exit_index = index
            break
        if stop_touched:
            reason = "TRAIL_STOP" if runner_active else "STOP"
            fill(candle, effective_stop, remaining, reason)
            terminal_reason = reason
            exit_index = index
            break

        for price, fraction, reason in pending_targets:
            target_fill(candle, price, fraction, reason)
            if remaining == 0:
                terminal_reason = reason
                exit_index = index
                break
        if remaining == 0:
            break

        raw_trail = _chandelier_level(
            candles=candles,
            atr=atr22,
            index=index,
            direction=direction,
            length=policy.chandelier_length,
            multiplier=policy.chandelier_multiplier,
        )
        if raw_trail is not None:
            if trail is None:
                trail = raw_trail
            elif direction == "LONG":
                trail = max(trail, raw_trail)
            else:
                trail = min(trail, raw_trail)
        if tp2_hit:
            runner_active = True

        bars_from_entry = index - entry_index + 1
        if bars_from_entry <= 3 and index < last_index:
            frame = frames[index]
            if frame.ma99 is not None and frame.atr14 is not None:
                pending_thesis_exit = _failure_on_close(
                    variant=variant,
                    direction=direction,
                    close=candle.close,
                    ma99=frame.ma99,
                    atr14=frame.atr14,
                    policy=policy,
                )

    if remaining > 0:
        candle = candles[last_index]
        fill(candle, candle.close, remaining, "WINDOW_END")
        terminal_reason = "WINDOW_END"
        exit_index = last_index

    if abs(sum(fraction for fraction, _ in fills_raw) - D("1")) > D("0.0000001"):
        raise RuntimeError("MARC R2 trade did not close exactly one position")

    gross_r = _costed_r(
        direction=direction,
        entry=entry,
        stop=stop,
        fills=fills_raw,
        cost_bps_per_side=0.0,
    )
    base_net_r = _costed_r(
        direction=direction,
        entry=entry,
        stop=stop,
        fills=fills_raw,
        cost_bps_per_side=config.base_cost_bps_per_side,
    )
    stress_net_r = _costed_r(
        direction=direction,
        entry=entry,
        stop=stop,
        fills=fills_raw,
        cost_bps_per_side=config.stress_cost_bps_per_side,
    )
    return (
        BacktestTrade(
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            direction=direction,
            source_signal_id=candidate.source_signal_id,
            entry_time=candles[entry_index].open_time,
            entry_price=float(entry),
            stop_loss=float(stop),
            exit_time=fills[-1].time,
            duration_bars=exit_index - entry_index + 1,
            fills=tuple(fills),
            gross_r=gross_r,
            base_net_r=base_net_r,
            stress_net_r=stress_net_r,
            tp1_hit=tp1_hit,
            tp2_hit=tp2_hit,
            terminal_reason=terminal_reason,
        ),
        exit_index,
    )


def _fresh_decision(
    *,
    frames,
    index: int,
    symbol: str,
    timeframe: str,
    config: BacktestConfig,
    policy: MARCPolicy,
):
    suffix_start = max(0, index - config.scan_lookback + 1)
    suffix = frames[suffix_start : index + 1]
    return evaluate_indicator_frames(
        suffix,
        symbol=symbol.upper(),
        timeframe=timeframe,
        snapshot_id=f"probe:{symbol}:{timeframe}:{index}",
        snapshot_hash=f"probe:{index}",
        policy=policy,
    )


def _snapshot_for_index(
    *,
    candles: tuple[Candle, ...],
    index: int,
    symbol: str,
    timeframe: str,
    config: BacktestConfig,
) -> MarketSnapshot:
    start = max(0, index - config.snapshot_window + 1)
    items = candles[start : index + 1]
    return MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe=timeframe,
        candles=items,
        captured_at=items[-1].close_time,
        source="MARC_R2_CAUSAL_SEARCH",
    )


def _delayed_hold_plan(
    *,
    engine: MARCSignalEngine,
    snapshot: MarketSnapshot,
    frame,
    direction: str,
    entry_price: Decimal,
) -> object:
    state = MARCState.LONG_READY if direction == "LONG" else MARCState.SHORT_READY
    decision = MARCDecision(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        state=state,
        direction=direction,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_hash,
        cross_index=None,
        confirmation_index=len(snapshot.candles) - 1,
        persistence_count=3,
        ma7=frame.ma7,
        ma25=frame.ma25,
        ma99=frame.ma99,
        atr14=frame.atr14,
        normalized_spread_atr=None,
        extension_atr=None,
        fresh=True,
        reason="R2 causal three-bar MA99 hold completed",
    )
    return engine.build_entry_plan(snapshot, decision, entry_price=entry_price)


def backtest_r2_variant_window(
    *,
    candles: tuple[Candle, ...],
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    variant: R2Variant,
    config: BacktestConfig | None = None,
    policy: MARCPolicy | None = None,
) -> BacktestWindowResult:
    """Run one pre-registered R2 variant with causal next-open actions."""
    if variant == R2Variant.R1_BASELINE:
        return backtest_window(
            candles=candles,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            config=config,
            policy=policy,
        )

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("window timestamps must be timezone-aware")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    selected_config = config or BacktestConfig()
    selected_policy = policy or MARCPolicy()
    selected_policy.cross_validity_bars(timeframe)
    if len(candles) < selected_policy.minimum_indicator_bars + 4:
        raise ValueError("not enough candles for MARC R2 experiment")

    source = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe=timeframe,
        candles=candles,
        captured_at=candles[-1].close_time,
        source="MARC_R2_EXPERIMENT_DATA",
    )
    frames = build_indicator_frames(source, policy=selected_policy)
    atr22 = _wilder_atr(candles, selected_policy.chandelier_atr_period)
    engine = MARCSignalEngine(policy=selected_policy)

    last_index = max(
        (index for index, candle in enumerate(candles) if candle.open_time < end),
        default=-1,
    )
    first_entry = next(
        (index for index, candle in enumerate(candles) if candle.open_time >= start),
        len(candles),
    )
    index = max(selected_policy.minimum_indicator_bars - 1, first_entry - 1)
    trades: list[BacktestTrade] = []
    rejections: Counter[str] = Counter()
    candidate_count = 0

    while index < last_index:
        probe = _fresh_decision(
            frames=frames,
            index=index,
            symbol=symbol,
            timeframe=timeframe,
            config=selected_config,
            policy=selected_policy,
        )
        if not probe.trade_ready or not probe.fresh or probe.direction is None:
            index += 1
            continue

        if variant == R2Variant.HOLD_MA99_3_THEN_ENTER:
            hold_end = index + 3
            delayed_entry_index = hold_end + 1
            if delayed_entry_index > last_index:
                break
            held = True
            for hold_index in range(index + 1, hold_end + 1):
                frame = frames[hold_index]
                if frame.ma99 is None:
                    held = False
                    break
                if probe.direction == "LONG":
                    held = candles[hold_index].close > frame.ma99
                else:
                    held = candles[hold_index].close < frame.ma99
                if not held:
                    break
            candidate_count += 1
            if not held:
                rejections["THREE_BAR_MA99_HOLD_FAILED"] += 1
                index += 1
                continue
            delayed_entry = candles[delayed_entry_index]
            if delayed_entry.open_time < start:
                index += 1
                continue
            if delayed_entry.open_time >= end:
                break
            snapshot = _snapshot_for_index(
                candles=candles,
                index=hold_end,
                symbol=symbol,
                timeframe=timeframe,
                config=selected_config,
            )
            plan = _delayed_hold_plan(
                engine=engine,
                snapshot=snapshot,
                frame=frames[hold_end],
                direction=probe.direction,
                entry_price=delayed_entry.open,
            )
            if not plan.accepted or plan.candidate is None:
                rejections[plan.rejection_reason or "DELAYED_PLAN_REJECTED"] += 1
                index = hold_end
                continue
            trade, exit_index = _simulate_trade_baseline(
                candles=candles,
                atr22=atr22,
                candidate=plan.candidate,
                entry_index=delayed_entry_index,
                last_index=last_index,
                config=selected_config,
                policy=selected_policy,
            )
            trades.append(trade)
            index = max(hold_end + 1, exit_index)
            continue

        entry_index = index + 1
        entry = candles[entry_index]
        if entry.open_time < start:
            index += 1
            continue
        if entry.open_time >= end:
            break
        candidate_count += 1
        snapshot = _snapshot_for_index(
            candles=candles,
            index=index,
            symbol=symbol,
            timeframe=timeframe,
            config=selected_config,
        )
        decision = evaluate_indicator_frames(
            frames[max(0, index - selected_config.scan_lookback + 1) : index + 1],
            symbol=symbol.upper(),
            timeframe=timeframe,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            policy=selected_policy,
        )
        plan = engine.build_entry_plan(snapshot, decision, entry_price=entry.open)
        if not plan.accepted or plan.candidate is None:
            rejections[plan.rejection_reason or "UNKNOWN_REJECTION"] += 1
            index += 1
            continue

        trade, exit_index = _simulate_with_early_failure(
            candles=candles,
            frames=frames,
            atr22=atr22,
            candidate=plan.candidate,
            entry_index=entry_index,
            last_index=last_index,
            config=selected_config,
            policy=selected_policy,
            variant=variant,
        )
        trades.append(trade)
        index = max(index + 1, exit_index)

    return BacktestWindowResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        candidate_count=candidate_count,
        rejected_plan_count=sum(rejections.values()),
        rejection_reasons=tuple(sorted(rejections.items())),
        trades=tuple(trades),
    )


def _simulate_trade_baseline(**kwargs):
    # Late import avoids exposing the baseline implementation as an R2 rule.
    from research_layer.marc_backtest.engine import _simulate_trade

    return _simulate_trade(**kwargs)
