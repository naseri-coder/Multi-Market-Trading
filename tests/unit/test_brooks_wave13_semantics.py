from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.pattern_expansion import (
    classify_ma_gap_episode,
    classify_ma_gap_count_context,
    classify_ma_gap_maturity_context,
    scan_ma_gap_observations,
    detect_moving_average_pullback_setups,
    _second_ma_gap_sequence,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,9,18,tzinfo=UTC)
P=BrooksFullCorePolicy()

def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D("1"))

def snap(cs):
    cs=tuple(cs)
    return MarketSnapshot(exchange="binance",market_type="futures",symbol="BTCUSDT",timeframe="15m",candles=cs,captured_at=cs[-1].close_time,source="W13_TEST")

def ctx(direction="LONG"):
    if direction=="LONG":
        return SimpleNamespace(regime="BULL_TREND",structure_direction="BULL_TREND",always_in="LONG",breakout_direction="LONG",breakout_streak=2,metrics=SimpleNamespace(bar_overlap_rate=D("0.1")))
    return SimpleNamespace(regime="BEAR_TREND",structure_direction="BEAR_TREND",always_in="SHORT",breakout_direction="SHORT",breakout_streak=2,metrics=SimpleNamespace(bar_overlap_rate=D("0.1")))

def strong(direction="LONG"):
    return SimpleNamespace(is_strong=True,direction=direction)

def weak(direction="LONG"):
    return SimpleNamespace(is_strong=False,direction=direction)

def rising_fixture(n=8, gap_indices=()):
    ema=tuple(D(100+i) for i in range(n))
    cs=[]
    for i,e in enumerate(ema):
        if i in gap_indices:
            cs.append(bar(i,e-3,e-1,e-4,e-2))  # bull reversal body, wholly below rising MA
        else:
            cs.append(bar(i,e+2,e+4,e+1,e+3))
    return cs,ema

def falling_fixture(n=8, gap_indices=()):
    ema=tuple(D(140-i) for i in range(n))
    cs=[]
    for i,e in enumerate(ema):
        if i in gap_indices:
            cs.append(bar(i,e+3,e+4,e+1,e+2))  # bear reversal body, wholly above falling MA
        else:
            cs.append(bar(i,e-2,e-1,e-4,e-3))
    return cs,ema

# BROOKS-GAP-018

def test_018_first_ma_gap_is_owned_by_active_episode():
    cs,ema=rising_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        ep=classify_ma_gap_episode(tuple(cs),ema,ctx(),P)
    assert ep and ep.active and ep.first_gap_index==7 and ep.direction=="LONG"
    assert ep.episode_id.startswith("MA_GAP_EPISODE:LONG:")

def test_018_rolling_memory_cannot_relabel_later_gap_first():
    cs,ema=rising_fixture(30,{3,29})
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        found=detect_moving_average_pullback_setups(snap(cs),ctx(),P)
    assert not any(x.setup_type=="FIRST_MA_GAP_BAR_LONG" for x in found)
    ep=classify_ma_gap_episode(tuple(cs),ema,ctx(),P)
    assert ep.first_gap_index==3

def test_018_new_ma_slope_cycle_gets_new_episode_identity():
    ema=tuple(map(D,["100","101","102","103","104","103","102","103","104","105"]))
    cs=[bar(i,e+2,e+4,e+1,e+3) for i,e in enumerate(ema)]
    cs[4]=bar(4,101,103,100,102)  # old gap relative to 104
    cs[9]=bar(9,102,104,101,103)  # first gap in new rising episode
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        ep=classify_ma_gap_episode(tuple(cs),ema,ctx(),P)
    assert ep and ep.episode_start_index==7 and ep.first_gap_index==9

def test_018_ma_slope_must_align_with_active_trend():
    cs,ema=falling_fixture(8)
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        ep=classify_ma_gap_episode(tuple(cs),ema,ctx("LONG"),P)
    assert ep and not ep.active and ep.state=="MA_SLOPE_NOT_ALIGNED_WITH_ACTIVE_TREND"

