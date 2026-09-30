from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.modules.brooks_core.correction_lifecycle import (
    build_active_trend_episode,
    build_exhaustion_origin,
    classify_climax_outcome,
    classify_head_shoulders_outcome,
    classify_mtr_retest_lifecycle,
)
from app.modules.market_data.entities import Candle

BASE=datetime(2026,9,1,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def bull_seq():
    return tuple(bar(i,100+i,103+i,99+i,102+i) for i in range(8))
def bear_seq():
    return tuple(bar(i,120-i,121-i,117-i,118-i) for i in range(8))
def origin_bull(cs=None,idx=4,late=True,evidence=True):
    cs=cs or bull_seq(); trend=build_active_trend_episode(trend_direction='BULL_TREND',origin_index=0,evaluated_index=idx,late_trend=late)
    return build_exhaustion_origin(cs,trend,origin_index=idx,engineering_acceleration_evidence=evidence)
def origin_bear(cs=None,idx=4,late=True,evidence=True):
    cs=cs or bear_seq(); trend=build_active_trend_episode(trend_direction='BEAR_TREND',origin_index=0,evaluated_index=idx,late_trend=late)
    return build_exhaustion_origin(cs,trend,origin_index=idx,engineering_acceleration_evidence=evidence)

# BROOKS-GAP-063
def test_063_late_trend_acceleration_builds_exhaustion_origin():
    x=origin_bull(); assert x and x.state=='EXHAUSTION_ORIGIN_PENDING_OUTCOME' and x.exhaustion_id.endswith(':4')
def test_063_identical_large_bar_without_late_trend_is_not_exhaustion():
    assert origin_bull(late=False) is None
def test_063_engineering_size_evidence_alone_is_not_source_identity():
    assert origin_bull(evidence=False) is None
def test_063_bear_directional_mirror_preserves_origin():
    x=origin_bear(); assert x and x.direction=='SHORT' and x.trend.trend_direction=='BEAR_TREND'
def test_063_origin_is_outcome_pending_not_automatic_trade_state():
    x=origin_bull(); assert x and 'PENDING_OUTCOME' in x.state and not hasattr(x,'trade_eligible')
def test_063_future_outcome_does_not_mutate_origin_identity():
    cs=list(bull_seq()); x=origin_bull(tuple(cs)); cs.append(bar(8,108,109,102,103)); y=classify_climax_outcome(tuple(cs),x,current_regime='BULL_TREND',evaluated_index=8); assert y.origin.exhaustion_id==x.exhaustion_id and x.state=='EXHAUSTION_ORIGIN_PENDING_OUTCOME'
def test_063_no_universal_numeric_rule_encoded_in_origin_model():
    x=origin_bull(); assert x.engineering_acceleration_evidence is True and 'EXHAUSTION' in x.exhaustion_id

# BROOKS-GAP-064
def test_064_t1_origin_valid_but_dependent_outcome_not_yet_valid():
    cs=bull_seq(); x=origin_bull(cs); life=classify_climax_outcome(cs,x,current_regime='BULL_TREND',evaluated_index=4); assert life.state=='PENDING_CLIMAX_OUTCOME'
def test_064_later_reversal_attempt_uses_same_063_origin():
    cs=list(bull_seq()[:5]); cs.append(bar(5,105,106,99,100)); x=origin_bull(tuple(cs),idx=4); life=classify_climax_outcome(tuple(cs),x,current_regime='BULL_TREND',evaluated_index=5); assert life.state=='REVERSAL_ATTEMPT_PENDING_OUTCOME' and life.origin.exhaustion_id==x.exhaustion_id and life.reversal_attempt_index==5
def test_064_range_outcome_is_causal_same_origin():
    cs=list(bull_seq()[:5]); cs.append(bar(5,105,106,99,100)); x=origin_bull(tuple(cs),idx=4); life=classify_climax_outcome(tuple(cs),x,current_regime='TRADING_RANGE',evaluated_index=5); assert life.state=='RESOLVED_TRADING_RANGE' and life.origin.exhaustion_id==x.exhaustion_id
def test_064_opposite_trend_outcome_is_causal_same_origin():
    cs=list(bull_seq()[:5]); cs.append(bar(5,105,106,99,100)); x=origin_bull(tuple(cs),idx=4); life=classify_climax_outcome(tuple(cs),x,current_regime='BEAR_TREND',current_always_in='SHORT',evaluated_index=5); assert life.state=='RESOLVED_OPPOSITE_TREND'
def test_064_continuation_after_reversal_attempt_preserves_origin():
    cs=list(bull_seq()[:5]); cs.append(bar(5,105,106,99,100)); cs.append(bar(6,101,110,100,109)); x=origin_bull(tuple(cs),idx=4); life=classify_climax_outcome(tuple(cs),x,current_regime='BULL_TREND',evaluated_index=6); assert life.state=='RESOLVED_CONTINUATION' and life.transition_index==6
def test_064_false_transition_without_valid_063_origin_is_impossible():
    cs=bull_seq(); assert origin_bull(cs,late=False) is None
def test_064_bear_mirror_reversal_attempt():
    cs=list(bear_seq()[:5]); cs.append(bar(5,115,121,114,120)); x=origin_bear(tuple(cs),idx=4); life=classify_climax_outcome(tuple(cs),x,current_regime='BEAR_TREND',evaluated_index=5); assert life.state=='REVERSAL_ATTEMPT_PENDING_OUTCOME' and life.origin.direction=='SHORT'

# BROOKS-GAP-058
def test_058_hns_shape_defaults_to_alias_range_flag_context_not_trade():
    x=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=2,head_index=4,right_shoulder_index=6,neckline_state='ALIAS_RANGE_OR_FLAG'); assert x.state=='ALIAS_RANGE_OR_FLAG_CONTEXT' and not x.trade_eligible
