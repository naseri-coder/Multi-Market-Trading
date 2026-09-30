from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.modules.brooks_core.correction_lifecycle import (
    CompactPatternOrigin,
    build_breakout_attempt_identity,
    classify_breakout_lifecycle,
    classify_failed_breakout_confirmation,
    classify_failure_of_failure,
    classify_breakout_test,
    classify_near_breakout_pullback,
    classify_compact_pattern_lifecycle,
)
from app.modules.brooks_core.pattern_expansion import _bodies_only_ii_at
from app.modules.market_data.entities import Candle

BASE=datetime(2026,9,1,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))

def long_failed_breakout(strong=False):
    cs=[bar(0,98,100,97,99),bar(1,99,106,98,104),bar(2,104,105,97,98)]
    origin=build_breakout_attempt_identity(tuple(cs),direction='LONG',reference_id='SWING:0',reference_level=D('100'),attempt_index=1,engineering_strong=strong)
    return cs,origin

def short_failed_breakout(strong=False):
    cs=[bar(0,102,103,100,101),bar(1,101,102,94,96),bar(2,96,103,95,102)]
    origin=build_breakout_attempt_identity(tuple(cs),direction='SHORT',reference_id='SWING:0',reference_level=D('100'),attempt_index=1,engineering_strong=strong)
    return cs,origin

# BROOKS-GAP-034
def test_034_weak_breakout_strong_reversal_confirms_failure():
    cs,o=long_failed_breakout(False); x=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); assert x.state=='CONFIRMED_STRONG_REVERSAL_WEAK_BREAKOUT'
def test_034_strong_breakout_strong_reversal_waits_when_forces_similar():
    cs,o=long_failed_breakout(True); x=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); assert x.state=='AWAITING_NEXT_BAR_COMPARISON'
def test_034_similar_forces_next_bar_can_confirm():
    cs,o=long_failed_breakout(True); cs.append(bar(3,98,99,94,95)); x=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); assert x.state=='CONFIRMED_BY_NEXT_BAR_FOLLOW_THROUGH' and x.next_bar_index==3
def test_034_reentry_without_reversal_setup_is_not_confirmed():
    cs=[bar(0,98,100,97,99),bar(1,99,104,98,103),bar(2,99,101,98,100)]; o=build_breakout_attempt_identity(tuple(cs),direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); x=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=False); assert x.state=='RETURN_INSIDE_NO_REVERSAL_SETUP'
def test_034_future_next_bar_not_used_at_signal_prefix():
    cs,o=long_failed_breakout(True); before=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True,evaluated_index=2); cs.append(bar(3,98,99,94,95)); after=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True,evaluated_index=3); assert before.state=='AWAITING_NEXT_BAR_COMPARISON' and after.state=='CONFIRMED_BY_NEXT_BAR_FOLLOW_THROUGH'
def test_034_bear_mirror():
    cs,o=short_failed_breakout(False); x=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); assert x.reversal_direction=='LONG' and x.state=='CONFIRMED_STRONG_REVERSAL_WEAK_BREAKOUT'

# BROOKS-GAP-035
def test_035_genuine_failure_of_failure_requires_trigger_then_later_failure():
    cs,o=long_failed_breakout(False); fb=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); cs.append(bar(3,98,100,96,97)); cs.append(bar(4,99,106,98,105)); x=classify_failure_of_failure(tuple(cs),fb); assert x.state=='FAILURE_OF_FAILURE_CONFIRMED' and x.later_failure_index==4 and x.breakout_origin.breakout_id==o.breakout_id
def test_035_not_present_at_first_failure_timestamp():
    cs,o=long_failed_breakout(False); fb=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); x=classify_failure_of_failure(tuple(cs),fb,evaluated_index=2); assert x.state=='FIRST_FAILURE_WAITING_FOR_TRIGGER'
def test_035_triggered_but_not_yet_failed():
    cs,o=long_failed_breakout(False); fb=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); cs.append(bar(3,98,100,96,97)); x=classify_failure_of_failure(tuple(cs),fb); assert x.state=='FIRST_FAILURE_ATTEMPT_TRIGGERED'
def test_035_untriggered_invalidation_cannot_seed_failure_of_failure():
    cs,o=long_failed_breakout(False); fb=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); cs.append(bar(3,102,106,99,104)); x=classify_failure_of_failure(tuple(cs),fb); assert x.state=='UNTRIGGERED_INVALIDATION_NOT_FIRST_FAILURE' and x.later_failure_index is None
def test_035_same_bar_trigger_and_failure_fails_closed():
    cs,o=long_failed_breakout(False); fb=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); cs.append(bar(3,100,106,96,101)); x=classify_failure_of_failure(tuple(cs),fb); assert x.state=='AMBIGUOUS_ORDER_FAIL_CLOSED'
def test_035_no_genuine_first_failure_means_no_failure_of_failure():
    cs,o=long_failed_breakout(True); fb=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True,evaluated_index=2); x=classify_failure_of_failure(tuple(cs),fb); assert x.state=='NO_GENUINE_FIRST_FAILURE' and x.reversal_origin is None
