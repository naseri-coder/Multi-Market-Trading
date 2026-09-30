from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.brooks_core.books_full_patterns import detect_double_top_bottom, detect_micro_double_top_bottom, detect_wedge_reversal
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.correction_lifecycle import (
    classify_wedge_second_signal, build_wedge_attempt_origin, evaluate_wedge_attempt_lifecycle,
)
from app.modules.brooks_core.structural_geometry import build_structural_second_test, build_micro_double_structure
from app.modules.brooks_core.structure_entities import ConfirmedSwing, SwingScanResult
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,7,1,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i); return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def snap(cs):
    cs=tuple(cs); return MarketSnapshot('binance','futures','BTCUSDT','15m',cs,cs[-1].close_time,'W07')
def sw(kind,i,price,confirmed=None): return ConfirmedSwing(kind,i,i if confirmed is None else confirmed,D(str(price)))
def scan(*xs): return SwingScanResult(tuple(xs),(),1,1)
def ctx(regime='TRADING_RANGE',always='UNRESOLVED'): return SimpleNamespace(regime=regime,always_in=always,structure_direction=regime)
POL=BrooksFullCorePolicy()

def second_test_candles():
    return [bar(0,100,104,96,101),bar(1,101,105,90,94),bar(2,94,110,93,108),bar(3,108,109,94,97),bar(4,97,106,95,104),bar(5,104,107,94,96)]

def top_wedge_sequence():
    return [bar(0,100,102,99,101),bar(1,101,104,100,103),bar(2,103,104,100,102),bar(3,102,106,101,105),bar(4,105,106,102,104),bar(5,104,108,103,107),bar(6,107,108,101,102),bar(7,102,109,102,108),bar(8,108,109,100,101)]

# 051 structural second-test process
def test_051_structural_double_bottom_allows_higher_second_bottom_outside_legacy_band():
    cs=second_test_candles(); g=build_structural_second_test(tuple(cs),scan(sw('LOW',1,90),sw('HIGH',2,110),sw('LOW',3,94)),side='BOTTOM',evaluated_index=5)
    assert g and g.price_relation=='HIGHER_TEST' and g.zone_low==D('90') and g.zone_high==D('94')
def test_051_structural_double_top_directional_mirror():
    cs=[bar(0,100,101,95,97),bar(1,97,110,96,108),bar(2,108,109,90,92),bar(3,92,106,91,94),bar(4,94,105,92,93)]
    g=build_structural_second_test(tuple(cs),scan(sw('HIGH',1,110),sw('LOW',2,90),sw('HIGH',3,106)),side='TOP',evaluated_index=4)
    assert g and g.price_relation=='LOWER_TEST'
def test_051_numeric_equality_without_intervening_move_is_not_structural_double():
    cs=second_test_candles(); assert build_structural_second_test(tuple(cs),scan(sw('LOW',1,90),sw('LOW',3,90)),side='BOTTOM',evaluated_index=5) is None
def test_051_second_test_is_not_available_before_causal_confirmation():
    cs=second_test_candles(); q=scan(sw('LOW',1,90,2),sw('HIGH',2,110,3),sw('LOW',3,94,5))
    assert build_structural_second_test(tuple(cs),q,side='BOTTOM',evaluated_index=4) is None
    assert build_structural_second_test(tuple(cs),q,side='BOTTOM',evaluated_index=5) is not None
def test_051_detector_carries_structural_identity_not_equality_gate():
    cs=second_test_candles(); cs[-1]=bar(5,96,100,92,99); q=scan(sw('LOW',1,90),sw('HIGH',2,110),sw('LOW',3,94))
    with patch('app.modules.brooks_core.books_full_patterns.confirm_swings_causally',return_value=q): f=detect_double_top_bottom(snap(cs),ctx(),POL)
    x=next(z for z in f if z.direction=='LONG'); m=dict(x.metadata); assert m['price_relation']=='HIGHER_TEST' and m['semantic']=='STRUCTURAL_SECOND_TEST_NOT_NUMERIC_EQUALITY_ONLY'
def test_051_similar_prices_from_unrelated_unbridged_tests_do_not_merge():
    cs=second_test_candles(); q=scan(sw('LOW',1,90),sw('HIGH',2,110),sw('LOW',3,94),sw('LOW',5,94))
    g=build_structural_second_test(tuple(cs),q,side='BOTTOM',evaluated_index=5); assert g and g.second_test_index==3

