"""Typed causal market-structure primitives for Phase 7B.

These are engineering infrastructure, not new Brooks rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

SwingKind = Literal["HIGH", "LOW"]
StructureDirection = Literal["BULL_TREND", "BEAR_TREND", "AMBIGUOUS"]


@dataclass(frozen=True, slots=True)
class ConfirmedSwing:
    kind: SwingKind
    candle_index: int
    confirmed_at_index: int
    price: Decimal

    def __post_init__(self) -> None:
        if self.candle_index < 0:
            raise ValueError("candle_index must be non-negative")
        if self.confirmed_at_index < self.candle_index:
            raise ValueError("confirmed_at_index cannot precede candle_index")
        if self.price <= 0:
            raise ValueError("swing price must be positive")


@dataclass(frozen=True, slots=True)
class SwingScanResult:
    swings: tuple[ConfirmedSwing, ...]
    ambiguous_indices: tuple[int, ...]
    left_bars: int
    right_bars: int


@dataclass(frozen=True, slots=True)
class StructureEvaluation:
    direction: StructureDirection
    reason: str
    supporting_swing_indices: tuple[int, ...] = ()