def test_018_candidate_preserves_episode_identity():
    cs,ema=rising_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        found=detect_moving_average_pullback_setups(snap(cs),ctx(),P)
    item=next(x for x in found if x.setup_type=="FIRST_MA_GAP_BAR_LONG")
    m=dict(item.metadata)
    assert m["canonical_gap_id"]=="BROOKS-GAP-018" and m["episode_id"].startswith("MA_GAP_EPISODE:LONG:")

def test_018_bear_mirror():
    cs,ema=falling_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong("SHORT")):
        ep=classify_ma_gap_episode(tuple(cs),ema,ctx("SHORT"),P)
    assert ep and ep.direction=="SHORT" and ep.first_gap_index==7

def test_018_prefix_future_reset_does_not_relabel_prior_episode():
    cs,ema=rising_fixture(7,{6})
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        before=classify_ma_gap_episode(tuple(cs),ema,ctx(),P)
    cs2=cs+[bar(7,104,106,102,103),bar(8,103,105,101,102)]
    ema2=ema+(D("105"),D("104"))
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        historical=classify_ma_gap_episode(tuple(cs),ema,ctx(),P)
        after=classify_ma_gap_episode(tuple(cs2),ema2,ctx(),P)
    assert before==historical and after.evaluated_index==8

# BROOKS-GAP-019

def _twenty_touch(direction="LONG",count=20):
    n=count+1
    if direction=="LONG":
        ema=tuple(D(100+i)/D("10")+D("100") for i in range(n))
        cs=[bar(i,e+2,e+4,e+1,e+3) for i,e in enumerate(ema[:-1])]
        e=ema[-1]; cs.append(bar(n-1,e+2,e+3,e-1,e))  # bearish-ish/touch; no reversal minimum required
    else:
        ema=tuple(D("140")-D(i)/D("10") for i in range(n))
        cs=[bar(i,e-2,e-1,e-4,e-3) for i,e in enumerate(ema[:-1])]
        e=ema[-1]; cs.append(bar(n-1,e-2,e+1,e-3,e))
    return cs,ema

def test_019_twenty_first_touch_no_reversal_bar_hard_gate():
    cs,ema=_twenty_touch("LONG",20)
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        found=detect_moving_average_pullback_setups(snap(cs),ctx(),P)
    item=next(x for x in found if x.setup_type=="TWENTY_GAP_BAR_LONG")
    assert dict(item.metadata)["entry_semantic"]=="FIRST_TOUCH_AT_OR_NEAR_MA_SOURCE_VARIANT"

def test_019_nineteen_is_not_literal_twenty_gap_condition():
    cs,ema=_twenty_touch("LONG",19)
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        found=detect_moving_average_pullback_setups(snap(cs),ctx(),P)
    assert not any(x.setup_type=="TWENTY_GAP_BAR_LONG" for x in found)

def test_019_bear_mirror_first_touch():
    cs,ema=_twenty_touch("SHORT",20)
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong("SHORT")):
        found=detect_moving_average_pullback_setups(snap(cs),ctx("SHORT"),P)
    assert any(x.setup_type=="TWENTY_GAP_BAR_SHORT" for x in found)

def test_019_weak_context_does_not_promote_touch():
    cs,ema=_twenty_touch("LONG",20)
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=weak()):
        found=detect_moving_average_pullback_setups(snap(cs),ctx(),P)
    assert not any(x.setup_type=="TWENTY_GAP_BAR_LONG" for x in found)

def test_019_prefix_before_touch_has_no_touch_candidate():
    cs,ema=_twenty_touch("LONG",20)
    prefix=cs[:-1]; ema_prefix=ema[:-1]
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema_prefix), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        found=detect_moving_average_pullback_setups(snap(prefix),ctx(),P)
    assert not any(x.setup_type=="TWENTY_GAP_BAR_LONG" for x in found)

