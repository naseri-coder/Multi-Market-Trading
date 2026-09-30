from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import app.modules.brooks_core.books_full_patterns as patterns
from app.modules.brooks_core.books_full_entities import (
    BrooksPatternCandidate, BrooksPatternObservation, BrooksPatternScan,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.correction_lifecycle import MTRRetestLifecycle
from app.modules.brooks_core.market_context import (
    BrooksMarketContext,
    HigherTimeframeContextIdentity,
    HTFPatternIdentity,
    MultiTimeframePatternLink,
    HTFFailedBreakoutContext,
    NestedHTFMTRContext,
    _htf_nested_pattern_state,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,9,1,tzinfo=UTC)
P=BrooksFullCorePolicy()

def bar(i, *, minutes=15, o=100, h=102, l=98, c=101):
    t=BASE+timedelta(minutes=minutes*i)
    return Candle(t,t+timedelta(minutes=minutes),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D("1"))

def snap(n=24, timeframe="15m"):
    cs=tuple(bar(i) for i in range(n))
    return MarketSnapshot("binance","futures","BTCUSDT",timeframe,cs,cs[-1].close_time,"W16_TEST")

def htf_context(tf="15m", n=20, side="LONG"):
    at=BASE+timedelta(minutes=15*n)
    return HigherTimeframeContextIdentity(
        timeframe=tf,context_id=f"HTF:{tf}:{n}",regime="BULL_TREND" if side=="LONG" else "BEAR_TREND",
        always_in=side,directional_side=side,structural_location="AT_HTF_SUPPORT" if side=="LONG" else "AT_HTF_RESISTANCE",
        support=D("90"),resistance=D("110"),range_low=None,range_high=None,
        channel_direction=side,available_at=at,trade_eligible=False,
    )

def parent_pattern(*, tf="15m", pid="HTF_DOUBLE_BOTTOM_LONG", direction="LONG", n=20, origin="DB:1"):
    at=BASE+timedelta(minutes=15*n)
    return HTFPatternIdentity(
        timeframe=tf,pattern_identity_id=f"HTF_PATTERN:{tf}:{pid}:{n}:{origin}",
        parent_context_id=f"HTF:{tf}:{n}",pattern_id=pid,role="HTF_CANDIDATE_PATTERN_CONTEXT",
        direction=direction,signal_index=n,origin_id=origin,lifecycle_state="CANDIDATE_AVAILABLE",
        available_at=at,trade_eligible=False,
    )

def failed_context(*, direction="LONG", n=20, event="FAILED_BREAKOUT", origin="BO:1"):
    at=BASE+timedelta(minutes=15*n)
    return HTFFailedBreakoutContext(
        timeframe="15m",context_id=f"HTF_{event}:{origin}:{n}",parent_context_id=f"HTF:15m:{n}",
        event_type=event,breakout_origin_id=origin,reversal_direction=direction if event=="FAILED_BREAKOUT" else "UNRESOLVED",
        state="CONFIRMED_BY_NEXT_BAR_FOLLOW_THROUGH" if event=="FAILED_BREAKOUT" else "BREAKOUT_TEST",
        event_index=n,available_at=at,trade_eligible=False,
    )

def mtr_context(*, direction="LONG", n=20, episode="MTR:BEAR_TREND:4:12", state="RETEST_CONFIRMED_WAITING_SECOND_REVERSAL"):
    at=BASE+timedelta(minutes=15*n)
    return NestedHTFMTRContext(
        timeframe="15m",context_id=f"HTF_MTR:15m:{episode}:{n}",parent_context_id=f"HTF:15m:{n}",
        mtr_episode_id=episode,prior_trend_direction="BEAR_TREND" if direction=="LONG" else "BULL_TREND",
        reversal_direction=direction,state=state,old_extreme_index=4,structure_break_index=12,
        retest_index=18,second_reversal_index=None,available_at=at,trade_eligible=False,
    )

def mc(*, patterns_=(), failures=(), mtrs=(), evaluated=None):
    evaluated=evaluated or BASE+timedelta(hours=8)
    return BrooksMarketContext(
        regime="TRADING_RANGE",always_in="UNRESOLVED",trend_strength=D(".5"),trading_range_probability=D(".5"),
        volatility_ratio=D(".01"),compression_expansion_ratio=D("1"),volatility_state="BALANCED",
        channel_quality="UNRESOLVED",channel_direction="UNRESOLVED",swing_quality=D(".5"),
        location="MID_RANGE_OR_CHANNEL",support=D("90"),resistance=D("110"),
        measured_move_probability=D("0"),measured_move_target=None,measured_move_failure=False,
        higher_timeframe="15m",higher_timeframe_regime="BULL_TREND",timeframe_alignment="ALIGNED",
        higher_timeframe_agreement=D("1"),higher_timeframe_contexts=(htf_context(),),
        native_timeframe="5m",evaluated_at=evaluated,higher_timeframe_patterns=tuple(patterns_),
        higher_timeframe_failed_breakouts=tuple(failures),higher_timeframe_mtr_contexts=tuple(mtrs),
    )

def native_candidate(direction="LONG"):
    return BrooksPatternCandidate(
        direction=direction,setup_type="MICRO_DOUBLE_BOTTOM_LONG" if direction=="LONG" else "MICRO_DOUBLE_TOP_SHORT",
        family="DOUBLE_TOP_BOTTOM_REVERSAL",signal_index=30,reasons=("structural_second_test","entry_method_owned"),
        source_rule_ids=("BB-REV-MICRO-DOUBLE-TOP-BOTTOM",),taxonomy="SOURCE_INTERPRETATION",priority=20,
        context_required="REVERSAL_OR_RANGE_EXTREME",
        metadata=(("entry_method","LIMIT_OR_MARKET_ANTICIPATION"),("economic_opportunity_id","MICRO_DOUBLE:DB:1:LONG")),
    )

# BROOKS-GAP-072

def test_072_native_pattern_links_to_specific_htf_parent_identity():
    p=parent_pattern()
    links=mc(patterns_=(p,)).multitimeframe_links("MICRO_DOUBLE_BOTTOM_LONG",30,"LONG")
    assert len(links)==1
    x=links[0]
    assert isinstance(x,MultiTimeframePatternLink)
    assert x.parent_pattern_id==p.pattern_identity_id and x.parent_context_id==p.parent_context_id
    assert x.native_pattern_id=="MICRO_DOUBLE_BOTTOM_LONG" and x.candidate_direction=="LONG"
    assert x.trade_eligible is False

def test_072_opposite_direction_parent_is_not_false_parent():
    assert mc(patterns_=(parent_pattern(direction="SHORT"),)).multitimeframe_links("X",30,"LONG")==()

def test_072_future_parent_pattern_is_not_backdated():
    future=parent_pattern(n=40)
    early=BASE+timedelta(minutes=15*30)
    assert mc(patterns_=(future,),evaluated=early).multitimeframe_links("X",30,"LONG")==()

def test_072_parent_pattern_is_context_not_entry():
    p=parent_pattern()
    assert p.trade_eligible is False
    assert mc(patterns_=(p,)).multitimeframe_links("X",30,"LONG")[0].trade_eligible is False

def test_072_candidate_metadata_states_current_and_parent_pattern_together():
    p=parent_pattern()
    out=patterns._attach_multitimeframe_nesting(native_candidate(),mc(patterns_=(p,)))
    md=dict(out.metadata)
    assert md["current_tf_pattern"]=="MICRO_DOUBLE_BOTTOM_LONG"
    assert p.pattern_identity_id in md["htf_parent_pattern_ids"]
    assert p.parent_context_id in md["htf_parent_context_ids"]

def test_072_entry_method_and_economic_identity_are_preserved():
    out=patterns._attach_multitimeframe_nesting(native_candidate(),mc(patterns_=(parent_pattern(),)))
    md=dict(out.metadata)
    assert md["entry_method"]=="LIMIT_OR_MARKET_ANTICIPATION"
    assert md["economic_opportunity_id"]=="MICRO_DOUBLE:DB:1:LONG"

def test_072_normal_htf_scan_is_reused_for_parent_identity(monkeypatch):
    c=BrooksPatternCandidate(
        direction="LONG",setup_type="DOUBLE_BOTTOM_LONG",family="DOUBLE_TOP_BOTTOM_REVERSAL",signal_index=23,
        reasons=("structural_test","reversal_minimum"),source_rule_ids=("BB-REV-DOUBLE-TOP-BOTTOM",),
        taxonomy="SOURCE_INTERPRETATION",priority=20,context_required="REVERSAL_OR_RANGE_EXTREME",
        metadata=(("structure_id","DB:HTF:1"),),
    )
    monkeypatch.setattr(patterns,"scan_full_brooks_patterns",lambda *a,**k:BrooksPatternScan((c,),(),()))
    monkeypatch.setattr(patterns,"scan_major_trend_reversal_lifecycles",lambda *a,**k:())
    ps,fb,m=_htf_nested_pattern_state(snap(),P,htf_context(n=24))
    assert len(ps)==1 and ps[0].origin_id=="DB:HTF:1"
    assert ps[0].pattern_id=="DOUBLE_BOTTOM_LONG" and not fb and not m

# BROOKS-GAP-074

def test_074_failed_breakout_origin_is_directionally_available():
    f=failed_context(direction="LONG")
    got=mc(failures=(f,)).candidate_htf_failed_breakout_contexts("LONG")
    assert got==(f,) and got[0].breakout_origin_id=="BO:1"

def test_074_opposite_failed_breakout_is_not_linked_to_candidate():
    f=failed_context(direction="SHORT")
    assert mc(failures=(f,)).candidate_htf_failed_breakout_contexts("LONG")==()

def test_074_swing_test_is_structural_context_without_reversal_direction_promotion():
    t=failed_context(event="SWING_TEST",origin="TEST:1")
    assert mc(failures=(t,)).htf_swing_test_contexts()==(t,)
    assert t.reversal_direction=="UNRESOLVED" and t.trade_eligible is False

def test_074_failed_breakout_origin_is_attached_to_native_candidate():
    f=failed_context(direction="LONG",origin="BO:EXACT")
    out=patterns._attach_multitimeframe_nesting(native_candidate("LONG"),mc(failures=(f,)))
    md=dict(out.metadata)
    assert f.context_id in md["htf_failed_breakout_ids"]
    assert "BO:EXACT" in md["htf_failed_breakout_origin_ids"]

def test_074_future_failed_breakout_context_not_backdated():
    f=failed_context(direction="LONG",n=40)
    early=BASE+timedelta(minutes=15*30)
    assert mc(failures=(f,),evaluated=early).candidate_htf_failed_breakout_contexts("LONG")==()

def test_074_existing_wave10_observation_identity_is_consumed(monkeypatch):
    obs=BrooksPatternObservation(
        pattern_id="FAILED_BREAKOUT_CONTEXT_LONG",pattern_name="Failed Breakout",role="FAILURE_CONTEXT",
        signal_index=23,direction="SHORT",source_rule_ids=("BB-RNG-05-FAILED-BREAKOUT",),
        metadata=(("breakout_id","BO:HTF:23"),("confirmation_state","CONFIRMED_BY_NEXT_BAR_FOLLOW_THROUGH")),
    )
    monkeypatch.setattr(patterns,"scan_full_brooks_patterns",lambda *a,**k:BrooksPatternScan((),(obs,),()))
    monkeypatch.setattr(patterns,"scan_major_trend_reversal_lifecycles",lambda *a,**k:())
    ps,fb,m=_htf_nested_pattern_state(snap(),P,htf_context(n=24))
    assert len(fb)==1 and fb[0].breakout_origin_id=="BO:HTF:23"
    assert fb[0].reversal_direction=="SHORT" and fb[0].event_type=="FAILED_BREAKOUT"

def test_074_existing_wave10_breakout_test_is_consumed_without_entry_promotion(monkeypatch):
    obs=BrooksPatternObservation(
        pattern_id="BREAKOUT_TEST_LONG",pattern_name="Breakout Test",role="BREAKOUT_CONTEXT",
        signal_index=23,direction="LONG",source_rule_ids=("BB-RNG-BREAKOUT-TEST",),
        metadata=(("structure_id","TEST:HTF:23"),("kind","BREAKOUT_TEST")),
    )
    monkeypatch.setattr(patterns,"scan_full_brooks_patterns",lambda *a,**k:BrooksPatternScan((),(obs,),()))
    monkeypatch.setattr(patterns,"scan_major_trend_reversal_lifecycles",lambda *a,**k:())
    ps,fb,m=_htf_nested_pattern_state(snap(),P,htf_context(n=24))
    assert len(fb)==1 and fb[0].event_type=="SWING_TEST"
    assert fb[0].breakout_origin_id=="TEST:HTF:23" and fb[0].trade_eligible is False

# BROOKS-GAP-073

def test_073_nested_htf_mtr_episode_is_available_by_reversal_direction():
    x=mtr_context(direction="LONG")
    assert mc(mtrs=(x,)).candidate_htf_mtr_contexts("LONG")== (x,)

def test_073_opposite_mtr_direction_does_not_attach():
    x=mtr_context(direction="SHORT")
    assert mc(mtrs=(x,)).candidate_htf_mtr_contexts("LONG")==()

def test_073_mtr_episode_identity_and_state_attach_to_native_candidate():
    x=mtr_context(direction="LONG",episode="MTR:BEAR_TREND:7:14")
    out=patterns._attach_multitimeframe_nesting(native_candidate("LONG"),mc(mtrs=(x,)))
    md=dict(out.metadata)
    assert "MTR:BEAR_TREND:7:14" in md["htf_mtr_episode_ids"]
    assert "RETEST_CONFIRMED_WAITING_SECOND_REVERSAL" in md["htf_mtr_states"]

def test_073_future_htf_mtr_state_not_backdated():
    x=mtr_context(direction="LONG",n=40)
    early=BASE+timedelta(minutes=15*30)
    assert mc(mtrs=(x,),evaluated=early).candidate_htf_mtr_contexts("LONG")==()

def test_073_shared_wave08_mtr_lifecycle_is_consumed(monkeypatch):
    life=MTRRetestLifecycle(
        prior_trend_direction="BEAR_TREND",reversal_direction="LONG",
        mtr_episode_id="MTR:BEAR_TREND:4:12",old_extreme_index=4,structure_break_index=12,
        retest_index=18,second_reversal_index=None,active=True,state="RETEST_CONFIRMED_WAITING_SECOND_REVERSAL",
    )
    monkeypatch.setattr(patterns,"scan_full_brooks_patterns",lambda *a,**k:BrooksPatternScan((),(),()))
    monkeypatch.setattr(patterns,"scan_major_trend_reversal_lifecycles",lambda *a,**k:(life,))
    ps,fb,m=_htf_nested_pattern_state(snap(),P,htf_context(n=24))
    assert len(m)==1 and m[0].mtr_episode_id==life.mtr_episode_id
    assert m[0].state==life.state and m[0].reversal_direction=="LONG"
    assert m[0].trade_eligible is False

def test_073_nested_mtr_context_does_not_change_entry_method_or_economic_identity():
    out=patterns._attach_multitimeframe_nesting(native_candidate("LONG"),mc(mtrs=(mtr_context(),)))
    md=dict(out.metadata)
    assert md["entry_method"]=="LIMIT_OR_MARKET_ANTICIPATION"
    assert md["economic_opportunity_id"]=="MICRO_DOUBLE:DB:1:LONG"

def test_073_native_mtr_detector_still_uses_shared_lifecycle_symbol():
    assert callable(patterns.scan_major_trend_reversal_lifecycles)
    assert "scan_major_trend_reversal_lifecycles" in patterns.detect_major_trend_reversal.__code__.co_names
