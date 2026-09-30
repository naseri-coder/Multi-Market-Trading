from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.brooks_core.books_entities import RangeHierarchyContext
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.correction_lifecycle import (
    classify_hl_recurrence,
    classify_range_hl_location,
    evaluate_hl_entry_attempt_lifecycle,
    classify_generic_reversal_attempts,
)
from app.modules.brooks_core.pattern_catalog import CoverageRole, pattern_coverage_catalog
from app.modules.brooks_core.pattern_expansion import (
    _extended_entry_count,
    detect_extended_h4_l4,
    scan_extended_hl_recurrence_observations,
    scan_failed_hl_entry_observations,
    scan_range_hl_context_observations,
)
from app.modules.brooks_core.second_entry_v2 import detect_book_second_entry
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,4,1,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def snap(cs):
    cs=tuple(cs); return MarketSnapshot('binance','futures','BTCUSDT','15m',cs,cs[-1].close_time,'W06')
def bull_h2():
    return (bar(0,100,105,99,103),bar(1,103,103,95,97),bar(2,97,104,96,101),bar(3,101,103,97,98),bar(4,98,104,98,102))
def bear_l2():
    return (bar(0,100,101,95,97),bar(1,97,105,97,103),bar(2,103,104,96,99),bar(3,99,103,97,102),bar(4,102,103,96,98))
def extended_h4():
    return (bar(0,105,110,100,108),bar(1,108,109,96,99),bar(2,99,109.5,98,105),bar(3,105,109,99,101),bar(4,101,109.5,100,105),bar(5,105,109,100,101),bar(6,101,109.5,100,105),bar(7,105,109,100,101),bar(8,101,109.5,100,105))
def fake_swing(kind='HIGH',idx=0): return SimpleNamespace(kind=kind,candle_index=idx)
def range_ctx(): return SimpleNamespace(regime='TRADING_RANGE',structure_direction='AMBIGUOUS',range_evidence=SimpleNamespace(composite_supported=True))
def trend_ctx(): return SimpleNamespace(regime='BULL_TREND',structure_direction='BULL_TREND')
def hierarchy(position='NEAR_ENCLOSING_LOW', relation=None, local_low='95', local_high='110'):
    return RangeHierarchyContext(True,D(local_low),D(local_high),D('90'),D('130'),position,relation or position,True,True,5,20)

# BROOKS-GAP-012
def test_012_same_episode_h2_allows_shallower_second_leg():
    r=detect_book_second_entry(bull_h2(),trend_direction='BULL_TREND',start_index=0)
    assert r.setup and r.setup.setup_type=='H2_CONFIRMED' and r.setup.second_excursion_index==3
    assert bull_h2()[3].low > bull_h2()[1].low
def test_012_two_trigger_looking_bars_without_lower_high_do_not_make_h2():
    cs=(bar(0,100,105,99,103),bar(1,103,103,95,97),bar(2,97,104,96,101),bar(3,101,104.5,97,102),bar(4,102,105,98,104))
    assert detect_book_second_entry(cs,trend_direction='BULL_TREND',start_index=0).setup is None
def test_012_true_reset_rearms_new_h1():
    cs=(bar(0,100,105,99,103),bar(1,100,101,95,97),bar(2,97,102,96,101),bar(3,101,106,100,105),bar(4,104,105,99,100),bar(5,100,105.5,100,103))
    r=classify_hl_recurrence(cs,trend_direction='BULL_TREND',start_index=0)
    assert r.reset_index==3 and r.episode_origin_index==3 and [x.label for x in r.events]==['H1']
def test_012_false_reset_preserves_same_episode_h2():
    cs=(bar(0,100,105,99,103),bar(1,103,103,95,97),bar(2,97,104,96,101),bar(3,101,103,97,98),bar(4,98,104,98,102))
    r=classify_hl_recurrence(cs,trend_direction='BULL_TREND',start_index=0)
    assert r.reset_index is None and [x.label for x in r.events]==['H1','H2']
def test_012_h2_is_not_known_on_prefix_before_event():
    assert [x.label for x in classify_hl_recurrence(bull_h2()[:4],trend_direction='BULL_TREND',start_index=0).events]==['H1']
    assert [x.label for x in classify_hl_recurrence(bull_h2(),trend_direction='BULL_TREND',start_index=0).events]==['H1','H2']
