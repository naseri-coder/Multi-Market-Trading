from __future__ import annotations
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.brooks_core.structure_entities import ConfirmedSwing, SwingScanResult
from app.modules.brooks_core.structural_geometry import (
    LineAnchor, ProjectedLineGeometry, TrendChannelGeometry,
    classify_channel_boundary_event, build_expanding_triangle_geometry,
    classify_expanding_triangle_lifecycle, build_dueling_lines_confluence,
    build_parabolic_wedge_geometry, build_head_shoulders_lifecycle,
)
from app.modules.market_data.entities import Candle

BASE=datetime(2026,1,1,tzinfo=UTC)

def bar(i,o='100',h='120',l='80',c='100'):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),Decimal(o),Decimal(h),Decimal(l),Decimal(c),Decimal('10'))

def candles(n=16): return [bar(i) for i in range(n)]
def sw(kind,i,confirmed,price): return ConfirmedSwing(kind,i,confirmed,Decimal(str(price)))
def scan(*items): return SwingScanResult(tuple(items),(),1,1)

def manual_bull_channel(cs, upper_anchor=2, slope='1'):
    a1=LineAnchor('LOW',1,2,Decimal('90'),cs[1].close_time,cs[2].close_time)
    a2=LineAnchor('LOW',3,4,Decimal('92'),cs[3].close_time,cs[4].close_time)
    up=LineAnchor('HIGH',upper_anchor,upper_anchor+1,Decimal('100'),cs[upper_anchor].close_time,cs[upper_anchor+1].close_time)
    idx=len(cs)-1; sp=Decimal(slope)
    tv=Decimal('92')+sp*Decimal(idx-3); uv=Decimal('100')+sp*Decimal(idx-upper_anchor)
    trend=ProjectedLineGeometry('BULL_TREND_LINE','BULL_TREND',(a1,a2),sp,tv,idx,'ABOVE_LINE',False,False)
    line=ProjectedLineGeometry('BULL_TREND_CHANNEL_LINE','BULL_TREND',(up,),sp,uv,idx,'BELOW_LINE',False,False)
    return TrendChannelGeometry('BULL_TREND',trend,line,tv,uv,uv-tv,5,7,Decimal('0.7'))

def test_006_channel_line_test_is_not_break():
    cs=candles(8); cs[-2]=bar(6,'103','104','100','103'); ch=manual_bull_channel(tuple(cs)); value=ch.opposite_channel_line.projected_value
    cs[-1]=bar(7,'104',str(value),'100','104')
    e=classify_channel_boundary_event(tuple(cs),ch)
    assert e.state=='CHANNEL_LINE_TEST' and not e.penetrated and not e.closed_beyond

def test_006_overshoot_is_not_close_break_or_reversal():
    cs=candles(8); cs[-2]=bar(6,'103','104','100','103'); ch=manual_bull_channel(tuple(cs)); value=ch.opposite_channel_line.projected_value
    cs[-1]=bar(7,'104',str(value+1),'100',str(value-1))
    e=classify_channel_boundary_event(tuple(cs),ch)
    assert e.state=='CHANNEL_LINE_OVERSHOOT' and e.penetrated and not e.closed_beyond and not e.reentered

def test_006_close_beyond_is_channel_line_break():
    cs=candles(8); ch=manual_bull_channel(tuple(cs)); value=ch.opposite_channel_line.projected_value
    cs[-1]=bar(7,'104',str(value+2),'100',str(value+1))
    assert classify_channel_boundary_event(tuple(cs),ch).state=='CHANNEL_LINE_BREAK'

def test_006_later_reentry_is_not_backdated_to_break_bar():
    cs=candles(9); ch8=manual_bull_channel(tuple(cs[:8])); v7=ch8.opposite_channel_line.projected_value
    cs[7]=bar(7,'104',str(v7+2),'100',str(v7+1))
    assert classify_channel_boundary_event(tuple(cs[:8]),ch8).state=='CHANNEL_LINE_BREAK'
    ch9=manual_bull_channel(tuple(cs)); v8=ch9.opposite_channel_line.projected_value
    cs[8]=bar(8,'104',str(v8),'100',str(v8-1))
    assert classify_channel_boundary_event(tuple(cs),ch9).state=='FAILED_BREAK_REENTRY'