def test_019_metadata_keeps_twenty_condition_source_owned_only_here():
    cs,ema=_twenty_touch("LONG",20)
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        item=next(x for x in detect_moving_average_pullback_setups(snap(cs),ctx(),P) if x.setup_type=="TWENTY_GAP_BAR_LONG")
    assert dict(item.metadata)["twenty_bar_condition"]=="SOURCE_OWNED_FOR_BROOKS_GAP_019_ONLY"

# BROOKS-GAP-020

def test_020_ma_gap_maturity_is_context_not_prediction():
    cs,ema=rising_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        obs=scan_ma_gap_observations(snap(cs),ctx(),P)
    item=next(x for x in obs if x.pattern_id=="MA_GAP_TREND_MATURITY_CONTEXT")
    assert dict(item.metadata)["trade_eligible"]=="false"
    assert "NOT_REVERSAL_PREDICTION" in dict(item.metadata)["state"]

def test_020_no_ma_gap_evidence_no_maturity_context():
    cs,ema=rising_fixture(8,set())
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        obs=scan_ma_gap_observations(snap(cs),ctx(),P)
    assert not any(x.pattern_id=="MA_GAP_TREND_MATURITY_CONTEXT" for x in obs)

def test_020_origin_episode_id_is_preserved():
    cs,ema=rising_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        ep=classify_ma_gap_episode(tuple(cs),ema,ctx(),P)
        mat=classify_ma_gap_maturity_context(ep,None,None,evaluated_index=7)
    assert mat and mat.origin_episode_id==ep.episode_id

def test_020_bear_mirror_context():
    cs,ema=falling_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong("SHORT")):
        obs=scan_ma_gap_observations(snap(cs),ctx("SHORT"),P)
    assert any(x.pattern_id=="MA_GAP_TREND_MATURITY_CONTEXT" and x.direction=="SHORT" for x in obs)

def test_020_future_gap_not_visible_on_earlier_prefix():
    cs,ema=rising_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema[:-1]), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        obs=scan_ma_gap_observations(snap(cs[:-1]),ctx(),P)
    assert not any(x.pattern_id=="MA_GAP_TREND_MATURITY_CONTEXT" for x in obs)

def test_020_trade_eligibility_owned_by_no_entry_rule():
    cs,ema=rising_fixture(8,{7})
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        item=next(x for x in scan_ma_gap_observations(snap(cs),ctx(),P) if x.pattern_id=="MA_GAP_TREND_MATURITY_CONTEXT")
    assert item.role=="TREND_MATURITY_CONTEXT" and dict(item.metadata)["canonical_gap_id"]=="BROOKS-GAP-020"

# BROOKS-GAP-055

def test_055_below_twenty_can_remain_strong_trend_ma_test_context():
    cs,ema=_twenty_touch("LONG",8)
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        x=classify_ma_gap_count_context(tuple(cs),ema,ctx(),P)
    assert x and x.consecutive_non_touch_bars==8 and not x.twenty_bar_source_guide_met
    assert x.state=="STRONG_TREND_MA_TEST_BELOW_TWENTY_SOURCE_GUIDE"

def test_055_twenty_is_source_guide_not_magic_threshold():
    cs,ema=_twenty_touch("LONG",20)
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        x=classify_ma_gap_count_context(tuple(cs),ema,ctx(),P)
    assert x and x.twenty_bar_source_guide_met

def test_055_count_without_strong_context_is_not_promoted():
    cs,ema=_twenty_touch("LONG",8)
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=weak()):
        x=classify_ma_gap_count_context(tuple(cs),ema,ctx(),P)
    assert x and x.state=="MA_TEST_COUNT_CONTEXT_WITHOUT_STRONG_TREND_CONFIRMATION" and not x.trade_eligible

def test_055_no_touch_no_count_context():
    cs,ema=rising_fixture(8,set())
    assert classify_ma_gap_count_context(tuple(cs),ema,ctx(),P) is None