def test_058_failed_neckline_break_reentry_prioritizes_with_trend_continuation():
    x=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=2,head_index=4,right_shoulder_index=6,neckline_state='FAILED_NECKLINE_BREAK_REENTRY'); assert x.state=='WITH_TREND_CONTINUATION_CONTEXT' and x.with_trend_direction=='LONG'
def test_058_single_neckline_break_is_only_pending_reversal_followthrough():
    x=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=2,head_index=4,right_shoulder_index=6,neckline_state='NECKLINE_BREAK'); assert x.state=='REVERSAL_ATTEMPT_PENDING_FOLLOW_THROUGH' and not x.trade_eligible
def test_058_sustained_neckline_followthrough_is_reversal_context_not_trade():
    x=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=2,head_index=4,right_shoulder_index=6,neckline_state='CONTINUATION_BEYOND_NECKLINE'); assert x.state=='REVERSAL_FOLLOW_THROUGH_CONTEXT' and x.reversal_direction=='SHORT' and not x.trade_eligible
def test_058_bottom_mirror_preserves_source_identity():
    x=classify_head_shoulders_outcome(side='BOTTOM',left_shoulder_index=3,head_index=5,right_shoulder_index=7,neckline_state='FAILED_NECKLINE_BREAK_REENTRY'); assert x.structure_id=='HNS:BOTTOM:3:5:7' and x.with_trend_direction=='SHORT' and x.reversal_direction=='LONG'
def test_058_invalid_side_cannot_manufacture_identity():
    assert classify_head_shoulders_outcome(side='MIDDLE',left_shoulder_index=1,head_index=2,right_shoulder_index=3,neckline_state='ALIAS_RANGE_OR_FLAG') is None
def test_058_hns_identity_does_not_collide_with_climax_identity():
    h=classify_head_shoulders_outcome(side='TOP',left_shoulder_index=2,head_index=4,right_shoulder_index=6,neckline_state='ALIAS_RANGE_OR_FLAG'); e=origin_bull(); assert h.structure_id != e.exhaustion_id
