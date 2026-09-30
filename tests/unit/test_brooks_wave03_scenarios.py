import pytest
from decimal import Decimal as D
from datetime import UTC, datetime, timedelta
from app.modules.brooks_core.structure_entities import ConfirmedSwing, SwingScanResult
from app.modules.market_data.entities import Candle

def candles(n=16):
    t=datetime(2026,1,1,tzinfo=UTC); out=[]
    for i in range(n):
        out.append(Candle(t+timedelta(minutes=15*i),t+timedelta(minutes=15*(i+1)),D('100'),D('106'),D('94'),D('100'),D('1')))
    return out

def with_bar(cs,i,lo,hi,op='100',cl='100'):
    c=cs[i]; cs[i]=Candle(c.open_time,c.close_time,D(op),D(hi),D(lo),D(cl),D('1')); return cs

def sw(kind,i,confirm,price): return ConfirmedSwing(kind,i,confirm,D(str(price)))
def scan(*items): return SwingScanResult(tuple(items),(),2,2)
def triangle_swings(high2='106',low2='92',confirm_last=11):
    return (sw('HIGH',2,3,110),sw('LOW',4,5,90),sw('HIGH',6,7,108),sw('LOW',8,9,low2),sw('HIGH',10,confirm_last,high2))
from app.modules.brooks_core.structural_geometry import build_trend_line_geometry, build_trend_channel_geometry, build_triangle_geometry

@pytest.mark.parametrize('case,expected',[
 ('bull_line',True),('bear_line',True),('insufficient_line',False),('delayed_line',False),('line_break',True),
 ('bull_channel',True),('bear_channel',True),('pseudo_channel',False),('noisy_channel',True),
 ('triangle',True),('parallel_range',False),('expanding',False),('directional_channel',False),('insufficient_triangle',False),('future_pivot',False),
])
def test_wave03_deterministic_scenarios(case,expected):
    cs=candles()
    if case=='bull_line': result=build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('LOW',6,7,97)),direction='BULL_TREND',evaluated_index=10)
    elif case=='bear_line': result=build_trend_line_geometry(tuple(cs),scan(sw('HIGH',2,3,105),sw('HIGH',6,7,103)),direction='BEAR_TREND',evaluated_index=10)
    elif case=='insufficient_line': result=build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95)),direction='BULL_TREND',evaluated_index=10)
    elif case=='delayed_line': result=build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('LOW',6,12,97)),direction='BULL_TREND',evaluated_index=10)
    elif case=='line_break':
        cs=with_bar(cs,9,'99','105'); cs=with_bar(cs,10,'98','102'); result=build_trend_line_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('LOW',6,7,97)),direction='BULL_TREND',evaluated_index=10)
    elif case=='bull_channel': result=build_trend_channel_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('HIGH',4,5,102),sw('LOW',6,7,97),sw('HIGH',8,9,104)),direction='BULL_TREND',evaluated_index=10)
    elif case=='bear_channel': result=build_trend_channel_geometry(tuple(cs),scan(sw('HIGH',2,3,105),sw('LOW',4,5,98),sw('HIGH',6,7,103),sw('LOW',8,9,96)),direction='BEAR_TREND',evaluated_index=10)
    elif case=='pseudo_channel': result=build_trend_channel_geometry(tuple(cs),scan(sw('LOW',2,3,97),sw('HIGH',4,5,102),sw('LOW',6,7,95),sw('HIGH',8,9,104)),direction='BULL_TREND',evaluated_index=10)
    elif case=='noisy_channel':
        cs=with_bar(cs,9,'96','107'); result=build_trend_channel_geometry(tuple(cs),scan(sw('LOW',2,3,95),sw('HIGH',4,5,102),sw('LOW',6,7,97),sw('HIGH',8,9,104)),direction='BULL_TREND',evaluated_index=10)
    elif case=='triangle': result=build_triangle_geometry(tuple(cs),triangle_swings(),evaluated_index=12)
    elif case=='parallel_range': result=build_triangle_geometry(tuple(cs),(sw('HIGH',2,3,110),sw('LOW',4,5,90),sw('HIGH',6,7,110),sw('LOW',8,9,90),sw('HIGH',10,11,110)),evaluated_index=12)
    elif case=='expanding': result=build_triangle_geometry(tuple(cs),(sw('HIGH',2,3,110),sw('LOW',4,5,90),sw('HIGH',6,7,112),sw('LOW',8,9,88),sw('HIGH',10,11,114)),evaluated_index=12)
    elif case=='directional_channel': result=build_triangle_geometry(tuple(cs),(sw('HIGH',2,3,104),sw('LOW',4,5,94),sw('HIGH',6,7,106),sw('LOW',8,9,96),sw('HIGH',10,11,108)),evaluated_index=12)
    elif case=='insufficient_triangle': result=build_triangle_geometry(tuple(cs),triangle_swings()[:4],evaluated_index=12)
    else: result=build_triangle_geometry(tuple(cs),triangle_swings(confirm_last=14),evaluated_index=12)
    assert (result is not None) is expected
    if case=='line_break': assert result.break_evidence
