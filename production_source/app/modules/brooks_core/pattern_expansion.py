"""Phase-2 Brooks trilogy pattern expansion.

Detectors here distinguish observations from trade candidates. A named Brooks pattern
is not automatically an entry: breakout-mode, context and magnet patterns remain
non-actionable until price action supplies a directional trigger and enough reasons.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from app.modules.brooks_core.books_full_entities import (
    BrooksPatternCandidate,
    BrooksPatternObservation,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.causal_structure import confirm_swings_causally
from app.modules.brooks_core.correction_lifecycle import (
    ReversalPatternOrigin,
    classify_generic_reversal_attempts,
    classify_structural_correction,
    correction_reset_by_resumption,
    correction_step,
    evaluate_reversal_pattern_lifecycle,
    classify_hl_recurrence,
    evaluate_hl_entry_attempt_lifecycle,
    classify_range_hl_location,
    classify_head_shoulders_outcome,
    build_breakout_attempt_identity, classify_breakout_lifecycle,
    classify_failed_breakout_confirmation, classify_breakout_test, classify_near_breakout_pullback,
    CompactPatternOrigin, classify_compact_pattern_lifecycle,
)
from app.modules.brooks_core.context_classifier import (
    body_fraction,
    close_location,
    is_strong_bear_bar,
    is_strong_bull_bar,
    is_bear_reversal_bar_minimum,
    is_bull_reversal_bar_minimum,
    positive_price_overlap_rate,
    classify_strong_trend_evidence,
    assess_books_context,
)
from app.modules.brooks_core.structural_geometry import (
    build_trend_line_geometry,
    build_trend_channel_geometry,
    build_triangle_geometry,
    build_expanding_triangle_geometry,
    classify_expanding_triangle_lifecycle,
    classify_channel_boundary_event,
    build_dueling_lines_confluence,
    build_parabolic_wedge_geometry,
    build_head_shoulders_lifecycle,
    project_line_value,
    build_structural_second_test,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

_ZERO = Decimal("0")
_HALF = Decimal("0.5")
_ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class ExtendedPatternScan:
    observations: tuple[BrooksPatternObservation, ...]
    candidates: tuple[BrooksPatternCandidate, ...]


@dataclass(frozen=True, slots=True)
class MAGapEpisodeIdentity:
    """BROOKS-GAP-018: first MA-gap belongs to one active MA-slope/trend episode."""

    episode_id: str
    direction: str
    episode_start_index: int
    first_gap_index: int | None
    evaluated_index: int
    ma_slope_direction: str
    active: bool
    strong_trend_supported: bool
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class MAGapCountContext:
    """BROOKS-GAP-055: twenty is a source guide, not a magical hard gate."""

    direction: str
    evaluated_index: int
    consecutive_non_touch_bars: int
    twenty_bar_source_guide_met: bool
    strong_trend_supported: bool
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class MAGapMaturityContext:
    """BROOKS-GAP-020: MA-gap evidence can mark maturity/final-leg risk, not certainty."""

    context_id: str
    direction: str
    origin_episode_id: str
    evaluated_index: int
    first_gap_index: int | None
    second_attempt_index: int | None
    twenty_bar_source_guide_met: bool
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class SecondMAGapSequenceIdentity:
    """BROOKS-GAP-056: origin-preserving first attempt -> move-away -> second attempt."""

    sequence_id: str
    direction: str
    gap_run_start_index: int
    first_attempt_index: int
    move_away_index: int
    second_attempt_index: int
    evaluated_index: int
    state: str
    trade_eligible: bool = True



@dataclass(frozen=True, slots=True)
class CountertrendOpportunityIdentity:
    """BROOKS-GAP-061: scalp while old Always-In holds vs true reversal flip."""
    opportunity_id: str
    direction: str
    prior_always_in: str
    current_always_in: str
    signal_index: int
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class MinorReversalIdentity:
    """BROOKS-GAP-062: developed opposite swing while major trend remains intact."""
    reversal_id: str
    direction: str
    major_trend_direction: str
    origin_swing_index: int
    confirmed_at_index: int
    evaluated_index: int
    state: str
    trade_eligible: bool = False




def classify_countertrend_opportunity(
    *,
    direction: str,
    prior_always_in: str,
    current_always_in: str,
    signal_index: int,
) -> CountertrendOpportunityIdentity | None:
    """BROOKS-GAP-061: identity only; no automatic entry promotion."""
    if direction not in {"LONG","SHORT"} or prior_always_in not in {"LONG","SHORT"}:
        return None
    if direction == prior_always_in:
        return None
    if current_always_in == prior_always_in:
        state="COUNTERTREND_SCALP_OLD_TREND_INTACT"
    elif current_always_in == direction:
        state="REVERSAL_TRADE_ALWAYS_IN_FLIPPED"
    else:
        state="OPPOSITE_OPPORTUNITY_FLIP_UNRESOLVED"
    return CountertrendOpportunityIdentity(
        f"COUNTERTREND:{prior_always_in}:{direction}:{signal_index}",
        direction,prior_always_in,current_always_in,signal_index,state,False
    )


def classify_minor_reversal_identity(
    candles: tuple[Candle, ...],
    context,
    policy: BrooksFullCorePolicy,
    *,
    evaluated_index: int | None = None,
) -> MinorReversalIdentity | None:
    """BROOKS-GAP-062: requires a developed causal opposite swing, not one bar."""
    if not candles:
        return None
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    if end<2:
        return None
    trend=getattr(context,"structure_direction","AMBIGUOUS")
    always_in=getattr(context,"always_in","UNRESOLVED")
    if trend=="BULL_TREND" and always_in=="LONG":
        direction="SHORT"; kind="HIGH"
    elif trend=="BEAR_TREND" and always_in=="SHORT":
        direction="LONG"; kind="LOW"
    else:
        return None
    scan=confirm_swings_causally(
        tuple(candles[:end+1]),
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    swings=[x for x in scan.swings if x.kind==kind and x.confirmed_at_index<=end and x.candle_index<=end-2]
    if not swings:
        return None
    origin=swings[-1]
    if direction=="SHORT":
        developed=candles[end].close < candles[origin.candle_index].close and any(
            c.close<c.open for c in candles[origin.candle_index+1:end+1]
        )
    else:
        developed=candles[end].close > candles[origin.candle_index].close and any(
            c.close>c.open for c in candles[origin.candle_index+1:end+1]
        )
    if not developed:
        return None
    return MinorReversalIdentity(
        f"MINOR_REVERSAL:{direction}:{origin.candle_index}:{end}",
        direction,trend,origin.candle_index,origin.confirmed_at_index,end,
        "CONFIRMED_MINOR_REVERSAL_SWING_MAJOR_TREND_INTACT",False
    )


def _inside(current: Candle, previous: Candle) -> bool:
    return current.high <= previous.high and current.low >= previous.low


def _outside(current: Candle, previous: Candle) -> bool:
    return current.high >= previous.high and current.low <= previous.low


def _body_inside(current: Candle, previous: Candle) -> bool:
    c_lo, c_hi = sorted((current.open, current.close))
    p_lo, p_hi = sorted((previous.open, previous.close))
    return c_lo >= p_lo and c_hi <= p_hi


def _bodies_only_ii_at(candles: tuple[Candle, ...], end_index: int) -> bool:
    if end_index < 2:
        return False
    a, b, c = candles[end_index-2:end_index+1]
    return _body_inside(b, a) and _body_inside(c, b) and not (_inside(b, a) and _inside(c, b))


def _bull_reversal(candle: Candle) -> bool:
    return is_bull_reversal_bar_minimum(candle)


def _bear_reversal(candle: Candle) -> bool:
    return is_bear_reversal_bar_minimum(candle)


def _span(candles: tuple[Candle, ...]) -> Decimal:
    if not candles:
        return _ZERO
    return max(c.high for c in candles) - min(c.low for c in candles)


def _median_range(candles: tuple[Candle, ...]) -> Decimal:
    values = [c.high - c.low for c in candles if c.high > c.low]
    return _ZERO if not values else median(values)


def _ema20(candles: tuple[Candle, ...]) -> tuple[Decimal, ...]:
    if not candles:
        return ()
    alpha = Decimal("2") / Decimal("21")
    value = candles[0].close
    out = [value]
    for candle in candles[1:]:
        value = candle.close * alpha + value * (_ONE - alpha)
        out.append(value)
    return tuple(out)


def _obs(pattern_id: str, name: str, role: str, index: int, *,
         direction: str = "UNRESOLVED", rule_ids: tuple[str, ...] = (),
         metadata: tuple[tuple[str, str], ...] = ()) -> BrooksPatternObservation:
    return BrooksPatternObservation(
        pattern_id=pattern_id,
        pattern_name=name,
        role=role,
        signal_index=index,
        direction=direction,
        source_rule_ids=rule_ids,
        metadata=metadata,
    )


def scan_signal_bar_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    candles = snapshot.candles
    last = len(candles) - 1
    final = candles[-1]
    out: list[BrooksPatternObservation] = []

    if len(candles) >= 2:
        previous = candles[-2]
        if _inside(final, previous):
            out.append(_obs("INSIDE_BAR", "Inside Bar", "BREAKOUT_MODE", last,
                            rule_ids=("BB-TRD-04-CANDLE-PATTERNS",)))
        if _outside(final, previous):
            out.append(_obs("OUTSIDE_BAR", "Outside Bar", "CONTEXT", last,
                            rule_ids=("BB-TRD-07-OUTSIDE-BAR",)))

    if len(candles) >= 3:
        a, b, c = candles[-3:]
        if _inside(b, a) and _inside(c, b):
            out.append(_obs("II", "ii", "BREAKOUT_MODE", last,
                            rule_ids=("BB-TRD-06-II-III",)))
        if _outside(b, a) and _outside(c, b):
            out.append(_obs("OO", "oo", "CONTEXT", last,
                            rule_ids=("BB-TRD-07-OUTSIDE-BAR",)))
        if _outside(a, candles[-4]) if len(candles) >= 4 else False:
            if _inside(b, a) and _outside(c, b):
                out.append(_obs("OIO", "oio", "CONTEXT", last,
                                rule_ids=("BB-TRD-07-OUTSIDE-BAR",)))

    if len(candles) >= 4:
        a, b, c, d = candles[-4:]
        if _inside(b, a) and _inside(c, b) and _inside(d, c):
            out.append(_obs("III", "iii", "BREAKOUT_MODE", last,
                            rule_ids=("BB-TRD-06-II-III",)))
        if _inside(b, a) and _outside(c, b) and _inside(d, c):
            out.append(_obs("IOI", "ioi", "BREAKOUT_MODE", last,
                            rule_ids=("BB-TRD-06-IOI",)))
        nested_ioi = (
            _inside(b, a)
            and _outside(c, b)
            and _inside(c, a)
            and _inside(d, c)
        )
        if nested_ioi:
            out.append(_obs(
                "NESTED_IOI", "Nested ioi", "BREAKOUT_MODE", last,
                rule_ids=("BB-TRD-06-IOI",),
                metadata=(("taxonomy", "SOURCE_INTERPRETATION_FROM_IOI_PLUS_NESTING"),),
            ))

    if _bodies_only_ii_at(candles, last):
        out.append(_obs(
            "BODIES_ONLY_II", "Bodies-only ii", "BREAKOUT_MODE", last,
            rule_ids=("BB-RNG-BODIES-ONLY-II",),
            metadata=(
                ("semantic", "SOURCE_VARIANT_TAILS_IGNORED_LESS_RELIABLE"),
                ("trade_eligible", "false"),
            ),
        ))

    direction = (
        "LONG"
        if final.close > final.open
        else ("SHORT" if final.close < final.open else "UNRESOLVED")
    )
    if final.high == max(final.open, final.close) or final.low == min(final.open, final.close):
        out.append(_obs("SHAVED_BAR", "Shaved Bar", "CONTEXT", last,
                        direction=direction, rule_ids=("BB-TRD-06-SHAVED-BAR",)))

    baseline = candles[-25:-1] if len(candles) >= 25 else candles[:-1]
    typical = _median_range(tuple(baseline))
    if typical > 0 and (final.high - final.low) >= typical * policy.climax_range_multiple_of_recent_median:
        trend_side = "LONG" if context.structure_direction == "BULL_TREND" else "SHORT" if context.structure_direction == "BEAR_TREND" else "UNRESOLVED"
        if direction == trend_side and direction != "UNRESOLVED":
            out.append(_obs("LARGE_TREND_BAR", "Large Trend Bar", "CONTEXT", last,
                            direction=direction, rule_ids=("BB-TRD-06-EXHAUSTION-BAR",),
                            metadata=(("semantic","ENGINEERING_SIZE_EVIDENCE_NOT_EXHAUSTION_IDENTITY"),)))

    if len(candles) >= 2:
        previous = candles[-2]
        two_bar_bull = (
            is_strong_bear_bar(previous, policy.context)
            and is_strong_bull_bar(final, policy.context)
        )
        two_bar_bear = (
            is_strong_bull_bar(previous, policy.context)
            and is_strong_bear_bar(final, policy.context)
        )
        if two_bar_bull or two_bar_bear:
            out.append(_obs("TWO_BAR_REVERSAL", "Two-Bar Reversal", "ENTRY_CONTEXT", last,
                            direction="LONG" if two_bar_bull else "SHORT",
                            rule_ids=("BB-TRD-05-TWO-BAR-REVERSAL",)))

    if len(candles) >= 3:
        a, b, c = candles[-3:]
        bull = a.close < a.open and c.close > c.open and c.close > b.high
        bear = a.close > a.open and c.close < c.open and c.close < b.low
        if bull or bear:
            out.append(_obs("THREE_BAR_REVERSAL", "Three-Bar Reversal", "ENTRY_CONTEXT", last,
                            direction="LONG" if bull else "SHORT",
                            rule_ids=("BB-TRD-05-THREE-BAR-REVERSAL",)))

    recent = candles[-6:]
    tolerance = (
        _median_range(tuple(recent))
        * policy.micro_double_tolerance_fraction_of_median_range
    )
    if tolerance > 0 and len(recent) >= 2:
        lows = [c.low for c in recent]
        highs = [c.high for c in recent]
        if sum(abs(x - lows[-1]) <= tolerance for x in lows[:-1]) >= 1:
            out.append(_obs("BULL_LEDGE", "Bull Ledge", "CONTEXT", last,
                            direction="LONG", rule_ids=("BB-TRD-06-LEDGE",)))
        if sum(abs(x - highs[-1]) <= tolerance for x in highs[:-1]) >= 1:
            out.append(_obs("BEAR_LEDGE", "Bear Ledge", "CONTEXT", last,
                            direction="SHORT", rule_ids=("BB-TRD-06-LEDGE",)))

    if len(candles) >= 20:
        ema = _ema20(candles)[-1]
        if final.low > ema:
            out.append(_obs(
                "GAP_BAR_ABOVE_MA", "Moving Average Gap Bar Above MA", "CONTEXT", last,
                direction="LONG", rule_ids=("BB-RNG-14-GAP-BAR",),
                metadata=(("ema", str(ema)), ("taxonomy", "SOURCE_RULE")),
            ))
        elif final.high < ema:
            out.append(_obs(
                "GAP_BAR_BELOW_MA", "Moving Average Gap Bar Below MA", "CONTEXT", last,
                direction="SHORT", rule_ids=("BB-RNG-14-GAP-BAR",),
                metadata=(("ema", str(ema)), ("taxonomy", "SOURCE_RULE")),
            ))

    return tuple(out)


def scan_generic_breakout_attempt_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    """Causal price-extension breakout attempts (BROOKS-GAP-033).

    An attempt exists when the current closed bar trades beyond the latest causal
    swing level.  Closing beyond, strength and follow-through remain separate
    evidence; wick-only penetration is observation-only and never a trade signal.
    """
    candles = snapshot.candles
    if len(candles) < policy.context.swing_left_bars + policy.context.swing_right_bars + 3:
        return ()
    prior = candles[:-1]
    scan = confirm_swings_causally(
        prior,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    final = candles[-1]
    out: list[BrooksPatternObservation] = []
    for direction, kind in (("LONG", "HIGH"), ("SHORT", "LOW")):
        matches = [item for item in scan.swings if item.kind == kind]
        if not matches:
            continue
        swing = matches[-1]
        level = (
            candles[swing.candle_index].high
            if kind == "HIGH"
            else candles[swing.candle_index].low
        )
        extended = final.high > level if direction == "LONG" else final.low < level
        if not extended:
            continue
        closed_beyond = final.close > level if direction == "LONG" else final.close < level
        strong = (
            is_strong_bull_bar(final, policy.context)
            if direction == "LONG"
            else is_strong_bear_bar(final, policy.context)
        )
        out.append(_obs(
            f"BREAKOUT_ATTEMPT_{direction}",
            f"Breakout Attempt {direction.title()}",
            "BREAKOUT_ATTEMPT",
            len(candles) - 1,
            direction=direction,
            rule_ids=("BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",),
            metadata=(
                ("reference_swing_index", str(swing.candle_index)),
                ("reference_level", str(level)),
                ("closed_beyond", "true" if closed_beyond else "false"),
                ("strong_bar", "true" if strong else "false"),
            ),
        ))
    return tuple(out)


def _pattern_ending_before_final(candles: tuple[Candle, ...]) -> str | None:
    if len(candles) >= 5:
        a, b, c, d = candles[-5], candles[-4], candles[-3], candles[-2]
        if _inside(b, a) and _inside(c, b) and _inside(d, c):
            return "III"
        if _inside(b, a) and _outside(c, b) and _inside(c, a) and _inside(d, c):
            return "NESTED_IOI"
        if _inside(b, a) and _outside(c, b) and _inside(d, c):
            return "IOI"
    if len(candles) >= 4:
        a, b, c = candles[-4], candles[-3], candles[-2]
        if _inside(b, a) and _inside(c, b):
            return "II"
    return None

def detect_candle_pattern_breakouts(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    candles = snapshot.candles
    pattern = _pattern_ending_before_final(candles)
    if pattern is None:
        return ()
    signal = candles[-2]
    final = candles[-1]
    out: list[BrooksPatternCandidate] = []
    for direction in ("LONG", "SHORT"):
        triggered = final.close > signal.high if direction == "LONG" else final.close < signal.low
        strong = is_strong_bull_bar(final, policy.context) if direction == "LONG" else is_strong_bear_bar(final, policy.context)
        if not (triggered and strong):
            continue
        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"{pattern}_BREAKOUT_{direction}",
            family="BREAKOUT",
            signal_index=len(candles) - 1,
            reasons=(f"{pattern.lower()}_breakout_mode_pattern", "strong_directional_breakout_trigger", f"context_{context.regime.lower()}"),
            source_rule_ids=("BB-TRD-06-BREAKOUT-MODE", "BB-RNG-02-BREAKOUT-FOLLOWTHROUGH", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION",
            priority=19,
            context_required="BREAKOUT_OR_TREND",
            metadata=(("pattern", pattern),),
        ))
    return tuple(out)


def detect_reversal_bar_failure(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    candles = snapshot.candles
    if len(candles) < 2:
        return ()
    previous = candles[-2]
    cases = []
    if context.regime == "BULL_TREND" and _bear_reversal(previous):
        cases.append(("LONG", ReversalPatternOrigin(
            attempt_id=f"REVERSAL_BAR_SHORT@{len(candles)-2}", pattern_id="BEAR_REVERSAL_BAR",
            direction="SHORT", signal_index=len(candles)-2,
            trigger_level=previous.low, objective_level=None, failure_level=previous.high,
        )))
    if context.regime == "BEAR_TREND" and _bull_reversal(previous):
        cases.append(("SHORT", ReversalPatternOrigin(
            attempt_id=f"REVERSAL_BAR_LONG@{len(candles)-2}", pattern_id="BULL_REVERSAL_BAR",
            direction="LONG", signal_index=len(candles)-2,
            trigger_level=previous.high, objective_level=None, failure_level=previous.low,
        )))
    out=[]
    for continuation_direction, origin in cases:
        life=evaluate_reversal_pattern_lifecycle(candles, origin)
        if life.state != "SIGNAL_INVALIDATED_BEFORE_TRIGGER":
            continue
        out.append(BrooksPatternCandidate(
            direction=continuation_direction,
            setup_type="BEAR_REVERSAL_BAR_FAILURE_LONG" if continuation_direction=="LONG" else "BULL_REVERSAL_BAR_FAILURE_SHORT",
            family="FAILED_FAILURE", signal_index=len(candles)-1,
            reasons=("originating_reversal_signal_invalidated_before_trigger", "wrong_side_breakout_of_owned_signal_bar", f"with_trend_{context.regime.lower()}_context"),
            source_rule_ids=("BB-TRD-06-REVERSAL-BAR-FAILURE", "BB-REV-09-FAILURES", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=8, context_required=context.regime,
            metadata=(("attempt_id", origin.attempt_id), ("origin_pattern_id", origin.pattern_id),
                      ("trigger_level", str(origin.trigger_level)), ("failure_level", str(origin.failure_level)),
                      ("lifecycle_state", life.state)),
        ))
    return tuple(out)


def _ma_direction_from_context(context) -> str | None:
    regime = getattr(context, "regime", "AMBIGUOUS")
    always_in = getattr(context, "always_in", "UNRESOLVED")
    if regime == "BULL_TREND" and always_in == "LONG":
        return "LONG"
    if regime == "BEAR_TREND" and always_in == "SHORT":
        return "SHORT"
    return None


def _ma_slope_direction(ema: tuple[Decimal, ...], index: int) -> str:
    if index <= 0 or index >= len(ema):
        return "FLAT"
    if ema[index] > ema[index - 1]:
        return "LONG"
    if ema[index] < ema[index - 1]:
        return "SHORT"
    return "FLAT"


def _gap_side(candle: Candle, ema_value: Decimal, direction: str) -> bool:
    # In a bull-trend pullback the MA-gap bar is wholly below the MA; bear mirror above it.
    if direction == "LONG":
        return candle.high < ema_value
    if direction == "SHORT":
        return candle.low > ema_value
    return False


def _trend_side_non_touch(candle: Candle, ema_value: Decimal, direction: str) -> bool:
    # Twenty-gap condition before the first MA touch: bull bars remain wholly above,
    # bear bars remain wholly below the MA.
    if direction == "LONG":
        return candle.low > ema_value
    if direction == "SHORT":
        return candle.high < ema_value
    return False


def _touches_ma(candle: Candle, ema_value: Decimal) -> bool:
    return candle.low <= ema_value <= candle.high


def _consecutive_trend_side_non_touch(
    candles: tuple[Candle, ...],
    ema: tuple[Decimal, ...],
    *,
    direction: str,
    before_index: int,
) -> int:
    count = 0
    for i in range(before_index - 1, -1, -1):
        if not _trend_side_non_touch(candles[i], ema[i], direction):
            break
        count += 1
    return count


def classify_ma_gap_episode(
    candles: tuple[Candle, ...],
    ema: tuple[Decimal, ...],
    context,
    policy: BrooksFullCorePolicy,
    *,
    evaluated_index: int | None = None,
) -> MAGapEpisodeIdentity | None:
    """BROOKS-GAP-018: active first-gap identity with MA-slope reset semantics.

    The episode is the current contiguous run of MA slope aligned with the active
    Always-In trend.  This prevents rolling-memory expiry from manufacturing a new
    FIRST gap.  A true slope-cycle reversal creates a new episode identity.
    """
    if not candles or len(candles) != len(ema):
        return None
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    direction = _ma_direction_from_context(context)
    if direction is None or end < 1:
        return None
    slope_direction = _ma_slope_direction(ema, end)
    if slope_direction != direction:
        return MAGapEpisodeIdentity(
            f"MA_GAP_EPISODE:{direction}:INACTIVE:{end}", direction, end, None, end,
            slope_direction, False, False, "MA_SLOPE_NOT_ALIGNED_WITH_ACTIVE_TREND", False
        )

    start = end - 1
    while start > 0 and _ma_slope_direction(ema, start) == direction:
        start -= 1
    if start < end and _ma_slope_direction(ema, start) != direction:
        start += 1

    first_gap = next(
        (i for i in range(start, end + 1) if _gap_side(candles[i], ema[i], direction)),
        None,
    )
    strong_index = max(start, (first_gap - 1) if first_gap is not None and first_gap > start else end - 1)
    strong = classify_strong_trend_evidence(
        candles, context, policy.context, evaluated_index=max(1, strong_index)
    )
    strong_supported = bool(strong.is_strong and strong.direction == direction)
    state = (
        "ACTIVE_STRONG_TREND_FIRST_MA_GAP_AVAILABLE"
        if first_gap is not None and strong_supported
        else "ACTIVE_MA_SLOPE_EPISODE_NO_STRONG_FIRST_GAP"
    )
    return MAGapEpisodeIdentity(
        f"MA_GAP_EPISODE:{direction}:{start}", direction, start, first_gap, end,
        slope_direction, True, strong_supported, state, False
    )


def classify_ma_gap_count_context(
    candles: tuple[Candle, ...],
    ema: tuple[Decimal, ...],
    context,
    policy: BrooksFullCorePolicy,
    *,
    evaluated_index: int | None = None,
) -> MAGapCountContext | None:
    """BROOKS-GAP-055: expose count as a guide without making 20 universal."""
    if not candles or len(candles) != len(ema):
        return None
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    direction = _ma_direction_from_context(context)
    if direction is None or end < 1 or not _touches_ma(candles[end], ema[end]):
        return None
    count = _consecutive_trend_side_non_touch(candles, ema, direction=direction, before_index=end)
    if count <= 0:
        return None
    strong = classify_strong_trend_evidence(
        candles, context, policy.context, evaluated_index=end - 1
    )
    supported = bool(strong.is_strong and strong.direction == direction)
    guide = count >= 20  # SOURCE_GUIDE: Brooks explicitly says nothing magical about 20.
    state = (
        "TWENTY_BAR_SOURCE_GUIDE_MET"
        if guide
        else "STRONG_TREND_MA_TEST_BELOW_TWENTY_SOURCE_GUIDE"
        if supported
        else "MA_TEST_COUNT_CONTEXT_WITHOUT_STRONG_TREND_CONFIRMATION"
    )
    return MAGapCountContext(direction, end, count, guide, supported, state, False)


def _second_ma_gap_sequence(
    candles: tuple[Candle, ...],
    ema: tuple[Decimal, ...],
    *,
    direction: str,
) -> SecondMAGapSequenceIdentity | None:
    """BROOKS-GAP-056 causal sequence without legacy over-constrained predicates.

    Source sequence: first reversal toward the MA fails to reach it, price moves
    away, then a later reversal toward the MA becomes the second attempt.  Full-bar
    non-touch identifies the MA-gap run; distance-to-MA change is an explicit
    ENGINEERING_CLASSIFICATION_POLICY for "toward" versus "away", not a Brooks
    universal price threshold.
    """
    if len(candles) != len(ema) or len(candles) < 3 or direction not in {"LONG", "SHORT"}:
        return None
    last = len(candles) - 1
    if not _gap_side(candles[last], ema[last], direction):
        return None

    start = last
    while start > 0 and _gap_side(candles[start - 1], ema[start - 1], direction):
        start -= 1
    if last - start < 2:
        return None

    def distance(i: int) -> Decimal:
        return (ema[i] - candles[i].close) if direction == "LONG" else (candles[i].close - ema[i])

    def toward(i: int) -> bool:
        if not _gap_side(candles[i], ema[i], direction):
            return False
        if i == start:
            return candles[i].close > candles[i].open if direction == "LONG" else candles[i].close < candles[i].open
        directional = candles[i].close > candles[i - 1].close if direction == "LONG" else candles[i].close < candles[i - 1].close
        return directional and distance(i) < distance(i - 1)

    if not toward(last):
        return None
    first_attempt = next((i for i in range(start, last - 1) if toward(i)), None)
    if first_attempt is None:
        return None
    move_away = next(
        (
            i for i in range(first_attempt + 1, last)
            if _gap_side(candles[i], ema[i], direction) and distance(i) > distance(i - 1)
        ),
        None,
    )
    if move_away is None:
        return None
    return SecondMAGapSequenceIdentity(
        f"SECOND_MA_GAP:{direction}:{start}:{first_attempt}:{move_away}:{last}",
        direction, start, first_attempt, move_away, last, last,
        "SECOND_ATTEMPT_TOWARD_MA_AFTER_FIRST_ATTEMPT_FAILED_AND_MOVED_AWAY", True
    )


def classify_ma_gap_maturity_context(
    episode: MAGapEpisodeIdentity | None,
    count_context: MAGapCountContext | None,
    second_sequence: SecondMAGapSequenceIdentity | None,
    *,
    evaluated_index: int,
) -> MAGapMaturityContext | None:
    """BROOKS-GAP-020: maturity/final-leg risk is context, never a prediction."""
    if episode is None or not episode.active:
        return None
    source_guide = bool(count_context and count_context.twenty_bar_source_guide_met)
    second_index = second_sequence.second_attempt_index if second_sequence is not None else None
    if episode.first_gap_index is None and second_index is None and not source_guide:
        return None
    if not episode.strong_trend_supported and second_sequence is None and not source_guide:
        return None
    return MAGapMaturityContext(
        f"MA_GAP_MATURITY:{episode.episode_id}:{evaluated_index}",
        episode.direction, episode.episode_id, evaluated_index, episode.first_gap_index,
        second_index, source_guide,
        "MA_GAP_TREND_MATURITY_FINAL_LEG_RISK_CONTEXT_NOT_REVERSAL_PREDICTION", False
    )


def scan_ma_gap_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    """WAVE_13 context/lifecycle observations; no automatic trade promotion."""
    candles = snapshot.candles
    if len(candles) < 2:
        return ()
    ema = _ema20(candles)
    direction = _ma_direction_from_context(context)
    if direction is None:
        return ()
    end = len(candles) - 1
    episode = classify_ma_gap_episode(candles, ema, context, policy, evaluated_index=end)
    count_context = classify_ma_gap_count_context(
        candles, ema, context, policy, evaluated_index=end
    )
    second = _second_ma_gap_sequence(candles, ema, direction=direction)
    maturity = classify_ma_gap_maturity_context(
        episode, count_context, second, evaluated_index=end
    )
    out: list[BrooksPatternObservation] = []
    if episode is not None:
        out.append(_obs(
            "MA_GAP_EPISODE", "MA-gap Episode Identity", "TREND_CONTEXT", end,
            direction=direction, rule_ids=("BB-RNG-14-FIRST-MA-GAP",),
            metadata=(
                ("canonical_gap_id", "BROOKS-GAP-018"),
                ("episode_id", episode.episode_id),
                ("episode_start_index", str(episode.episode_start_index)),
                ("first_gap_index", "" if episode.first_gap_index is None else str(episode.first_gap_index)),
                ("ma_slope_direction", episode.ma_slope_direction),
                ("strong_trend_supported", "true" if episode.strong_trend_supported else "false"),
                ("state", episode.state), ("trade_eligible", "false"),
            ),
        ))
    if count_context is not None:
        out.append(_obs(
            "MA_GAP_COUNT_CONTEXT", "MA-gap Count Source Guide", "TREND_CONTEXT", end,
            direction=direction, rule_ids=("BB-RNG-13-TWENTY-GAP",),
            metadata=(
                ("canonical_gap_id", "BROOKS-GAP-055"),
                ("consecutive_non_touch_bars", str(count_context.consecutive_non_touch_bars)),
                ("twenty_bar_source_guide_met", "true" if count_context.twenty_bar_source_guide_met else "false"),
                ("strong_trend_supported", "true" if count_context.strong_trend_supported else "false"),
                ("state", count_context.state),
                ("semantic", "TWENTY_IS_SOURCE_GUIDE_NOT_UNIVERSAL_HARD_GATE"),
                ("trade_eligible", "false"),
            ),
        ))
    if maturity is not None:
        out.append(_obs(
            "MA_GAP_TREND_MATURITY_CONTEXT", "MA-gap Trend Maturity / Final-leg Risk Context",
            "TREND_MATURITY_CONTEXT", end, direction=direction,
            rule_ids=("BB-TRD-19-TREND-STRENGTH", "BB-RNG-14-FIRST-MA-GAP"),
            metadata=(
                ("canonical_gap_id", "BROOKS-GAP-020"),
                ("context_id", maturity.context_id),
                ("origin_episode_id", maturity.origin_episode_id),
                ("first_gap_index", "" if maturity.first_gap_index is None else str(maturity.first_gap_index)),
                ("second_attempt_index", "" if maturity.second_attempt_index is None else str(maturity.second_attempt_index)),
                ("twenty_bar_source_guide_met", "true" if maturity.twenty_bar_source_guide_met else "false"),
                ("state", maturity.state),
                ("trade_eligible", "false"),
            ),
        ))
    return tuple(out)


def detect_moving_average_pullback_setups(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    candles = snapshot.candles
    direction = _ma_direction_from_context(context)
    if len(candles) < 3 or direction is None:
        return ()
    ema = _ema20(candles)
    end = len(candles) - 1
    final = candles[end]
    out: list[BrooksPatternCandidate] = []

    episode = classify_ma_gap_episode(candles, ema, context, policy, evaluated_index=end)
    prior_strong = classify_strong_trend_evidence(
        candles, context, policy.context, evaluated_index=end - 1
    )
    prior_strong_supported = bool(prior_strong.is_strong and prior_strong.direction == direction)

    # BROOKS-GAP-019: the literal twenty-or-more condition belongs only to the
    # named twenty-gap first-touch setup. A reversal-bar stop-entry is NOT a
    # universal prerequisite; first-touch/limit-entry semantics are represented.
    non_touch_count = _consecutive_trend_side_non_touch(
        candles, ema, direction=direction, before_index=end
    )
    if (
        non_touch_count >= 20
        and _touches_ma(final, ema[end])
        and prior_strong_supported
    ):
        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"TWENTY_GAP_BAR_{direction}",
            family="TREND_CONTINUATION",
            signal_index=end,
            reasons=(
                "twenty_or_more_consecutive_bars_without_touching_ema",
                "first_ma_touch_after_extended_non_touch_sequence",
                "strong_with_trend_context",
                "first_touch_or_limit_entry_variant_does_not_require_reversal_bar",
            ),
            source_rule_ids=("BB-RNG-13-TWENTY-GAP", "BB-TRD-19-TREND-STRENGTH", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=7, context_required=context.regime,
            metadata=(
                ("ema20", str(ema[end])),
                ("consecutive_non_touch_bars", str(non_touch_count)),
                ("canonical_gap_id", "BROOKS-GAP-019"),
                ("entry_semantic", "FIRST_TOUCH_AT_OR_NEAR_MA_SOURCE_VARIANT"),
                ("twenty_bar_condition", "SOURCE_OWNED_FOR_BROOKS_GAP_019_ONLY"),
            ),
        ))

    # BROOKS-GAP-018: only the FIRST gap in the active MA-slope episode can own
    # FIRST semantics.  No rolling 20-bar memory can manufacture a later FIRST.
    if (
        episode is not None
        and episode.active
        and episode.strong_trend_supported
        and episode.first_gap_index == end
        and ((_bull_reversal(final) and direction == "LONG") or (_bear_reversal(final) and direction == "SHORT"))
    ):
        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"FIRST_MA_GAP_BAR_{direction}",
            family="TREND_CONTINUATION",
            signal_index=end,
            reasons=(
                "first_ma_gap_in_active_strong_trend_episode",
                "ma_slope_aligned_with_active_trend",
                "with_trend_reversal_from_first_gap_for_test_of_extreme",
            ),
            source_rule_ids=("BB-RNG-14-FIRST-MA-GAP", "BB-TRD-19-TREND-STRENGTH", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=11, context_required=context.regime,
            metadata=(
                ("ema20", str(ema[end])),
                ("canonical_gap_id", "BROOKS-GAP-018"),
                ("episode_id", episode.episode_id),
                ("episode_start_index", str(episode.episode_start_index)),
                ("first_gap_index", str(episode.first_gap_index)),
                ("ma_slope_direction", episode.ma_slope_direction),
            ),
        ))

    second = _second_ma_gap_sequence(candles, ema, direction=direction)
    if second is not None:
        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"SECOND_MA_GAP_BAR_{direction}",
            family="TREND_CONTINUATION",
            signal_index=end,
            reasons=(
                "first_reversal_toward_ma_failed_to_reach_ma",
                "price_moved_away_after_first_attempt",
                "second_reversal_toward_ma",
            ),
            source_rule_ids=("BB-RNG-14-SECOND-MA-GAP", "BB-TRD-19-TREND-STRENGTH", "BB-RNG-26-TWO-REASONS"),
            taxonomy="BOOK_INTERPRETATION", priority=9, context_required=context.regime,
            metadata=(
                ("ema20", str(ema[end])),
                ("canonical_gap_id", "BROOKS-GAP-056"),
                ("sequence_id", second.sequence_id),
                ("gap_run_start_index", str(second.gap_run_start_index)),
                ("first_attempt_index", str(second.first_attempt_index)),
                ("failure_index", str(second.move_away_index)),
                ("move_away_index", str(second.move_away_index)),
                ("second_attempt_index", str(second.second_attempt_index)),
                ("engineering_policy", "DISTANCE_TO_MA_DIRECTION_OF_CHANGE_NOT_SOURCE_THRESHOLD"),
            ),
        ))
    return tuple(out)


def detect_double_top_bottom_pullback(
    snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    """Use the BROOKS-GAP-051 structural double identity for later pullback tests."""
    candles=snapshot.candles
    if len(candles)<20:
        return ()
    scan=confirm_swings_causally(candles[:-1],left_bars=policy.context.swing_left_bars,right_bars=policy.context.swing_right_bars)
    final=candles[-1]; out=[]
    for side,direction,blocked,reversal in (("BOTTOM","LONG",context.regime=="BEAR_TREND",_bull_reversal(final)),("TOP","SHORT",context.regime=="BULL_TREND",_bear_reversal(final))):
        if blocked or not reversal:
            continue
        structure=build_structural_second_test(candles,scan,side=side,evaluated_index=len(candles)-2)
        if structure is None:
            continue
        between=candles[structure.second_test_index+1:-1]
        moved_away=(bool(between) and (max(c.high for c in between)>candles[structure.second_test_index].high if side=="BOTTOM" else min(c.low for c in between)<candles[structure.second_test_index].low))
        level=final.low if side=="BOTTOM" else final.high
        recent=candles[-policy.range_window_bars:]
        engineering_tolerance=_span(tuple(recent))*policy.double_test_tolerance_fraction_of_recent_range  # ENGINEERING_TOLERANCE only
        tests_zone=structure.zone_low-engineering_tolerance<=level<=structure.zone_high+engineering_tolerance
        if not (moved_away and tests_zone):
            continue
        name="DOUBLE_BOTTOM_PULLBACK_LONG" if side=="BOTTOM" else "DOUBLE_TOP_PULLBACK_SHORT"
        out.append(BrooksPatternCandidate(
            direction=direction,setup_type=name,family="BREAKOUT_PULLBACK",signal_index=len(candles)-1,
            reasons=("structural_double_test_established","move_away_from_second_test","later_pullback_retests_structural_zone_and_reverses"),
            source_rule_ids=(("BB-REV-08-DOUBLE-BOTTOM-PULLBACK","BB-RNG-05-BREAKOUT-PULLBACK","BB-RNG-26-TWO-REASONS") if side=="BOTTOM" else ("BB-REV-08-DOUBLE-TOP-PULLBACK","BB-RNG-05-BREAKOUT-PULLBACK","BB-RNG-26-TWO-REASONS")),
            taxonomy="SOURCE_INTERPRETATION",priority=6,context_required="REVERSAL_OR_RANGE_EXTREME",
            metadata=(("structure_id",structure.structure_id),("first_test_index",str(structure.first_test_index)),("second_test_index",str(structure.second_test_index)),("price_relation",structure.price_relation)),
        ))
    return tuple(out)


def _alternating_recent_swings(snapshot: MarketSnapshot, policy: BrooksFullCorePolicy):
    scan = confirm_swings_causally(
        snapshot.candles,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    swings = list(scan.swings[-7:])
    out = []
    for swing in swings:
        if not out or out[-1].kind != swing.kind:
            out.append(swing)
        elif swing.candle_index > out[-1].candle_index:
            out[-1] = swing
    return tuple(out)


def detect_expanding_triangle(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    candles = snapshot.candles
    swings = _alternating_recent_swings(snapshot, policy)
    if len(swings) < 4:
        return ()
    prior = swings[-4:]
    final = candles[-1]
    out: list[BrooksPatternCandidate] = []

    kinds = tuple(s.kind for s in prior)
    if kinds == ("LOW", "HIGH", "LOW", "HIGH"):
        l1, h1, l2, h2 = prior
        low1, low2 = candles[l1.candle_index].low, candles[l2.candle_index].low
        high1, high2 = candles[h1.candle_index].high, candles[h2.candle_index].high
        if low2 < low1 and high2 > high1 and final.low < low2 and _bull_reversal(final):
            out.append(BrooksPatternCandidate(
                direction="LONG", setup_type="EXPANDING_TRIANGLE_BOTTOM_LONG", family="WEDGE_REVERSAL",
                signal_index=len(candles) - 1,
                reasons=("five_swing_expanding_triangle_sequence", "progressively_lower_lows_and_higher_highs", "third_low_reverses_up"),
                source_rule_ids=("BB-REV-06-EXPANDING-TRIANGLE", "BB-REV-03-MAJOR-TREND-REVERSAL", "BB-RNG-26-TWO-REASONS"),
                taxonomy="SOURCE_INTERPRETATION", priority=24, context_required="REVERSAL_OR_RANGE_EXTREME",
                metadata=(("swing_indices", ",".join(str(s.candle_index) for s in prior) + f",{len(candles)-1}"),),
            ))

    if kinds == ("HIGH", "LOW", "HIGH", "LOW"):
        h1, l1, h2, l2 = prior
        high1, high2 = candles[h1.candle_index].high, candles[h2.candle_index].high
        low1, low2 = candles[l1.candle_index].low, candles[l2.candle_index].low
        if high2 > high1 and low2 < low1 and final.high > high2 and _bear_reversal(final):
            out.append(BrooksPatternCandidate(
                direction="SHORT", setup_type="EXPANDING_TRIANGLE_TOP_SHORT", family="WEDGE_REVERSAL",
                signal_index=len(candles) - 1,
                reasons=("five_swing_expanding_triangle_sequence", "progressively_higher_highs_and_lower_lows", "third_high_reverses_down"),
                source_rule_ids=("BB-REV-06-EXPANDING-TRIANGLE", "BB-REV-03-MAJOR-TREND-REVERSAL", "BB-RNG-26-TWO-REASONS"),
                taxonomy="SOURCE_INTERPRETATION", priority=24, context_required="REVERSAL_OR_RANGE_EXTREME",
                metadata=(("swing_indices", ",".join(str(s.candle_index) for s in prior) + f",{len(candles)-1}"),),
            ))
    return tuple(out)


def _stairs_structure(swings, *, direction: str):
    """Classify Brooks broad-channel stairs from causal swings.

    BOOK_INTERPRETATION: Brooks requires trending swing extremes and breakout tests
    that retrace beyond prior breakout points.  We translate that literally to the
    last three same-side swing extremes plus the first opposite swing after each of
    the last two breakouts.  Shrinking stairs additionally requires strictly smaller
    positive breakout extensions.
    """
    if direction == "LONG":
        primary = [x for x in swings if x.kind == "HIGH"][-3:]
        secondary = [x for x in swings if x.kind == "LOW"]
        if len(primary) < 3 or len(secondary) < 3:
            return None
        if not all(b.price > a.price for a, b in zip(primary, primary[1:])):
            return None
        recent_lows = secondary[-3:]
        if not all(b.price > a.price for a, b in zip(recent_lows, recent_lows[1:])):
            return None
        overlaps = []
        for prev, breakout in zip(primary, primary[1:]):
            pullback = next((x for x in swings if x.kind == "LOW" and x.candle_index > breakout.candle_index), None)
            overlaps.append(pullback is not None and pullback.price < prev.price)
        extensions = tuple(b.price - a.price for a, b in zip(primary, primary[1:]))
    elif direction == "SHORT":
        primary = [x for x in swings if x.kind == "LOW"][-3:]
        secondary = [x for x in swings if x.kind == "HIGH"]
        if len(primary) < 3 or len(secondary) < 3:
            return None
        if not all(b.price < a.price for a, b in zip(primary, primary[1:])):
            return None
        recent_highs = secondary[-3:]
        if not all(b.price < a.price for a, b in zip(recent_highs, recent_highs[1:])):
            return None
        overlaps = []
        for prev, breakout in zip(primary, primary[1:]):
            pullback = next((x for x in swings if x.kind == "HIGH" and x.candle_index > breakout.candle_index), None)
            overlaps.append(pullback is not None and pullback.price > prev.price)
        extensions = tuple(a.price - b.price for a, b in zip(primary, primary[1:]))
    else:
        return None
    if not all(overlaps) or not all(x > 0 for x in extensions):
        return None
    shrinking = all(b < a for a, b in zip(extensions, extensions[1:]))
    return primary, extensions, shrinking


def scan_structure_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    candles = snapshot.candles
    swings = _alternating_recent_swings(snapshot, policy)
    out: list[BrooksPatternObservation] = []
    last = len(candles) - 1

    if len(swings) >= 5 and context.regime in {"TRADING_RANGE", "AMBIGUOUS"}:
        triangle = build_triangle_geometry(candles, tuple(swings), evaluated_index=last)
        if triangle is not None:
            out.append(_obs(
                "TRIANGLE", "Triangle / Converging Structural Range", "BREAKOUT_MODE", last,
                rule_ids=("BB-RNG-23-TRIANGLE",),
                metadata=(
                    ("swing_indices", ",".join(str(i) for i in triangle.swing_indices)),
                    ("context", context.regime),
                    ("upper_slope", str(triangle.upper_boundary.slope_per_bar)),
                    ("lower_slope", str(triangle.lower_boundary.slope_per_bar)),
                    ("projected_upper", str(triangle.upper_boundary.projected_value)),
                    ("projected_lower", str(triangle.lower_boundary.projected_value)),
                    ("containment_fraction", str(triangle.containment_fraction)),
                    ("semantic", "GEOMETRY_CONTEXT_NOT_TRADE_ELIGIBILITY"),
                ),
            ))
            tri_indices = tuple(triangle.swing_indices)
            tri_origin = CompactPatternOrigin(
                "TRIANGLE", "TRIANGLE:" + ":".join(str(i) for i in tri_indices), min(tri_indices), max(tri_indices),
                max(candles[i].high for i in tri_indices), min(candles[i].low for i in tri_indices),
            )
            tri_life = classify_compact_pattern_lifecycle(candles, tri_origin, evaluated_index=last)
            out.append(_obs(
                "TRIANGLE_COMPACT_LIFECYCLE", "Triangle Compact Pattern Lifecycle", "STRUCTURAL_CONTEXT", last,
                rule_ids=("BB-RNG-COMPACT-PATTERN-LIFECYCLE",),
                metadata=(("structure_id", tri_origin.structure_id), ("state", tri_life.state),
                          ("breakout_direction", tri_life.breakout_direction or ""),
                          ("reentry_index", "" if tri_life.reentry_index is None else str(tri_life.reentry_index)),
                          ("opposite_break_index", "" if tri_life.opposite_break_index is None else str(tri_life.opposite_break_index)),
                          ("trade_eligible", "false")),
            ))

    full_scan = confirm_swings_causally(
        candles,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    # WAVE_04: expanding-triangle and H&S evolution are structural observations only.
    expanding = build_expanding_triangle_geometry(candles, tuple(full_scan.swings), evaluated_index=last)
    if expanding is not None:
        lifecycle = classify_expanding_triangle_lifecycle(candles, expanding, evaluated_index=last)
        out.append(_obs(
            "EXPANDING_TRIANGLE_STRUCTURE", "Expanding Triangle Structure", "STRUCTURAL_CONTEXT", last,
            rule_ids=("BB-RNG-EXPANDING-TRIANGLE",),
            metadata=(
                ("swing_indices", ",".join(str(i) for i in expanding.swing_indices)),
                ("upper_slope", str(expanding.upper_boundary.slope_per_bar)),
                ("lower_slope", str(expanding.lower_boundary.slope_per_bar)),
                ("reference_width", str(expanding.reference_width)),
                ("current_width", str(expanding.current_width)),
                ("available_from_index", str(expanding.available_from_index)),
                ("lifecycle_state", lifecycle.state),
                ("first_break_index", "" if lifecycle.first_break_index is None else str(lifecycle.first_break_index)),
                ("first_break_direction", lifecycle.first_break_direction or ""),
                ("reentry_index", "" if lifecycle.reentry_index is None else str(lifecycle.reentry_index)),
                ("opposite_break_index", "" if lifecycle.opposite_break_index is None else str(lifecycle.opposite_break_index)),
                ("enlarged_structure", "true" if lifecycle.enlarged_structure else "false"),
                ("semantic", "LIFECYCLE_CONTEXT_NOT_TRADE_ELIGIBILITY"),
            ),
        ))

    for side, pattern_id, name, direction in (
        ("TOP", "HEAD_SHOULDERS_TOP", "Head and Shoulders Top", "SHORT"),
        ("BOTTOM", "HEAD_SHOULDERS_BOTTOM", "Head and Shoulders Bottom", "LONG"),
    ):
        hs = build_head_shoulders_lifecycle(candles, full_scan, side=side, evaluated_index=last)
        if hs is None:
            continue
        outcome = classify_head_shoulders_outcome(
            side=side, left_shoulder_index=hs.left_shoulder_index, head_index=hs.head_index,
            right_shoulder_index=hs.right_shoulder_index, neckline_state=hs.state,
        )
        role = "ALIAS_CONTEXT" if outcome is not None and outcome.state in {"ALIAS_RANGE_OR_FLAG_CONTEXT", "WITH_TREND_CONTINUATION_CONTEXT"} else "REVERSAL_STRUCTURE_CONTEXT"
        out.append(_obs(
            pattern_id, name, role, last, direction=direction,
            rule_ids=("BB-RNG-20-HEAD-SHOULDERS-AS-RANGE", "BB-REV-HEAD-SHOULDERS"),
            metadata=(
                ("left_shoulder_index", str(hs.left_shoulder_index)),
                ("head_index", str(hs.head_index)),
                ("right_shoulder_index", str(hs.right_shoulder_index)),
                ("neckline_projected", str(hs.neckline.projected_value)),
                ("neckline_state", hs.state),
                ("neckline_break", "true" if hs.neckline_break else "false"),
                ("neckline_reentry", "true" if hs.neckline_reentry else "false"),
                ("prior_trend_line_break", "true" if hs.prior_trend_line is not None and hs.prior_trend_line.break_evidence else "false"),
                ("hns_structure_id", "" if outcome is None else outcome.structure_id),
                ("outcome_state", "UNRESOLVED" if outcome is None else outcome.state),
                ("with_trend_direction", "" if outcome is None else outcome.with_trend_direction),
                ("reversal_direction", "" if outcome is None else outcome.reversal_direction),
                ("trade_eligible", "false"),
                ("semantic", "HNS_ALIAS_CONTINUATION_PRIMARY_REVERSAL_REQUIRES_FOLLOW_THROUGH"),
            ),
        ))

    if len(candles) >= 2:
        previous, final = candles[-2], candles[-1]
        if final.low > previous.high:
            out.append(_obs("PRICE_GAP_UP", "Price Gap Up", "BREAKOUT_CONTEXT", last,
                            direction="LONG", rule_ids=("BB-RNG-06-GAPS",),
                            metadata=(("gap_low", str(previous.high)), ("gap_high", str(final.low)))))
        elif final.high < previous.low:
            out.append(_obs("PRICE_GAP_DOWN", "Price Gap Down", "BREAKOUT_CONTEXT", last,
                            direction="SHORT", rule_ids=("BB-RNG-06-GAPS",),
                            metadata=(("gap_low", str(final.high)), ("gap_high", str(previous.low)))))

    if context.regime in {"BULL_TREND", "BEAR_TREND"} and len(candles) >= 20:
        ema = _ema20(candles)
        median_range = _median_range(candles[-20:])
        from app.modules.brooks_core.advanced_context import assess_advanced_context
        line_context = assess_advanced_context(snapshot, policy=policy)
        confluence = build_dueling_lines_confluence(
            candles, full_scan, direction=context.regime, evaluated_index=last,
            ema_value=ema[-1], tolerance=median_range,
            measured_move_value=line_context.measured_move_target,
        )
        if confluence is not None and confluence.confluent:
            direction = "LONG" if context.regime == "BULL_TREND" else "SHORT"
            out.append(_obs(
                "DUELING_LINES", "Dueling Lines Pullback", "STRUCTURAL_CONTEXT", last,
                direction=direction, rule_ids=("BB-RNG-19-DUELING-LINES",),
                metadata=(
                    ("pullback_line_role", confluence.pullback_line.role),
                    ("pullback_anchor_indices", ",".join(str(a.candle_index) for a in confluence.pullback_line.anchors)),
                    ("pullback_projected", str(confluence.pullback_line.projected_value)),
                    ("support_resistance_source", confluence.support_source),
                    ("support_resistance_value", str(confluence.support_value)),
                    ("separation", str(confluence.separation)),
                    ("engineering_tolerance", str(confluence.tolerance)),
                    ("semantic", "VISIBLE_CONFLUENCE_CONTEXT_NOT_ENTRY"),
                ),
            ))

    if context.regime in {"BULL_TREND", "BEAR_TREND"}:
        direction = "LONG" if context.regime == "BULL_TREND" else "SHORT"
        stairs = _stairs_structure(swings, direction=direction)
        if stairs is not None:
            primary, extensions, shrinking = stairs
            metadata = (
                ("swing_indices", ",".join(str(s.candle_index) for s in swings)),
                ("breakout_extensions", ",".join(str(x) for x in extensions)),
                ("breakout_tests_overlap_prior_points", "true"),
            )
            out.append(_obs("BROAD_CHANNEL_STAIRS", "Broad Channel / Stairs", "TREND_CONTEXT", last,
                            direction=direction, rule_ids=("BB-TRD-26-STAIRS-BROAD-CHANNEL",),
                            metadata=metadata))
            if shrinking:
                out.append(_obs("SHRINKING_STAIRS", "Shrinking Stairs", "WANING_MOMENTUM_CONTEXT", last,
                                direction=direction, rule_ids=("BB-TRD-26-SHRINKING-STAIRS",),
                                metadata=metadata + (("breakout_extensions_strictly_shrinking", "true"),)))

    if context.regime in {"BULL_TREND", "BEAR_TREND"}:
        from app.modules.brooks_core.advanced_context import classify_small_pullback_trend
        direction = "LONG" if context.regime == "BULL_TREND" else "SHORT"
        spt=classify_small_pullback_trend(candles,direction=direction,evaluated_index=last)
        if spt is not None and spt.state in {"ACTIVE_SMALL_PULLBACK_TREND","SMALL_PULLBACK_TREND_WITH_LATER_EXPANSION"}:
            out.append(_obs("SMALL_PULLBACK_TREND", "Small Pullback Trend", "TREND_CONTEXT", last,
                            direction=direction, rule_ids=("BB-TRD-23-SMALL-PULLBACK-TREND",),
                            metadata=(("episode_id",spt.episode_id),("pullback_episode_count",str(spt.pullback_episode_count)),
                                      ("max_pullback_run",str(spt.max_pullback_run)),("max_pullback_depth",str(spt.max_pullback_depth)),
                                      ("median_bar_range",str(spt.median_bar_range)),("later_expansion","true" if spt.later_expansion else "false"),
                                      ("state",spt.state),("trade_eligible","false"),("canonical_gap_id","BROOKS-GAP-025"),
                                      ("engineering_policy","DEPTH_DURATION_SPACING_CLASSIFICATION_NOT_BROOKS_HARD_GATE"))))

    for pattern_id, name, rule_id in (
        ("TREND_FROM_OPEN", "Trend From the Open", "BB-TRD-23-TREND-FROM-OPEN"),
        ("REVERSAL_DAY", "Reversal Day", "BB-TRD-24-REVERSAL-DAY"),
        ("TREND_RESUMPTION_DAY", "Trend Resumption Day", "BB-TRD-25-TREND-RESUMPTION-DAY"),
        ("OPENING_REVERSAL", "Opening Reversal", "BB-REV-19-OPENING-REVERSAL"),
        ("OPENING_SWING", "Opening Swing", "BB-REV-19-OPENING-REVERSAL"),
        ("GAP_OPENING", "Gap Opening", "BB-REV-20-GAP-OPENING"),
    ):
        out.append(_obs(pattern_id, name, "NOT_APPLICABLE_WITHOUT_SESSION_ANCHOR", last,
                        rule_ids=(rule_id,), metadata=(("reason", "24_7_crypto_snapshot_has_no_explicit_session_anchor"),)))
    return tuple(out)


def detect_triangle_breakout(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    candles = snapshot.candles
    if len(candles) < 12:
        return ()
    prior_snapshot = MarketSnapshot(
        exchange=snapshot.exchange, market_type=snapshot.market_type, symbol=snapshot.symbol,
        timeframe=snapshot.timeframe, candles=candles[:-1], captured_at=candles[-2].close_time,
        source="BROOKS_PHASE2_TRIANGLE_CONTEXT",
    )
    swings = _alternating_recent_swings(prior_snapshot, policy)
    if len(swings) < 5:
        return ()
    five = swings[-5:]
    indices = [s.candle_index for s in five]
    region = candles[min(indices):len(candles)-1]
    if not region:
        return ()
    if positive_price_overlap_rate(tuple(region)) < policy.context.range_min_body_overlap_rate:
        return ()
    triangle = build_triangle_geometry(tuple(candles[:-1]), tuple(swings), evaluated_index=len(candles) - 2)
    if triangle is None:
        return ()
    high = project_line_value(triangle.upper_boundary, len(candles) - 1)
    low = project_line_value(triangle.lower_boundary, len(candles) - 1)
    if low >= high:
        return ()
    final = candles[-1]
    out: list[BrooksPatternCandidate] = []

    if final.close > high and is_strong_bull_bar(final, policy.context):
        out.append(BrooksPatternCandidate(
            direction="LONG", setup_type="TRIANGLE_BREAKOUT_LONG", family="BREAKOUT",
            signal_index=len(candles) - 1,
            reasons=("five_leg_triangle_breakout_mode", "strong_close_above_triangle", "directional_breakout_trigger"),
            source_rule_ids=("BB-RNG-23-TRIANGLE", "BB-RNG-02-BREAKOUT-FOLLOWTHROUGH", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=17, context_required="BREAKOUT_OR_TREND",
            metadata=(("triangle_high", str(high)), ("triangle_low", str(low)), ("boundary_semantic", "PROJECTED_TRIANGLE_LINES")),
        ))
    if final.close < low and is_strong_bear_bar(final, policy.context):
        out.append(BrooksPatternCandidate(
            direction="SHORT", setup_type="TRIANGLE_BREAKOUT_SHORT", family="BREAKOUT",
            signal_index=len(candles) - 1,
            reasons=("five_leg_triangle_breakout_mode", "strong_close_below_triangle", "directional_breakout_trigger"),
            source_rule_ids=("BB-RNG-23-TRIANGLE", "BB-RNG-02-BREAKOUT-FOLLOWTHROUGH", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=17, context_required="BREAKOUT_OR_TREND",
            metadata=(("triangle_high", str(high)), ("triangle_low", str(low)), ("boundary_semantic", "PROJECTED_TRIANGLE_LINES")),
        ))
    return tuple(out)


def scan_wave05_foundation_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    """Expose WAVE_05 lifecycle identity as context only, never trade eligibility."""
    if context.regime not in {"BULL_TREND", "BEAR_TREND"}:
        return ()
    candles=snapshot.candles
    if len(candles) < 3:
        return ()
    start=max(0, len(candles)-policy.context.pullback_window_bars)
    last=len(candles)-1
    out=[]
    correction=classify_structural_correction(candles, trend_direction=context.regime, start_index=start)
    if correction is not None and correction.two_legged:
        out.append(_obs(
            "TWO_LEGGED_CORRECTION", "Structural Two-Legged Correction", "CORRECTION_CONTEXT", last,
            direction="LONG" if context.regime=="BULL_TREND" else "SHORT",
            rule_ids=("BB-TRD-ABC-CORRECTION", "BB-RNG-17-HL-BAR-COUNT"),
            metadata=(("origin_index",str(correction.origin_index)),
                      ("first_leg",f"{correction.first_leg.start_index}:{correction.first_leg.end_index}"),
                      ("reaction",f"{correction.reaction.start_index}:{correction.reaction.end_index}"),
                      ("second_leg",f"{correction.second_leg.start_index}:{correction.second_leg.end_index}"),
                      ("semantic","STRUCTURAL_CORRECTION_NOT_ENTRY_SIGNAL")),
        ))
    reversal=classify_generic_reversal_attempts(candles, trend_direction=context.regime, start_index=start)
    if reversal is not None and reversal.first_attempt_index is not None:
        out.append(_obs(
            "GENERIC_SECOND_REVERSAL_STATE", "Generic Reversal Attempt Lifecycle", "REVERSAL_CONTEXT", last,
            direction=reversal.reversal_direction,
            rule_ids=("BB-REV-SECOND-REVERSAL-STATE",),
            metadata=(("state",reversal.state),
                      ("first_attempt_index",str(reversal.first_attempt_index)),
                      ("resumption_index","" if reversal.resumption_index is None else str(reversal.resumption_index)),
                      ("second_attempt_index","" if reversal.second_attempt_index is None else str(reversal.second_attempt_index)),
                      ("semantic","FOUNDATIONAL_REVERSAL_STATE_NOT_WEDGE_H2_L2_OR_TRADE")),
        ))
    return tuple(out)


def _compact_origin_ending_at(candles: tuple[Candle, ...], end: int) -> CompactPatternOrigin | None:
    if end >= 2:
        a, b, c = candles[end-2:end+1]
        if _inside(b, a) and _inside(c, b):
            pattern = "II"
        elif _bodies_only_ii_at(candles, end):
            pattern = "BODIES_ONLY_II"
        else:
            pattern = None
        if pattern:
            block = candles[end-2:end+1]
            return CompactPatternOrigin(pattern, f"{pattern}:{end-2}:{end}", end-2, end, max(x.high for x in block), min(x.low for x in block))
    if end >= 3:
        a, b, c, d = candles[end-3:end+1]
        if _inside(b, a) and _outside(c, b) and _inside(d, c):
            block = candles[end-3:end+1]
            return CompactPatternOrigin("IOI", f"IOI:{end-3}:{end}", end-3, end, max(x.high for x in block), min(x.low for x in block))
    return None


def scan_breakout_lifecycle_observations(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """WAVE_10 034/036/037: typed breakout state; observation/context only."""
    candles = snapshot.candles
    last = len(candles) - 1
    if last < 3:
        return ()
    scan = confirm_swings_causally(candles, left_bars=policy.context.swing_left_bars, right_bars=policy.context.swing_right_bars)
    out = []
    search_start = max(1, last - 40)  # ENGINEERING_SEARCH_POLICY only.
    for direction, kind in (("LONG", "HIGH"), ("SHORT", "LOW")):
        chosen = None
        ref = None
        for i in range(search_start, last + 1):
            eligible = [x for x in scan.swings if x.kind == kind and x.confirmed_at_index < i]
            if not eligible:
                continue
            sw = eligible[-1]
            level = candles[sw.candle_index].high if kind == "HIGH" else candles[sw.candle_index].low
            bar = candles[i]
            extends = bar.high > level if direction == "LONG" else bar.low < level
            if not extends:
                continue
            strong = is_strong_bull_bar(bar, policy.context) if direction == "LONG" else is_strong_bear_bar(bar, policy.context)
            chosen = build_breakout_attempt_identity(candles, direction=direction, reference_id=f"SWING:{sw.candle_index}", reference_level=level, attempt_index=i, engineering_strong=strong)
            ref = sw
        if chosen is None or ref is None:
            continue
        life = classify_breakout_lifecycle(candles, chosen, evaluated_index=last)
        out.append(_obs(
            f"BREAKOUT_LIFECYCLE_{direction}", "Breakout Lifecycle", "BREAKOUT_CONTEXT", last, direction=direction,
            rule_ids=("BB-RNG-BREAKOUT-LIFECYCLE",),
            metadata=(("breakout_id", chosen.breakout_id), ("reference_level", str(chosen.reference_level)), ("state", life.state),
                      ("attempt_index", str(chosen.attempt_index)), ("follow_through_index", "" if life.follow_through_index is None else str(life.follow_through_index)),
                      ("test_index", "" if life.test_index is None else str(life.test_index)), ("reentry_index", "" if life.reentry_index is None else str(life.reentry_index)),
                      ("trade_eligible", "false"), ("search_policy", "ENGINEERING_SEARCH_POLICY_40_BARS")),
        ))
        if life.reentry_index is not None:
            ri = life.reentry_index
            rb = candles[ri]
            rev_dir = "SHORT" if direction == "LONG" else "LONG"
            rev_strong = is_strong_bear_bar(rb, policy.context) if rev_dir == "SHORT" else is_strong_bull_bar(rb, policy.context)
            fb = classify_failed_breakout_confirmation(candles, chosen, signal_index=ri, reversal_is_strong=rev_strong, evaluated_index=last)
            if fb is not None:
                out.append(_obs(
                    f"FAILED_BREAKOUT_CONTEXT_{direction}", "Failed Breakout Strength/Follow-through Context", "FAILURE_CONTEXT", last,
                    direction=fb.reversal_direction, rule_ids=("BB-RNG-05-FAILED-BREAKOUT",),
                    metadata=(("breakout_id", chosen.breakout_id), ("confirmation_state", fb.state), ("breakout_strength", fb.breakout_strength),
                              ("reversal_strength", fb.reversal_strength), ("trade_eligible", "false")),
                ))
        rc = candles[ref.candle_index]
        zone_low, zone_high = ((max(rc.open, rc.close), rc.high) if direction == "LONG" else (rc.low, min(rc.open, rc.close)))
        bt = classify_breakout_test(candles, chosen, zone_low=zone_low, zone_high=zone_high, evaluated_index=last)
        if bt is not None:
            structural = bt.structural_test
            out.append(_obs(
                f"BREAKOUT_TEST_{direction}", "Breakout Test", "BREAKOUT_CONTEXT", last, direction=direction,
                rule_ids=("BB-RNG-BREAKOUT-TEST",),
                metadata=(
                    ("structure_id", bt.structure_id),
                    ("test_id", bt.test_id),
                    ("kind", bt.kind),
                    ("test_index", str(bt.test_index)),
                    ("occurrence_state", bt.occurrence_state),
                    ("outcome_state", bt.outcome_state),
                    ("outcome_index", "" if bt.outcome_index is None else str(bt.outcome_index)),
                    ("reference_id", "" if structural is None else structural.reference_id),
                    ("reference_type", "" if structural is None else structural.reference_type),
                    ("zone_low", "" if structural is None else str(structural.zone_low)),
                    ("zone_high", "" if structural is None else str(structural.zone_high)),
                    (
                        "origin_episode_id",
                        ""
                        if structural is None or structural.origin_episode_id is None
                        else structural.origin_episode_id,
                    ),
                    ("trade_eligible", "false"),
                    ("canonical_chapter3_gap_id", "B1C03-014,B1C03-015"),
                ),
            ))
        if last >= 1:
            nb = classify_near_breakout_pullback(candles, direction=direction, reference_id=f"SWING:{ref.candle_index}", reference_level=chosen.reference_level,
                zone_low=zone_low, zone_high=zone_high, approach_index=last-1, evaluated_index=last)
            if nb is not None:
                out.append(_obs(
                    f"NEAR_BREAKOUT_PULLBACK_{direction}", "Near-breakout Functional Pullback", "BREAKOUT_CONTEXT", last, direction=direction,
                    rule_ids=("BB-RNG-BREAKOUT-TEST",), metadata=(("structure_id", nb.structure_id), ("kind", nb.kind), ("test_index", str(nb.test_index)), ("trade_eligible", "false")),
                ))
    return tuple(out)


def scan_compact_pattern_lifecycle_observations(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """BROOKS-GAP-042/043: preserve one compact-pattern origin through later outcome."""
    candles = snapshot.candles
    last = len(candles) - 1
    if last < 3:
        return ()
    origin = None
    for end in range(max(2, last - 30), last + 1):  # ENGINEERING_SEARCH_POLICY only.
        x = _compact_origin_ending_at(candles, end)
        if x is not None:
            origin = x
    if origin is None:
        return ()
    life = classify_compact_pattern_lifecycle(candles, origin, evaluated_index=last)
    return (_obs(
        "COMPACT_PATTERN_LIFECYCLE", f"{origin.pattern_id} Compact Pattern Lifecycle", "STRUCTURAL_CONTEXT", last,
        rule_ids=("BB-RNG-COMPACT-PATTERN-LIFECYCLE",),
        metadata=(("structure_id", origin.structure_id), ("pattern_id", origin.pattern_id), ("state", life.state),
                  ("breakout_direction", life.breakout_direction or ""), ("breakout_index", "" if life.breakout_index is None else str(life.breakout_index)),
                  ("reentry_index", "" if life.reentry_index is None else str(life.reentry_index)), ("opposite_break_index", "" if life.opposite_break_index is None else str(life.opposite_break_index)),
                  ("pullback_index", "" if life.pullback_index is None else str(life.pullback_index)), ("trade_eligible", "false")),
    ),)


def scan_extended_patterns(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
    market_context=None,
) -> ExtendedPatternScan:
    observations = list(scan_signal_bar_observations(snapshot, context, policy))
    observations.extend(scan_generic_breakout_attempt_observations(snapshot, context, policy))
    observations.extend(scan_breakout_lifecycle_observations(snapshot, context, policy))
    observations.extend(scan_compact_pattern_lifecycle_observations(snapshot, context, policy))
    observations.extend(scan_structure_observations(snapshot, context, policy))
    observations.extend(scan_ma_gap_observations(snapshot, context, policy))
    observations.extend(scan_additional_context_observations(snapshot, context, policy))
    observations.extend(scan_failed_hl_entry_observations(snapshot, context, policy))
    observations.extend(scan_wave05_foundation_observations(snapshot, context, policy))
    observations.extend(scan_extended_hl_recurrence_observations(snapshot, context, policy))
    observations.extend(scan_range_hl_context_observations(snapshot, context, policy, market_context))

    candidates: list[BrooksPatternCandidate] = []
    candidates.extend(detect_candle_pattern_breakouts(snapshot, context, policy))
    candidates.extend(detect_reversal_bar_failure(snapshot, context, policy))
    candidates.extend(detect_moving_average_pullback_setups(snapshot, context, policy))
    candidates.extend(detect_double_top_bottom_pullback(snapshot, context, policy))
    candidates.extend(detect_expanding_triangle(snapshot, context, policy))
    candidates.extend(detect_triangle_breakout(snapshot, context, policy))
    candidates.extend(detect_micro_wedge(snapshot, context, policy))

    unique_obs = {}
    for item in observations:
        key = (item.pattern_id, item.signal_index, item.direction, item.role)
        unique_obs.setdefault(key, item)
    unique_candidates = {}
    for item in candidates:
        key = (item.family, item.setup_type, item.direction, item.signal_index)
        unique_candidates.setdefault(key, item)
    return ExtendedPatternScan(tuple(unique_obs.values()), tuple(unique_candidates.values()))


def _extended_entry_count(candles: tuple[Candle, ...], *, direction: str, start: int) -> tuple[int, int | None]:
    """Compatibility wrapper over the canonical episode-owned recurrence model."""
    trend_direction = "BULL_TREND" if direction == "LONG" else "BEAR_TREND" if direction == "SHORT" else None
    if trend_direction is None:
        return 0, None
    recurrence = classify_hl_recurrence(candles, trend_direction=trend_direction, start_index=start)
    if recurrence is None or not recurrence.events:
        return 0, None
    return recurrence.highest_entry_number, recurrence.events[-1].index


def scan_extended_hl_recurrence_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    """Expose H3/H4/L3/L4 recurrence as context, never generic eligibility."""
    if context.regime not in {"BULL_TREND", "BEAR_TREND"}:
        return ()
    candles = snapshot.candles
    scan = confirm_swings_causally(candles, left_bars=policy.context.swing_left_bars, right_bars=policy.context.swing_right_bars)
    kind = "HIGH" if context.regime == "BULL_TREND" else "LOW"
    anchors = [s for s in scan.swings if s.kind == kind and s.candle_index < len(candles)-1]
    if not anchors:
        return ()
    start = max(anchors[-1].candle_index, len(candles)-policy.context.pullback_window_bars)
    recurrence = classify_hl_recurrence(candles, trend_direction=context.regime, start_index=start)
    if recurrence is None or not recurrence.events:
        return ()
    event = recurrence.events[-1]
    if event.index != len(candles)-1 or event.number not in {3,4}:
        return ()
    semantic = "WEDGE_VARIANT_CONTEXT_NOT_GENERIC_ENTRY" if event.number == 3 else "COMPLEX_CORRECTION_CONTEXT_NOT_GENERIC_ENTRY"
    return (_obs(
        f"{event.label}_RECURRENCE_CONTEXT", f"{event.label} Recurrence Context", "CORRECTION_RECURRENCE_CONTEXT", event.index,
        direction=recurrence.direction, rule_ids=("BB-RNG-17-HL-BAR-COUNT",),
        metadata=(("entry_number",str(event.number)),("episode_origin_index",str(recurrence.episode_origin_index)),
                  ("continuation_index",str(event.continuation_index)),("semantic",semantic),("trade_eligible","false")),
    ),)


def detect_extended_h4_l4(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy) -> tuple[BrooksPatternCandidate, ...]:
    """WAVE_06: H4/L4 count alone is never an autonomous trade candidate."""
    return ()


def scan_range_hl_context_observations(
    snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy, market_context=None
) -> tuple[BrooksPatternObservation, ...]:
    """Consume WAVE_02 hierarchy for range H/L location context without a fade entry."""
    evidence = getattr(context, "range_evidence", None)
    hierarchy = getattr(market_context, "range_hierarchy", None) if market_context is not None else None
    if context.regime != "TRADING_RANGE" or evidence is None or not evidence.composite_supported or hierarchy is None or not hierarchy.nested:
        return ()
    candles = snapshot.candles
    location = classify_range_hl_location(hierarchy, current_price=candles[-1].close, edge_zone_fraction=policy.range_extreme_zone_fraction)
    out: list[BrooksPatternObservation] = []
    scan = confirm_swings_causally(candles, left_bars=policy.context.swing_left_bars, right_bars=policy.context.swing_right_bars)
    for direction, trend_direction, kind in (("LONG","BULL_TREND","HIGH"),("SHORT","BEAR_TREND","LOW")):
        anchors=[s for s in scan.swings if s.kind==kind and s.candle_index < len(candles)-1]
        if not anchors:
            continue
        start=max(anchors[-1].candle_index, len(candles)-policy.context.pullback_window_bars)
        recurrence=classify_hl_recurrence(candles, trend_direction=trend_direction, start_index=start)
        if recurrence is None or not recurrence.events or recurrence.events[-1].index != len(candles)-1:
            continue
        event=recurrence.events[-1]
        out.append(_obs(
            f"RANGE_{event.label}_{direction}_CONTEXT", f"Range {event.label} {direction.title()} Context", "RANGE_LOCATION_CONTEXT", event.index,
            direction=direction, rule_ids=("BB-RNG-17-HL-BAR-COUNT",),
            metadata=(("entry_number",str(event.number)),("episode_origin_index",str(recurrence.episode_origin_index)),
                      ("local_price_relation",location.local_price_relation),("enclosing_relation",location.enclosing_relation),
                      ("location_semantic",location.semantic),("trade_eligible","false")),
        ))
    return tuple(out)


def scan_additional_context_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    candles = snapshot.candles
    last = len(candles) - 1
    out: list[BrooksPatternObservation] = []
    from app.modules.brooks_core.advanced_context import (
        classify_breakout_to_range_episode_link,
        classify_channel_opposing_flag_context,
        classify_channel_start_structural_test,
        classify_micro_channel_identity,
        classify_spike_channel_lifecycle,
        classify_trend_range_evolution,
    )
    micro=classify_micro_channel_identity(candles,policy,evaluated_index=last)
    if micro is not None:
        out.append(_obs(
            "BULL_MICRO_CHANNEL" if micro.direction=="LONG" else "BEAR_MICRO_CHANNEL",
            "Bull Micro Channel" if micro.direction=="LONG" else "Bear Micro Channel",
            "TREND_CONTEXT",last,direction=micro.direction,rule_ids=("BB-TRD-16-MICRO-CHANNEL",),
            metadata=(("channel_id",micro.channel_id),("bar_count",str(micro.bar_count)),
                      ("line_proximity_count",str(micro.line_proximity_count)),("small_bar_count",str(micro.small_bar_count)),
                      ("countertrend_bar_count",str(micro.countertrend_bar_count)),("engineering_tolerance",str(micro.engineering_tolerance)),
                      ("state",micro.state),("trade_eligible","false"),("canonical_gap_id","BROOKS-GAP-007"))
        ))

    structure = context.structure_direction

    strong=classify_strong_trend_evidence(candles,context,policy.context,evaluated_index=last)
    if strong.is_strong:
        out.append(_obs(
            "STRONG_TREND_EVIDENCE","Strong Trend Evidence Composite","TREND_CONTEXT",last,
            direction=strong.direction,rule_ids=("BB-TRD-19-TREND-STRENGTH",),
            metadata=(("trending_swings","true" if strong.trending_swings else "false"),
                      ("directional_bars","true" if strong.directional_bars else "false"),
                      ("little_body_overlap","true" if strong.little_body_overlap else "false"),
                      ("small_tail_fraction",str(strong.small_tail_fraction)),
                      ("urgency","true" if strong.urgency else "false"),
                      ("failed_countertrend_attempts",str(strong.failed_countertrend_attempts)),
                      ("limited_pullbacks","true" if strong.limited_pullbacks else "false"),
                      ("trade_eligible","false"),("canonical_gap_id","BROOKS-GAP-008"),("classification_policy",strong.classification_policy))
        ))

    spike_lifecycle=classify_spike_channel_lifecycle(snapshot,policy,evaluated_index=last)
    if spike_lifecycle is not None:
        out.append(_obs(
            "SPIKE_CHANNEL_LIFECYCLE","Spike to Channel Lifecycle","TREND_CONTEXT",last,
            direction=spike_lifecycle.direction,rule_ids=("BB-TRD-SPIKE-CHANNEL",),
            metadata=(("episode_id",spike_lifecycle.episode_id),("spike_start_index",str(spike_lifecycle.spike_start_index)),
                      ("spike_end_index",str(spike_lifecycle.spike_end_index)),
                      ("channel_start_index","" if spike_lifecycle.channel_start_index is None else str(spike_lifecycle.channel_start_index)),
                      ("state",spike_lifecycle.state),("trade_eligible","false"),("canonical_gap_id","BROOKS-GAP-009"))
        ))
        evo=classify_trend_range_evolution(
            candles,direction=spike_lifecycle.direction,
            origin_index=spike_lifecycle.spike_start_index,evaluated_index=last
        )
        if evo is not None:
            out.append(_obs(
                "TREND_RANGE_EVOLUTION","Trend to Range Evolution","TREND_CONTEXT",last,
                direction=evo.direction,rule_ids=("BB-TRD-22-TRENDING-RANGE",),
                metadata=(("episode_id",evo.episode_id),("state",evo.state),
                          ("overlap_rate",str(evo.overlap_rate)),("countertrend_fraction",str(evo.countertrend_fraction)),
                          ("trade_eligible","false"),("canonical_gap_id","BROOKS-GAP-010"))
            ))

        channel_test = classify_channel_start_structural_test(
            snapshot, policy, evaluated_index=last
        )
        if channel_test is not None:
            out.append(_obs(
                "CHANNEL_START_STRUCTURAL_TEST",
                "Channel Start Structural Test",
                "STRUCTURAL_CONTEXT",
                last,
                direction=channel_test.direction,
                rule_ids=("BB-TRD-SPIKE-CHANNEL",),
                metadata=(
                    ("test_id", channel_test.test_id),
                    ("reference_id", channel_test.reference_id),
                    ("reference_type", channel_test.reference_type),
                    (
                        "reference_level",
                        ""
                        if channel_test.reference_level is None
                        else str(channel_test.reference_level),
                    ),
                    ("zone_low", str(channel_test.zone_low)),
                    ("zone_high", str(channel_test.zone_high)),
                    ("test_index", str(channel_test.occurrence_index)),
                    ("occurrence_state", channel_test.occurrence_state),
                    ("outcome_state", channel_test.outcome_state),
                    ("origin_episode_id", channel_test.origin_episode_id or ""),
                    ("trade_eligible", "false"),
                    ("canonical_chapter3_gap_id", "B1C03-007,B1C03-014"),
                ),
            ))

        opposing_flag = classify_channel_opposing_flag_context(
            snapshot, policy, evaluated_index=last
        )
        if opposing_flag is not None:
            out.append(_obs(
                "CHANNEL_OPPOSING_FLAG_CONTEXT",
                "Channel Opposing Flag / Retracement Risk Context",
                "TREND_CONTEXT",
                last,
                direction=opposing_flag.direction,
                rule_ids=("BB-TRD-SPIKE-CHANNEL",),
                metadata=(
                    ("context_id", opposing_flag.context_id),
                    ("episode_id", opposing_flag.episode_id),
                    ("opposing_direction", opposing_flag.opposing_direction),
                    ("channel_start_index", str(opposing_flag.channel_start_index)),
                    ("established_at_index", str(opposing_flag.established_at_index)),
                    ("state", opposing_flag.state),
                    ("trade_eligible", "false"),
                    ("canonical_chapter3_gap_id", "B1C03-008"),
                ),
            ))

        range_evidence = getattr(context, "range_evidence", None)
        current_range_supported = bool(
            context.regime == "TRADING_RANGE"
            and range_evidence is not None
            and range_evidence.composite_supported
        )
        episode_link = classify_breakout_to_range_episode_link(
            snapshot,
            policy,
            current_range_supported=current_range_supported,
            evaluated_index=last,
        )
        if episode_link is not None:
            out.append(_obs(
                "BREAKOUT_RANGE_EPISODE_LINK",
                "Breakout / Spike to Later Range Episode Link",
                "TREND_RANGE_CONTEXT",
                last,
                direction=spike_lifecycle.direction,
                rule_ids=("BB-TRD-22-TRENDING-RANGE",),
                metadata=(
                    ("link_id", episode_link.link_id),
                    ("range_id", episode_link.range_id),
                    ("origin_breakout_id", episode_link.origin_breakout_id or ""),
                    ("origin_spike_episode_id", episode_link.origin_spike_episode_id),
                    ("parent_evolution_episode_id", episode_link.parent_evolution_episode_id),
                    ("symbol", episode_link.symbol),
                    ("timeframe", episode_link.timeframe),
                    ("range_origin_index", str(episode_link.range_origin_index)),
                    ("range_established_index", str(episode_link.range_established_index)),
                    ("state", episode_link.state),
                    ("trade_eligible", "false"),
                    ("canonical_chapter3_gap_id", "B1C03-018"),
                ),
            ))
    if structure in {"BULL_TREND", "BEAR_TREND"} and context.metrics.bar_overlap_rate >= policy.context.range_min_body_overlap_rate:
        out.append(_obs("TRENDING_TRADING_RANGE", "Trending Trading Range", "TREND_CONTEXT", last,
                        direction="LONG" if structure == "BULL_TREND" else "SHORT",
                        rule_ids=("BB-TRD-22-TRENDING-RANGE",),
                        metadata=(("bar_overlap_rate", str(context.metrics.bar_overlap_rate)),)))

    # Spike and generic channel are context, not standalone entries.
    recent3 = candles[-3:]
    bull_spike = sum(is_strong_bull_bar(c, policy.context) for c in recent3) >= 2
    bear_spike = sum(is_strong_bear_bar(c, policy.context) for c in recent3) >= 2
    if bull_spike or bear_spike:
        out.append(_obs(
            "BULL_SPIKE" if bull_spike else "BEAR_SPIKE",
            "Bull Spike" if bull_spike else "Bear Spike",
            "TREND_CONTEXT", last,
            direction="LONG" if bull_spike else "SHORT",
            rule_ids=("BB-TRD-SPIKE",),
        ))

    scan = confirm_swings_causally(
        candles, left_bars=policy.context.swing_left_bars, right_bars=policy.context.swing_right_bars
    )
    highs = [x for x in scan.swings if x.kind == "HIGH"]
    lows = [x for x in scan.swings if x.kind == "LOW"]
    if structure in {"BULL_TREND", "BEAR_TREND"}:
        trend_line = build_trend_line_geometry(candles, scan, direction=structure, evaluated_index=last)
        if trend_line is not None:
            out.append(_obs(
                trend_line.role, "Canonical Trend Line", "STRUCTURAL_CONTEXT", last,
                direction="LONG" if structure == "BULL_TREND" else "SHORT",
                rule_ids=("BB-TRD-TREND-LINE",),
                metadata=(
                    ("anchor_indices", ",".join(str(a.candle_index) for a in trend_line.anchors)),
                    ("anchor_confirmed_at", ",".join(str(a.confirmed_at_index) for a in trend_line.anchors)),
                    ("slope", str(trend_line.slope_per_bar)),
                    ("projected_value", str(trend_line.projected_value)),
                    ("relation", trend_line.current_relation),
                    ("break_evidence", "true" if trend_line.break_evidence else "false"),
                    ("crossed_this_bar", "true" if trend_line.crossed_this_bar else "false"),
                    ("semantic", "STRUCTURAL_EVIDENCE_NOT_REVERSAL_ENTRY"),
                ),
            ))
        channel = build_trend_channel_geometry(candles, scan, direction=structure, evaluated_index=last)
        if channel is not None:
            out.append(_obs(
                "CHANNEL", "Canonical Trend Channel", "TREND_CONTEXT", last,
                direction="LONG" if structure == "BULL_TREND" else "SHORT",
                rule_ids=("BB-TRD-CHANNEL",),
                metadata=(
                    ("trend_line_role", channel.trend_line.role),
                    ("channel_line_role", channel.opposite_channel_line.role),
                    ("trend_anchor_indices", ",".join(str(a.candle_index) for a in channel.trend_line.anchors)),
                    ("channel_anchor_index", str(channel.opposite_channel_line.anchors[0].candle_index)),
                    ("slope", str(channel.trend_line.slope_per_bar)),
                    ("projected_lower", str(channel.projected_lower)),
                    ("projected_upper", str(channel.projected_upper)),
                    ("containment_fraction", str(channel.containment_fraction)),
                    ("semantic", "CANONICAL_GEOMETRY_NOT_OVERSHOOT_LIFECYCLE"),
                ),
            ))
            channel_event = classify_channel_boundary_event(candles, channel, evaluated_index=last)
            if channel_event is not None and channel_event.state != "INSIDE_CHANNEL":
                out.append(_obs(
                    channel_event.state, "Trend-Channel-Line Structural Event", "STRUCTURAL_CONTEXT", last,
                    direction="LONG" if structure == "BULL_TREND" else "SHORT",
                    rule_ids=("BB-TRD-CHANNEL", "BB-REV-CHANNEL-OVERSHOOT"),
                    metadata=(
                        ("boundary_role", channel_event.boundary_role),
                        ("boundary_value", str(channel_event.boundary_value)),
                        ("channel_anchor_index", str(channel_event.channel_anchor_index)),
                        ("penetrated", "true" if channel_event.penetrated else "false"),
                        ("closed_beyond", "true" if channel_event.closed_beyond else "false"),
                        ("prior_penetration", "true" if channel_event.prior_penetration else "false"),
                        ("prior_close_beyond", "true" if channel_event.prior_close_beyond else "false"),
                        ("reentered", "true" if channel_event.reentered else "false"),
                        ("initial_break_semantic", "TREND_ACCELERATION_OR_GREATER_STRENGTH" if channel_event.state in {"CHANNEL_LINE_BREAK", "CHANNEL_LINE_OVERSHOOT"} else "NOT_APPLICABLE"),
                        ("failure_semantic", "EXHAUSTION_OR_REVERSAL_CONTEXT_NOT_ENTRY" if channel_event.state == "FAILED_BREAK_REENTRY" else "NOT_APPLICABLE"),
                        ("semantic", "CHANNEL_LINE_EVENT_NOT_TREND_LINE_BREAK_OR_ENTRY"),
                    ),
                ))

    minor=classify_minor_reversal_identity(candles,context,policy,evaluated_index=last)
    if minor is not None:
        out.append(_obs(
            "MINOR_REVERSAL_SHORT" if minor.direction=="SHORT" else "MINOR_REVERSAL_LONG",
            "Minor Trend Reversal","REVERSAL_CONTEXT",last,direction=minor.direction,
            rule_ids=("BB-REV-09-MINOR-REVERSAL",),
            metadata=(("reversal_id",minor.reversal_id),("major_trend_direction",minor.major_trend_direction),
                      ("origin_swing_index",str(minor.origin_swing_index)),("confirmed_at_index",str(minor.confirmed_at_index)),
                      ("state",minor.state),("trade_eligible","false"),("canonical_gap_id","BROOKS-GAP-062"))
        ))

    if len(candles)>=2 and (_bear_reversal(candles[-1]) or _bull_reversal(candles[-1])):
        prior_snapshot=MarketSnapshot(
            exchange=snapshot.exchange,market_type=snapshot.market_type,symbol=snapshot.symbol,timeframe=snapshot.timeframe,
            candles=tuple(candles[:-1]),captured_at=candles[-2].close_time,source="WAVE12_COUNTERTREND_PREFIX"
        )
        prior_context=assess_books_context(prior_snapshot,policy=policy.context)
        opp_direction="SHORT" if _bear_reversal(candles[-1]) else "LONG"
        opp=classify_countertrend_opportunity(
            direction=opp_direction,prior_always_in=prior_context.always_in,
            current_always_in=context.always_in,signal_index=last
        )
        if opp is not None:
            out.append(_obs(
                "COUNTERTREND_SCALP_CONTEXT" if opp.state=="COUNTERTREND_SCALP_OLD_TREND_INTACT" else "REVERSAL_TRADE_CONTEXT",
                "Countertrend Scalp vs Reversal Trade","REVERSAL_CONTEXT",last,direction=opp.direction,
                rule_ids=("BB-REV-15-ALWAYS-IN",),
                metadata=(("opportunity_id",opp.opportunity_id),("prior_always_in",opp.prior_always_in),
                          ("current_always_in",opp.current_always_in),("state",opp.state),("trade_eligible","false"),("canonical_gap_id","BROOKS-GAP-061"))
            ))

    if len(candles) >= 2:
        previous, final = candles[-2], candles[-1]
        bull_resume = structure == "BULL_TREND" and previous.close <= previous.open and is_strong_bull_bar(final, policy.context)
        bear_resume = structure == "BEAR_TREND" and previous.close >= previous.open and is_strong_bear_bar(final, policy.context)
        if bull_resume or bear_resume:
            out.append(_obs("TREND_RESUMPTION", "Trend Resumption", "ENTRY_CONTEXT", last,
                            direction="LONG" if bull_resume else "SHORT",
                            rule_ids=("BB-TRD-TREND-RESUMPTION",)))

    for side, pattern_id, name, direction in (
        ("TOP", "PARABOLIC_WEDGE_TOP", "Parabolic Wedge Top", "SHORT"),
        ("BOTTOM", "PARABOLIC_WEDGE_BOTTOM", "Parabolic Wedge Bottom", "LONG"),
    ):
        parabolic = build_parabolic_wedge_geometry(candles, scan, side=side, evaluated_index=last)
        if parabolic is None:
            continue
        reversal_signal = _bear_reversal(candles[-1]) if side == "TOP" else _bull_reversal(candles[-1])
        out.append(_obs(
            pattern_id, name, "REVERSAL_CONTEXT", last, direction=direction,
            rule_ids=("BB-REV-05-PARABOLIC-WEDGE",),
            metadata=(
                ("push_indices", ",".join(str(i) for i in parabolic.push_indices)),
                ("slope_1", str(parabolic.first_slope)),
                ("slope_2", str(parabolic.second_slope)),
                ("accelerating", "true"),
                ("canonical_channel_available", "true" if parabolic.channel is not None else "false"),
                ("channel_overshoot", "true" if parabolic.channel_overshoot else "false"),
                ("reversal_signal_present", "true" if reversal_signal else "false"),
                ("semantic", "PARABOLIC_STRUCTURE_CONTEXT_NOT_SECOND_SIGNAL_ENTRY"),
            ),
        ))

    from app.modules.brooks_core.advanced_context import assess_advanced_context
    advanced = assess_advanced_context(snapshot, policy=policy)
    target = advanced.measured_move_target
    typical = _median_range(tuple(candles[-20:]))
    if target is not None and typical > 0 and len(candles) >= 3:
        recent_mm = candles[-6:]
        if advanced.measured_move_direction == "LONG" and max(x.high for x in recent_mm) < target:
            near = target - max(x.high for x in recent_mm) <= typical
            if near and candles[-1].close < candles[-2].close:
                out.append(_obs("MEASURED_MOVE_FAILURE", "Measured Move Failure", "FAILURE_CONTEXT", last,
                                direction="SHORT", rule_ids=("BB-REV-09-MEASURED-MOVE-FAILURE", "BB-TRD-MEASURED-MOVE"),
                                metadata=(("target", str(target)),)))
        elif advanced.measured_move_direction == "SHORT" and min(x.low for x in recent_mm) > target:
            near = min(x.low for x in recent_mm) - target <= typical
            if near and candles[-1].close > candles[-2].close:
                out.append(_obs("MEASURED_MOVE_FAILURE", "Measured Move Failure", "FAILURE_CONTEXT", last,
                                direction="LONG", rule_ids=("BB-REV-09-MEASURED-MOVE-FAILURE", "BB-TRD-MEASURED-MOVE"),
                                metadata=(("target", str(target)),)))

    if snapshot.timeframe == "1d" and len(candles) >= 21:
        previous_volumes = [c.volume for c in candles[-21:-1]]
        final = candles[-1]
        huge_relative = previous_volumes and final.volume > max(previous_volumes)
        bull_reversal = structure == "BEAR_TREND" and _bull_reversal(final)
        bear_reversal = structure == "BULL_TREND" and _bear_reversal(final)
        if huge_relative and (bull_reversal or bear_reversal):
            out.append(_obs(
                "HUGE_VOLUME_DAILY_REVERSAL", "Huge-Volume Daily Reversal", "REVERSAL_CONTEXT", last,
                direction="LONG" if bull_reversal else "SHORT",
                rule_ids=("BB-REV-10-HUGE-VOLUME-DAILY",),
                metadata=(("volume_relation", "greater_than_prior_20_daily_bars"),),
            ))
    return tuple(out)


def detect_micro_wedge(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    candles = snapshot.candles
    if len(candles) < 5:
        return ()
    window = candles[-5:]
    final = candles[-1]
    high_pushes = sum(cur.high > prev.high for prev, cur in zip(window, window[1:]))
    low_pushes = sum(cur.low < prev.low for prev, cur in zip(window, window[1:]))
    out: list[BrooksPatternCandidate] = []
    if high_pushes >= 3 and _bear_reversal(final) and not (
        context.regime == "BULL_TREND" and context.always_in == "LONG"
    ):
        out.append(BrooksPatternCandidate(
            direction="SHORT", setup_type="MICRO_WEDGE_TOP_SHORT", family="WEDGE_REVERSAL",
            signal_index=len(candles) - 1,
            reasons=("three_micro_pushes_up_within_five_bars", "bear_reversal_after_third_push", "not_fading_resolved_always_in_bull"),
            source_rule_ids=("BB-REV-05-MICRO-WEDGE", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=29, context_required="TREND_EXTREME_OR_RANGE_EXTREME",
        ))
    if low_pushes >= 3 and _bull_reversal(final) and not (
        context.regime == "BEAR_TREND" and context.always_in == "SHORT"
    ):
        out.append(BrooksPatternCandidate(
            direction="LONG", setup_type="MICRO_WEDGE_BOTTOM_LONG", family="WEDGE_REVERSAL",
            signal_index=len(candles) - 1,
            reasons=("three_micro_pushes_down_within_five_bars", "bull_reversal_after_third_push", "not_fading_resolved_always_in_bear"),
            source_rule_ids=("BB-REV-05-MICRO-WEDGE", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=29, context_required="TREND_EXTREME_OR_RANGE_EXTREME",
        ))
    return tuple(out)


def scan_failed_hl_entry_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    """Expose the latest originating H/L attempt outcome without inventing an objective."""
    candles=snapshot.candles
    if len(candles)<8 or context.structure_direction not in {"BULL_TREND","BEAR_TREND"}:
        return ()
    scan=confirm_swings_causally(candles,left_bars=policy.context.swing_left_bars,right_bars=policy.context.swing_right_bars)
    kind="HIGH" if context.structure_direction=="BULL_TREND" else "LOW"
    anchors=[s for s in scan.swings if s.kind==kind and s.candle_index < len(candles)-1]
    if not anchors:
        return ()
    start=max(anchors[-1].candle_index,len(candles)-policy.context.pullback_window_bars)
    recurrence=classify_hl_recurrence(candles,trend_direction=context.structure_direction,start_index=start)
    if recurrence is None or not recurrence.events:
        return ()
    for event in reversed(recurrence.events):
        lifecycle=evaluate_hl_entry_attempt_lifecycle(candles,recurrence,event_number=event.number,objective_level=None)
        if lifecycle is None or lifecycle.failure_index != len(candles)-1:
            continue
        opposite="SHORT" if recurrence.direction=="LONG" else "LONG"
        definitive=lifecycle.state=="FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE"
        pattern_id=f"FAILED_{event.label}" if definitive else f"{event.label}_OUTCOME_CONTEXT"
        return (_obs(
            pattern_id, f"{event.label} Outcome Context", "FAILURE_CONTEXT", len(candles)-1, direction=opposite,
            rule_ids=("BB-REV-09-FAILURES","BB-RNG-17-HL-BAR-COUNT"),
            metadata=(("attempt_id",lifecycle.origin.attempt_id),("originating_entry",event.label),
                      ("episode_origin_index",str(recurrence.episode_origin_index)),("signal_index",str(event.index)),
                      ("trigger_index",str(lifecycle.trigger_index) if lifecycle.trigger_index is not None else "none"),
                      ("failure_index",str(lifecycle.failure_index)),("lifecycle_state",lifecycle.state),
                      ("objective_owned","false"),("failure_confirmed","true" if definitive else "false"),
                      ("trade_eligible","false")),
        ),)
    return ()

