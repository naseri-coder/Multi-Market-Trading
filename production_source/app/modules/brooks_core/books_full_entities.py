"""Typed entities for the Brooks trilogy full-core detector.

This module is deliberately strategy-family oriented.  It lets the core represent
trend continuation, breakout, trading-range and reversal setups separately instead of
forcing every pattern through an H2/L2 state machine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Direction = Literal["LONG", "SHORT"]
SetupFamily = Literal[
    "TREND_CONTINUATION",
    "BREAKOUT",
    "BREAKOUT_PULLBACK",
    "FAILED_BREAKOUT",
    "FAILED_FAILURE",
    "TRADING_RANGE_FADE",
    "MAJOR_TREND_REVERSAL",
    "WEDGE_REVERSAL",
    "CLIMACTIC_REVERSAL",
    "FINAL_FLAG_REVERSAL",
    "DOUBLE_TOP_BOTTOM_REVERSAL",
]
Taxonomy = Literal["SOURCE_RULE", "SOURCE_INTERPRETATION", "ENGINEERING_POLICY"]


@dataclass(frozen=True, slots=True)
class BrooksPatternCandidate:
    direction: Direction
    setup_type: str
    family: SetupFamily
    signal_index: int
    reasons: tuple[str, ...]
    source_rule_ids: tuple[str, ...]
    taxonomy: Taxonomy
    priority: int
    context_required: str
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.signal_index < 0:
            raise ValueError("signal_index must be >= 0")
        if len(set(self.reasons)) < 2:
            # Brooks' Chapter 26 guidance is encoded as an engine invariant: a tradeable
            # candidate must have at least two independent reasons.  A detector that has
            # only one observation is diagnostic, not a candidate.
            raise ValueError("BrooksPatternCandidate requires at least two reasons")
        if not self.source_rule_ids:
            raise ValueError("candidate must carry source rule ids")




@dataclass(frozen=True, slots=True)
class BrooksPatternObservation:
    pattern_id: str
    pattern_name: str
    role: str
    signal_index: int
    direction: str = "UNRESOLVED"
    source_rule_ids: tuple[str, ...] = ()
    taxonomy: Taxonomy = "SOURCE_INTERPRETATION"
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.pattern_id.strip() or not self.pattern_name.strip():
            raise ValueError("pattern id/name are required")
        if self.signal_index < 0:
            raise ValueError("signal_index must be >= 0")
        if self.direction not in {"LONG", "SHORT", "UNRESOLVED"}:
            raise ValueError("invalid observation direction")

@dataclass(frozen=True, slots=True)
class BrooksPatternScan:
    candidates: tuple[BrooksPatternCandidate, ...]
    observations: tuple[BrooksPatternObservation, ...] = ()
    diagnostics: tuple[tuple[str, str], ...] = ()