def test_055_observation_labels_engineering_vs_source_semantics():
    cs,ema=_twenty_touch("LONG",8)
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema), patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong()):
        item=next(x for x in scan_ma_gap_observations(snap(cs),ctx(),P) if x.pattern_id=="MA_GAP_COUNT_CONTEXT")
    m=dict(item.metadata)
    assert m["semantic"]=="TWENTY_IS_SOURCE_GUIDE_NOT_UNIVERSAL_HARD_GATE" and m["trade_eligible"]=="false"

def test_055_bear_mirror_below_twenty_context():
    cs,ema=_twenty_touch("SHORT",7)
    with patch("app.modules.brooks_core.pattern_expansion.classify_strong_trend_evidence",return_value=strong("SHORT")):
        x=classify_ma_gap_count_context(tuple(cs),ema,ctx("SHORT"),P)
    assert x and x.direction=="SHORT" and not x.twenty_bar_source_guide_met

# BROOKS-GAP-056

def _second_seq(direction="LONG"):
    ema=(D("100"),)*4
    if direction=="LONG":
        cs=[bar(0,94,98,93,96),bar(1,96,99,95,97),bar(2,97,98.5,92,93),bar(3,93,97,91,96)]
    else:
        cs=[bar(0,106,107,102,104),bar(1,104,105,101,103),bar(2,103,108,101.5,107),bar(3,107,109,103,104)]
    return cs,ema

def test_056_second_attempt_sequence_identity_long():
    cs,ema=_second_seq("LONG")
    x=_second_ma_gap_sequence(tuple(cs),ema,direction="LONG")
    assert x and (x.first_attempt_index,x.move_away_index,x.second_attempt_index)==(0,2,3)

def test_056_bear_mirror():
    cs,ema=_second_seq("SHORT")
    x=_second_ma_gap_sequence(tuple(cs),ema,direction="SHORT")
    assert x and x.direction=="SHORT" and x.second_attempt_index==3

def test_056_no_move_away_no_second_sequence():
    ema=(D("100"),)*4
    cs=[bar(0,94,98,93,96),bar(1,96,99,95,97),bar(2,97,99,96,98),bar(3,98,99,97,98.5)]
    assert _second_ma_gap_sequence(tuple(cs),ema,direction="LONG") is None

def test_056_no_first_attempt_no_second_sequence():
    ema=(D("100"),)*4
    cs=[bar(0,97,98,93,94),bar(1,94,96,92,93),bar(2,93,97,91,96),bar(3,96,99,95,98)]
    assert _second_ma_gap_sequence(tuple(cs),ema,direction="LONG") is None

def test_056_prefix_has_no_future_second_attempt():
    cs,ema=_second_seq("LONG")
    assert _second_ma_gap_sequence(tuple(cs[:-1]),ema[:-1],direction="LONG") is None
    assert _second_ma_gap_sequence(tuple(cs),ema,direction="LONG") is not None

def test_056_candidate_preserves_typed_sequence_identity():
    cs,ema=_second_seq("LONG")
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema):
        found=detect_moving_average_pullback_setups(snap(cs),ctx(),P)
    item=next(x for x in found if x.setup_type=="SECOND_MA_GAP_BAR_LONG")
    m=dict(item.metadata)
    assert m["canonical_gap_id"]=="BROOKS-GAP-056"
    assert int(m["first_attempt_index"]) < int(m["move_away_index"]) < int(m["second_attempt_index"])

def test_056_engineering_policy_is_not_source_threshold():
    cs,ema=_second_seq("LONG")
    with patch("app.modules.brooks_core.pattern_expansion._ema20",return_value=ema):
        item=next(x for x in detect_moving_average_pullback_setups(snap(cs),ctx(),P) if x.setup_type=="SECOND_MA_GAP_BAR_LONG")
    assert dict(item.metadata)["engineering_policy"]=="DISTANCE_TO_MA_DIRECTION_OF_CHANGE_NOT_SOURCE_THRESHOLD"
