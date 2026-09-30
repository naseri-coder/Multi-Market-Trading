from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import classify_strong_trend_evidence
from app.modules.brooks_core.advanced_context import (
    classify_micro_channel_identity,
    classify_spike_channel_lifecycle,
    classify_trend_range_evolution,
    classify_small_pullback_trend,
)
from app.modules.brooks_core.pattern_expansion import (
    classify_countertrend_opportunity,
    classify_minor_reversal_identity,
)
from app.modules.brooks_core.books_full_patterns import detect_direct_trend_participation
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,9,1,tzinfo=UTC)
P=BrooksFullCorePolicy()

def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))

def snap(cs):
    return MarketSnapshot(exchange='binance',market_type='futures',symbol='BTCUSDT',timeframe='15m',candles=tuple(cs),captured_at=cs[-1].close_time,source='W12_TEST')

def bull_context(**kw):
    d=dict(regime='BULL_TREND',structure_direction='BULL_TREND',always_in='LONG',breakout_direction='LONG')
    d.update(kw); return SimpleNamespace(**d)

def bear_context(**kw):
    d=dict(regime='BEAR_TREND',structure_direction='BEAR_TREND',always_in='SHORT',breakout_direction='SHORT')
    d.update(kw); return SimpleNamespace(**d)

def bull_strong(n=8):
    out=[]
    for i in range(n):
        o=100+i*3; out.append(bar(i,o,o+4,o-1,o+3.4))
    return out

def bear_strong(n=8):
    out=[]
    for i in range(n):
        o=130-i*3; out.append(bar(i,o,o+1,o-4,o-3.4))
    return out

def bull_micro_with_one_pullback():
    return [
        bar(0,100,102,99.0,101.2),
        bar(1,101.2,103,99.3,102.0),
        bar(2,102.0,103,99.6,101.8),
        bar(3,101.8,104,99.9,103.0),
        bar(4,103.0,105,100.2,104.0),
        bar(5,104.0,106,100.5,105.0),
    ]

def spike_channel():
    return [
        bar(0,100,106,99,105),
        bar(1,105,111,104,110),
        bar(2,110,111,106,107),
        bar(3,107,112,106,111),
        bar(4,111,113,108,112),
    ]

def small_pullback(active=True):
    out=[]
    for i in range(10):
        if i in ({4} if active else {4}):
            if active:
                out.append(bar(i,112,113,110.8,111.4))
            else:
                out.append(bar(i,112,114,103,104))
        else:
            o=100+i*2
            out.append(bar(i,o,o+2,o-.5,o+1.5))
    return out

def bull_minor_fixture():
    return [
        bar(0,100,102,99,101),bar(1,101,104,100,103),bar(2,103,106,102,105),
        bar(3,105,110,104,109),bar(4,109,109.5,105,106),bar(5,106,107,102,103),
    ]

def bear_minor_fixture():
    return [
        bar(0,110,111,108,109),bar(1,109,110,106,107),bar(2,107,108,104,105),
        bar(3,105,106,100,101),bar(4,101,105,100.5,104),bar(5,104,108,103,107),
    ]

# BROOKS-GAP-002
def test_002_strong_trend_bar_direct_candidate():
    cs=bull_strong(); x=detect_direct_trend_participation(snap(cs),bull_context(),P)
    assert any(c.setup_type=='STRONG_TREND_BAR_DIRECT_ENTRY_LONG' for c in x)
def test_002_bear_mirror():
    cs=bear_strong(); x=detect_direct_trend_participation(snap(cs),bear_context(),P)
    assert any(c.setup_type=='STRONG_TREND_BAR_DIRECT_ENTRY_SHORT' for c in x)
def test_002_not_without_established_always_in():
    cs=bull_strong(); assert detect_direct_trend_participation(snap(cs),bull_context(always_in='UNRESOLVED'),P)==()
def test_002_not_on_weak_final_bar():
    cs=bull_strong(); cs[-1]=bar(7,121,122,120,121.2)
    x=detect_direct_trend_participation(snap(cs),bull_context(),P)
    assert not any(c.setup_type.startswith('STRONG_TREND_BAR_DIRECT_ENTRY') for c in x)
