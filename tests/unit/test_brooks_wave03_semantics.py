from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.modules.brooks_core.structural_geometry import (
    build_trend_line_geometry, build_trend_channel_geometry,
    build_triangle_geometry, project_line_value,
)
from app.modules.brooks_core.structure_entities import ConfirmedSwing, SwingScanResult
from app.modules.market_data.entities import Candle


def candles(n=16):
    t=datetime(2026,1,1,tzinfo=UTC); out=[]
    for i in range(n):
        lo=D('94'); hi=D('106'); op=D('100'); cl=D('100')
        out.append(Candle(t+timedelta(minutes=15*i),t+timedelta(minutes=15*(i+1)),op,hi,lo,cl,D('1')))
    return out

def with_bar(cs,i,lo,hi,op='100',cl='100'):
    c=cs[i]; cs[i]=Candle(c.open_time,c.close_time,D(op),D(hi),D(lo),D(cl),D('1')); return cs

def sw(kind,i,confirm,price): return ConfirmedSwing(kind,i,confirm,D(str(price)))
def scan(*items): return SwingScanResult(tuple(items),(),2,2)


def test_wave03_bull_trend_line_projection_and_anchor_identity():
    cs=candles(); g=build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('LOW',6,7,97)),direction='BULL_TREND',evaluated_index=10)
    assert g is not None and g.slope_per_bar==D('0.5') and g.projected_value==D('99')
    assert [a.candle_index for a in g.anchors]==[2,6] and [a.confirmed_at_index for a in g.anchors]==[3,7]

def test_wave03_bear_trend_line_mirror():
    cs=candles(); g=build_trend_line_geometry(tuple(cs),scan(sw('HIGH',2,3,105),sw('HIGH',6,7,103)),direction='BEAR_TREND',evaluated_index=10)
    assert g is not None and g.slope_per_bar==D('-0.5') and g.projected_value==D('101')

def test_wave03_one_anchor_or_unconfirmed_second_anchor_is_unavailable():
    cs=candles()
    assert build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95)),direction='BULL_TREND',evaluated_index=10) is None
    s=scan(sw('LOW',2,3,95),sw('LOW',6,12,97))
    assert build_trend_line_geometry(tuple(cs),s,direction='BULL_TREND',evaluated_index=10) is None
    assert build_trend_line_geometry(tuple(cs),s,direction='BULL_TREND',evaluated_index=12) is not None

def test_wave03_horizontal_support_is_not_projected_bull_trend_line():
    cs=candles(); assert build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('LOW',6,7,95)),direction='BULL_TREND',evaluated_index=10) is None

def test_wave03_trend_line_break_is_structural_evidence_not_candidate():
    cs=with_bar(candles(),9,'99','105','100','100'); cs=with_bar(cs,10,'98','102','100','100')
    g=build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('LOW',6,7,97)),direction='BULL_TREND',evaluated_index=10)
    assert g is not None and g.break_evidence and g.crossed_this_bar
    assert not hasattr(g,'setup_type')

def test_wave03_valid_bull_channel_has_parallel_opposite_boundary():
    cs=candles(); s=scan(sw('LOW',2,3,95),sw('HIGH',4,5,102),sw('LOW',6,7,97),sw('HIGH',8,9,104))
    g=build_trend_channel_geometry(tuple(cs),s,direction='BULL_TREND',evaluated_index=10)
    assert g is not None and g.trend_line.slope_per_bar==g.opposite_channel_line.slope_per_bar
    assert g.projected_lower < g.projected_upper and g.width>0

def test_wave03_valid_bear_channel_mirror():
    cs=candles(); s=scan(sw('HIGH',2,3,105),sw('LOW',4,5,98),sw('HIGH',6,7,103),sw('LOW',8,9,96))
    g=build_trend_channel_geometry(tuple(cs),s,direction='BEAR_TREND',evaluated_index=10)
    assert g is not None and g.trend_line.slope_per_bar==g.opposite_channel_line.slope_per_bar and g.projected_lower<g.projected_upper

