from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.books_full_patterns import (
    _structural_final_flag, detect_final_flag, scan_final_flag_context_observations,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.correction_lifecycle import (
    build_active_trend_episode, build_final_flag_lifecycle, build_final_flag_attempt_origin,
    evaluate_final_flag_attempt_lifecycle, classify_mtr_retest_lifecycle,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,8,1,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def snap(cs):
    cs=tuple(cs); return MarketSnapshot('binance','futures','BTCUSDT','15m',cs,cs[-1].close_time,'W08')
def ctx(regime='BULL_TREND',always_in='LONG',structure='BULL_TREND',breakout='UNRESOLVED',streak=0):
    return SimpleNamespace(regime=regime,always_in=always_in,structure_direction=structure,breakout_direction=breakout,breakout_streak=streak)
def bull_final_flag(flag_bars=7):
    cs=[]
    for i in range(20):
        b=100+2*i; cs.append(bar(i,b,b+3,b-1,b+2))
    for j in range(flag_bars):
        i=20+j; o=139.2 if j%2==0 else 140.2; c=140.2 if j%2==0 else 139.2
        cs.append(bar(i,o,141,138.5,c))
    i=len(cs); cs.append(bar(i,140.5,141,134,135))
    return cs
def bear_final_flag(flag_bars=7):
    cs=[]
    for i in range(20):
        b=160-2*i; cs.append(bar(i,b,b+1,b-3,b-2))
    for j in range(flag_bars):
        i=20+j; o=120.8 if j%2==0 else 119.8; c=119.8 if j%2==0 else 120.8
        cs.append(bar(i,o,121.5,119,c))
    i=len(cs); cs.append(bar(i,119.5,126,119,125))
    return cs
def mtr_seq(delay=13):
    cs=[bar(0,100,105,99,104),bar(1,104,110,103,109),bar(2,108,109,100,101)]
    for k in range(delay):
        i=len(cs); cs.append(bar(i,102,106,100,103))
    i=len(cs); cs.append(bar(i,106,109.5,105,109))
    i=len(cs); cs.append(bar(i,109,109.2,102,103))
    return tuple(cs)
def final_flag_life(direction='BULL_TREND'):
    cs=tuple(bull_final_flag(7)[:-1])
    t=build_active_trend_episode(trend_direction=direction,origin_index=2,evaluated_index=len(cs)-1,late_trend=True)
    f=build_final_flag_lifecycle(cs,t,flag_origin_index=len(cs)-7,flag_end_index=len(cs)-1)
    return cs,t,f

# BROOKS-GAP-024
def test_024_active_late_bull_trend_has_final_flag_context():
    cs=bull_final_flag(7); f=_structural_final_flag(snap(cs),ctx(),BrooksFullCorePolicy()); assert f and f.trend.active and f.trend.trend_direction=='BULL_TREND'
def test_024_active_late_bear_trend_mirror():
    cs=bear_final_flag(7); f=_structural_final_flag(snap(cs),ctx('BEAR_TREND','SHORT','BEAR_TREND'),BrooksFullCorePolicy()); assert f and f.trend.trend_direction=='BEAR_TREND'
def test_024_stale_historical_structure_in_range_is_not_active_final_flag():
    cs=bull_final_flag(7); stale=ctx('TRADING_RANGE','UNRESOLVED','BULL_TREND'); assert _structural_final_flag(snap(cs),stale,BrooksFullCorePolicy()) is None
def test_024_historical_direction_alone_is_insufficient():
    cs=bull_final_flag(7); stale=ctx('AMBIGUOUS','UNRESOLVED','BULL_TREND'); assert not detect_final_flag(snap(cs),stale,BrooksFullCorePolicy())
def test_024_new_trend_episode_has_new_identity():
    a=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=5,evaluated_index=20,late_trend=True); b=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=30,evaluated_index=50,late_trend=True); assert a.episode_id!=b.episode_id
