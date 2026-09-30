from __future__ import annotations
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest
from app.modules.brooks_core.structure_entities import ConfirmedSwing,SwingScanResult
from app.modules.brooks_core.structural_geometry import *
from app.modules.market_data.entities import Candle
BASE=datetime(2026,2,1,tzinfo=UTC)
def b(i,c='100',h='120',l='80'):
 t=BASE+timedelta(minutes=15*i); return Candle(t,t+timedelta(minutes=15),Decimal(c),Decimal(h),Decimal(l),Decimal(c),Decimal('1'))
def cs(n=14): return [b(i) for i in range(n)]
def s(k,i,p): return ConfirmedSwing(k,i,i+1,Decimal(str(p)))
def sc(*x): return SwingScanResult(tuple(x),(),1,1)
def channel(items):
 a1=LineAnchor('LOW',1,2,Decimal('90'),items[1].close_time,items[2].close_time); a2=LineAnchor('LOW',3,4,Decimal('92'),items[3].close_time,items[4].close_time); up=LineAnchor('HIGH',2,3,Decimal('100'),items[2].close_time,items[3].close_time); i=len(items)-1
 tl=ProjectedLineGeometry('BULL_TREND_LINE','BULL_TREND',(a1,a2),Decimal('1'),Decimal('92')+Decimal(i-3),i,'ABOVE_LINE',False,False); ul=ProjectedLineGeometry('BULL_TREND_CHANNEL_LINE','BULL_TREND',(up,),Decimal('1'),Decimal('100')+Decimal(i-2),i,'BELOW_LINE',False,False)
 return TrendChannelGeometry('BULL_TREND',tl,ul,tl.projected_value,ul.projected_value,ul.projected_value-tl.projected_value,5,7,Decimal('.7'))

def run(name):
 items=cs()
 if name=='channel_intact':
  items[-2]=b(12,c='109',h='110',l='103'); items[-1]=b(13,c='109',h='110',l='103'); return classify_channel_boundary_event(tuple(items),channel(tuple(items))).state=='INSIDE_CHANNEL'
 if name in {'channel_test','channel_overshoot','channel_break'}:
  items[-2]=b(12,c='109',h='110',l='103'); ch=channel(tuple(items)); v=ch.opposite_channel_line.projected_value
  if name=='channel_test': items[-1]=b(13,c=str(v-1),h=str(v))
  elif name=='channel_overshoot': items[-1]=b(13,c=str(v-1),h=str(v+1))
  else: items[-1]=b(13,c=str(v+1),h=str(v+2))
  want={'channel_test':'CHANNEL_LINE_TEST','channel_overshoot':'CHANNEL_LINE_OVERSHOOT','channel_break':'CHANNEL_LINE_BREAK'}[name]
  return classify_channel_boundary_event(tuple(items),channel(tuple(items))).state==want
 if name=='trendline_not_channel_break':
  items[-2]=b(12,c='109',h='110',l='103'); items[-1]=b(13,c='103',h='110',l='101'); e=classify_channel_boundary_event(tuple(items),channel(tuple(items))); return e.state=='INSIDE_CHANNEL'
 if name in {'expanding','parallel_control'}:
  swings=sc(s('LOW',1,95),s('HIGH',3,105),s('LOW',5,93 if name=='expanding' else 96),s('HIGH',7,108 if name=='expanding' else 104))
  g=build_expanding_triangle_geometry(tuple(items),swings.swings,evaluated_index=12); return (g is not None)==(name=='expanding')
 if name=='dueling_confluence':
  q=sc(s('LOW',2,95),s('HIGH',4,110),s('LOW',6,97),s('HIGH',8,108)); d=build_dueling_lines_confluence(tuple(items),q,direction='BULL_TREND',evaluated_index=10,ema_value=Decimal('106'),tolerance=Decimal('1')); return bool(d and d.confluent)
 if name=='dueling_false':
  q=sc(s('LOW',2,95),s('HIGH',4,110),s('LOW',6,97),s('HIGH',8,108)); d=build_dueling_lines_confluence(tuple(items),q,direction='BULL_TREND',evaluated_index=10,ema_value=Decimal('102'),tolerance=Decimal('1')); return bool(d and not d.confluent)
 if name in {'parabolic','parabolic_false'}:
  third=110 if name=='parabolic' else 106; q=sc(s('LOW',1,90),s('HIGH',2,100),s('LOW',5,92),s('HIGH',6,104),s('HIGH',8,third)); p=build_parabolic_wedge_geometry(tuple(items),q,side='TOP',evaluated_index=10); return (p is not None)==(name=='parabolic')
 if name in {'hs_break','hs_invalid'}:
  head=110 if name=='hs_break' else 104; q=sc(s('HIGH',2,105),s('LOW',4,95),s('HIGH',6,head),s('LOW',8,96),s('HIGH',10,106)); items[12]=b(12,c='96'); h=build_head_shoulders_lifecycle(tuple(items),q,side='TOP',evaluated_index=12); return (h is not None)==(name=='hs_break')
 if name=='future_prefix':
  q=sc(s('LOW',1,95),s('HIGH',3,105),s('LOW',5,93),ConfirmedSwing('HIGH',7,13,Decimal('108'))); return build_expanding_triangle_geometry(tuple(items),q.swings,evaluated_index=12) is None
 raise AssertionError(name)

@pytest.mark.parametrize('name',['channel_intact','channel_test','channel_overshoot','channel_break','trendline_not_channel_break','expanding','parallel_control','dueling_confluence','dueling_false','parabolic','parabolic_false','hs_break','hs_invalid','future_prefix'])
def test_wave04_scenario(name): assert run(name)
