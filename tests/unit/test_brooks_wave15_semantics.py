from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.candidate_scoring import score_candidate
from app.modules.brooks_core.market_context import (
    BrooksMarketContext,
    CandidateHTFAlignment,
    HigherTimeframeContextIdentity,
    _htf_context_identity,
    aggregate_relevant_higher_timeframes,
    aggregate_to_higher_timeframe,
    relevant_higher_timeframes,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,9,1,tzinfo=UTC)
P=BrooksFullCorePolicy()

def bar(i, *, minutes=5, o=100, h=102, l=98, c=101):
    t=BASE+timedelta(minutes=minutes*i)
    return Candle(t,t+timedelta(minutes=minutes),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D("1"))

def snap(candles, timeframe="5m", captured_at=None):
    candles=tuple(candles)
    return MarketSnapshot(
        exchange="binance",market_type="futures",symbol="BTCUSDT",timeframe=timeframe,
        candles=candles,captured_at=captured_at or candles[-1].close_time,source="W15_TEST"
    )

def htf(tf="15m", side="LONG", location="AT_HTF_SUPPORT", always_in=None, n=1):
    ai=always_in if always_in is not None else side
    regime="BULL_TREND" if side=="LONG" else "BEAR_TREND" if side=="SHORT" else "TRADING_RANGE"
    return HigherTimeframeContextIdentity(
        timeframe=tf,context_id=f"HTF:{tf}:{n}",regime=regime,always_in=ai,
        directional_side=side,structural_location=location,support=D("90"),resistance=D("110"),
        range_low=D("90"),range_high=D("110"),channel_direction=side,
        available_at=BASE+timedelta(hours=n),trade_eligible=False,
    )

def mc(contexts=(), *, local_regime="TRADING_RANGE", local_ai="UNRESOLVED", legacy_alignment="ALIGNED"):
    return BrooksMarketContext(
        regime=local_regime,always_in=local_ai,trend_strength=D(".5"),trading_range_probability=D(".5"),
        volatility_ratio=D(".01"),compression_expansion_ratio=D("1"),volatility_state="BALANCED",
        channel_quality="UNRESOLVED",channel_direction="UNRESOLVED",swing_quality=D(".5"),
        location="MID_RANGE_OR_CHANNEL",support=D("90"),resistance=D("110"),
        measured_move_probability=D("0"),measured_move_target=None,measured_move_failure=False,
        higher_timeframe=contexts[0].timeframe if contexts else None,
        higher_timeframe_regime=contexts[0].regime if contexts else "UNAVAILABLE",
        timeframe_alignment=legacy_alignment,higher_timeframe_agreement=D("1") if legacy_alignment=="ALIGNED" else D(".5"),
        higher_timeframe_contexts=tuple(contexts),
    )

def candidate(direction):
    return SimpleNamespace(direction=direction,setup_type=f"W15_{direction}",rule_evidence=())

# GAP-070: candidate-relative directional HTF alignment

def test_070_long_with_bullish_htf_is_aligned():
    x=mc((htf(side="LONG"),)).candidate_htf_alignment("LONG")
    assert x.state=="ALIGNED_WITH_CANDIDATE" and x.candidate_direction=="LONG"

def test_070_long_with_bearish_htf_is_opposed():
    assert mc((htf(side="SHORT"),)).candidate_htf_alignment("LONG").state=="OPPOSED_TO_CANDIDATE"

def test_070_short_with_bearish_htf_is_aligned():
    assert mc((htf(side="SHORT"),)).candidate_htf_alignment("SHORT").state=="ALIGNED_WITH_CANDIDATE"

def test_070_short_with_bullish_htf_is_opposed():
    assert mc((htf(side="LONG"),)).candidate_htf_alignment("SHORT").state=="OPPOSED_TO_CANDIDATE"

def test_070_ambiguous_htf_not_silently_aligned():
    x=mc((htf(side="UNRESOLVED",always_in="UNRESOLVED"),)).candidate_htf_alignment("LONG")
    assert x.state=="AMBIGUOUS_HTF" and not x.aligned_context_ids

def test_070_same_htf_strength_opposite_candidate_direction_scores_differ():
    ctx=mc((htf(side="LONG"),),local_regime="TRADING_RANGE",legacy_alignment="ALIGNED")
    long=score_candidate(candidate("LONG"),risk_score=50,market_context=ctx)
    short=score_candidate(candidate("SHORT"),risk_score=50,market_context=ctx)
    assert long.context_quality > short.context_quality

def test_070_directionless_legacy_alignment_cannot_support_opposite_candidate():
    ctx=mc((htf(side="LONG"),),local_regime="TRADING_RANGE",legacy_alignment="ALIGNED")
    assert ctx.timeframe_alignment=="ALIGNED"
    assert ctx.candidate_htf_alignment("SHORT").state=="OPPOSED_TO_CANDIDATE"
    assert ctx.direction_alignment("SHORT") < ctx.direction_alignment("LONG")

def test_070_mixed_htf_is_not_silently_positive():
    x=mc((htf("15m","LONG",n=1),htf("1h","SHORT",n=2))).candidate_htf_alignment("LONG")
    assert x.state=="MIXED_DIRECTIONAL_HTF"

def test_070_incomplete_future_htf_candle_is_not_used():
    # 61 x 5m bars => 20 complete 15m bars plus one incomplete 15m bucket.
    candles=[bar(i) for i in range(61)]
    s=snap(candles,captured_at=candles[-1].close_time)
    agg=aggregate_to_higher_timeframe(s,"15m")
    assert agg is not None and len(agg.candles)==20
    assert agg.candles[-1].close_time <= s.captured_at

