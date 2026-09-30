import os,sys
sys.path.insert(0,os.path.dirname(__file__))
import test_brooks_wave14_semantics as s
import test_brooks_wave08_semantics as w08
import test_brooks_wave10_semantics as w10
import test_brooks_wave11_semantics as w11
import test_brooks_wave12_semantics as w12
import test_brooks_wave13_semantics as w13

def test_s01_range_lower_limit(): s.test_045_valid_broad_range_lower_edge_long_limit_fade()
def test_s02_range_upper_limit(): s.test_045_valid_broad_range_upper_edge_short_mirror()
def test_s03_range_middle_rejected(): s.test_045_range_middle_not_entry()
def test_s04_ttr_suppressed(): s.test_045_ttr_is_suppressed()
def test_s05_barbwire_suppressed(): s.test_045_barbwire_is_suppressed()
def test_s06_local_edge_enclosing_middle_rejected(): s.test_045_local_edge_in_enclosing_middle_not_promoted()
def test_s07_micro_anticipation(): s.test_068_micro_double_anticipatory_variant_before_confirmation()
def test_s08_micro_confirmation(): s.test_068_micro_double_confirmation_control_is_stop_trigger()
def test_s09_final_flag_anticipation(): s.test_068_final_flag_anticipatory_variant_preserves_origin()
def test_s10_future_confirmation_not_backdated(): s.test_068_future_confirmation_does_not_backdate_anticipatory_state()
def test_s11_economic_identity_preserved(): s.test_068_same_micro_double_economic_identity_across_entry_methods()
def test_s12_candidate_dedup_one_signal(): s.test_068_semantic_variants_still_choose_one_economic_signal()
def test_s13_range_edge_no_fixed_25(): w11.test_029_old_universal_25_percent_not_identity()
def test_s14_local_enclosing_breakout_preserved(): w11.test_038_local_breakout_inside_enclosing_range_is_context_not_new_trend()
def test_s15_minor_reversal_not_entry(): w12.test_062_single_opposite_bar_not_full_identity()
def test_s16_countertrend_scalp_distinct():
    a=w12.classify_countertrend_opportunity(direction="SHORT",prior_always_in="LONG",current_always_in="LONG",signal_index=5)
    b=w12.classify_countertrend_opportunity(direction="SHORT",prior_always_in="LONG",current_always_in="SHORT",signal_index=5)
    assert a.state!=b.state
def test_s17_mtr_gt12(): w08.test_059_retest_beyond_old_12_bar_ceiling_is_still_valid()
def test_s18_final_flag_gt6(): w08.test_069_active_structural_final_flag_beyond_six_bars_is_recognized()
def test_s19_failure_of_failure_preserved(): w10.test_035_genuine_failure_of_failure_requires_trigger_then_later_failure()
def test_s20_ma_gap_episode_preserved(): w13.test_018_rolling_memory_cannot_relabel_later_gap_first()
