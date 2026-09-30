import os,sys
sys.path.insert(0,os.path.dirname(__file__))
import test_brooks_wave15_semantics as s
import test_brooks_wave08_semantics as w08
import test_brooks_wave12_semantics as w12
import test_brooks_wave14_semantics as w14

def test_s01_long_bullish_htf(): s.test_070_long_with_bullish_htf_is_aligned()
def test_s02_long_bearish_htf(): s.test_070_long_with_bearish_htf_is_opposed()
def test_s03_short_bearish_htf(): s.test_070_short_with_bearish_htf_is_aligned()
def test_s04_short_bullish_htf(): s.test_070_short_with_bullish_htf_is_opposed()
def test_s05_ambiguous_htf(): s.test_070_ambiguous_htf_not_silently_aligned()
def test_s06_incomplete_htf_causal(): s.test_070_incomplete_future_htf_candle_is_not_used()
def test_s07_htf_support_context(): s.test_071_long_supportive_htf_location()
def test_s08_htf_range_middle_context_only(): s.test_071_htf_range_middle_is_neutral_not_entry()
def test_s09_multiple_relevant_htfs(): s.test_075_multiple_available_htfs_are_aggregated_causally()
def test_s10_daily_not_fabricated(): s.test_075_daily_context_absent_when_history_insufficient_not_fabricated()
def test_s11_htf_always_in_preserved(): s.test_076_resolved_always_in_can_define_directional_side()
def test_s12_htf_ai_mirror(): s.test_076_candidate_direction_mirror_uses_same_htf_identity()
def test_s13_wave14_range_entry_preserved(): w14.test_045_valid_broad_range_lower_edge_long_limit_fade()
def test_s14_wave14_entry_method_preserved(): w14.test_068_micro_double_anticipatory_variant_before_confirmation()
def test_s15_wave14_economic_identity_preserved(): w14.test_068_same_micro_double_economic_identity_across_entry_methods()
def test_s16_minor_reversal_not_always_in(): w12.test_062_single_opposite_bar_not_full_identity()
def test_s17_countertrend_scalp_distinct():
    a=w12.classify_countertrend_opportunity(direction="SHORT",prior_always_in="LONG",current_always_in="LONG",signal_index=5)
    b=w12.classify_countertrend_opportunity(direction="SHORT",prior_always_in="LONG",current_always_in="SHORT",signal_index=5)
    assert a.state!=b.state
def test_s18_mtr_gt12_preserved(): w08.test_059_retest_beyond_old_12_bar_ceiling_is_still_valid()
def test_s19_final_flag_gt6_preserved(): w08.test_069_active_structural_final_flag_beyond_six_bars_is_recognized()
def test_s20_directionless_htf_gate_removed(): s.test_070_directionless_legacy_alignment_cannot_support_opposite_candidate()
