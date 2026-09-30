"""Conservative guardrails before future H1/H2/L1/L2 counting.

EH-006 remains unresolved. This module intentionally does NOT count H1/H2/L1/L2.
It only identifies bar relationships that the existing source catalog says are explicit
(inside/outside bars) or engineering-sensitive (equal boundaries), and blocks counting
when such edge cases occur.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.brooks_core.source_rules import (
    evaluate_br010_inside_bar,
    evaluate_br011_outside_bar,
)
from app.modules.market_data.entities import Candle


@dataclass(frozen=True, slots=True)
class PullbackCountingGuard:
    allowed: bool
    reason: str
    blocked_indices: tuple[int, ...] = ()


def assess_h1_h2_l1_l2_counting_window(
    candles: tuple[Candle, ...],
) -> PullbackCountingGuard:
    if len(candles) < 2:
        return PullbackCountingGuard(
            allowed=False,
            reason="at least two bars are required",
        )

    blocked: list[int] = []
    for i in range(1, len(candles)):
        previous = candles[i - 1]
        current = candles[i]

        inside = evaluate_br010_inside_bar(current, previous).status == "PASS"
        outside = evaluate_br011_outside_bar(current, previous).status == "PASS"
        equal_high = current.high == previous.high
        equal_low = current.low == previous.low

        if inside or outside or equal_high or equal_low:
            blocked.append(i)

    if blocked:
        return PullbackCountingGuard(
            allowed=False,
            reason=(
                "EH-006 unresolved edge case present; H1/H2/L1/L2 counting "
                "must remain fail-closed"
            ),
            blocked_indices=tuple(blocked),
        )

    return PullbackCountingGuard(
        allowed=True,
        reason=(
            "window has no detected inside/outside/equal-boundary edge case; "
            "this does not itself define H1/H2/L1/L2"
        ),
    )
