from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_patterns import (
    detect_trading_range_fades,
    detect_anticipatory_reversal_entries,
    detect_micro_double_top_bottom,
    detect_final_flag,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.engine_contract import EntryExecutionIntent
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,9,18,tzinfo=UTC)
P=BrooksFullCorePolicy()

def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D("1"))

def snap(cs):
    cs=tuple(cs)
    return MarketSnapshot(exchange="binance",market_type="futures",symbol="BTCUSDT",timeframe="15m",candles=cs,captured_at=cs[-1].close_time,source="W14_TEST")

def tr_ctx():
    return SimpleNamespace(regime="TRADING_RANGE",always_in="UNRESOLVED",structure_direction="TRADING_RANGE",breakout_direction="UNRESOLVED",breakout_streak=0,metrics=SimpleNamespace(bar_overlap_rate=D(".7")))

def rev_ctx(regime="TRADING_RANGE",always_in="UNRESOLVED"):
    return SimpleNamespace(regime=regime,always_in=always_in,structure_direction=regime,breakout_direction="UNRESOLVED",breakout_streak=0,metrics=SimpleNamespace(bar_overlap_rate=D(".5")))

def market(subtype="BROAD_TRADING_RANGE", hierarchy=None, barbwire=False, location="AT_SUPPORT"):
    return SimpleNamespace(range_subtype=subtype,range_hierarchy=hierarchy,barbwire_active=barbwire,location=location,local_breakout_relation="NOT_NESTED")

def broad(is_broad=True, room="4"):
    return SimpleNamespace(is_broad=is_broad,state="BROAD_TRADING_RANGE",room_multiple=D(room))

def edge(direction="LONG", state=None):
    if state is None: state="AT_LOWER_RANGE_EDGE" if direction=="LONG" else "AT_UPPER_RANGE_EDGE"
    return SimpleNamespace(range_id="RANGE:10:29",low=D("90"),high=D("110"),engineering_tolerance=D("2"),state=state)

def range_bars(n=45):
    out=[]
    for i in range(n-1):
        out.append(bar(i,99+(i%2),110,90,100-(i%2)))
    out.append(bar(n-1,94,96,89,95))
    return out

def _range_patches(edge_side_effect):
    return (
        patch("app.modules.brooks_core.books_full_patterns.classify_broad_trading_range",return_value=broad()),
        patch("app.modules.brooks_core.books_full_patterns.classify_tight_trading_range",return_value=None),
        patch("app.modules.brooks_core.books_full_patterns.classify_barbwire_identity",return_value=None),
        patch("app.modules.brooks_core.books_full_patterns.classify_range_edge",side_effect=edge_side_effect),
    )

# GAP-045

def test_045_valid_broad_range_lower_edge_long_limit_fade():
    cs=range_bars()
    ps=_range_patches([edge("LONG"),edge("SHORT","RANGE_MIDDLE")])
    with ps[0],ps[1],ps[2],ps[3]:
        found=detect_trading_range_fades(snap(cs),tr_ctx(),P,market())
    item=next(x for x in found if x.direction=="LONG")
    m=dict(item.metadata)
    assert item.setup_type=="TRADING_RANGE_FADE_LONG"
    assert m["entry_method"]=="LIMIT_OR_MARKET_FADE"
    assert m["entry_reference_price"]=="90"
    assert m["range_id"]=="RANGE:10:29"

def test_045_valid_broad_range_upper_edge_short_mirror():
    cs=range_bars(); ps=_range_patches([edge("LONG","RANGE_MIDDLE"),edge("SHORT")])
    with ps[0],ps[1],ps[2],ps[3]:
        found=detect_trading_range_fades(snap(cs),tr_ctx(),P,market(location="AT_RESISTANCE"))
    item=next(x for x in found if x.direction=="SHORT")
    assert dict(item.metadata)["entry_reference_price"]=="110"

def test_045_range_middle_not_entry():
    cs=range_bars(); ps=_range_patches([edge("LONG","RANGE_MIDDLE"),edge("SHORT","RANGE_MIDDLE")])
    with ps[0],ps[1],ps[2],ps[3]:
        assert detect_trading_range_fades(snap(cs),tr_ctx(),P,market())==()

