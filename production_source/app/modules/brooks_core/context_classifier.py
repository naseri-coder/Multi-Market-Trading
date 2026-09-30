"""Causal market-context classifier grounded in the Brooks trilogy.

Source concepts implemented qualitatively:
- Trends: trending highs/lows, directional trend bars, little overlap, urgency,
  small/infrequent pullbacks, failed countertrend attempts.
- Breakouts: strong trend bars plus follow-through.
- Always In: usually a spike/breakout with follow-through; commonly at least two
  consecutive reasonably strong trend bars.
- Trading ranges: two-sided price action and overlap; a breakout of a small range
  inside a larger range does not automatically create a new trend.

All numeric cutoffs that turn those ideas into deterministic code live in
``BrooksBooksPolicy`` and are engineering choices, not Brooks-authored thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from app.modules.brooks_core.books_entities import (
    BrooksContextAssessment,
    Chapter2BarContext,
    ContextMetrics,
    RangeIdentityEvidence,
    RangeHierarchyContext,
)
from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.causal_structure import (
    confirm_swings_causally,
    evaluate_br031_structure,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

_ZERO = Decimal("0")
_ONE = Decimal("1")

@dataclass(frozen=True, slots=True)
class TightTradingRangeIdentity:
    """BROOKS-GAP-027: inspectable TTR subtype built on WAVE_02 range evidence."""
    range_id: str
    origin_index: int
    end_index: int
    evidence: RangeIdentityEvidence
    doji_like_count: int
    tail_dominant_count: int
    frequent_reversals: bool
    heavy_overlap: bool
    is_tight: bool
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class BarbwireIdentity:
    """BROOKS-GAP-028: source-distinct barbwire identity, not generic overlap."""
    range_id: str
    origin_index: int
    end_index: int
    evidence: RangeIdentityEvidence
    bar_count: int
    doji_like_count: int
    tail_dominant_count: int
    persistent_overlap: bool
    middle_bar_overlap_guide: bool
    relatively_large_bar_count: int
    is_barbwire: bool
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class BroadTradingRangeIdentity:
    """BROOKS-GAP-032: ordinary/broad range with explicit room evidence."""
    range_id: str
    origin_index: int
    end_index: int
    evidence: RangeIdentityEvidence
    low: Decimal
    high: Decimal
    width: Decimal
    median_bar_range: Decimal
    room_multiple: Decimal
    room_present: bool
    is_broad: bool
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class RangeEdgeIdentity:
    """BROOKS-GAP-029: one coherent range-boundary location identity."""
    range_id: str
    side: str
    low: Decimal
    high: Decimal
    engineering_tolerance: Decimal
    state: str
    evaluated_index: int


@dataclass(frozen=True, slots=True)
class LocalEnclosingBreakoutContext:
    """BROOKS-GAP-038: local breakout relation to WAVE_02 enclosing range."""
    hierarchy: RangeHierarchyContext
    direction: str
    state: str
    evaluated_index: int
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class StrongTrendEvidence:
    """BROOKS-GAP-008: transparent multi-component strong-trend evidence."""
    direction: str
    evaluated_index: int
    trending_swings: bool
    directional_bars: bool
    little_body_overlap: bool
    small_tail_fraction: Decimal
    urgency: bool
    failed_countertrend_attempts: int
    limited_pullbacks: bool
    is_strong: bool
    classification_policy: str = "ENGINEERING_CLASSIFICATION_POLICY_EXPLICIT_COMPONENTS"


def _range(candle: Candle) -> Decimal:
    return candle.high - candle.low


def body_fraction(candle: Candle) -> Decimal:
    spread = _range(candle)
    if spread <= 0:
        return _ZERO
    return abs(candle.close - candle.open) / spread


def close_location(candle: Candle) -> Decimal:
    spread = _range(candle)
    if spread <= 0:
        return Decimal("0.5")
    return (candle.close - candle.low) / spread


def open_location(candle: Candle) -> Decimal:
    spread = _range(candle)
    if spread <= 0:
        return Decimal("0.5")
    return (candle.open - candle.low) / spread


def _tail_fractions(candle: Candle) -> tuple[Decimal, Decimal]:
    spread = _range(candle)
    if spread <= 0:
        return _ZERO, _ZERO
    upper = candle.high - max(candle.open, candle.close)
    lower = min(candle.open, candle.close) - candle.low
    return upper / spread, lower / spread


def _body_size(candle: Candle) -> Decimal:
    return abs(candle.close - candle.open)


def _chapter2_recent_median_body(
    candles: tuple[Candle, ...],
    *,
    index: int,
    policy: BrooksBooksPolicy,
) -> Decimal | None:
    start = max(0, index - policy.chapter2_relative_body_lookback_bars)
    prior = [_body_size(c) for c in candles[start:index]]
    return median(prior) if prior else None


def _chapter2_bar_state_at(
    candles: tuple[Candle, ...],
    *,
    index: int,
    policy: BrooksBooksPolicy,
) -> tuple[str, Decimal | None]:
    candle = candles[index]
    body = _body_size(candle)
    recent_median = _chapter2_recent_median_body(candles, index=index, policy=policy)
    small_shape = body_fraction(candle) <= policy.small_body_max_fraction
    small_relative = recent_median is None or body <= recent_median
    if body == 0 or (small_shape and small_relative):
        return "DOJI_LIKE", recent_median
    if candle.close > candle.open:
        return "BULL_TREND_BAR_LIKE", recent_median
    if candle.close < candle.open:
        return "BEAR_TREND_BAR_LIKE", recent_median
    return "DOJI_LIKE", recent_median


def _chapter2_trending_doji_sequence(
    candles: tuple[Candle, ...],
    *,
    end: int,
    policy: BrooksBooksPolicy,
) -> tuple[str, int]:
    start = end
    while start >= 0:
        state, _ = _chapter2_bar_state_at(candles, index=start, policy=policy)
        if state != "DOJI_LIKE":
            break
        start -= 1
    start += 1
    run = tuple(candles[start:end + 1])
    if len(run) < policy.chapter2_trending_doji_min_bars:
        return "UNRESOLVED", len(run)

    pair_count = len(run) - 1
    majority = pair_count // 2 + 1
    pairs = zip(run, run[1:], strict=False)
    bull_closes = all(b.close > a.close for a, b in pairs)
    pairs = zip(run, run[1:], strict=False)
    bear_closes = all(b.close < a.close for a, b in pairs)
    higher_highs = sum(
        b.high > a.high for a, b in zip(run, run[1:], strict=False)
    )
    higher_lows = sum(
        b.low > a.low for a, b in zip(run, run[1:], strict=False)
    )
    lower_highs = sum(
        b.high < a.high for a, b in zip(run, run[1:], strict=False)
    )
    lower_lows = sum(
        b.low < a.low for a, b in zip(run, run[1:], strict=False)
    )

    if bull_closes and higher_highs >= majority and higher_lows >= majority:
        return "LONG", len(run)
    if bear_closes and lower_highs >= majority and lower_lows >= majority:
        return "SHORT", len(run)
    return "UNRESOLVED", len(run)


def _chapter2_intrinsic_pause_kind(
    candles: tuple[Candle, ...],
    *,
    index: int,
    policy: BrooksBooksPolicy,
) -> str | None:
    if index < 0 or index >= len(candles):
        return None

    candle = candles[index]
    state, recent_median = _chapter2_bar_state_at(
        candles, index=index, policy=policy
    )
    if state == "DOJI_LIKE":
        return "DOJI"
    if index > 0:
        previous = candles[index - 1]
        if candle.high <= previous.high and candle.low >= previous.low:
            return "INSIDE_BAR"

    direction = (
        "LONG"
        if state == "BULL_TREND_BAR_LIKE"
        else "SHORT"
        if state == "BEAR_TREND_BAR_LIKE"
        else "UNRESOLVED"
    )
    if direction == "UNRESOLVED" or recent_median is None:
        return None

    upper_tail, lower_tail = _tail_fractions(candle)
    trend_side_tail = upper_tail if direction == "LONG" else lower_tail
    small_relative = _body_size(candle) <= recent_median
    if small_relative and trend_side_tail > body_fraction(candle):
        return "SAME_DIRECTION_TAIL_PAUSE"
    return None


def _chapter2_climax_run(
    candles: tuple[Candle, ...],
    *,
    end: int,
    policy: BrooksBooksPolicy,
) -> tuple[str, int, str, int | None, str | None]:
    state, _ = _chapter2_bar_state_at(candles, index=end, policy=policy)
    pause_index: int | None = None
    pause_kind: str | None = None
    run_end = end

    intrinsic_pause = _chapter2_intrinsic_pause_kind(
        candles, index=end, policy=policy
    )
    if end > 0:
        previous_state, _ = _chapter2_bar_state_at(
            candles, index=end - 1, policy=policy
        )
        previous_direction = (
            "LONG"
            if previous_state == "BULL_TREND_BAR_LIKE"
            else "SHORT"
            if previous_state == "BEAR_TREND_BAR_LIKE"
            else "UNRESOLVED"
        )
        current_direction = (
            "LONG"
            if state == "BULL_TREND_BAR_LIKE"
            else "SHORT"
            if state == "BEAR_TREND_BAR_LIKE"
            else "UNRESOLVED"
        )
        opposite_pause = (
            previous_direction in {"LONG", "SHORT"}
            and current_direction in {"LONG", "SHORT"}
            and current_direction != previous_direction
        )
        if previous_direction in {"LONG", "SHORT"} and (
            intrinsic_pause is not None or opposite_pause
        ):
            pause_index = end
            pause_kind = (
                intrinsic_pause
                if intrinsic_pause is not None
                else "OPPOSITE_TREND_BAR"
            )
            run_end = end - 1
            state = previous_state

    if run_end < 0:
        return "UNRESOLVED", 0, "NO_CLIMAX_RUN", pause_index, pause_kind
    if state not in {"BULL_TREND_BAR_LIKE", "BEAR_TREND_BAR_LIKE"}:
        return "UNRESOLVED", 0, "NO_CLIMAX_RUN", pause_index, pause_kind

    direction = "LONG" if state == "BULL_TREND_BAR_LIKE" else "SHORT"
    wanted = state
    start = run_end
    while start > 0:
        previous_index = start - 1
        previous, _ = _chapter2_bar_state_at(
            candles, index=previous_index, policy=policy
        )
        if previous != wanted:
            break
        if (
            _chapter2_intrinsic_pause_kind(
                candles, index=previous_index, policy=policy
            )
            is not None
        ):
            break
        start -= 1

    run_length = run_end - start + 1
    if pause_index is not None:
        climax_state = (
            "BUY_CLIMAX_ENDED_AT_PAUSE"
            if direction == "LONG"
            else "SELL_CLIMAX_ENDED_AT_PAUSE"
        )
    else:
        climax_state = (
            "ACTIVE_BUY_CLIMAX"
            if direction == "LONG"
            else "ACTIVE_SELL_CLIMAX"
        )
    return direction, run_length, climax_state, pause_index, pause_kind


def assess_chapter2_bar_context(
    candles: tuple[Candle, ...],
    policy: BrooksBooksPolicy,
    *,
    evaluated_index: int | None = None,
) -> Chapter2BarContext | None:
    """Book 1 / Chapter 2 evidence; context only and never a direct trade gate."""
    if not candles:
        return None
    end = (
        len(candles) - 1
        if evaluated_index is None
        else min(evaluated_index, len(candles) - 1)
    )
    if end < 0:
        return None

    candle = candles[end]
    state, recent_median = _chapter2_bar_state_at(candles, index=end, policy=policy)
    body = _body_size(candle)
    spread = _range(candle)
    upper_tail, lower_tail = _tail_fractions(candle)
    relative_multiple = (
        body / recent_median
        if recent_median is not None and recent_median > 0
        else None
    )
    direction = (
        "LONG"
        if candle.close > candle.open
        else "SHORT"
        if candle.close < candle.open
        else "UNRESOLVED"
    )
    trending_doji_direction, trending_doji_run_length = (
        _chapter2_trending_doji_sequence(candles, end=end, policy=policy)
    )

    prior_start = max(0, end - policy.chapter2_relative_body_lookback_bars)
    prior = tuple(candles[prior_start:end])
    if direction == "LONG":
        prior_close_count = sum(candle.close >= c.close for c in prior)
        prior_extreme_count = sum(candle.high > c.high for c in prior)
        prior_extreme_close_count = sum(candle.close >= c.high for c in prior)
    elif direction == "SHORT":
        prior_close_count = sum(candle.close <= c.close for c in prior)
        prior_extreme_count = sum(candle.low < c.low for c in prior)
        prior_extreme_close_count = sum(candle.close <= c.low for c in prior)
    else:
        prior_close_count = 0
        prior_extreme_count = 0
        prior_extreme_close_count = 0

    start = max(0, end - policy.chapter2_relative_body_lookback_bars + 1)
    recent = tuple(candles[start:end + 1])
    bull_bodies = [_body_size(c) for c in recent if c.close > c.open]
    bear_bodies = [_body_size(c) for c in recent if c.close < c.open]
    lower_tail_total = sum((_tail_fractions(c)[1] for c in recent), _ZERO)
    upper_tail_total = sum((_tail_fractions(c)[0] for c in recent), _ZERO)
    bull_total = sum(bull_bodies, _ZERO)
    bear_total = sum(bear_bodies, _ZERO)
    if len(bull_bodies) > len(bear_bodies) and bull_total > bear_total:
        pressure_direction = "LONG"
    elif len(bear_bodies) > len(bull_bodies) and bear_total > bull_total:
        pressure_direction = "SHORT"
    else:
        pressure_direction = "UNRESOLVED"

    (
        climax_direction,
        climax_run_length,
        climax_state,
        climax_pause_index,
        climax_pause_kind,
    ) = _chapter2_climax_run(candles, end=end, policy=policy)
    if climax_run_length >= 2:
        progression_end = end if climax_pause_index is None else end - 1
        progression_start = progression_end - climax_run_length + 1
        climax_body_sizes = [
            _body_size(c)
            for c in candles[progression_start : progression_end + 1]
        ]
        if all(
            later > earlier
            for earlier, later in zip(
                climax_body_sizes, climax_body_sizes[1:], strict=False
            )
        ):
            climax_body_progression = "INCREASING"
        elif all(
            later < earlier
            for earlier, later in zip(
                climax_body_sizes, climax_body_sizes[1:], strict=False
            )
        ):
            climax_body_progression = "DECREASING"
        else:
            climax_body_progression = "MIXED"
    elif climax_run_length == 1:
        climax_body_progression = "SINGLE_BAR"
    else:
        climax_body_progression = "NONE"

    strong_geometry = (
        state == "BULL_TREND_BAR_LIKE"
        and body_fraction(candle) >= policy.strong_bar_min_body_fraction
        and close_location(candle)
        >= _ONE - policy.strong_bar_close_extreme_fraction
    ) or (
        state == "BEAR_TREND_BAR_LIKE"
        and body_fraction(candle) >= policy.strong_bar_min_body_fraction
        and close_location(candle) <= policy.strong_bar_close_extreme_fraction
    )

    return Chapter2BarContext(
        evaluated_index=end,
        bar_state=state,
        direction=direction,
        body_size=body,
        bar_range=spread,
        body_fraction=body_fraction(candle),
        open_location=open_location(candle),
        close_location=close_location(candle),
        upper_tail_fraction=upper_tail,
        lower_tail_fraction=lower_tail,
        recent_median_body=recent_median,
        relative_body_multiple=relative_multiple,
        body_at_or_above_recent_median=bool(
            recent_median is not None and body >= recent_median
        ),
        strong_geometry_proxy=strong_geometry,
        directional_prior_close_count=prior_close_count,
        directional_prior_extreme_count=prior_extreme_count,
        directional_prior_extreme_close_count=prior_extreme_close_count,
        trending_doji_direction=trending_doji_direction,
        trending_doji_run_length=trending_doji_run_length,
        bull_body_count=len(bull_bodies),
        bear_body_count=len(bear_bodies),
        bull_body_total=bull_total,
        bear_body_total=bear_total,
        lower_tail_fraction_total=lower_tail_total,
        upper_tail_fraction_total=upper_tail_total,
        pressure_direction=pressure_direction,
        climax_direction=climax_direction,
        climax_run_length=climax_run_length,
        climax_body_progression=climax_body_progression,
        climax_state=climax_state,
        climax_pause_index=climax_pause_index,
        climax_pause_kind=climax_pause_kind,
    )


def _body_interval(candle: Candle) -> tuple[Decimal, Decimal]:
    return min(candle.open, candle.close), max(candle.open, candle.close)


def body_overlap_fraction(a: Candle, b: Candle) -> Decimal:
    a_low, a_high = _body_interval(a)
    b_low, b_high = _body_interval(b)
    overlap = min(a_high, b_high) - max(a_low, b_low)
    if overlap <= 0:
        return _ZERO
    smaller = min(a_high - a_low, b_high - b_low)
    if smaller <= 0:
        return _ZERO
    return min(_ONE, overlap / smaller)


def is_strong_bull_bar(candle: Candle, policy: BrooksBooksPolicy) -> bool:
    return (
        candle.close > candle.open
        and body_fraction(candle) >= policy.strong_bar_min_body_fraction
        and close_location(candle) >= _ONE - policy.strong_bar_close_extreme_fraction
    )


def is_strong_bear_bar(candle: Candle, policy: BrooksBooksPolicy) -> bool:
    return (
        candle.close < candle.open
        and body_fraction(candle) >= policy.strong_bar_min_body_fraction
        and close_location(candle) <= policy.strong_bar_close_extreme_fraction
    )


def is_bull_reversal_bar_minimum(candle: Candle) -> bool:
    """Brooks minimum bull reversal-bar identity (BROOKS-GAP-001).

    Minimum identity is deliberately weaker than setup quality: a bull body OR a
    close above the bar midpoint qualifies the bar for reversal-bar semantics.
    Callers remain responsible for pattern/context/strength requirements.
    """
    return candle.close > candle.open or close_location(candle) > Decimal("0.5")


def is_bear_reversal_bar_minimum(candle: Candle) -> bool:
    """Brooks minimum bear reversal-bar identity (BROOKS-GAP-001)."""
    return candle.close < candle.open or close_location(candle) < Decimal("0.5")


def chapter5_reversal_diagnostic(
    candles: tuple[Candle, ...], *, direction: str
) -> tuple[tuple[str, str], ...]:
    """Closed-bar, descriptive Chapter-5 reversal/overlap observation; never a gate."""
    if not candles or direction not in {"LONG", "SHORT"}:
        return ()
    current = candles[-1]
    previous = candles[-2] if len(candles) > 1 else None
    bull = direction == "LONG"
    minimum = (
        is_bull_reversal_bar_minimum(current)
        if bull else is_bear_reversal_bar_minimum(current)
    )
    body = abs(current.close - current.open)
    upper = current.high - max(current.open, current.close)
    lower = min(current.open, current.close) - current.low
    rejection_tail = lower if bull else upper
    adverse_tail = upper if bull else lower
    directional_body = current.close > current.open if bull else current.close < current.open
    position = close_location(current)
    previous_close_relation = "NO_PRIOR_BAR"
    overlap = _ZERO
    inside_prior_range = False
    weak_displacement = False
    midpoint_warning = False
    two_sided = False
    relative_range = "NO_PRIOR_BAR"
    if previous is not None:
        previous_close_relation = (
            "SUPPORTIVE" if (current.close > previous.close if bull
                            else current.close < previous.close)
            else "EQUAL" if current.close == previous.close else "ADVERSE"
        )
        overlap = max(
            _ZERO, min(current.high, previous.high) - max(current.low, previous.low)
        )
        inside_prior_range = (
            current.high <= previous.high and current.low >= previous.low
        )
        weak_displacement = previous.low <= current.close <= previous.high
        midpoint = (current.high + current.low) / 2
        midpoint_warning = (
            midpoint >= previous.low if bull else midpoint <= previous.high
        )
        two_sided = (
            overlap > 0 and
            ((current.close > current.open and previous.close < previous.open)
             or (current.close < current.open and previous.close > previous.open))
        )
        relative_range = (
            "LARGER" if _range(current) > _range(previous)
            else "SMALLER" if _range(current) < _range(previous) else "EQUAL"
        )
    doji_like_balance = body == 0 or (
        body <= upper and body <= lower
    )
    if not minimum:
        quality = "MINIMUM_NOT_MET"
    elif doji_like_balance:
        quality = "DOJI_LIKE_CONTEXT_DEPENDENT"
    elif directional_body and rejection_tail > adverse_tail:
        quality = "DIRECTIONAL_REJECTION_SUPPORT"
    else:
        quality = "MIXED_CONTEXTUAL_QUALITY"
    overlap_context = (
        "REVERSAL_APPEARANCE_RANGE_CAUTION"
        if previous is not None and (inside_prior_range or (
            overlap > 0 and (weak_displacement or doji_like_balance or two_sided)
        ))
        else "NO_PRIOR_CONTEXT" if previous is None else "DISPLACEMENT_OR_MIXED"
    )
    return (
        ("minimum_reversal_shape", str(minimum).lower()),
        ("directional_body", str(directional_body).lower()),
        ("close_location", str(position)),
        ("previous_close_relation", previous_close_relation),
        ("rejection_tail", str(rejection_tail)),
        ("adverse_tail", str(adverse_tail)),
        ("adverse_tail_exceeds_body", str(adverse_tail > body).lower()),
        ("body_size", str(body)),
        ("relative_range", relative_range),
        ("doji_like_balance", str(doji_like_balance).lower()),
        ("prior_range_overlap", str(overlap)),
        ("inside_prior_range", str(inside_prior_range).lower()),
        ("weak_displacement", str(weak_displacement).lower()),
        ("midpoint_overlap_caution", str(midpoint_warning).lower()),
        ("two_sided_action", str(two_sided).lower()),
        ("quality", quality),
        ("overlap_context", overlap_context),
        ("trade_eligible", "false"),
        ("range_identity_created", "false"),
    )


def _ema20(candles: tuple[Candle, ...]) -> tuple[Decimal, ...]:
    if not candles:
        return ()
    alpha = Decimal("2") / Decimal("21")
    value = candles[0].close
    values = [value]
    for candle in candles[1:]:
        value = candle.close * alpha + value * (_ONE - alpha)
        values.append(value)
    return tuple(values)


def _adjusted_displacement(
    candles: tuple[Candle, ...],
    *,
    direction: str,
) -> Decimal:
    if len(candles) < 2:
        return _ZERO
    high = max(c.high for c in candles)
    low = min(c.low for c in candles)
    width = high - low
    if width <= 0:
        return _ZERO
    signed = (candles[-1].close - candles[0].close) / width
    return signed if direction == "BULL_TREND" else -signed


def _path_efficiency(candles: tuple[Candle, ...]) -> Decimal:
    if len(candles) < 2:
        return _ZERO
    net = abs(candles[-1].close - candles[0].close)
    path = sum(
        abs(current.close - previous.close)
        for previous, current in zip(candles, candles[1:])
    )
    return _ZERO if path <= 0 else net / path


def _directional_bar_fraction(candles: tuple[Candle, ...], direction: str) -> Decimal:
    if not candles:
        return _ZERO
    if direction == "BULL_TREND":
        count = sum(c.close > c.open for c in candles)
    else:
        count = sum(c.close < c.open for c in candles)
    return Decimal(count) / Decimal(len(candles))


def body_overlap_rate(candles: tuple[Candle, ...]) -> Decimal:
    """Adjacent-pair body-overlap rate; distinct from full-price overlap."""
    if len(candles) < 2:
        return _ZERO
    count = sum(body_overlap_fraction(a, b) > 0 for a, b in zip(candles, candles[1:]))
    return Decimal(count) / Decimal(len(candles) - 1)


def price_overlap_fraction(a: Candle, b: Candle) -> Decimal:
    """Fraction of the smaller full bar overlapped by the adjacent bar."""
    overlap = min(a.high, b.high) - max(a.low, b.low)
    if overlap <= 0:
        return _ZERO
    smaller = min(a.high - a.low, b.high - b.low)
    if smaller <= 0:
        return _ZERO
    return min(_ONE, overlap / smaller)


def positive_price_overlap_rate(candles: tuple[Candle, ...]) -> Decimal:
    """Rate of adjacent pairs with any positive full-price intersection."""
    if len(candles) < 2:
        return _ZERO
    count = sum(price_overlap_fraction(a, b) > 0 for a, b in zip(candles, candles[1:]))
    return Decimal(count) / Decimal(len(candles) - 1)


def material_price_overlap_rate(
    candles: tuple[Candle, ...],
    *,
    minimum_fraction: Decimal = Decimal("0.50"),
) -> Decimal:
    """Rate of materially overlapping pairs. 0.50 is an engineering guide, not a range definition."""
    if len(candles) < 2:
        return _ZERO
    count = sum(
        price_overlap_fraction(a, b) >= minimum_fraction
        for a, b in zip(candles, candles[1:])
    )
    return Decimal(count) / Decimal(len(candles) - 1)


def _direction_reversal_count(candles: tuple[Candle, ...]) -> int:
    directions = [1 if c.close > c.open else -1 if c.close < c.open else 0 for c in candles]
    nonzero = [value for value in directions if value]
    return sum(a != b for a, b in zip(nonzero, nonzero[1:]))


def assess_range_identity_evidence(
    candles: tuple[Candle, ...], policy: BrooksBooksPolicy
) -> RangeIdentityEvidence:
    """Build an inspectable composite range identity without a magic aggregate score."""
    if not candles:
        return RangeIdentityEvidence(
            _ZERO, _ZERO, _ZERO, _ZERO, 0, 0, 0, 0, 0, _ZERO,
            False, False, False, False,
        )
    raw_overlap = positive_price_overlap_rate(candles)
    material_overlap = material_price_overlap_rate(candles)
    body_overlap = body_overlap_rate(candles)
    small_body_fraction = Decimal(
        sum(body_fraction(c) <= policy.small_body_max_fraction for c in candles)
    ) / Decimal(len(candles))
    bull_count = sum(c.close > c.open for c in candles)
    bear_count = sum(c.close < c.open for c in candles)
    reversals = _direction_reversal_count(candles)
    failed_up = sum(
        cur.high > prev.high and cur.close <= prev.high
        for prev, cur in zip(candles, candles[1:])
    )
    failed_down = sum(
        cur.low < prev.low and cur.close >= prev.low
        for prev, cur in zip(candles, candles[1:])
    )
    displacement = abs(_adjusted_displacement(candles, direction="BULL_TREND"))
    two_sided = bull_count > 0 and bear_count > 0
    limited_displacement = displacement <= policy.range_max_abs_adjusted_displacement
    material_overlap_evidence = material_overlap >= policy.range_min_body_overlap_rate
    repeated_reversal_evidence = reversals >= 2
    failed_both_directions = failed_up > 0 and failed_down > 0
    small_body_evidence = small_body_fraction >= policy.tight_range_min_small_body_fraction
    tight_range_like = (
        material_overlap >= policy.tight_range_min_overlap_rate
        and small_body_evidence
    )
    composite_supported = (
        two_sided
        and limited_displacement
        and raw_overlap > 0
        and (material_overlap_evidence or repeated_reversal_evidence or failed_both_directions)
        and (material_overlap_evidence or small_body_evidence or failed_both_directions)
    )
    return RangeIdentityEvidence(
        raw_price_overlap_rate=raw_overlap,
        material_price_overlap_rate=material_overlap,
        body_overlap_rate=body_overlap,
        small_body_fraction=small_body_fraction,
        bull_bar_count=bull_count,
        bear_bar_count=bear_count,
        reversal_count=reversals,
        failed_up_continuation_count=failed_up,
        failed_down_continuation_count=failed_down,
        adjusted_displacement=displacement,
        two_sided=two_sided,
        limited_displacement=limited_displacement,
        tight_range_like=tight_range_like,
        composite_supported=composite_supported,
    )




def _tail_dominant(candle: Candle) -> bool:
    spread = _range(candle)
    if spread <= 0:
        return False
    body = abs(candle.close - candle.open)
    return spread - body > body


def _median_bar_range(candles: tuple[Candle, ...]) -> Decimal:
    values = [c.high - c.low for c in candles if c.high > c.low]
    return median(values) if values else _ZERO


def classify_tight_trading_range(
    candles: tuple[Candle, ...],
    policy: BrooksBooksPolicy,
    *,
    origin_index: int = 0,
    evaluated_index: int | None = None,
) -> TightTradingRangeIdentity | None:
    """BROOKS-GAP-027 using transparent WAVE_02 evidence, never an opaque score."""
    if not candles:
        return None
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    if origin_index < 0 or end < origin_index or end - origin_index + 1 < 2:
        return None
    segment = tuple(candles[origin_index:end + 1])
    evidence = assess_range_identity_evidence(segment, policy)
    dojis = sum(
        _chapter2_bar_state_at(segment, index=i, policy=policy)[0] == "DOJI_LIKE"
        for i in range(len(segment))
    )
    tails = sum(_tail_dominant(c) for c in segment)
    # ENGINEERING_CLASSIFICATION_POLICY: source says heavy overlap / many reversals;
    # existing WAVE_02 overlap policy and an inspectable reversal-density comparison
    # make those qualitative components deterministic without a weighted score.
    heavy_overlap = evidence.material_price_overlap_rate >= policy.tight_range_min_overlap_rate
    required_reversals = 1 if len(segment) == 2 else 2
    frequent_reversals = evidence.reversal_count >= required_reversals
    is_tight = bool(
        evidence.composite_supported
        and evidence.two_sided
        and evidence.limited_displacement
        and heavy_overlap
        and dojis > 0
        and tails > 0
        and frequent_reversals
    )
    rid = f"RANGE:{origin_index}:{end}"
    return TightTradingRangeIdentity(
        rid, origin_index, end, evidence, dojis, tails, frequent_reversals,
        heavy_overlap, is_tight,
        "TIGHT_TRADING_RANGE" if is_tight else "GENERIC_RANGE_NOT_TIGHT",
        False,
    )


def classify_barbwire_identity(
    candles: tuple[Candle, ...],
    policy: BrooksBooksPolicy,
    *,
    origin_index: int = 0,
    evaluated_index: int | None = None,
) -> BarbwireIdentity | None:
    """BROOKS-GAP-028 source components: 3+ overlap, doji, tails; size is evidence only."""
    if not candles:
        return None
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    if origin_index < 0 or end < origin_index or end - origin_index + 1 < 3:
        return None
    segment = tuple(candles[origin_index:end + 1])
    ttr = classify_tight_trading_range(segment, policy)
    if ttr is None:
        return None
    evidence = ttr.evidence
    dojis = sum(
        _chapter2_bar_state_at(segment, index=i, policy=policy)[0] == "DOJI_LIKE"
        for i in range(len(segment))
    )
    tails = sum(_tail_dominant(c) for c in segment)
    overlaps = tuple(price_overlap_fraction(a, b) for a, b in zip(segment, segment[1:]))
    persistent = bool(overlaps) and all(x > 0 for x in overlaps)
    # Brooks' >half-middle-bar statement is retained as a source guide for triples,
    # not promoted to the universal identity for all barbwire.
    half = Decimal("0.50")
    middle_guide = any(
        price_overlap_fraction(segment[i], segment[i-1]) > half
        and price_overlap_fraction(segment[i], segment[i+1]) > half
        for i in range(1, len(segment) - 1)
    )
    med = _median_bar_range(segment)
    large_count = sum((c.high - c.low) >= med for c in segment) if med > 0 else 0
    is_barbwire = bool(
        ttr.is_tight
        and len(segment) >= 3
        and dojis >= 1
        and tails >= 1
        and persistent
        and (middle_guide or evidence.material_price_overlap_rate >= policy.tight_range_min_overlap_rate)
    )
    rid = f"BARBWIRE:{origin_index}:{end}"
    return BarbwireIdentity(
        rid, origin_index, end, evidence, len(segment), dojis, tails, persistent,
        middle_guide, large_count, is_barbwire,
        "BARBWIRE" if is_barbwire else "TIGHT_OR_GENERIC_RANGE_NOT_BARBWIRE",
        False,
    )


def classify_broad_trading_range(
    candles: tuple[Candle, ...],
    policy: BrooksBooksPolicy,
    *,
    origin_index: int = 0,
    evaluated_index: int | None = None,
) -> BroadTradingRangeIdentity | None:
    """BROOKS-GAP-032: explicit range width/room versus tight-range identity."""
    if not candles:
        return None
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    if origin_index < 0 or end < origin_index or end - origin_index + 1 < 3:
        return None
    segment = tuple(candles[origin_index:end + 1])
    evidence = assess_range_identity_evidence(segment, policy)
    ttr = classify_tight_trading_range(segment, policy)
    low, high = min(c.low for c in segment), max(c.high for c in segment)
    width = high - low
    med = _median_bar_range(segment)
    room_multiple = width / med if med > 0 else _ZERO
    # ENGINEERING_CLASSIFICATION_POLICY: width > 2 median bars operationalizes
    # "room for scalps"; it is exposed and is not a Brooks-authored universal number.
    room_present = med > 0 and width > med * Decimal("2")
    is_broad = bool(evidence.composite_supported and not (ttr and ttr.is_tight) and room_present)
    rid = f"RANGE:{origin_index}:{end}"
    return BroadTradingRangeIdentity(
        rid, origin_index, end, evidence, low, high, width, med, room_multiple,
        room_present, is_broad, "BROAD_TRADING_RANGE" if is_broad else "NOT_BROAD_RANGE", False
    )


def classify_range_edge(
    base: tuple[Candle, ...],
    current: Candle,
    policy: BrooksBooksPolicy,
    *,
    direction: str,
    origin_index: int = 0,
    evaluated_index: int,
) -> RangeEdgeIdentity | None:
    """BROOKS-GAP-029: canonical range boundary plus explicit engineering tolerance."""
    if direction not in {"LONG", "SHORT"} or not base:
        return None
    evidence = assess_range_identity_evidence(base, policy)
    if not evidence.composite_supported:
        return None
    low, high = min(c.low for c in base), max(c.high for c in base)
    tol = _median_bar_range(base)  # ENGINEERING_TOLERANCE, not a universal 25% edge.
    side = "LOWER" if direction == "LONG" else "UPPER"
    near = current.low <= low + tol if direction == "LONG" else current.high >= high - tol
    state = f"AT_{side}_RANGE_EDGE" if near else "RANGE_MIDDLE"
    return RangeEdgeIdentity(f"RANGE:{origin_index}:{evaluated_index-1}", side, low, high, tol, state, evaluated_index)


def classify_local_breakout_vs_enclosing(
    current: Candle,
    hierarchy: RangeHierarchyContext | None,
    *,
    evaluated_index: int,
) -> LocalEnclosingBreakoutContext | None:
    """BROOKS-GAP-038: local-range escape is not enclosing-range escape."""
    if hierarchy is None or not hierarchy.nested:
        return None
    vals=(hierarchy.local_low,hierarchy.local_high,hierarchy.enclosing_low,hierarchy.enclosing_high)
    if any(v is None for v in vals):
        return None
    ll,lh,el,eh=vals
    up = current.high > lh
    down = current.low < ll
    if up and down:
        return LocalEnclosingBreakoutContext(hierarchy, "AMBIGUOUS", "TWO_SIDED_LOCAL_BREAKOUT_ATTEMPT", evaluated_index, False)
    if up:
        state = "ENCLOSING_RANGE_BREAKOUT" if current.close > eh else "LOCAL_BREAKOUT_INSIDE_ENCLOSING_RANGE"
        return LocalEnclosingBreakoutContext(hierarchy, "LONG", state, evaluated_index, False)
    if down:
        state = "ENCLOSING_RANGE_BREAKOUT" if current.close < el else "LOCAL_BREAKOUT_INSIDE_ENCLOSING_RANGE"
        return LocalEnclosingBreakoutContext(hierarchy, "SHORT", state, evaluated_index, False)
    return LocalEnclosingBreakoutContext(hierarchy, "UNRESOLVED", "NO_LOCAL_BREAKOUT", evaluated_index, False)



def classify_strong_trend_evidence(
    candles: tuple[Candle, ...],
    context: BrooksContextAssessment,
    policy: BrooksBooksPolicy,
    *,
    evaluated_index: int | None = None,
) -> StrongTrendEvidence:
    """BROOKS-GAP-008: explicit components, not one opaque score."""
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    direction="LONG" if context.regime=="BULL_TREND" else "SHORT" if context.regime=="BEAR_TREND" else "UNRESOLVED"
    if end < 1 or direction=="UNRESOLVED":
        return StrongTrendEvidence(direction,end,False,False,False,_ZERO,False,0,False,False)
    window=tuple(candles[max(0,end-policy.recent_window_bars+1):end+1])
    aligned=sum((c.close>c.open) if direction=="LONG" else (c.close<c.open) for c in window)
    directional_bars=Decimal(aligned)/Decimal(len(window)) >= policy.min_directional_bar_fraction
    little_body_overlap=body_overlap_rate(window) <= (_ONE-policy.min_directional_bar_fraction)
    tails=[]
    for c in window:
        spread=_range(c)
        if spread<=0: continue
        body=abs(c.close-c.open)
        tails.append((spread-body)/spread)
    small_tail_fraction=(sum(tails,_ZERO)/Decimal(len(tails))) if tails else _ONE
    small_tails=small_tail_fraction <= Decimal("0.55")  # ENGINEERING_CLASSIFICATION_POLICY
    urgency=context.breakout_direction==direction or (
        direction=="LONG" and window[-1].close>window[0].close
    ) or (
        direction=="SHORT" and window[-1].close<window[0].close
    )
    opposite=[c for c in window if (c.close<c.open if direction=="LONG" else c.close>c.open)]
    failed_countertrend=0
    for a,b in zip(window,window[1:]):
        if direction=="LONG" and a.close<a.open and b.close>a.close: failed_countertrend+=1
        if direction=="SHORT" and a.close>a.open and b.close<a.close: failed_countertrend+=1
    limited_pullbacks=len(opposite) <= max(1,len(window)//3)  # ENGINEERING_CLASSIFICATION_POLICY
    trending_swings=context.structure_direction in {"BULL_TREND","BEAR_TREND"} and (
        (direction=="LONG" and context.structure_direction=="BULL_TREND") or
        (direction=="SHORT" and context.structure_direction=="BEAR_TREND")
    )
    contextual_support = trending_swings or little_body_overlap or small_tails or failed_countertrend>0 or limited_pullbacks
    is_strong=bool(directional_bars and urgency and contextual_support and context.always_in==direction)
    return StrongTrendEvidence(
        direction,end,trending_swings,directional_bars,little_body_overlap,small_tail_fraction,
        urgency,failed_countertrend,limited_pullbacks,is_strong
    )


def assess_range_hierarchy(
    candles: tuple[Candle, ...],
    policy: BrooksBooksPolicy,
    *,
    edge_zone_fraction: Decimal,
) -> RangeHierarchyContext:
    """Causal local/enclosing range hierarchy (BROOKS-GAP-030).

    The enclosing range must be established in an earlier block with its own
    composite two-sided evidence.  A later local range must independently satisfy
    range evidence and be price-contained inside those prior boundaries.  Different
    lookback lengths alone never establish nesting.
    """
    empty = RangeHierarchyContext(
        nested=False, local_low=None, local_high=None, enclosing_low=None,
        enclosing_high=None, local_position="NOT_NESTED",
        current_relation="NOT_NESTED", local_range_supported=False,
        enclosing_range_supported=False, local_window_bars=policy.tight_range_window_bars,
        enclosing_window_bars=policy.recent_window_bars,
    )
    local_n = policy.tight_range_window_bars
    enclosing_n = policy.recent_window_bars
    if len(candles) < enclosing_n + local_n + 1:
        return empty

    current = candles[-1]
    history = candles[:-1]
    local = tuple(history[-local_n:])
    enclosing = tuple(history[-(local_n + enclosing_n):-local_n])
    if len(local) != local_n or len(enclosing) != enclosing_n:
        return empty

    local_evidence = assess_range_identity_evidence(local, policy)
    enclosing_evidence = assess_range_identity_evidence(enclosing, policy)
    local_low, local_high = min(c.low for c in local), max(c.high for c in local)
    enclosing_low, enclosing_high = min(c.low for c in enclosing), max(c.high for c in enclosing)
    enclosing_width = enclosing_high - enclosing_low
    local_width = local_high - local_low
    contained = (
        local_low >= enclosing_low
        and local_high <= enclosing_high
        and enclosing_width > 0
        and local_width > 0
        and local_width < enclosing_width
    )
    nested = bool(
        local_evidence.composite_supported
        and enclosing_evidence.composite_supported
        and contained
    )
    if not nested:
        return RangeHierarchyContext(
            nested=False, local_low=local_low, local_high=local_high,
            enclosing_low=enclosing_low, enclosing_high=enclosing_high,
            local_position="NOT_NESTED", current_relation="NOT_NESTED",
            local_range_supported=local_evidence.composite_supported,
            enclosing_range_supported=enclosing_evidence.composite_supported,
            local_window_bars=local_n, enclosing_window_bars=enclosing_n,
        )

    local_mid = (local_low + local_high) / Decimal("2")
    low_edge = enclosing_low + enclosing_width * edge_zone_fraction
    high_edge = enclosing_high - enclosing_width * edge_zone_fraction
    if local_mid <= low_edge:
        position = "NEAR_ENCLOSING_LOW"
    elif local_mid >= high_edge:
        position = "NEAR_ENCLOSING_HIGH"
    else:
        position = "ENCLOSING_MIDDLE"

    if current.close > enclosing_high:
        relation = "DEPARTING_ABOVE_ENCLOSING_RANGE"
    elif current.close < enclosing_low:
        relation = "DEPARTING_BELOW_ENCLOSING_RANGE"
    else:
        relation = position
    return RangeHierarchyContext(
        nested=True, local_low=local_low, local_high=local_high,
        enclosing_low=enclosing_low, enclosing_high=enclosing_high,
        local_position=position, current_relation=relation,
        local_range_supported=True, enclosing_range_supported=True,
        local_window_bars=local_n, enclosing_window_bars=enclosing_n,
    )

def _ema_side_fraction(candles: tuple[Candle, ...], direction: str) -> Decimal:
    if not candles:
        return _ZERO
    ema = _ema20(candles)
    if direction == "BULL_TREND":
        count = sum(c.close >= e for c, e in zip(candles, ema))
    else:
        count = sum(c.close <= e for c, e in zip(candles, ema))
    return Decimal(count) / Decimal(len(candles))


def _tight_range_like(candles: tuple[Candle, ...], policy: BrooksBooksPolicy) -> bool:
    window = candles[-policy.tight_range_window_bars :]
    if len(window) < policy.tight_range_window_bars:
        return False
    evidence = assess_range_identity_evidence(tuple(window), policy)
    return evidence.tight_range_like


def _recent_strong_breakout(
    candles: tuple[Candle, ...], policy: BrooksBooksPolicy
) -> tuple[str, int]:
    """Return most recent source-style breakout direction/streak.

    We inspect only closed bars and require a run of strong trend bars. The numeric
    strong-bar proxy is engineering policy; the usual two-bar confirmation concept is
    source-grounded from Always In / breakout follow-through discussions.
    """
    lookback = candles[-policy.breakout_lookback_bars :]
    best_direction = "UNRESOLVED"
    best_streak = 0
    current_direction: str | None = None
    current_streak = 0

    for index, candle in enumerate(lookback):
        if is_strong_bull_bar(candle, policy):
            direction = "LONG"
        elif is_strong_bear_bar(candle, policy):
            direction = "SHORT"
        else:
            direction = None

        if direction is None:
            current_direction = None
            current_streak = 0
            continue
        if direction == current_direction:
            current_streak += 1
        else:
            current_direction = direction
            current_streak = 1

        if current_streak >= policy.always_in_min_consecutive_strong_bars:
            streak_start = index - current_streak + 1
            absolute_start = len(candles) - len(lookback) + streak_start
            base_start = max(0, absolute_start - policy.recent_window_bars)
            base = candles[base_start:absolute_start]
            if len(base) < 3:
                continue
            # V5 AI-001/BO-001: momentum must clear structure before the run;
            # the base may precede the short breakout-lookback window.
            cleared_structure = (
                candle.close > max(item.high for item in base)
                if direction == "LONG"
                else candle.close < min(item.low for item in base)
            )
            if cleared_structure:
                best_direction = direction
                best_streak = current_streak

    return best_direction, best_streak


def assess_books_context(
    snapshot: MarketSnapshot,
    *,
    policy: BrooksBooksPolicy,
) -> BrooksContextAssessment:
    candles = snapshot.candles
    chapter2 = assess_chapter2_bar_context(candles, policy)
    if len(candles) < policy.context_window_bars:
        empty = ContextMetrics(
            directional_bar_fraction=_ZERO,
            body_overlap_rate=_ZERO,
            bar_overlap_rate=_ZERO,
            adjusted_displacement=_ZERO,
            close_path_efficiency=_ZERO,
            ema_side_fraction=_ZERO,
            strong_bull_bar_count=0,
            strong_bear_bar_count=0,
            tight_range_like=False,
        )
        return BrooksContextAssessment(
            regime="AMBIGUOUS",
            always_in="UNRESOLVED",
            reason="insufficient closed bars for book-grounded context window",
            structure_direction="AMBIGUOUS",
            breakout_direction="UNRESOLVED",
            breakout_streak=0,
            metrics=empty,
            chapter2_bar_context=chapter2,
        )

    scan = confirm_swings_causally(
        candles,
        left_bars=policy.swing_left_bars,
        right_bars=policy.swing_right_bars,
    )
    structure = evaluate_br031_structure(scan)
    breakout_direction, breakout_streak = _recent_strong_breakout(candles, policy)

    # Brooks notes that context can make one decisive breakout bar sufficient for
    # Always-In.  The deterministic exception below requires that the final closed
    # strong bar also breaks a previously confirmed causal swing; it is not a generic
    # one-bar momentum shortcut.
    if breakout_direction == "UNRESOLVED" and scan.swings:
        final = candles[-1]
        highs = [x for x in scan.swings if x.kind == "HIGH" and x.candle_index < len(candles) - 1]
        lows = [x for x in scan.swings if x.kind == "LOW" and x.candle_index < len(candles) - 1]
        if highs and is_strong_bull_bar(final, policy):
            level = candles[highs[-1].candle_index].high
            if final.close > level:
                breakout_direction, breakout_streak = "LONG", 1
        if breakout_direction == "UNRESOLVED" and lows and is_strong_bear_bar(final, policy):
            level = candles[lows[-1].candle_index].low
            if final.close < level:
                breakout_direction, breakout_streak = "SHORT", 1

    recent = candles[-policy.recent_window_bars :]
    strong_bull = sum(is_strong_bull_bar(c, policy) for c in recent)
    strong_bear = sum(is_strong_bear_bar(c, policy) for c in recent)
    range_evidence = assess_range_identity_evidence(tuple(recent), policy)
    body_overlap = range_evidence.body_overlap_rate
    # Legacy ContextMetrics.bar_overlap_rate is retained as a compatibility alias
    # for material full-price overlap. New consumers should use range_evidence.
    bar_overlap = range_evidence.material_price_overlap_rate
    ttr_identity = classify_tight_trading_range(tuple(recent), policy)
    tight = bool(ttr_identity and ttr_identity.is_tight)

    # Compute direction-adjusted metrics relative to the resolved structure where
    # possible. If unresolved, use the breakout direction as the tentative direction.
    tentative = structure.direction
    if tentative == "AMBIGUOUS":
        if breakout_direction == "LONG":
            tentative = "BULL_TREND"
        elif breakout_direction == "SHORT":
            tentative = "BEAR_TREND"

    if tentative in {"BULL_TREND", "BEAR_TREND"}:
        directional = _directional_bar_fraction(recent, tentative)
        displacement = _adjusted_displacement(recent, direction=tentative)
        ema_side = _ema_side_fraction(recent, tentative)
    else:
        bull_fraction = _directional_bar_fraction(recent, "BULL_TREND")
        bear_fraction = _directional_bar_fraction(recent, "BEAR_TREND")
        directional = max(bull_fraction, bear_fraction)
        bull_disp = abs(_adjusted_displacement(recent, direction="BULL_TREND"))
        displacement = bull_disp
        ema_side = Decimal("0.5")

    efficiency = _path_efficiency(recent)
    metrics = ContextMetrics(
        directional_bar_fraction=directional,
        body_overlap_rate=body_overlap,
        bar_overlap_rate=bar_overlap,
        adjusted_displacement=displacement,
        close_path_efficiency=efficiency,
        ema_side_fraction=ema_side,
        strong_bull_bar_count=strong_bull,
        strong_bear_bar_count=strong_bear,
        tight_range_like=tight,
    )

    # A newly strong breakout against the prior resolved structure is a transition,
    # not an immediate continuation setup. This is source-grounded conceptually;
    # the deterministic bar threshold is engineering policy.
    if (
        structure.direction == "BULL_TREND"
        and breakout_direction == "SHORT"
    ) or (
        structure.direction == "BEAR_TREND"
        and breakout_direction == "LONG"
    ):
        return BrooksContextAssessment(
            regime="TRANSITION",
            always_in=breakout_direction,
            reason="recent strong opposite breakout/follow-through conflicts with prior structure",
            structure_direction=structure.direction,
            breakout_direction=breakout_direction,
            breakout_streak=breakout_streak,
            metrics=metrics,
            range_evidence=range_evidence,
            chapter2_bar_context=chapter2,
        )

    # Chapter 2: a sequence of doji-like bars can itself be directional when
    # closes and most highs/lows trend. This is market-state evidence only; it never
    # establishes Always-In or an autonomous entry.
    if (
        chapter2 is not None
        and chapter2.trending_doji_direction in {"LONG", "SHORT"}
        and breakout_direction == "UNRESOLVED"
    ):
        target_regime = (
            "BULL_TREND"
            if chapter2.trending_doji_direction == "LONG"
            else "BEAR_TREND"
        )
        opposite_structure = (
            structure.direction == "BEAR_TREND"
            if target_regime == "BULL_TREND"
            else structure.direction == "BULL_TREND"
        )
        if opposite_structure:
            return BrooksContextAssessment(
                regime="TRANSITION",
                always_in="UNRESOLVED",
                reason=(
                    "Chapter-2 trending doji sequence conflicts with prior "
                    "resolved structure"
                ),
                structure_direction=structure.direction,
                breakout_direction=breakout_direction,
                breakout_streak=breakout_streak,
                metrics=metrics,
                range_evidence=range_evidence,
                chapter2_bar_context=chapter2,
            )
        return BrooksContextAssessment(
            regime=target_regime,
            always_in="UNRESOLVED",
            reason=(
                "Chapter-2 trending doji sequence establishes directional "
                "price action without an Always-In shortcut"
            ),
            structure_direction=structure.direction,
            breakout_direction=breakout_direction,
            breakout_streak=breakout_streak,
            metrics=metrics,
            range_evidence=range_evidence,
            chapter2_bar_context=chapter2,
        )

    # BROOKS-GAP-026: range identity is a composite of inspectable two-sided
    # evidence, not a single overlap/displacement threshold coincidence.
    range_like = range_evidence.composite_supported
    if range_like and breakout_direction == "UNRESOLVED":
        return BrooksContextAssessment(
            regime="TRADING_RANGE",
            always_in="UNRESOLVED",
            reason="two-sided overlapping price action without a confirmed breakout/follow-through",
            structure_direction=structure.direction,
            breakout_direction=breakout_direction,
            breakout_streak=breakout_streak,
            metrics=metrics,
            range_evidence=range_evidence,
            chapter2_bar_context=chapter2,
        )

    # A confirmed breakout can establish Always-In before engineering swing structure
    # catches up. This mirrors Brooks' spike/follow-through concept while remaining
    # causal and closed-bar only.
    if breakout_direction == "LONG" and structure.direction != "BEAR_TREND":
        return BrooksContextAssessment(
            regime="BULL_TREND",
            always_in="LONG",
            reason="strong bull breakout/follow-through with no conflicting bear structure",
            structure_direction=structure.direction,
            breakout_direction=breakout_direction,
            breakout_streak=breakout_streak,
            metrics=metrics,
            range_evidence=range_evidence,
            chapter2_bar_context=chapter2,
        )
    if breakout_direction == "SHORT" and structure.direction != "BULL_TREND":
        return BrooksContextAssessment(
            regime="BEAR_TREND",
            always_in="SHORT",
            reason="strong bear breakout/follow-through with no conflicting bull structure",
            structure_direction=structure.direction,
            breakout_direction=breakout_direction,
            breakout_streak=breakout_streak,
            metrics=metrics,
            range_evidence=range_evidence,
            chapter2_bar_context=chapter2,
        )

    # Mature continuation proxy. It deliberately combines multiple pieces of context
    # instead of relying on one R40 threshold.
    if structure.direction in {"BULL_TREND", "BEAR_TREND"}:
        mature = (
            directional >= policy.min_directional_bar_fraction
            and displacement >= policy.min_recent_adjusted_displacement
            and efficiency >= policy.min_recent_close_path_efficiency
            and ema_side >= policy.min_ema_side_fraction
            and not tight
        )
        if mature:
            always_in = "LONG" if structure.direction == "BULL_TREND" else "SHORT"
            return BrooksContextAssessment(
                regime=structure.direction,
                always_in=always_in,
                reason="resolved HH/HL or LH/LL structure plus multi-factor continuation evidence",
                structure_direction=structure.direction,
                breakout_direction=breakout_direction,
                breakout_streak=breakout_streak,
                metrics=metrics,
                range_evidence=range_evidence,
                chapter2_bar_context=chapter2,
            )

        if range_like:
            return BrooksContextAssessment(
                regime="TRADING_RANGE",
                always_in="UNRESOLVED",
                reason="resolved swing structure is overridden by current two-sided/range-like context",
                structure_direction=structure.direction,
                breakout_direction=breakout_direction,
                breakout_streak=breakout_streak,
                metrics=metrics,
                range_evidence=range_evidence,
                chapter2_bar_context=chapter2,
            )

        return BrooksContextAssessment(
            regime="AMBIGUOUS",
            always_in="UNRESOLVED",
            reason="structure exists but trend continuation evidence is not mature enough",
            structure_direction=structure.direction,
            breakout_direction=breakout_direction,
            breakout_streak=breakout_streak,
            metrics=metrics,
            range_evidence=range_evidence,
            chapter2_bar_context=chapter2,
        )

    return BrooksContextAssessment(
        regime="AMBIGUOUS",
        always_in="UNRESOLVED",
        reason="no source-style breakout and no resolved trend/range context",
        structure_direction=structure.direction,
        breakout_direction=breakout_direction,
        breakout_streak=breakout_streak,
        metrics=metrics,
        range_evidence=range_evidence,
        chapter2_bar_context=chapter2,
    )
