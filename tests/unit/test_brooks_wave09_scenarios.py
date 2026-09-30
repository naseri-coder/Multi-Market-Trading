from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.books_full_patterns import _structural_final_flag
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.correction_lifecycle import (
    build_active_trend_episode, build_exhaustion_origin, classify_climax_outcome,
    classify_head_shoulders_outcome, classify_mtr_retest_lifecycle,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,9,2,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i); return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def snap(cs):
    cs=tuple(cs); return MarketSnapshot('binance','futures','BTCUSDT','15m',cs,cs[-1].close_time,'W09')
def ctx(regime='BULL_TREND',ai='LONG',structure='BULL_TREND'):
    return SimpleNamespace(regime=regime,always_in=ai,structure_direction=structure,breakout_direction='UNRESOLVED',breakout_streak=0)
def bull_origin():
    cs=tuple(bar(i,100+i,103+i,99+i,102+i) for i in range(6)); t=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=0,evaluated_index=4,late_trend=True); return cs,build_exhaustion_origin(cs,t,origin_index=4,engineering_acceleration_evidence=True)
def bear_origin():
    cs=tuple(bar(i,120-i,121-i,117-i,118-i) for i in range(6)); t=build_active_trend_episode(trend_direction='BEAR_TREND',origin_index=0,evaluated_index=4,late_trend=True); return cs,build_exhaustion_origin(cs,t,origin_index=4,engineering_acceleration_evidence=True)
def bull_final_flag(n=7):
    cs=[]
    for i in range(20): b=100+2*i; cs.append(bar(i,b,b+3,b-1,b+2))
    for j in range(n):
        i=20+j; o=139.2 if j%2==0 else 140.2; c=140.2 if j%2==0 else 139.2; cs.append(bar(i,o,141,138.5,c))
    i=len(cs); cs.append(bar(i,140.5,141,134,135)); return cs

def test_scenario_01_063_positive():
    _,o=bull_origin(); assert o is not None
def test_scenario_02_063_negative_near_miss():
    cs,_=bull_origin(); t=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=0,evaluated_index=4,late_trend=False); assert build_exhaustion_origin(cs,t,origin_index=4,engineering_acceleration_evidence=True) is None
def test_scenario_03_063_prefix_causality():
    cs,o=bull_origin(); assert classify_climax_outcome(cs,o,current_regime='BULL_TREND',evaluated_index=4).state=='PENDING_CLIMAX_OUTCOME'
def test_scenario_04_063_064_transition_same_origin():
    cs,o=bull_origin(); rows=list(cs[:5]); rows.append(bar(5,105,106,99,100)); life=classify_climax_outcome(tuple(rows),o,current_regime='BULL_TREND',evaluated_index=5); assert life.state=='REVERSAL_ATTEMPT_PENDING_OUTCOME' and life.origin.exhaustion_id==o.exhaustion_id
def test_scenario_05_064_false_without_063():
    cs,_=bull_origin(); t=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=0,evaluated_index=4,late_trend=False); assert build_exhaustion_origin(cs,t,origin_index=4,engineering_acceleration_evidence=True) is None
def test_scenario_06_064_future_event_prefix():
    cs,o=bull_origin(); p=classify_climax_outcome(cs,o,current_regime='BULL_TREND',evaluated_index=4); rows=list(cs[:5]); rows.append(bar(5,105,106,99,100)); f=classify_climax_outcome(tuple(rows),o,current_regime='TRADING_RANGE',evaluated_index=5); assert p.state=='PENDING_CLIMAX_OUTCOME' and f.state=='RESOLVED_TRADING_RANGE'
def test_scenario_07_058_positive_continuation():
    x=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=1,head_index=3,right_shoulder_index=5,neckline_state='FAILED_NECKLINE_BREAK_REENTRY'); assert x.state=='WITH_TREND_CONTINUATION_CONTEXT'
def test_scenario_08_058_negative_shape_only():
    x=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=1,head_index=3,right_shoulder_index=5,neckline_state='ALIAS_RANGE_OR_FLAG'); assert x.state=='ALIAS_RANGE_OR_FLAG_CONTEXT' and not x.trade_eligible
def test_scenario_09_058_prefix_pending_reversal():
    x=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=1,head_index=3,right_shoulder_index=5,neckline_state='NECKLINE_BREAK'); assert x.state=='REVERSAL_ATTEMPT_PENDING_FOLLOW_THROUGH'
def test_scenario_10_bull_bear_mirror():
    _,b=bull_origin(); _,s=bear_origin(); assert b.direction=='LONG' and s.direction=='SHORT'
def test_scenario_11_active_local_flag_parent_trend_preserved():
    f=_structural_final_flag(snap(bull_final_flag(7)),ctx(),BrooksFullCorePolicy()); assert f is not None and f.trend.active
def test_scenario_12_stale_final_flag_rejected():
    assert _structural_final_flag(snap(bull_final_flag(7)),ctx('TRADING_RANGE','UNRESOLVED','BULL_TREND'),BrooksFullCorePolicy()) is None
def test_scenario_13_mtr_over_12_same_episode_preserved():
    cs=[bar(0,100,105,99,104),bar(1,104,110,103,109),bar(2,108,109,100,101)]
    for _ in range(13): i=len(cs); cs.append(bar(i,102,106,100,103))
    i=len(cs); cs.append(bar(i,106,109.5,105,109)); i=len(cs); cs.append(bar(i,109,109.2,102,103))
    x=classify_mtr_retest_lifecycle(tuple(cs),prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')); assert x.retest_index-2>12 and x.state=='SECOND_REVERSAL_CONFIRMED'
def test_scenario_14_final_flag_over_6_preserved():
    f=_structural_final_flag(snap(bull_final_flag(9)),ctx(),BrooksFullCorePolicy()); assert f is not None and f.bar_count>6