def test_002_candidate_owns_trade_eligibility():
    c=[c for c in detect_direct_trend_participation(snap(bull_strong()),bull_context(),P) if c.setup_type.startswith('STRONG_TREND_BAR')][0]
    assert dict(c.metadata)['trade_eligibility_owner']=='BROOKS-GAP-002'
def test_002_prefix_future_bar_not_used():
    cs=bull_strong(); pre=detect_direct_trend_participation(snap(cs[:-1]),bull_context(),P); full=detect_direct_trend_participation(snap(cs),bull_context(),P)
    assert all(c.signal_index==len(cs)-2 for c in pre) and all(c.signal_index==len(cs)-1 for c in full)

# BROOKS-GAP-003
def test_003_always_in_participation_without_fresh_pattern():
    cs=bull_strong(); cs[-1]=bar(7,121,123,120,122)
    x=detect_direct_trend_participation(snap(cs),bull_context(),P)
    assert any(c.setup_type=='ALWAYS_IN_TREND_PARTICIPATION_LONG' for c in x)
def test_003_bear_mirror():
    x=detect_direct_trend_participation(snap(bear_strong()),bear_context(),P)
    assert any(c.setup_type=='ALWAYS_IN_TREND_PARTICIPATION_SHORT' for c in x)
def test_003_opposite_current_bar_fails_closed():
    cs=bull_strong(); cs[-1]=bar(7,122,123,118,119)
    x=detect_direct_trend_participation(snap(cs),bull_context(),P)
    assert not any(c.setup_type.startswith('ALWAYS_IN_TREND_PARTICIPATION') for c in x)
def test_003_requires_strong_trend_composite():
    cs=[bar(i,100,102,98,100.2 if i%2==0 else 99.8) for i in range(8)]
    assert detect_direct_trend_participation(snap(cs),bull_context(),P)==()
def test_003_trade_owner_is_explicit():
    c=[c for c in detect_direct_trend_participation(snap(bull_strong()),bull_context(),P) if c.setup_type.startswith('ALWAYS_IN')][0]
    assert dict(c.metadata)['trade_eligibility_owner']=='BROOKS-GAP-003'
def test_003_context_direction_mismatch_rejected():
    assert detect_direct_trend_participation(snap(bull_strong()),bull_context(always_in='SHORT'),P)==()

# BROOKS-GAP-007
def test_007_micro_channel_allows_one_small_pullback():
    x=classify_micro_channel_identity(tuple(bull_micro_with_one_pullback()),P)
    assert x and x.direction=='LONG' and x.countertrend_bar_count<=1
def test_007_line_proximity_is_explicit():
    x=classify_micro_channel_identity(tuple(bull_micro_with_one_pullback()),P); assert x.line_proximity_count>=x.bar_count-1
def test_007_two_countertrend_bars_near_miss():
    cs=bull_micro_with_one_pullback(); cs[4]=bar(4,104,105,100.2,103)
    x=classify_micro_channel_identity(tuple(cs),P); assert x is None or x.countertrend_bar_count<=1
def test_007_source_guide_bounds_identity_segment():
    x=classify_micro_channel_identity(tuple(bull_micro_with_one_pullback()*2),P); assert x is None or 2<=x.bar_count<=10
def test_007_prefix_is_causal():
    cs=bull_micro_with_one_pullback(); a=classify_micro_channel_identity(tuple(cs),P,evaluated_index=3); b=classify_micro_channel_identity(tuple(cs),P,evaluated_index=5); assert a is None or a.end_index==3; assert b is None or b.end_index==5
def test_007_not_trade_eligible():
    x=classify_micro_channel_identity(tuple(bull_micro_with_one_pullback()),P); assert x and not x.trade_eligible

# BROOKS-GAP-008
def test_008_strong_trend_composite_positive():
    x=classify_strong_trend_evidence(tuple(bull_strong()),bull_context(),P.context); assert x.is_strong
