"""Pure translation and missing-concept rules for Brooks knowledge extraction."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from statistics import median

from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate, BrooksPatternObservation
from app.modules.brooks_core.books_full_patterns import detect_final_flag
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import assess_books_context, is_strong_bear_bar, is_strong_bull_bar
from app.modules.brooks_core.higher_probability import assess_higher_probability as legacy_probability_band
from app.modules.market_data.entities import MarketSnapshot

from .entities import Bias, FindingState, KnowledgeCategory, KnowledgeFinding, ProbabilityBand, SessionAnchor
from .source_registry import rule_origin


def bias_from_direction(direction: str) -> Bias:
    value = str(direction or '').upper()
    if value == 'LONG':
        return Bias.BULLISH
    if value == 'SHORT':
        return Bias.BEARISH
    return Bias.NEUTRAL if value in {'NEUTRAL', 'TRADING_RANGE'} else Bias.UNRESOLVED


def _finding(rule_id: str, concept: str, category: KnowledgeCategory, index: int, *,
             bias: Bias = Bias.NEUTRAL, state: FindingState = FindingState.DETECTED,
             evidence: tuple[tuple[str, str], ...] = (),
             probability_band: ProbabilityBand | None = None) -> KnowledgeFinding:
    return KnowledgeFinding(rule_id, concept, category, state, bias, index, rule_origin(rule_id), evidence, probability_band)


def observation_findings(item: BrooksPatternObservation) -> tuple[KnowledgeFinding, ...]:
    role = item.role.upper()
    pid = item.pattern_id.upper()
    state = FindingState.NOT_APPLICABLE if role.startswith('NOT_APPLICABLE') else FindingState.DETECTED
    if state is FindingState.NOT_APPLICABLE:
        category = KnowledgeCategory.EVIDENCE
    elif 'FAILURE' in role or pid.startswith('FAILED_'):
        category = KnowledgeCategory.FAILURE
    elif 'CHANNEL' in pid or 'CHANNEL' in item.pattern_name.upper():
        category = KnowledgeCategory.CHANNEL
    elif pid in {'BULL_SPIKE', 'BEAR_SPIKE'}:
        category = KnowledgeCategory.PRESSURE
    elif 'TRADING_RANGE' in pid or pid in {'TRIANGLE', 'TIGHT_TRADING_RANGE'}:
        category = KnowledgeCategory.RANGE
    elif 'TREND' in role:
        category = KnowledgeCategory.TREND
    elif 'CONTEXT' in role:
        category = KnowledgeCategory.CONTEXT
    elif 'ENTRY' in role or 'BREAKOUT_MODE' in role:
        category = KnowledgeCategory.ENTRY
    else:
        category = KnowledgeCategory.STRUCTURE
    if item.pattern_id == 'NESTED_IOI':
        rid = 'BB-TRD-06-NESTED-IOI'
    elif item.pattern_id == 'OPENING_SWING':
        rid = 'BB-REV-19-OPENING-SWING'
    else:
        rid = item.source_rule_ids[0] if item.source_rule_ids else 'BB-TRD-04-CANDLE-PATTERNS'
    evidence = (("pattern_id", item.pattern_id), ("role", item.role), *item.metadata)
    result=[_finding(rid, item.pattern_name, category, item.signal_index, bias=bias_from_direction(item.direction), state=state, evidence=evidence)]
    if any(key in item.pattern_id for key in ('FAILED_', 'FAILURE')):
        result.append(_finding(rid, item.pattern_name, KnowledgeCategory.TRAP, item.signal_index, bias=bias_from_direction(item.direction), state=state, evidence=evidence))
    return tuple(result)


def candidate_findings(item: BrooksPatternCandidate, context, advanced=None) -> tuple[KnowledgeFinding, ...]:
    bias = bias_from_direction(item.direction)
    primary = item.source_rule_ids[0]
    evidence=(("setup_type", item.setup_type), ("family", item.family), ("taxonomy", item.taxonomy), ("reasons", " | ".join(item.reasons)), *item.metadata)
    findings=[_finding(primary, item.setup_type, KnowledgeCategory.STRUCTURE, item.signal_index, bias=bias, evidence=evidence)]
    findings.append(_finding(primary, item.setup_type, KnowledgeCategory.ENTRY, item.signal_index, bias=bias, evidence=evidence))
    if item.family in {'FAILED_BREAKOUT','FAILED_FAILURE'} or 'FAIL' in item.setup_type:
        findings.append(_finding(primary, item.setup_type, KnowledgeCategory.FAILURE, item.signal_index, bias=bias, evidence=evidence))
        findings.append(_finding(primary, item.setup_type, KnowledgeCategory.TRAP, item.signal_index, bias=bias, evidence=evidence))
    if item.family == 'TRADING_RANGE_FADE':
        findings.append(_finding(primary, 'Trading Range', KnowledgeCategory.RANGE, item.signal_index, bias=Bias.NEUTRAL, evidence=evidence))
    if item.family == 'TREND_CONTINUATION':
        findings.append(_finding(primary, 'Trend Continuation', KnowledgeCategory.TREND, item.signal_index, bias=bias, evidence=evidence))
    legacy = legacy_probability_band(item, context, advanced)
    band = {'HIGHER': ProbabilityBand.HIGHER, 'NORMAL': ProbabilityBand.BALANCED, 'LOWER': ProbabilityBand.LOWER}.get(legacy.band.value, ProbabilityBand.UNRESOLVED)
    findings.append(_finding(primary, f'Source-relative probability: {item.setup_type}', KnowledgeCategory.PROBABILITY, item.signal_index, bias=bias, evidence=(("basis", "BROOKS_CONTEXT_RELATIVE_NOT_CALIBRATED"), ("reasons", " | ".join(legacy.reasons))), probability_band=band))
    for rid in item.source_rule_ids:
        if rid in {'BB-RNG-26-TWO-REASONS', 'BB-RNG-29-SIGNAL-BAR-STOP'}:
            # Trade-selection/execution principles are audited but intentionally excluded
            # from market-truth output. They are not observable market structures.
            continue
        findings.append(_finding(rid, rule_origin(rid).concept, KnowledgeCategory.EVIDENCE, item.signal_index, bias=bias, evidence=evidence))
    return tuple(findings)


def context_findings(snapshot: MarketSnapshot, context, advanced) -> tuple[KnowledgeFinding, ...]:
    last=len(snapshot.candles)-1
    out=[]
    regime_bias = Bias.BULLISH if context.regime == 'BULL_TREND' else Bias.BEARISH if context.regime == 'BEAR_TREND' else Bias.NEUTRAL
    out.append(_finding('BB-RNG-CTX-TREND-VS-RANGE', context.regime, KnowledgeCategory.CONTEXT, last, bias=regime_bias, evidence=(("reason", context.reason),)))
    if context.regime in {'BULL_TREND','BEAR_TREND'}:
        out.append(_finding('BB-TRD-19-TREND-STRENGTH', context.regime, KnowledgeCategory.TREND, last, bias=regime_bias, evidence=(("reason", context.reason),)))
    if context.regime == 'TRADING_RANGE':
        range_rule = 'BB-RNG-22-TIGHT-RANGE' if context.metrics.tight_range_like else 'BB-RNG-21-BUY-LOW-SELL-HIGH'
        out.append(_finding(range_rule, 'Trading Range', KnowledgeCategory.RANGE, last, evidence=(("reason", context.reason),)))
        out.append(_finding(range_rule, 'Trading Range Directional Probability', KnowledgeCategory.PROBABILITY, last, evidence=(("basis", 'TWO_SIDED_UNCERTAINTY_NOT_CALIBRATED'),), probability_band=ProbabilityBand.BALANCED))
    if context.always_in in {'LONG','SHORT'}:
        ai_bias = bias_from_direction(context.always_in)
        ai_data=(("breakout_direction", context.breakout_direction), ("breakout_streak", str(context.breakout_streak)))
        out.append(_finding('BB-REV-15-ALWAYS-IN', 'Always In', KnowledgeCategory.PRESSURE, last, bias=ai_bias, evidence=ai_data))
        out.append(_finding('BB-REV-15-ALWAYS-IN', 'Always-In Directional Probability', KnowledgeCategory.PROBABILITY, last, bias=ai_bias, evidence=(("basis", 'SOURCE_RELATIVE_DIRECTIONAL_BIAS_NOT_CALIBRATED'),), probability_band=ProbabilityBand.HIGHER))
    if advanced.tight_channel_direction in {'LONG','SHORT'}:
        out.append(_finding('BB-TRD-TIGHT-CHANNEL', 'Tight Channel', KnowledgeCategory.CHANNEL, last, bias=bias_from_direction(advanced.tight_channel_direction)))
    if advanced.spike_channel_direction in {'LONG','SHORT'}:
        out.append(_finding('BB-TRD-SPIKE-CHANNEL', 'Spike and Channel', KnowledgeCategory.CHANNEL, last, bias=bias_from_direction(advanced.spike_channel_direction)))
    if advanced.measured_move_target is not None:
        out.append(_finding('BB-TRD-MEASURED-MOVE', 'Measured Move', KnowledgeCategory.CONTEXT, last, bias=bias_from_direction(advanced.measured_move_direction), evidence=(("target", str(advanced.measured_move_target)), ("semantics", "MAGNET_NOT_TRADE_TARGET"))))
    return tuple(out)


def detect_successful_breakout(snapshot: MarketSnapshot, context) -> tuple[KnowledgeFinding, ...]:
    if context.breakout_direction not in {'LONG','SHORT'} or context.breakout_streak < 2:
        return ()
    last=len(snapshot.candles)-1
    bias=bias_from_direction(context.breakout_direction)
    data=(("follow_through_bars", str(context.breakout_streak)), ("regime", context.regime), ("semantics", "SUCCESSFUL_BREAKOUT_AS_SPIKE"))
    return (
        _finding('BB-RNG-02-SUCCESSFUL-BREAKOUT', 'Successful Breakout', KnowledgeCategory.STRUCTURE, last, bias=bias, evidence=data, probability_band=ProbabilityBand.HIGHER),
        _finding('BB-RNG-02-SUCCESSFUL-BREAKOUT', 'Successful Breakout Pressure', KnowledgeCategory.PRESSURE, last, bias=bias, evidence=data),
        _finding('BB-RNG-02-SUCCESSFUL-BREAKOUT', 'Successful Breakout Probability', KnowledgeCategory.PROBABILITY, last, bias=bias, evidence=(("basis", "STRONG_BREAKOUT_PLUS_FOLLOW_THROUGH"),), probability_band=ProbabilityBand.HIGHER),
    )


def detect_nested_trading_range(snapshot: MarketSnapshot) -> tuple[KnowledgeFinding, ...]:
    candles=snapshot.candles
    if len(candles) < 40:
        return ()
    outer=candles[-40:]
    inner=candles[-10:]
    outer_hi=max(c.high for c in outer); outer_lo=min(c.low for c in outer)
    inner_hi=max(c.high for c in inner); inner_lo=min(c.low for c in inner)
    outer_span=outer_hi-outer_lo; inner_span=inner_hi-inner_lo
    if outer_span <= 0:
        return ()
    # Engineering detector for Brooks' explicit semantic: a smaller range inside a larger range.
    contained=inner_hi < outer_hi and inner_lo > outer_lo
    materially_smaller=inner_span <= outer_span * Decimal('0.60')
    if not (contained and materially_smaller):
        return ()
    return (_finding('BB-RNG-02-NESTED-TRADING-RANGE', 'Small Trading Range Within Larger Trading Range', KnowledgeCategory.RANGE, len(candles)-1, evidence=(("outer_span", str(outer_span)), ("inner_span", str(inner_span)), ("threshold", "ENGINEERING_INTERPRETATION_0.60"))),)


def _prefix(snapshot: MarketSnapshot, end_exclusive: int) -> MarketSnapshot | None:
    candles=snapshot.candles[:end_exclusive]
    if not candles:
        return None
    return MarketSnapshot(exchange=snapshot.exchange, market_type=snapshot.market_type, symbol=snapshot.symbol, timeframe=snapshot.timeframe, candles=candles, captured_at=candles[-1].close_time, source='KNOWLEDGE_PREFIX')


def detect_final_flag_failure(snapshot: MarketSnapshot, policy: BrooksFullCorePolicy) -> tuple[KnowledgeFinding, ...]:
    if len(snapshot.candles) < 27:
        return ()
    prior=_prefix(snapshot, len(snapshot.candles)-1)
    if prior is None:
        return ()
    prior_context=assess_books_context(prior, policy=policy.context)
    prior_flags=detect_final_flag(prior, prior_context, policy)
    if not prior_flags:
        return ()
    final=snapshot.candles[-1]; prior_bar=snapshot.candles[-2]
    out=[]
    for flag in prior_flags:
        original='LONG' if flag.direction == 'SHORT' else 'SHORT'
        resumed=(is_strong_bull_bar(final, policy.context) and final.close > prior_bar.high) if original == 'LONG' else (is_strong_bear_bar(final, policy.context) and final.close < prior_bar.low)
        if not resumed:
            continue
        bias=bias_from_direction(original)
        data=(("failed_reversal", flag.setup_type), ("original_trend", original), ("semantics", "FAILED_FINAL_FLAG_BECOMES_TREND_RESUMPTION_BREAKOUT_PULLBACK"))
        out.append(_finding('BB-REV-07-FINAL-FLAG-FAILURE', 'Failed Final Flag', KnowledgeCategory.FAILURE, len(snapshot.candles)-1, bias=bias, evidence=data))
        out.append(_finding('BB-REV-07-FINAL-FLAG-FAILURE', 'Failed Final Flag Trap', KnowledgeCategory.TRAP, len(snapshot.candles)-1, bias=bias, evidence=data))
    return tuple(out)


def detect_always_in_failure(snapshot: MarketSnapshot, policy: BrooksFullCorePolicy) -> tuple[KnowledgeFinding, ...]:
    if len(snapshot.candles) < max(policy.context.context_window_bars + 2, 22):
        return ()
    base=_prefix(snapshot, len(snapshot.candles)-2)
    if base is None:
        return ()
    base_context=assess_books_context(base, policy=policy.context)
    if base_context.always_in not in {'LONG','SHORT'}:
        return ()
    attempt=snapshot.candles[-2]; final=snapshot.candles[-1]
    original=base_context.always_in
    failed=False
    if original == 'LONG':
        failed=is_strong_bear_bar(attempt, policy.context) and not is_strong_bear_bar(final, policy.context) and final.close > attempt.close
    else:
        failed=is_strong_bull_bar(attempt, policy.context) and not is_strong_bull_bar(final, policy.context) and final.close < attempt.close
    if not failed:
        return ()
    data=(("prior_always_in", original), ("attempt_bar_index", str(len(snapshot.candles)-2)), ("semantics", "OPPOSITE_SPIKE_WITHOUT_REQUIRED_FOLLOW_THROUGH"))
    bias=bias_from_direction(original)
    return (
        _finding('BB-REV-15-ALWAYS-IN-FAILURE', 'Failed Always-In Flip Attempt', KnowledgeCategory.FAILURE, len(snapshot.candles)-1, bias=bias, evidence=data),
        _finding('BB-REV-15-ALWAYS-IN-FAILURE', 'Always-In Trap', KnowledgeCategory.TRAP, len(snapshot.candles)-1, bias=bias, evidence=data),
    )


def opening_session_findings(
    snapshot: MarketSnapshot,
    policy: BrooksFullCorePolicy,
    session: SessionAnchor | None,
) -> tuple[KnowledgeFinding, ...]:
    """Detect opening reversal/swing only when an explicit session anchor is supplied.

    The first-hour time window is source semantics. Strong-bar thresholds are the same
    versioned engineering proxies used elsewhere in the Brooks core.
    """
    last=len(snapshot.candles)-1
    if session is None:
        reason=(("reason", "NO_EXPLICIT_SESSION_OPEN_ANCHOR_IN_MARKET_SNAPSHOT"),)
        return (
            _finding('BB-REV-19-OPENING-REVERSAL', 'Opening Reversal', KnowledgeCategory.EVIDENCE, last, state=FindingState.NOT_APPLICABLE, evidence=reason),
            _finding('BB-REV-19-OPENING-SWING', 'Opening Swing', KnowledgeCategory.EVIDENCE, last, state=FindingState.NOT_APPLICABLE, evidence=reason),
        )
    session_end=session.open_time + timedelta(hours=1)
    indexed=[(i,c) for i,c in enumerate(snapshot.candles) if session.open_time <= c.open_time < session_end]
    if len(indexed) < 2:
        reason=(("reason", "INSUFFICIENT_CLOSED_BARS_IN_FIRST_HOUR"), ("session", session.label))
        return (
            _finding('BB-REV-19-OPENING-REVERSAL', 'Opening Reversal', KnowledgeCategory.EVIDENCE, last, state=FindingState.UNRESOLVED, evidence=reason),
            _finding('BB-REV-19-OPENING-SWING', 'Opening Swing', KnowledgeCategory.EVIDENCE, last, state=FindingState.UNRESOLVED, evidence=reason),
        )

    first_index, first=indexed[0]
    initial='LONG' if is_strong_bull_bar(first, policy.context) else 'SHORT' if is_strong_bear_bar(first, policy.context) else None
    if initial is None and len(indexed) >= 3:
        a=indexed[0][1]; b=indexed[1][1]
        if a.close > a.open and b.close > b.open:
            initial='LONG'
        elif a.close < a.open and b.close < b.open:
            initial='SHORT'
    if initial is None:
        return ()

    reversal=None
    for pos in range(1,len(indexed)):
        i,c=indexed[pos]; prev=indexed[pos-1][1]
        if initial == 'LONG':
            strong=is_strong_bear_bar(c, policy.context)
            trigger=c.close < prev.low
            bias=Bias.BEARISH
        else:
            strong=is_strong_bull_bar(c, policy.context)
            trigger=c.close > prev.high
            bias=Bias.BULLISH
        if strong and trigger:
            reversal=(pos,i,c,bias); break
    if reversal is None:
        return ()
    pos,i,c,bias=reversal
    data=(("session", session.label), ("session_open", session.open_time.isoformat()), ("initial_pressure", initial), ("reversal_index", str(i)), ("basis", "FIRST_HOUR_SHARP_REVERSAL_WITH_STRONG_OPPOSITE_BAR"))
    out=[_finding('BB-REV-19-OPENING-REVERSAL','Opening Reversal',KnowledgeCategory.STRUCTURE,i,bias=bias,evidence=data)]
    # Brooks treats strong opening reversals with follow-through as the better swing cases.
    if pos + 1 < len(indexed):
        follow=indexed[pos+1][1]
        follow_ok=(follow.close < c.low if bias is Bias.BEARISH else follow.close > c.high) or (is_strong_bear_bar(follow, policy.context) if bias is Bias.BEARISH else is_strong_bull_bar(follow, policy.context))
        if follow_ok:
            swing_data=data+(("follow_through_index", str(indexed[pos+1][0])), ("probability_semantics", "SOURCE_RELATIVE_NOT_CALIBRATED"))
            out.append(_finding('BB-REV-19-OPENING-SWING','Opening Swing',KnowledgeCategory.STRUCTURE,indexed[pos+1][0],bias=bias,evidence=swing_data))
            out.append(_finding('BB-REV-19-OPENING-SWING','Opening Swing Probability',KnowledgeCategory.PROBABILITY,indexed[pos+1][0],bias=bias,evidence=(("basis", "STRONG_OPENING_REVERSAL_PLUS_FOLLOW_THROUGH"),),probability_band=ProbabilityBand.HIGHER))
    return tuple(out)


def opening_swing_unavailable(snapshot: MarketSnapshot) -> KnowledgeFinding:
    # Backward-compatible helper retained for focused callers/tests.
    return opening_session_findings(snapshot, BrooksFullCorePolicy(), None)[1]