def test_006_trend_channel_line_identity_is_preserved():
    cs=candles(8); e=classify_channel_boundary_event(tuple(cs),manual_bull_channel(tuple(cs)))
    assert e.boundary_role=='BULL_TREND_CHANNEL_LINE'

def expanding_scan():
    return scan(sw('LOW',1,2,95),sw('HIGH',3,4,105),sw('LOW',5,6,93),sw('HIGH',7,8,108))

def test_044_expanding_geometry_requires_divergence():
    cs=tuple(candles(12)); g=build_expanding_triangle_geometry(cs,expanding_scan().swings,evaluated_index=10)
    assert g is not None and g.diverging and g.current_width>g.reference_width
    flat=scan(sw('LOW',1,2,95),sw('HIGH',3,4,105),sw('LOW',5,6,96),sw('HIGH',7,8,104))
    assert build_expanding_triangle_geometry(cs,flat.swings,evaluated_index=10) is None

def test_044_break_then_reentry_becomes_known_later_only():
    cs=candles(12); g=build_expanding_triangle_geometry(tuple(cs),expanding_scan().swings,evaluated_index=11); assert g
    i=g.available_from_index; upper=lambda x: g.upper_boundary.anchors[-1].price+g.upper_boundary.slope_per_bar*Decimal(x-g.upper_boundary.anchors[-1].candle_index)
    cs[i]=bar(i,'100',str(upper(i)+2),'80',str(upper(i)+1))
    first=classify_expanding_triangle_lifecycle(tuple(cs[:i+1]),build_expanding_triangle_geometry(tuple(cs[:i+1]),expanding_scan().swings,evaluated_index=i),evaluated_index=i)
    assert first.state=='BREAKOUT_IN_PROGRESS'
    cs[i+1]=bar(i+1,'100','120','80','100')
    g2=build_expanding_triangle_geometry(tuple(cs),expanding_scan().swings,evaluated_index=i+1)
    later=classify_expanding_triangle_lifecycle(tuple(cs),g2,evaluated_index=i+1)
    assert later.state=='FAILED_BREAK_REENTRY' and later.reentry_index==i+1

def test_044_failed_break_can_later_reverse_through_other_side():
    cs=candles(13); g=build_expanding_triangle_geometry(tuple(cs),expanding_scan().swings,evaluated_index=12); assert g
    i=g.available_from_index
    uv=lambda x: g.upper_boundary.anchors[-1].price+g.upper_boundary.slope_per_bar*Decimal(x-g.upper_boundary.anchors[-1].candle_index)
    lv=lambda x: g.lower_boundary.anchors[-1].price+g.lower_boundary.slope_per_bar*Decimal(x-g.lower_boundary.anchors[-1].candle_index)
    cs[i]=bar(i,'100',str(uv(i)+2),'80',str(uv(i)+1)); cs[i+1]=bar(i+1,'100','120','80','100')
    cs[i+2]=bar(i+2,'100','120',str(lv(i+2)-2),str(lv(i+2)-1))
    life=classify_expanding_triangle_lifecycle(tuple(cs),build_expanding_triangle_geometry(tuple(cs),expanding_scan().swings,evaluated_index=i+2),evaluated_index=i+2)
    assert life.state=='FAILED_BREAK_REVERSED_THROUGH_OTHER_SIDE'

def dueling_scan():
    return scan(sw('LOW',2,3,95),sw('HIGH',4,5,110),sw('LOW',6,7,97),sw('HIGH',8,9,108))

def test_057_dueling_lines_requires_real_pullback_line_and_typed_reference():
    cs=tuple(candles(12)); d=build_dueling_lines_confluence(cs,dueling_scan(),direction='BULL_TREND',evaluated_index=10,ema_value=Decimal('106'),tolerance=Decimal('1'))
    assert d is not None and d.confluent and d.pullback_line.role=='BULL_PULLBACK_CHANNEL_LINE' and d.support_source=='EMA20'

