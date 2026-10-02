"""Source-grounded pattern families from the Al Brooks trilogy.

The goal is not to turn every chart description into a magic numeric score.  Each
family has its own context and geometry.  Where Brooks is qualitative, deterministic
OHLC interpretations are explicitly marked SOURCE_INTERPRETATION or ENGINEERING_POLICY.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from statistics import median

from app.modules.brooks_core.advanced_context import classify_spike_channel_lifecycle
from app.modules.brooks_core.books_full_entities import (
    BrooksPatternCandidate,
    BrooksPatternObservation,
    BrooksPatternScan,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.causal_structure import (
    confirm_swings_causally,
    evaluate_br031_structure,
)
from app.modules.brooks_core.context_classifier import (
    body_fraction,
    close_location,
    is_strong_bear_bar,
    is_strong_bull_bar,
    is_bear_reversal_bar_minimum,
    is_bull_reversal_bar_minimum,
    assess_books_context,
    assess_range_identity_evidence,
    classify_broad_trading_range,
    classify_tight_trading_range,
    classify_barbwire_identity,
    classify_range_edge,
    classify_strong_trend_evidence,
)
from app.modules.brooks_core.second_entry_v2 import detect_book_second_entry
from app.modules.brooks_core.structural_geometry import (
    projected_value_from_swings, build_structural_second_test, build_micro_double_structure,
)
from app.modules.brooks_core.correction_lifecycle import (
    classify_wedge_second_signal, build_wedge_attempt_origin, evaluate_wedge_attempt_lifecycle,
    build_active_trend_episode, build_final_flag_lifecycle, build_final_flag_attempt_origin,
    evaluate_final_flag_attempt_lifecycle, classify_mtr_retest_lifecycle,
    build_exhaustion_origin, classify_climax_outcome,
    build_breakout_attempt_identity, classify_breakout_lifecycle,
    classify_failed_breakout_confirmation, classify_failure_of_failure,
)
from app.modules.brooks_core.pattern_expansion import scan_extended_patterns
from app.modules.market_data.entities import Candle, MarketSnapshot

_ZERO = Decimal("0")
_HALF = Decimal("0.5")
_MICRO_DOUBLE_SEARCH_MAX_BARS = 3  # ENGINEERING_SEARCH_POLICY, not a Brooks universal rule.
# ENGINEERING_SEARCH_POLICY only; never final-flag validity.
_FINAL_FLAG_FAILURE_SEARCH_MAX_BARS = 40


def _span(candles: tuple[Candle, ...]) -> Decimal:
    if not candles:
        return _ZERO
    return max(c.high for c in candles) - min(c.low for c in candles)


def _ema20_values(candles: tuple[Candle, ...]) -> tuple[Decimal, ...]:
    if not candles:
        return ()
    alpha = Decimal("2") / Decimal("21")
    value = candles[0].close
    values = [value]
    for candle in candles[1:]:
        value = candle.close * alpha + value * (Decimal("1") - alpha)
        values.append(value)
    return tuple(values)


def _bull_reversal(c: Candle) -> bool:
    return is_bull_reversal_bar_minimum(c)


def _bear_reversal(c: Candle) -> bool:
    return is_bear_reversal_bar_minimum(c)


def _candidate_side_event(direction: str, current: Candle, previous: Candle) -> bool:
    return current.high > previous.high if direction == "LONG" else current.low < previous.low


def _close_beyond(direction: str, candle: Candle, level: Decimal) -> bool:
    return candle.close > level if direction == "LONG" else candle.close < level


def _close_back_inside(direction: str, candle: Candle, level: Decimal) -> bool:
    return candle.close <= level if direction == "LONG" else candle.close >= level


def _latest_swing_before(
    candles: tuple[Candle, ...],
    *,
    end_exclusive: int,
    kind: str,
    policy: BrooksFullCorePolicy,
):
    if end_exclusive < policy.context.swing_left_bars + policy.context.swing_right_bars + 2:
        return None
    scan = confirm_swings_causally(
        candles[:end_exclusive],
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    matches = [s for s in scan.swings if s.kind == kind]
    return matches[-1] if matches else None


def _swing_level(candles: tuple[Candle, ...], swing) -> Decimal:
    candle = candles[swing.candle_index]
    return candle.high if swing.kind == "HIGH" else candle.low


def detect_trend_second_entry(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    if context.regime not in {"BULL_TREND", "BEAR_TREND"}:
        return None

    scan = confirm_swings_causally(
        snapshot.candles,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    wanted = "HIGH" if context.regime == "BULL_TREND" else "LOW"
    anchors = [s for s in scan.swings if s.kind == wanted]
    if not anchors:
        return None

    start_index = anchors[-1].candle_index
    if len(snapshot.candles) - start_index > policy.context.pullback_window_bars:
        start_index = len(snapshot.candles) - policy.context.pullback_window_bars

    assessment = detect_book_second_entry(
        snapshot.candles,
        trend_direction=context.regime,
        start_index=start_index,
    )
    if assessment.setup is None:
        if assessment.events:
            event = assessment.events[-1]
            if event.index == len(snapshot.candles) - 1 and event.label in {"H1", "L1"}:
                direction = "LONG" if event.label == "H1" else "SHORT"
                return BrooksPatternCandidate(
                    direction=direction,
                    setup_type=f"{event.label}_CONFIRMED",
                    family="TREND_CONTINUATION",
                    signal_index=event.index,
                    reasons=(
                        f"mature_{context.regime.lower()}_context",
                        f"source_bar_count_{event.label.lower()}",
                        "first_with_trend_pullback_entry",
                    ),
                    source_rule_ids=(
                        "BB-TRD-19-TREND-STRENGTH",
                        "BB-RNG-17-HL-BAR-COUNT",
                        "BB-RNG-26-TWO-REASONS",
                    ),
                    taxonomy="SOURCE_INTERPRETATION",
                    priority=18,
                    context_required=context.regime,
                    metadata=(("start_index", str(start_index)), ("entry_number", "1")),
                )
        return None

    setup = assessment.setup
    return BrooksPatternCandidate(
        direction=setup.direction,
        setup_type=setup.setup_type,
        family="TREND_CONTINUATION",
        signal_index=setup.signal_index,
        reasons=(
            f"mature_{context.regime.lower()}_context",
            f"source_bar_count_{setup.setup_type.lower()}",
            "two_leg_pullback_second_entry",
        ),
        source_rule_ids=(
            "BB-TRD-19-TREND-STRENGTH",
            "BB-RNG-17-HL-BAR-COUNT",
            "BB-RNG-26-TWO-REASONS",
        ),
        taxonomy="SOURCE_INTERPRETATION",
        priority=10,
        context_required=context.regime,
        metadata=(("start_index", str(start_index)),),
    )


def _typed_breakout_failure_candidates(candles: tuple[Candle, ...], policy: BrooksFullCorePolicy):
    """WAVE_10 034/035: strength-aware failed breakout and genuine failure-of-failure."""
    last = len(candles) - 1
    out: list[BrooksPatternCandidate] = []
    for breakout_index in range(max(1, last - 40), last):  # ENGINEERING_SEARCH_POLICY only.
        for breakout_direction, kind in (("LONG", "HIGH"), ("SHORT", "LOW")):
            swing = _latest_swing_before(
                candles,
                end_exclusive=breakout_index,
                kind=kind,
                policy=policy,
            )
            if swing is None:
                continue
            level = _swing_level(candles, swing)
            bar = candles[breakout_index]
            extends = bar.high > level if breakout_direction == "LONG" else bar.low < level
            if not extends:
                continue
            breakout_strong = (
                is_strong_bull_bar(bar, policy.context)
                if breakout_direction == "LONG"
                else is_strong_bear_bar(bar, policy.context)
            )
            origin = build_breakout_attempt_identity(
                candles, direction=breakout_direction, reference_id=f"SWING:{swing.candle_index}",
                reference_level=level,
                attempt_index=breakout_index,
                engineering_strong=breakout_strong,
            )
            if origin is None:
                continue
            life = classify_breakout_lifecycle(candles, origin, evaluated_index=last)
            if life.reentry_index is None:
                continue
            ri = life.reentry_index
            rev_dir = "SHORT" if breakout_direction == "LONG" else "LONG"
            rb = candles[ri]
            rev_strong = is_strong_bear_bar(rb, policy.context) if rev_dir == "SHORT" else is_strong_bull_bar(rb, policy.context)
            fb = classify_failed_breakout_confirmation(
                candles, origin, signal_index=ri, reversal_is_strong=rev_strong, evaluated_index=last,
            )
            if fb is None:
                continue
            confirmed = fb.state in {"CONFIRMED_STRONG_REVERSAL_WEAK_BREAKOUT", "CONFIRMED_BY_NEXT_BAR_FOLLOW_THROUGH"}
            confirm_index = ri if fb.state == "CONFIRMED_STRONG_REVERSAL_WEAK_BREAKOUT" else fb.next_bar_index
            if confirmed and confirm_index == last:
                out.append(BrooksPatternCandidate(
                    direction=fb.reversal_direction, setup_type=f"FAILED_BREAKOUT_{fb.reversal_direction}", family="FAILED_BREAKOUT",
                    signal_index=last,
                    reasons=("breakout_attempt_beyond_causal_swing", "origin_preserving_reentry_reversal", "strength_or_next_bar_confirmation"),
                    source_rule_ids=("BB-RNG-05-FAILED-BREAKOUT", "BB-RNG-26-TWO-REASONS"), taxonomy="SOURCE_INTERPRETATION", priority=18,
                    context_required="RANGE_OR_FAILED_BREAKOUT",
                    metadata=(("breakout_id", origin.breakout_id), ("breakout_index", str(breakout_index)), ("reference_level", str(level)),
                              ("confirmation_state", fb.state), ("breakout_strength", fb.breakout_strength), ("reversal_strength", fb.reversal_strength)),
                ))
            fof = classify_failure_of_failure(candles, fb, evaluated_index=last)
            if fof.state == "FAILURE_OF_FAILURE_CONFIRMED" and fof.later_failure_index == last:
                out.append(BrooksPatternCandidate(
                    direction=breakout_direction, setup_type=f"FAILED_FAILURE_{breakout_direction}", family="FAILED_FAILURE", signal_index=last,
                    reasons=("genuine_failed_breakout_reversal_triggered", "same_first_failure_attempt_later_failed", "original_breakout_direction_resumed"),
                    source_rule_ids=("BB-RNG-05-FAILED-FAILURE", "BB-RNG-05-BREAKOUT-PULLBACK", "BB-RNG-26-TWO-REASONS"),
                    taxonomy="SOURCE_INTERPRETATION", priority=11, context_required="BREAKOUT_RESUMPTION",
                    metadata=(("breakout_id", origin.breakout_id), ("first_failure_attempt_id", fof.reversal_origin.attempt_id if fof.reversal_origin else ""),
                              ("first_failure_signal_index", str(fb.signal_index)), ("later_failure_index", str(fof.later_failure_index)),
                              ("failure_of_failure_state", fof.state)),
                ))
    return tuple(out)


def detect_breakout_family(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    candles = snapshot.candles
    final = candles[-1]
    candidates: list[BrooksPatternCandidate] = []

    # Fresh breakout on the final closed bar over/under the latest causal swing.
    for direction, kind in (("LONG", "HIGH"), ("SHORT", "LOW")):
        swing = _latest_swing_before(
            candles,
            end_exclusive=len(candles) - 1,
            kind=kind,
            policy=policy,
        )
        if swing is None:
            continue
        level = _swing_level(candles, swing)
        strong = (
            is_strong_bull_bar(final, policy.context)
            if direction == "LONG"
            else is_strong_bear_bar(final, policy.context)
        )
        previous = candles[-2]
        previous_strong = (
            is_strong_bull_bar(previous, policy.context)
            if direction == "LONG"
            else is_strong_bear_bar(previous, policy.context)
        )
        follow_through = previous_strong and _close_beyond(direction, previous, level)
        close_beyond = _close_beyond(direction, final, level)
        # BROOKS-GAP-004: a decisive single breakout bar can be sufficient in
        # context; a second strong bar is stronger follow-through evidence, not
        # the universal definition of a breakout.  Wick-only attempts are kept
        # observation-only by BROOKS-GAP-033 and never reach this trade candidate.
        if close_beyond and strong:
            reasons = [
                "close_beyond_causal_swing_level",
                "strong_directional_breakout_bar",
            ]
            if follow_through:
                reasons.extend((
                    "two_consecutive_strong_bars_beyond_breakout_level",
                    "breakout_follow_through_confirmed",
                ))
            else:
                reasons.append("decisive_single_bar_breakout")
            reasons.append(f"context_{context.regime.lower()}")
            candidates.append(
                BrooksPatternCandidate(
                    direction=direction,
                    setup_type=f"BREAKOUT_{direction}",
                    family="BREAKOUT",
                    signal_index=len(candles) - 1,
                    reasons=tuple(reasons),
                    source_rule_ids=(
                        "BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",
                        "BB-REV-15-ALWAYS-IN",
                        "BB-RNG-26-TWO-REASONS",
                    ),
                    taxonomy="SOURCE_INTERPRETATION",
                    priority=20,
                    context_required="BREAKOUT_OR_TREND",
                    metadata=(
                        ("reference_swing_index", str(swing.candle_index)),
                        ("reference_level", str(level)),
                        ("breakout_strength", "strong"),
                        ("follow_through", "true" if follow_through else "false"),
                    ),
                )
            )

    # Breakout pullback / failed failure.  Brooks explicitly describes a small
    # breakout pullback as roughly one to five bars.
    last = len(candles) - 1
    earliest = max(1, last - policy.breakout_pullback_max_bars)
    for breakout_index in range(earliest, last):
        for direction, kind in (("LONG", "HIGH"), ("SHORT", "LOW")):
            swing = _latest_swing_before(
                candles,
                end_exclusive=breakout_index,
                kind=kind,
                policy=policy,
            )
            if swing is None:
                continue
            level = _swing_level(candles, swing)
            breakout_bar = candles[breakout_index]
            if not _close_beyond(direction, breakout_bar, level):
                continue

            between = candles[breakout_index + 1 : last]
            final_resumes = _candidate_side_event(direction, final, candles[-2])
            final_holds = _close_beyond(direction, final, level)
            if not (final_resumes and final_holds):
                continue

            had_failure = any(_close_back_inside(direction, c, level) for c in between)
            pullback_seen = bool(between) and any(
                (c.close < c.open or c.low <= level)
                if direction == "LONG"
                else (c.close > c.open or c.high >= level)
                for c in between
            )
            if had_failure:
                # BROOKS-GAP-035: a reentry alone is not a genuine failure-of-failure.
                # The typed origin/trigger/failure chain is evaluated separately below.
                continue
            if not pullback_seen:
                continue
            family = "BREAKOUT_PULLBACK"
            setup_type = f"BREAKOUT_PULLBACK_{direction}"
            reasons = (
                "prior_breakout_beyond_causal_swing",
                "small_one_to_five_bar_pullback",
                "final_bar_resumes_breakout_direction",
            )
            rule_ids = (
                "BB-RNG-05-BREAKOUT-PULLBACK",
                "BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",
                "BB-RNG-26-TWO-REASONS",
            )
            priority = 12

            candidates.append(
                BrooksPatternCandidate(
                    direction=direction,
                    setup_type=setup_type,
                    family=family,
                    signal_index=last,
                    reasons=reasons,
                    source_rule_ids=rule_ids,
                    taxonomy="SOURCE_INTERPRETATION",
                    priority=priority,
                    context_required="BREAKOUT_RESUMPTION",
                    metadata=(
                        ("breakout_index", str(breakout_index)),
                        ("reference_swing_index", str(swing.candle_index)),
                        ("reference_level", str(level)),
                    ),
                )
            )

            # earliest qualifying breakout is enough for a deterministic family scan
            break

    # WAVE_10 034/035: typed strength comparison and genuine failure-of-failure.
    candidates.extend(_typed_breakout_failure_candidates(candles, policy))

    return tuple(candidates)


def detect_trading_range_fades(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
    market_context=None,
):
    """BROOKS-GAP-045: typed range-edge fade/limit execution using WAVE_11 identity."""
    if context.regime != "TRADING_RANGE":
        return ()

    candles = snapshot.candles
    if len(candles) < policy.range_window_bars:
        return ()
    base = tuple(candles[-policy.range_window_bars:-1])
    final = candles[-1]
    origin_index = len(candles) - 1 - len(base)

    broad = classify_broad_trading_range(base, policy.context, origin_index=origin_index)
    ttr = classify_tight_trading_range(base, policy.context)
    barbwire = classify_barbwire_identity(base, policy.context)
    if broad is None or not broad.is_broad:
        return ()
    if (ttr is not None and ttr.is_tight) or (barbwire is not None and barbwire.is_barbwire):
        return ()
    if market_context is not None:
        if market_context.range_subtype != "BROAD_TRADING_RANGE" or market_context.barbwire_active:
            return ()

    out: list[BrooksPatternCandidate] = []
    for direction in ("LONG", "SHORT"):
        edge = classify_range_edge(
            base, final, policy.context, direction=direction,
            origin_index=origin_index, evaluated_index=len(candles)-1,
        )
        if edge is None:
            continue
        expected = "AT_LOWER_RANGE_EDGE" if direction == "LONG" else "AT_UPPER_RANGE_EDGE"
        if edge.state != expected:
            continue

        hierarchy_state = "NOT_NESTED"
        if market_context is not None and market_context.range_hierarchy is not None:
            hierarchy = market_context.range_hierarchy
            if hierarchy.nested:
                hierarchy_state = hierarchy.local_position
                required = "NEAR_ENCLOSING_LOW" if direction == "LONG" else "NEAR_ENCLOSING_HIGH"
                if hierarchy.local_position != required:
                    # A local edge in the enclosing middle is not silently promoted.
                    continue

        reversal_ok = _bull_reversal(final) if direction == "LONG" else _bear_reversal(final)
        reference_price = edge.low if direction == "LONG" else edge.high
        reasons = (
            "broad_trading_range_with_room",
            "canonical_range_edge_identity",
            "source_range_fade_limit_or_market_execution",
        )
        if reversal_ok:
            reasons += ("reversal_bar_additional_confirmation",)

        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"TRADING_RANGE_FADE_{direction}",
            family="TRADING_RANGE_FADE",
            signal_index=len(candles)-1,
            reasons=reasons,
            source_rule_ids=(
                "BB-RNG-21-BUY-LOW-SELL-HIGH",
                "BB-RNG-22-TIGHT-RANGE",
                "BB-RNG-26-TWO-REASONS",
            ),
            taxonomy="SOURCE_INTERPRETATION",
            priority=15,
            context_required="TRADING_RANGE",
            metadata=(
                ("canonical_gap_id", "BROOKS-GAP-045"),
                ("range_id", edge.range_id),
                ("range_low", str(edge.low)),
                ("range_high", str(edge.high)),
                ("range_subtype", broad.state),
                ("range_edge_state", edge.state),
                ("range_hierarchy_state", hierarchy_state),
                ("edge_engineering_tolerance", str(edge.engineering_tolerance)),
                (
                    "edge_semantic",
                    "CANONICAL_RANGE_BOUNDARY_WITH_ENGINEERING_TOLERANCE_NOT_UNIVERSAL_PERCENT",
                ),
                ("trade_room_multiple", str(broad.room_multiple)),
                ("entry_method", "LIMIT_OR_MARKET_FADE"),
                ("entry_trigger_semantic", "AT_OR_NEAR_CANONICAL_RANGE_EDGE"),
                ("entry_reference_price", str(reference_price)),
                (
                    "economic_opportunity_id",
                    f"RANGE_FADE:{edge.range_id}:{direction}:{len(candles)-1}",
                ),
                ("entry_confirmation_state", "RANGE_EDGE_LOCATION_CONFIRMED"),
            ),
        ))
    return tuple(out)


def detect_double_top_bottom(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """BROOKS-GAP-051: structural second test, never numeric equality alone."""
    candles = snapshot.candles
    scan = confirm_swings_causally(
        candles,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars
    )
    final = candles[-1]
    last = len(candles) - 1
    out: list[BrooksPatternCandidate] = []
    for side, direction, reversal_ok in (
        ("TOP", "SHORT", _bear_reversal(final)),
        ("BOTTOM", "LONG", _bull_reversal(final)),
    ):
        if not reversal_ok:
            continue
        structure = build_structural_second_test(candles, scan, side=side, evaluated_index=last)
        if structure is None or structure.confirmed_at_index > last:
            continue
        tested_level = final.high if side == "TOP" else final.low
        if not (structure.zone_low <= tested_level <= structure.zone_high):
            continue
        continuation = (
            (side == "TOP" and context.regime == "BEAR_TREND")
            or (side == "BOTTOM" and context.regime == "BULL_TREND")
        )
        name = "DOUBLE_TOP" if side == "TOP" else "DOUBLE_BOTTOM"
        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"{name}_{'BEAR_FLAG_SHORT' if side == 'TOP' and continuation else 'BULL_FLAG_LONG' if side == 'BOTTOM' and continuation else 'REVERSAL_SHORT' if side == 'TOP' else 'REVERSAL_LONG'}",
            family="TREND_CONTINUATION" if continuation else "DOUBLE_TOP_BOTTOM_REVERSAL",
            signal_index=last,
            reasons=("structural_first_test_move_away_second_test", f"{direction.lower()}_reversal_at_structural_second_test_zone",
                     f"{name.lower()}_with_trend_flag" if continuation else f"{name.lower()}_reversal_context"),
            source_rule_ids=(("BB-RNG-12-DOUBLE-TOP-BEAR-FLAG", "BB-RNG-26-TWO-REASONS") if side == "TOP" and continuation else
                             ("BB-RNG-12-DOUBLE-BOTTOM-BULL-FLAG", "BB-RNG-26-TWO-REASONS") if side == "BOTTOM" and continuation else
                             ("BB-REV-DOUBLE-TOP-BOTTOM", "BB-RNG-26-TWO-REASONS")),
            taxonomy="SOURCE_INTERPRETATION", priority=10 if continuation else 30,
            context_required=context.regime if continuation else "REVERSAL_OR_RANGE_EXTREME",
            metadata=(("structure_id",structure.structure_id),("first_test_index",str(structure.first_test_index)),
                      ("intervening_index",str(structure.intervening_index)),("second_test_index",str(structure.second_test_index)),
                      ("price_relation",structure.price_relation),("zone_low",str(structure.zone_low)),("zone_high",str(structure.zone_high)),
                      ("semantic","STRUCTURAL_SECOND_TEST_NOT_NUMERIC_EQUALITY_ONLY")),
        ))
    return tuple(out)

def detect_micro_double_top_bottom(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """BROOKS-GAP-052: consecutive or bounded nearly-consecutive micro second tests."""
    candles = snapshot.candles
    if len(candles) < 2:
        return ()
    baseline = candles[-20:] if len(candles) >= 20 else candles
    ranges = [c.high - c.low for c in baseline if c.high > c.low]
    if not ranges:
        return ()
    tolerance = median(ranges) * policy.micro_double_tolerance_fraction_of_median_range
    final = candles[-1]
    out: list[BrooksPatternCandidate] = []
    for side, direction, reversal_ok, blocked in (
        ("TOP","SHORT",_bear_reversal(final), context.regime == "BULL_TREND" and context.always_in == "LONG"),
        ("BOTTOM","LONG",_bull_reversal(final), context.regime == "BEAR_TREND" and context.always_in == "SHORT"),
    ):
        if not reversal_ok or blocked:
            continue
        structure = build_micro_double_structure(
            candles,
            side=side,
            max_bar_distance=_MICRO_DOUBLE_SEARCH_MAX_BARS,
            engineering_tolerance=tolerance
        )
        if structure is None:
            continue
        name = "MICRO_DOUBLE_TOP_SHORT" if side == "TOP" else "MICRO_DOUBLE_BOTTOM_LONG"
        out.append(BrooksPatternCandidate(
            direction=direction, setup_type=name, family="DOUBLE_TOP_BOTTOM_REVERSAL", signal_index=len(candles)-1,
            reasons=("consecutive_or_nearly_consecutive_micro_second_test", f"{direction.lower()}_reversal_on_second_micro_test", f"context_{context.regime.lower()}"),
            source_rule_ids=("BB-REV-MICRO-DOUBLE-TOP-BOTTOM", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=27, context_required="REVERSAL_OR_RANGE_EXTREME",
            metadata=(("structure_id",structure.structure_id),("first_test_index",str(structure.first_test_index)),
                      ("second_test_index",str(structure.second_test_index)),("bar_distance",str(structure.bar_distance)),
                      ("price_relation",structure.price_relation),("engineering_tolerance",str(structure.engineering_tolerance)),
                      ("search_policy","ENGINEERING_SEARCH_POLICY_BOUNDED_NEAR_CONSECUTIVE"),
                      ("canonical_entry_gap_id","BROOKS-GAP-068"),("entry_method","STOP_TRIGGER_CONFIRMATION"),
                      ("entry_trigger_semantic","REVERSAL_BAR_CONFIRMATION_AFTER_MICRO_DOUBLE"),
                      ("economic_opportunity_id",f"MICRO_DOUBLE:{structure.structure_id}:{direction}"),
                      ("entry_confirmation_state","CONFIRMED")),
        ))
    return tuple(out)

def _wedge_pushes(candles, scan, *, kind: str, policy: BrooksFullCorePolicy):
    swings=[x for x in scan.swings if x.kind==kind]
    if len(swings) < policy.wedge_push_count:
        return None
    pushes=swings[-policy.wedge_push_count:]
    if pushes[-1].candle_index-pushes[0].candle_index > policy.wedge_lookback_bars:
        return None
    recent_span=_span(candles[-policy.wedge_lookback_bars:])
    # ENGINEERING_TOLERANCE only
    eng_tol=recent_span*policy.double_test_tolerance_fraction_of_recent_range
    levels=[_swing_level(candles,x) for x in pushes]
    if kind=="HIGH" and levels[-1] < min(levels[:-1])-eng_tol:
        return None
    if kind=="LOW" and levels[-1] > max(levels[:-1])+eng_tol:
        return None
    return tuple(pushes)


def detect_wedge_reversal(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """BROOKS-GAP-053: wedge identity plus first/failed/second signal lifecycle."""
    candles=snapshot.candles
    scan=confirm_swings_causally(candles,left_bars=policy.context.swing_left_bars,right_bars=policy.context.swing_right_bars)
    last=len(candles)-1
    out=[]
    for kind,side,direction in (("HIGH","TOP","SHORT"),("LOW","BOTTOM","LONG")):
        pushes=_wedge_pushes(candles,scan,kind=kind,policy=policy)
        if pushes is None or pushes[-1].candle_index >= last:
            continue
        push_indices=tuple(x.candle_index for x in pushes)
        with_trend=(direction=="LONG" and context.regime=="BULL_TREND") or (direction=="SHORT" and context.regime=="BEAR_TREND")
        if with_trend:
            signal_ok=_bull_reversal(candles[last]) if direction=="LONG" else _bear_reversal(candles[last])
            if not signal_ok:
                continue
            wedge=classify_wedge_second_signal(candles,push_indices=push_indices,side=side,evaluated_index=last)
            setup_type="H3_WEDGE_BULL_FLAG_LONG" if direction=="LONG" else "L3_WEDGE_BEAR_FLAG_SHORT"
            family="TREND_CONTINUATION"; priority=9; requirement=context.regime
            reasons=("three_countertrend_pushes_form_wedge_flag","reversal_bar_resumes_established_trend","with_trend_wedge_flag_can_use_first_signal")
            rules=("BB-RNG-18-WEDGE-PULLBACK","BB-RNG-17-HL-BAR-COUNT","BB-RNG-26-TWO-REASONS")
            signal_identity="FIRST_SIGNAL_WITH_TREND"
        else:
            wedge=classify_wedge_second_signal(candles,push_indices=push_indices,side=side,evaluated_index=last)
            if wedge is None or wedge.first_attempt_index is None:
                continue
            current_first=wedge.first_attempt_index==last
            current_second=wedge.second_attempt_index==last
            first_strong = (
                is_strong_bull_bar(candles[wedge.first_attempt_index],policy.context)
                if direction=="LONG"
                else is_strong_bear_bar(candles[wedge.first_attempt_index],policy.context)
            )
            if not (current_second or (current_first and first_strong)):
                continue
            setup_type=f"WEDGE_REVERSAL_{direction}"; family="WEDGE_REVERSAL"; priority=28; requirement="TREND_EXTREME_OR_RANGE_EXTREME"
            signal_identity="SECOND_WEDGE_SIGNAL" if current_second else "EXCEPTIONALLY_STRONG_FIRST_WEDGE_SIGNAL"
            reasons=("three_push_wedge_identity","countertrend_wedge_signal_lifecycle_confirmed",
                     "second_signal_after_first_attempt_failure_or_resumption" if current_second else "strong_first_signal_exception")
            rules=("BB-REV-05-WEDGE-THREE-PUSH","BB-RNG-26-TWO-REASONS")
        out.append(BrooksPatternCandidate(
            direction=direction,setup_type=setup_type,family=family,signal_index=last,reasons=reasons,source_rule_ids=rules,
            taxonomy="SOURCE_INTERPRETATION",priority=priority,context_required=requirement,
            metadata=(("wedge_structure_id",wedge.wedge_structure_id),("push_indices",",".join(map(str,wedge.push_indices))),
                      ("first_attempt_index",str(wedge.first_attempt_index)),("resumption_index","" if wedge.resumption_index is None else str(wedge.resumption_index)),
                      ("second_attempt_index","" if wedge.second_attempt_index is None else str(wedge.second_attempt_index)),
                      ("signal_identity",signal_identity),("generic_second_reversal_state",wedge.state)),
        ))
    return tuple(out)


def scan_wedge_failure_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy
):
    """BROOKS-GAP-054 context: preserve exact wedge origin; no failure-of-failure promotion."""
    candles=snapshot.candles
    scan=confirm_swings_causally(candles,left_bars=policy.context.swing_left_bars,right_bars=policy.context.swing_right_bars)
    last=len(candles)-1; out=[]
    for kind,side in (("HIGH","TOP"),("LOW","BOTTOM")):
        pushes=_wedge_pushes(candles,scan,kind=kind,policy=policy)
        if pushes is None:
            continue
        wedge = classify_wedge_second_signal(
            candles,
            push_indices=tuple(x.candle_index for x in pushes),
            side=side,
            evaluated_index=last
        )
        if wedge is None or wedge.first_attempt_index is None:
            continue
        signal_number=2 if wedge.second_attempt_index is not None else 1
        origin=build_wedge_attempt_origin(candles,wedge,signal_number=signal_number,objective_level=None)
        if origin is None:
            continue
        life=evaluate_wedge_attempt_lifecycle(candles,origin,evaluated_index=last)
        rl=life.reversal_lifecycle
        out.append(BrooksPatternObservation(
            pattern_id=f"WEDGE_{side}_ATTEMPT_LIFECYCLE",
            pattern_name=f"Wedge {side.title()} Attempt Lifecycle",
            role="WEDGE_FAILURE_CONTEXT",
            signal_index=last,direction=wedge.reversal_direction,source_rule_ids=("BB-REV-05-WEDGE-THREE-PUSH",),taxonomy="SOURCE_INTERPRETATION",
            metadata=(("wedge_structure_id",wedge.wedge_structure_id),("push_indices",",".join(map(str,wedge.push_indices))),
                      ("signal_number",str(signal_number)),("attempt_id",origin.reversal_origin.attempt_id),
                      ("trigger_index","" if rl.trigger_index is None else str(rl.trigger_index)),
                      ("failure_index","" if rl.failure_index is None else str(rl.failure_index)),("lifecycle_state",rl.state),
                      ("objective_owned","false"),("failure_confirmed","true" if life.failure_confirmed else "false"),
                      ("failure_of_failure_implemented","false"),("trade_eligible","false")),
        ))
    return tuple(out)

def scan_major_trend_reversal_lifecycles(
    snapshot: MarketSnapshot,
    policy: BrooksFullCorePolicy,
):
    """Shared WAVE_08/WAVE_16 MTR lifecycle source of truth.

    Search bounds/tolerance are engineering policies.  The returned lifecycle is the
    canonical structural prior-trend -> break -> old-extreme retest -> second-reversal
    state and has no universal retest deadline.
    """
    candles = snapshot.candles
    if len(candles) < policy.mtr_lookback_bars:
        return ()
    scan = confirm_swings_causally(
        candles,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars
    )
    highs = [x for x in scan.swings if x.kind == "HIGH"]
    lows = [x for x in scan.swings if x.kind == "LOW"]
    if len(highs) < 2 or len(lows) < 2:
        return ()
    recent = candles[-policy.mtr_lookback_bars:]
    width = _span(recent)
    if width <= 0:
        return ()
    # ENGINEERING_TOLERANCE only.
    test_tolerance = width * policy.double_test_tolerance_fraction_of_recent_range
    last = len(candles) - 1

    def short_episode():
        for old_high in reversed([h for h in highs if h.candle_index < last]):
            prior_highs = [h for h in highs if h.candle_index <= old_high.candle_index][-2:]
            support_lows = [l for l in lows if l.candle_index < old_high.candle_index][-2:]
            if len(prior_highs) < 2 or len(support_lows) < 2:
                continue
            if not (prior_highs[-1].price > prior_highs[-2].price and support_lows[-1].price > support_lows[-2].price):
                continue
            if support_lows[-1].candle_index - support_lows[-2].candle_index < policy.major_trend_line_anchor_spacing_bars:
                continue
            breaks = [
                i for i in range(old_high.candle_index + 1, last + 1)
                if candles[i].close < projected_value_from_swings(support_lows[-2], support_lows[-1], i)
                and is_strong_bear_bar(candles[i], policy.context)
            ]
            if breaks:
                return old_high.candle_index, breaks[0]
        return None

    def long_episode():
        for old_low in reversed([l for l in lows if l.candle_index < last]):
            prior_lows = [l for l in lows if l.candle_index <= old_low.candle_index][-2:]
            resistance_highs = [h for h in highs if h.candle_index < old_low.candle_index][-2:]
            if len(prior_lows) < 2 or len(resistance_highs) < 2:
                continue
            if not (prior_lows[-1].price < prior_lows[-2].price and resistance_highs[-1].price < resistance_highs[-2].price):
                continue
            if resistance_highs[-1].candle_index - resistance_highs[-2].candle_index < policy.major_trend_line_anchor_spacing_bars:
                continue
            breaks = [
                i for i in range(old_low.candle_index + 1, last + 1)
                if candles[i].close > projected_value_from_swings(resistance_highs[-2], resistance_highs[-1], i)
                and is_strong_bull_bar(candles[i], policy.context)
            ]
            if breaks:
                return old_low.candle_index, breaks[0]
        return None

    out = []
    short = short_episode()
    if short is not None:
        old_extreme_index, break_index = short
        life = classify_mtr_retest_lifecycle(
            candles, prior_trend_direction="BULL_TREND", old_extreme_index=old_extreme_index,
            structure_break_index=break_index, engineering_test_tolerance=test_tolerance,
        )
        if life is not None:
            out.append(life)
    long = long_episode()
    if long is not None:
        old_extreme_index, break_index = long
        life = classify_mtr_retest_lifecycle(
            candles, prior_trend_direction="BEAR_TREND", old_extreme_index=old_extreme_index,
            structure_break_index=break_index, engineering_test_tolerance=test_tolerance,
        )
        if life is not None:
            out.append(life)
    return tuple(out)


def detect_major_trend_reversal(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """BROOKS-GAP-059 via the shared structural MTR lifecycle source of truth."""
    candles = snapshot.candles
    last = len(candles) - 1
    ema = _ema20_values(candles)
    out: list[BrooksPatternCandidate] = []
    for life in scan_major_trend_reversal_lifecycles(snapshot, policy):
        if life.second_reversal_index != last:
            continue
        break_index = life.structure_break_index
        old_extreme = (
            candles[life.old_extreme_index].high
            if life.prior_trend_direction == "BULL_TREND"
            else candles[life.old_extreme_index].low
        )
        short = life.reversal_direction == "SHORT"
        out.append(BrooksPatternCandidate(
            direction=life.reversal_direction,
            setup_type="MAJOR_TREND_REVERSAL_SHORT" if short else "MAJOR_TREND_REVERSAL_LONG",
            family="MAJOR_TREND_REVERSAL", signal_index=last,
            reasons=(
                "established_prior_bull_trend" if short else "established_prior_bear_trend",
                "significant_support_trend_line_break" if short else "significant_resistance_trend_line_break",
                "old_high_retest_same_mtr_episode" if short else "old_low_retest_same_mtr_episode",
                "second_bear_reversal_after_retest" if short else "second_bull_reversal_after_retest",
            ),
            source_rule_ids=("BB-REV-03-MAJOR-TREND-REVERSAL", "BB-RNG-26-TWO-REASONS"),
            taxonomy="SOURCE_INTERPRETATION", priority=25, context_required="REVERSAL_MATURITY",
            metadata=(
                ("mtr_episode_id", life.mtr_episode_id),
                ("structure_break_index", str(break_index)),
                ("old_extreme", str(old_extreme)),
                ("retest_index", str(life.retest_index)),
                ("second_reversal_index", str(life.second_reversal_index)),
                ("retest_bar_deadline", "none"),
                ("timing_semantic", "STRUCTURAL_LIFECYCLE_NOT_UNIVERSAL_TIMER"),
                ("ema_break", "true" if (
                    candles[break_index].close < ema[break_index] if short
                    else candles[break_index].close > ema[break_index]
                ) else "false"),
            ),
        ))
    return tuple(out)


def _exhaustion_origin_at(snapshot: MarketSnapshot, policy: BrooksFullCorePolicy, index: int):
    """BROOKS-GAP-063: mature active trend plus engineering acceleration evidence."""
    if index < 20 or index >= len(snapshot.candles):
        return None
    prefix = _snapshot_prefix(snapshot, index)
    ctx = assess_books_context(prefix, policy=policy.context)
    trend = _active_trend_episode(prefix, ctx, policy, evaluated_index=index)
    if trend is None or not trend.late_trend:
        return None
    prior = prefix.candles[max(trend.origin_index, index - 20):index]
    ranges = [c.high - c.low for c in prior if c.high > c.low]
    if not ranges:
        return None
    bar = prefix.candles[index]
    large = (bar.high - bar.low) >= median(ranges) * policy.climax_range_multiple_of_recent_median
    strong = is_strong_bull_bar(bar, policy.context) if trend.trend_direction == "BULL_TREND" else is_strong_bear_bar(bar, policy.context)
    recent = prefix.candles[max(trend.origin_index, index - policy.climax_lookback_bars + 1):index + 1]
    aligned_strong = sum(
        is_strong_bull_bar(c, policy.context) if trend.trend_direction == "BULL_TREND" else is_strong_bear_bar(c, policy.context)
        for c in recent
    )
    engineering_acceleration = large and strong and aligned_strong >= policy.climax_min_strong_bars
    return build_exhaustion_origin(
        prefix.candles,
        trend,
        origin_index=index,
        engineering_acceleration_evidence=engineering_acceleration
    )


def _latest_exhaustion_origin(snapshot: MarketSnapshot, policy: BrooksFullCorePolicy, *, before_index: int | None = None):
    end = len(snapshot.candles) - 1 if before_index is None else min(before_index, len(snapshot.candles) - 1)
    start = max(20, end - 25)  # ENGINEERING_SEARCH_POLICY only.
    for i in range(end, start - 1, -1):
        origin = _exhaustion_origin_at(snapshot, policy, i)
        if origin is not None:
            return origin
    return None


def scan_climax_lifecycle_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy
):
    """BROOKS-GAP-063/064: one origin identity, causal outcome state."""
    if len(snapshot.candles) < 21:
        return ()
    last = len(snapshot.candles) - 1
    origin = _latest_exhaustion_origin(snapshot, policy, before_index=last)
    if origin is None:
        return ()
    life = classify_climax_outcome(
        snapshot.candles, origin, current_regime=getattr(context, "regime", "AMBIGUOUS"),
        current_always_in=getattr(context, "always_in", "UNRESOLVED"), evaluated_index=last,
    )
    return (BrooksPatternObservation(
        pattern_id="CLIMAX_LIFECYCLE", pattern_name="Climax / Exhaustion Lifecycle", role="CONTEXT",
        signal_index=last, direction="SHORT" if origin.direction == "LONG" else "LONG",
        source_rule_ids=("BB-TRD-06-EXHAUSTION-BAR", "BB-REV-04-CLIMACTIC-REVERSAL"),
        metadata=(("exhaustion_id", origin.exhaustion_id), ("origin_index", str(origin.origin_index)),
                  ("trend_episode_id", origin.trend.episode_id), ("origin_state", origin.state),
                  ("outcome_state", life.state), ("transition_index", "" if life.transition_index is None else str(life.transition_index)),
                  ("reversal_attempt_index", "" if life.reversal_attempt_index is None else str(life.reversal_attempt_index)),
                  ("engineering_evidence_semantic", "SIZE_AND_STRONG_BAR_EVIDENCE_NOT_BROOKS_UNIVERSAL_RULE")),
    ),)


def detect_climactic_reversal(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """Candidate needs a prior BROOKS-GAP-063 origin plus a later reversal attempt."""
    candles = snapshot.candles
    if len(candles) < 25:
        return ()
    last = len(candles) - 1
    origin = _latest_exhaustion_origin(snapshot, policy, before_index=last - 1)
    if origin is None:
        return ()
    life = classify_climax_outcome(
        candles, origin, current_regime=getattr(context, "regime", "AMBIGUOUS"),
        current_always_in=getattr(context, "always_in", "UNRESOLVED"), evaluated_index=last,
    )
    if life.reversal_attempt_index != last:
        return ()
    final = candles[last]
    direction = "SHORT" if origin.direction == "LONG" else "LONG"
    strong = is_strong_bear_bar(final, policy.context) if direction == "SHORT" else is_strong_bull_bar(final, policy.context)
    if not strong:
        return ()
    setup = "CLIMACTIC_REVERSAL_SHORT" if direction == "SHORT" else "CLIMACTIC_REVERSAL_LONG"
    return (BrooksPatternCandidate(
        direction=direction, setup_type=setup, family="CLIMACTIC_REVERSAL", signal_index=last,
        reasons=("mature_active_trend_exhaustion_origin", "later_reversal_attempt_same_climax_origin"),
        source_rule_ids=("BB-REV-04-CLIMACTIC-REVERSAL", "BB-RNG-26-TWO-REASONS"),
        taxonomy="SOURCE_INTERPRETATION", priority=35, context_required="CLIMAX_AT_EXTREME",
        metadata=(("climax_confirmed", "true"), ("extreme_confirmed", "true"),
                  ("exhaustion_id", origin.exhaustion_id), ("exhaustion_origin_index", str(origin.origin_index)),
                  ("climax_outcome_state", life.state), ("engineering_evidence_semantic", "NOT_SIZE_ONLY")),
    ),)

def _overlap(a: Candle, b: Candle) -> Decimal:
    overlap = min(a.high, b.high) - max(a.low, b.low)
    if overlap <= 0:
        return _ZERO
    smaller = min(a.high - a.low, b.high - b.low)
    if smaller <= 0:
        return _ZERO
    return min(Decimal("1"), overlap / smaller)


def _snapshot_prefix(snapshot: MarketSnapshot, end_index: int) -> MarketSnapshot:
    items = snapshot.candles[:end_index + 1]
    return MarketSnapshot(
        exchange=snapshot.exchange, market_type=snapshot.market_type, symbol=snapshot.symbol, timeframe=snapshot.timeframe,
        candles=items, captured_at=items[-1].close_time, source=snapshot.source,
    )


def _active_trend_episode(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy, *, evaluated_index: int):
    direction = getattr(context, "regime", "AMBIGUOUS")
    if direction not in {"BULL_TREND", "BEAR_TREND"}:
        return None
    always_in = getattr(context, "always_in", "UNRESOLVED")
    aligned = "LONG" if direction == "BULL_TREND" else "SHORT"
    if always_in in {"LONG", "SHORT"} and always_in != aligned:
        return None
    candles = snapshot.candles[:evaluated_index + 1]
    scan = confirm_swings_causally(candles, left_bars=policy.context.swing_left_bars, right_bars=policy.context.swing_right_bars)
    structure = evaluate_br031_structure(scan)
    if structure.direction == direction and structure.supporting_swing_indices:
        origin = min(structure.supporting_swing_indices)
    else:
        breakout_direction = getattr(context, "breakout_direction", "UNRESOLVED")
        breakout_streak = max(1, int(getattr(context, "breakout_streak", 0) or 0))
        if breakout_direction == aligned:
            origin = max(0, evaluated_index - breakout_streak + 1)
        else:
            origin = max(0, evaluated_index - policy.context.recent_window_bars + 1)
    episode_candles = candles[origin:]
    ranges = [c.high-c.low for c in episode_candles if c.high > c.low]
    episode_span = _span(tuple(episode_candles))
    multi_push = len([x for x in scan.swings if x.candle_index >= origin and x.kind == "HIGH"]) >= 3 and len([x for x in scan.swings if x.candle_index >= origin and x.kind == "LOW"]) >= 3
    extended = bool(ranges) and episode_span >= median(ranges) * policy.final_flag_min_trend_span_multiple
    return build_active_trend_episode(trend_direction=direction, origin_index=origin, evaluated_index=evaluated_index, late_trend=multi_push or extended)


def _structural_final_flag(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """Build a flag inside the active trend episode; no universal maximum bar count."""
    candles = snapshot.candles
    if len(candles) < 4:
        return None
    flag_end = len(candles) - 2  # the final closed bar is the possible reversal signal
    prefix = _snapshot_prefix(snapshot, flag_end)
    prefix_context = assess_books_context(prefix, policy=policy.context)
    if prefix_context.regime not in {"BULL_TREND", "BEAR_TREND"} and getattr(context, "regime", None) in {"BULL_TREND", "BEAR_TREND"} and len(prefix.candles) < policy.context.context_window_bars:
        # Compatibility only for short synthetic histories; Production histories use canonical prefix context.
        prefix_context = context
    trend = _active_trend_episode(snapshot, prefix_context, policy, evaluated_index=flag_end)
    if trend is None or not trend.late_trend:
        return None
    max_length = flag_end - trend.origin_index + 1
    chosen = None
    # Longest structurally two-sided suffix wins.  Length is evidence, never a validity ceiling.
    for length in range(max_length, 1, -1):
        flag = candles[flag_end-length+1:flag_end+1]
        range_identity = assess_range_identity_evidence(tuple(flag), policy.context)
        if range_identity.composite_supported:
            chosen=(flag_end-length+1,flag_end); break
    if chosen is None:
        bar = candles[flag_end]
        prior = candles[flag_end-1]
        inside = bar.high <= prior.high and bar.low >= prior.low
        if body_fraction(bar) <= policy.context.small_body_max_fraction or inside:
            chosen=(flag_end,flag_end)
    if chosen is None:
        return None
    return build_final_flag_lifecycle(candles, trend, flag_origin_index=chosen[0], flag_end_index=chosen[1])


def scan_final_flag_context_observations(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    flag = _structural_final_flag(snapshot, context, policy)
    if flag is None:
        return ()
    direction = "SHORT" if flag.trend.trend_direction == "BULL_TREND" else "LONG"
    return (BrooksPatternObservation(
        pattern_id="ACTIVE_FINAL_FLAG_CONTEXT", pattern_name="Active Final Flag Context", role="REVERSAL_CONTEXT",
        signal_index=flag.flag_end_index, direction=direction, source_rule_ids=("BB-REV-07-FINAL-FLAG",), taxonomy="SOURCE_INTERPRETATION",
        metadata=(("final_flag_id",flag.final_flag_id),("trend_episode_id",flag.trend.episode_id),
                  ("trend_direction",flag.trend.trend_direction),("flag_bars",str(flag.bar_count)),
                  ("active_trend","true"),("trade_eligible","false")),
    ),)


def detect_final_flag(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """BROOKS-GAP-024/069: active late-trend structural flag, not stale direction or <=6 bars."""
    candles = snapshot.candles
    if len(candles) < 4:
        return ()
    flag = _structural_final_flag(snapshot, context, policy)
    if flag is None:
        return ()
    final = candles[-1]
    out=[]
    if flag.trend.trend_direction == "BULL_TREND" and is_strong_bear_bar(final, policy.context) and final.close < flag.flag_low:
        out.append(BrooksPatternCandidate(
            direction="SHORT", setup_type="FINAL_FLAG_REVERSAL_SHORT", family="FINAL_FLAG_REVERSAL", signal_index=len(candles)-1,
            reasons=("active_late_bull_trend_episode","structural_final_flag_pause","bear_breakout_reverses_from_same_flag_episode"),
            source_rule_ids=("BB-REV-07-FINAL-FLAG","BB-RNG-26-TWO-REASONS"), taxonomy="SOURCE_INTERPRETATION", priority=32,
            context_required="ACTIVE_LATE_TREND_FINAL_FLAG",
            metadata=(("final_flag_id",flag.final_flag_id),("trend_episode_id",flag.trend.episode_id),("flag_bars",str(flag.bar_count)),
                      ("active_trend","true"),("max_bar_semantic","NONE_STRUCTURAL_LIFECYCLE"),
                      ("canonical_entry_gap_id","BROOKS-GAP-068"),("entry_method","STOP_TRIGGER_CONFIRMATION"),
                      ("entry_trigger_semantic","FLAG_BREAKOUT_REVERSAL_CONFIRMATION"),
                      ("economic_opportunity_id",f"FINAL_FLAG:{flag.final_flag_id}:SHORT"),
                      ("entry_confirmation_state","CONFIRMED")),
        ))
    if flag.trend.trend_direction == "BEAR_TREND" and is_strong_bull_bar(final, policy.context) and final.close > flag.flag_high:
        out.append(BrooksPatternCandidate(
            direction="LONG", setup_type="FINAL_FLAG_REVERSAL_LONG", family="FINAL_FLAG_REVERSAL", signal_index=len(candles)-1,
            reasons=("active_late_bear_trend_episode","structural_final_flag_pause","bull_breakout_reverses_from_same_flag_episode"),
            source_rule_ids=("BB-REV-07-FINAL-FLAG","BB-RNG-26-TWO-REASONS"), taxonomy="SOURCE_INTERPRETATION", priority=32,
            context_required="ACTIVE_LATE_TREND_FINAL_FLAG",
            metadata=(("final_flag_id",flag.final_flag_id),("trend_episode_id",flag.trend.episode_id),("flag_bars",str(flag.bar_count)),
                      ("active_trend","true"),("max_bar_semantic","NONE_STRUCTURAL_LIFECYCLE"),
                      ("canonical_entry_gap_id","BROOKS-GAP-068"),("entry_method","STOP_TRIGGER_CONFIRMATION"),
                      ("entry_trigger_semantic","FLAG_BREAKOUT_REVERSAL_CONFIRMATION"),
                      ("economic_opportunity_id",f"FINAL_FLAG:{flag.final_flag_id}:LONG"),
                      ("entry_confirmation_state","CONFIRMED")),
        ))
    return tuple(out)


def scan_final_flag_failure_observations(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy):
    """Reconstruct a prior triggered final-flag attempt and preserve exact origin identity."""
    candles=snapshot.candles; last=len(candles)-1
    if last < 2: return ()
    start=max(3,last-_FINAL_FLAG_FAILURE_SEARCH_MAX_BARS)
    for signal_index in range(last-1,start-1,-1):
        prefix=_snapshot_prefix(snapshot,signal_index)
        pctx=assess_books_context(prefix,policy=policy.context)
        candidates=detect_final_flag(prefix,pctx,policy)
        for candidate in candidates:
            flag=_structural_final_flag(prefix,pctx,policy)
            if flag is None: continue
            origin=build_final_flag_attempt_origin(candles,flag,signal_index=signal_index,direction=candidate.direction,objective_level=None)
            if origin is None: continue
            life=evaluate_final_flag_attempt_lifecycle(candles,origin)
            if life.reversal_lifecycle.failure_index != last: continue
            definitive=life.failure_confirmed
            return (BrooksPatternObservation(
                pattern_id="FAILED_FINAL_FLAG" if definitive else "FINAL_FLAG_OUTCOME_CONTEXT",
                pattern_name="Failed Final Flag Lifecycle", role="FAILURE_CONTEXT", signal_index=last,
                direction="LONG" if candidate.direction=="SHORT" else "SHORT", source_rule_ids=("BB-REV-07-FINAL-FLAG","BB-REV-09-FAILURES"),
                taxonomy="SOURCE_INTERPRETATION",
                metadata=(("final_flag_id",flag.final_flag_id),("trend_episode_id",flag.trend.episode_id),
                          ("attempt_id",origin.reversal_origin.attempt_id),("origin_signal_index",str(signal_index)),
                          ("trigger_index","none" if life.reversal_lifecycle.trigger_index is None else str(life.reversal_lifecycle.trigger_index)),
                          ("failure_index",str(last)),("lifecycle_state",life.state),("failure_confirmed","true" if definitive else "false"),
                          ("failure_of_failure","false"),("trade_eligible","false")),
            ),)
    return ()


def detect_direct_trend_participation(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    """BROOKS-GAP-002/003 direct participation paths owned by these rules only."""
    if context.regime not in {"BULL_TREND","BEAR_TREND"}:
        return ()
    direction="LONG" if context.regime=="BULL_TREND" else "SHORT"
    if context.always_in != direction:
        return ()
    candles=snapshot.candles
    last=len(candles)-1
    final=candles[-1]
    strong=classify_strong_trend_evidence(candles,context,policy.context,evaluated_index=last)
    if not strong.is_strong:
        return ()
    aligned_final=final.close>final.open if direction=="LONG" else final.close<final.open
    direct_strong=is_strong_bull_bar(final,policy.context) if direction=="LONG" else is_strong_bear_bar(final,policy.context)
    out=[]
    if direct_strong:
        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"STRONG_TREND_BAR_DIRECT_ENTRY_{direction}",
            family="TREND_CONTINUATION",
            signal_index=last,
            reasons=("closed_strong_trend_bar","established_always_in_strong_trend","urgent_spike_participation"),
            source_rule_ids=("BB-TRD-SPIKE",),
            taxonomy="SOURCE_RULE",
            priority=4,
            context_required=context.regime,
            metadata=(("participation_semantic","MARKET_AT_CLOSE_OR_STOP_BEYOND_STRONG_BAR"),
                      ("strong_trend_components","EXPLICIT_COMPOSITE"),
                      ("trade_eligibility_owner","BROOKS-GAP-002"))
        ))
    # BROOKS-GAP-003 does not require a fresh pattern; however a final bar that is
    # actively opposite the established Always-In direction is not used as an urgent
    # participation timestamp. This is a fail-closed current-state distinction.
    if aligned_final or final.close==final.open:
        out.append(BrooksPatternCandidate(
            direction=direction,
            setup_type=f"ALWAYS_IN_TREND_PARTICIPATION_{direction}",
            family="TREND_CONTINUATION",
            signal_index=last,
            reasons=("established_always_in_direction","strong_trend_composite_remains_active","fresh_pattern_not_required"),
            source_rule_ids=("BB-REV-15-ALWAYS-IN",),
            taxonomy="SOURCE_RULE",
            priority=5,
            context_required=context.regime,
            metadata=(("participation_semantic","ALWAYS_IN_MARKET_PARTICIPATION_WITHOUT_FRESH_SETUP"),
                      ("trade_eligibility_owner","BROOKS-GAP-003"))
        ))
    return tuple(out)


def detect_anticipatory_reversal_entries(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternCandidate, ...]:
    """BROOKS-GAP-068: causal limit/market anticipation distinct from confirmation."""
    candles = snapshot.candles
    if len(candles) < 2:
        return ()
    final = candles[-1]
    out: list[BrooksPatternCandidate] = []

    # Micro-double anticipation: the structural second test exists now, but a
    # reversal-bar confirmation is not required for the anticipatory variant.
    baseline = candles[-20:] if len(candles) >= 20 else candles
    ranges = [c.high - c.low for c in baseline if c.high > c.low]
    if ranges:
        tolerance = median(ranges) * policy.micro_double_tolerance_fraction_of_median_range
        for side, direction, blocked in (
            ("TOP", "SHORT", context.regime == "BULL_TREND" and context.always_in == "LONG"),
            ("BOTTOM", "LONG", context.regime == "BEAR_TREND" and context.always_in == "SHORT"),
        ):
            if blocked:
                continue
            structure = build_micro_double_structure(
                candles, side=side, max_bar_distance=_MICRO_DOUBLE_SEARCH_MAX_BARS,
                engineering_tolerance=tolerance,
            )
            if structure is None or structure.second_test_index != len(candles)-1:
                continue
            already_confirmed = _bear_reversal(final) if direction == "SHORT" else _bull_reversal(final)
            if already_confirmed:
                continue
            reference = structure.second_level
            out.append(BrooksPatternCandidate(
                direction=direction,
                setup_type=f"MICRO_DOUBLE_{'TOP' if side=='TOP' else 'BOTTOM'}_ANTICIPATORY_{direction}",
                family="DOUBLE_TOP_BOTTOM_REVERSAL",
                signal_index=len(candles)-1,
                reasons=(
                    "micro_double_second_test_structure_present",
                    "source_allows_limit_or_market_anticipation_before_stop_confirmation",
                    f"context_{context.regime.lower()}",
                ),
                source_rule_ids=("BB-REV-MICRO-DOUBLE-TOP-BOTTOM","BB-RNG-26-TWO-REASONS"),
                taxonomy="SOURCE_INTERPRETATION", priority=28,
                context_required="REVERSAL_OR_RANGE_EXTREME",
                metadata=(
                    ("canonical_gap_id","BROOKS-GAP-068"),("structure_id",structure.structure_id),
                    ("first_test_index",str(structure.first_test_index)),("second_test_index",str(structure.second_test_index)),
                    ("entry_method","LIMIT_OR_MARKET_ANTICIPATION"),
                    ("entry_trigger_semantic","MICRO_DOUBLE_SECOND_TEST_ANTICIPATION"),
                    ("entry_reference_price",str(reference)),
                    ("economic_opportunity_id",f"MICRO_DOUBLE:{structure.structure_id}:{direction}"),
                    ("entry_confirmation_state","ANTICIPATORY_UNCONFIRMED"),
                    ("engineering_policy","STRUCTURAL_SECOND_TEST_REFERENCE_NO_FIXED_ANTICIPATION_OFFSET"),
                ),
            ))

    # Final-flag anticipation: require the already-canonical active final-flag
    # episode plus an opposite reversal minimum, but not the later flag breakout.
    flag = _structural_final_flag(snapshot, context, policy)
    if flag is not None and flag.flag_end_index == len(candles)-2:
        if flag.trend.trend_direction == "BULL_TREND":
            direction="SHORT"; reversal_ok=_bear_reversal(final); confirmed=final.close < flag.flag_low
        else:
            direction="LONG"; reversal_ok=_bull_reversal(final); confirmed=final.close > flag.flag_high
        if reversal_ok and not confirmed:
            out.append(BrooksPatternCandidate(
                direction=direction,
                setup_type=f"FINAL_FLAG_ANTICIPATORY_{direction}",
                family="FINAL_FLAG_REVERSAL",
                signal_index=len(candles)-1,
                reasons=(
                    "active_final_flag_origin_preserved",
                    "opposite_reversal_minimum_before_breakout_confirmation",
                    "source_allows_limit_or_market_anticipation",
                ),
                source_rule_ids=("BB-REV-07-FINAL-FLAG","BB-RNG-26-TWO-REASONS"),
                taxonomy="SOURCE_INTERPRETATION", priority=33,
                context_required="ACTIVE_LATE_TREND_FINAL_FLAG",
                metadata=(
                    ("canonical_gap_id","BROOKS-GAP-068"),("final_flag_id",flag.final_flag_id),
                    ("trend_episode_id",flag.trend.episode_id),("active_trend","true"),
                    ("entry_method","MARKET_OR_LIMIT_ANTICIPATION"),
                    ("entry_trigger_semantic","FINAL_FLAG_OPPOSITE_REVERSAL_MINIMUM_BEFORE_BREAKOUT"),
                    ("entry_reference_price",str(final.close)),
                    ("economic_opportunity_id",f"FINAL_FLAG:{flag.final_flag_id}:{direction}"),
                    ("entry_confirmation_state","ANTICIPATORY_UNCONFIRMED"),
                    ("engineering_policy","CURRENT_CLOSED_BAR_PRICE_NO_FIXED_ANTICIPATION_OFFSET"),
                ),
            ))
    return tuple(out)


def _attach_multitimeframe_nesting(candidate: BrooksPatternCandidate, market_context):
    """WAVE_16 context plumbing only; never creates a second economic opportunity."""
    if market_context is None:
        return candidate
    metadata = list(candidate.metadata)
    existing = {k for k, _ in metadata}
    def add(key: str, value: str) -> None:
        if key not in existing:
            metadata.append((key, value))
            existing.add(key)

    add("current_tf_pattern", candidate.setup_type)
    add("current_tf_signal_index", str(candidate.signal_index))

    link_fn = getattr(market_context, "multitimeframe_links", None)
    links = tuple(link_fn(candidate.setup_type, candidate.signal_index, candidate.direction)) if callable(link_fn) else ()
    if links:
        add("htf_parent_link_ids", "|".join(x.link_id for x in links))
        add("htf_parent_pattern_ids", "|".join(x.parent_pattern_id for x in links))
        add("htf_parent_context_ids", "|".join(x.parent_context_id for x in links))
        add("htf_parent_timeframes", "|".join(x.parent_timeframe for x in links))

    fb_fn = getattr(market_context, "candidate_htf_failed_breakout_contexts", None)
    fb = tuple(fb_fn(candidate.direction)) if callable(fb_fn) else ()
    if fb:
        add("htf_failed_breakout_ids", "|".join(x.context_id for x in fb))
        add("htf_failed_breakout_origin_ids", "|".join(x.breakout_origin_id for x in fb))

    test_fn = getattr(market_context, "htf_swing_test_contexts", None)
    tests = tuple(test_fn()) if callable(test_fn) else ()
    if tests:
        add("htf_swing_test_ids", "|".join(x.context_id for x in tests))

    mtr_fn = getattr(market_context, "candidate_htf_mtr_contexts", None)
    mtr = tuple(mtr_fn(candidate.direction)) if callable(mtr_fn) else ()
    if mtr:
        add("htf_mtr_context_ids", "|".join(x.context_id for x in mtr))
        add("htf_mtr_episode_ids", "|".join(x.mtr_episode_id for x in mtr))
        add("htf_mtr_states", "|".join(x.state for x in mtr))

    return replace(candidate, metadata=tuple(metadata))


def scan_chapter6_diagnostic_observations(
    snapshot: MarketSnapshot,
    context,
    policy: BrooksFullCorePolicy,
) -> tuple[BrooksPatternObservation, ...]:
    """Causal Chapter 6 context with no rule credit or trade eligibility."""
    candles = snapshot.candles
    end = len(candles) - 1
    final = candles[end]
    observations: list[BrooksPatternObservation] = []

    if end >= 1:
        previous = candles[end - 1]
        bull = is_strong_bear_bar(previous, policy.context) and is_strong_bull_bar(
            final, policy.context
        )
        bear = is_strong_bull_bar(previous, policy.context) and is_strong_bear_bar(
            final, policy.context
        )
        if bull or bear:
            direction = "LONG" if bull else "SHORT"
            overlap = max(previous.low, final.low) < min(previous.high, final.high)
            observations.append(
                BrooksPatternObservation(
                    pattern_id=f"CH6:TWO_BAR:{end - 1}:{end}:{direction}",
                    pattern_name="CH6_TWO_BAR_PAIR",
                    role="DIAGNOSTIC_ONLY",
                    signal_index=end,
                    direction=direction,
                    source_rule_ids=(),
                    metadata=(
                        ("pair_identity", f"TWO_BAR_REVERSAL:{end - 1}:{end}:{direction}"),
                        ("first_index", str(end - 1)),
                        ("second_index", str(end)),
                        ("first_high", str(previous.high)),
                        ("first_low", str(previous.low)),
                        ("second_high", str(final.high)),
                        ("second_low", str(final.low)),
                        ("pair_high", str(max(previous.high, final.high))),
                        ("pair_low", str(min(previous.low, final.low))),
                        ("ranges_overlap", str(overlap).lower()),
                        ("context_regime", context.regime),
                        ("trade_eligible", "false"),
                    ),
                )
            )

    baseline = candles[-20:]
    ranges = [item.high - item.low for item in baseline if item.high > item.low]
    if end >= 1 and ranges:
        tolerance = median(ranges) * policy.micro_double_tolerance_fraction_of_median_range
        lifecycle = classify_spike_channel_lifecycle(snapshot, policy, evaluated_index=end)
        for side, reversal_direction, trend_regime in (
            ("TOP", "SHORT", "BULL_TREND"),
            ("BOTTOM", "LONG", "BEAR_TREND"),
        ):
            structure = build_micro_double_structure(
                candles,
                side=side,
                max_bar_distance=_MICRO_DOUBLE_SEARCH_MAX_BARS,
                engineering_tolerance=tolerance,
            )
            if structure is None:
                continue
            trend_direction = "LONG" if side == "TOP" else "SHORT"
            spike_active = bool(
                lifecycle is not None
                and lifecycle.direction == trend_direction
                and lifecycle.state == "SPIKE_ACTIVE"
            )
            continuation = (
                spike_active
                and context.regime == trend_regime
                and context.always_in == trend_direction
            )
            role = (
                "SPIKE_CONTINUATION_CONTEXT"
                if continuation
                else "POSSIBLE_REVERSAL_CONTEXT"
            )
            observations.append(
                BrooksPatternObservation(
                    pattern_id=f"CH6:MICRO_DOUBLE:{structure.structure_id}:{side}",
                    pattern_name=f"CH6_MICRO_DOUBLE_{side}_CONTEXT",
                    role="DIAGNOSTIC_ONLY",
                    signal_index=end,
                    direction=reversal_direction,
                    source_rule_ids=(),
                    metadata=(
                        ("structure_id", structure.structure_id),
                        ("first_test_index", str(structure.first_test_index)),
                        ("second_test_index", str(structure.second_test_index)),
                        ("bar_distance", str(structure.bar_distance)),
                        ("contextual_role", role),
                        ("spike_state", lifecycle.state if lifecycle else "NO_SPIKE"),
                        ("context_regime", context.regime),
                        ("search_policy", "ENGINEERING_SEARCH_POLICY_BOUNDED_NEAR_CONSECUTIVE"),
                        ("trade_eligible", "false"),
                    ),
                )
            )

    shaved_top = final.high == max(final.open, final.close)
    shaved_bottom = final.low == min(final.open, final.close)
    if shaved_top or shaved_bottom:
        direction = (
            "LONG" if final.close > final.open
            else "SHORT" if final.close < final.open
            else "UNRESOLVED"
        )
        trend_regime = "BULL_TREND" if direction == "LONG" else "BEAR_TREND"
        strong = (
            direction != "UNRESOLVED"
            and context.regime == trend_regime
            and classify_strong_trend_evidence(
                candles, context, policy.context, evaluated_index=end
            ).is_strong
        )
        qualification = (
            "STRONG_MATCHING_TREND" if strong
            else "TRADING_RANGE_GEOMETRY" if context.regime == "TRADING_RANGE"
            else "UNQUALIFIED_GEOMETRY"
        )
        observations.append(
            BrooksPatternObservation(
                pattern_id=f"CH6:SHAVED:{end}:{direction}",
                pattern_name="CH6_SHAVED_BAR_CONTEXT",
                role="DIAGNOSTIC_ONLY",
                signal_index=end,
                direction=direction,
                source_rule_ids=(),
                metadata=(
                    ("shaved_top", str(shaved_top).lower()),
                    ("shaved_bottom", str(shaved_bottom).lower()),
                    ("context_qualification", qualification),
                    ("context_regime", context.regime),
                    ("trade_eligible", "false"),
                ),
            )
        )
    return tuple(observations)


def scan_full_brooks_patterns(snapshot: MarketSnapshot, context, policy: BrooksFullCorePolicy, market_context=None) -> BrooksPatternScan:
    candidates: list[BrooksPatternCandidate] = []
    candidates.extend(detect_direct_trend_participation(snapshot, context, policy))
    extended = scan_extended_patterns(snapshot, context, policy, market_context)
    candidates.extend(extended.candidates)
    wedge_observations = scan_wedge_failure_observations(snapshot, context, policy)
    final_flag_observations = scan_final_flag_context_observations(snapshot, context, policy) + scan_final_flag_failure_observations(snapshot, context, policy)
    climax_observations = scan_climax_lifecycle_observations(snapshot, context, policy)

    chapter6_observations = scan_chapter6_diagnostic_observations(snapshot, context, policy)

    h2l2 = detect_trend_second_entry(snapshot, context, policy)
    if h2l2 is not None:
        candidates.append(h2l2)

    candidates.extend(detect_breakout_family(snapshot, context, policy))
    candidates.extend(detect_trading_range_fades(snapshot, context, policy, market_context))
    candidates.extend(detect_double_top_bottom(snapshot, context, policy))
    candidates.extend(detect_micro_double_top_bottom(snapshot, context, policy))
    candidates.extend(detect_wedge_reversal(snapshot, context, policy))
    candidates.extend(detect_major_trend_reversal(snapshot, context, policy))
    candidates.extend(detect_climactic_reversal(snapshot, context, policy))
    candidates.extend(detect_final_flag(snapshot, context, policy))
    candidates.extend(detect_anticipatory_reversal_entries(snapshot, context, policy))

    # Deduplicate exact family/direction/signal combinations.  Multiple source reasons
    # can point to the same setup; the family remains one auditable candidate.
    unique = {}
    for raw_item in candidates:
        item = _attach_multitimeframe_nesting(raw_item, market_context)
        key = (item.family, item.direction, item.signal_index, item.setup_type)
        unique.setdefault(key, item)

    ordered = tuple(
        sorted(
            unique.values(),
            key=lambda c: (c.priority, -len(c.reasons), -c.signal_index, c.setup_type),
        )
    )
    return BrooksPatternScan(
        candidates=ordered,
        observations=(
            extended.observations + wedge_observations + final_flag_observations
            + climax_observations + chapter6_observations
        ),
        diagnostics=(
            ("candidate_count", str(len(ordered))),
            ("observation_count", str(
                len(extended.observations) + len(wedge_observations)
                + len(final_flag_observations) + len(climax_observations)
                + len(chapter6_observations)
            )),
            ("context_regime", context.regime),
            ("structure_direction", context.structure_direction),
        ),
    )