def test_012_l2_directional_mirror():
    r=detect_book_second_entry(bear_l2(),trend_direction='BEAR_TREND',start_index=0)
    assert r.setup and r.setup.setup_type=='L2_CONFIRMED' and r.setup.direction=='SHORT'

# BROOKS-GAP-014
def test_014_same_episode_h3_is_typed_recurrence_not_arbitrary_count():
    r=classify_hl_recurrence(extended_h4()[:7],trend_direction='BULL_TREND',start_index=0)
    assert [x.label for x in r.events]==['H1','H2','H3'] and r.episode_origin_index==0
def test_014_h4_remains_same_episode_recurrence():
    r=classify_hl_recurrence(extended_h4(),trend_direction='BULL_TREND',start_index=0)
    assert [x.label for x in r.events]==['H1','H2','H3','H4']
def test_014_count_alone_no_longer_emits_trade_candidate():
    assert detect_extended_h4_l4(snap(extended_h4()),trend_ctx(),BrooksFullCorePolicy())==()
def test_014_h4_catalog_role_is_observation():
    row=next(x for x in pattern_coverage_catalog() if x.pattern_id=='H4_L4_COMPLEX_PULLBACK')
    assert row.role==CoverageRole.OBSERVATION

# BROOKS-GAP-017
def h2_then(*tail): return bull_h2()+tuple(tail)
def recurrence_h2(): return classify_hl_recurrence(bull_h2(),trend_direction='BULL_TREND',start_index=0)
def test_017_trigger_then_failure_before_owned_objective_is_failed_attempt():
    cs=h2_then(bar(5,102,105,99,104),bar(6,104,105,97,99))
    x=evaluate_hl_entry_attempt_lifecycle(cs,recurrence_h2(),event_number=2,objective_level=D('108'))
    assert x.state=='FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE' and x.trigger_index==5 and x.failure_index==6 and x.origin.pattern_id=='H2'
def test_017_objective_first_prevents_failed_h2_label():
    cs=h2_then(bar(5,102,105,99,104),bar(6,104,109,99,108))
    x=evaluate_hl_entry_attempt_lifecycle(cs,recurrence_h2(),event_number=2,objective_level=D('108'))
    assert x.state=='OBJECTIVE_REACHED' and x.failure_index is None
def test_017_untriggered_opposite_break_is_invalidation_not_failed_entry():
    cs=h2_then(bar(5,102,104,97,98))
    x=evaluate_hl_entry_attempt_lifecycle(cs,recurrence_h2(),event_number=2,objective_level=D('108'))
    assert x.state=='SIGNAL_INVALIDATED_BEFORE_TRIGGER' and x.trigger_index is None
def test_017_same_bar_trigger_failure_is_fail_closed_ambiguous():
    cs=h2_then(bar(5,102,105,97,101))
    assert evaluate_hl_entry_attempt_lifecycle(cs,recurrence_h2(),event_number=2,objective_level=D('108')).state=='AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR'
def test_017_future_failure_not_backdated_to_trigger_prefix():
    cs=h2_then(bar(5,102,105,99,104),bar(6,104,105,97,99))
    assert evaluate_hl_entry_attempt_lifecycle(cs[:6],recurrence_h2(),event_number=2,objective_level=D('108')).state=='TRIGGERED_ACTIVE'
    assert evaluate_hl_entry_attempt_lifecycle(cs,recurrence_h2(),event_number=2,objective_level=D('108')).state=='FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE'
def test_017_runtime_without_objective_does_not_overclaim_failed_h2():
    cs=h2_then(bar(5,102,105,99,104),bar(6,104,105,99,103),bar(7,103,104,97,98))
    fake=SimpleNamespace(swings=(fake_swing('HIGH',0),))
    with patch('app.modules.brooks_core.pattern_expansion.confirm_swings_causally',return_value=fake):
        obs=scan_failed_hl_entry_observations(snap(cs),SimpleNamespace(structure_direction='BULL_TREND'),BrooksFullCorePolicy())
    assert obs and obs[0].pattern_id=='H2_OUTCOME_CONTEXT'
    md=dict(obs[0].metadata); assert md['failure_confirmed']=='false' and md['objective_owned']=='false' and md['attempt_id'].startswith('H2:')