def test_wave03_swing_count_without_valid_trend_line_cannot_make_channel():
    cs=candles(); s=scan(sw('LOW',2,3,97),sw('HIGH',4,5,102),sw('LOW',6,7,95),sw('HIGH',8,9,104))
    assert build_trend_channel_geometry(tuple(cs),s,direction='BULL_TREND',evaluated_index=10) is None

def test_wave03_minor_outlier_does_not_destroy_channel_identity():
    cs=with_bar(candles(),9,'96','107','100','100'); s=scan(sw('LOW',2,3,95),sw('HIGH',4,5,102),sw('LOW',6,7,97),sw('HIGH',8,9,104))
    g=build_trend_channel_geometry(tuple(cs),s,direction='BULL_TREND',evaluated_index=10)
    assert g is not None and g.containment_fraction < D('1')

def triangle_swings(high2='106',low2='92',confirm_last=11):
    return (sw('HIGH',2,3,110),sw('LOW',4,5,90),sw('HIGH',6,7,108),sw('LOW',8,9,low2),sw('HIGH',10,confirm_last,high2))

def test_wave03_converging_triangle_geometry():
    cs=candles(); g=build_triangle_geometry(tuple(cs),triangle_swings(),evaluated_index=12)
    assert g is not None and g.converging and g.upper_boundary.slope_per_bar < g.lower_boundary.slope_per_bar
    assert g.current_width < g.reference_width and g.current_width>0

def test_wave03_parallel_and_diverging_structures_are_not_triangle():
    cs=candles()
    parallel=(sw('HIGH',2,3,110),sw('LOW',4,5,90),sw('HIGH',6,7,110),sw('LOW',8,9,90),sw('HIGH',10,11,110))
    diverge=(sw('HIGH',2,3,110),sw('LOW',4,5,90),sw('HIGH',6,7,112),sw('LOW',8,9,88),sw('HIGH',10,11,114))
    assert build_triangle_geometry(tuple(cs),parallel,evaluated_index=12) is None
    assert build_triangle_geometry(tuple(cs),diverge,evaluated_index=12) is None

def test_wave03_directional_parallel_channel_is_not_triangle():
    cs=candles(); ss=(sw('HIGH',2,3,104),sw('LOW',4,5,94),sw('HIGH',6,7,106),sw('LOW',8,9,96),sw('HIGH',10,11,108))
    assert build_triangle_geometry(tuple(cs),ss,evaluated_index=12) is None

def test_wave03_insufficient_or_future_triangle_anchor_is_unavailable():
    cs=candles(); assert build_triangle_geometry(tuple(cs),triangle_swings()[:4],evaluated_index=12) is None
    assert build_triangle_geometry(tuple(cs),triangle_swings(confirm_last=14),evaluated_index=12) is None
    assert build_triangle_geometry(tuple(cs),triangle_swings(confirm_last=14),evaluated_index=14) is not None

def test_wave03_projected_boundaries_are_inspectable_not_trade_eligibility():
    cs=candles(); g=build_triangle_geometry(tuple(cs),triangle_swings(),evaluated_index=12)
    assert g is not None and project_line_value(g.upper_boundary,13) > project_line_value(g.lower_boundary,13)
    assert not hasattr(g,'direction') and not hasattr(g,'setup_type')

def test_wave03_triangle_breakout_uses_projected_boundary_not_raw_region_extreme():
    from unittest.mock import patch
    from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
    from app.modules.brooks_core.pattern_expansion import detect_triangle_breakout
    from app.modules.market_data.entities import MarketSnapshot
    cs=candles(15)
    # Strong final bull bar closes above the projected upper line (~104),
    # while remaining below the historical region high (110).
    cs=with_bar(cs,14,'101','106','102','105.5')
    ss=triangle_swings()
    snap=MarketSnapshot('binance','futures','BTCUSDT','15m',tuple(cs),cs[-1].close_time,'W03')
    with patch('app.modules.brooks_core.pattern_expansion._alternating_recent_swings', return_value=ss):
        found=detect_triangle_breakout(snap,None,BrooksFullCorePolicy())
    assert len(found)==1 and found[0].setup_type=='TRIANGLE_BREAKOUT_LONG'
    md=dict(found[0].metadata)
    assert md['boundary_semantic']=='PROJECTED_TRIANGLE_LINES'
    assert D(md['triangle_high']) < D('110')