def test_035_bear_mirror_identity_chain():
    cs,o=short_failed_breakout(False); fb=classify_failed_breakout_confirmation(tuple(cs),o,signal_index=2,reversal_is_strong=True); cs.append(bar(3,102,104,100,103)); cs.append(bar(4,96,101,93,94)); x=classify_failure_of_failure(tuple(cs),fb); assert x.state=='FAILURE_OF_FAILURE_CONFIRMED' and x.breakout_origin.direction=='SHORT'

# BROOKS-GAP-036
def test_036_breakout_test_can_occur_more_than_20_bars_later():
    cs=[bar(0,98,100,97,99),bar(1,100,106,99,105)]; o=build_breakout_attempt_identity(tuple(cs),direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1)
    for i in range(2,23): cs.append(bar(i,103,106,101,104))
    cs.append(bar(23,103,105,99.5,102)); x=classify_breakout_test(tuple(cs),o,zone_low=D('99'),zone_high=D('100')); assert x and x.test_index==23
def test_036_breakout_test_prefix_has_no_future_test():
    cs=[bar(0,98,100,97,99),bar(1,100,106,99,105),bar(2,103,106,101,104),bar(3,103,105,99.5,102)]; o=build_breakout_attempt_identity(tuple(cs),direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); assert classify_breakout_test(tuple(cs),o,zone_low=D('99'),zone_high=D('100'),evaluated_index=2) is None and classify_breakout_test(tuple(cs),o,zone_low=D('99'),zone_high=D('100'),evaluated_index=3).test_index==3
def test_036_near_breakout_can_function_as_pullback_without_actual_breakout():
    cs=[bar(0,98,100,97,99),bar(1,98.5,99.8,98,99.4),bar(2,99.3,99.4,96,97)]; x=classify_near_breakout_pullback(tuple(cs),direction='LONG',reference_id='S',reference_level=D('100'),zone_low=D('99'),zone_high=D('100'),approach_index=1); assert x and x.kind=='NEAR_BREAKOUT_FUNCTIONAL_PULLBACK'
def test_036_actual_breakout_is_not_near_breakout_variant():
    cs=[bar(0,98,100,97,99),bar(1,99,101,98,100.5),bar(2,100,101,97,98)]; assert classify_near_breakout_pullback(tuple(cs),direction='LONG',reference_id='S',reference_level=D('100'),zone_low=D('99'),zone_high=D('100'),approach_index=1) is None
def test_036_unrelated_late_bar_outside_zone_not_test():
    cs=[bar(0,98,100,97,99),bar(1,100,106,99,105),bar(2,104,107,103,106)]; o=build_breakout_attempt_identity(tuple(cs),direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); assert classify_breakout_test(tuple(cs),o,zone_low=D('99'),zone_high=D('100')) is None
def test_036_bear_mirror_breakout_test():
    cs=[bar(0,101,103,100,102),bar(1,100,101,94,95),bar(2,97,100.5,95,96)]; o=build_breakout_attempt_identity(tuple(cs),direction='SHORT',reference_id='S',reference_level=D('100'),attempt_index=1); x=classify_breakout_test(tuple(cs),o,zone_low=D('100'),zone_high=D('101')); assert x and x.direction=='SHORT'

# BROOKS-GAP-037
def test_037_wick_only_attempt_is_explicit_state_not_successful_breakout():
    cs=(bar(0,98,100,97,99),bar(1,99,101,98,99.5)); o=build_breakout_attempt_identity(cs,direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); x=classify_breakout_lifecycle(cs,o); assert x.state=='BREAKOUT_ATTEMPT_ONLY' and not o.closed_beyond
def test_037_close_beyond_is_breakout_established():
    cs=(bar(0,98,100,97,99),bar(1,99,104,98,103)); o=build_breakout_attempt_identity(cs,direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); assert classify_breakout_lifecycle(cs,o).state=='BREAKOUT_ESTABLISHED'
def test_037_follow_through_is_later_state():
    cs=(bar(0,98,100,97,99),bar(1,99,104,98,103),bar(2,103,106,102,105)); o=build_breakout_attempt_identity(cs,direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); x=classify_breakout_lifecycle(cs,o); assert x.state=='FOLLOW_THROUGH_CONFIRMED' and x.follow_through_index==2
def test_037_failed_follow_through_reentry_is_explicit():
    cs=(bar(0,98,100,97,99),bar(1,99,104,98,103),bar(2,103,104,97,99)); o=build_breakout_attempt_identity(cs,direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); x=classify_breakout_lifecycle(cs,o); assert x.state=='FAILED_FOLLOW_THROUGH_REENTRY' and x.reentry_index==2
def test_037_future_reentry_not_backdated():
    cs=(bar(0,98,100,97,99),bar(1,99,104,98,103),bar(2,103,104,97,99)); o=build_breakout_attempt_identity(cs,direction='LONG',reference_id='S',reference_level=D('100'),attempt_index=1); assert classify_breakout_lifecycle(cs,o,evaluated_index=1).state=='BREAKOUT_ESTABLISHED' and classify_breakout_lifecycle(cs,o,evaluated_index=2).state=='FAILED_FOLLOW_THROUGH_REENTRY'
