"""Causal H2/L2-like second-entry detector.

Source basis:
- PDF p11: bull trend, look for High 2 (H2), two legs sideways-to-down, buy stop
  above signal-bar high.
- PDF p12: bear trend, look for Low 2 (L2), two legs sideways-to-up, sell stop
  below signal-bar low.

The source does not specify all inside/outside/equal-boundary counting edge cases.
This implementation therefore:
- reuses the Phase 7B fail-closed guard;
- uses a simple causal two-countertrend-leg state machine;
- labels the result H2_CONFIRMED / L2_CONFIRMED rather than claiming a complete
  reproduction of every Brooks counting convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.brooks_core.pullback_guard import (
    assess_h1_h2_l1_l2_counting_window,
)
from app.modules.market_data.entities import Candle

SetupDirection = Literal["LONG", "SHORT"]


@dataclass(frozen=True, slots=True)
class SecondEntrySetup:
    direction: SetupDirection
    setup_type: str
    start_index: int
    signal_index: int
    countertrend_legs: int
    source_pages: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SecondEntryAssessment:
    setup: SecondEntrySetup | None
    reason: str
    blocked_indices: tuple[int, ...] = ()


def detect_second_entry(
    candles: tuple[Candle, ...],
    *,
    trend_direction: str,
    start_index: int,
) -> SecondEntryAssessment:
    if trend_direction not in {"BULL_TREND", "BEAR_TREND"}:
        return SecondEntryAssessment(None, "resolved bull/bear trend required")
    if start_index < 0 or start_index >= len(candles) - 1:
        return SecondEntryAssessment(None, "invalid pullback start index")

    window = candles[start_index:]
    guard = assess_h1_h2_l1_l2_counting_window(window)
    if not guard.allowed:
        return SecondEntryAssessment(
            setup=None,
            reason=guard.reason,
            blocked_indices=tuple(start_index + i for i in guard.blocked_indices),
        )

    countertrend_legs = 0
    in_countertrend_leg = False
    last_index = len(candles) - 1

    for i in range(start_index + 1, len(candles)):
        previous = candles[i - 1]
        current = candles[i]

        if trend_direction == "BULL_TREND":
            moved_against_trend = current.low < previous.low
            resume_attempt = current.high > previous.high
        else:
            moved_against_trend = current.high > previous.high
            resume_attempt = current.low < previous.low

        if moved_against_trend and not in_countertrend_leg:
            countertrend_legs += 1
            in_countertrend_leg = True

        if resume_attempt and in_countertrend_leg:
            if i == last_index and countertrend_legs >= 2:
                if trend_direction == "BULL_TREND":
                    return SecondEntryAssessment(
                        SecondEntrySetup(
                            direction="LONG",
                            setup_type="H2_CONFIRMED",
                            start_index=start_index,
                            signal_index=i,
                            countertrend_legs=countertrend_legs,
                            source_pages=(11,),
                        ),
                        "two causal sideways/down legs followed by second up-resumption attempt",
                    )
                return SecondEntryAssessment(
                    SecondEntrySetup(
                        direction="SHORT",
                        setup_type="L2_CONFIRMED",
                        start_index=start_index,
                        signal_index=i,
                        countertrend_legs=countertrend_legs,
                        source_pages=(12,),
                    ),
                    "two causal sideways/up legs followed by second down-resumption attempt",
                )
            in_countertrend_leg = False

    return SecondEntryAssessment(
        setup=None,
        reason=f"no second-entry setup at final closed bar; legs={countertrend_legs}",
    )