def test_057_ema_nearness_without_line_confluence_is_insufficient():
    cs=tuple(candles(12)); d=build_dueling_lines_confluence(cs,dueling_scan(),direction='BULL_TREND',evaluated_index=10,ema_value=Decimal('102'),tolerance=Decimal('1'))
    assert d is not None and not d.confluent

def parabolic_scan(accel=True):
    third=110 if accel else 106
    return scan(sw('LOW',1,2,90),sw('HIGH',2,3,100),sw('LOW',5,6,92),sw('HIGH',6,7,104),sw('HIGH',8,9,third))

def test_065_parabolic_wedge_preserves_acceleration_and_prior_channel_context():
    p=build_parabolic_wedge_geometry(tuple(candles(12)),parabolic_scan(True),side='TOP',evaluated_index=10)
    assert p is not None and p.accelerating and p.second_slope>p.first_slope and p.channel is not None

def test_065_nonaccelerating_three_pushes_are_not_parabolic():
    assert build_parabolic_wedge_geometry(tuple(candles(12)),parabolic_scan(False),side='TOP',evaluated_index=10) is None

def hs_scan():
    return scan(sw('HIGH',2,3,105),sw('LOW',4,5,95),sw('HIGH',6,7,110),sw('LOW',8,9,96),sw('HIGH',10,11,106))

def test_067_head_shoulders_neckline_break_is_typed_not_trade():
    cs=candles(13); cs[11]=bar(11,'100','120','80','100'); cs[12]=bar(12,'100','120','80','96')
    hs=build_head_shoulders_lifecycle(tuple(cs),hs_scan(),side='TOP',evaluated_index=12)
    assert hs is not None and hs.state=='NECKLINE_BREAK' and hs.neckline_break and hs.right_shoulder_index==10

def test_067_neckline_failure_reentry_is_later_state():
    cs=candles(14); cs[12]=bar(12,'100','120','80','96'); cs[13]=bar(13,'100','120','80','100')
    hs=build_head_shoulders_lifecycle(tuple(cs),hs_scan(),side='TOP',evaluated_index=13)
    assert hs is not None and hs.state=='FAILED_NECKLINE_BREAK_REENTRY' and hs.neckline_reentry

def test_067_visual_three_swings_without_head_extreme_is_not_hs_lifecycle():
    bad=scan(sw('HIGH',2,3,105),sw('LOW',4,5,95),sw('HIGH',6,7,104),sw('LOW',8,9,96),sw('HIGH',10,11,106))
    assert build_head_shoulders_lifecycle(tuple(candles(13)),bad,side='TOP',evaluated_index=12) is None

def test_044_enlargement_requires_outer_structural_extension():
    q=scan(sw('LOW',1,2,95),sw('HIGH',3,4,105),sw('LOW',5,6,94),sw('HIGH',7,8,108),sw('LOW',9,10,92))
    g=build_expanding_triangle_geometry(tuple(candles(14)),q.swings,evaluated_index=12)
    assert g is not None and g.enlarged_structure


def test_057_measured_move_can_be_typed_support_reference():
    cs=tuple(candles(12))
    d=build_dueling_lines_confluence(
        cs,dueling_scan(),direction='BULL_TREND',evaluated_index=10,
        ema_value=Decimal('102'),measured_move_value=Decimal('106'),tolerance=Decimal('1')
    )
    assert d is not None and d.confluent and d.support_source=='MEASURED_MOVE'


def test_065_parabolic_third_push_can_overshoot_prior_canonical_channel():
    p=build_parabolic_wedge_geometry(tuple(candles(12)),parabolic_scan(True),side='TOP',evaluated_index=10)
    assert p is not None and p.channel is not None and p.channel_overshoot


def test_067_continuation_after_neckline_break_is_distinct_from_initial_break():
    cs=candles(14); cs[12]=bar(12,'100','120','80','96'); cs[13]=bar(13,'100','120','80','95')
    hs=build_head_shoulders_lifecycle(tuple(cs),hs_scan(),side='TOP',evaluated_index=13)
    assert hs is not None and hs.state=='CONTINUATION_BEYOND_NECKLINE' and hs.neckline_break and not hs.neckline_reentry