def test_045_ttr_is_suppressed():
    cs=range_bars()
    with patch("app.modules.brooks_core.books_full_patterns.classify_broad_trading_range",return_value=broad()),          patch("app.modules.brooks_core.books_full_patterns.classify_tight_trading_range",return_value=SimpleNamespace(is_tight=True)),          patch("app.modules.brooks_core.books_full_patterns.classify_barbwire_identity",return_value=None):
        assert detect_trading_range_fades(snap(cs),tr_ctx(),P,market())==()

def test_045_barbwire_is_suppressed():
    cs=range_bars()
    with patch("app.modules.brooks_core.books_full_patterns.classify_broad_trading_range",return_value=broad()),          patch("app.modules.brooks_core.books_full_patterns.classify_tight_trading_range",return_value=None),          patch("app.modules.brooks_core.books_full_patterns.classify_barbwire_identity",return_value=SimpleNamespace(is_barbwire=True)):
        assert detect_trading_range_fades(snap(cs),tr_ctx(),P,market(barbwire=True))==()

def test_045_local_edge_in_enclosing_middle_not_promoted():
    cs=range_bars()
    h=SimpleNamespace(nested=True,local_position="ENCLOSING_MIDDLE")
    ps=_range_patches([edge("LONG"),edge("SHORT","RANGE_MIDDLE")])
    with ps[0],ps[1],ps[2],ps[3]:
        assert detect_trading_range_fades(snap(cs),tr_ctx(),P,market(hierarchy=h))==()

def test_045_nested_enclosing_lower_location_can_trade_long():
    cs=range_bars()
    h=SimpleNamespace(nested=True,local_position="NEAR_ENCLOSING_LOW")
    ps=_range_patches([edge("LONG"),edge("SHORT","RANGE_MIDDLE")])
    with ps[0],ps[1],ps[2],ps[3]:
        found=detect_trading_range_fades(snap(cs),tr_ctx(),P,market(hierarchy=h))
    assert len(found)==1 and found[0].direction=="LONG"

def test_045_insufficient_broad_range_room_rejected():
    cs=range_bars()
    with patch("app.modules.brooks_core.books_full_patterns.classify_broad_trading_range",return_value=broad(False)),          patch("app.modules.brooks_core.books_full_patterns.classify_tight_trading_range",return_value=None),          patch("app.modules.brooks_core.books_full_patterns.classify_barbwire_identity",return_value=None):
        assert detect_trading_range_fades(snap(cs),tr_ctx(),P,market())==()

def test_045_future_edge_does_not_backdate_prefix():
    cs=range_bars()
    ps=_range_patches([edge("LONG","RANGE_MIDDLE"),edge("SHORT","RANGE_MIDDLE")])
    with ps[0],ps[1],ps[2],ps[3]:
        before=detect_trading_range_fades(snap(cs),tr_ctx(),P,market())
    ps=_range_patches([edge("LONG"),edge("SHORT","RANGE_MIDDLE")])
    with ps[0],ps[1],ps[2],ps[3]:
        after=detect_trading_range_fades(snap(cs+[bar(len(cs),94,96,89,95)]),tr_ctx(),P,market())
    assert before==() and any(x.direction=="LONG" for x in after)

