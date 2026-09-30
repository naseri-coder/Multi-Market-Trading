import os,sys
sys.path.insert(0,os.path.dirname(__file__))
import test_brooks_wave13_semantics as s
import test_brooks_wave08_semantics as w08
import test_brooks_wave09_semantics as w09
import test_brooks_wave10_semantics as w10
import test_brooks_wave11_semantics as w11
import test_brooks_wave12_semantics as w12

def test_scenario_01_018_first_episode(): s.test_018_first_ma_gap_is_owned_by_active_episode()
def test_scenario_02_018_stale_not_first(): s.test_018_rolling_memory_cannot_relabel_later_gap_first()
def test_scenario_03_018_reset_new_identity(): s.test_018_new_ma_slope_cycle_gets_new_episode_identity()
def test_scenario_04_019_touch_without_reversal_gate(): s.test_019_twenty_first_touch_no_reversal_bar_hard_gate()
def test_scenario_05_019_19_not_literal_20(): s.test_019_nineteen_is_not_literal_twenty_gap_condition()
def test_scenario_06_020_context_only(): s.test_020_ma_gap_maturity_is_context_not_prediction()
def test_scenario_07_020_prefix(): s.test_020_future_gap_not_visible_on_earlier_prefix()
def test_scenario_08_055_below20_context(): s.test_055_below_twenty_can_remain_strong_trend_ma_test_context()
def test_scenario_09_055_count_weak_no_promotion(): s.test_055_count_without_strong_context_is_not_promoted()
def test_scenario_10_056_sequence(): s.test_056_second_attempt_sequence_identity_long()
def test_scenario_11_056_missing_moveaway(): s.test_056_no_move_away_no_second_sequence()
def test_scenario_12_056_prefix(): s.test_056_prefix_has_no_future_second_attempt()
def test_scenario_13_mtr_gt12(): w08.test_059_retest_beyond_old_12_bar_ceiling_is_still_valid()
def test_scenario_14_final_flag_gt6(): w08.test_069_active_structural_final_flag_beyond_six_bars_is_recognized()
def test_scenario_15_large_bar_not_exhaustion(): w09.test_063_identical_large_bar_without_late_trend_is_not_exhaustion()
def test_scenario_16_failure_of_failure_chain(): w10.test_035_genuine_failure_of_failure_requires_trigger_then_later_failure()
def test_scenario_17_local_enclosing_range(): w11.test_038_local_breakout_inside_enclosing_range_is_context_not_new_trend()
def test_scenario_18_minor_not_one_bar(): w12.test_062_single_opposite_bar_not_full_identity()
def test_scenario_19_countertrend_scalp_vs_reversal():
    s1=w12.classify_countertrend_opportunity(direction="SHORT",prior_always_in="LONG",current_always_in="LONG",signal_index=5)
    s2=w12.classify_countertrend_opportunity(direction="SHORT",prior_always_in="LONG",current_always_in="SHORT",signal_index=5)
    assert s1.state!=s2.state
def test_scenario_20_second_ma_gap_bear_mirror(): s.test_056_bear_mirror()
