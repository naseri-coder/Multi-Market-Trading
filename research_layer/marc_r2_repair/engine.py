"""Causal MARC R2 exit-repair experiments.

The entry signal remains the frozen R1 signal. These variants test whether R1
was losing edge through trade management rather than signal detection.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
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


class RepairVariant(StrEnum):
    R1_BASELINE = "R1_BASELINE"
    PARTIAL25_BE_AFTER_1R = "PARTIAL25_BE_AFTER_1R"
    FULL_BE_AFTER_1R_TP2_50_RUNNER50 = "FULL_BE_AFTER_1R_TP2_50_RUNNER50"
    FULL_BE_TP2_50_RUNNER50_COST_BUDGET = (
        "FULL_BE_TP2_50_RUNNER50_COST_BUDGET"
    )


def _stress_roundtrip_drag_r(
    *,
    entry: Decimal,
    stop: Decimal,
    stress_cost_bps_per_side: float,
) -> Decimal:
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("risk must be positive")
    bps = D(str(stress_cost_bps_per_side)) / D("10000")
    return (D("2") * entry * bps) / risk


def _cost_budget_passes(
    *,
    entry: Decimal,
    stop: Decimal,
    config: BacktestConfig,
    max_stress_drag_r: Decimal = D("0.25"),
) -> bool:
    return (
        _stress_roundtrip_drag_r(
            entry=entry,
            stop=stop,
            stress_cost_bps_per_side=config.stress_cost_bps_per_side,
        )
        <= max_stress_drag_r
    )


def _simulate_repaired_trade(
    *,
    candles: tuple[Candle, ...],
    atr22: tuple[Decimal | None, ...],
    candidate,
    entry_index: int,
    last_index: int,
    config: BacktestConfig,
    policy: MARCPolicy,
    variant: RepairVariant,
) -> tuple[BacktestTrade, int]:
    if variant == RepairVariant.R1_BASELINE:
        raise ValueError("baseline must use the frozen R1 simulator")

    direction = candidate.direction
    entry = candidate.entry_price
    stop = candidate.stop_loss
    tp1, tp2 = candidate.targets
    partial_tp1 = variant == RepairVariant.PARTIAL25_BE_AFTER_1R
    tp1_fraction = D("0.25") if partial_tp1 else D("0")
    tp2_fraction = D("0.25") if partial_tp1 else D("0.50")

    remaining = D("1")
    tp1_hit = False
    tp2_hit = False
    be_active = False
    be_pending = False
    runner_active = False
    trail: Decimal | None = None
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
            raise RuntimeError("invalid MARC R2 repair fill fraction")
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

    def mark_tp1(candle: Candle, *, at_open: bool = False) -> None:
        nonlocal tp1_hit, be_pending
        if tp1_hit:
            return
        tp1_hit = True
        be_pending = True
        if tp1_fraction > 0:
            fill(candle, tp1, min(tp1_fraction, remaining), "TP1", at_open=at_open)

    def fill_tp2(candle: Candle, *, at_open: bool = False) -> None:
        nonlocal tp2_hit
        if tp2_hit:
            return
        if not tp1_hit:
            mark_tp1(candle, at_open=at_open)
        tp2_hit = True
        fill(candle, tp2, min(tp2_fraction, remaining), "TP2", at_open=at_open)

    for index in range(entry_index, last_index + 1):
        candle = candles[index]

        if be_pending:
            be_active = True
            be_pending = False

        effective_stop = stop
        if be_active:
            if direction == "LONG":
                effective_stop = max(effective_stop, entry)
            else:
                effective_stop = min(effective_stop, entry)
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
            tp1_gap = not tp1_hit and candle.open >= tp1
            tp2_gap = not tp2_hit and candle.open >= tp2
        else:
            if candle.open >= effective_stop:
                fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                terminal_reason = "STOP_GAP"
                exit_index = index
                break
            tp1_gap = not tp1_hit and candle.open <= tp1
            tp2_gap = not tp2_hit and candle.open <= tp2

        if tp1_gap:
            mark_tp1(candle, at_open=True)
        if tp2_gap:
            fill_tp2(candle, at_open=True)

        # TP2 filled at the open deterministically precedes later intrabar
        # movement. A prior closed-bar Chandelier level can therefore protect
        # the runner immediately.
        if tp2_hit and not runner_active:
            runner_active = True
            if trail is not None:
                if direction == "LONG":
                    effective_stop = max(effective_stop, trail)
                    breached = candle.open <= effective_stop
                else:
                    effective_stop = min(effective_stop, trail)
                    breached = candle.open >= effective_stop
                if breached and remaining > 0:
                    fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                    terminal_reason = "STOP_GAP"
                    exit_index = index
                    break

        if direction == "LONG":
            tp1_touch = not tp1_hit and candle.high >= tp1
            tp2_touch = not tp2_hit and candle.high >= tp2
            stop_touch = candle.low <= effective_stop
        else:
            tp1_touch = not tp1_hit and candle.low <= tp1
            tp2_touch = not tp2_hit and candle.low <= tp2
            stop_touch = candle.high >= effective_stop

        target_touch = tp1_touch or tp2_touch
        if stop_touch and target_touch:
            fill(candle, effective_stop, remaining, "STOP_FIRST_AMBIGUOUS")
            terminal_reason = "STOP_FIRST_AMBIGUOUS"
            exit_index = index
            break
        if stop_touch:
            reason = "TRAIL_STOP" if runner_active else (
                "BREAK_EVEN_STOP" if be_active else "STOP"
            )
            fill(candle, effective_stop, remaining, reason)
            terminal_reason = reason
            exit_index = index
            break

        if tp1_touch:
            mark_tp1(candle)
        if tp2_touch:
            fill_tp2(candle)

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

    if remaining > 0:
        candle = candles[last_index]
        fill(candle, candle.close, remaining, "WINDOW_END")
        terminal_reason = "WINDOW_END"
        exit_index = last_index

    if abs(sum(fraction for fraction, _ in fills_raw) - D("1")) > D("0.0000001"):
        raise RuntimeError("MARC R2 repaired trade did not close one position")

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


def backtest_repair_variant_window(
    *,
    candles: tuple[Candle, ...],
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    variant: RepairVariant,
    config: BacktestConfig | None = None,
    policy: MARCPolicy | None = None,
) -> BacktestWindowResult:
    """Run one pre-registered trade-management variant causally."""
    if variant == RepairVariant.R1_BASELINE:
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

    source = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe=timeframe,
        candles=candles,
        captured_at=candles[-1].close_time,
        source="MARC_R2_REPAIR_DATA",
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
        suffix_start = max(0, index - selected_config.scan_lookback + 1)
        suffix = frames[suffix_start : index + 1]
        probe = evaluate_indicator_frames(
            suffix,
            symbol=symbol.upper(),
            timeframe=timeframe,
            snapshot_id=f"probe:{symbol}:{timeframe}:{index}",
            snapshot_hash=f"probe:{index}",
            policy=selected_policy,
        )
        if not probe.trade_ready or not probe.fresh:
            index += 1
            continue

        entry_index = index + 1
        entry_candle = candles[entry_index]
        if entry_candle.open_time < start:
            index += 1
            continue
        if entry_candle.open_time >= end:
            break

        snapshot_start = max(0, index - selected_config.snapshot_window + 1)
        snapshot_candles = candles[snapshot_start : index + 1]
        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol=symbol.upper(),
            timeframe=timeframe,
            candles=snapshot_candles,
            captured_at=snapshot_candles[-1].close_time,
            source="MARC_R2_REPAIR_CAUSAL",
        )
        decision = evaluate_indicator_frames(
            suffix,
            symbol=symbol.upper(),
            timeframe=timeframe,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            policy=selected_policy,
        )
        candidate_count += 1
        plan = engine.build_entry_plan(
            snapshot,
            decision,
            entry_price=entry_candle.open,
        )
        if not plan.accepted or plan.candidate is None:
            rejections[plan.rejection_reason or "UNKNOWN_REJECTION"] += 1
            index += 1
            continue

        if variant == RepairVariant.FULL_BE_TP2_50_RUNNER50_COST_BUDGET:
            if not _cost_budget_passes(
                entry=plan.candidate.entry_price,
                stop=plan.candidate.stop_loss,
                config=selected_config,
            ):
                rejections["STRESS_COST_BUDGET_EXCEEDED"] += 1
                index += 1
                continue

        trade, exit_index = _simulate_repaired_trade(
            candles=candles,
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
