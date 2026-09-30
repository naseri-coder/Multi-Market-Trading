from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import pytest

from app.modules.brooks_core.correction_lifecycle import (
    ReversalPatternOrigin, classify_generic_reversal_attempts,
    classify_structural_correction, evaluate_reversal_pattern_lifecycle,
)
from app.modules.brooks_core.pattern_expansion import _extended_entry_count
from app.modules.brooks_core.second_entry_v2 import detect_book_second_entry
from app.modules.market_data.entities import Candle

BASE=datetime(2026,4,1,tzinfo=UTC)
def b(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D('1'))

def run(name):
    if name=='013_reset':
        cs=(b(0,100,105,99,103),b(1,100,101,95,97),b(2,97,102,96,101),b(3,101,106,100,105),b(4,104,105,99,100),b(5,100,105.5,100,103))
        return _extended_entry_count(cs,direction='LONG',start=0)==(1,5)
    if name=='013_false_reset':
        cs=(b(0,100,105,99,103),b(1,103,103,95,97),b(2,97,104,96,101),b(3,101,104,99,103),b(4,103,103,97,98),b(5,98,104,98,103))
        return _extended_entry_count(cs,direction='LONG',start=0)==(2,5)
    if name=='013_bear':
        cs=(b(0,100,101,95,97),b(1,97,105,97,103),b(2,103,104,96,99),b(3,99,100,94,95),b(4,95,101,95,100),b(5,100,100,94.5,97))
        return _extended_entry_count(cs,direction='SHORT',start=0)==(1,5)
    if name in {'015_abc','015_near_miss','015_bear'}:
        if name=='015_abc': cs=(b(0,100,105,99,103),b(1,103,103,95,97),b(2,97,102,96,101),b(3,101,101.5,96.5,98)); td='BULL_TREND'; want=True
        elif name=='015_near_miss': cs=(b(0,100,105,99,103),b(1,103,103,97,99),b(2,99,100,96,98)); td='BULL_TREND'; want=False
        else: cs=(b(0,100,101,95,97),b(1,97,105,97,103),b(2,103,104,96,99),b(3,99,103.5,96.5,102)); td='BEAR_TREND'; want=True
        x=classify_structural_correction(cs,trend_direction=td,start_index=0)
        return bool(x and x.two_legged)==want
    if name=='015_h2':
        cs=(b(0,100,105,99,103),b(1,100,101,95,97),b(2,97,102,96,101),b(3,101,101.5,96.5,98),b(4,98,102,97,101))
        r=detect_book_second_entry(cs,trend_direction='BULL_TREND',start_index=0)
        return bool(r.setup and r.setup.setup_type=='H2_CONFIRMED')
    if name in {'016_second','016_first_only','016_bear'}:
        if name=='016_bear': cs=(b(0,100,101,96,97),b(1,97,103,96,102),b(2,102,102,95,96),b(3,96,103,95,102)); td='BEAR_TREND'; want='SECOND_REVERSAL_ATTEMPT'
        else:
            full=(b(0,100,104,99,103),b(1,103,104,98,99),b(2,99,105,99,104),b(3,104,105,98,99))
            cs=full if name=='016_second' else full[:2]; td='BULL_TREND'; want='SECOND_REVERSAL_ATTEMPT' if name=='016_second' else 'FIRST_REVERSAL_ATTEMPT'
        return classify_generic_reversal_attempts(cs,trend_direction=td).state==want
    origin=ReversalPatternOrigin('a1','REVERSAL_TEST','SHORT',1,D('95'),D('90'),D('105'))
    if name=='060_objective': cs=(b(0,100,103,97,101),b(1,101,105,95,99),b(2,99,104,94,96),b(3,96,100,89,91)); want='OBJECTIVE_REACHED'
    elif name=='060_failure': cs=(b(0,100,103,97,101),b(1,101,105,95,99),b(2,99,104,94,96),b(3,96,106,93,104)); want='FAILED_AFTER_TRIGGER_BEFORE_OBJECTIVE'
    elif name=='060_untriggered': cs=(b(0,100,103,97,101),b(1,101,105,95,99),b(2,99,106,96,104)); want='SIGNAL_INVALIDATED_BEFORE_TRIGGER'
    elif name=='060_ambiguous': cs=(b(0,100,103,97,101),b(1,101,105,95,99),b(2,99,106,94,100)); want='AMBIGUOUS_TRIGGER_AND_FAILURE_SAME_BAR'
    elif name=='060_prefix': cs=(b(0,100,103,97,101),b(1,101,105,95,99),b(2,99,104,94,96)); want='TRIGGERED_ACTIVE'
    else: raise AssertionError(name)
    return evaluate_reversal_pattern_lifecycle(cs,origin).state==want

CASES=['013_reset','013_false_reset','013_bear','015_abc','015_near_miss','015_bear','015_h2','016_second','016_first_only','016_bear','060_objective','060_failure','060_untriggered','060_ambiguous','060_prefix']
@pytest.mark.parametrize('name',CASES)
def test_wave05_deterministic_scenario(name): assert run(name)
