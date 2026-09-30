from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.engine_contract import TargetPlanLifecycle, TargetSourceEvidence
from app.modules.brooks_core.books_full_entities import BrooksPatternScan
from test_brooks_wave18_semantics import (
    P, adv_none, bar, breakout_snapshot, candidate, failure_obs, fake_channel,
    flat_bars, range_md, range_plan, snap,
)


def test_scenario_021_full_three_bar_spike():
    from app.modules.brooks_core.advanced_context import _spike
    cs=[bar(0,100,111,99,110),bar(1,110,121,109,120),bar(2,120,131,119,130),bar(3,130,132,128,130)]
    with patch("app.modules.brooks_core.advanced_context.is_strong_bull_bar", side_effect=lambda c,p:c.close>c.open and c.close-c.open>=D("8")),          patch("app.modules.brooks_core.advanced_context.is_strong_bear_bar", return_value=False):
        _,x=_spike(snap(cs),P)
    assert x==(0,2,"LONG")


def test_scenario_021_one_bar_near_miss():
    from app.modules.brooks_core.advanced_context import _spike
    cs=[bar(0,100,111,99,110),bar(1,110,112,108,110)]
    with patch("app.modules.brooks_core.advanced_context.is_strong_bull_bar", side_effect=lambda c,p:c.close>c.open and c.close-c.open>=D("8")),          patch("app.modules.brooks_core.advanced_context.is_strong_bear_bar", return_value=False):
        _,x=_spike(snap(cs),P)
    assert x is None


def test_scenario_022_channel_breakout_positive():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","BREAKOUT")
    with patch("app.modules.brooks_core.books_full_engine.build_trend_channel_geometry",return_value=fake_channel("LONG")),          patch("app.modules.brooks_core.books_full_engine.classify_channel_boundary_event",return_value=SimpleNamespace(state="CHANNEL_LINE_BREAK",boundary_value=D("110"))):
        out=e._channel_target_sources(snap(flat_bars()),c)
    assert any(x[1].source_type=="CHANNEL_BREAKOUT_MEASURED_MOVE" for x in out)


def test_scenario_022_channel_touch_negative():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","BREAKOUT")
    with patch("app.modules.brooks_core.books_full_engine.build_trend_channel_geometry",return_value=fake_channel("LONG")),          patch("app.modules.brooks_core.books_full_engine.classify_channel_boundary_event",return_value=SimpleNamespace(state="CHANNEL_LINE_TEST",boundary_value=D("110"))):
        out=e._channel_target_sources(snap(flat_bars()),c)
    assert not any(x[1].source_type=="CHANNEL_BREAKOUT_MEASURED_MOVE" for x in out)


def test_scenario_023_trend_magnets_positive():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","TREND_CONTINUATION",metadata=(("reference_level","106"),))
    plan=TargetPlanLifecycle("P","TREND_TRADE","LONG",20)
    with patch.object(e,"_channel_target_sources",return_value=[]), patch.object(e,"_failed_reversal_target_sources",return_value=[]):
        out=e._source_target_pool(snap(flat_bars()),c,entry=D("90"),recent_average_range=D("4"),tick=D(".1"),advanced=adv_none(),target_plan=plan)
    assert {"MOVING_AVERAGE_TEST","BREAKOUT_TEST_LEVEL"} <= {x[1].source_type for x in out}


def test_scenario_023_no_forward_room_near_miss():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","TREND_CONTINUATION")
    plan=TargetPlanLifecycle("P","TREND_TRADE","LONG",20)
    with patch.object(e,"_channel_target_sources",return_value=[]), patch.object(e,"_failed_reversal_target_sources",return_value=[]):
        out=e._source_target_pool(snap(flat_bars()),c,entry=D("110"),recent_average_range=D("4"),tick=D(".1"),advanced=adv_none(),target_plan=plan)
    assert not any(x[1].source_type=="MOVING_AVERAGE_TEST" for x in out)


def test_scenario_046_midpoint_positive():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","TRADING_RANGE_FADE",metadata=range_md())
    with patch.object(e,"_channel_target_sources",return_value=[]), patch.object(e,"_failed_reversal_target_sources",return_value=[]):
        out=e._source_target_pool(snap(flat_bars()),c,entry=D("96"),recent_average_range=D("4"),tick=D(".1"),advanced=adv_none(),target_plan=range_plan())
    assert any(x[1].source_type=="RANGE_MIDPOINT" for x in out)


def test_scenario_046_midpoint_no_room_negative():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","TRADING_RANGE_FADE",metadata=range_md())
    with patch.object(e,"_channel_target_sources",return_value=[]), patch.object(e,"_failed_reversal_target_sources",return_value=[]):
        out=e._source_target_pool(snap(flat_bars()),c,entry=D("101"),recent_average_range=D("4"),tick=D(".1"),advanced=adv_none(),target_plan=range_plan())
    assert not any(x[1].source_type=="RANGE_MIDPOINT" for x in out)


def test_scenario_047_confirmed_failure_positive():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","MAJOR_TREND_REVERSAL")
    with patch("app.modules.brooks_core.books_full_engine.scan_full_brooks_patterns",return_value=BrooksPatternScan((),(failure_obs(True),),())):
        out=e._failed_reversal_target_sources(snap(flat_bars()),c,D(".1"))
    assert any(x[1].source_type=="FAILED_REVERSAL_ENTRY_PRICE" for x in out)


def test_scenario_047_price_without_origin_negative():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","MAJOR_TREND_REVERSAL")
    with patch("app.modules.brooks_core.books_full_engine.scan_full_brooks_patterns",return_value=BrooksPatternScan((),(),())):
        assert e._failed_reversal_target_sources(snap(flat_bars()),c,D(".1"))==[]


