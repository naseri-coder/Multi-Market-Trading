from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.modules.market_data.entities import Candle


def average_true_range(
    candles: Sequence[Candle],
    *,
    period: int = 14,
) -> Decimal:
    """Return the arithmetic mean of recent causal true ranges."""
    if period < 14:
        raise ValueError("ATR period must be at least 14 candles")
    if len(candles) < period:
        raise ValueError(
            f"ATR requires at least {period} closed candles; got {len(candles)}"
        )

    true_ranges: list[Decimal] = []
    for index, candle in enumerate(candles):
        if index == 0:
            true_range = candle.high - candle.low
        else:
            previous_close = candles[index - 1].close
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(true_range)

    recent = true_ranges[-period:]
    return sum(recent, Decimal("0")) / Decimal(period)


def average_bar_range(
    candles: Sequence[Candle],
    *,
    period: int,
) -> Decimal:
    """Return the arithmetic mean high-low range of the latest closed bars."""
    if period < 1:
        raise ValueError("bar-range period must be positive")
    if len(candles) < period:
        raise ValueError(
            f"average bar range requires at least {period} closed candles; got {len(candles)}"
        )
    recent = candles[-period:]
    return sum((c.high - c.low for c in recent), Decimal("0")) / Decimal(period)
