"""Comprehensive Brooks context built only from causally closed candles.

Numeric likelihoods here are ENGINEERING_CONTEXT_LIKELIHOOD values, not claims that
Al Brooks supplied calibrated probabilities. Outcome probability is handled separately.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median

from app.modules.brooks_core.advanced_context import assess_advanced_context
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.books_entities import RangeHierarchyContext
from app.modules.brooks_core.causal_structure import confirm_swings_causally, evaluate_br031_structure
from app.modules.brooks_core.context_classifier import (
    assess_books_context,
    assess_range_hierarchy,
    assess_range_identity_evidence,
    classify_tight_trading_range,
    classify_barbwire_identity,
    classify_broad_trading_range,
    classify_local_breakout_vs_enclosing,
)
from app.modules.market_data.entities import Candle, MarketSnapshot, TIMEFRAME_SECONDS

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _clamp(value: Decimal) -> Decimal:
    return min(_ONE, max(_ZERO, value))


@dataclass(frozen=True, slots=True)
class HigherTimeframeContextIdentity:
    """WAVE_15 typed causal HTF context; it is context evidence, never an entry."""

    timeframe: str
    context_id: str
    regime: str
    always_in: str
    directional_side: str
    structural_location: str
    support: Decimal | None
    resistance: Decimal | None
    range_low: Decimal | None
    range_high: Decimal | None
    channel_direction: str
    available_at: datetime
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class CandidateHTFAlignment:
    """BROOKS-GAP-070 candidate-relative HTF direction identity."""

    candidate_direction: str
    state: str
    aligned_context_ids: tuple[str, ...]
    opposed_context_ids: tuple[str, ...]
    ambiguous_context_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.candidate_direction not in {"LONG", "SHORT"}:
            raise ValueError("candidate direction must be LONG or SHORT")
        if self.state not in {
            "ALIGNED_WITH_CANDIDATE",
            "OPPOSED_TO_CANDIDATE",
            "MIXED_DIRECTIONAL_HTF",
            "AMBIGUOUS_HTF",
            "UNAVAILABLE",
        }:
            raise ValueError("invalid candidate-relative HTF state")


@dataclass(frozen=True, slots=True)
class HTFPatternIdentity:
    """BROOKS-GAP-072 parent pattern identity on one causally closed HTF."""

    timeframe: str
    pattern_identity_id: str
    parent_context_id: str
    pattern_id: str
    role: str
    direction: str
    signal_index: int
    origin_id: str
    lifecycle_state: str
    available_at: datetime
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class MultiTimeframePatternLink:
    """Typed child/native -> parent/HTF link; context only, never an entry."""

    link_id: str
    native_timeframe: str
    native_pattern_id: str
    native_signal_index: int
    candidate_direction: str
    parent_timeframe: str
    parent_pattern_id: str
    parent_context_id: str
    relation: str
    evaluated_at: datetime
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class HTFFailedBreakoutContext:
    """BROOKS-GAP-074 origin-preserving HTF failed-breakout or swing-test context."""

    timeframe: str
    context_id: str
    parent_context_id: str
    event_type: str
    breakout_origin_id: str
    reversal_direction: str
    state: str
    event_index: int
    available_at: datetime
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class NestedHTFMTRContext:
    """BROOKS-GAP-073 nested HTF MTR lifecycle exposed to native candidates."""

    timeframe: str
    context_id: str
    parent_context_id: str
    mtr_episode_id: str
    prior_trend_direction: str
    reversal_direction: str
    state: str
    old_extreme_index: int
    structure_break_index: int
    retest_index: int | None
    second_reversal_index: int | None
    available_at: datetime
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class BrooksMarketContext:
    regime: str
    always_in: str
    trend_strength: Decimal
    trading_range_probability: Decimal
    volatility_ratio: Decimal
    compression_expansion_ratio: Decimal
    volatility_state: str
    channel_quality: str
    channel_direction: str
    swing_quality: Decimal
    location: str
    support: Decimal | None
    resistance: Decimal | None
    measured_move_probability: Decimal
    measured_move_target: Decimal | None
    measured_move_failure: bool
    higher_timeframe: str | None
    higher_timeframe_regime: str
    timeframe_alignment: str
    higher_timeframe_agreement: Decimal
    probability_semantics: str = "ENGINEERING_CONTEXT_LIKELIHOOD_NOT_EMPIRICAL"
    range_hierarchy: RangeHierarchyContext | None = None
    range_subtype: str = "UNRESOLVED"
    barbwire_active: bool = False
    local_breakout_relation: str = "NOT_NESTED"
    higher_timeframe_contexts: tuple[HigherTimeframeContextIdentity, ...] = ()
    native_timeframe: str = ""
    evaluated_at: datetime | None = None
    higher_timeframe_patterns: tuple[HTFPatternIdentity, ...] = ()
    higher_timeframe_failed_breakouts: tuple[HTFFailedBreakoutContext, ...] = ()
    higher_timeframe_mtr_contexts: tuple[NestedHTFMTRContext, ...] = ()

    def candidate_htf_alignment(self, direction: str) -> CandidateHTFAlignment:
        """Return HTF direction relative to this actual candidate (BROOKS-GAP-070)."""
        side = direction.upper()
        if side not in {"LONG", "SHORT"}:
            raise ValueError("candidate direction must be LONG or SHORT")
        if not self.higher_timeframe_contexts:
            return CandidateHTFAlignment(side, "UNAVAILABLE", (), (), ())
        aligned: list[str] = []
        opposed: list[str] = []
        ambiguous: list[str] = []
        for item in self.higher_timeframe_contexts:
            if item.directional_side == side:
                aligned.append(item.context_id)
            elif item.directional_side in {"LONG", "SHORT"}:
                opposed.append(item.context_id)
            else:
                ambiguous.append(item.context_id)
        if aligned and opposed:
            state = "MIXED_DIRECTIONAL_HTF"
        elif aligned:
            state = "ALIGNED_WITH_CANDIDATE"
        elif opposed:
            state = "OPPOSED_TO_CANDIDATE"
        else:
            state = "AMBIGUOUS_HTF"
        return CandidateHTFAlignment(side, state, tuple(aligned), tuple(opposed), tuple(ambiguous))

    def candidate_htf_location_state(self, direction: str) -> str:
        """BROOKS-GAP-071 structural HTF location relative to a reversal direction."""
        side = direction.upper()
        if side not in {"LONG", "SHORT"}:
            raise ValueError("candidate direction must be LONG or SHORT")
        if not self.higher_timeframe_contexts:
            return "UNAVAILABLE"
        supportive = (
            {"AT_HTF_SUPPORT", "AT_HTF_RANGE_LOW_EDGE", "BELOW_HTF_SUPPORT"}
            if side == "LONG"
            else {"AT_HTF_RESISTANCE", "AT_HTF_RANGE_HIGH_EDGE", "ABOVE_HTF_RESISTANCE"}
        )
        opposed = (
            {"AT_HTF_RESISTANCE", "AT_HTF_RANGE_HIGH_EDGE", "ABOVE_HTF_RESISTANCE"}
            if side == "LONG"
            else {"AT_HTF_SUPPORT", "AT_HTF_RANGE_LOW_EDGE", "BELOW_HTF_SUPPORT"}
        )
        states = {item.structural_location for item in self.higher_timeframe_contexts}
        if states & supportive:
            return "SUPPORTIVE_HTF_LOCATION"
        if states & opposed:
            return "OPPOSED_HTF_LOCATION"
        if states:
            return "NEUTRAL_HTF_LOCATION"
        return "UNAVAILABLE"

    def multitimeframe_links(
        self, native_pattern_id: str, native_signal_index: int, direction: str
    ) -> tuple[MultiTimeframePatternLink, ...]:
        """BROOKS-GAP-072: preserve explicit native-child -> HTF-parent identity."""
        side = direction.upper()
        if side not in {"LONG", "SHORT"} or not self.native_timeframe:
            return ()
        evaluated = self.evaluated_at
        if evaluated is None:
            return ()
        out = []
        for parent in self.higher_timeframe_patterns:
            if parent.available_at > evaluated:
                continue
            if parent.direction not in {side, "UNRESOLVED"}:
                continue
            relation = (
                "HTF_PARENT_PATTERN_SAME_DIRECTION"
                if parent.direction == side
                else "HTF_PARENT_PATTERN_CONTEXT"
            )
            out.append(MultiTimeframePatternLink(
                link_id=(
                    f"MTF:{self.native_timeframe}:{native_pattern_id}:{native_signal_index}"
                    f"->{parent.pattern_identity_id}"
                ),
                native_timeframe=self.native_timeframe,
                native_pattern_id=native_pattern_id,
                native_signal_index=native_signal_index,
                candidate_direction=side,
                parent_timeframe=parent.timeframe,
                parent_pattern_id=parent.pattern_identity_id,
                parent_context_id=parent.parent_context_id,
                relation=relation,
                evaluated_at=evaluated,
                trade_eligible=False,
            ))
        return tuple(out)

    def candidate_htf_failed_breakout_contexts(
        self, direction: str
    ) -> tuple[HTFFailedBreakoutContext, ...]:
        side = direction.upper()
        return tuple(
            item for item in self.higher_timeframe_failed_breakouts
            if item.event_type == "FAILED_BREAKOUT"
            and item.reversal_direction == side
            and (self.evaluated_at is None or item.available_at <= self.evaluated_at)
        )

    def htf_swing_test_contexts(self) -> tuple[HTFFailedBreakoutContext, ...]:
        return tuple(
            item for item in self.higher_timeframe_failed_breakouts
            if item.event_type == "SWING_TEST"
            and (self.evaluated_at is None or item.available_at <= self.evaluated_at)
        )

    def candidate_htf_mtr_contexts(self, direction: str) -> tuple[NestedHTFMTRContext, ...]:
        side = direction.upper()
        return tuple(
            item for item in self.higher_timeframe_mtr_contexts
            if item.reversal_direction == side
            and (self.evaluated_at is None or item.available_at <= self.evaluated_at)
        )

    def direction_alignment(self, direction: str) -> Decimal:
        """Composite local + candidate-relative HTF context; no directionless HTF bonus."""
        side = direction.upper()
        points: list[Decimal] = []
        if self.always_in in {"LONG", "SHORT"}:
            points.append(_ONE if self.always_in == side else _ZERO)
        if self.regime == "BULL_TREND":
            points.append(_ONE if side == "LONG" else _ZERO)
        elif self.regime == "BEAR_TREND":
            points.append(_ONE if side == "SHORT" else _ZERO)
        elif self.regime == "TRADING_RANGE":
            points.append(Decimal("0.5"))
        htf = self.candidate_htf_alignment(side)
        if htf.state == "ALIGNED_WITH_CANDIDATE":
            points.append(_ONE)
        elif htf.state == "OPPOSED_TO_CANDIDATE":
            points.append(_ZERO)
        # Mixed/ambiguous HTF is not silently treated as positive evidence.
        return sum(points, _ZERO) / Decimal(len(points)) if points else Decimal("0.5")


def _median_range(candles: tuple[Candle, ...]) -> Decimal:
    values = [item.high - item.low for item in candles if item.high > item.low]
    return median(values) if values else _ZERO


def _median_close(candles: tuple[Candle, ...]) -> Decimal:
    values = [item.close for item in candles if item.close > 0]
    return median(values) if values else _ZERO


def _next_higher_timeframe(timeframe: str) -> str | None:
    """Legacy closest-HTF helper retained for compatibility."""
    return {
        "5m": "15m",
        "15m": "1h",
        "30m": "2h",
        "1h": "4h",
        "2h": "6h",
        "4h": "1d",
        "6h": "1d",
        "12h": "1d",
    }.get(timeframe)


_RELEVANT_HTF_SEARCH_ORDER = ("15m", "1h", "1d")
# ENGINEERING_SEARCH_POLICY for BROOKS-GAP-075.  Brooks' source semantic owns
# "multiple relevant higher timeframes", not this finite machine search list.


def relevant_higher_timeframes(timeframe: str) -> tuple[str, ...]:
    source_seconds = TIMEFRAME_SECONDS.get(timeframe)
    if source_seconds is None:
        return ()
    return tuple(
        target
        for target in _RELEVANT_HTF_SEARCH_ORDER
        if TIMEFRAME_SECONDS[target] > source_seconds
        and TIMEFRAME_SECONDS[target] % source_seconds == 0
    )


def aggregate_to_higher_timeframe(
    snapshot: MarketSnapshot,
    target: str,
) -> MarketSnapshot | None:
    """Aggregate only fully closed HTF candles available by snapshot.captured_at."""
    if target not in TIMEFRAME_SECONDS:
        return None
    source_seconds = TIMEFRAME_SECONDS[snapshot.timeframe]
    target_seconds = TIMEFRAME_SECONDS[target]
    if target_seconds <= source_seconds or target_seconds % source_seconds:
        return None
    expected = target_seconds // source_seconds
    groups: dict[int, list[Candle]] = {}
    for candle in snapshot.candles:
        bucket = int(candle.open_time.timestamp()) // target_seconds * target_seconds
        groups.setdefault(bucket, []).append(candle)

    aggregated: list[Candle] = []
    for bucket, items in sorted(groups.items()):
        if len(items) != expected:
            continue
        bucket_open = datetime.fromtimestamp(bucket, tz=UTC)
        bucket_close = datetime.fromtimestamp(bucket + target_seconds, tz=UTC)
        if items[0].open_time != bucket_open or items[-1].close_time != bucket_close:
            continue
        if bucket_close > snapshot.captured_at:
            # BROOKS-GAP-070 causality: an incomplete/future HTF candle is unavailable.
            continue
        aggregated.append(Candle(
            open_time=bucket_open,
            close_time=bucket_close,
            open=items[0].open,
            high=max(item.high for item in items),
            low=min(item.low for item in items),
            close=items[-1].close,
            volume=sum((item.volume for item in items), _ZERO),
        ))
    if len(aggregated) < 20:
        return None
    return MarketSnapshot(
        exchange=snapshot.exchange,
        market_type=snapshot.market_type,
        symbol=snapshot.symbol,
        timeframe=target,
        candles=tuple(aggregated),
        captured_at=aggregated[-1].close_time,
        source="CAUSAL_LOCAL_HTF_AGGREGATION",
    )


def aggregate_higher_timeframe(snapshot: MarketSnapshot) -> MarketSnapshot | None:
    target = _next_higher_timeframe(snapshot.timeframe)
    return None if target is None else aggregate_to_higher_timeframe(snapshot, target)


def aggregate_relevant_higher_timeframes(snapshot: MarketSnapshot) -> tuple[MarketSnapshot, ...]:
    """BROOKS-GAP-075: expose every causally available relevant HTF from the search policy."""
    return tuple(
        item
        for target in relevant_higher_timeframes(snapshot.timeframe)
        if (item := aggregate_to_higher_timeframe(snapshot, target)) is not None
    )


def _htf_context_identity(
    htf: MarketSnapshot,
    policy: BrooksFullCorePolicy,
) -> HigherTimeframeContextIdentity:
    """Build 071/076 identity using only this already-closed HTF prefix."""
    htf_policy = replace(
        policy.context,
        context_window_bars=20,
        recent_window_bars=10,
    )
    context = assess_books_context(htf, policy=htf_policy)
    advanced = assess_advanced_context(htf, policy=policy)
    scan = confirm_swings_causally(
        htf.candles,
        left_bars=htf_policy.swing_left_bars,
        right_bars=htf_policy.swing_right_bars,
    )
    lows = [item for item in scan.swings if item.kind == "LOW"]
    highs = [item for item in scan.swings if item.kind == "HIGH"]
    recent = tuple(htf.candles[-20:])
    support = lows[-1].price if lows else min(item.low for item in recent)
    resistance = highs[-1].price if highs else max(item.high for item in recent)
    last = htf.candles[-1].close
    tolerance = _median_range(recent)  # ENGINEERING_TOLERANCE for qualitative location.
    range_evidence = assess_range_identity_evidence(recent, htf_policy)
    range_low = min(item.low for item in recent) if range_evidence.composite_supported else None
    range_high = max(item.high for item in recent) if range_evidence.composite_supported else None
    if range_low is not None and range_high is not None:
        if last - range_low <= tolerance:
            location = "AT_HTF_RANGE_LOW_EDGE"
        elif range_high - last <= tolerance:
            location = "AT_HTF_RANGE_HIGH_EDGE"
        else:
            location = "HTF_RANGE_MIDDLE"
    elif last > resistance:
        location = "ABOVE_HTF_RESISTANCE"
    elif last < support:
        location = "BELOW_HTF_SUPPORT"
    elif last - support <= tolerance:
        location = "AT_HTF_SUPPORT"
    elif resistance - last <= tolerance:
        location = "AT_HTF_RESISTANCE"
    else:
        location = "HTF_MID_STRUCTURE"

    directional_side = (
        context.always_in
        if context.always_in in {"LONG", "SHORT"}
        else "LONG" if context.regime == "BULL_TREND"
        else "SHORT" if context.regime == "BEAR_TREND"
        else "UNRESOLVED"
    )
    channel_direction = (
        advanced.tight_channel_direction
        if advanced.tight_channel_direction != "UNRESOLVED"
        else advanced.spike_channel_direction
    )
    available_at = htf.candles[-1].close_time
    return HigherTimeframeContextIdentity(
        timeframe=htf.timeframe,
        context_id=f"HTF:{htf.timeframe}:{int(available_at.timestamp())}",
        regime=context.regime,
        always_in=context.always_in,
        directional_side=directional_side,
        structural_location=location,
        support=support,
        resistance=resistance,
        range_low=range_low,
        range_high=range_high,
        channel_direction=channel_direction,
        available_at=available_at,
        trade_eligible=False,
    )


def _origin_id(metadata: dict[str, str], fallback: str) -> str:
    for key in (
        "mtr_episode_id", "breakout_id", "structure_id", "wedge_structure_id",
        "final_flag_id", "attempt_id", "episode_id",
    ):
        value = metadata.get(key)
        if value:
            return value
    return fallback


def _htf_nested_pattern_state(
    htf: MarketSnapshot,
    policy: BrooksFullCorePolicy,
    parent: HigherTimeframeContextIdentity,
) -> tuple[
    tuple[HTFPatternIdentity, ...],
    tuple[HTFFailedBreakoutContext, ...],
    tuple[NestedHTFMTRContext, ...],
]:
    """WAVE_16: derive nesting from existing causal pattern/failure/MTR sources."""
    # Runtime-local imports avoid a module cycle.  No alternate detector is created:
    # 072 consumes the normal pattern scan, 074 consumes WAVE_10 breakout lifecycle,
    # and 073 consumes the WAVE_08 MTR lifecycle helper.
    from app.modules.brooks_core.books_full_patterns import (
        scan_full_brooks_patterns,
        scan_major_trend_reversal_lifecycles,
    )

    htf_policy = replace(policy.context, context_window_bars=20, recent_window_bars=10)
    base = assess_books_context(htf, policy=htf_policy)
    scan = scan_full_brooks_patterns(htf, base, policy, None)
    patterns: list[HTFPatternIdentity] = []
    failures: list[HTFFailedBreakoutContext] = []

    for item in scan.candidates:
        md = dict(item.metadata)
        fallback = f"{item.family}:{item.setup_type}:{item.signal_index}"
        origin = _origin_id(md, fallback)
        available = htf.candles[min(item.signal_index, len(htf.candles)-1)].close_time
        patterns.append(HTFPatternIdentity(
            timeframe=htf.timeframe,
            pattern_identity_id=f"HTF_PATTERN:{htf.timeframe}:{item.setup_type}:{item.signal_index}:{origin}",
            parent_context_id=parent.context_id,
            pattern_id=item.setup_type,
            role="HTF_CANDIDATE_PATTERN_CONTEXT",
            direction=item.direction,
            signal_index=item.signal_index,
            origin_id=origin,
            lifecycle_state=md.get("lifecycle_state", md.get("confirmation_state", "CANDIDATE_AVAILABLE")),
            available_at=available,
            trade_eligible=False,
        ))
        if item.family == "FAILED_BREAKOUT" and md.get("breakout_id"):
            failures.append(HTFFailedBreakoutContext(
                timeframe=htf.timeframe,
                context_id=f"HTF_FAILED_BREAKOUT:{htf.timeframe}:{md['breakout_id']}:{item.signal_index}",
                parent_context_id=parent.context_id,
                event_type="FAILED_BREAKOUT",
                breakout_origin_id=md["breakout_id"],
                reversal_direction=item.direction,
                state=md.get("confirmation_state", "CONFIRMED_FAILED_BREAKOUT"),
                event_index=item.signal_index,
                available_at=available,
                trade_eligible=False,
            ))

    for item in scan.observations:
        md = dict(item.metadata)
        fallback = f"{item.pattern_id}:{item.signal_index}"
        origin = _origin_id(md, fallback)
        available = htf.candles[min(item.signal_index, len(htf.candles)-1)].close_time
        patterns.append(HTFPatternIdentity(
            timeframe=htf.timeframe,
            pattern_identity_id=f"HTF_PATTERN:{htf.timeframe}:{item.pattern_id}:{item.signal_index}:{origin}",
            parent_context_id=parent.context_id,
            pattern_id=item.pattern_id,
            role=item.role,
            direction=item.direction,
            signal_index=item.signal_index,
            origin_id=origin,
            lifecycle_state=md.get("state", md.get("lifecycle_state", md.get("confirmation_state", "OBSERVED"))),
            available_at=available,
            trade_eligible=False,
        ))
        if item.pattern_id.startswith("FAILED_BREAKOUT_CONTEXT_") and md.get("breakout_id"):
            failures.append(HTFFailedBreakoutContext(
                timeframe=htf.timeframe,
                context_id=f"HTF_FAILED_BREAKOUT:{htf.timeframe}:{md['breakout_id']}:{item.signal_index}",
                parent_context_id=parent.context_id,
                event_type="FAILED_BREAKOUT",
                breakout_origin_id=md["breakout_id"],
                reversal_direction=item.direction,
                state=md.get("confirmation_state", "FAILED_BREAKOUT_CONTEXT"),
                event_index=item.signal_index,
                available_at=available,
                trade_eligible=False,
            ))
        elif item.pattern_id.startswith("BREAKOUT_TEST_") and md.get("structure_id"):
            failures.append(HTFFailedBreakoutContext(
                timeframe=htf.timeframe,
                context_id=f"HTF_SWING_TEST:{htf.timeframe}:{md['structure_id']}:{item.signal_index}",
                parent_context_id=parent.context_id,
                event_type="SWING_TEST",
                breakout_origin_id=md["structure_id"],
                reversal_direction="UNRESOLVED",
                state=md.get("kind", "BREAKOUT_TEST"),
                event_index=item.signal_index,
                available_at=available,
                trade_eligible=False,
            ))

    mtr: list[NestedHTFMTRContext] = []
    for life in scan_major_trend_reversal_lifecycles(htf, policy):
        available = htf.candles[-1].close_time
        mtr.append(NestedHTFMTRContext(
            timeframe=htf.timeframe,
            context_id=f"HTF_MTR:{htf.timeframe}:{life.mtr_episode_id}:{len(htf.candles)-1}",
            parent_context_id=parent.context_id,
            mtr_episode_id=life.mtr_episode_id,
            prior_trend_direction=life.prior_trend_direction,
            reversal_direction=life.reversal_direction,
            state=life.state,
            old_extreme_index=life.old_extreme_index,
            structure_break_index=life.structure_break_index,
            retest_index=life.retest_index,
            second_reversal_index=life.second_reversal_index,
            available_at=available,
            trade_eligible=False,
        ))

    # Stable exact-identity dedup, without collapsing source-distinct roles.
    unique_p = {x.pattern_identity_id: x for x in patterns}
    unique_f = {x.context_id: x for x in failures}
    unique_m = {x.context_id: x for x in mtr}
    return tuple(unique_p.values()), tuple(unique_f.values()), tuple(unique_m.values())


def build_market_context(
    snapshot: MarketSnapshot,
    *,
    policy: BrooksFullCorePolicy | None = None,
) -> BrooksMarketContext:
    policy = policy or BrooksFullCorePolicy()
    base = assess_books_context(snapshot, policy=policy.context)
    range_hierarchy = assess_range_hierarchy(
        snapshot.candles, policy.context, edge_zone_fraction=policy.range_extreme_zone_fraction
    )
    advanced = assess_advanced_context(snapshot, policy=policy)
    metrics = base.metrics

    ttr_window = tuple(snapshot.candles[-policy.context.tight_range_window_bars:])
    bw_window = tuple(snapshot.candles[-policy.barbwire_veto_window_bars:])
    broad_window = tuple(snapshot.candles[-policy.context.recent_window_bars:])
    ttr_identity = classify_tight_trading_range(ttr_window, policy.context) if len(ttr_window) >= 2 else None
    barbwire_identity = classify_barbwire_identity(bw_window, policy.context) if len(bw_window) >= 3 else None
    broad_identity = classify_broad_trading_range(broad_window, policy.context) if len(broad_window) >= 3 else None
    if barbwire_identity is not None and barbwire_identity.is_barbwire:
        range_subtype = "BARBWIRE"
    elif ttr_identity is not None and ttr_identity.is_tight:
        range_subtype = "TIGHT_TRADING_RANGE"
    elif broad_identity is not None and broad_identity.is_broad:
        range_subtype = "BROAD_TRADING_RANGE"
    elif base.regime == "TRADING_RANGE":
        range_subtype = "GENERIC_TRADING_RANGE"
    else:
        range_subtype = "NOT_RANGE"
    local_breakout = classify_local_breakout_vs_enclosing(
        snapshot.candles[-1], range_hierarchy, evaluated_index=len(snapshot.candles)-1
    )
    local_breakout_relation = "NOT_NESTED" if local_breakout is None else local_breakout.state

    trend_parts = (
        _clamp(metrics.directional_bar_fraction),
        _clamp(_ONE - metrics.bar_overlap_rate),
        _clamp(metrics.ema_side_fraction),
        _clamp(abs(metrics.adjusted_displacement)),
    )
    trend_strength = sum(trend_parts, _ZERO) / Decimal(len(trend_parts))
    range_parts = (
        _clamp(metrics.bar_overlap_rate),
        _clamp(_ONE - abs(metrics.adjusted_displacement)),
        _ONE if metrics.tight_range_like else _ZERO,
    )
    trading_range_probability = sum(range_parts, _ZERO) / Decimal(len(range_parts))

    recent = snapshot.candles[-5:]
    prior = snapshot.candles[-20:-5]
    recent_range = _median_range(recent)
    prior_range = _median_range(prior)
    ratio = recent_range / prior_range if prior_range > 0 else _ONE
    median_close = _median_close(snapshot.candles[-20:])
    volatility_ratio = recent_range / median_close if median_close > 0 else _ZERO
    volatility_state = "EXPANDING" if ratio > _ONE else "COMPRESSING" if ratio < _ONE else "BALANCED"

    from app.modules.brooks_core.pattern_expansion import (
        scan_additional_context_observations,
        scan_structure_observations,
    )
    observations = (
        *scan_structure_observations(snapshot, base, policy),
        *scan_additional_context_observations(snapshot, base, policy),
    )
    ids = {item.pattern_id for item in observations}
    # V5: scanner emits directional IDs; the former generic ID was unreachable.
    if {"BULL_MICRO_CHANNEL", "BEAR_MICRO_CHANNEL"} & ids:
        channel_quality = "MICRO"
    elif advanced.tight_channel_direction != "UNRESOLVED":
        channel_quality = "TIGHT"
    elif "BROAD_CHANNEL_STAIRS" in ids:
        channel_quality = "BROAD"
    elif advanced.spike_channel_direction != "UNRESOLVED":
        channel_quality = "SPIKE_AND_CHANNEL"
    else:
        channel_quality = "UNRESOLVED"
    channel_direction = (
        advanced.tight_channel_direction
        if advanced.tight_channel_direction != "UNRESOLVED"
        else advanced.spike_channel_direction
    )

    scan = confirm_swings_causally(
        snapshot.candles,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    structure = evaluate_br031_structure(scan)
    swing_quality = Decimal("0.25")
    if len(scan.swings) >= 4:
        swing_quality = Decimal("0.5")
    if structure.direction in {"BULL_TREND", "BEAR_TREND"}:
        swing_quality = _ONE

    lows = [item for item in scan.swings if item.kind == "LOW"]
    highs = [item for item in scan.swings if item.kind == "HIGH"]
    support = lows[-1].price if lows else min(item.low for item in snapshot.candles[-20:])
    resistance = highs[-1].price if highs else max(item.high for item in snapshot.candles[-20:])
    last = snapshot.candles[-1].close
    tolerance = _median_range(snapshot.candles[-20:])
    if resistance is not None and last > resistance:
        location = "ABOVE_RESISTANCE"
    elif support is not None and last < support:
        location = "BELOW_SUPPORT"
    elif support is not None and last - support <= tolerance:
        location = "AT_SUPPORT"
    elif resistance is not None and resistance - last <= tolerance:
        location = "AT_RESISTANCE"
    else:
        location = "MID_RANGE_OR_CHANNEL"

    measured_failure = False
    measured_probability = _ZERO
    target = advanced.measured_move_target
    if target is not None:
        aligned = (
            advanced.measured_move_direction == base.always_in
            or (advanced.measured_move_direction == "LONG" and base.regime == "BULL_TREND")
            or (advanced.measured_move_direction == "SHORT" and base.regime == "BEAR_TREND")
        )
        measured_probability = trend_strength if aligned else trading_range_probability / Decimal("2")
        history = snapshot.candles[-6:]
        if len(history) >= 3 and tolerance > 0:
            if advanced.measured_move_direction == "LONG" and max(x.high for x in history) < target:
                near = target - max(x.high for x in history) <= tolerance
                measured_failure = near and history[-1].close < history[-2].close
            elif advanced.measured_move_direction == "SHORT" and min(x.low for x in history) > target:
                near = min(x.low for x in history) - target <= tolerance
                measured_failure = near and history[-1].close > history[-2].close

    # WAVE_15: preserve multiple causally closed HTF identities.  The legacy
    # single-HTF fields remain diagnostic/backward-compatible and are NOT candidate scoring.
    htf_snapshots = aggregate_relevant_higher_timeframes(snapshot)
    htf_contexts = tuple(_htf_context_identity(item, policy) for item in htf_snapshots)
    htf_patterns: list[HTFPatternIdentity] = []
    htf_failures: list[HTFFailedBreakoutContext] = []
    htf_mtr: list[NestedHTFMTRContext] = []
    for htf_snapshot, htf_context in zip(htf_snapshots, htf_contexts):
        patterns, failures, mtr = _htf_nested_pattern_state(htf_snapshot, policy, htf_context)
        htf_patterns.extend(patterns)
        htf_failures.extend(failures)
        htf_mtr.extend(mtr)
    higher_timeframe = htf_contexts[0].timeframe if htf_contexts else None
    higher_regime = htf_contexts[0].regime if htf_contexts else "UNAVAILABLE"
    alignment = "UNAVAILABLE"
    agreement = Decimal("0.5")
    if htf_contexts:
        primary_side = "LONG" if base.regime == "BULL_TREND" else "SHORT" if base.regime == "BEAR_TREND" else None
        higher_side = htf_contexts[0].directional_side if htf_contexts[0].directional_side in {"LONG", "SHORT"} else None
        if primary_side and higher_side:
            alignment = "ALIGNED" if primary_side == higher_side else "OPPOSED"
            agreement = _ONE if alignment == "ALIGNED" else _ZERO
        elif higher_side is None and primary_side is None:
            alignment = "NEUTRAL"
        else:
            alignment = "MIXED"

    return BrooksMarketContext(
        regime=base.regime,
        always_in=base.always_in,
        trend_strength=trend_strength.quantize(Decimal("0.0001")),
        trading_range_probability=trading_range_probability.quantize(Decimal("0.0001")),
        volatility_ratio=volatility_ratio.quantize(Decimal("0.000001")),
        compression_expansion_ratio=ratio.quantize(Decimal("0.0001")),
        volatility_state=volatility_state,
        channel_quality=channel_quality,
        channel_direction=channel_direction,
        swing_quality=swing_quality,
        location=location,
        support=support,
        resistance=resistance,
        measured_move_probability=measured_probability.quantize(Decimal("0.0001")),
        measured_move_target=target,
        measured_move_failure=measured_failure,
        higher_timeframe=higher_timeframe,
        higher_timeframe_regime=higher_regime,
        timeframe_alignment=alignment,
        higher_timeframe_agreement=agreement,
        range_hierarchy=range_hierarchy,
        range_subtype=range_subtype,
        barbwire_active=bool(barbwire_identity and barbwire_identity.is_barbwire),
        local_breakout_relation=local_breakout_relation,
        higher_timeframe_contexts=htf_contexts,
        native_timeframe=snapshot.timeframe,
        evaluated_at=snapshot.captured_at,
        higher_timeframe_patterns=tuple(htf_patterns),
        higher_timeframe_failed_breakouts=tuple(htf_failures),
        higher_timeframe_mtr_contexts=tuple(htf_mtr),
    )
