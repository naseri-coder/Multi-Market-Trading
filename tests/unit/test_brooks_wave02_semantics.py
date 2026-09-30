from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import (
    assess_range_hierarchy,
    assess_range_identity_evidence,
    body_overlap_rate,
    material_price_overlap_rate,
    positive_price_overlap_rate,
    price_overlap_fraction,
)
from app.modules.brooks_core.market_context import build_market_context
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)

def c(i, o, h, l, cl):
    return Candle(open_time=BASE+timedelta(minutes=15*i), close_time=BASE+timedelta(minutes=15*(i+1)), open=Decimal(str(o)), high=Decimal(str(h)), low=Decimal(str(l)), close=Decimal(str(cl)), volume=Decimal('1'))

def snap(cs):
    return MarketSnapshot(exchange='binance', market_type='futures', symbol='BTCUSDT', timeframe='15m', candles=tuple(cs), captured_at=cs[-1].close_time, source='W02_TEST')

def alternating(start, n, low, high, *, center=100):
    out=[]
    for j in range(n):
        o=Decimal(str(center-0.2 if j%2==0 else center+0.2)); cl=Decimal(str(center+0.2 if j%2==0 else center-0.2))
        out.append(c(start+j,o,Decimal(str(high)),Decimal(str(low)),cl))
    return out

def hierarchy_fixture(local_center=100, current_close=100, nested=True):
    parent=alternating(0,20,95,105,center=100)
    if nested:
        local=alternating(20,6,local_center-1.5,local_center+1.5,center=local_center)
    else:
        local=alternating(20,6,106,110,center=108)
    current=c(26,current_close,current_close+0.4,current_close-0.4,current_close)
    return parent+local+[current]

def test_wave02_overlap_vocabulary_is_explicit_and_distinct():
    a=c(0,0,10,0,2); b=c(1,8,18,7,9)
    assert price_overlap_fraction(a,b) == Decimal('0.3')
    assert price_overlap_fraction(a,b) == price_overlap_fraction(b,a)
    assert positive_price_overlap_rate((a,b)) == Decimal('1')
    assert material_price_overlap_rate((a,b)) == Decimal('0')

def test_wave02_body_overlap_is_not_full_price_overlap():
    a=c(0,1,10,0,2); b=c(1,8,9,1,7)
    assert positive_price_overlap_rate((a,b)) == Decimal('1')
    assert body_overlap_rate((a,b)) == Decimal('0')

def test_wave02_clear_two_sided_range_has_inspectable_composite_evidence():
    e=assess_range_identity_evidence(tuple(alternating(0,20,95,105)), BrooksBooksPolicy())
    assert e.composite_supported and e.two_sided and e.reversal_count >= 2
    assert e.material_price_overlap_rate > 0 and e.raw_price_overlap_rate > 0

def test_wave02_incidental_overlap_in_directional_trend_is_not_range():
    cs=[]
    for i in range(20):
        cs.append(c(i,100+i,102+i,99+i,101+i))
    e=assess_range_identity_evidence(tuple(cs), BrooksBooksPolicy())
    assert not e.composite_supported

def test_wave02_single_overlap_pair_is_not_enough():
    e=assess_range_identity_evidence((c(0,100,102,99,101),c(1,101,103,100,102)), BrooksBooksPolicy())
    assert not e.composite_supported

def test_wave02_failed_continuation_components_are_visible():
    cs=[c(0,100,101,99,100.5),c(1,100.5,102,100,100.8),c(2,100.8,101,98,100.2),c(3,100.2,102,99,100.4)]
    e=assess_range_identity_evidence(tuple(cs), BrooksBooksPolicy())
    assert e.failed_up_continuation_count >= 1
    assert e.failed_down_continuation_count >= 1

def test_wave02_nested_middle_and_market_context_propagation():
    cs=hierarchy_fixture(100,100)
    h=assess_range_hierarchy(tuple(cs), BrooksBooksPolicy(), edge_zone_fraction=Decimal('0.25'))
    assert h.nested and h.local_position == 'ENCLOSING_MIDDLE' and h.current_relation == 'ENCLOSING_MIDDLE'
    # build_market_context requires >=40 bars for broader context; hierarchy function itself is the canonical primitive.

def test_wave02_nested_low_and_high_locations():
    low=assess_range_hierarchy(tuple(hierarchy_fixture(97,97)), BrooksBooksPolicy(), edge_zone_fraction=Decimal('0.25'))
    high=assess_range_hierarchy(tuple(hierarchy_fixture(103,103)), BrooksBooksPolicy(), edge_zone_fraction=Decimal('0.25'))
    assert low.local_position == 'NEAR_ENCLOSING_LOW'
    assert high.local_position == 'NEAR_ENCLOSING_HIGH'

def test_wave02_departure_is_relative_to_established_parent_not_local():
    inside=assess_range_hierarchy(tuple(hierarchy_fixture(100,102)), BrooksBooksPolicy(), edge_zone_fraction=Decimal('0.25'))
    above=assess_range_hierarchy(tuple(hierarchy_fixture(100,106)), BrooksBooksPolicy(), edge_zone_fraction=Decimal('0.25'))
    below=assess_range_hierarchy(tuple(hierarchy_fixture(100,94)), BrooksBooksPolicy(), edge_zone_fraction=Decimal('0.25'))
    assert inside.current_relation == 'ENCLOSING_MIDDLE'
    assert above.current_relation == 'DEPARTING_ABOVE_ENCLOSING_RANGE'
    assert below.current_relation == 'DEPARTING_BELOW_ENCLOSING_RANGE'

def test_wave02_noncontained_structures_are_not_nested():
    h=assess_range_hierarchy(tuple(hierarchy_fixture(nested=False)), BrooksBooksPolicy(), edge_zone_fraction=Decimal('0.25'))
    assert not h.nested and h.local_position == 'NOT_NESTED'

def test_wave02_hierarchy_propagates_into_market_context():
    prefix = alternating(0, 20, 80, 120, center=100)
    parent = alternating(20, 20, 95, 105, center=100)
    local = alternating(40, 6, 98.5, 101.5, center=100)
    current = c(46, 100, 100.4, 99.6, 100)
    context = build_market_context(snap(prefix + parent + local + [current]), policy=BrooksFullCorePolicy())
    assert context.range_hierarchy is not None
    assert context.range_hierarchy.nested
    assert context.range_hierarchy.local_position == 'ENCLOSING_MIDDLE'