def test_037_bear_mirror_attempt():
    cs=(bar(0,101,103,100,102),bar(1,101,102,99,100.5)); o=build_breakout_attempt_identity(cs,direction='SHORT',reference_id='S',reference_level=D('100'),attempt_index=1); assert o and classify_breakout_lifecycle(cs,o).state=='BREAKOUT_ATTEMPT_ONLY'

# BROOKS-GAP-042
def compact_origin(): return CompactPatternOrigin('II','II:0:2',0,2,D('105'),D('95'))
def test_042_compact_breakout_preserves_origin_identity():
    cs=(bar(0,100,105,95,101),bar(1,100,104,96,101),bar(2,100,103,97,101),bar(3,102,107,101,106)); x=classify_compact_pattern_lifecycle(cs,compact_origin()); assert x.state=='BREAKOUT_ATTEMPT_ACTIVE' and x.origin.structure_id=='II:0:2'
def test_042_failed_breakout_returns_to_same_pattern():
    cs=(bar(0,100,105,95,101),bar(1,100,104,96,101),bar(2,100,103,97,101),bar(3,102,107,101,106),bar(4,105,106,99,101)); x=classify_compact_pattern_lifecycle(cs,compact_origin()); assert x.state=='FAILED_BREAKOUT_RETURNED_TO_SAME_PATTERN' and x.reentry_index==4
def test_042_opposite_breakout_after_failure_same_origin():
    cs=(bar(0,100,105,95,101),bar(1,100,104,96,101),bar(2,100,103,97,101),bar(3,102,107,101,106),bar(4,105,106,99,101),bar(5,100,101,93,94)); x=classify_compact_pattern_lifecycle(cs,compact_origin()); assert x.state=='OPPOSITE_BREAKOUT_AFTER_FAILURE' and x.opposite_break_index==5 and x.origin.structure_id=='II:0:2'
def test_042_breakout_pullback_same_pattern_identity():
    cs=(bar(0,100,105,95,101),bar(1,100,104,96,101),bar(2,100,103,97,101),bar(3,102,107,101,106),bar(4,106,108,104,106)); x=classify_compact_pattern_lifecycle(cs,compact_origin()); assert x.state=='BREAKOUT_PULLBACK_SAME_PATTERN' and x.pullback_index==4
def test_042_prefix_causality():
    cs=(bar(0,100,105,95,101),bar(1,100,104,96,101),bar(2,100,103,97,101),bar(3,102,107,101,106),bar(4,105,106,99,101),bar(5,100,101,93,94)); o=compact_origin(); assert classify_compact_pattern_lifecycle(cs,o,evaluated_index=3).state=='BREAKOUT_ATTEMPT_ACTIVE' and classify_compact_pattern_lifecycle(cs,o,evaluated_index=5).state=='OPPOSITE_BREAKOUT_AFTER_FAILURE'
def test_042_local_price_reversal_without_origin_is_not_constructed_by_classifier():
    assert classify_compact_pattern_lifecycle((bar(0,100,101,99,100),),compact_origin(),evaluated_index=0).state=='PATTERN_READY'

# BROOKS-GAP-043
def test_043_bodies_only_ii_recognized_when_tails_are_not_nested():
    cs=(bar(0,100,110,90,108),bar(1,102,112,88,106),bar(2,103,109,91,105)); assert _bodies_only_ii_at(cs,2)
def test_043_full_ii_is_not_relabelled_bodies_only_variant():
    cs=(bar(0,100,110,90,108),bar(1,102,109,91,106),bar(2,103,108,92,105)); assert not _bodies_only_ii_at(cs,2)
def test_043_non_nested_bodies_are_negative():
    cs=(bar(0,100,110,90,108),bar(1,99,112,88,109),bar(2,98,113,87,110)); assert not _bodies_only_ii_at(cs,2)
def test_043_variant_appears_only_after_second_nested_body_closes():
    cs=(bar(0,100,110,90,108),bar(1,102,112,88,106),bar(2,103,109,91,105)); assert not _bodies_only_ii_at(cs,1) and _bodies_only_ii_at(cs,2)
def test_043_has_no_numeric_threshold_dependency():
    cs=(bar(0,100,200,1,108),bar(1,102,250,0.5,106),bar(2,103,300,0.1,105)); assert _bodies_only_ii_at(cs,2)
def test_043_compact_identity_can_consume_bodies_only_variant_without_trade_promotion():
    o=CompactPatternOrigin('BODIES_ONLY_II','BODIES_ONLY_II:0:2',0,2,D('300'),D('0.1')); x=classify_compact_pattern_lifecycle((bar(0,100,200,1,108),bar(1,102,250,0.5,106),bar(2,103,300,0.1,105)),o); assert x.state=='PATTERN_READY' and x.origin.pattern_id=='BODIES_ONLY_II'
