from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest
from app.modules.market_data.entities import Candle
BASE=datetime(2026,1,1,tzinfo=UTC)
def c(i,o,h,l,cl):
    return Candle(open_time=BASE+timedelta(minutes=15*i), close_time=BASE+timedelta(minutes=15*(i+1)), open=Decimal(str(o)), high=Decimal(str(h)), low=Decimal(str(l)), close=Decimal(str(cl)), volume=Decimal('1'))
def alternating(start,n,low,high,center=100):
    out=[]
    for j in range(n):
        o=Decimal(str(center-0.2 if j%2==0 else center+0.2)); cl=Decimal(str(center+0.2 if j%2==0 else center-0.2)); out.append(c(start+j,o,high,low,cl))
    return out
def hierarchy_fixture(local_center=100,current_close=100,nested=True):
    parent=alternating(0,20,95,105,100)
    local=alternating(20,6,local_center-1.5,local_center+1.5,local_center) if nested else alternating(20,6,106,110,108)
    return parent+local+[c(26,current_close,current_close+0.4,current_close-0.4,current_close)]
from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import assess_range_identity_evidence, assess_range_hierarchy, material_price_overlap_rate, positive_price_overlap_rate, body_overlap_rate

@pytest.mark.parametrize('case', range(15))
def test_wave02_deterministic_scenario_matrix(case):
    p=BrooksBooksPolicy()
    if case == 0: assert assess_range_identity_evidence(tuple(alternating(0,20,95,105)),p).composite_supported
    elif case == 1:
        cs=[c(i,100+i,102+i,99+i,101+i) for i in range(20)]; assert not assess_range_identity_evidence(tuple(cs),p).composite_supported
    elif case == 2:
        cs=[c(i,100+i*0.5,102+i*0.5,99+i*0.5,101+i*0.5) for i in range(20)]; assert not assess_range_identity_evidence(tuple(cs),p).composite_supported
    elif case == 3: assert assess_range_identity_evidence(tuple(alternating(0,20,95,105)),p).reversal_count >= 2
    elif case == 4:
        cs=[c(0,100,101,99,100.5),c(1,100.5,102,100,100.8),c(2,100.8,101,98,100.2),c(3,100.2,102,99,100.4)]; e=assess_range_identity_evidence(tuple(cs),p); assert e.failed_up_continuation_count and e.failed_down_continuation_count
    elif case == 5: assert assess_range_hierarchy(tuple(hierarchy_fixture(100,100)),p,edge_zone_fraction=Decimal('0.25')).local_position=='ENCLOSING_MIDDLE'
    elif case == 6: assert assess_range_hierarchy(tuple(hierarchy_fixture(97,97)),p,edge_zone_fraction=Decimal('0.25')).local_position=='NEAR_ENCLOSING_LOW'
    elif case == 7: assert assess_range_hierarchy(tuple(hierarchy_fixture(103,103)),p,edge_zone_fraction=Decimal('0.25')).local_position=='NEAR_ENCLOSING_HIGH'
    elif case == 8: assert not assess_range_hierarchy(tuple(hierarchy_fixture(100,102)),p,edge_zone_fraction=Decimal('0.25')).current_relation.startswith('DEPARTING')
    elif case == 9: assert assess_range_hierarchy(tuple(hierarchy_fixture(100,106)),p,edge_zone_fraction=Decimal('0.25')).current_relation=='DEPARTING_ABOVE_ENCLOSING_RANGE'
    elif case == 10: assert assess_range_hierarchy(tuple(hierarchy_fixture(100,94)),p,edge_zone_fraction=Decimal('0.25')).current_relation=='DEPARTING_BELOW_ENCLOSING_RANGE'
    elif case == 11: assert not assess_range_hierarchy(tuple(hierarchy_fixture(nested=False)),p,edge_zone_fraction=Decimal('0.25')).nested
    elif case == 12:
        a,b=c(0,0,10,0,2),c(1,8,18,7,9); assert positive_price_overlap_rate((a,b))==1 and material_price_overlap_rate((a,b))==0
    elif case == 13:
        a,b=c(0,0,10,0,4),c(1,3,12,2,5); assert material_price_overlap_rate((a,b))==1
    else:
        a,b=c(0,1,10,0,2),c(1,8,9,1,7); assert positive_price_overlap_rate((a,b))==1 and body_overlap_rate((a,b))==0
