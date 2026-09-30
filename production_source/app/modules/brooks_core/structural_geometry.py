"""Causal projected-line geometry shared by Brooks structural patterns.

The swing-confirmation algorithm is engineering infrastructure.  This module preserves
confirmed anchor identity and projected geometry; it does not turn geometry into trade
eligibility or implement channel/triangle breakout lifecycles.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.modules.brooks_core.structure_entities import ConfirmedSwing, SwingScanResult
from app.modules.market_data.entities import Candle

LineRelation = Literal["ABOVE_LINE", "BELOW_LINE", "INTERSECTS_LINE"]


@dataclass(frozen=True, slots=True)
class LineAnchor:
    kind: str
    candle_index: int
    confirmed_at_index: int
    price: Decimal
    candle_time: datetime
    confirmed_at_time: datetime


@dataclass(frozen=True, slots=True)
class ProjectedLineGeometry:
    role: str
    direction: str
    anchors: tuple[LineAnchor, ...]
    slope_per_bar: Decimal
    projected_value: Decimal
    evaluated_index: int
    current_relation: LineRelation
    break_evidence: bool
    crossed_this_bar: bool


@dataclass(frozen=True, slots=True)
class TrendChannelGeometry:
    direction: str
    trend_line: ProjectedLineGeometry
    opposite_channel_line: ProjectedLineGeometry
    projected_lower: Decimal
    projected_upper: Decimal
    width: Decimal
    contained_bar_count: int
    evaluated_bar_count: int
    containment_fraction: Decimal


@dataclass(frozen=True, slots=True)
class TriangleGeometry:
    upper_boundary: ProjectedLineGeometry
    lower_boundary: ProjectedLineGeometry
    swing_indices: tuple[int, ...]
    reference_width: Decimal
    current_width: Decimal
    converging: bool
    contained_bar_count: int
    evaluated_bar_count: int
    containment_fraction: Decimal


def projected_value_from_swings(first: ConfirmedSwing, second: ConfirmedSwing, index: int) -> Decimal:
    dx = second.candle_index - first.candle_index
    if dx <= 0:
        raise ValueError("line anchors must be ordered at distinct candle indices")
    slope = (second.price - first.price) / Decimal(dx)
    return second.price + slope * Decimal(index - second.candle_index)


def project_line_value(line: ProjectedLineGeometry, index: int) -> Decimal:
    anchor = line.anchors[-1]
    return anchor.price + line.slope_per_bar * Decimal(index - anchor.candle_index)


def _anchor(candles: tuple[Candle, ...], swing: ConfirmedSwing) -> LineAnchor:
    return LineAnchor(
        kind=swing.kind,
        candle_index=swing.candle_index,
        confirmed_at_index=swing.confirmed_at_index,
        price=swing.price,
        candle_time=candles[swing.candle_index].close_time,
        confirmed_at_time=candles[swing.confirmed_at_index].close_time,
    )


def _relation(candle: Candle, value: Decimal) -> LineRelation:
    if candle.low > value:
        return "ABOVE_LINE"
    if candle.high < value:
        return "BELOW_LINE"
    return "INTERSECTS_LINE"


def line_geometry_from_swings(
    candles: tuple[Candle, ...], first: ConfirmedSwing, second: ConfirmedSwing, *,
    evaluated_index: int, role: str, direction: str, break_side: str,
) -> ProjectedLineGeometry | None:
    if not candles or not (0 <= evaluated_index < len(candles)):
        return None
    if first.candle_index >= second.candle_index:
        return None
    if first.confirmed_at_index > evaluated_index or second.confirmed_at_index > evaluated_index:
        return None
    value = projected_value_from_swings(first, second, evaluated_index)
    slope = (second.price - first.price) / Decimal(second.candle_index - first.candle_index)
    current = candles[evaluated_index]
    broken = current.low < value if break_side == "BELOW" else current.high > value
    crossed = False
    if evaluated_index > 0:
        previous_value = projected_value_from_swings(first, second, evaluated_index - 1)
        previous = candles[evaluated_index - 1]
        previous_broken = previous.low < previous_value if break_side == "BELOW" else previous.high > previous_value
        crossed = broken and not previous_broken
    return ProjectedLineGeometry(
        role=role,
        direction=direction,
        anchors=(_anchor(candles, first), _anchor(candles, second)),
        slope_per_bar=slope,
        projected_value=value,
        evaluated_index=evaluated_index,
        current_relation=_relation(current, value),
        break_evidence=broken,
        crossed_this_bar=crossed,
    )


def _parallel_geometry(
    candles: tuple[Candle, ...], swing: ConfirmedSwing, *, slope: Decimal,
    evaluated_index: int, role: str, direction: str, break_side: str,
) -> ProjectedLineGeometry:
    value = swing.price + slope * Decimal(evaluated_index - swing.candle_index)
    current = candles[evaluated_index]
    broken = current.low < value if break_side == "BELOW" else current.high > value
    crossed = False
    if evaluated_index > 0:
        previous_value = swing.price + slope * Decimal(evaluated_index - 1 - swing.candle_index)
        previous = candles[evaluated_index - 1]
        previous_broken = previous.low < previous_value if break_side == "BELOW" else previous.high > previous_value
        crossed = broken and not previous_broken
    return ProjectedLineGeometry(
        role=role,
        direction=direction,
        anchors=(_anchor(candles, swing),),
        slope_per_bar=slope,
        projected_value=value,
        evaluated_index=evaluated_index,
        current_relation=_relation(current, value),
        break_evidence=broken,
        crossed_this_bar=crossed,
    )


def build_trend_line_geometry(
    candles: tuple[Candle, ...], scan: SwingScanResult, *, direction: str,
    evaluated_index: int | None = None,
) -> ProjectedLineGeometry | None:
    if not candles:
        return None
    index = len(candles) - 1 if evaluated_index is None else evaluated_index
    kind = "LOW" if direction == "BULL_TREND" else "HIGH" if direction == "BEAR_TREND" else None
    if kind is None:
        return None
    eligible = [s for s in scan.swings if s.kind == kind and s.confirmed_at_index <= index]
    if len(eligible) < 2:
        return None
    first, second = eligible[-2], eligible[-1]
    if direction == "BULL_TREND" and second.price <= first.price:
        return None
    if direction == "BEAR_TREND" and second.price >= first.price:
        return None
    return line_geometry_from_swings(
        candles, first, second, evaluated_index=index,
        role="BULL_TREND_LINE" if direction == "BULL_TREND" else "BEAR_TREND_LINE",
        direction=direction, break_side="BELOW" if direction == "BULL_TREND" else "ABOVE",
    )


def build_trend_channel_geometry(
    candles: tuple[Candle, ...], scan: SwingScanResult, *, direction: str,
    evaluated_index: int | None = None,
) -> TrendChannelGeometry | None:
    if not candles:
        return None
    index = len(candles) - 1 if evaluated_index is None else evaluated_index
    trend = build_trend_line_geometry(candles, scan, direction=direction, evaluated_index=index)
    if trend is None:
        return None
    first_index = trend.anchors[0].candle_index
    kind = "HIGH" if direction == "BULL_TREND" else "LOW"
    opposite = [
        s for s in scan.swings
        if s.kind == kind and s.confirmed_at_index <= index and s.candle_index >= first_index
    ]
    if not opposite:
        return None
    def signed_distance(s: ConfirmedSwing) -> Decimal:
        base = project_line_value(trend, s.candle_index)
        return s.price - base if direction == "BULL_TREND" else base - s.price
    valid = [(s, signed_distance(s)) for s in opposite if signed_distance(s) > 0]
    if not valid:
        return None
    channel_anchor, _ = max(valid, key=lambda item: item[1])
    channel_line = _parallel_geometry(
        candles, channel_anchor, slope=trend.slope_per_bar, evaluated_index=index,
        role="BULL_TREND_CHANNEL_LINE" if direction == "BULL_TREND" else "BEAR_TREND_CHANNEL_LINE",
        direction=direction, break_side="ABOVE" if direction == "BULL_TREND" else "BELOW",
    )
    if direction == "BULL_TREND":
        lower, upper = trend.projected_value, channel_line.projected_value
    else:
        lower, upper = channel_line.projected_value, trend.projected_value
    if lower >= upper:
        return None
    start = first_index
    contained = 0
    total = 0
    for i in range(start, index + 1):
        trend_value = project_line_value(trend, i)
        channel_value = project_line_value(channel_line, i)
        lo, hi = sorted((trend_value, channel_value))
        candle = candles[i]
        total += 1
        if candle.low >= lo and candle.high <= hi:
            contained += 1
    fraction = Decimal(contained) / Decimal(total) if total else Decimal("0")
    return TrendChannelGeometry(
        direction=direction,
        trend_line=trend,
        opposite_channel_line=channel_line,
        projected_lower=lower,
        projected_upper=upper,
        width=upper - lower,
        contained_bar_count=contained,
        evaluated_bar_count=total,
        containment_fraction=fraction,
    )


def build_triangle_geometry(
    candles: tuple[Candle, ...], swings: tuple[ConfirmedSwing, ...], *,
    evaluated_index: int | None = None,
) -> TriangleGeometry | None:
    if not candles:
        return None
    index = len(candles) - 1 if evaluated_index is None else evaluated_index
    eligible = [s for s in swings if s.confirmed_at_index <= index]
    alternating: list[ConfirmedSwing] = []
    for swing in eligible:
        if not alternating or alternating[-1].kind != swing.kind:
            alternating.append(swing)
        elif swing.candle_index > alternating[-1].candle_index:
            alternating[-1] = swing
    if len(alternating) < 5:
        return None
    five = alternating[-5:]
    highs = [s for s in five if s.kind == "HIGH"]
    lows = [s for s in five if s.kind == "LOW"]
    if len(highs) < 2 or len(lows) < 2:
        return None
    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]
    upper = line_geometry_from_swings(
        candles, h1, h2, evaluated_index=index, role="TRIANGLE_UPPER_BOUNDARY",
        direction="UNRESOLVED", break_side="ABOVE",
    )
    lower = line_geometry_from_swings(
        candles, l1, l2, evaluated_index=index, role="TRIANGLE_LOWER_BOUNDARY",
        direction="UNRESOLVED", break_side="BELOW",
    )
    if upper is None or lower is None:
        return None
    reference_index = max(h1.candle_index, l1.candle_index)
    reference_width = project_line_value(upper, reference_index) - project_line_value(lower, reference_index)
    current_width = upper.projected_value - lower.projected_value
    converging = (
        lower.slope_per_bar > upper.slope_per_bar
        and reference_width > current_width > 0
    )
    if not converging:
        return None
    start = min(s.candle_index for s in five)
    contained = 0
    total = 0
    for i in range(start, index + 1):
        lo = project_line_value(lower, i)
        hi = project_line_value(upper, i)
        if lo >= hi:
            continue
        total += 1
        candle = candles[i]
        if candle.low >= lo and candle.high <= hi:
            contained += 1
    fraction = Decimal(contained) / Decimal(total) if total else Decimal("0")
    return TriangleGeometry(
        upper_boundary=upper,
        lower_boundary=lower,
        swing_indices=tuple(s.candle_index for s in five),
        reference_width=reference_width,
        current_width=current_width,
        converging=True,
        contained_bar_count=contained,
        evaluated_bar_count=total,
        containment_fraction=fraction,
    )


@dataclass(frozen=True, slots=True)
class ChannelBoundaryEvent:
    """Causal state at the projected trend-channel line; never trade eligibility."""
    state: str
    boundary_role: str
    boundary_value: Decimal
    evaluated_index: int
    penetrated: bool
    closed_beyond: bool
    prior_penetration: bool
    prior_close_beyond: bool
    reentered: bool
    channel_anchor_index: int


@dataclass(frozen=True, slots=True)
class ExpandingTriangleGeometry:
    upper_boundary: ProjectedLineGeometry
    lower_boundary: ProjectedLineGeometry
    swing_indices: tuple[int, ...]
    reference_width: Decimal
    current_width: Decimal
    available_from_index: int
    diverging: bool
    enlarged_structure: bool


@dataclass(frozen=True, slots=True)
class ExpandingTriangleLifecycle:
    geometry: ExpandingTriangleGeometry
    state: str
    first_break_index: int | None
    first_break_direction: str | None
    reentry_index: int | None
    opposite_break_index: int | None
    enlarged_structure: bool


@dataclass(frozen=True, slots=True)
class DuelingLinesConfluence:
    direction: str
    pullback_line: ProjectedLineGeometry
    support_source: str
    support_value: Decimal
    separation: Decimal
    tolerance: Decimal
    confluent: bool


@dataclass(frozen=True, slots=True)
class ParabolicWedgeGeometry:
    side: str
    push_indices: tuple[int, int, int]
    first_slope: Decimal
    second_slope: Decimal
    accelerating: bool
    channel: TrendChannelGeometry | None
    channel_overshoot: bool


@dataclass(frozen=True, slots=True)
class StructuralTestIdentity:
    """Generic causal structural-test occurrence; outcome is an independent dimension."""

    test_id: str
    reference_id: str
    reference_type: str
    direction: str
    reference_level: Decimal | None
    zone_low: Decimal
    zone_high: Decimal
    origin_episode_id: str | None
    occurrence_index: int
    evaluated_index: int
    occurrence_state: str = "TEST_OCCURRED"
    outcome_state: str = "PENDING"
    trade_eligible: bool = False


def classify_structural_test(
    candles: tuple[Candle, ...],
    *,
    reference_id: str,
    reference_type: str,
    zone_low: Decimal,
    zone_high: Decimal,
    search_start_index: int,
    direction: str = "UNRESOLVED",
    reference_level: Decimal | None = None,
    origin_episode_id: str | None = None,
    evaluated_index: int | None = None,
    outcome_state: str = "PENDING",
) -> StructuralTestIdentity | None:
    """Return the first causal interaction with a structural zone, without inferring reaction."""

    if not candles or zone_low > zone_high:
        return None
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    start = max(0, search_start_index)
    if start > end:
        return None
    for index in range(start, end + 1):
        candle = candles[index]
        if candle.high < zone_low or candle.low > zone_high:
            continue
        return StructuralTestIdentity(
            test_id=f"STRUCTURAL_TEST:{reference_type}:{reference_id}:{index}",
            reference_id=reference_id,
            reference_type=reference_type,
            direction=direction,
            reference_level=reference_level,
            zone_low=zone_low,
            zone_high=zone_high,
            origin_episode_id=origin_episode_id,
            occurrence_index=index,
            evaluated_index=end,
            occurrence_state="TEST_OCCURRED",
            outcome_state=outcome_state,
            trade_eligible=False,
        )
    return None


@dataclass(frozen=True, slots=True)
class StructuralSecondTest:
    """Causal first-test / move-away / second-test identity (BROOKS-GAP-051)."""
    side: str
    structure_id: str
    first_test_index: int
    intervening_index: int
    second_test_index: int
    first_level: Decimal
    second_level: Decimal
    zone_low: Decimal
    zone_high: Decimal
    price_relation: str
    confirmed_at_index: int


@dataclass(frozen=True, slots=True)
class MicroDoubleStructure:
    """Bounded consecutive/nearly-consecutive micro second-test identity."""
    side: str
    structure_id: str
    first_test_index: int
    second_test_index: int
    bar_distance: int
    first_level: Decimal
    second_level: Decimal
    price_relation: str
    intervening_move_away: bool
    engineering_tolerance: Decimal


@dataclass(frozen=True, slots=True)
class HeadShouldersLifecycle:
    side: str
    left_shoulder_index: int
    head_index: int
    right_shoulder_index: int
    neckline: ProjectedLineGeometry
    prior_trend_line: ProjectedLineGeometry | None
    state: str
    neckline_break: bool
    neckline_reentry: bool


def build_structural_second_test(
    candles: tuple[Candle, ...], scan: SwingScanResult, *, side: str, evaluated_index: int | None = None,
) -> StructuralSecondTest | None:
    """Identify a structural second test without numeric equality as its definition."""
    if not candles:
        return None
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if not 0 <= end < len(candles):
        return None
    kind = "HIGH" if side == "TOP" else "LOW" if side == "BOTTOM" else None
    opposite = "LOW" if side == "TOP" else "HIGH"
    if kind is None:
        return None
    primary = [x for x in scan.swings if x.kind == kind and getattr(x, "confirmed_at_index", x.candle_index) <= end]
    others = [x for x in scan.swings if x.kind == opposite and getattr(x, "confirmed_at_index", x.candle_index) <= end]
    for first, second in reversed(list(zip(primary[:-1], primary[1:]))):
        between = [x for x in others if first.candle_index < x.candle_index < second.candle_index]
        if not between:
            continue
        middle = between[-1]
        first_level = candles[first.candle_index].high if side == "TOP" else candles[first.candle_index].low
        second_level = candles[second.candle_index].high if side == "TOP" else candles[second.candle_index].low
        relation = "EQUAL_TEST" if second_level == first_level else "HIGHER_TEST" if second_level > first_level else "LOWER_TEST"
        return StructuralSecondTest(
            side=side, structure_id=f"{side}:{first.candle_index}:{middle.candle_index}:{second.candle_index}",
            first_test_index=first.candle_index, intervening_index=middle.candle_index, second_test_index=second.candle_index,
            first_level=first_level, second_level=second_level, zone_low=min(first_level, second_level),
            zone_high=max(first_level, second_level), price_relation=relation,
            confirmed_at_index=max(getattr(second, "confirmed_at_index", second.candle_index), getattr(middle, "confirmed_at_index", middle.candle_index)),
        )
    return None


def build_micro_double_structure(
    candles: tuple[Candle, ...], *, side: str, max_bar_distance: int, engineering_tolerance: Decimal,
    evaluated_index: int | None = None,
) -> MicroDoubleStructure | None:
    """Find a bounded micro second test; window/tolerance are explicit engineering aids."""
    if not candles or max_bar_distance < 1 or engineering_tolerance < 0:
        return None
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if not 0 <= end < len(candles):
        return None
    if side not in {"TOP", "BOTTOM"}:
        return None
    second = candles[end]
    second_level = second.high if side == "TOP" else second.low
    for distance in range(1, min(max_bar_distance, end) + 1):
        first_index = end - distance
        first = candles[first_index]
        first_level = first.high if side == "TOP" else first.low
        if abs(second_level - first_level) > engineering_tolerance:
            continue
        middle = candles[first_index + 1:end]
        if distance == 1:
            moved_away = True
        elif side == "TOP":
            moved_away = bool(middle) and min(x.low for x in middle) < min(first.low, second.low)
        else:
            moved_away = bool(middle) and max(x.high for x in middle) > max(first.high, second.high)
        if not moved_away:
            continue
        relation = "EQUAL_TEST" if second_level == first_level else "HIGHER_TEST" if second_level > first_level else "LOWER_TEST"
        return MicroDoubleStructure(
            side=side, structure_id=f"MICRO:{side}:{first_index}:{end}", first_test_index=first_index,
            second_test_index=end, bar_distance=distance, first_level=first_level, second_level=second_level,
            price_relation=relation, intervening_move_away=moved_away, engineering_tolerance=engineering_tolerance,
        )
    return None


def classify_channel_boundary_event(
    candles: tuple[Candle, ...], channel: TrendChannelGeometry, *, evaluated_index: int | None = None,
) -> ChannelBoundaryEvent | None:
    if not candles:
        return None
    index = len(candles) - 1 if evaluated_index is None else evaluated_index
    if not (0 <= index < len(candles)):
        return None
    line = channel.opposite_channel_line
    value = project_line_value(line, index)
    current = candles[index]
    bull = channel.direction == "BULL_TREND"
    penetrated = current.high > value if bull else current.low < value
    closed_beyond = current.close > value if bull else current.close < value
    touched = current.high >= value if bull else current.low <= value
    prior_penetration = prior_close_beyond = False
    if index > 0:
        prior_value = project_line_value(line, index - 1)
        previous = candles[index - 1]
        prior_penetration = previous.high > prior_value if bull else previous.low < prior_value
        prior_close_beyond = previous.close > prior_value if bull else previous.close < prior_value
    inside_close = current.close <= value if bull else current.close >= value
    reentered = (prior_penetration or prior_close_beyond) and inside_close
    if reentered:
        state = "FAILED_BREAK_REENTRY"
    elif closed_beyond:
        state = "CHANNEL_LINE_BREAK"
    elif penetrated:
        state = "CHANNEL_LINE_OVERSHOOT"
    elif touched:
        state = "CHANNEL_LINE_TEST"
    else:
        state = "INSIDE_CHANNEL"
    return ChannelBoundaryEvent(
        state=state, boundary_role=line.role, boundary_value=value, evaluated_index=index,
        penetrated=penetrated, closed_beyond=closed_beyond,
        prior_penetration=prior_penetration, prior_close_beyond=prior_close_beyond,
        reentered=reentered, channel_anchor_index=line.anchors[0].candle_index,
    )


def build_expanding_triangle_geometry(
    candles: tuple[Candle, ...], swings: tuple[ConfirmedSwing, ...], *, evaluated_index: int | None = None,
) -> ExpandingTriangleGeometry | None:
    if not candles:
        return None
    index = len(candles) - 1 if evaluated_index is None else evaluated_index
    eligible = [s for s in swings if s.confirmed_at_index <= index]
    alternating: list[ConfirmedSwing] = []
    for swing in eligible:
        if not alternating or alternating[-1].kind != swing.kind:
            alternating.append(swing)
        elif swing.candle_index > alternating[-1].candle_index:
            alternating[-1] = swing
    if len(alternating) < 4:
        return None
    recent = alternating[-6:]
    highs = [s for s in recent if s.kind == "HIGH"]
    lows = [s for s in recent if s.kind == "LOW"]
    if len(highs) < 2 or len(lows) < 2:
        return None
    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]
    if not (h2.price > h1.price and l2.price < l1.price):
        return None
    upper = line_geometry_from_swings(candles, h1, h2, evaluated_index=index,
        role="EXPANDING_TRIANGLE_UPPER_BOUNDARY", direction="UNRESOLVED", break_side="ABOVE")
    lower = line_geometry_from_swings(candles, l1, l2, evaluated_index=index,
        role="EXPANDING_TRIANGLE_LOWER_BOUNDARY", direction="UNRESOLVED", break_side="BELOW")
    if upper is None or lower is None:
        return None
    reference_index = max(h1.candle_index, l1.candle_index)
    reference_width = project_line_value(upper, reference_index) - project_line_value(lower, reference_index)
    current_width = upper.projected_value - lower.projected_value
    diverging = upper.slope_per_bar > lower.slope_per_bar and current_width > reference_width > 0
    if not diverging:
        return None
    prior_highs = highs[:-1]
    prior_lows = lows[:-1]
    outer_extension = (
        (len(prior_highs) >= 2 and highs[-1].price > max(x.price for x in prior_highs))
        or (len(prior_lows) >= 2 and lows[-1].price < min(x.price for x in prior_lows))
    )
    return ExpandingTriangleGeometry(
        upper_boundary=upper, lower_boundary=lower,
        swing_indices=tuple(s.candle_index for s in recent),
        reference_width=reference_width, current_width=current_width,
        available_from_index=max(h2.confirmed_at_index, l2.confirmed_at_index), diverging=True,
        enlarged_structure=outer_extension,
    )


def classify_expanding_triangle_lifecycle(
    candles: tuple[Candle, ...], geometry: ExpandingTriangleGeometry, *, evaluated_index: int | None = None,
) -> ExpandingTriangleLifecycle:
    index = len(candles) - 1 if evaluated_index is None else evaluated_index
    first_break_index = None
    first_break_direction = None
    reentry_index = None
    opposite_break_index = None
    for i in range(geometry.available_from_index, index + 1):
        upper = project_line_value(geometry.upper_boundary, i)
        lower = project_line_value(geometry.lower_boundary, i)
        close = candles[i].close
        direction = "ABOVE" if close > upper else "BELOW" if close < lower else None
        if first_break_index is None and direction is not None:
            first_break_index, first_break_direction = i, direction
            continue
        if first_break_index is not None and reentry_index is None and direction is None:
            reentry_index = i
            continue
        if reentry_index is not None and direction is not None and direction != first_break_direction:
            opposite_break_index = i
            break
    if opposite_break_index is not None:
        state = "FAILED_BREAK_REVERSED_THROUGH_OTHER_SIDE"
    elif reentry_index is not None:
        state = "FAILED_BREAK_REENTRY"
    elif first_break_index is not None:
        state = "BREAKOUT_IN_PROGRESS"
    else:
        state = "EXPANDING_STRUCTURE_INTACT"
    return ExpandingTriangleLifecycle(
        geometry=geometry, state=state, first_break_index=first_break_index,
        first_break_direction=first_break_direction, reentry_index=reentry_index,
        opposite_break_index=opposite_break_index,
        enlarged_structure=geometry.enlarged_structure,
    )


def build_dueling_lines_confluence(
    candles: tuple[Candle, ...], scan: SwingScanResult, *, direction: str,
    evaluated_index: int, ema_value: Decimal | None, tolerance: Decimal,
    measured_move_value: Decimal | None = None,
) -> DuelingLinesConfluence | None:
    if tolerance <= 0:
        return None
    if direction == "BULL_TREND":
        counter = [s for s in scan.swings if s.kind == "HIGH" and s.confirmed_at_index <= evaluated_index]
        if len(counter) < 2 or counter[-1].price >= counter[-2].price:
            return None
        first, second = counter[-2], counter[-1]
        pullback = line_geometry_from_swings(candles, first, second, evaluated_index=evaluated_index,
            role="BULL_PULLBACK_CHANNEL_LINE", direction=direction, break_side="ABOVE")
        structural = [s for s in scan.swings if s.kind == "LOW" and s.confirmed_at_index <= evaluated_index]
    elif direction == "BEAR_TREND":
        counter = [s for s in scan.swings if s.kind == "LOW" and s.confirmed_at_index <= evaluated_index]
        if len(counter) < 2 or counter[-1].price <= counter[-2].price:
            return None
        first, second = counter[-2], counter[-1]
        pullback = line_geometry_from_swings(candles, first, second, evaluated_index=evaluated_index,
            role="BEAR_PULLBACK_CHANNEL_LINE", direction=direction, break_side="BELOW")
        structural = [s for s in scan.swings if s.kind == "HIGH" and s.confirmed_at_index <= evaluated_index]
    else:
        return None
    if pullback is None:
        return None
    refs: list[tuple[str, Decimal]] = []
    trend = build_trend_line_geometry(candles, scan, direction=direction, evaluated_index=evaluated_index)
    channel = build_trend_channel_geometry(candles, scan, direction=direction, evaluated_index=evaluated_index)
    if trend is not None:
        refs.append((trend.role, trend.projected_value))
    if channel is not None:
        refs.append((channel.opposite_channel_line.role, channel.opposite_channel_line.projected_value))
    if ema_value is not None:
        refs.append(("EMA20", ema_value))
    if measured_move_value is not None:
        refs.append(("MEASURED_MOVE", measured_move_value))
    if structural:
        refs.append(("CONFIRMED_SWING_SUPPORT_RESISTANCE", structural[-1].price))
    if not refs:
        return None
    source, value = min(refs, key=lambda item: abs(item[1] - pullback.projected_value))
    separation = abs(value - pullback.projected_value)
    return DuelingLinesConfluence(
        direction=direction, pullback_line=pullback, support_source=source,
        support_value=value, separation=separation, tolerance=tolerance,
        confluent=separation <= tolerance,
    )


def build_parabolic_wedge_geometry(
    candles: tuple[Candle, ...], scan: SwingScanResult, *, side: str, evaluated_index: int,
) -> ParabolicWedgeGeometry | None:
    if side == "TOP":
        pushes = [s for s in scan.swings if s.kind == "HIGH" and s.confirmed_at_index <= evaluated_index][-3:]
        direction = "BULL_TREND"
        if len(pushes) < 3 or not (pushes[0].price < pushes[1].price < pushes[2].price):
            return None
        d1 = pushes[1].candle_index - pushes[0].candle_index; d2 = pushes[2].candle_index - pushes[1].candle_index
        if d1 <= 0 or d2 <= 0: return None
        slope1=(pushes[1].price-pushes[0].price)/Decimal(d1); slope2=(pushes[2].price-pushes[1].price)/Decimal(d2)
        accelerating=slope2 > slope1 > 0
    elif side == "BOTTOM":
        pushes = [s for s in scan.swings if s.kind == "LOW" and s.confirmed_at_index <= evaluated_index][-3:]
        direction = "BEAR_TREND"
        if len(pushes) < 3 or not (pushes[0].price > pushes[1].price > pushes[2].price):
            return None
        d1 = pushes[1].candle_index - pushes[0].candle_index; d2 = pushes[2].candle_index - pushes[1].candle_index
        if d1 <= 0 or d2 <= 0: return None
        slope1=(pushes[0].price-pushes[1].price)/Decimal(d1); slope2=(pushes[1].price-pushes[2].price)/Decimal(d2)
        accelerating=slope2 > slope1 > 0
    else:
        return None
    if not accelerating:
        return None
    # The third push must not define the channel boundary it is being tested against.
    # Reuse the canonical WAVE_03 channel builder on only causally earlier swings.
    prior_scan = SwingScanResult(
        swings=tuple(s for s in scan.swings if s.candle_index < pushes[-1].candle_index),
        ambiguous_indices=scan.ambiguous_indices, left_bars=scan.left_bars, right_bars=scan.right_bars,
    )
    channel=build_trend_channel_geometry(candles, prior_scan, direction=direction, evaluated_index=evaluated_index)
    overshoot=False
    if channel is not None:
        value=project_line_value(channel.opposite_channel_line, pushes[-1].candle_index)
        overshoot=pushes[-1].price > value if side=="TOP" else pushes[-1].price < value
    return ParabolicWedgeGeometry(
        side=side, push_indices=tuple(s.candle_index for s in pushes),
        first_slope=slope1, second_slope=slope2, accelerating=True,
        channel=channel, channel_overshoot=overshoot,
    )


def build_head_shoulders_lifecycle(
    candles: tuple[Candle, ...], scan: SwingScanResult, *, side: str, evaluated_index: int,
) -> HeadShouldersLifecycle | None:
    primary_kind = "HIGH" if side == "TOP" else "LOW" if side == "BOTTOM" else None
    opposite_kind = "LOW" if side == "TOP" else "HIGH"
    if primary_kind is None:
        return None
    primary=[s for s in scan.swings if s.kind==primary_kind and s.confirmed_at_index<=evaluated_index][-3:]
    if len(primary)<3: return None
    left, head, right=primary
    if side=="TOP" and not (head.price > left.price and head.price > right.price): return None
    if side=="BOTTOM" and not (head.price < left.price and head.price < right.price): return None
    opposite=[s for s in scan.swings if s.kind==opposite_kind and s.confirmed_at_index<=evaluated_index]
    first=next((s for s in opposite if left.candle_index < s.candle_index < head.candle_index),None)
    second=next((s for s in opposite if head.candle_index < s.candle_index < right.candle_index),None)
    if first is None or second is None: return None
    neckline=line_geometry_from_swings(candles,first,second,evaluated_index=evaluated_index,
        role="HEAD_SHOULDERS_NECKLINE",direction="SHORT" if side=="TOP" else "LONG",
        break_side="BELOW" if side=="TOP" else "ABOVE")
    if neckline is None: return None
    prior=build_trend_line_geometry(candles,scan,direction="BULL_TREND" if side=="TOP" else "BEAR_TREND",evaluated_index=evaluated_index)
    current=candles[evaluated_index]
    break_now=current.close < neckline.projected_value if side=="TOP" else current.close > neckline.projected_value
    prev_break=False
    if evaluated_index>0:
        pv=project_line_value(neckline,evaluated_index-1); pc=candles[evaluated_index-1].close
        prev_break=pc < pv if side=="TOP" else pc > pv
    reentry=prev_break and not break_now
    if reentry: state="FAILED_NECKLINE_BREAK_REENTRY"
    elif break_now and prev_break: state="CONTINUATION_BEYOND_NECKLINE"
    elif break_now: state="NECKLINE_BREAK"
    elif prior is not None and prior.break_evidence: state="RIGHT_SHOULDER_AFTER_TREND_LINE_BREAK"
    else: state="ALIAS_RANGE_OR_FLAG"
    return HeadShouldersLifecycle(
        side=side,left_shoulder_index=left.candle_index,head_index=head.candle_index,
        right_shoulder_index=right.candle_index,neckline=neckline,prior_trend_line=prior,
        state=state,neckline_break=break_now,neckline_reentry=reentry,
    )