def test_045_engine_uses_typed_limit_reference_price():
    cs=[bar(i,100,104,96,100) for i in range(30)]
    c=BrooksPatternCandidate("LONG","TRADING_RANGE_FADE_LONG","TRADING_RANGE_FADE",29,
        ("broad_range","range_edge"),("BB-RNG-21-BUY-LOW-SELL-HIGH",),"SOURCE_INTERPRETATION",15,"TRADING_RANGE",
        metadata=(("range_low","90"),("range_high","110"),("entry_method","LIMIT_OR_MARKET_FADE"),
                  ("entry_trigger_semantic","AT_OR_NEAR_CANONICAL_RANGE_EDGE"),("entry_reference_price","90"),
                  ("economic_opportunity_id","RANGE_FADE:X:LONG:29"),("range_subtype","BROAD_TRADING_RANGE"),
                  ("range_edge_state","AT_LOWER_RANGE_EDGE")))
    plan=BrooksTrilogyFullCoreEngine(policy=P)._execution_geometry(snap(cs),c,SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED"))
    assert plan[0]==D("90")

def test_045_entry_intent_is_typed_and_inspectable():
    c=BrooksPatternCandidate("LONG","X","TRADING_RANGE_FADE",1,("a","b"),("r",),"SOURCE_INTERPRETATION",1,"TRADING_RANGE",
        metadata=(("entry_method","LIMIT_OR_MARKET_FADE"),("entry_trigger_semantic","EDGE"),("entry_reference_price","99"),
                  ("economic_opportunity_id","OPP")))
    x=BrooksTrilogyFullCoreEngine(policy=P)._entry_execution_intent(c)
    assert isinstance(x,EntryExecutionIntent) and x.entry_method=="LIMIT_OR_MARKET_FADE" and not x.anticipatory

# GAP-068

def micro_structure(side="TOP"):
    return SimpleNamespace(structure_id=f"MICRO:{side}:1:2",first_test_index=1,second_test_index=2,bar_distance=1,
                           first_level=D("105"),second_level=D("105"),price_relation="EQUAL_TEST",engineering_tolerance=D("1"),intervening_move_away=True)

def micro_cs(side="TOP"):
    if side=="TOP": return [bar(0,100,103,98,101),bar(1,102,105,99,103),bar(2,103,105,101,104)]
    return [bar(0,100,102,97,99),bar(1,98,101,95,97),bar(2,97,99,95,96)]

def test_068_micro_double_anticipatory_variant_before_confirmation():
    cs=micro_cs("TOP")
    with patch("app.modules.brooks_core.books_full_patterns.build_micro_double_structure",return_value=micro_structure("TOP")),          patch("app.modules.brooks_core.books_full_patterns._bear_reversal",return_value=False):
        found=detect_anticipatory_reversal_entries(snap(cs),rev_ctx(),P)
    item=next(x for x in found if x.setup_type=="MICRO_DOUBLE_TOP_ANTICIPATORY_SHORT")
    m=dict(item.metadata)
    assert m["entry_method"]=="LIMIT_OR_MARKET_ANTICIPATION"
    assert m["entry_confirmation_state"]=="ANTICIPATORY_UNCONFIRMED"

def test_068_micro_double_confirmation_control_is_stop_trigger():
    cs=micro_cs("TOP")
    with patch("app.modules.brooks_core.books_full_patterns.build_micro_double_structure",return_value=micro_structure("TOP")),          patch("app.modules.brooks_core.books_full_patterns._bear_reversal",return_value=True):
        found=detect_micro_double_top_bottom(snap(cs),rev_ctx(),P)
    item=next(x for x in found if x.direction=="SHORT")
    assert dict(item.metadata)["entry_method"]=="STOP_TRIGGER_CONFIRMATION"

def test_068_no_micro_double_origin_no_anticipatory_entry():
    cs=micro_cs("TOP")
    with patch("app.modules.brooks_core.books_full_patterns.build_micro_double_structure",return_value=None):
        found=detect_anticipatory_reversal_entries(snap(cs),rev_ctx(),P)
    assert not any("MICRO_DOUBLE" in x.setup_type for x in found)

def fake_flag(direction="BULL_TREND"):
    trend=SimpleNamespace(trend_direction=direction,episode_id=f"TREND:{direction}:0",active=True,late_trend=True)
    return SimpleNamespace(trend=trend,final_flag_id=f"FINAL_FLAG:{direction}:0:1",flag_origin_index=1,flag_end_index=1,
                           flag_low=D("98"),flag_high=D("104"),bar_count=1,state="ACTIVE_FINAL_FLAG_CONTEXT")

def test_068_final_flag_anticipatory_variant_preserves_origin():
    cs=[bar(0,100,103,97,102),bar(1,102,104,99,103),bar(2,103,104,99,101)]
    with patch("app.modules.brooks_core.books_full_patterns._structural_final_flag",return_value=fake_flag()),          patch("app.modules.brooks_core.books_full_patterns._bear_reversal",return_value=True):
        found=detect_anticipatory_reversal_entries(snap(cs),rev_ctx("BULL_TREND","LONG"),P)
    item=next(x for x in found if x.setup_type=="FINAL_FLAG_ANTICIPATORY_SHORT")
    m=dict(item.metadata)
    assert m["final_flag_id"].startswith("FINAL_FLAG:BULL_TREND")
    assert m["entry_method"]=="MARKET_OR_LIMIT_ANTICIPATION"

def test_068_final_flag_confirmation_control_is_stop_trigger():
    cs=[bar(0,100,103,97,102),bar(1,102,104,99,103),bar(2,102,104,99,103),bar(3,100,101,95,96)]
    with patch("app.modules.brooks_core.books_full_patterns._structural_final_flag",return_value=fake_flag()),          patch("app.modules.brooks_core.books_full_patterns.is_strong_bear_bar",return_value=True):
        found=detect_final_flag(snap(cs),rev_ctx("BULL_TREND","LONG"),P)
    item=next(x for x in found if x.setup_type=="FINAL_FLAG_REVERSAL_SHORT")
    assert dict(item.metadata)["entry_method"]=="STOP_TRIGGER_CONFIRMATION"

def test_068_final_flag_context_alone_without_reversal_minimum_no_entry():
    cs=[bar(0,100,103,97,102),bar(1,102,104,99,103),bar(2,101,104,99,103)]
    with patch("app.modules.brooks_core.books_full_patterns._structural_final_flag",return_value=fake_flag()),          patch("app.modules.brooks_core.books_full_patterns._bear_reversal",return_value=False):
        found=detect_anticipatory_reversal_entries(snap(cs),rev_ctx("BULL_TREND","LONG"),P)
    assert not any("FINAL_FLAG_ANTICIPATORY" in x.setup_type for x in found)

def test_068_future_confirmation_does_not_backdate_anticipatory_state():
    pre=[bar(0,100,103,97,102),bar(1,102,104,99,103),bar(2,103,104,99,101)]
    with patch("app.modules.brooks_core.books_full_patterns._structural_final_flag",return_value=fake_flag()),          patch("app.modules.brooks_core.books_full_patterns._bear_reversal",return_value=True):
        item=next(x for x in detect_anticipatory_reversal_entries(snap(pre),rev_ctx("BULL_TREND","LONG"),P) if "FINAL_FLAG" in x.setup_type)
    assert dict(item.metadata)["entry_confirmation_state"]=="ANTICIPATORY_UNCONFIRMED"

def test_068_bear_final_flag_mirror():
    flag=fake_flag("BEAR_TREND")
    cs=[bar(0,100,103,97,98),bar(1,98,101,96,97),bar(2,97,102,96,100)]
    with patch("app.modules.brooks_core.books_full_patterns._structural_final_flag",return_value=flag),          patch("app.modules.brooks_core.books_full_patterns._bull_reversal",return_value=True):
        found=detect_anticipatory_reversal_entries(snap(cs),rev_ctx("BEAR_TREND","SHORT"),P)
    assert any(x.setup_type=="FINAL_FLAG_ANTICIPATORY_LONG" for x in found)

def test_068_same_micro_double_economic_identity_across_entry_methods():
    cs=micro_cs("TOP"); st=micro_structure("TOP")
    with patch("app.modules.brooks_core.books_full_patterns.build_micro_double_structure",return_value=st),          patch("app.modules.brooks_core.books_full_patterns._bear_reversal",return_value=False):
        a=next(x for x in detect_anticipatory_reversal_entries(snap(cs),rev_ctx(),P) if "MICRO_DOUBLE" in x.setup_type)
    with patch("app.modules.brooks_core.books_full_patterns.build_micro_double_structure",return_value=st),          patch("app.modules.brooks_core.books_full_patterns._bear_reversal",return_value=True):
        c=next(x for x in detect_micro_double_top_bottom(snap(cs),rev_ctx(),P) if x.direction=="SHORT")
    assert dict(a.metadata)["economic_opportunity_id"]==dict(c.metadata)["economic_opportunity_id"]

def test_068_engine_anticipatory_entry_uses_reference_not_stop_trigger():
    cs=[bar(i,100,104,96,100) for i in range(30)]
    c=BrooksPatternCandidate("SHORT","MICRO_DOUBLE_TOP_ANTICIPATORY_SHORT","DOUBLE_TOP_BOTTOM_REVERSAL",29,
        ("origin","anticipation"),("BB-REV-MICRO-DOUBLE-TOP-BOTTOM",),"SOURCE_INTERPRETATION",28,"REVERSAL_OR_RANGE_EXTREME",
        metadata=(("entry_method","LIMIT_OR_MARKET_ANTICIPATION"),("entry_trigger_semantic","MICRO_DOUBLE_SECOND_TEST_ANTICIPATION"),
                  ("entry_reference_price","103"),("economic_opportunity_id","MICRO:X:SHORT")))
    plan=BrooksTrilogyFullCoreEngine(policy=P)._execution_geometry(snap(cs),c,SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED"))
    assert plan[0]==D("103")

def test_068_stop_confirmation_geometry_remains_signal_stop_trigger():
    cs=[bar(i,100,104,96,100) for i in range(30)]
    c=BrooksPatternCandidate("SHORT","MICRO_DOUBLE_TOP_SHORT","DOUBLE_TOP_BOTTOM_REVERSAL",29,
        ("origin","confirmation"),("BB-REV-MICRO-DOUBLE-TOP-BOTTOM",),"SOURCE_INTERPRETATION",27,"REVERSAL_OR_RANGE_EXTREME",
        metadata=(("entry_method","STOP_TRIGGER_CONFIRMATION"),("entry_trigger_semantic","REVERSAL_BAR_CONFIRMATION_AFTER_MICRO_DOUBLE"),
                  ("economic_opportunity_id","MICRO:X:SHORT")))
    plan=BrooksTrilogyFullCoreEngine(policy=P)._execution_geometry(snap(cs),c,SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED"))
    assert plan[0] < cs[-1].low

def test_068_active_final_flag_context_contract_is_mapped():
    c=BrooksPatternCandidate("SHORT","FINAL_FLAG_ANTICIPATORY_SHORT","FINAL_FLAG_REVERSAL",2,
        ("flag","reversal"),("BB-REV-07-FINAL-FLAG",),"SOURCE_INTERPRETATION",33,"ACTIVE_LATE_TREND_FINAL_FLAG",
        metadata=(("active_trend","true"),("final_flag_id","F"),("trend_episode_id","T"),("entry_method","MARKET_OR_LIMIT_ANTICIPATION"),
                  ("entry_trigger_semantic","X"),("economic_opportunity_id","F:SHORT")))
    status=BrooksTrilogyFullCoreEngine(policy=P)._context_contract_status(c,rev_ctx("BULL_TREND","LONG"),market())
    assert status[0]=="PASS"

def test_068_semantic_variants_still_choose_one_economic_signal():
    base=(("active_trend","true"),("final_flag_id","F"),("trend_episode_id","T"),("economic_opportunity_id","F:SHORT"))
    a=BrooksPatternCandidate("SHORT","FINAL_FLAG_ANTICIPATORY_SHORT","FINAL_FLAG_REVERSAL",10,("a","b"),("r",),"SOURCE_INTERPRETATION",33,"ACTIVE_LATE_TREND_FINAL_FLAG",
        metadata=base+(("entry_method","MARKET_OR_LIMIT_ANTICIPATION"),("entry_trigger_semantic","ANT"),))
    c=BrooksPatternCandidate("SHORT","FINAL_FLAG_REVERSAL_SHORT","FINAL_FLAG_REVERSAL",10,("a","c"),("r",),"SOURCE_INTERPRETATION",32,"ACTIVE_LATE_TREND_FINAL_FLAG",
        metadata=base+(("entry_method","STOP_TRIGGER_CONFIRMATION"),("entry_trigger_semantic","CONF"),))
    chosen=BrooksTrilogyFullCoreEngine(policy=P)._choose_candidate((a,c),rev_ctx("BULL_TREND","LONG"),None,market())
    assert chosen in {a,c}

def test_068_entry_method_identity_not_free_text_only():
    c=BrooksPatternCandidate("LONG","X","DOUBLE_TOP_BOTTOM_REVERSAL",1,("a","b"),("r",),"SOURCE_INTERPRETATION",1,"REVERSAL_OR_RANGE_EXTREME",
        metadata=(("entry_method","LIMIT_OR_MARKET_ANTICIPATION"),("entry_trigger_semantic","STRUCTURE"),("entry_reference_price","99"),("economic_opportunity_id","E")))
    x=BrooksTrilogyFullCoreEngine(policy=P)._entry_execution_intent(c)
    assert x.entry_method=="LIMIT_OR_MARKET_ANTICIPATION" and x.economic_opportunity_id=="E" and x.anticipatory