def test_008_bear_mirror():
    x=classify_strong_trend_evidence(tuple(bear_strong()),bear_context(),P.context); assert x.is_strong and x.direction=='SHORT'
def test_008_directional_bars_without_always_in_not_strong():
    x=classify_strong_trend_evidence(tuple(bull_strong()),bull_context(always_in='UNRESOLVED'),P.context); assert not x.is_strong
def test_008_components_are_inspectable_not_score():
    x=classify_strong_trend_evidence(tuple(bull_strong()),bull_context(),P.context); assert x.directional_bars and x.urgency and x.classification_policy.startswith('ENGINEERING_CLASSIFICATION_POLICY')
def test_008_sideways_overlap_negative():
    cs=tuple(bar(i,100,102,98,100.2 if i%2==0 else 99.8) for i in range(8)); x=classify_strong_trend_evidence(cs,bull_context(breakout_direction='UNRESOLVED'),P.context); assert not x.is_strong
def test_008_prefix_no_future_components():
    cs=tuple(bull_strong()); x=classify_strong_trend_evidence(cs,bull_context(),P.context,evaluated_index=4); assert x.evaluated_index==4

# BROOKS-GAP-009
def test_009_spike_to_channel_progression():
    x=classify_spike_channel_lifecycle(snap(spike_channel()),P); assert x and x.state in {'SPIKE_TO_CHANNEL_CONFIRMED','CHANNEL_OVERLAP_EXPANDING'}
def test_009_t1_spike_precedes_channel_state():
    cs=spike_channel(); a=classify_spike_channel_lifecycle(snap(cs),P,evaluated_index=1); b=classify_spike_channel_lifecycle(snap(cs),P,evaluated_index=4); assert a.state=='SPIKE_ACTIVE' and b.episode_id==a.episode_id and b.state!=a.state
def test_009_no_spike_no_lifecycle():
    cs=[bar(i,100,102,98,100.2 if i%2==0 else 99.8) for i in range(5)]; assert classify_spike_channel_lifecycle(snap(cs),P) is None
def test_009_bear_spike_identity():
    cs=[bar(0,110,111,104,105),bar(1,105,106,99,100),bar(2,100,104,99,103),bar(3,103,104,98,99)]
    x=classify_spike_channel_lifecycle(snap(cs),P); assert x and x.direction=='SHORT'
def test_009_channel_state_context_only():
    x=classify_spike_channel_lifecycle(snap(spike_channel()),P); assert x and not x.trade_eligible
def test_009_future_channel_not_backdated():
    cs=spike_channel(); assert classify_spike_channel_lifecycle(snap(cs),P,evaluated_index=1).channel_start_index is None

# BROOKS-GAP-010
def test_010_directional_spike_state():
    cs=tuple(bull_strong(2)); x=classify_trend_range_evolution(cs,direction='LONG',origin_index=0); assert x.state=='DIRECTIONAL_SPIKE'
def test_010_channel_overlap_state():
    cs=tuple(spike_channel()); x=classify_trend_range_evolution(cs,direction='LONG',origin_index=0); assert x.state in {'CHANNEL_WITH_GROWING_OVERLAP','TWO_SIDED_RANGE_PRESSURE','TRANSITIONAL_TREND'}
def test_010_state_is_context_only():
    x=classify_trend_range_evolution(tuple(spike_channel()),direction='LONG',origin_index=0); assert not x.trade_eligible
def test_010_invalid_origin_rejected():
    assert classify_trend_range_evolution(tuple(spike_channel()),direction='LONG',origin_index=99) is None
def test_010_bear_symmetry():
    x=classify_trend_range_evolution(tuple(bear_strong(5)),direction='SHORT',origin_index=0); assert x and x.direction=='SHORT'
def test_010_prefix_state_uses_only_prefix():
    cs=tuple(spike_channel()); x=classify_trend_range_evolution(cs,direction='LONG',origin_index=0,evaluated_index=2); assert x.evaluated_index==2

# BROOKS-GAP-025
def test_025_small_pullback_active_positive():
    x=classify_small_pullback_trend(tuple(small_pullback(True)),direction='LONG'); assert x and x.state.startswith('ACTIVE_SMALL_PULLBACK') or x.state=='SMALL_PULLBACK_TREND_WITH_LATER_EXPANSION'
