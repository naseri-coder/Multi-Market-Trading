"""Causal/non-repainting swing infrastructure.

IMPORTANT:
- The source supports HH/HL vs LH/LL as market-structure concepts (BR-031).
- The source does NOT specify the numeric swing-confirmation algorithm (EH-002).
- Therefore `left_bars` / `right_bars` are explicit engineering parameters and this
  module must never present them as Brooks-authored thresholds.
"""

from __future__ import annotations

from app.modules.brooks_core.structure_entities import (
    ConfirmedSwing,
    StructureEvaluation,
    SwingScanResult,
)
from app.modules.market_data.entities import Candle


def confirm_swings_causally(
    candles: tuple[Candle, ...],
    *,
    left_bars: int,
    right_bars: int,
) -> SwingScanResult:
    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars and right_bars must be >= 1")

    swings: list[ConfirmedSwing] = []
    ambiguous: list[int] = []

    last_candidate = len(candles) - right_bars
    for i in range(left_bars, last_candidate):
        current = candles[i]
        left = candles[i - left_bars : i]
        right = candles[i + 1 : i + 1 + right_bars]

        high_values = tuple(c.high for c in (*left, *right))
        low_values = tuple(c.low for c in (*left, *right))

        strict_high = all(current.high > value for value in high_values)
        strict_low = all(current.low < value for value in low_values)

        high_tie = any(current.high == value for value in high_values)
        low_tie = any(current.low == value for value in low_values)

        if high_tie or low_tie:
            ambiguous.append(i)

        if strict_high:
            swings.append(
                ConfirmedSwing(
                    kind="HIGH",
                    candle_index=i,
                    confirmed_at_index=i + right_bars,
                    price=current.high,
                )
            )
        if strict_low:
            swings.append(
                ConfirmedSwing(
                    kind="LOW",
                    candle_index=i,
                    confirmed_at_index=i + right_bars,
                    price=current.low,
                )
            )

    swings.sort(key=lambda item: (item.candle_index, item.kind))
    return SwingScanResult(
        swings=tuple(swings),
        ambiguous_indices=tuple(sorted(set(ambiguous))),
        left_bars=left_bars,
        right_bars=right_bars,
    )


def evaluate_br031_structure(
    scan: SwingScanResult,
) -> StructureEvaluation:
    """Apply BR-031 only to already-confirmed engineering swing points.

    This function does not claim that the swing algorithm itself comes from Brooks.
    """
    highs = [s for s in scan.swings if s.kind == "HIGH"]
    lows = [s for s in scan.swings if s.kind == "LOW"]

    if len(highs) < 2 or len(lows) < 2:
        return StructureEvaluation(
            direction="AMBIGUOUS",
            reason="insufficient confirmed swings for HH/HL or LH/LL evaluation",
        )

    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]

    bull = h2.price > h1.price and l2.price > l1.price
    bear = h2.price < h1.price and l2.price < l1.price

    support = (h1.candle_index, h2.candle_index, l1.candle_index, l2.candle_index)

    if bull:
        return StructureEvaluation(
            direction="BULL_TREND",
            reason="BR-031 HH/HL progression on confirmed engineering swings",
            supporting_swing_indices=support,
        )
    if bear:
        return StructureEvaluation(
            direction="BEAR_TREND",
            reason="BR-031 LH/LL progression on confirmed engineering swings",
            supporting_swing_indices=support,
        )
    return StructureEvaluation(
        direction="AMBIGUOUS",
        reason="confirmed swings do not form both HH/HL or both LH/LL",
        supporting_swing_indices=support,
    )
