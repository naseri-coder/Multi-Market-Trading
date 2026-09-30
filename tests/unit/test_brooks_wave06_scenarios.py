from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import pytest
from app.modules.brooks_core.correction_lifecycle import classify_hl_recurrence, classify_range_hl_location
from app.modules.brooks_core.books_entities import RangeHierarchyContext
from app.modules.market_data.entities import Candle
BASE=datetime(2026,5,1,tzinfo=UTC)
def b(i,o,h,l,c):
 t=BASE+timedelta(minutes=15*i); return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def bull(): return (b(0,100,105,99,103),b(1,103,103,95,97),b(2,97,104,96,101),b(3,101,103,97,98),b(4,98,104,98,102))
def bear(): return (b(0,100,101,95,97),b(1,97,105,97,103),b(2,103,104,96,99),b(3,99,103,97,102),b(4,102,103,96,98))
def h4(): return (b(0,105,110,100,108),b(1,108,109,96,99),b(2,99,109.5,98,105),b(3,105,109,99,101),b(4,101,109.5,100,105),b(5,105,109,100,101),b(6,101,109.5,100,105),b(7,105,109,100,101),b(8,101,109.5,100,105))
@pytest.mark.parametrize('name,series,trend,expected',[('bull_h2',bull(),'BULL_TREND','H2'),('bear_l2',bear(),'BEAR_TREND','L2'),('bull_h1_prefix',bull()[:3],'BULL_TREND','H1'),('bear_l1_prefix',bear()[:3],'BEAR_TREND','L1'),('bull_h3',h4()[:7],'BULL_TREND','H3'),('bull_h4',h4(),'BULL_TREND','H4')])
def test_wave06_recurrence_scenarios(name,series,trend,expected):
 r=classify_hl_recurrence(series,trend_direction=trend,start_index=0); assert r and r.events[-1].label==expected
@pytest.mark.parametrize('current,position,relation,local_low,local_high,expected',[('96','NEAR_ENCLOSING_LOW','NEAR_ENCLOSING_LOW','95','110','ENCLOSING_LOW_EDGE'),('124','NEAR_ENCLOSING_HIGH','NEAR_ENCLOSING_HIGH','110','125','ENCLOSING_HIGH_EDGE'),('101','ENCLOSING_MIDDLE','ENCLOSING_MIDDLE','100','120','LOCAL_EDGE_ENCLOSING_MIDDLE'),('110','ENCLOSING_MIDDLE','ENCLOSING_MIDDLE','100','120','ENCLOSING_MIDDLE_OR_NONALIGNED_EDGE'),('96','NEAR_ENCLOSING_LOW','DEPARTING_BELOW_ENCLOSING_RANGE','95','110','DEPARTING_BELOW_ENCLOSING_RANGE')])
def test_wave06_range_location_scenarios(current,position,relation,local_low,local_high,expected):
 h=RangeHierarchyContext(True,D(local_low),D(local_high),D('90'),D('130'),position,relation,True,True,5,20)
 assert classify_range_hl_location(h,current_price=D(current),edge_zone_fraction=D('.25')).semantic==expected

def test_wave06_true_reset_new_episode_h1():
 cs=(b(0,100,105,99,103),b(1,100,101,95,97),b(2,97,102,96,101),b(3,101,106,100,105),b(4,104,105,99,100),b(5,100,105.5,100,103)); r=classify_hl_recurrence(cs,trend_direction='BULL_TREND',start_index=0); assert r.reset_index==3 and r.events[-1].label=='H1'
def test_wave06_false_reset_preserves_h2(): assert classify_hl_recurrence(bull(),trend_direction='BULL_TREND',start_index=0).reset_index is None
def test_wave06_no_second_entry_without_intervening_lower_high():
 cs=(b(0,100,105,99,103),b(1,103,103,95,97),b(2,97,104,96,101),b(3,101,104.5,97,102),b(4,102,105,98,104)); assert classify_hl_recurrence(cs,trend_direction='BULL_TREND',start_index=0).highest_entry_number==1
def test_wave06_h2_second_leg_needs_no_fresh_low(): assert bull()[3].low>bull()[1].low and classify_hl_recurrence(bull(),trend_direction='BULL_TREND',start_index=0).state=='H2_CONFIRMED'
def test_wave06_future_h4_prefix_is_only_h3(): assert classify_hl_recurrence(h4()[:7],trend_direction='BULL_TREND',start_index=0).state=='H3_CONFIRMED'