def test_scenario_048_multiple_meanings_same_price():
    e=BrooksTrilogyFullCoreEngine(policy=P)
    a=TargetSourceEvidence("RANGE_MIDPOINT","A",0,10,"LONG","R")
    b=TargetSourceEvidence("FAILED_REVERSAL_ENTRY_PRICE","B",1,10,"LONG","F")
    typed,basis=e._coalesce_target_identities([(D("110"),a,"mid"),(D("110"),b,"failed")],signal_index=20)
    _,final,_=e._arbitrate_target_identities(typed,entry=D("100"),direction="LONG",signal_index=20,basis_by_source_id=basis)
    assert len(final)==1 and len(final[0].sources)==2


def test_scenario_048_nearest_price_does_not_discard_far_semantic_target():
    e=BrooksTrilogyFullCoreEngine(policy=P)
    a=TargetSourceEvidence("RANGE_MIDPOINT","A",0,10,"LONG","R")
    b=TargetSourceEvidence("OPPOSITE_RANGE_BOUNDARY","B",0,10,"LONG","R")
    typed,basis=e._coalesce_target_identities([(D("105"),a,"mid"),(D("120"),b,"edge")],signal_index=20)
    targets,_,_=e._arbitrate_target_identities(typed,entry=D("100"),direction="LONG",signal_index=20,basis_by_source_id=basis)
    assert targets==(D("105"),D("120"))


def test_scenario_049_range_height_positive():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","BREAKOUT",metadata=range_md())
    plan=TargetPlanLifecycle("P","BREAKOUT_TRANSITION","LONG",20,range_id="RANGE:0:19")
    with patch.object(e,"_channel_target_sources",return_value=[]),patch.object(e,"_failed_reversal_target_sources",return_value=[]):
        out=e._source_target_pool(breakout_snapshot(True,True),c,entry=D("105.1"),recent_average_range=D("4"),tick=D(".1"),advanced=adv_none(),target_plan=plan)
    assert any(x[1].source_type=="RANGE_HEIGHT_MEASURED_MOVE" for x in out)


def test_scenario_049_failed_breakout_no_range_height_projection():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","BREAKOUT",metadata=range_md())
    plan=TargetPlanLifecycle("P","BREAKOUT_TRANSITION","LONG",20,range_id="RANGE:0:19")
    with patch.object(e,"_channel_target_sources",return_value=[]),patch.object(e,"_failed_reversal_target_sources",return_value=[]):
        out=e._source_target_pool(breakout_snapshot(True,False),c,entry=D("104.1"),recent_average_range=D("4"),tick=D(".1"),advanced=adv_none(),target_plan=plan)
    assert not any(x[1].source_type=="RANGE_HEIGHT_MEASURED_MOVE" for x in out)


def test_scenario_050_range_trade_state():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","TRADING_RANGE_FADE",metadata=range_md())
    assert e._target_plan_lifecycle(snap(flat_bars()),c,context=SimpleNamespace(regime="TRADING_RANGE")).state=="RANGE_TRADE"


def test_scenario_050_breakout_transition_state():
    e=BrooksTrilogyFullCoreEngine(policy=P); c=candidate("LONG","BREAKOUT",metadata=range_md())
    assert e._target_plan_lifecycle(breakout_snapshot(True,True),c,context=SimpleNamespace(regime="TRADING_RANGE")).state=="BREAKOUT_TRANSITION"


def test_scenario_target_source_multiplicity_preserved():
    e=BrooksTrilogyFullCoreEngine(policy=P)
    a=TargetSourceEvidence("RANGE_MIDPOINT","MID",0,10,"LONG","R")
    b=TargetSourceEvidence("FAILED_REVERSAL_ENTRY_PRICE","FAIL",1,10,"LONG","F")
    typed,_=e._coalesce_target_identities([(D("110"),a,"mid"),(D("110"),b,"fail")],signal_index=20)
    assert {x.source_id for x in typed[0].sources}=={"MID","FAIL"}


def test_scenario_entry_method_preserved_by_target_semantics():
    e=BrooksTrilogyFullCoreEngine(policy=P)
    md=range_md()+(
        ("entry_method","LIMIT_OR_MARKET_FADE"),
        ("entry_trigger_semantic","AT_OR_NEAR_CANONICAL_RANGE_EDGE"),
        ("entry_reference_price","96"),
        ("economic_opportunity_id","RANGE_FADE:R:LONG:20"),
    )
    c=candidate("LONG","TRADING_RANGE_FADE",metadata=md)
    assert e._entry_execution_intent(c).entry_method=="LIMIT_OR_MARKET_FADE"


def test_scenario_no_new_economic_candidate_from_target_plan():
    plan=TargetPlanLifecycle("P","RANGE_TRADE","LONG",20,range_id="RANGE:0:19")
    assert plan.trade_eligible is False


def test_scenario_gate3_htf_contract_not_reimplemented_by_wave18():
    plan=TargetPlanLifecycle("P","TREND_TRADE","LONG",20)
    assert not hasattr(plan,"htf_aligned")


def test_scenario_mtr_gt12_policy_not_reintroduced():
    import inspect
    from app.modules.brooks_core import books_full_engine
    text=inspect.getsource(books_full_engine.BrooksTrilogyFullCoreEngine)
    assert "mtr_retest_max_bars" not in text


def test_scenario_final_flag_gt6_policy_not_reintroduced():
    import inspect
    from app.modules.brooks_core import books_full_engine
    text=inspect.getsource(books_full_engine.BrooksTrilogyFullCoreEngine)
    assert "final_flag_window_bars" not in text


def test_scenario_wave19_080_not_implemented():
    import inspect
    from app.modules.brooks_core import books_full_engine
    assert "BROOKS-GAP-080" not in inspect.getsource(books_full_engine)