# 052 micro-double near-consecutive semantics
def test_052_adjacent_micro_double_top_still_recognized():
    cs=(bar(0,100,105,98,104),bar(1,104,105.2,99,100)); g=build_micro_double_structure(cs,side='TOP',max_bar_distance=3,engineering_tolerance=D('1'))
    assert g and g.bar_distance==1
def test_052_nearly_consecutive_micro_double_bottom_two_bars_apart():
    cs=(bar(0,100,104,95,97),bar(1,100,107,98,105),bar(2,105,106,95.3,104)); g=build_micro_double_structure(cs,side='BOTTOM',max_bar_distance=3,engineering_tolerance=D('1'))
    assert g and g.bar_distance==2 and g.intervening_move_away
def test_052_nearly_consecutive_micro_double_top_three_bars_apart():
    cs=(bar(0,100,105,99,104),bar(1,103,103.5,95,96),bar(2,96,102,94,101),bar(3,101,105.2,98,99)); g=build_micro_double_structure(cs,side='TOP',max_bar_distance=3,engineering_tolerance=D('1'))
    assert g and g.bar_distance==3
def test_052_distant_extrema_are_not_micro_double():
    cs=tuple([bar(0,100,105,99,104)]+[bar(i,100,101,95,100) for i in range(1,4)]+[bar(4,104,105.1,99,100)])
    assert build_micro_double_structure(cs,side='TOP',max_bar_distance=3,engineering_tolerance=D('1')) is None
def test_052_near_price_without_intervening_move_away_is_not_nearly_consecutive_structure():
    cs=(bar(0,100,105,99,104),bar(1,100,101,99.5,100),bar(2,104,105.1,99.2,100)); assert build_micro_double_structure(cs,side='TOP',max_bar_distance=3,engineering_tolerance=D('1')) is None
def test_052_detector_recognizes_nearly_consecutive_and_reports_engineering_search_policy():
    cs=[bar(i,100,103,97,100) for i in range(17)]+[bar(17,100,105,99,104),bar(18,103,103.5,95,96),bar(19,101,105.2,98,99)]
    f=detect_micro_double_top_bottom(snap(cs),ctx(),POL); x=next(z for z in f if z.direction=='SHORT'); assert dict(x.metadata)['bar_distance']=='2' and dict(x.metadata)['search_policy'].startswith('ENGINEERING_SEARCH_POLICY')
def test_052_general_distant_double_is_not_automatically_micro_double():
    cs=tuple([bar(0,100,105,99,104)]+[bar(i,100,110 if i==3 else 103,95,100) for i in range(1,7)]+[bar(7,104,105,99,100)])
    assert build_micro_double_structure(cs,side='TOP',max_bar_distance=3,engineering_tolerance=D('1')) is None

# 053 wedge second signal
def test_053_wedge_first_attempt_identity_is_attached_to_pushes():
    cs=tuple(top_wedge_sequence()[:7]); x=classify_wedge_second_signal(cs,push_indices=(1,3,5),side='TOP')
    assert x and x.first_attempt_index==6 and x.second_attempt_index is None and x.wedge_structure_id=='WEDGE:TOP:1:3:5'
def test_053_first_attempt_failure_and_resumption_preserved():
    cs=tuple(top_wedge_sequence()[:8]); x=classify_wedge_second_signal(cs,push_indices=(1,3,5),side='TOP'); assert x.state=='FIRST_ATTEMPT_FAILED_RESUMPTION' and x.resumption_index==7
def test_053_valid_later_second_wedge_signal():
    cs=tuple(top_wedge_sequence()); x=classify_wedge_second_signal(cs,push_indices=(1,3,5),side='TOP'); assert x.state=='SECOND_REVERSAL_ATTEMPT' and x.second_attempt_index==8
def test_053_generic_second_reversal_without_valid_wedge_identity_is_not_wedge_second_signal():
    cs=tuple(top_wedge_sequence()); assert classify_wedge_second_signal(cs,push_indices=(5,3,1),side='TOP') is None
def test_053_future_second_signal_not_present_on_earlier_prefix():
    cs=tuple(top_wedge_sequence()); assert classify_wedge_second_signal(cs,push_indices=(1,3,5),side='TOP',evaluated_index=7).second_attempt_index is None