def test_025_substantial_single_countertrend_bar_not_small_pullback_trend():
    x=classify_small_pullback_trend(tuple(small_pullback(False)),direction='LONG'); assert x and x.state=='NOT_SMALL_PULLBACK_TREND'
def test_025_depth_duration_spacing_visible():
    x=classify_small_pullback_trend(tuple(small_pullback(True)),direction='LONG'); assert x.max_pullback_run>=0 and x.max_pullback_depth>=0 and x.pullback_episode_count>=0
def test_025_bear_mirror():
    cs=[bar(i,130-i*2,131-i*2,128-i*2,128.5-i*2) for i in range(10)]; x=classify_small_pullback_trend(tuple(cs),direction='SHORT'); assert x and x.direction=='SHORT'
def test_025_prefix_causal():
    cs=tuple(small_pullback(True)); x=classify_small_pullback_trend(cs,direction='LONG',evaluated_index=7); assert x and x.evaluated_index==7
def test_025_context_not_entry():
    x=classify_small_pullback_trend(tuple(small_pullback(True)),direction='LONG'); assert x and not x.trade_eligible

# BROOKS-GAP-061
def test_061_old_trend_intact_is_countertrend_scalp():
    x=classify_countertrend_opportunity(direction='SHORT',prior_always_in='LONG',current_always_in='LONG',signal_index=5); assert x.state=='COUNTERTREND_SCALP_OLD_TREND_INTACT'
def test_061_always_in_flip_is_reversal_trade():
    x=classify_countertrend_opportunity(direction='SHORT',prior_always_in='LONG',current_always_in='SHORT',signal_index=5); assert x.state=='REVERSAL_TRADE_ALWAYS_IN_FLIPPED'
def test_061_same_direction_not_countertrend():
    assert classify_countertrend_opportunity(direction='LONG',prior_always_in='LONG',current_always_in='LONG',signal_index=5) is None
def test_061_unresolved_flip_is_not_promoted():
    x=classify_countertrend_opportunity(direction='SHORT',prior_always_in='LONG',current_always_in='UNRESOLVED',signal_index=5); assert x.state=='OPPOSITE_OPPORTUNITY_FLIP_UNRESOLVED' and not x.trade_eligible
def test_061_bear_mirror_scalp():
    x=classify_countertrend_opportunity(direction='LONG',prior_always_in='SHORT',current_always_in='SHORT',signal_index=5); assert x.state=='COUNTERTREND_SCALP_OLD_TREND_INTACT'
def test_061_identity_stable_at_signal():
    x=classify_countertrend_opportunity(direction='SHORT',prior_always_in='LONG',current_always_in='LONG',signal_index=7); assert x.opportunity_id.endswith(':7')

# BROOKS-GAP-062
def test_062_bull_trend_minor_reversal_requires_developed_swing():
    x=classify_minor_reversal_identity(tuple(bull_minor_fixture()),bull_context(),P); assert x and x.direction=='SHORT'
def test_062_single_opposite_bar_not_full_identity():
    cs=bull_minor_fixture()[:5]; assert classify_minor_reversal_identity(tuple(cs),bull_context(),P) is None
def test_062_bear_mirror():
    x=classify_minor_reversal_identity(tuple(bear_minor_fixture()),bear_context(),P); assert x and x.direction=='LONG'
def test_062_requires_major_trend_intact():
    assert classify_minor_reversal_identity(tuple(bull_minor_fixture()),bull_context(always_in='SHORT'),P) is None
def test_062_prefix_confirmation_not_backdated():
    cs=tuple(bull_minor_fixture()); assert classify_minor_reversal_identity(cs,bull_context(),P,evaluated_index=4) is None; assert classify_minor_reversal_identity(cs,bull_context(),P,evaluated_index=5) is not None
def test_062_context_not_automatic_entry():
    x=classify_minor_reversal_identity(tuple(bull_minor_fixture()),bull_context(),P); assert x and not x.trade_eligible
