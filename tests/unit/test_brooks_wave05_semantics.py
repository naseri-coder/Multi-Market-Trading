from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.correction_lifecycle import (
    ReversalPatternOrigin,
    classify_generic_reversal_attempts,
    classify_structural_correction,
    evaluate_reversal_pattern_lifecycle,
)
from app.modules.brooks_core.pattern_expansion import _extended_entry_count, detect_reversal_bar_failure
from app.modules.brooks_core.second_entry_v2 import detect_book_second_entry
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,3,1,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def snap(cs):
    cs=tuple(cs); return MarketSnapshot('binance','futures','BTCUSDT','15m',cs,cs[-1].close_time,'W05')
def ctx(regime): return SimpleNamespace(regime=regime)

# BROOKS-GAP-013
def test_013_full_resumption_resets_extended_count_episode():
    cs=(bar(0,100,105,99,103),bar(1,100,101,95,97),bar(2,97,102,96,101),bar(3,101,106,100,105),bar(4,104,105,99,100),bar(5,100,105.5,100,103))
    assert _extended_entry_count(cs,direction='LONG',start=0)==(1,5)
def test_013_reaction_inside_origin_does_not_false_reset():
    cs=(bar(0,100,105,99,103),bar(1,103,103,95,97),bar(2,97,102,96,101),bar(3,101,104,99,103),bar(4,103,103,97,98),bar(5,98,104,98,103))
    assert _extended_entry_count(cs,direction='LONG',start=0)==(2,5)
def test_013_bear_reset_is_directional_mirror():
    cs=(bar(0,100,101,95,97),bar(1,97,105,97,103),bar(2,103,104,96,99),bar(3,99,100,94,95),bar(4,95,101,95,100),bar(5,100,100,94.5,97))
    assert _extended_entry_count(cs,direction='SHORT',start=0)==(1,5)
def test_013_reset_is_not_known_before_resumption_bar():
    prefix=(bar(0,100,105,99,103),bar(1,100,101,95,97),bar(2,97,102,96,101))
    assert _extended_entry_count(prefix,direction='LONG',start=0)==(1,2)

# BROOKS-GAP-015
def test_015_structural_abc_second_leg_need_not_make_new_extreme():
    cs=(bar(0,100,105,99,103),bar(1,103,103,95,97),bar(2,97,102,96,101),bar(3,101,101.5,96.5,98))
    x=classify_structural_correction(cs,trend_direction='BULL_TREND',start_index=0)
    assert x and x.two_legged and x.first_leg.start_index==1 and x.reaction.start_index==2 and x.second_leg.start_index==3
    assert cs[3].low>cs[1].low
def test_015_two_arbitrary_countertrend_bars_are_not_two_legs():
    cs=(bar(0,100,105,99,103),bar(1,103,103,97,99),bar(2,99,100,96,98))
    x=classify_structural_correction(cs,trend_direction='BULL_TREND',start_index=0)
    assert x and not x.two_legged and x.reaction is None
def test_015_second_leg_is_causal_prefix_state():
    cs=(bar(0,100,105,99,103),bar(1,103,103,95,97),bar(2,97,102,96,101),bar(3,101,101.5,96.5,98))
    assert not classify_structural_correction(cs,trend_direction='BULL_TREND',start_index=0,evaluated_index=2).two_legged
    assert classify_structural_correction(cs,trend_direction='BULL_TREND',start_index=0,evaluated_index=3).two_legged
def test_015_bear_two_legged_correction_mirror():
    cs=(bar(0,100,101,95,97),bar(1,97,105,97,103),bar(2,103,104,96,99),bar(3,99,103.5,96.5,102))
    x=classify_structural_correction(cs,trend_direction='BEAR_TREND',start_index=0)
    assert x and x.two_legged and x.second_leg.direction=='UP'
def test_015_h2_accepts_structural_second_leg_without_fresh_low():
    cs=(bar(0,100,105,99,103),bar(1,100,101,95,97),bar(2,97,102,96,101),bar(3,101,101.5,96.5,98),bar(4,98,102,97,101))
    r=detect_book_second_entry(cs,trend_direction='BULL_TREND',start_index=0)
    assert r.setup and r.setup.setup_type=='H2_CONFIRMED' and r.setup.second_excursion_index==3

