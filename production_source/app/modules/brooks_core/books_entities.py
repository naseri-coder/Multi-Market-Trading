"""Typed entities for the book-grounded Brooks v2 context and setup engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

MarketRegime = Literal[
    "BULL_TREND",
    "BEAR_TREND",
    "TRADING_RANGE",
    "TRANSITION",
    "AMBIGUOUS",
]
AlwaysInDirection = Literal["LONG", "SHORT", "UNRESOLVED"]


@dataclass(frozen=True, slots=True)
class RangeIdentityEvidence:
    """Inspectable causal evidence for Brooks trading-range identity."""
    raw_price_overlap_rate: Decimal
    material_price_overlap_rate: Decimal
    body_overlap_rate: Decimal
    small_body_fraction: Decimal
    bull_bar_count: int
    bear_bar_count: int
    reversal_count: int
    failed_up_continuation_count: int
    failed_down_continuation_count: int
    adjusted_displacement: Decimal
    two_sided: bool
    limited_displacement: bool
    tight_range_like: bool
    composite_supported: bool


@dataclass(frozen=True, slots=True)
class RangeHierarchyContext:
    """Local-range relationship to a causally established enclosing range."""
    nested: bool
    local_low: Decimal | None
    local_high: Decimal | None
    enclosing_low: Decimal | None
    enclosing_high: Decimal | None
    local_position: str
    current_relation: str
    local_range_supported: bool
    enclosing_range_supported: bool
    local_window_bars: int
    enclosing_window_bars: int


@dataclass(frozen=True, slots=True)
class Chapter2BarContext:
    """Causal Book-1/Chapter-2 bar, sequence, pressure, and climax evidence."""

    evaluated_index: int
    bar_state: str
    direction: str
    body_size: Decimal
    bar_range: Decimal
    body_fraction: Decimal
    open_location: Decimal
    close_location: Decimal
    upper_tail_fraction: Decimal
    lower_tail_fraction: Decimal
    recent_median_body: Decimal | None
    relative_body_multiple: Decimal | None
    body_at_or_above_recent_median: bool
    strong_geometry_proxy: bool
    directional_prior_close_count: int
    directional_prior_extreme_count: int
    directional_prior_extreme_close_count: int
    trending_doji_direction: str
    trending_doji_run_length: int
    bull_body_count: int
    bear_body_count: int
    bull_body_total: Decimal
    bear_body_total: Decimal
    lower_tail_fraction_total: Decimal
    upper_tail_fraction_total: Decimal
    pressure_direction: str
    climax_direction: str
    climax_run_length: int
    climax_body_progression: str
    climax_state: str
    climax_pause_index: int | None
    climax_pause_kind: str | None


@dataclass(frozen=True, slots=True)
class ContextMetrics:
    directional_bar_fraction: Decimal
    body_overlap_rate: Decimal
    bar_overlap_rate: Decimal
    adjusted_displacement: Decimal
    close_path_efficiency: Decimal
    ema_side_fraction: Decimal
    strong_bull_bar_count: int
    strong_bear_bar_count: int
    tight_range_like: bool


@dataclass(frozen=True, slots=True)
class BrooksContextAssessment:
    regime: MarketRegime
    always_in: AlwaysInDirection
    reason: str
    structure_direction: str
    breakout_direction: AlwaysInDirection
    breakout_streak: int
    metrics: ContextMetrics
    range_evidence: RangeIdentityEvidence | None = None
    chapter2_bar_context: Chapter2BarContext | None = None


@dataclass(frozen=True, slots=True)
class BarCountEvent:
    index: int
    number: int
    label: str


@dataclass(frozen=True, slots=True)
class BookSecondEntrySetup:
    direction: Literal["LONG", "SHORT"]
    setup_type: Literal["H2_CONFIRMED", "L2_CONFIRMED"]
    start_index: int
    signal_index: int
    entry_number: int
    first_entry_index: int
    second_excursion_index: int
    events: tuple[BarCountEvent, ...]


@dataclass(frozen=True, slots=True)
class BookSecondEntryAssessment:
    setup: BookSecondEntrySetup | None
    reason: str
    events: tuple[BarCountEvent, ...] = ()
    highest_entry_number: int = 0
