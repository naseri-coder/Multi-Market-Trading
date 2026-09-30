from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import (
    TightTradingRangeIdentity, RangeIdentityEvidence,
    classify_tight_trading_range, classify_barbwire_identity,
    classify_broad_trading_range, classify_range_edge,
    classify_local_breakout_vs_enclosing, assess_range_hierarchy,
)
from app.modules.market_data.entities import Candle

BASE=datetime(2026,9,1,tzinfo=UTC)
P=BrooksBooksPolicy()
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))

def tight(n=6):
    return tuple(bar(i,99.9 if i%2==0 else 100.1,102,98,100.1 if i%2==0 else 99.9) for i in range(n))

def broad(n=19):
    centers=[96,99,102,99,96,99]
    out=[]
    for i in range(n):
        x=centers[i%len(centers)]; bull=i%2==0
        out.append(bar(i,x-0.5 if bull else x+0.5,x+2.5,x-2.5,x+0.5 if bull else x-0.5))
    return tuple(out)

def trending_overlap(n=6):
    return tuple(bar(i,100+i*.2,102+i*.2,99+i*.2,101+i*.2) for i in range(n))

def hierarchy_fixture(local_center=100,current_close=102,current_high=None,current_low=None):
    def alt(start,n,lo,hi,center):
        return [bar(start+j,center-.2 if j%2==0 else center+.2,hi,lo,center+.2 if j%2==0 else center-.2) for j in range(n)]
    cs=alt(0,20,95,105,100)+alt(20,6,local_center-1.5,local_center+1.5,local_center)
    h=current_high if current_high is not None else current_close+.4
    l=current_low if current_low is not None else current_close-.4
    cs.append(bar(26,current_close,h,l,current_close))
    return tuple(cs)

# 027
def test_027_source_components_identify_ttr():
    x=classify_tight_trading_range(tight(),P); assert x and x.is_tight and x.state=='TIGHT_TRADING_RANGE'
def test_027_broad_range_is_not_ttr():
    x=classify_tight_trading_range(broad(),P); assert x and not x.is_tight
def test_027_overlap_only_trend_not_specialized_range():
    x=classify_tight_trading_range(trending_overlap(),P); assert x and not x.is_tight
def test_027_prefix_future_two_sided_evidence_not_backdated():
    pre=tuple(bar(i,99.8,102,98,100.2) for i in range(3)); a=classify_tight_trading_range(pre,P); b=classify_tight_trading_range(tight(),P); assert not a.is_tight and b.is_tight
def test_027_reuses_wave02_range_evidence():
    x=classify_tight_trading_range(tight(),P); assert isinstance(x.evidence,RangeIdentityEvidence) and x.evidence.composite_supported
def test_027_ttr_is_context_not_entry():
    assert classify_tight_trading_range(tight(),P).trade_eligible is False

# 028
def test_028_canonical_barbwire_positive():
    x=classify_barbwire_identity(tight(),P); assert x and x.is_barbwire and x.doji_like_count>=1 and x.tail_dominant_count>=1
def test_028_ordinary_broad_range_not_barbwire():
    x=classify_barbwire_identity(broad(6),P); assert x and not x.is_barbwire
def test_028_high_overlap_alone_insufficient():
    x=classify_barbwire_identity(trending_overlap(),P); assert x and not x.is_barbwire
def test_028_small_bodies_alone_insufficient():
    cs=tuple(bar(i,100+i*5,101+i*5,99+i*5,100.1+i*5) for i in range(3)); x=classify_barbwire_identity(cs,P); assert x and not x.is_barbwire
def test_028_requires_three_bars_causally():
    assert classify_barbwire_identity(tight(2),P) is None and classify_barbwire_identity(tight(3),P).is_barbwire
def test_028_barbwire_not_trade_eligible():
    assert classify_barbwire_identity(tight(),P).trade_eligible is False

# 029
def test_029_lower_range_edge_uses_one_canonical_range_geometry():
    b=broad(); cur=bar(30,97,99,94,98.5); x=classify_range_edge(b,cur,P,direction='LONG',origin_index=0,evaluated_index=30); assert x and x.state=='AT_LOWER_RANGE_EDGE'
def test_029_upper_range_edge_mirror():
    b=broad(); cur=bar(30,102,105,100,101); x=classify_range_edge(b,cur,P,direction='SHORT',origin_index=0,evaluated_index=30); assert x and x.state=='AT_UPPER_RANGE_EDGE'
