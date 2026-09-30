from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from app.modules.brooks_core.structural_geometry import build_structural_second_test, build_micro_double_structure
from app.modules.brooks_core.correction_lifecycle import classify_wedge_second_signal, build_wedge_attempt_origin, evaluate_wedge_attempt_lifecycle
from app.modules.brooks_core.structure_entities import ConfirmedSwing, SwingScanResult
from app.modules.market_data.entities import Candle
BASE=datetime(2026,7,2,tzinfo=UTC)
def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i); return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))
def sw(kind,i,price,confirmed=None): return ConfirmedSwing(kind,i,i if confirmed is None else confirmed,D(str(price)))
def scan(*xs): return SwingScanResult(tuple(xs),(),1,1)
def second_test_candles(): return [bar(0,100,104,96,101),bar(1,101,105,90,94),bar(2,94,110,93,108),bar(3,108,109,94,97),bar(4,97,106,95,104),bar(5,104,107,94,96)]
def top_wedge_sequence(): return [bar(0,100,102,99,101),bar(1,101,104,100,103),bar(2,103,104,100,102),bar(3,102,106,101,105),bar(4,105,106,102,104),bar(5,104,108,103,107),bar(6,107,108,101,102),bar(7,102,109,102,108),bar(8,108,109,100,101)]

def test_s01_structural_double_bottom(): assert build_structural_second_test(tuple(second_test_candles()),scan(sw('LOW',1,90),sw('HIGH',2,110),sw('LOW',3,94)),side='BOTTOM',evaluated_index=5)
def test_s02_structural_double_top():
    cs=(bar(0,100,101,95,97),bar(1,97,110,96,108),bar(2,108,109,90,92),bar(3,92,106,91,94)); assert build_structural_second_test(cs,scan(sw('HIGH',1,110),sw('LOW',2,90),sw('HIGH',3,106)),side='TOP',evaluated_index=3)
def test_s03_equality_only_false_double(): assert build_structural_second_test(tuple(second_test_candles()),scan(sw('LOW',1,90),sw('LOW',3,90)),side='BOTTOM',evaluated_index=5) is None
def test_s04_second_test_outside_old_fixed_band():
    g=build_structural_second_test(tuple(second_test_candles()),scan(sw('LOW',1,90),sw('HIGH',2,110),sw('LOW',3,94)),side='BOTTOM',evaluated_index=5); assert abs(g.second_level-g.first_level)==D('4')
def test_s05_consecutive_micro_double(): assert build_micro_double_structure((bar(0,100,105,99,104),bar(1,104,105.2,99,100)),side='TOP',max_bar_distance=3,engineering_tolerance=D('1')).bar_distance==1
def test_s06_nearly_consecutive_micro_double(): assert build_micro_double_structure((bar(0,100,104,95,97),bar(1,100,107,98,105),bar(2,105,106,95.2,104)),side='BOTTOM',max_bar_distance=3,engineering_tolerance=D('1')).bar_distance==2
def test_s07_distant_false_micro_double():
    cs=tuple([bar(0,100,105,99,104)]+[bar(i,100,101,95,100) for i in range(1,4)]+[bar(4,104,105.1,99,100)]); assert build_micro_double_structure(cs,side='TOP',max_bar_distance=3,engineering_tolerance=D('1')) is None
def test_s08_wedge_first_signal(): assert classify_wedge_second_signal(tuple(top_wedge_sequence()[:7]),push_indices=(1,3,5),side='TOP').first_attempt_index==6
def test_s09_failed_first_wedge_attempt(): assert classify_wedge_second_signal(tuple(top_wedge_sequence()[:8]),push_indices=(1,3,5),side='TOP').resumption_index==7
def test_s10_valid_second_wedge_signal(): assert classify_wedge_second_signal(tuple(top_wedge_sequence()),push_indices=(1,3,5),side='TOP').second_attempt_index==8
def test_s11_generic_second_reversal_without_wedge(): assert classify_wedge_second_signal(tuple(top_wedge_sequence()),push_indices=(5,3,1),side='TOP') is None
def _origin(cs,obj='90'):
    w=classify_wedge_second_signal(tuple(cs),push_indices=(1,3,5),side='TOP'); return build_wedge_attempt_origin(tuple(cs),w,signal_number=1,objective_level=D(obj) if obj else None)
def test_s12_triggered_wedge_lifecycle():
    cs=top_wedge_sequence()[:7]+[bar(7,102,104,97,99)]; assert evaluate_wedge_attempt_lifecycle(tuple(cs),_origin(cs)).state=='TRIGGERED_ACTIVE'
def test_s13_untriggered_wedge_invalidation():
    cs=top_wedge_sequence()[:7]+[bar(7,102,109,102,108)]; assert evaluate_wedge_attempt_lifecycle(tuple(cs),_origin(cs)).state=='SIGNAL_INVALIDATED_BEFORE_TRIGGER'
def test_s14_wedge_failure():
    cs=top_wedge_sequence()[:7]+[bar(7,102,104,97,99),bar(8,99,109,95,108)]; assert evaluate_wedge_attempt_lifecycle(tuple(cs),_origin(cs)).failure_confirmed
def test_s15_same_bar_ambiguous_wedge_outcome():
    cs=top_wedge_sequence()[:7]+[bar(7,102,109,97,103)]; assert evaluate_wedge_attempt_lifecycle(tuple(cs),_origin(cs)).state=='AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR'
def test_s16_future_prefix_causality():
    cs=top_wedge_sequence(); assert classify_wedge_second_signal(tuple(cs),push_indices=(1,3,5),side='TOP',evaluated_index=7).second_attempt_index is None
def test_s17_bull_bear_micro_mirror():
    top=build_micro_double_structure((bar(0,100,105,99,104),bar(1,104,105.2,99,100)),side='TOP',max_bar_distance=3,engineering_tolerance=D('1'))
    bottom=build_micro_double_structure((bar(0,100,101,95,96),bar(1,96,101,95.2,100)),side='BOTTOM',max_bar_distance=3,engineering_tolerance=D('1')); assert top and bottom
