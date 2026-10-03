"""WAVE_05 causal correction, reversal-attempt, and originating-failure foundations.

These objects preserve structural episode identity.  They are context evidence only:
no function in this module creates trade eligibility or implements deferred WAVE_06+
rules.  Numeric thresholds are intentionally absent; OHLC translations use directional
progress and explicit originating levels supplied by the owning detector.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.modules.brooks_core.context_classifier import (
    is_bear_reversal_bar_minimum,
    is_bull_reversal_bar_minimum,
)
from app.modules.brooks_core.structural_geometry import (
    StructuralTestIdentity,
    classify_structural_test,
)
from app.modules.market_data.entities import Candle

TrendDirection = Literal["BULL_TREND", "BEAR_TREND"]
StepKind = Literal["COUNTERTREND", "WITH_TREND", "NEUTRAL"]


@dataclass(frozen=True, slots=True)
class CorrectionLeg:
    role: Literal["FIRST_COUNTERTREND_LEG", "WITH_TREND_REACTION", "SECOND_COUNTERTREND_LEG"]
    direction: Literal["UP", "DOWN"]
    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class CorrectionEpisode:
    trend_direction: TrendDirection
    origin_index: int
    first_leg: CorrectionLeg | None
    reaction: CorrectionLeg | None
    second_leg: CorrectionLeg | None
    reset_index: int | None
    state: str

    @property
    def two_legged(self) -> bool:
        return self.second_leg is not None


@dataclass(frozen=True, slots=True)
class GenericReversalAttemptLifecycle:
    trend_direction: TrendDirection
    reversal_direction: Literal["LONG", "SHORT"]
    first_attempt_index: int | None
    resumption_index: int | None
    second_attempt_index: int | None
    state: str


@dataclass(frozen=True, slots=True)
class ReversalPatternOrigin:
    attempt_id: str
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    signal_index: int
    trigger_level: Decimal
    objective_level: Decimal | None
    failure_level: Decimal


@dataclass(frozen=True, slots=True)
class ReversalPatternLifecycle:
    origin: ReversalPatternOrigin
    state: str
    trigger_index: int | None
    objective_index: int | None
    failure_index: int | None
    trapped_side: Literal["LONG", "SHORT"] | None


@dataclass(frozen=True, slots=True)
class BreakoutAttemptIdentity:
    breakout_id: str
    direction: Literal["LONG", "SHORT"]
    reference_id: str
    reference_level: Decimal
    attempt_index: int
    closed_beyond: bool
    engineering_strong: bool


@dataclass(frozen=True, slots=True)
class BreakoutLifecycle:
    origin: BreakoutAttemptIdentity
    state: str
    evaluated_index: int
    follow_through_index: int | None = None
    test_index: int | None = None
    reentry_index: int | None = None


@dataclass(frozen=True, slots=True)
class FailedBreakoutConfirmation:
    origin: BreakoutAttemptIdentity
    reversal_direction: Literal["LONG", "SHORT"]
    signal_index: int
    state: str
    breakout_strength: str
    reversal_strength: str
    next_bar_index: int | None = None


@dataclass(frozen=True, slots=True)
class FailureOfFailureLifecycle:
    breakout_origin: BreakoutAttemptIdentity
    first_failure: FailedBreakoutConfirmation
    reversal_origin: ReversalPatternOrigin | None
    reversal_lifecycle: ReversalPatternLifecycle | None
    state: str
    later_failure_index: int | None


@dataclass(frozen=True, slots=True)
class GenericFailureOfFailureLifecycle:
    original_setup_id: str
    original_direction: Literal["LONG", "SHORT"]
    first_failure_origin: ReversalPatternOrigin
    first_failure_lifecycle: ReversalPatternLifecycle
    state: str
    evaluated_index: int
    later_failure_index: int | None


@dataclass(frozen=True, slots=True)
class BreakoutTestIdentity:
    structure_id: str
    direction: Literal["LONG", "SHORT"]
    kind: str
    reference_level: Decimal
    test_index: int
    pull_away_index: int | None
    state: str
    structural_test: StructuralTestIdentity | None = None
    outcome_state: str = "PENDING"
    outcome_index: int | None = None
    trade_eligible: bool = False

    @property
    def test_id(self) -> str:
        return (
            self.structural_test.test_id
            if self.structural_test is not None
            else self.structure_id
        )

    @property
    def occurrence_state(self) -> str:
        return (
            self.structural_test.occurrence_state
            if self.structural_test is not None
            else "TEST_OCCURRED"
        )


@dataclass(frozen=True, slots=True)
class CompactPatternOrigin:
    pattern_id: str
    structure_id: str
    start_index: int
    end_index: int
    high: Decimal
    low: Decimal


@dataclass(frozen=True, slots=True)
class CompactPatternLifecycle:
    origin: CompactPatternOrigin
    state: str
    evaluated_index: int
    breakout_direction: Literal["LONG", "SHORT"] | None = None
    breakout_index: int | None = None
    reentry_index: int | None = None
    opposite_break_index: int | None = None
    pullback_index: int | None = None


def build_breakout_attempt_identity(
    candles: tuple[Candle, ...], *, direction: Literal["LONG", "SHORT"], reference_id: str,
    reference_level: Decimal, attempt_index: int, engineering_strong: bool = False,
) -> BreakoutAttemptIdentity | None:
    if direction not in {"LONG", "SHORT"} or not (0 <= attempt_index < len(candles)):
        return None
    bar = candles[attempt_index]
    extended = bar.high > reference_level if direction == "LONG" else bar.low < reference_level
    if not extended:
        return None
    closed = bar.close > reference_level if direction == "LONG" else bar.close < reference_level
    return BreakoutAttemptIdentity(
        f"BREAKOUT:{direction}:{reference_id}:{attempt_index}", direction, reference_id,
        reference_level, attempt_index, closed, engineering_strong,
    )


def classify_breakout_lifecycle(
    candles: tuple[Candle, ...],
        origin: BreakoutAttemptIdentity,
        *,
        evaluated_index: int | None = None,
) -> BreakoutLifecycle:
    end = len(candles)-1 if evaluated_index is None else min(evaluated_index, len(candles)-1)
    if end < origin.attempt_index:
        return BreakoutLifecycle(origin, "ORIGIN_NOT_YET_AVAILABLE", end)
    follow = test = reentry = None
    for i in range(origin.attempt_index + 1, end + 1):
        c = candles[i]
        beyond_close = c.close > origin.reference_level if origin.direction == "LONG" else c.close < origin.reference_level
        back_inside = c.close <= origin.reference_level if origin.direction == "LONG" else c.close >= origin.reference_level
        touches = c.low <= origin.reference_level if origin.direction == "LONG" else c.high >= origin.reference_level
        if origin.closed_beyond and test is None and touches and beyond_close:
            test = i
        if follow is None and beyond_close:
            prev = candles[i-1]
            progressing = (
                c.close > prev.close
                if origin.direction == "LONG"
                else c.close < prev.close
            )
            if progressing:
                follow = i
        if back_inside:
            reentry = i
            break
    if reentry is not None:
        state = (
            "FAILED_FOLLOW_THROUGH_REENTRY"
            if origin.closed_beyond
            else "ATTEMPT_REJECTED_REENTRY"
        )
    elif test is not None:
        state = "BREAKOUT_TEST_HOLDING"
    elif follow is not None:
        state = "FOLLOW_THROUGH_CONFIRMED"
    else:
        state = "BREAKOUT_ESTABLISHED" if origin.closed_beyond else "BREAKOUT_ATTEMPT_ONLY"
    return BreakoutLifecycle(origin, state, end, follow, test, reentry)


def classify_failed_breakout_confirmation(
    candles: tuple[Candle, ...], origin: BreakoutAttemptIdentity, *, signal_index: int,
    reversal_is_strong: bool, evaluated_index: int | None = None,
) -> FailedBreakoutConfirmation | None:
    end = len(candles)-1 if evaluated_index is None else min(evaluated_index, len(candles)-1)
    if not (origin.attempt_index < signal_index <= end):
        return None
    life = classify_breakout_lifecycle(candles, origin, evaluated_index=signal_index)
    if life.reentry_index != signal_index:
        return None
    rev_dir: Literal["LONG", "SHORT"] = "SHORT" if origin.direction == "LONG" else "LONG"
    reversal = is_bear_reversal_bar_minimum if rev_dir == "SHORT" else is_bull_reversal_bar_minimum
    if not reversal(candles[signal_index]):
        return FailedBreakoutConfirmation(origin,
            rev_dir,
            signal_index,
            "RETURN_INSIDE_NO_REVERSAL_SETUP",
            "STRONG" if origin.engineering_strong else "WEAK_OR_NEUTRAL",
            "STRONG" if reversal_is_strong else "WEAK_OR_NEUTRAL")
    if reversal_is_strong and not origin.engineering_strong:
        return FailedBreakoutConfirmation(origin,
            rev_dir,
            signal_index,
            "CONFIRMED_STRONG_REVERSAL_WEAK_BREAKOUT",
            "WEAK_OR_NEUTRAL", "STRONG")
    if end > signal_index:
        nxt = candles[signal_index+1]
        sig = candles[signal_index]
        follows = nxt.close < sig.close and nxt.low < sig.low if rev_dir == "SHORT" else nxt.close > sig.close and nxt.high > sig.high
        if follows:
            return FailedBreakoutConfirmation(origin, rev_dir, signal_index, "CONFIRMED_BY_NEXT_BAR_FOLLOW_THROUGH",
                "STRONG" if origin.engineering_strong else "WEAK_OR_NEUTRAL",
                "STRONG" if reversal_is_strong else "WEAK_OR_NEUTRAL", signal_index+1)
        return FailedBreakoutConfirmation(origin,
            rev_dir,
            signal_index,
            "NOT_CONFIRMED_BY_NEXT_BAR",
            "STRONG" if origin.engineering_strong else "WEAK_OR_NEUTRAL",
            "STRONG" if reversal_is_strong else "WEAK_OR_NEUTRAL", signal_index+1)
    return FailedBreakoutConfirmation(origin, rev_dir, signal_index, "AWAITING_NEXT_BAR_COMPARISON",
        "STRONG" if origin.engineering_strong else "WEAK_OR_NEUTRAL",
        "STRONG" if reversal_is_strong else "WEAK_OR_NEUTRAL")


def classify_generic_failure_of_failure(
    candles: tuple[Candle, ...],
        *,
        original_setup_id: str,
        original_direction: Literal["LONG", "SHORT"],
    first_failure_origin: ReversalPatternOrigin, evaluated_index: int | None = None,
) -> GenericFailureOfFailureLifecycle:
    """BROOKS-GAP-035 generic adapter over the single WAVE_05 failure truth.

    Callers must explicitly supply the originating setup identity; this function never
    discovers an anonymous local reversal and never treats invalidation as failure.
    """
    end = len(candles)-1 if evaluated_index is None else min(evaluated_index, len(candles)-1)
    life = evaluate_reversal_pattern_lifecycle(candles, first_failure_origin, evaluated_index=end)
    if life.state == "FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE":
        state, later = "FAILURE_OF_FAILURE_CONFIRMED", life.failure_index
    elif life.state == "SIGNAL_INVALIDATED_BEFORE_TRIGGER":
        state, later = "UNTRIGGERED_INVALIDATION_NOT_FIRST_FAILURE", None
    elif life.state.startswith("AMBIGUOUS_"):
        state, later = "AMBIGUOUS_ORDER_FAIL_CLOSED", None
    elif life.state == "TRIGGERED_ACTIVE":
        state, later = "FIRST_FAILURE_ATTEMPT_TRIGGERED", None
    else:
        state, later = "FIRST_FAILURE_WAITING_FOR_TRIGGER", None
    return GenericFailureOfFailureLifecycle(original_setup_id,
        original_direction,
        first_failure_origin,
        life,
        state,
        end,
        later)


def classify_failure_of_failure(
    candles: tuple[Candle, ...], first_failure: FailedBreakoutConfirmation, *, evaluated_index: int | None = None,
) -> FailureOfFailureLifecycle:
    confirmed = first_failure.state in {"CONFIRMED_STRONG_REVERSAL_WEAK_BREAKOUT", "CONFIRMED_BY_NEXT_BAR_FOLLOW_THROUGH"}
    if not confirmed:
        return FailureOfFailureLifecycle(first_failure.origin, first_failure, None, None, "NO_GENUINE_FIRST_FAILURE", None)
    signal = candles[first_failure.signal_index]
    direction = first_failure.reversal_direction
    rev_origin = ReversalPatternOrigin(
        attempt_id=f"{first_failure.origin.breakout_id}:FIRST_FAILURE:{first_failure.signal_index}",
        pattern_id="FAILED_BREAKOUT_REVERSAL",
            direction=direction,
            signal_index=first_failure.signal_index,
        trigger_level=signal.low if direction=="SHORT" else signal.high, objective_level=None,
        failure_level=signal.high if direction=="SHORT" else signal.low,
    )
    generic = classify_generic_failure_of_failure(
        candles,
            original_setup_id=first_failure.origin.breakout_id,
            original_direction=first_failure.origin.direction,
        first_failure_origin=rev_origin, evaluated_index=evaluated_index,
    )
    return FailureOfFailureLifecycle(
        first_failure.origin,
        first_failure,
        rev_origin,
        generic.first_failure_lifecycle,
        generic.state,
        generic.later_failure_index
    )


def classify_breakout_test(
    candles: tuple[Candle, ...],
    origin: BreakoutAttemptIdentity,
    *,
    zone_low: Decimal,
    zone_high: Decimal,
    evaluated_index: int | None = None,
) -> BreakoutTestIdentity | None:
    """Classify test occurrence first; only later bars may resolve hold/failure outcome."""

    end = len(candles)-1 if evaluated_index is None else min(evaluated_index, len(candles)-1)
    if end <= origin.attempt_index or zone_low > zone_high:
        return None
    occurrence = classify_structural_test(
        candles,
        reference_id=origin.reference_id,
        reference_type="BREAKOUT_REFERENCE",
        zone_low=zone_low,
        zone_high=zone_high,
        search_start_index=origin.attempt_index + 1,
        direction=origin.direction,
        reference_level=origin.reference_level,
        origin_episode_id=origin.breakout_id,
        evaluated_index=end,
    )
    if occurrence is None:
        return None

    state = "TEST_OCCURRED"
    outcome_state = "PENDING"
    outcome_index = None
    for i in range(occurrence.occurrence_index + 1, end + 1):
        candle = candles[i]
        back_inside = (
            candle.close <= origin.reference_level
            if origin.direction == "LONG"
            else candle.close >= origin.reference_level
        )
        if back_inside:
            state = "TEST_FAILS_BREAKOUT_SIDE"
            outcome_state = "FAILS_BREAKOUT_SIDE"
            outcome_index = i
            break
        holds = (
            candle.close > origin.reference_level
            if origin.direction == "LONG"
            else candle.close < origin.reference_level
        )
        if holds:
            state = "TEST_HOLDS_BREAKOUT_SIDE"
            outcome_state = "HOLDS_BREAKOUT_SIDE"
            outcome_index = i
            break

    occurrence = StructuralTestIdentity(
        test_id=occurrence.test_id,
        reference_id=occurrence.reference_id,
        reference_type=occurrence.reference_type,
        direction=occurrence.direction,
        reference_level=occurrence.reference_level,
        zone_low=occurrence.zone_low,
        zone_high=occurrence.zone_high,
        origin_episode_id=occurrence.origin_episode_id,
        occurrence_index=occurrence.occurrence_index,
        evaluated_index=end,
        occurrence_state=occurrence.occurrence_state,
        outcome_state=outcome_state,
        trade_eligible=False,
    )
    return BreakoutTestIdentity(
        origin.breakout_id,
        origin.direction,
        "ACTUAL_BREAKOUT_TEST",
        origin.reference_level,
        occurrence.occurrence_index,
        None,
        state,
        occurrence,
        outcome_state,
        outcome_index,
        False,
    )


def classify_near_breakout_pullback(
    candles: tuple[Candle, ...],
    *,
    direction: Literal["LONG", "SHORT"],
    reference_id: str,
    reference_level: Decimal,
    zone_low: Decimal, zone_high: Decimal, approach_index: int, evaluated_index: int | None = None,
) -> BreakoutTestIdentity | None:
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    if not (0 <= approach_index < end) or zone_low > zone_high:
        return None
    a=candles[approach_index]
    actual = a.high > reference_level if direction=="LONG" else a.low < reference_level
    intersects = a.high >= zone_low and a.low <= zone_high
    if actual or not intersects:
        return None
    n=candles[approach_index+1]
    pulls = n.close < a.close if direction=="LONG" else n.close > a.close
    if not pulls:
        return None
    return BreakoutTestIdentity(
        f"NEAR_BREAKOUT:{direction}:{reference_id}:{approach_index}",
        direction,
        "NEAR_BREAKOUT_FUNCTIONAL_PULLBACK",
        reference_level,
        approach_index,
        approach_index + 1,
        "APPROACH_THEN_PULLBACK",
        None,
        "FUNCTIONAL_PULLBACK_CONFIRMED",
        approach_index + 1,
        False,
    )


def classify_compact_pattern_lifecycle(
    candles: tuple[Candle, ...],
    origin: CompactPatternOrigin,
    *,
    evaluated_index: int | None = None,
) -> CompactPatternLifecycle:
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    if end <= origin.end_index:
        return CompactPatternLifecycle(origin, "PATTERN_READY", end)
    breakout_dir=None; breakout_i=reentry=opp=pullback=None
    for i in range(origin.end_index+1,end+1):
        c=candles[i]
        if breakout_i is None:
            if c.close > origin.high:
                breakout_dir="LONG"; breakout_i=i; continue
            if c.close < origin.low:
                breakout_dir="SHORT"; breakout_i=i; continue
            if c.high > origin.high:
                breakout_dir="LONG"; breakout_i=i; continue
            if c.low < origin.low:
                breakout_dir="SHORT"; breakout_i=i; continue
            continue
        if reentry is None:
            inside = origin.low <= c.close <= origin.high
            if inside:
                reentry=i; continue
            touches = c.low <= origin.high if breakout_dir=="LONG" else c.high >= origin.low
            holds = c.close > origin.high if breakout_dir=="LONG" else c.close < origin.low
            if pullback is None and touches and holds:
                pullback=i
            continue
        if breakout_dir=="LONG" and c.close < origin.low:
            opp=i; break
        if breakout_dir=="SHORT" and c.close > origin.high:
            opp=i; break
    if opp is not None: state="OPPOSITE_BREAKOUT_AFTER_FAILURE"
    elif reentry is not None: state="FAILED_BREAKOUT_RETURNED_TO_SAME_PATTERN"
    elif pullback is not None: state="BREAKOUT_PULLBACK_SAME_PATTERN"
    elif breakout_i is not None: state="BREAKOUT_ATTEMPT_ACTIVE"
    else: state="PATTERN_READY"
    return CompactPatternLifecycle(origin,state,end,breakout_dir,breakout_i,reentry,opp,pullback)


def correction_step(
    previous: Candle,
    current: Candle,
    *,
    trend_direction: TrendDirection,
) -> StepKind:
    """Classify one closed-bar directional step without a fixed magnitude threshold."""
    if current.close != previous.close:
        with_trend = (
            current.close > previous.close
            if trend_direction == "BULL_TREND"
            else current.close < previous.close
        )
        return "WITH_TREND" if with_trend else "COUNTERTREND"
    if trend_direction == "BULL_TREND":
        if current.low < previous.low and current.high <= previous.high:
            return "COUNTERTREND"
        if current.high > previous.high and current.low >= previous.low:
            return "WITH_TREND"
    else:
        if current.high > previous.high and current.low >= previous.low:
            return "COUNTERTREND"
        if current.low < previous.low and current.high <= previous.high:
            return "WITH_TREND"
    return "NEUTRAL"


def correction_reset_by_resumption(
    candles: tuple[Candle, ...],
    *,
    trend_direction: TrendDirection,
    origin_index: int,
    evaluated_index: int
) -> bool:
    """Use the pre-existing Core interpretation of full resumption beyond correction origin."""
    origin = candles[origin_index]
    current = candles[evaluated_index]
    return (
        current.high > origin.high
        if trend_direction == "BULL_TREND"
        else current.low < origin.low
    )


def classify_structural_correction(
    candles: tuple[Candle, ...],
    *,
    trend_direction: TrendDirection,
    start_index: int,
    evaluated_index: int | None = None
) -> CorrectionEpisode | None:
    if trend_direction not in {"BULL_TREND", "BEAR_TREND"} or not candles:
        return None
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if start_index < 0 or end <= start_index or end >= len(candles):
        return None
    first_start = first_end = reaction_start = reaction_end = second_start = second_end = None
    for i in range(start_index + 1, end + 1):
        step = correction_step(candles[i - 1], candles[i], trend_direction=trend_direction)
        if first_start is None:
            if step == "COUNTERTREND":
                first_start = first_end = i
            continue
        if reaction_start is None:
            if step == "COUNTERTREND":
                first_end = i
                continue
            if step == "WITH_TREND":
                reaction_start = reaction_end = i
                if correction_reset_by_resumption(candles, trend_direction=trend_direction, origin_index=start_index, evaluated_index=i):
                    return CorrectionEpisode(trend_direction, start_index,
                        CorrectionLeg("FIRST_COUNTERTREND_LEG", "DOWN" if trend_direction=="BULL_TREND" else "UP", first_start, first_end),
                        CorrectionLeg("WITH_TREND_REACTION", "UP" if trend_direction=="BULL_TREND" else "DOWN", reaction_start, reaction_end),
                        None, i, "RESET_AFTER_TREND_RESUMPTION")
            continue
        if second_start is None:
            if step == "WITH_TREND":
                reaction_end = i
                if correction_reset_by_resumption(candles, trend_direction=trend_direction, origin_index=start_index, evaluated_index=i):
                    return CorrectionEpisode(trend_direction, start_index,
                        CorrectionLeg("FIRST_COUNTERTREND_LEG", "DOWN" if trend_direction=="BULL_TREND" else "UP", first_start, first_end),
                        CorrectionLeg("WITH_TREND_REACTION", "UP" if trend_direction=="BULL_TREND" else "DOWN", reaction_start, reaction_end),
                        None, i, "RESET_AFTER_TREND_RESUMPTION")
                continue
            if step == "COUNTERTREND":
                second_start = second_end = i
            continue
        if step == "COUNTERTREND":
            second_end = i
    first = None if first_start is None else CorrectionLeg("FIRST_COUNTERTREND_LEG", "DOWN" if trend_direction=="BULL_TREND" else "UP", first_start, first_end)
    reaction = None if reaction_start is None else CorrectionLeg("WITH_TREND_REACTION", "UP" if trend_direction=="BULL_TREND" else "DOWN", reaction_start, reaction_end)
    second = None if second_start is None else CorrectionLeg("SECOND_COUNTERTREND_LEG", "DOWN" if trend_direction=="BULL_TREND" else "UP", second_start, second_end)
    state = "SECOND_LEG_ESTABLISHED" if second else "REACTION_IN_PROGRESS" if reaction else "FIRST_LEG_IN_PROGRESS" if first else "NO_CORRECTION"
    return CorrectionEpisode(trend_direction, start_index, first, reaction, second, None, state)


def classify_generic_reversal_attempts(
    candles: tuple[Candle, ...],
    *,
    trend_direction: TrendDirection,
    start_index: int = 0,
    evaluated_index: int | None = None
) -> GenericReversalAttemptLifecycle | None:
    if not candles or trend_direction not in {"BULL_TREND", "BEAR_TREND"}:
        return None
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if start_index < 0 or end < start_index or end >= len(candles):
        return None
    reversal = (
        is_bear_reversal_bar_minimum
        if trend_direction == "BULL_TREND"
        else is_bull_reversal_bar_minimum
    )
    direction = "SHORT" if trend_direction == "BULL_TREND" else "LONG"
    first = resume = second = None
    for i in range(start_index, end + 1):
        if first is None:
            if reversal(candles[i]): first = i
            continue
        if resume is None:
            first_bar = candles[first]
            cur = candles[i]
            failed = cur.high > first_bar.high if trend_direction == "BULL_TREND" else cur.low < first_bar.low
            if failed: resume = i
            continue
        if i > resume and reversal(candles[i]):
            second = i
            break
    state = (
        "SECOND_REVERSAL_ATTEMPT"
        if second is not None
        else "FIRST_ATTEMPT_FAILED_RESUMPTION"
        if resume is not None
        else "FIRST_REVERSAL_ATTEMPT"
        if first is not None
        else "NO_REVERSAL_ATTEMPT"
    )
    return GenericReversalAttemptLifecycle(trend_direction, direction, first, resume, second, state)


def evaluate_reversal_pattern_lifecycle(
    candles: tuple[Candle, ...],
    origin: ReversalPatternOrigin,
    *,
    evaluated_index: int | None = None
) -> ReversalPatternLifecycle:
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if origin.signal_index < 0 or origin.signal_index > end or end >= len(candles):
        return ReversalPatternLifecycle(origin, "ORIGIN_NOT_YET_AVAILABLE", None, None, None, None)
    trigger = objective = failure = None
    for i in range(origin.signal_index + 1, end + 1):
        c = candles[i]
        trigger_hit = c.high > origin.trigger_level if origin.direction == "LONG" else c.low < origin.trigger_level
        failure_hit = c.low < origin.failure_level if origin.direction == "LONG" else c.high > origin.failure_level
        objective_hit = False
        if origin.objective_level is not None:
            objective_hit = (
                c.high >= origin.objective_level
                if origin.direction == "LONG"
                else c.low <= origin.objective_level
            )
        if trigger is None:
            if failure_hit and not trigger_hit:
                return ReversalPatternLifecycle(origin, "SIGNAL_INVALIDATED_BEFORE_TRIGGER", None, None, i, None)
            if trigger_hit and failure_hit:
                return ReversalPatternLifecycle(origin, "AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR", i, None, i, None)
            if trigger_hit:
                trigger = i
                if objective_hit:
                    objective = i
                    return ReversalPatternLifecycle(
                        origin,
                        "OBJECTIVE_REACHED",
                        trigger,
                        objective,
                        None,
                        None,
                    )
                continue
        else:
            if objective_hit and failure_hit:
                return ReversalPatternLifecycle(
                    origin,
                    "AMBIGUOUS_OBJECTIVE_AND_FAILURE_SAME_BAR",
                    trigger,
                    i,
                    i,
                    None,
                )
            if objective_hit:
                return ReversalPatternLifecycle(origin, "OBJECTIVE_REACHED", trigger, i, None, None)
            if failure_hit:
                trapped = origin.direction
                return ReversalPatternLifecycle(origin, "FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE", trigger, None, i, trapped)
    return ReversalPatternLifecycle(origin, "TRIGGERED_ACTIVE" if trigger is not None else "WAITING_FOR_TRIGGER", trigger, objective, failure, None)

@dataclass(frozen=True, slots=True)
class HLEntryEvent:
    """One H/L recurrence event inside a single causal correction episode."""
    index: int
    number: int
    label: str
    continuation_index: int


@dataclass(frozen=True, slots=True)
class HLCorrectionRecurrence:
    """Episode-owned H1-H4/L1-L4 recurrence state (WAVE_06)."""
    trend_direction: TrendDirection
    direction: Literal["LONG", "SHORT"]
    episode_origin_index: int
    events: tuple[HLEntryEvent, ...]
    reset_index: int | None
    state: str

    @property
    def highest_entry_number(self) -> int:
        return self.events[-1].number if self.events else 0


@dataclass(frozen=True, slots=True)
class RangeHLCorrectionLocation:
    """Range hierarchy/location context only; never autonomous trade eligibility."""
    local_price_relation: str
    enclosing_relation: str
    semantic: str
    trade_eligible: bool = False


def classify_hl_recurrence(
    candles: tuple[Candle, ...],
    *,
    trend_direction: TrendDirection,
    start_index: int,
    evaluated_index: int | None = None,
    max_events: int = 4,
) -> HLCorrectionRecurrence | None:
    """Reconstruct H/L recurrence from one causal correction episode.

    BROOKS-GAP-012 uses Brooks' relative-bar recurrence: after H1, a lower-high
    continuation bar can arm H2 and a later bar trading above its prior high is H2;
    L2 mirrors this with a higher low. Fresh adverse extremes are not required.
    BROOKS-GAP-013 reset semantics remain the only episode reset source.
    """
    if not candles or trend_direction not in {"BULL_TREND", "BEAR_TREND"}:
        return None
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if start_index < 0 or start_index >= end or end >= len(candles):
        return None
    direction: Literal["LONG", "SHORT"] = "LONG" if trend_direction == "BULL_TREND" else "SHORT"
    episode_origin = start_index
    reset_index: int | None = None
    events: list[HLEntryEvent] = []
    saw_initial_countertrend = False
    initial_counter_index: int | None = None
    armed_index: int | None = None

    for i in range(start_index + 1, end + 1):
        prev, cur = candles[i - 1], candles[i]
        step = correction_step(prev, cur, trend_direction=trend_direction)
        event = cur.high > prev.high if direction == "LONG" else cur.low < prev.low

        if events and armed_index is None and correction_reset_by_resumption(
            candles,
            trend_direction=trend_direction,
            origin_index=episode_origin,
            evaluated_index=i,
        ):
            episode_origin = i
            reset_index = i
            events = []
            saw_initial_countertrend = False
            initial_counter_index = None
            armed_index = None
            continue

        if not events:
            if step == "COUNTERTREND":
                saw_initial_countertrend = True
                if initial_counter_index is None:
                    initial_counter_index = i
            if event and saw_initial_countertrend:
                events.append(HLEntryEvent(
                    i,
                    1,
                    "H1" if direction == "LONG" else "L1",
                    initial_counter_index or i,
                ))
                armed_index = None
            continue

        continuation = cur.high < prev.high if direction == "LONG" else cur.low > prev.low
        if continuation and i > events[-1].index:
            armed_index = i

        if event and armed_index is not None and i > armed_index:
            number = events[-1].number + 1
            if number <= max_events:
                events.append(HLEntryEvent(
                    i,
                    number,
                    f"H{number}" if direction == "LONG" else f"L{number}",
                    armed_index,
                ))
            armed_index = None

    state = f"{events[-1].label}_CONFIRMED" if events else "NO_ENTRY_EVENT"
    return HLCorrectionRecurrence(
        trend_direction,
        direction,
        episode_origin,
        tuple(events),
        reset_index,
        state,
    )


def build_hl_attempt_origin(
    candles: tuple[Candle, ...],
    recurrence: HLCorrectionRecurrence,
    *,
    event_number: int,
    objective_level: Decimal | None,
) -> ReversalPatternOrigin | None:
    event = next((item for item in recurrence.events if item.number == event_number), None)
    if event is None or event.index >= len(candles):
        return None
    signal = candles[event.index]
    trigger = signal.high if recurrence.direction == "LONG" else signal.low
    failure = signal.low if recurrence.direction == "LONG" else signal.high
    return ReversalPatternOrigin(
        attempt_id=f"{event.label}:{recurrence.episode_origin_index}:{event.index}",
        pattern_id=event.label,
        direction=recurrence.direction,
        signal_index=event.index,
        trigger_level=trigger,
        objective_level=objective_level,
        failure_level=failure,
    )


def evaluate_hl_entry_attempt_lifecycle(
    candles: tuple[Candle, ...],
    recurrence: HLCorrectionRecurrence,
    *,
    event_number: int,
    objective_level: Decimal | None,
    evaluated_index: int | None = None,
) -> ReversalPatternLifecycle | None:
    """Evaluate an originating H/L attempt while preserving WAVE_05 failure identity.

    When the owning setup does not supply a scalper objective, the lifecycle refuses
    to label a failure-to-objective. It still exposes trigger/failure-level state so
    consumers can fail closed instead of inventing a target.
    """
    origin = build_hl_attempt_origin(
        candles,
        recurrence,
        event_number=event_number,
        objective_level=objective_level,
    )
    if origin is None:
        return None
    if objective_level is not None:
        return evaluate_reversal_pattern_lifecycle(candles, origin, evaluated_index=evaluated_index)

    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if end < origin.signal_index or end >= len(candles):
        return ReversalPatternLifecycle(origin, "ORIGIN_NOT_YET_AVAILABLE", None, None, None, None)
    trigger: int | None = None
    for i in range(origin.signal_index + 1, end + 1):
        c = candles[i]
        trigger_hit = c.high > origin.trigger_level if origin.direction == "LONG" else c.low < origin.trigger_level
        failure_hit = c.low < origin.failure_level if origin.direction == "LONG" else c.high > origin.failure_level
        if trigger is None:
            if trigger_hit and failure_hit:
                return ReversalPatternLifecycle(origin, "AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR", i, None, i, None)
            if failure_hit:
                return ReversalPatternLifecycle(origin, "SIGNAL_INVALIDATED_BEFORE_TRIGGER", None, None, i, None)
            if trigger_hit:
                trigger = i
                continue
        elif failure_hit:
            return ReversalPatternLifecycle(origin, "FAILURE_LEVEL_BREACHED_OBJECTIVE_UNSPECIFIED", trigger, None, i, origin.direction)
    return ReversalPatternLifecycle(origin, "TRIGGERED_OBJECTIVE_UNSPECIFIED" if trigger is not None else "WAITING_FOR_TRIGGER", trigger, None, None, None)


def classify_range_hl_location(
    hierarchy,
    *,
    current_price: Decimal,
    edge_zone_fraction: Decimal,
) -> RangeHLCorrectionLocation:
    """Consume WAVE_02 local/enclosing hierarchy without turning location into entry."""
    if hierarchy is None or not getattr(hierarchy, "nested", False):
        return RangeHLCorrectionLocation("NOT_NESTED", "NOT_NESTED", "NO_ENCLOSING_RANGE_CONTEXT")
    low, high = hierarchy.local_low, hierarchy.local_high
    if low is None or high is None or high <= low:
        return RangeHLCorrectionLocation(
            "LOCAL_RANGE_UNRESOLVED",
            hierarchy.current_relation,
            "NO_LOCAL_RANGE_GEOMETRY",
        )
    width = high - low
    low_edge = low + width * edge_zone_fraction
    high_edge = high - width * edge_zone_fraction
    if current_price <= low_edge:
        local = "NEAR_LOCAL_LOW"
    elif current_price >= high_edge:
        local = "NEAR_LOCAL_HIGH"
    else:
        local = "LOCAL_MIDDLE"
    enclosing = hierarchy.current_relation
    if enclosing.startswith("DEPARTING_"):
        semantic = enclosing
    elif local == "NEAR_LOCAL_LOW" and hierarchy.local_position == "NEAR_ENCLOSING_LOW":
        semantic = "ENCLOSING_LOW_EDGE"
    elif local == "NEAR_LOCAL_HIGH" and hierarchy.local_position == "NEAR_ENCLOSING_HIGH":
        semantic = "ENCLOSING_HIGH_EDGE"
    elif (
        local in {"NEAR_LOCAL_LOW", "NEAR_LOCAL_HIGH"}
        and hierarchy.local_position == "ENCLOSING_MIDDLE"
    ):
        semantic = "LOCAL_EDGE_ENCLOSING_MIDDLE"
    else:
        semantic = "ENCLOSING_MIDDLE_OR_NONALIGNED_EDGE"
    return RangeHLCorrectionLocation(local, enclosing, semantic, False)



@dataclass(frozen=True, slots=True)
class WedgeSecondSignalIdentity:
    """Wedge-owned specialization of the generic WAVE_05 reversal-attempt lifecycle."""
    wedge_structure_id: str
    side: str
    push_indices: tuple[int, int, int]
    trend_direction: TrendDirection
    reversal_direction: Literal["LONG", "SHORT"]
    first_attempt_index: int | None
    resumption_index: int | None
    second_attempt_index: int | None
    state: str


@dataclass(frozen=True, slots=True)
class WedgeAttemptOrigin:
    wedge: WedgeSecondSignalIdentity
    signal_number: int
    reversal_origin: ReversalPatternOrigin


@dataclass(frozen=True, slots=True)
class WedgeAttemptLifecycle:
    origin: WedgeAttemptOrigin
    reversal_lifecycle: ReversalPatternLifecycle
    failure_confirmed: bool

    @property
    def state(self) -> str:
        return self.reversal_lifecycle.state


def classify_wedge_second_signal(
    candles: tuple[Candle, ...],
    *,
    push_indices: tuple[int, int, int],
    side: str,
    evaluated_index: int | None = None,
) -> WedgeSecondSignalIdentity | None:
    """Attach generic first/fail/resume/second reversal state to one wedge structure."""
    if side not in {"TOP", "BOTTOM"} or len(push_indices) != 3:
        return None
    if tuple(sorted(push_indices)) != push_indices or push_indices[-1] >= len(candles):
        return None
    trend_direction: TrendDirection = "BULL_TREND" if side == "TOP" else "BEAR_TREND"
    generic = classify_generic_reversal_attempts(
        candles,
        trend_direction=trend_direction,
        start_index=push_indices[-1],
        evaluated_index=evaluated_index
    )
    if generic is None:
        return None
    wedge_id = f"WEDGE:{side}:{push_indices[0]}:{push_indices[1]}:{push_indices[2]}"
    return WedgeSecondSignalIdentity(
        wedge_structure_id=wedge_id, side=side, push_indices=push_indices, trend_direction=trend_direction,
        reversal_direction=generic.reversal_direction, first_attempt_index=generic.first_attempt_index,
        resumption_index=generic.resumption_index, second_attempt_index=generic.second_attempt_index, state=generic.state,
    )


def build_wedge_attempt_origin(
    candles: tuple[Candle, ...],
    wedge: WedgeSecondSignalIdentity,
    *,
    signal_number: int,
    objective_level: Decimal | None,
) -> WedgeAttemptOrigin | None:
    """Create a wedge-specific identity while reusing ReversalPatternOrigin."""
    signal_index = (
        wedge.first_attempt_index
        if signal_number == 1
        else wedge.second_attempt_index
        if signal_number == 2
        else None
    )
    if signal_index is None or signal_index >= len(candles):
        return None
    signal = candles[signal_index]
    direction = wedge.reversal_direction
    trigger = signal.high if direction == "LONG" else signal.low
    failure = signal.low if direction == "LONG" else signal.high
    origin = ReversalPatternOrigin(
        attempt_id=f"{wedge.wedge_structure_id}:S{signal_number}:{signal_index}",
        pattern_id=f"WEDGE_{wedge.side}_SIGNAL_{signal_number}",
        direction=direction,
        signal_index=signal_index,
        trigger_level=trigger, objective_level=objective_level, failure_level=failure,
    )
    return WedgeAttemptOrigin(wedge=wedge, signal_number=signal_number, reversal_origin=origin)


def evaluate_wedge_attempt_lifecycle(
    candles: tuple[Candle, ...], origin: WedgeAttemptOrigin, *, evaluated_index: int | None = None,
) -> WedgeAttemptLifecycle:
    """Reuse WAVE_05 trigger/failure ordering; fail closed if an objective is not owned."""
    life = evaluate_reversal_pattern_lifecycle(candles, origin.reversal_origin, evaluated_index=evaluated_index)
    confirmed = life.state == "FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE" and origin.reversal_origin.objective_level is not None
    if life.state == "FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE" and origin.reversal_origin.objective_level is None:
        life = ReversalPatternLifecycle(
            life.origin, "FAILURE_LEVEL_BREACHED_OBJECTIVE_UNSPECIFIED", life.trigger_index, life.objective_index, life.failure_index, life.trapped_side
        )
    return WedgeAttemptLifecycle(origin=origin, reversal_lifecycle=life, failure_confirmed=confirmed)

@dataclass(frozen=True, slots=True)
class ActiveTrendEpisode:
    """Current directional regime episode; stale historical structure is never active."""
    trend_direction: TrendDirection
    episode_id: str
    origin_index: int
    evaluated_index: int
    active: bool
    late_trend: bool
    state: str


@dataclass(frozen=True, slots=True)
class FinalFlagLifecycle:
    """Final-flag identity owned by one active late-trend episode."""
    trend: ActiveTrendEpisode
    final_flag_id: str
    flag_origin_index: int
    flag_end_index: int
    flag_low: Decimal
    flag_high: Decimal
    bar_count: int
    state: str


@dataclass(frozen=True, slots=True)
class FinalFlagAttemptOrigin:
    final_flag: FinalFlagLifecycle
    reversal_origin: ReversalPatternOrigin


@dataclass(frozen=True, slots=True)
class FinalFlagAttemptLifecycle:
    origin: FinalFlagAttemptOrigin
    reversal_lifecycle: ReversalPatternLifecycle
    failure_confirmed: bool

    @property
    def state(self) -> str:
        return self.reversal_lifecycle.state


@dataclass(frozen=True, slots=True)
class ExhaustionOriginIdentity:
    """BROOKS-GAP-063: late-trend acceleration origin, not an outcome prediction."""
    trend: ActiveTrendEpisode
    exhaustion_id: str
    direction: Literal["LONG", "SHORT"]
    origin_index: int
    engineering_acceleration_evidence: bool
    state: str = "EXHAUSTION_ORIGIN_PENDING_OUTCOME"


@dataclass(frozen=True, slots=True)
class ClimaxOutcomeLifecycle:
    """BROOKS-GAP-064: causal outcome owned by one BROOKS-GAP-063 origin."""
    origin: ExhaustionOriginIdentity
    state: str
    evaluated_index: int
    transition_index: int | None
    reversal_attempt_index: int | None


@dataclass(frozen=True, slots=True)
class HeadShouldersOutcomeIdentity:
    """BROOKS-GAP-058 consumer of WAVE_04 H&S geometry/lifecycle."""
    structure_id: str
    side: str
    left_shoulder_index: int
    head_index: int
    right_shoulder_index: int
    prior_trend_direction: TrendDirection
    with_trend_direction: Literal["LONG", "SHORT"]
    reversal_direction: Literal["LONG", "SHORT"]
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class MTRRetestLifecycle:
    """Structural MTR break/retest/second-reversal state with no universal timer."""
    prior_trend_direction: TrendDirection
    reversal_direction: Literal["LONG", "SHORT"]
    mtr_episode_id: str
    old_extreme_index: int
    structure_break_index: int
    retest_index: int | None
    second_reversal_index: int | None
    active: bool
    state: str


def build_active_trend_episode(
    *, trend_direction: TrendDirection, origin_index: int, evaluated_index: int, late_trend: bool
) -> ActiveTrendEpisode | None:
    if (
        trend_direction not in {"BULL_TREND", "BEAR_TREND"}
        or origin_index < 0
        or evaluated_index < origin_index
    ):
        return None
    episode_id = f"TREND:{trend_direction}:{origin_index}"
    return ActiveTrendEpisode(
        trend_direction=trend_direction, episode_id=episode_id, origin_index=origin_index,
        evaluated_index=evaluated_index, active=True, late_trend=late_trend,
        state="ACTIVE_LATE_TREND" if late_trend else "ACTIVE_TREND_NOT_LATE",
    )


def build_final_flag_lifecycle(
    candles: tuple[Candle, ...],
    trend: ActiveTrendEpisode,
    *,
    flag_origin_index: int,
    flag_end_index: int
) -> FinalFlagLifecycle | None:
    if not trend.active or not trend.late_trend or flag_origin_index < trend.origin_index:
        return None
    if flag_end_index < flag_origin_index or flag_end_index >= len(candles):
        return None
    flag = candles[flag_origin_index:flag_end_index + 1]
    if not flag:
        return None
    flag_id = f"FINAL_FLAG:{trend.episode_id}:{flag_origin_index}:{flag_end_index}"
    return FinalFlagLifecycle(
        trend=trend, final_flag_id=flag_id, flag_origin_index=flag_origin_index,
        flag_end_index=flag_end_index, flag_low=min(c.low for c in flag),
        flag_high=max(c.high for c in flag), bar_count=len(flag), state="ACTIVE_FINAL_FLAG_CONTEXT",
    )


def build_final_flag_attempt_origin(
    candles: tuple[Candle, ...], final_flag: FinalFlagLifecycle, *, signal_index: int,
    direction: Literal["LONG", "SHORT"], objective_level: Decimal | None = None,
) -> FinalFlagAttemptOrigin | None:
    if (
        direction not in {"LONG", "SHORT"}
        or signal_index <= final_flag.flag_end_index
        or signal_index >= len(candles)
    ):
        return None
    signal = candles[signal_index]
    trigger = signal.high if direction == "LONG" else signal.low
    failure = signal.low if direction == "LONG" else signal.high
    origin = ReversalPatternOrigin(
        attempt_id=f"{final_flag.final_flag_id}:SIGNAL:{signal_index}",
        pattern_id="FINAL_FLAG_REVERSAL", direction=direction, signal_index=signal_index,
        trigger_level=trigger, objective_level=objective_level, failure_level=failure,
    )
    return FinalFlagAttemptOrigin(final_flag=final_flag, reversal_origin=origin)


def evaluate_final_flag_attempt_lifecycle(
    candles: tuple[Candle, ...], origin: FinalFlagAttemptOrigin, *, evaluated_index: int | None = None,
) -> FinalFlagAttemptLifecycle:
    life = evaluate_reversal_pattern_lifecycle(candles, origin.reversal_origin, evaluated_index=evaluated_index)
    confirmed = life.state == "FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE"
    return FinalFlagAttemptLifecycle(origin=origin, reversal_lifecycle=life, failure_confirmed=confirmed)


def build_exhaustion_origin(
    candles: tuple[Candle, ...], trend: ActiveTrendEpisode, *, origin_index: int,
    engineering_acceleration_evidence: bool,
) -> ExhaustionOriginIdentity | None:
    """Create an exhaustion origin only inside an active mature/late trend.

    Numeric bar-size/strength evidence is explicitly engineering evidence and can never
    establish exhaustion without the current active late-trend episode.
    """
    if not trend.active or not trend.late_trend or not engineering_acceleration_evidence:
        return None
    if not (trend.origin_index <= origin_index < len(candles)):
        return None
    bar = candles[origin_index]
    direction: Literal["LONG", "SHORT"] = (
        "LONG" if trend.trend_direction == "BULL_TREND" else "SHORT"
    )
    aligned = bar.close > bar.open if direction == "LONG" else bar.close < bar.open
    if not aligned:
        return None
    eid = f"EXHAUSTION:{trend.episode_id}:{origin_index}"
    return ExhaustionOriginIdentity(trend, eid, direction, origin_index, True)


def classify_climax_outcome(
    candles: tuple[Candle, ...], origin: ExhaustionOriginIdentity, *, current_regime: str,
    current_always_in: str = "UNRESOLVED", evaluated_index: int | None = None,
) -> ClimaxOutcomeLifecycle:
    """Resolve one climax origin causally; no timer or anonymous reconstruction."""
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    end = max(origin.origin_index, min(end, len(candles) - 1))
    if end <= origin.origin_index:
        return ClimaxOutcomeLifecycle(origin, "PENDING_CLIMAX_OUTCOME", end, None, None)
    reversal = is_bear_reversal_bar_minimum if origin.direction == "LONG" else is_bull_reversal_bar_minimum
    attempt = next((i for i in range(origin.origin_index + 1, end + 1) if reversal(candles[i])), None)
    opposite_regime = "BEAR_TREND" if origin.direction == "LONG" else "BULL_TREND"
    opposite_ai = "SHORT" if origin.direction == "LONG" else "LONG"
    if (
        current_regime == opposite_regime
        or (current_regime == "TRANSITION" and current_always_in == opposite_ai)
    ):
        return ClimaxOutcomeLifecycle(origin, "RESOLVED_OPPOSITE_TREND", end, end, attempt)
    if current_regime == "TRADING_RANGE":
        return ClimaxOutcomeLifecycle(origin, "RESOLVED_TRADING_RANGE", end, end, attempt)
    if attempt is not None:
        origin_bar = candles[origin.origin_index]
        continuation = next((
            i for i in range(attempt + 1, end + 1)
            if (
                candles[i].high > origin_bar.high
                if origin.direction == "LONG"
                else candles[i].low < origin_bar.low
            )
        ), None)
        aligned_regime = "BULL_TREND" if origin.direction == "LONG" else "BEAR_TREND"
        if continuation is not None and current_regime == aligned_regime:
            return ClimaxOutcomeLifecycle(origin, "RESOLVED_CONTINUATION", end, continuation, attempt)
        return ClimaxOutcomeLifecycle(origin, "REVERSAL_ATTEMPT_PENDING_OUTCOME", end, attempt, attempt)
    return ClimaxOutcomeLifecycle(origin, "PENDING_CLIMAX_OUTCOME", end, None, None)


def classify_head_shoulders_outcome(
    *,
    side: str,
    left_shoulder_index: int,
    head_index: int,
    right_shoulder_index: int,
    neckline_state: str,
) -> HeadShouldersOutcomeIdentity | None:
    """Consume WAVE_04 H&S lifecycle without treating the textbook shape as a trade."""
    if side not in {"TOP", "BOTTOM"}:
        return None
    prior: TrendDirection = "BULL_TREND" if side == "TOP" else "BEAR_TREND"
    with_trend: Literal["LONG", "SHORT"] = "LONG" if side == "TOP" else "SHORT"
    reversal: Literal["LONG", "SHORT"] = "SHORT" if side == "TOP" else "LONG"
    if neckline_state == "FAILED_NECKLINE_BREAK_REENTRY":
        state = "WITH_TREND_CONTINUATION_CONTEXT"
    elif neckline_state == "CONTINUATION_BEYOND_NECKLINE":
        state = "REVERSAL_FOLLOW_THROUGH_CONTEXT"
    elif neckline_state in {"NECKLINE_BREAK", "RIGHT_SHOULDER_AFTER_TREND_LINE_BREAK"}:
        state = "REVERSAL_ATTEMPT_PENDING_FOLLOW_THROUGH"
    else:
        state = "ALIAS_RANGE_OR_FLAG_CONTEXT"
    sid = f"HNS:{side}:{left_shoulder_index}:{head_index}:{right_shoulder_index}"
    return HeadShouldersOutcomeIdentity(
        sid,
        side,
        left_shoulder_index,
        head_index,
        right_shoulder_index,
        prior,
        with_trend,
        reversal,
        state,
        False,
    )


def classify_mtr_retest_lifecycle(
    candles: tuple[Candle, ...], *, prior_trend_direction: TrendDirection,
    old_extreme_index: int, structure_break_index: int, engineering_test_tolerance: Decimal,
    episode_active: bool = True, evaluated_index: int | None = None,
) -> MTRRetestLifecycle | None:
    """Preserve one MTR episode; time since break is never a source-semantic gate."""
    if prior_trend_direction not in {"BULL_TREND", "BEAR_TREND"} or not candles:
        return None
    end = len(candles) - 1 if evaluated_index is None else evaluated_index
    if not (0 <= old_extreme_index < structure_break_index <= end < len(candles)):
        return None
    direction: Literal["LONG", "SHORT"] = (
        "SHORT" if prior_trend_direction == "BULL_TREND" else "LONG"
    )
    eid = f"MTR:{prior_trend_direction}:{old_extreme_index}:{structure_break_index}"
    if not episode_active:
        return MTRRetestLifecycle(prior_trend_direction, direction, eid, old_extreme_index, structure_break_index, None, None, False, "EPISODE_INACTIVE")
    level = candles[old_extreme_index].high if prior_trend_direction == "BULL_TREND" else candles[old_extreme_index].low
    retest = None
    for i in range(structure_break_index + 1, end + 1):
        c = candles[i]
        hit = (
            c.high >= level - engineering_test_tolerance
            if direction == "SHORT"
            else c.low <= level + engineering_test_tolerance
        )
        if hit:
            retest = i
            break
    if retest is None:
        return MTRRetestLifecycle(prior_trend_direction, direction, eid, old_extreme_index, structure_break_index, None, None, True, "WAITING_OLD_EXTREME_RETEST")
    reversal = is_bear_reversal_bar_minimum if direction == "SHORT" else is_bull_reversal_bar_minimum
    second = next((i for i in range(retest, end + 1) if reversal(candles[i])), None)
    state = "SECOND_REVERSAL_CONFIRMED" if second is not None else "RETEST_CONFIRMED_WAITING_SECOND_REVERSAL"
    return MTRRetestLifecycle(prior_trend_direction, direction, eid, old_extreme_index, structure_break_index, retest, second, True, state)