def test_053_countertrend_detector_requires_second_signal_or_strong_first():
    cs=top_wedge_sequence(); q=scan(sw('HIGH',1,104),sw('LOW',2,100),sw('HIGH',3,106),sw('LOW',4,102),sw('HIGH',5,108))
    with patch('app.modules.brooks_core.books_full_patterns.confirm_swings_causally',return_value=q): f=detect_wedge_reversal(snap(cs),ctx('BULL_TREND','LONG'),POL)
    assert any(dict(x.metadata)['signal_identity']=='SECOND_WEDGE_SIGNAL' for x in f)
def test_053_three_pushes_without_reversal_sequence_are_not_second_signal():
    cs=[bar(i,100+i,102+i,99+i,101+i) for i in range(9)]; q=scan(sw('HIGH',1,103),sw('HIGH',3,105),sw('HIGH',5,107))
    with patch('app.modules.brooks_core.books_full_patterns.confirm_swings_causally',return_value=q): assert not detect_wedge_reversal(snap(cs),ctx('BULL_TREND','LONG'),POL)

# 054 wedge failure lifecycle using shared W05 engine
def wedge_origin(cs,objective=None,signal=1):
    w=classify_wedge_second_signal(tuple(cs),push_indices=(1,3,5),side='TOP'); return build_wedge_attempt_origin(tuple(cs),w,signal_number=signal,objective_level=None if objective is None else D(str(objective)))
def test_054_originating_wedge_attempt_preserves_structure_and_signal_identity():
    cs=top_wedge_sequence()[:7]; o=wedge_origin(cs); assert o and o.wedge.wedge_structure_id=='WEDGE:TOP:1:3:5' and ':S1:6' in o.reversal_origin.attempt_id
def test_054_untriggered_invalidation_is_not_failed_entered_wedge():
    cs=top_wedge_sequence()[:7]+[bar(7,102,109,102,108)]; x=evaluate_wedge_attempt_lifecycle(tuple(cs),wedge_origin(cs,90)); assert x.state=='SIGNAL_INVALIDATED_BEFORE_TRIGGER' and not x.failure_confirmed
def test_054_triggered_active_wedge_attempt():
    cs=top_wedge_sequence()[:7]+[bar(7,102,104,97,99)]; x=evaluate_wedge_attempt_lifecycle(tuple(cs),wedge_origin(cs,90)); assert x.state=='TRIGGERED_ACTIVE'
def test_054_triggered_failure_before_owned_objective_is_confirmed():
    cs=top_wedge_sequence()[:7]+[bar(7,102,104,97,99),bar(8,99,109,95,108)]; x=evaluate_wedge_attempt_lifecycle(tuple(cs),wedge_origin(cs,90)); assert x.state=='FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE' and x.failure_confirmed
def test_054_objective_before_later_failure_is_not_failed_attempt():
    cs=top_wedge_sequence()[:7]+[bar(7,102,104,97,99),bar(8,99,100,89,91),bar(9,91,110,90,108)]; x=evaluate_wedge_attempt_lifecycle(tuple(cs),wedge_origin(cs,90)); assert x.state=='OBJECTIVE_REACHED' and not x.failure_confirmed
def test_054_same_bar_trigger_failure_unknown_order_fails_closed():
    cs=top_wedge_sequence()[:7]+[bar(7,102,109,97,103)]; x=evaluate_wedge_attempt_lifecycle(tuple(cs),wedge_origin(cs,90)); assert x.state=='AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR' and not x.failure_confirmed
def test_054_future_failure_does_not_backdate_trigger_prefix():
    cs=top_wedge_sequence()[:7]+[bar(7,102,104,97,99),bar(8,99,109,95,108)]; o=wedge_origin(cs,90); assert evaluate_wedge_attempt_lifecycle(tuple(cs),o,evaluated_index=7).state=='TRIGGERED_ACTIVE'; assert evaluate_wedge_attempt_lifecycle(tuple(cs),o).failure_confirmed
def test_054_unowned_objective_fails_closed_and_does_not_implement_failure_of_failure():
    cs=top_wedge_sequence()[:7]+[bar(7,102,104,97,99),bar(8,99,109,95,108)]; x=evaluate_wedge_attempt_lifecycle(tuple(cs),wedge_origin(cs,None)); assert x.state=='FAILURE_LEVEL_BREACHED_OBJECTIVE_UNSPECIFIED' and not x.failure_confirmed and 'FAILURE_OF_FAILURE' not in x.state