def test_024_future_termination_does_not_change_prior_episode_object():
    a=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=5,evaluated_index=20,late_trend=True); assert a.active and a.state=='ACTIVE_LATE_TREND'
def test_024_context_observation_is_not_trade_eligibility():
    obs=scan_final_flag_context_observations(snap(bull_final_flag(7)),ctx(),BrooksFullCorePolicy()); assert obs and dict(obs[0].metadata)['trade_eligible']=='false'

# BROOKS-GAP-059
def test_059_retest_inside_old_12_bar_period_is_valid():
    cs=mtr_seq(3); x=classify_mtr_retest_lifecycle(cs,prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')); assert x.state=='SECOND_REVERSAL_CONFIRMED'
def test_059_retest_beyond_old_12_bar_ceiling_is_still_valid():
    cs=mtr_seq(13); x=classify_mtr_retest_lifecycle(cs,prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')); assert x.retest_index-2>12 and x.state=='SECOND_REVERSAL_CONFIRMED'
def test_059_inactive_structural_episode_rejects_retest_regardless_of_age():
    cs=mtr_seq(3); x=classify_mtr_retest_lifecycle(cs,prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1'),episode_active=False); assert x.state=='EPISODE_INACTIVE' and x.retest_index is None
def test_059_episode_identity_preserves_old_extreme_and_break():
    cs=mtr_seq(4); x=classify_mtr_retest_lifecycle(cs,prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')); assert x.mtr_episode_id=='MTR:BULL_TREND:1:2'
def test_059_future_retest_is_not_visible_on_earlier_prefix():
    cs=mtr_seq(13); x=classify_mtr_retest_lifecycle(cs,prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1'),evaluated_index=10); assert x.state=='WAITING_OLD_EXTREME_RETEST' and x.retest_index is None
def test_059_bear_mirror_retest_and_second_reversal():
    cs=(bar(0,100,101,95,96),bar(1,96,97,90,91),bar(2,92,100,91,99),bar(3,98,99,93,94),bar(4,94,95,90.5,91),bar(5,91,99,90.8,98)); x=classify_mtr_retest_lifecycle(cs,prior_trend_direction='BEAR_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')); assert x.state=='SECOND_REVERSAL_CONFIRMED' and x.reversal_direction=='LONG'
def test_059_no_replacement_universal_timer_in_lifecycle():
    cs=mtr_seq(20); x=classify_mtr_retest_lifecycle(cs,prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')); assert x.active and x.retest_index is not None

# BROOKS-GAP-066
def _ff_attempt(objective=D('90')):
    base=list(bull_final_flag(7)[:-1]); t=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=2,evaluated_index=len(base)-1,late_trend=True); f=build_final_flag_lifecycle(tuple(base),t,flag_origin_index=len(base)-7,flag_end_index=len(base)-1)
    signal_i=len(base); base.append(bar(signal_i,140,141,135,136)); origin=build_final_flag_attempt_origin(tuple(base),f,signal_index=signal_i,direction='SHORT',objective_level=objective); return base,f,origin
def test_066_originating_final_flag_identity_is_preserved():
    base,f,o=_ff_attempt(); assert o.final_flag.final_flag_id==f.final_flag_id and f.trend.episode_id in o.reversal_origin.attempt_id
def test_066_untriggered_invalidation_is_not_failed_entered_flag():
    base,f,o=_ff_attempt(); i=len(base); base.append(bar(i,139,142,136,141)); x=evaluate_final_flag_attempt_lifecycle(tuple(base),o); assert x.state=='SIGNAL_INVALIDATED_BEFORE_TRIGGER' and not x.failure_confirmed
def test_066_triggered_active_final_flag_attempt():
    base,f,o=_ff_attempt(); i=len(base); base.append(bar(i,136,140,134,135)); x=evaluate_final_flag_attempt_lifecycle(tuple(base),o); assert x.state=='TRIGGERED_ACTIVE'
def test_066_objective_before_failure_is_not_failed_attempt():
    base,f,o=_ff_attempt(); i=len(base); base.append(bar(i,136,140,134,135)); i+=1; base.append(bar(i,134,136,89,91)); x=evaluate_final_flag_attempt_lifecycle(tuple(base),o); assert x.state=='OBJECTIVE_REACHED' and not x.failure_confirmed
def test_066_failure_before_objective_is_failed_same_origin():
    base,f,o=_ff_attempt(); i=len(base); base.append(bar(i,136,140,134,135)); i+=1; base.append(bar(i,138,142,93,140)); x=evaluate_final_flag_attempt_lifecycle(tuple(base),o); assert x.state=='FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE' and x.failure_confirmed and x.origin.final_flag.final_flag_id==f.final_flag_id
def test_066_same_bar_trigger_failure_ambiguity_fails_closed():
    base,f,o=_ff_attempt(); i=len(base); base.append(bar(i,138,142,134,139)); x=evaluate_final_flag_attempt_lifecycle(tuple(base),o); assert x.state=='AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR' and not x.failure_confirmed
def test_066_future_failure_absent_on_trigger_prefix():
    base,f,o=_ff_attempt(); i=len(base); base.append(bar(i,136,140,134,135)); prefix=evaluate_final_flag_attempt_lifecycle(tuple(base),o); i+=1; base.append(bar(i,138,142,93,140)); full=evaluate_final_flag_attempt_lifecycle(tuple(base),o); assert prefix.state=='TRIGGERED_ACTIVE' and full.failure_confirmed

# BROOKS-GAP-069
def test_069_active_final_flag_at_or_below_six_bars_still_recognized():
    cs=bull_final_flag(5); f=_structural_final_flag(snap(cs),ctx(),BrooksFullCorePolicy()); assert f and f.bar_count>=1
def test_069_active_structural_final_flag_beyond_six_bars_is_recognized():
    cs=bull_final_flag(9); f=_structural_final_flag(snap(cs),ctx(),BrooksFullCorePolicy()); assert f and f.bar_count>6
def test_069_short_flag_after_trend_ended_is_rejected():
    cs=bull_final_flag(3); assert _structural_final_flag(snap(cs),ctx('TRADING_RANGE','UNRESOLVED','BULL_TREND'),BrooksFullCorePolicy()) is None
def test_069_bar_count_alone_is_insufficient():
    cs=[]
    for i in range(27):
        b=100+2*i; cs.append(bar(i,b,b+3,b-1,b+2))
    cs.append(bar(27,154,155,148,149)); assert _structural_final_flag(snap(cs),ctx(),BrooksFullCorePolicy()) is None
def test_069_new_trend_episode_resets_flag_identity():
    cs=tuple(bull_final_flag(7)[:-1]); a=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=2,evaluated_index=26,late_trend=True); b=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=12,evaluated_index=26,late_trend=True); fa=build_final_flag_lifecycle(cs,a,flag_origin_index=20,flag_end_index=26); fb=build_final_flag_lifecycle(cs,b,flag_origin_index=20,flag_end_index=26); assert fa.final_flag_id!=fb.final_flag_id
def test_069_future_bar_does_not_mutate_historical_flag_identity():
    cs=tuple(bull_final_flag(7)[:-1]); a=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=2,evaluated_index=26,late_trend=True); f=build_final_flag_lifecycle(cs,a,flag_origin_index=20,flag_end_index=26); assert f.state=='ACTIVE_FINAL_FLAG_CONTEXT' and f.bar_count==7
def test_069_final_flag_window_policy_is_not_used_as_identity_ceiling():
    cs=bull_final_flag(9); found=detect_final_flag(snap(cs),ctx(),BrooksFullCorePolicy()); assert found and int(dict(found[0].metadata)['flag_bars'])>6
