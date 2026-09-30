from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from app.modules.brooks_core.books_full_patterns import _structural_final_flag, detect_final_flag
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.correction_lifecycle import build_active_trend_episode, build_final_flag_lifecycle, build_final_flag_attempt_origin, evaluate_final_flag_attempt_lifecycle, classify_mtr_retest_lifecycle
from app.modules.market_data.entities import Candle, MarketSnapshot
BASE=datetime(2026,8,2,tzinfo=UTC)
def b(i,o,h,l,c):
 t=BASE+timedelta(minutes=15*i); return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def sn(cs): cs=tuple(cs); return MarketSnapshot('binance','futures','BTCUSDT','15m',cs,cs[-1].close_time,'W08S')
def cx(regime='BULL_TREND',ai='LONG',structure='BULL_TREND'): return SimpleNamespace(regime=regime,always_in=ai,structure_direction=structure,breakout_direction='UNRESOLVED',breakout_streak=0)
def flag(n=7,bear=False):
 cs=[]
 for i in range(20):
  if bear:
   x=160-2*i; cs.append(b(i,x,x+1,x-3,x-2))
  else:
   x=100+2*i; cs.append(b(i,x,x+3,x-1,x+2))
 for j in range(n):
  i=20+j
  if bear:
   o=120.8 if j%2==0 else 119.8; c=119.8 if j%2==0 else 120.8; cs.append(b(i,o,121.5,119,c))
  else:
   o=139.2 if j%2==0 else 140.2; c=140.2 if j%2==0 else 139.2; cs.append(b(i,o,141,138.5,c))
 i=len(cs); cs.append(b(i,119.5,126,119,125) if bear else b(i,140.5,141,134,135)); return cs
def mtr(delay=13):
 cs=[b(0,100,105,99,104),b(1,104,110,103,109),b(2,108,109,100,101)]
 for _ in range(delay): i=len(cs); cs.append(b(i,102,106,100,103))
 i=len(cs); cs.append(b(i,106,109.5,105,109)); i=len(cs); cs.append(b(i,109,109.2,102,103)); return tuple(cs)
def attempt():
 cs=list(flag(7)[:-1]); t=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=2,evaluated_index=len(cs)-1,late_trend=True); f=build_final_flag_lifecycle(tuple(cs),t,flag_origin_index=len(cs)-7,flag_end_index=len(cs)-1); i=len(cs); cs.append(b(i,140,141,135,136)); o=build_final_flag_attempt_origin(tuple(cs),f,signal_index=i,direction='SHORT',objective_level=D('90')); return cs,o

def test_scenario_01_active_bull_final_flag(): assert _structural_final_flag(sn(flag()),cx(),BrooksFullCorePolicy())
def test_scenario_02_active_bear_final_flag(): assert _structural_final_flag(sn(flag(bear=True)),cx('BEAR_TREND','SHORT','BEAR_TREND'),BrooksFullCorePolicy())
def test_scenario_03_stale_historical_flag(): assert _structural_final_flag(sn(flag()),cx('TRADING_RANGE','UNRESOLVED','BULL_TREND'),BrooksFullCorePolicy()) is None
def test_scenario_04_ended_trend_recent_flag_shape(): assert not detect_final_flag(sn(flag(3)),cx('TRADING_RANGE','UNRESOLVED','BULL_TREND'),BrooksFullCorePolicy())
def test_scenario_05_new_trend_episode_identity(): assert build_active_trend_episode(trend_direction='BULL_TREND',origin_index=2,evaluated_index=20,late_trend=True).episode_id!=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=12,evaluated_index=20,late_trend=True).episode_id
def test_scenario_06_mtr_retest_inside_old_limit(): assert classify_mtr_retest_lifecycle(mtr(3),prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')).state=='SECOND_REVERSAL_CONFIRMED'
def test_scenario_07_mtr_retest_beyond_old_limit():
 x=classify_mtr_retest_lifecycle(mtr(13),prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1')); assert x.retest_index-2>12
def test_scenario_08_late_unrelated_not_same_mtr(): assert classify_mtr_retest_lifecycle(mtr(13),prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1'),episode_active=False).state=='EPISODE_INACTIVE'
def test_scenario_09_active_final_flag_le_six(): assert _structural_final_flag(sn(flag(5)),cx(),BrooksFullCorePolicy())
def test_scenario_10_active_final_flag_gt_six(): assert _structural_final_flag(sn(flag(9)),cx(),BrooksFullCorePolicy()).bar_count>6
def test_scenario_11_short_flag_after_trend_ended(): assert _structural_final_flag(sn(flag(3)),cx('TRADING_RANGE','UNRESOLVED','BULL_TREND'),BrooksFullCorePolicy()) is None
def test_scenario_12_triggered_final_flag_attempt():
 cs,o=attempt(); i=len(cs); cs.append(b(i,136,140,134,135)); assert evaluate_final_flag_attempt_lifecycle(tuple(cs),o).state=='TRIGGERED_ACTIVE'
def test_scenario_13_untriggered_invalidation():
 cs,o=attempt(); i=len(cs); cs.append(b(i,139,142,136,141)); assert evaluate_final_flag_attempt_lifecycle(tuple(cs),o).state=='SIGNAL_INVALIDATED_BEFORE_TRIGGER'
def test_scenario_14_failed_final_flag_attempt():
 cs,o=attempt(); i=len(cs); cs.append(b(i,136,140,134,135)); i+=1; cs.append(b(i,138,142,93,140)); assert evaluate_final_flag_attempt_lifecycle(tuple(cs),o).failure_confirmed
def test_scenario_15_same_bar_ambiguous_failure():
 cs,o=attempt(); i=len(cs); cs.append(b(i,138,142,134,139)); assert evaluate_final_flag_attempt_lifecycle(tuple(cs),o).state=='AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR'
def test_scenario_16_prefix_causality_retest(): assert classify_mtr_retest_lifecycle(mtr(13),prior_trend_direction='BULL_TREND',old_extreme_index=1,structure_break_index=2,engineering_test_tolerance=D('1'),evaluated_index=10).retest_index is None
def test_scenario_17_prefix_causality_final_flag_failure():
 cs,o=attempt(); i=len(cs); cs.append(b(i,136,140,134,135)); assert evaluate_final_flag_attempt_lifecycle(tuple(cs),o).state=='TRIGGERED_ACTIVE'; i+=1; cs.append(b(i,138,142,93,140)); assert evaluate_final_flag_attempt_lifecycle(tuple(cs),o).failure_confirmed
def test_scenario_18_bull_bear_mirrors(): assert _structural_final_flag(sn(flag()),cx(),BrooksFullCorePolicy()).trend.trend_direction=='BULL_TREND' and _structural_final_flag(sn(flag(bear=True)),cx('BEAR_TREND','SHORT','BEAR_TREND'),BrooksFullCorePolicy()).trend.trend_direction=='BEAR_TREND'
