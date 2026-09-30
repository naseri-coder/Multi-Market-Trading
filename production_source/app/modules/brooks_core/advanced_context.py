"""Additional Brooks context features used by the Phase-1 book-alignment refactor.

These are descriptive. Tight/spike channel and measured-move observations do not create
entries by themselves. Opening reversal is intentionally unavailable without a session anchor.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.causal_structure import confirm_swings_causally
from app.modules.brooks_core.context_classifier import (
    assess_range_identity_evidence,
    is_strong_bear_bar,
    is_strong_bull_bar,
)
from app.modules.brooks_core.correction_lifecycle import build_breakout_attempt_identity
from app.modules.brooks_core.structural_geometry import (
    StructuralTestIdentity,
    classify_structural_test,
)
from app.modules.market_data.entities import Candle, MarketSnapshot


@dataclass(frozen=True, slots=True)
class MicroChannelIdentity:
    """BROOKS-GAP-007: micro-trend-line channel with rare small pullbacks allowed."""
    channel_id: str
    direction: str
    start_index: int
    end_index: int
    bar_count: int
    line_proximity_count: int
    small_bar_count: int
    countertrend_bar_count: int
    engineering_tolerance: Decimal
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class SpikeChannelLifecycle:
    """BROOKS-GAP-009: causal spike -> pullback/channel progression."""
    episode_id: str
    direction: str
    spike_start_index: int
    spike_end_index: int
    channel_start_index: int | None
    evaluated_index: int
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class TrendRangeEvolution:
    """BROOKS-GAP-010: gradual trend/channel/range-pressure state."""
    episode_id: str
    direction: str
    origin_index: int
    evaluated_index: int
    overlap_rate: Decimal
    countertrend_fraction: Decimal
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class ChannelOpposingFlagContext:
    """Chapter-3 channel retracement/opposing-flag possibility; never an entry."""

    context_id: str
    episode_id: str
    direction: str
    opposing_direction: str
    channel_start_index: int
    established_at_index: int
    evaluated_index: int
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class TrendRangeEpisodeLink:
    """Causal link from breakout/spike evolution to a later range without identity conflation."""

    link_id: str
    range_id: str
    origin_breakout_id: str | None
    origin_spike_episode_id: str
    parent_evolution_episode_id: str
    symbol: str
    timeframe: str
    range_origin_index: int
    range_established_index: int
    evaluated_index: int
    state: str = "ESTABLISHED_RANGE_LINKED_TO_TREND_EVOLUTION"
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class SmallPullbackTrendIdentity:
    """BROOKS-GAP-025: shallow/infrequent pullback trend state."""
    episode_id: str
    direction: str
    origin_index: int
    evaluated_index: int
    pullback_episode_count: int
    max_pullback_run: int
    max_pullback_depth: Decimal
    median_bar_range: Decimal
    later_expansion: bool
    state: str
    trade_eligible: bool = False


@dataclass(frozen=True, slots=True)
class SpikeMeasuredMoveIdentity:
    """BROOKS-GAP-021 full-spike source identity with both source-supported anchors."""

    spike_id: str
    direction: str
    start_index: int
    end_index: int
    available_at_index: int
    open_close_target: Decimal
    extreme_target: Decimal
    state: str = "OBSERVED_FULL_SPIKE"

    def __post_init__(self) -> None:
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("spike measured-move direction must be LONG or SHORT")
        if self.start_index < 0 or self.end_index < self.start_index:
            raise ValueError("invalid spike measured-move span")
        if self.available_at_index < self.end_index:
            raise ValueError("spike target cannot be available before spike end")




@dataclass(frozen=True, slots=True)
class AdvancedBrooksContext:
    # V5 PHASE-001..005: descriptive state resolved before entry-pattern scanning.
    market_phase: str = "TRANSITION"
    phase_direction: str = "UNRESOLVED"
    tight_channel_direction: str = "UNRESOLVED"
    spike_channel_direction: str = "UNRESOLVED"
    measured_move_direction: str = "UNRESOLVED"
    measured_move_target: Decimal | None = None
    spike_measured_move_identity: SpikeMeasuredMoveIdentity | None = None
    opening_reversal_available: bool = False
    micro_channel_state: str = "UNRESOLVED"
    micro_channel_direction: str = "UNRESOLVED"
    spike_channel_state: str = "UNRESOLVED"
    trend_range_state: str = "UNRESOLVED"
    small_pullback_trend_state: str = "UNRESOLVED"
    reasons: tuple[str, ...] = ()

def _directional_pullback_runs(candles, direction: str) -> tuple[int, int]:
    max_run = 0
    run = 0
    with_trend = 0
    for candle in candles:
        aligned = candle.close > candle.open if direction == "LONG" else candle.close < candle.open
        if aligned:
            with_trend += 1
            run = 0
        else:
            run += 1
            max_run = max(max_run, run)
    return max_run, with_trend



def _bar_range(c: Candle) -> Decimal:
    return c.high-c.low


def _median_range(candles: tuple[Candle, ...]) -> Decimal:
    vals=[_bar_range(c) for c in candles if c.high>c.low]
    return median(vals) if vals else Decimal("0")


def _positive_overlap_rate(candles: tuple[Candle, ...]) -> Decimal:
    if len(candles)<2:
        return Decimal("0")
    hits=0
    for a,b in zip(candles,candles[1:]):
        if min(a.high,b.high)>max(a.low,b.low):
            hits+=1
    return Decimal(hits)/Decimal(len(candles)-1)


def classify_micro_channel_identity(
    candles: tuple[Candle, ...],
    policy: BrooksFullCorePolicy,
    *,
    evaluated_index: int | None = None,
) -> MicroChannelIdentity | None:
    """BROOKS-GAP-007. Roughly 2-10 bars is retained as a SOURCE GUIDE search span."""
    if len(candles)<2:
        return None
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    max_n=min(10,end+1)  # SOURCE GUIDE: roughly 2-10 bars, not a universal validity deadline.
    for n in range(max_n,1,-1):
        start=end-n+1
        seg=tuple(candles[start:end+1])
        net=seg[-1].close-seg[0].close
        if net==0:
            continue
        direction="LONG" if net>0 else "SHORT"
        vals=[c.low if direction=="LONG" else c.high for c in seg]
        slope=(vals[-1]-vals[0])/Decimal(n-1)
        med=_median_range(seg)
        if med<=0:
            continue
        tol=med*Decimal("0.50")  # ENGINEERING_TOLERANCE for "near the micro trend line".
        near=sum(abs(v-(vals[0]+slope*Decimal(i)))<=tol for i,v in enumerate(vals))
        small=sum(_bar_range(c)<=med*Decimal("1.50") for c in seg)  # ENGINEERING_CLASSIFICATION_POLICY.
        counter=sum((c.close<c.open) if direction=="LONG" else (c.close>c.open) for c in seg)
        # Source allows no or rare small pullbacks: one countertrend bar is allowed.
        valid=near>=n-1 and small>=n-1 and counter<=1
        if valid:
            return MicroChannelIdentity(
                f"MICRO_CHANNEL:{direction}:{start}:{end}",direction,start,end,n,near,small,counter,tol,
                "ACTIVE_MICRO_CHANNEL",False
            )
    return None


def classify_spike_channel_lifecycle(
    snapshot: MarketSnapshot,
    policy: BrooksFullCorePolicy,
    *,
    evaluated_index: int | None = None,
) -> SpikeChannelLifecycle | None:
    """BROOKS-GAP-009: later channel state never backdates the spike origin."""
    candles=snapshot.candles
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    if end<1:
        return None
    start_scan=max(0,end-policy.spike_channel_scan_bars+1)  # ENGINEERING_SEARCH_POLICY
    best=None
    for i in range(start_scan,end):
        a,b=candles[i],candles[i+1]
        if is_strong_bull_bar(a,policy.context) and is_strong_bull_bar(b,policy.context): best=(i,i+1,"LONG")
        if is_strong_bear_bar(a,policy.context) and is_strong_bear_bar(b,policy.context): best=(i,i+1,"SHORT")
    if best is None:
        return None
    a,b,direction=best
    after=tuple(candles[b+1:end+1])
    channel_start=None
    state="SPIKE_ACTIVE"
    if after:
        for off,c in enumerate(after,b+1):
            counter=c.close<c.open if direction=="LONG" else c.close>c.open
            if counter:
                channel_start=off
                break
        if channel_start is not None:
            later=tuple(candles[channel_start:end+1])
            resumed=any((c.close>c.open) if direction=="LONG" else (c.close<c.open) for c in later[1:])
            state="SPIKE_PULLBACK_FORMING" if not resumed else "SPIKE_TO_CHANNEL_CONFIRMED"
            if resumed and _positive_overlap_rate(later)>=Decimal("0.50"):
                state="CHANNEL_OVERLAP_EXPANDING"
    return SpikeChannelLifecycle(f"SPIKE:{direction}:{a}:{b}",direction,a,b,channel_start,end,state,False)


def classify_trend_range_evolution(
    candles: tuple[Candle, ...],
    *,
    direction: str,
    origin_index: int,
    evaluated_index: int | None = None,
) -> TrendRangeEvolution | None:
    """BROOKS-GAP-010: explicit spectrum state, context only."""
    if direction not in {"LONG","SHORT"} or not candles:
        return None
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    if origin_index<0 or origin_index>end:
        return None
    seg=tuple(candles[origin_index:end+1])
    overlap=_positive_overlap_rate(seg)
    counter=sum((c.close<c.open) if direction=="LONG" else (c.close>c.open) for c in seg)
    cf=Decimal(counter)/Decimal(len(seg))
    if len(seg)<=2 and cf==0:
        state="DIRECTIONAL_SPIKE"
    elif overlap<Decimal("0.50") and cf<=Decimal("0.25"):
        state="ORDERLY_TREND"
    elif overlap>=Decimal("0.50") and cf<Decimal("0.50"):
        state="CHANNEL_WITH_GROWING_OVERLAP"
    elif overlap>=Decimal("0.50") and cf>=Decimal("0.25"):
        state="TWO_SIDED_RANGE_PRESSURE"
    else:
        state="TRANSITIONAL_TREND"
    return TrendRangeEvolution(
        f"TREND_RANGE:{direction}:{origin_index}",direction,origin_index,end,overlap,cf,state,False
    )


def _channel_confirmation_index(
    candles: tuple[Candle, ...],
    lifecycle: SpikeChannelLifecycle,
    *,
    evaluated_index: int,
) -> int | None:
    if lifecycle.channel_start_index is None:
        return None
    start = lifecycle.channel_start_index
    for index in range(start + 1, evaluated_index + 1):
        candle = candles[index]
        resumed = (
            candle.close > candle.open
            if lifecycle.direction == "LONG"
            else candle.close < candle.open
        )
        if resumed:
            return index
    return None


def classify_channel_start_structural_test(
    snapshot: MarketSnapshot,
    policy: BrooksFullCorePolicy,
    *,
    evaluated_index: int | None = None,
) -> StructuralTestIdentity | None:
    """B1C03-007: causal return to the established channel-start area, context only."""

    candles = snapshot.candles
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    lifecycle = classify_spike_channel_lifecycle(snapshot, policy, evaluated_index=end)
    if lifecycle is None or lifecycle.channel_start_index is None:
        return None
    confirmed = _channel_confirmation_index(candles, lifecycle, evaluated_index=end)
    if confirmed is None or confirmed >= end:
        return None
    start_bar = candles[lifecycle.channel_start_index]
    if lifecycle.direction == "LONG":
        zone_low = start_bar.low
        zone_high = max(start_bar.open, start_bar.close)
        reference_level = start_bar.low
    else:
        zone_low = min(start_bar.open, start_bar.close)
        zone_high = start_bar.high
        reference_level = start_bar.high
    return classify_structural_test(
        candles,
        reference_id=f"{lifecycle.episode_id}:CHANNEL_START:{lifecycle.channel_start_index}",
        reference_type="CHANNEL_START",
        zone_low=zone_low,
        zone_high=zone_high,
        search_start_index=confirmed + 1,
        direction=lifecycle.direction,
        reference_level=reference_level,
        origin_episode_id=lifecycle.episode_id,
        evaluated_index=end,
    )


def classify_channel_opposing_flag_context(
    snapshot: MarketSnapshot,
    policy: BrooksFullCorePolicy,
    *,
    evaluated_index: int | None = None,
) -> ChannelOpposingFlagContext | None:
    """B1C03-008: established channel may be a future opposing flag/retracement context."""

    candles = snapshot.candles
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    lifecycle = classify_spike_channel_lifecycle(snapshot, policy, evaluated_index=end)
    if lifecycle is None or lifecycle.channel_start_index is None:
        return None
    confirmed = _channel_confirmation_index(candles, lifecycle, evaluated_index=end)
    if confirmed is None:
        return None
    if lifecycle.direction == "LONG":
        opposing = "SHORT"
        state = "POTENTIAL_BEAR_FLAG_RETRACEMENT_RISK"
    else:
        opposing = "LONG"
        state = "POTENTIAL_BULL_FLAG_RETRACEMENT_RISK"
    return ChannelOpposingFlagContext(
        context_id=f"CHANNEL_OPPOSING_FLAG:{lifecycle.episode_id}",
        episode_id=lifecycle.episode_id,
        direction=lifecycle.direction,
        opposing_direction=opposing,
        channel_start_index=lifecycle.channel_start_index,
        established_at_index=confirmed,
        evaluated_index=end,
        state=state,
        trade_eligible=False,
    )


def _origin_breakout_id_for_spike(
    snapshot: MarketSnapshot,
    policy: BrooksFullCorePolicy,
    lifecycle: SpikeChannelLifecycle,
    *,
    evaluated_index: int,
) -> str | None:
    candles = snapshot.candles
    prefix = tuple(candles[: evaluated_index + 1])
    scan = confirm_swings_causally(
        prefix,
        left_bars=policy.context.swing_left_bars,
        right_bars=policy.context.swing_right_bars,
    )
    kind = "HIGH" if lifecycle.direction == "LONG" else "LOW"
    for attempt_index in range(lifecycle.spike_start_index, lifecycle.spike_end_index + 1):
        eligible = [
            swing
            for swing in scan.swings
            if swing.kind == kind and swing.confirmed_at_index < attempt_index
        ]
        if not eligible:
            continue
        swing = eligible[-1]
        origin = build_breakout_attempt_identity(
            candles,
            direction=lifecycle.direction,
            reference_id=f"SWING:{swing.candle_index}",
            reference_level=swing.price,
            attempt_index=attempt_index,
            engineering_strong=True,
        )
        if origin is not None:
            return origin.breakout_id
    return None


def classify_breakout_to_range_episode_link(
    snapshot: MarketSnapshot,
    policy: BrooksFullCorePolicy,
    *,
    current_range_supported: bool,
    evaluated_index: int | None = None,
) -> TrendRangeEpisodeLink | None:
    """B1C03-018: retain causal origin linkage while preserving an independent range ID."""

    if not current_range_supported:
        return None
    candles = snapshot.candles
    end = len(candles) - 1 if evaluated_index is None else min(evaluated_index, len(candles) - 1)
    lifecycle = classify_spike_channel_lifecycle(snapshot, policy, evaluated_index=end)
    if lifecycle is None or lifecycle.channel_start_index is None:
        return None
    confirmed = _channel_confirmation_index(candles, lifecycle, evaluated_index=end)
    if confirmed is None:
        return None
    evolution = classify_trend_range_evolution(
        candles,
        direction=lifecycle.direction,
        origin_index=lifecycle.spike_start_index,
        evaluated_index=end,
    )
    if evolution is None or evolution.state != "TWO_SIDED_RANGE_PRESSURE":
        return None

    range_origin = lifecycle.channel_start_index
    established = None
    for index in range(max(confirmed + 1, range_origin + 2), end + 1):
        segment = tuple(candles[range_origin:index + 1])
        evidence = assess_range_identity_evidence(segment, policy.context)
        prefix_evolution = classify_trend_range_evolution(
            candles,
            direction=lifecycle.direction,
            origin_index=lifecycle.spike_start_index,
            evaluated_index=index,
        )
        if (
            evidence.composite_supported
            and prefix_evolution is not None
            and prefix_evolution.state == "TWO_SIDED_RANGE_PRESSURE"
        ):
            established = index
            break
    if established is None:
        return None

    current_evidence = assess_range_identity_evidence(
        tuple(candles[range_origin:end + 1]),
        policy.context,
    )
    if not current_evidence.composite_supported:
        return None

    range_id = (
        f"RANGE:CH3:{snapshot.symbol}:{snapshot.timeframe}:"
        f"{range_origin}:{established}"
    )
    breakout_id = _origin_breakout_id_for_spike(
        snapshot,
        policy,
        lifecycle,
        evaluated_index=end,
    )
    return TrendRangeEpisodeLink(
        link_id=f"TREND_RANGE_LINK:{range_id}:{lifecycle.episode_id}",
        range_id=range_id,
        origin_breakout_id=breakout_id,
        origin_spike_episode_id=lifecycle.episode_id,
        parent_evolution_episode_id=evolution.episode_id,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        range_origin_index=range_origin,
        range_established_index=established,
        evaluated_index=end,
        state="ESTABLISHED_RANGE_LINKED_TO_TREND_EVOLUTION",
        trade_eligible=False,
    )


def classify_small_pullback_trend(
    candles: tuple[Candle, ...],
    *,
    direction: str,
    evaluated_index: int | None = None,
) -> SmallPullbackTrendIdentity | None:
    """BROOKS-GAP-025: pullback depth/duration/spacing are explicit, not count-only."""
    if direction not in {"LONG","SHORT"} or len(candles)<5:
        return None
    end=len(candles)-1 if evaluated_index is None else min(evaluated_index,len(candles)-1)
    start=max(0,end-9)  # ENGINEERING_SEARCH_POLICY replacing legacy opaque 10-bar count proxy.
    seg=tuple(candles[start:end+1])
    med=_median_range(seg)
    if med<=0:
        return None
    episodes=[]; run=[]; anchor=seg[0].close
    for c in seg:
        counter=c.close<c.open if direction=="LONG" else c.close>c.open
        if counter:
            run.append(c)
        elif run:
            episodes.append(tuple(run)); run=[]
        anchor=c.close if not counter else anchor
    if run: episodes.append(tuple(run))
    max_run=max((len(x) for x in episodes),default=0)
    depths=[]
    for ep in episodes:
        if direction=="LONG":
            depths.append(max(x.high for x in ep)-min(x.low for x in ep))
        else:
            depths.append(max(x.high for x in ep)-min(x.low for x in ep))
    max_depth=max(depths,default=Decimal("0"))
    shallow=max_depth<=med*Decimal("1.50")  # ENGINEERING_CLASSIFICATION_POLICY
    infrequent=len(episodes)<=3 and max_run<=2  # ENGINEERING_CLASSIFICATION_POLICY
    aligned=sum((c.close>c.open) if direction=="LONG" else (c.close<c.open) for c in seg)
    urgent=Decimal(aligned)/Decimal(len(seg))>=Decimal("0.60")  # ENGINEERING_CLASSIFICATION_POLICY
    later_expansion=len(depths)>=2 and depths[-1]>max(depths[:-1])
    state="ACTIVE_SMALL_PULLBACK_TREND" if shallow and infrequent and urgent else "NOT_SMALL_PULLBACK_TREND"
    if later_expansion and state=="ACTIVE_SMALL_PULLBACK_TREND":
        state="SMALL_PULLBACK_TREND_WITH_LATER_EXPANSION"
    return SmallPullbackTrendIdentity(
        f"SMALL_PULLBACK:{direction}:{start}",direction,start,end,len(episodes),max_run,max_depth,med,later_expansion,state,False
    )


def _tight_channel_direction(snapshot: MarketSnapshot, policy: BrooksFullCorePolicy) -> str:
    window = snapshot.candles[-policy.tight_channel_window_bars :]
    if len(window) < policy.tight_channel_window_bars:
        return "UNRESOLVED"
    direction = "LONG" if window[-1].close > window[0].close else "SHORT"
    max_countertrend, aligned = _directional_pullback_runs(window, direction)
    fraction = Decimal(aligned) / Decimal(len(window))
    if max_countertrend <= 3 and fraction >= policy.context.min_directional_bar_fraction:
        return direction
    return "UNRESOLVED"


def _spike(snapshot: MarketSnapshot, policy: BrooksFullCorePolicy):
    """BROOKS-GAP-021: latest full contiguous strong-bar spike within engineering scan span."""
    candles = snapshot.candles
    start_scan = max(0, len(candles) - policy.spike_channel_scan_bars)  # ENGINEERING_SEARCH_POLICY
    best = None
    i = start_scan
    while i < len(candles):
        direction = None
        if is_strong_bull_bar(candles[i], policy.context):
            direction = "LONG"
        elif is_strong_bear_bar(candles[i], policy.context):
            direction = "SHORT"
        if direction is None:
            i += 1
            continue
        j = i
        while j + 1 < len(candles):
            nxt = candles[j + 1]
            aligned = (
                is_strong_bull_bar(nxt, policy.context)
                if direction == "LONG"
                else is_strong_bear_bar(nxt, policy.context)
            )
            if not aligned:
                break
            j += 1
        if j - i + 1 >= 2:
            best = (i, j, direction)
        i = max(i + 1, j + 1)
    return candles, best

def assess_advanced_context(
    snapshot: MarketSnapshot,
    *,
    policy: BrooksFullCorePolicy,
) -> AdvancedBrooksContext:
    tight_direction = _tight_channel_direction(snapshot, policy)
    candles, spike = _spike(snapshot, policy)
    spike_channel = "UNRESOLVED"
    measured_direction = "UNRESOLVED"
    measured_target = None
    spike_measured_move_identity = None
    reasons: list[str] = []

    if tight_direction != "UNRESOLVED":
        reasons.append(f"tight_channel={tight_direction}")

    phase = "TRANSITION"
    phase_direction = "UNRESOLVED"
    if spike is not None:
        start, end, direction = spike
        phase_direction = direction
        if len(candles) - 1 - end <= 2:
            phase = "SPIKE"
        after = candles[end + 1 :]
        if after:
            pullback_seen = any(
                c.close < c.open if direction == "LONG" else c.close > c.open
                for c in after[:-1]
            )
            resumed = (
                after[-1].close > after[-1].open
                if direction == "LONG"
                else after[-1].close < after[-1].open
            )
            if pullback_seen and resumed:
                spike_channel = direction
                phase = "SPIKE_CHANNEL"
                reasons.append(f"spike_channel={direction}")

        first = candles[start]
        last = candles[end]
        open_close_magnitude = (
            last.close - first.open
            if direction == "LONG"
            else first.open - last.close
        )
        extreme_magnitude = (
            last.high - first.low
            if direction == "LONG"
            else first.high - last.low
        )
        if open_close_magnitude > 0 and extreme_magnitude > 0:
            measured_direction = direction
            measured_target = (
                last.close + open_close_magnitude
                if direction == "LONG"
                else last.close - open_close_magnitude
            )
            extreme_target = (
                last.high + extreme_magnitude
                if direction == "LONG"
                else last.low - extreme_magnitude
            )
            spike_measured_move_identity = SpikeMeasuredMoveIdentity(
                spike_id=f"SPIKE:{direction}:{start}:{end}",
                direction=direction,
                start_index=start,
                end_index=end,
                available_at_index=end,
                open_close_target=measured_target,
                extreme_target=extreme_target,
            )
            reasons.append(f"measured_move_from_full_spike={direction}:{start}:{end}")

    if phase == "TRANSITION" and tight_direction != "UNRESOLVED":
        phase = "TIGHT_CHANNEL"
        phase_direction = tight_direction

    micro=classify_micro_channel_identity(snapshot.candles,policy)
    spike_lifecycle=classify_spike_channel_lifecycle(snapshot,policy)
    evo=None
    if spike_lifecycle is not None:
        evo=classify_trend_range_evolution(
            snapshot.candles,direction=spike_lifecycle.direction,
            origin_index=spike_lifecycle.spike_start_index,
        )
    spt_direction=phase_direction if phase_direction in {"LONG","SHORT"} else tight_direction
    spt=classify_small_pullback_trend(snapshot.candles,direction=spt_direction) if spt_direction in {"LONG","SHORT"} else None

    return AdvancedBrooksContext(
        market_phase=phase,
        phase_direction=phase_direction,
        tight_channel_direction=tight_direction,
        spike_channel_direction=spike_channel,
        measured_move_direction=measured_direction,
        measured_move_target=measured_target,
        spike_measured_move_identity=spike_measured_move_identity,
        opening_reversal_available=False,
        micro_channel_state=micro.state if micro is not None else "UNRESOLVED",
        micro_channel_direction=micro.direction if micro is not None else "UNRESOLVED",
        spike_channel_state=spike_lifecycle.state if spike_lifecycle is not None else "UNRESOLVED",
        trend_range_state=evo.state if evo is not None else "UNRESOLVED",
        small_pullback_trend_state=spt.state if spt is not None else "UNRESOLVED",
        reasons=tuple(reasons),
    )