def test_029_middle_is_not_edge():
    b=broad(); cur=bar(30,99.5,101,99,100); x=classify_range_edge(b,cur,P,direction='LONG',origin_index=0,evaluated_index=30); assert x and x.state=='RANGE_MIDDLE'
def test_029_nonrange_has_no_edge_identity():
    assert classify_range_edge(trending_overlap(),bar(10,101,102,100,101.5),P,direction='LONG',origin_index=0,evaluated_index=10) is None
def test_029_old_universal_25_percent_not_identity():
    x=classify_range_edge(broad(),bar(30,97,99,94,98),P,direction='LONG',origin_index=0,evaluated_index=30); assert x and x.engineering_tolerance>0
def test_029_future_edge_does_not_relabel_middle_prefix():
    b=broad(); mid=classify_range_edge(b,bar(30,99.5,101,99,100),P,direction='LONG',origin_index=0,evaluated_index=30); edge=classify_range_edge(b,bar(31,97,99,94,98),P,direction='LONG',origin_index=0,evaluated_index=31); assert mid.state=='RANGE_MIDDLE' and edge.state=='AT_LOWER_RANGE_EDGE'

# 032
def test_032_broad_horizontal_range_has_room():
    x=classify_broad_trading_range(broad(),P); assert x and x.is_broad and x.room_present and x.room_multiple>D('2')
def test_032_tight_range_not_broad():
    x=classify_broad_trading_range(tight(),P); assert x and not x.is_broad
def test_032_room_components_are_inspectable_not_score():
    x=classify_broad_trading_range(broad(),P); assert x.width>0 and x.median_bar_range>0 and x.room_multiple==x.width/x.median_bar_range
def test_032_directional_overlap_not_broad_range():
    x=classify_broad_trading_range(trending_overlap(),P); assert x and not x.is_broad
def test_032_future_widening_not_used_in_prefix():
    pre=broad(3); a=classify_broad_trading_range(pre,P); full=broad(); b=classify_broad_trading_range(full,P); assert (not a.is_broad) or a.end_index==2; assert b.end_index==18
def test_032_broad_identity_not_trade_eligible():
    assert classify_broad_trading_range(broad(),P).trade_eligible is False

# 038
def test_038_local_breakout_inside_enclosing_range_is_context_not_new_trend():
    cs=hierarchy_fixture(); h=assess_range_hierarchy(cs,P,edge_zone_fraction=D('.25')); x=classify_local_breakout_vs_enclosing(cs[-1],h,evaluated_index=26); assert x and x.state=='LOCAL_BREAKOUT_INSIDE_ENCLOSING_RANGE'
def test_038_actual_enclosing_breakout_is_distinct():
    cs=hierarchy_fixture(current_close=106,current_high=107,current_low=104); h=assess_range_hierarchy(cs,P,edge_zone_fraction=D('.25')); x=classify_local_breakout_vs_enclosing(cs[-1],h,evaluated_index=26); assert x and x.state=='ENCLOSING_RANGE_BREAKOUT'
def test_038_without_nested_foundation_no_dependent_context():
    cs=hierarchy_fixture(local_center=108,current_close=109); h=assess_range_hierarchy(cs,P,edge_zone_fraction=D('.25')); assert not h.nested and classify_local_breakout_vs_enclosing(cs[-1],h,evaluated_index=26) is None
def test_038_bear_mirror_local_breakout():
    cs=hierarchy_fixture(current_close=98,current_high=98.4,current_low=97); h=assess_range_hierarchy(cs,P,edge_zone_fraction=D('.25')); x=classify_local_breakout_vs_enclosing(cs[-1],h,evaluated_index=26); assert x and x.direction=='SHORT' and x.state=='LOCAL_BREAKOUT_INSIDE_ENCLOSING_RANGE'
def test_038_future_departure_does_not_relabel_local_breakout_state():
    cs=hierarchy_fixture(); h=assess_range_hierarchy(cs,P,edge_zone_fraction=D('.25')); a=classify_local_breakout_vs_enclosing(cs[-1],h,evaluated_index=26); future=bar(27,106,107,104,106); b=classify_local_breakout_vs_enclosing(future,h,evaluated_index=27); assert a.state=='LOCAL_BREAKOUT_INSIDE_ENCLOSING_RANGE' and b.state=='ENCLOSING_RANGE_BREAKOUT'
def test_038_context_is_not_trade_eligibility():
    cs=hierarchy_fixture(); h=assess_range_hierarchy(cs,P,edge_zone_fraction=D('.25')); assert classify_local_breakout_vs_enclosing(cs[-1],h,evaluated_index=26).trade_eligible is False
