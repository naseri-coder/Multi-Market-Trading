"""Causal implementation of the MARC R2 Fresh Reversal Transition hypothesis."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_backtest.engine import (
    BacktestConfig,
    _simulate_trade,
    _wilder_atr,
)
from research_layer.marc_backtest.entities import BacktestWindowResult

D = Decimal

FRT_TIMEFRAME = "15m"
FRT_MAX_CROSS_AGE_BARS = 3
FRT_MA99_SLOPE_LOOKBACK = 5
FRT_MIN_INITIAL_RISK_PCT = D("0.006")


def _cross_direction(previous, current) -> str | None:
    if (
        previous.ma7 is None
        or previous.ma25 is None
        or current.ma7 is None
        or current.ma25 is None
    ):
        return None
    if previous.ma7 <= previous.ma25 and current.ma7 > current.ma25:
        return "LONG"
    if previous.ma7 >= previous.ma25 and current.ma7 < current.ma25:
        return "SHORT"
    return None


def _latest_cross_age(frames, index: int, direction: str) -> int | None:
    for cursor in range(index, 0, -1):
        if _cross_direction(frames[cursor - 1], frames[cursor]) == direction:
            return index - cursor
    return None


def _ma99_slope_is_opposed(frames, index: int, direction: str) -> bool:
    if index < FRT_MA99_SLOPE_LOOKBACK:
        return False
    current = frames[index]
    previous = frames[index - FRT_MA99_SLOPE_LOOKBACK]
    if current.ma99 is None or previous.ma99 is None or current.atr14 is None:
        return False
    if current.atr14 <= 0:
        return False
    slope = (current.ma99 - previous.ma99) / current.atr14 / D(
        FRT_MA99_SLOPE_LOOKBACK
    )
    if direction == "LONG":
        return slope < 0
    if direction == "SHORT":
        return slope > 0
    raise ValueError("direction must be LONG or SHORT")


def _risk_pct(entry: Decimal, stop: Decimal) -> Decimal:
    if entry <= 0:
        raise ValueError("entry must be positive")
    return abs(entry - stop) / entry


def backtest_fresh_reversal_window(
    *,
    candles: tuple[Candle, ...],
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig | None = None,
    policy: MARCPolicy | None = None,
) -> BacktestWindowResult:
    """Run the single pre-registered Fresh Reversal Transition setup."""
    if timeframe != FRT_TIMEFRAME:
        raise ValueError("MARC R2 FRT is a 15m-only research setup")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("window timestamps must be timezone-aware")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end <= start:
        raise ValueError("end must be after start")

    selected_config = config or BacktestConfig()
    selected_policy = policy or MARCPolicy()
    if len(candles) < selected_policy.minimum_indicator_bars + 1:
        raise ValueError("not enough candles for MARC R2 FRT")

    source = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe=timeframe,
        candles=candles,
        captured_at=candles[-1].close_time,
        source="MARC_R2_FRT_DATA",
    )
    frames = build_indicator_frames(source, policy=selected_policy)
    atr22 = _wilder_atr(candles, selected_policy.chandelier_atr_period)
    engine = MARCSignalEngine(policy=selected_policy)

    last_index = max(
        (i for i, candle in enumerate(candles) if candle.open_time < end),
        default=-1,
    )
    first_entry = next(
        (i for i, candle in enumerate(candles) if candle.open_time >= start),
        len(candles),
    )
    index = max(selected_policy.minimum_indicator_bars - 1, first_entry - 1)
    trades = []
    rejections: Counter[str] = Counter()
    candidates = 0

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
        if not probe.trade_ready or not probe.fresh or probe.direction is None:
            index += 1
            continue

        entry_index = index + 1
        entry_candle = candles[entry_index]
        if entry_candle.open_time < start:
            index += 1
            continue
        if entry_candle.open_time >= end:
            break
        candidates += 1

        cross_age = _latest_cross_age(frames, index, probe.direction)
        if cross_age is None or cross_age > FRT_MAX_CROSS_AGE_BARS:
            rejections["FRT_CROSS_NOT_FRESH"] += 1
            index += 1
            continue
        if not _ma99_slope_is_opposed(frames, index, probe.direction):
            rejections["FRT_MA99_SLOPE_NOT_OPPOSED"] += 1
            index += 1
            continue

        snapshot_start = max(0, index - selected_config.snapshot_window + 1)
        snapshot_candles = candles[snapshot_start : index + 1]
        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol=symbol.upper(),
            timeframe=timeframe,
            candles=snapshot_candles,
            captured_at=snapshot_candles[-1].close_time,
            source="MARC_R2_FRT_CAUSAL",
        )
        decision = evaluate_indicator_frames(
            suffix,
            symbol=symbol.upper(),
            timeframe=timeframe,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            policy=selected_policy,
        )
        plan = engine.build_entry_plan(
            snapshot,
            decision,
            entry_price=entry_candle.open,
        )
        if not plan.accepted or plan.candidate is None:
            rejections[plan.rejection_reason or "FRT_PLAN_REJECTED"] += 1
            index += 1
            continue

        if (
            _risk_pct(plan.candidate.entry_price, plan.candidate.stop_loss)
            < FRT_MIN_INITIAL_RISK_PCT
        ):
            rejections["FRT_INITIAL_RISK_TOO_TIGHT"] += 1
            index += 1
            continue

        trade, exit_index = _simulate_trade(
            candles=candles,
            atr22=atr22,
            candidate=plan.candidate,
            entry_index=entry_index,
            last_index=last_index,
            config=selected_config,
            policy=selected_policy,
        )
        trades.append(trade)
        index = max(index + 1, exit_index)

    return BacktestWindowResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        candidate_count=candidates,
        rejected_plan_count=sum(rejections.values()),
        rejection_reasons=tuple(sorted(rejections.items())),
        trades=tuple(trades),
    )