def test_070_prefix_future_close_does_not_relabel_earlier_aggregate():
    pre=[bar(i) for i in range(61)]
    a=aggregate_to_higher_timeframe(snap(pre),"15m")
    post=pre+[bar(61),bar(62)]
    b=aggregate_to_higher_timeframe(snap(post),"15m")
    assert a is not None and b is not None
    assert len(a.candles)==20 and len(b.candles)==21
    assert a.candles==b.candles[:20]

# GAP-071: structural HTF location context only

def test_071_long_supportive_htf_location():
    assert mc((htf(side="LONG",location="AT_HTF_SUPPORT"),)).candidate_htf_location_state("LONG")=="SUPPORTIVE_HTF_LOCATION"

def test_071_short_resistance_supportive_htf_location():
    assert mc((htf(side="SHORT",location="AT_HTF_RESISTANCE"),)).candidate_htf_location_state("SHORT")=="SUPPORTIVE_HTF_LOCATION"

def test_071_long_at_htf_resistance_is_opposed_location():
    assert mc((htf(side="LONG",location="AT_HTF_RESISTANCE"),)).candidate_htf_location_state("LONG")=="OPPOSED_HTF_LOCATION"

def test_071_htf_range_middle_is_neutral_not_entry():
    ctx=htf(side="UNRESOLVED",location="HTF_RANGE_MIDDLE",always_in="UNRESOLVED")
    assert mc((ctx,)).candidate_htf_location_state("LONG")=="NEUTRAL_HTF_LOCATION"
    assert ctx.trade_eligible is False

def test_071_htf_location_identity_preserves_levels_and_time():
    x=htf(side="LONG",location="AT_HTF_RANGE_LOW_EDGE")
    assert x.support==D("90") and x.resistance==D("110")
    assert x.range_low==D("90") and x.range_high==D("110")
    assert x.available_at.tzinfo is not None and x.trade_eligible is False

def test_071_context_alone_never_owns_trade_eligibility():
    for loc in ("AT_HTF_SUPPORT","AT_HTF_RESISTANCE","AT_HTF_RANGE_LOW_EDGE","AT_HTF_RANGE_HIGH_EDGE"):
        assert htf(location=loc).trade_eligible is False

# GAP-075: multiple relevant HTFs, not fixed immediately adjacent

def test_075_relevant_htf_search_not_fixed_to_next_only():
    assert relevant_higher_timeframes("5m")==("15m","1h","1d")
    assert relevant_higher_timeframes("15m")==("1h","1d")

def test_075_multiple_available_htfs_are_aggregated_causally():
    candles=[bar(i) for i in range(240)]
    found=aggregate_relevant_higher_timeframes(snap(candles))
    assert tuple(x.timeframe for x in found)==("15m","1h")
    assert all(x.candles[-1].close_time <= snap(candles).captured_at for x in found)

def test_075_daily_context_absent_when_history_insufficient_not_fabricated():
    candles=[bar(i) for i in range(240)]
    found=aggregate_relevant_higher_timeframes(snap(candles))
    assert "1d" not in {x.timeframe for x in found}

def test_075_unsupported_or_nonhigher_target_fails_closed():
    candles=[bar(i) for i in range(100)]
    s=snap(candles)
    assert aggregate_to_higher_timeframe(s,"5m") is None
    assert aggregate_to_higher_timeframe(s,"bogus") is None

def test_075_timeframe_search_policy_is_explicitly_finite_engineering_policy():
    assert set(relevant_higher_timeframes("5m")) <= {"15m","1h","1d"}

# GAP-076: preserve HTF Always-In as distinct from regime

def trend_15m(n=40, direction="LONG"):
    out=[]
    for i in range(n):
        if direction=="LONG":
            o=100+i; c=o+2; h=c+1; l=o-1
        else:
            o=200-i; c=o-2; h=o+1; l=c-1
        out.append(bar(i,minutes=15,o=o,h=h,l=l,c=c))
    return out

def test_076_htf_identity_exposes_always_in_not_just_regime():
    ident=_htf_context_identity(snap(trend_15m(),"15m"),P)
    assert ident.always_in in {"LONG","SHORT","UNRESOLVED"}
    assert hasattr(ident,"regime") and hasattr(ident,"always_in")

def test_076_resolved_always_in_can_define_directional_side():
    x=htf(side="LONG",always_in="LONG")
    assert x.always_in=="LONG" and x.directional_side=="LONG"

def test_076_unresolved_always_in_does_not_invent_direction_from_boolean_strength():
    x=HigherTimeframeContextIdentity(
        timeframe="1h",context_id="H",regime="TRADING_RANGE",always_in="UNRESOLVED",
        directional_side="UNRESOLVED",structural_location="HTF_RANGE_MIDDLE",
        support=D("90"),resistance=D("110"),range_low=D("90"),range_high=D("110"),
        channel_direction="UNRESOLVED",available_at=BASE,trade_eligible=False,
    )
    assert mc((x,)).candidate_htf_alignment("LONG").state=="AMBIGUOUS_HTF"

def test_076_htf_always_in_context_remains_context_only():
    assert htf(side="SHORT",always_in="SHORT").trade_eligible is False

def test_076_candidate_direction_mirror_uses_same_htf_identity():
    ctx=mc((htf(side="SHORT",always_in="SHORT"),))
    assert ctx.candidate_htf_alignment("SHORT").state=="ALIGNED_WITH_CANDIDATE"
    assert ctx.candidate_htf_alignment("LONG").state=="OPPOSED_TO_CANDIDATE"
