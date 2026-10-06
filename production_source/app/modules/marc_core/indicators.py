"""Deterministic Decimal indicators for MARC."""

from __future__ import annotations

from decimal import Decimal

from app.modules.market_data.entities import MarketSnapshot

from app.modules.marc_core.entities import MARCIndicatorFrame
from app.modules.marc_core.policy import MARCPolicy


def _rolling_sma(values: tuple[Decimal, ...], period: int) -> tuple[Decimal | None, ...]:
    output: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return tuple(output)
    running = sum(values[:period], Decimal("0"))
    output[period - 1] = running / Decimal(period)
    for index in range(period, len(values)):
        running += values[index] - values[index - period]
        output[index] = running / Decimal(period)
    return tuple(output)


def _wilder_atr(snapshot: MarketSnapshot, period: int) -> tuple[Decimal | None, ...]:
    candles = snapshot.candles
    output: list[Decimal | None] = [None] * len(candles)
    if len(candles) <= period:
        return tuple(output)

    true_ranges: list[Decimal] = [Decimal("0")]
    for index in range(1, len(candles)):
        current = candles[index]
        previous_close = candles[index - 1].close
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous_close),
                abs(current.low - previous_close),
            )
        )

    first = sum(true_ranges[1 : period + 1], Decimal("0")) / Decimal(period)
    output[period] = first
    previous_atr = first
    for index in range(period + 1, len(candles)):
        previous_atr = (
            previous_atr * Decimal(period - 1) + true_ranges[index]
        ) / Decimal(period)
        output[index] = previous_atr
    return tuple(output)


def build_indicator_frames(
    snapshot: MarketSnapshot,
    *,
    policy: MARCPolicy | None = None,
) -> tuple[MARCIndicatorFrame, ...]:
    """Calculate the frozen SMA 7/25/99 and Wilder ATR14 series."""
    selected = policy or MARCPolicy()
    closes = tuple(candle.close for candle in snapshot.candles)
    ma7 = _rolling_sma(closes, selected.fast_period)
    ma25 = _rolling_sma(closes, selected.medium_period)
    ma99 = _rolling_sma(closes, selected.regime_period)
    atr14 = _wilder_atr(snapshot, selected.atr_period)

    return tuple(
        MARCIndicatorFrame(
            index=index,
            close_time=candle.close_time,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            ma7=ma7[index],
            ma25=ma25[index],
            ma99=ma99[index],
            atr14=atr14[index],
        )
        for index, candle in enumerate(snapshot.candles)
    )