# BROOKS-GAP-039
def test_039_enclosing_low_edge_is_distinct_location_context():
    x=classify_range_hl_location(hierarchy(),current_price=D('96'),edge_zone_fraction=D('0.25'))
    assert x.semantic=='ENCLOSING_LOW_EDGE' and not x.trade_eligible
def test_039_enclosing_high_edge_mirror():
    h=hierarchy('NEAR_ENCLOSING_HIGH','NEAR_ENCLOSING_HIGH','110','125')
    x=classify_range_hl_location(h,current_price=D('124'),edge_zone_fraction=D('0.25'))
    assert x.semantic=='ENCLOSING_HIGH_EDGE'
def test_039_local_edge_inside_enclosing_middle_is_not_enclosing_edge():
    h=hierarchy('ENCLOSING_MIDDLE','ENCLOSING_MIDDLE','100','120')
    x=classify_range_hl_location(h,current_price=D('101'),edge_zone_fraction=D('0.25'))
    assert x.semantic=='LOCAL_EDGE_ENCLOSING_MIDDLE' and not x.trade_eligible
def test_039_departure_overrides_prior_edge_location():
    h=hierarchy('NEAR_ENCLOSING_LOW','DEPARTING_BELOW_ENCLOSING_RANGE')
    assert classify_range_hl_location(h,current_price=D('96'),edge_zone_fraction=D('0.25')).semantic=='DEPARTING_BELOW_ENCLOSING_RANGE'
def test_039_range_h2_edge_is_observation_not_candidate():
    fake=SimpleNamespace(swings=(fake_swing('HIGH',0),))
    mc=SimpleNamespace(range_hierarchy=hierarchy())
    with patch('app.modules.brooks_core.pattern_expansion.confirm_swings_causally',return_value=fake):
        obs=scan_range_hl_context_observations(snap(bull_h2()),range_ctx(),BrooksFullCorePolicy(),mc)
    assert any(x.pattern_id=='RANGE_H2_LONG_CONTEXT' and dict(x.metadata)['trade_eligible']=='false' for x in obs)
def test_039_middle_range_h2_remains_noneligible_context():
    fake=SimpleNamespace(swings=(fake_swing('HIGH',0),))
    mc=SimpleNamespace(range_hierarchy=hierarchy('ENCLOSING_MIDDLE','ENCLOSING_MIDDLE','95','110'))
    with patch('app.modules.brooks_core.pattern_expansion.confirm_swings_causally',return_value=fake):
        obs=scan_range_hl_context_observations(snap(bull_h2()),range_ctx(),BrooksFullCorePolicy(),mc)
    assert obs and all(dict(x.metadata)['trade_eligible']=='false' for x in obs)

# BROOKS-GAP-040
def test_040_final_h4_is_context_observation_not_generic_continuation_candidate():
    fake=SimpleNamespace(swings=(fake_swing('HIGH',0),))
    with patch('app.modules.brooks_core.pattern_expansion.confirm_swings_causally',return_value=fake):
        obs=scan_extended_hl_recurrence_observations(snap(extended_h4()),trend_ctx(),BrooksFullCorePolicy())
    assert len(obs)==1 and obs[0].pattern_id=='H4_RECURRENCE_CONTEXT' and dict(obs[0].metadata)['trade_eligible']=='false'
def test_040_future_h4_does_not_relabel_h3_prefix():
    assert classify_hl_recurrence(extended_h4()[:7],trend_direction='BULL_TREND',start_index=0).state=='H3_CONFIRMED'
    assert classify_hl_recurrence(extended_h4(),trend_direction='BULL_TREND',start_index=0).state=='H4_CONFIRMED'
def test_040_reset_prevents_stale_h4_in_new_episode():
    cs=extended_h4()[:5]+(bar(5,105,111,104,110),bar(6,109,110,102,103),bar(7,103,110.5,103,108))
    r=classify_hl_recurrence(cs,trend_direction='BULL_TREND',start_index=0)
    assert r.reset_index==5 and r.highest_entry_number==1 and r.events[-1].label=='H1'
def test_040_second_reversal_identity_remains_distinct_from_h4_recurrence():
    seq=(bar(0,100,104,99,103),bar(1,103,104,98,99),bar(2,99,105,99,104),bar(3,104,105,98,99))
    x=classify_generic_reversal_attempts(seq,trend_direction='BULL_TREND')
    assert x.state=='SECOND_REVERSAL_ATTEMPT' and 'H4' not in x.state