# BROOKS-GAP-016
def reversal_sequence(): return (bar(0,100,104,99,103),bar(1,103,104,98,99),bar(2,99,105,99,104),bar(3,104,105,98,99))
def test_016_generic_second_reversal_preserves_attempt_identity():
    x=classify_generic_reversal_attempts(reversal_sequence(),trend_direction='BULL_TREND')
    assert x.state=='SECOND_REVERSAL_ATTEMPT' and (x.first_attempt_index,x.resumption_index,x.second_attempt_index)==(1,2,3)
def test_016_first_attempt_is_not_second_reversal():
    x=classify_generic_reversal_attempts(reversal_sequence()[:2],trend_direction='BULL_TREND')
    assert x.state=='FIRST_REVERSAL_ATTEMPT' and x.second_attempt_index is None
def test_016_second_reversal_unavailable_before_it_closes():
    assert classify_generic_reversal_attempts(reversal_sequence()[:3],trend_direction='BULL_TREND').state=='FIRST_ATTEMPT_FAILED_RESUMPTION'
    assert classify_generic_reversal_attempts(reversal_sequence(),trend_direction='BULL_TREND').state=='SECOND_REVERSAL_ATTEMPT'
def test_016_bear_trend_mirror():
    cs=(bar(0,100,101,96,97),bar(1,97,103,96,102),bar(2,102,102,95,96),bar(3,96,103,95,102))
    x=classify_generic_reversal_attempts(cs,trend_direction='BEAR_TREND')
    assert x.state=='SECOND_REVERSAL_ATTEMPT' and x.reversal_direction=='LONG'
def test_016_generic_state_is_not_h2_or_wedge_trade_identity():
    x=classify_generic_reversal_attempts(reversal_sequence(),trend_direction='BULL_TREND')
    assert 'H2' not in x.state and 'WEDGE' not in x.state

# BROOKS-GAP-060
def origin(direction='SHORT'):
    return ReversalPatternOrigin('attempt-1','REVERSAL_TEST',direction,1,D('95') if direction=='SHORT' else D('105'),D('90') if direction=='SHORT' else D('110'),D('105') if direction=='SHORT' else D('95'))
def test_060_trigger_then_objective_preserves_origin():
    cs=(bar(0,100,103,97,101),bar(1,101,105,95,99),bar(2,99,104,94,96),bar(3,96,100,89,91))
    x=evaluate_reversal_pattern_lifecycle(cs,origin())
    assert x.state=='OBJECTIVE_REACHED' and x.trigger_index==2 and x.objective_index==3 and x.origin.attempt_id=='attempt-1'
def test_060_trigger_then_failure_is_typed_and_trapped():
    cs=(bar(0,100,103,97,101),bar(1,101,105,95,99),bar(2,99,104,94,96),bar(3,96,106,93,104))
    x=evaluate_reversal_pattern_lifecycle(cs,origin())
    assert x.state=='FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE' and x.failure_index==3 and x.trapped_side=='SHORT'
def test_060_wrong_side_before_trigger_is_signal_invalidation_not_triggered_failure():
    cs=(bar(0,100,103,97,101),bar(1,101,105,95,99),bar(2,99,106,96,104))
    x=evaluate_reversal_pattern_lifecycle(cs,origin())
    assert x.state=='SIGNAL_INVALIDATED_BEFORE_TRIGGER' and x.trigger_index is None
def test_060_same_bar_trigger_and_failure_fails_closed_as_ambiguous():
    cs=(bar(0,100,103,97,101),bar(1,101,105,95,99),bar(2,99,106,94,100))
    assert evaluate_reversal_pattern_lifecycle(cs,origin()).state=='AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR'
def test_060_future_failure_does_not_backdate_active_trigger():
    cs=(bar(0,100,103,97,101),bar(1,101,105,95,99),bar(2,99,104,94,96),bar(3,96,106,93,104))
    assert evaluate_reversal_pattern_lifecycle(cs[:3],origin()).state=='TRIGGERED_ACTIVE'
    assert evaluate_reversal_pattern_lifecycle(cs,origin()).state=='FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE'
def test_060_existing_reversal_bar_failure_now_carries_origin_identity():
    cs=[bar(0,100,102,99,101),bar(1,101,102,98,99),bar(2,99,103,98.5,102.5)]
    f=detect_reversal_bar_failure(snap(cs),ctx('BULL_TREND'),BrooksFullCorePolicy())
    assert len(f)==1 and dict(f[0].metadata)['lifecycle_state']=='SIGNAL_INVALIDATED_BEFORE_TRIGGER'
