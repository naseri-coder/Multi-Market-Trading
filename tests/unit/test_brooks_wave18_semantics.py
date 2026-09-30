from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.brooks_core.advanced_context import _spike, assess_advanced_context
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import (
    BrooksPatternCandidate,
    BrooksPatternObservation,
    BrooksPatternScan,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.engine_contract import (
    BrooksEngineResult,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceEvidence,
    TargetSourceIdentity,
)
from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 9, 18, tzinfo=UTC)
P = BrooksFullCorePolicy()


def bar(i, o, h, l, c):
    t = BASE + timedelta(minutes=15 * i)
    return Candle(t, t + timedelta(minutes=15), D(str(o)), D(str(h)), D(str(l)), D(str(c)), D("1"))


def snap(cs):
    cs = tuple(cs)
    return MarketSnapshot("binance", "futures", "BTCUSDT", "15m", cs, cs[-1].close_time, "W18")


def flat_bars(n=21, low=96, high=104, close=100):
    return [bar(i, close, high, low, close) for i in range(n)]


def candidate(direction="LONG", family="BREAKOUT", signal_index=20, metadata=(), setup="W18"):
    return BrooksPatternCandidate(
        direction,
        setup,
        family,
        signal_index,
        ("source_identity", "source_context"),
        ("W18-TEST",),
        "SOURCE_INTERPRETATION",
        1,
        "ANY",
        metadata=metadata,
    )


def adv_none():
    return SimpleNamespace(
        spike_measured_move_identity=None,
        measured_move_target=None,
        measured_move_direction="UNRESOLVED",
    )


def range_md(low="96", high="104", rid="RANGE:0:19"):
    return (
        ("range_id", rid),
        ("range_low", low),
        ("range_high", high),
    )


def range_plan(direction="LONG", state="RANGE_TRADE"):
    return TargetPlanLifecycle(
        f"PLAN:{direction}:{state}", state, direction, 20, range_id="RANGE:0:19"
    )


def fake_channel(direction="LONG"):
    a1 = SimpleNamespace(candle_index=2, confirmed_at_index=4, price=D("100"))
    a2 = SimpleNamespace(candle_index=8, confirmed_at_index=10, price=D("102"))
    opp = SimpleNamespace(candle_index=5, confirmed_at_index=7, price=D("110"))
    if direction == "LONG":
        return SimpleNamespace(
            direction="BULL_TREND",
            trend_line=SimpleNamespace(anchors=(a1, a2)),
            opposite_channel_line=SimpleNamespace(anchors=(opp,)),
            projected_lower=D("100"),
            projected_upper=D("110"),
            width=D("10"),
        )
    return SimpleNamespace(
        direction="BEAR_TREND",
        trend_line=SimpleNamespace(anchors=(a1, a2)),
        opposite_channel_line=SimpleNamespace(anchors=(opp,)),
        projected_lower=D("90"),
        projected_upper=D("100"),
        width=D("10"),
    )


def failure_obs(confirmed=True):
    return BrooksPatternObservation(
        "FAILED_FINAL_FLAG",
        "Failed reversal lifecycle",
        "FAILURE_CONTEXT",
        10,
        direction="LONG",
        source_rule_ids=("BB-REV-09-FAILURES",),
        metadata=(
            ("attempt_id", "ATTEMPT:FAILED:1"),
            ("origin_signal_index", "5"),
            ("failure_index", "10"),
            ("failure_confirmed", "true" if confirmed else "false"),
            ("trade_eligible", "false"),
        ),
    )


# ---------------------------------------------------------------------------
# BROOKS-GAP-021
# ---------------------------------------------------------------------------

def test_021_full_spike_span_not_latest_internal_pair():
    cs = [
        bar(0, 100, 111, 99, 110),
        bar(1, 110, 121, 109, 120),
        bar(2, 120, 131, 119, 130),
        bar(3, 130, 132, 128, 130),
    ]
    with patch("app.modules.brooks_core.advanced_context.is_strong_bull_bar", side_effect=lambda c, p: c.close > c.open and c.close-c.open >= D("8")),          patch("app.modules.brooks_core.advanced_context.is_strong_bear_bar", return_value=False):
        _, identity = _spike(snap(cs), P)
    assert identity == (0, 2, "LONG")


def test_021_both_source_anchor_variants_are_preserved():
    cs = [
        bar(0, 100, 111, 99, 110),
        bar(1, 110, 121, 109, 120),
        bar(2, 120, 131, 119, 130),
        bar(3, 130, 132, 128, 130),
    ]
    patches = (
        patch("app.modules.brooks_core.advanced_context.is_strong_bull_bar", side_effect=lambda c, p: c.close > c.open and c.close-c.open >= D("8")),
        patch("app.modules.brooks_core.advanced_context.is_strong_bear_bar", return_value=False),
        patch("app.modules.brooks_core.advanced_context._tight_channel_direction", return_value="UNRESOLVED"),
        patch("app.modules.brooks_core.advanced_context.classify_micro_channel_identity", return_value=None),
        patch("app.modules.brooks_core.advanced_context.classify_spike_channel_lifecycle", return_value=None),
        patch("app.modules.brooks_core.advanced_context.classify_small_pullback_trend", return_value=None),
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        x = assess_advanced_context(snap(cs), policy=P)
    ident = x.spike_measured_move_identity
    assert ident is not None
    assert (ident.start_index, ident.end_index) == (0, 2)
    assert ident.open_close_target == D("160")
    assert ident.extreme_target == D("163")


def test_021_single_strong_bar_is_near_miss_not_spike():
    cs = [bar(0, 100, 111, 99, 110), bar(1, 110, 112, 108, 110)]
    with patch("app.modules.brooks_core.advanced_context.is_strong_bull_bar", side_effect=lambda c, p: c.close > c.open and c.close-c.open >= D("8")),          patch("app.modules.brooks_core.advanced_context.is_strong_bear_bar", return_value=False):
        _, identity = _spike(snap(cs), P)
    assert identity is None


def test_021_prefix_causality_extends_identity_without_backdating():
    first = [bar(0, 100, 111, 99, 110), bar(1, 110, 121, 109, 120)]
    third = first + [bar(2, 120, 131, 119, 130)]
    with patch("app.modules.brooks_core.advanced_context.is_strong_bull_bar", return_value=True),          patch("app.modules.brooks_core.advanced_context.is_strong_bear_bar", return_value=False):
        _, a = _spike(snap(first), P)
        _, b = _spike(snap(third), P)
    assert a == (0, 1, "LONG")
    assert b == (0, 2, "LONG")


# ---------------------------------------------------------------------------
# BROOKS-GAP-022 / 023
# ---------------------------------------------------------------------------

def test_022_channel_breakout_height_target_uses_canonical_channel():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "BREAKOUT")
    with patch("app.modules.brooks_core.books_full_engine.build_trend_channel_geometry", return_value=fake_channel("LONG")),          patch("app.modules.brooks_core.books_full_engine.classify_channel_boundary_event", return_value=SimpleNamespace(state="CHANNEL_LINE_BREAK", boundary_value=D("110"))):
        out = e._channel_target_sources(snap(flat_bars()), c)
    mm = next(x for x in out if x[1].source_type == "CHANNEL_BREAKOUT_MEASURED_MOVE")
    assert mm[0] == D("120")
    assert mm[1].structure_id.startswith("CHANNEL:BULL_TREND")


def test_022_channel_test_without_close_break_has_no_measured_move():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "BREAKOUT")
    with patch("app.modules.brooks_core.books_full_engine.build_trend_channel_geometry", return_value=fake_channel("LONG")),          patch("app.modules.brooks_core.books_full_engine.classify_channel_boundary_event", return_value=SimpleNamespace(state="CHANNEL_LINE_TEST", boundary_value=D("110"))):
        out = e._channel_target_sources(snap(flat_bars()), c)
    assert not any(x[1].source_type == "CHANNEL_BREAKOUT_MEASURED_MOVE" for x in out)


def test_022_short_directional_mirror():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("SHORT", "BREAKOUT")
    with patch("app.modules.brooks_core.books_full_engine.build_trend_channel_geometry", return_value=fake_channel("SHORT")),          patch("app.modules.brooks_core.books_full_engine.classify_channel_boundary_event", return_value=SimpleNamespace(state="CHANNEL_LINE_BREAK", boundary_value=D("90"))):
        out = e._channel_target_sources(snap(flat_bars()), c)
    mm = next(x for x in out if x[1].source_type == "CHANNEL_BREAKOUT_MEASURED_MOVE")
    assert mm[0] == D("80")


def test_023_channel_side_and_start_are_typed_trend_magnets():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TREND_CONTINUATION")
    with patch("app.modules.brooks_core.books_full_engine.build_trend_channel_geometry", return_value=fake_channel("LONG")):
        out = e._channel_target_sources(snap(flat_bars()), c)
    types = {x[1].source_type for x in out}
    assert {"TREND_CHANNEL_OPPOSITE_SIDE", "TREND_CHANNEL_START"} <= types


def test_023_moving_average_and_breakout_test_are_source_typed():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TREND_CONTINUATION", metadata=(("reference_level", "106"), ("reference_swing_index", "8")))
    plan = TargetPlanLifecycle("P", "TREND_TRADE", "LONG", 20)
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            snap(flat_bars()), c, entry=D("90"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=plan,
        )
    types = {x[1].source_type for x in out}
    assert "MOVING_AVERAGE_TEST" in types
    assert "BREAKOUT_TEST_LEVEL" in types


def test_023_behind_entry_magnet_is_not_promoted_to_target():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TREND_CONTINUATION")
    plan = TargetPlanLifecycle("P", "TREND_TRADE", "LONG", 20)
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            snap(flat_bars()), c, entry=D("110"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=plan,
        )
    assert not any(x[1].source_type == "MOVING_AVERAGE_TEST" for x in out)


# ---------------------------------------------------------------------------
# BROOKS-GAP-046
# ---------------------------------------------------------------------------

def test_046_range_midpoint_is_typed_magnet():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TRADING_RANGE_FADE", metadata=range_md())
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            snap(flat_bars()), c, entry=D("96"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=range_plan(),
        )
    mid = next(x for x in out if x[1].source_type == "RANGE_MIDPOINT")
    assert mid[0] == D("100")
    assert mid[1].structure_id == "RANGE:0:19"


def test_046_range_midpoint_behind_or_at_entry_is_not_target():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TRADING_RANGE_FADE", metadata=range_md())
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            snap(flat_bars()), c, entry=D("101"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=range_plan(),
        )
    assert not any(x[1].source_type == "RANGE_MIDPOINT" for x in out)


def test_046_short_midpoint_mirror():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("SHORT", "TRADING_RANGE_FADE", metadata=range_md())
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            snap(flat_bars()), c, entry=D("104"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=range_plan("SHORT"),
        )
    assert any(x[1].source_type == "RANGE_MIDPOINT" and x[0] == D("100") for x in out)


# ---------------------------------------------------------------------------
# BROOKS-GAP-047
# ---------------------------------------------------------------------------

def test_047_failed_reversal_origin_produces_stateful_entry_and_signal_magnets():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    cs = flat_bars()
    c = candidate("LONG", "MAJOR_TREND_REVERSAL")
    mocked = BrooksPatternScan((), (failure_obs(True),), ())
    with patch("app.modules.brooks_core.books_full_engine.scan_full_brooks_patterns", return_value=mocked):
        out = e._failed_reversal_target_sources(snap(cs), c, D(".1"))
    types = {x[1].source_type for x in out}
    assert "FAILED_REVERSAL_ENTRY_PRICE" in types
    assert "FAILED_REVERSAL_SIGNAL_BAR_HIGH" in types
    assert "FAILED_REVERSAL_SIGNAL_BAR_LOW" in types
    assert all(x[1].structure_id == "ATTEMPT:FAILED:1" for x in out)


def test_047_unconfirmed_failure_is_not_magnet_source():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "MAJOR_TREND_REVERSAL")
    mocked = BrooksPatternScan((), (failure_obs(False),), ())
    with patch("app.modules.brooks_core.books_full_engine.scan_full_brooks_patterns", return_value=mocked):
        out = e._failed_reversal_target_sources(snap(flat_bars()), c, D(".1"))
    assert out == []


def test_047_numeric_price_without_failure_origin_is_insufficient():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "MAJOR_TREND_REVERSAL", metadata=(("reference_level", "100"),))
    with patch("app.modules.brooks_core.books_full_engine.scan_full_brooks_patterns", return_value=BrooksPatternScan((), (), ())):
        out = e._failed_reversal_target_sources(snap(flat_bars()), c, D(".1"))
    assert out == []


# ---------------------------------------------------------------------------
# BROOKS-GAP-048
# ---------------------------------------------------------------------------

def _src(kind, sid, price, *, classification="SOURCE_SEMANTIC"):
    return (
        D(str(price)),
        TargetSourceEvidence(kind, sid, 1, 10, "LONG", sid, classification),
        kind.lower(),
    )


def test_048_arbitration_consumes_typed_identity_and_does_not_truncate_by_distance():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    entries = [
        _src("RANGE_MIDPOINT", "MID", 110),
        _src("OPPOSITE_RANGE_BOUNDARY", "EDGE", 120),
        _src("FAILED_REVERSAL_ENTRY_PRICE", "FAIL", 115),
    ]
    typed, basis = e._coalesce_target_identities(entries, signal_index=20)
    targets, final, _ = e._arbitrate_target_identities(
        typed, entry=D("100"), direction="LONG", signal_index=20, basis_by_source_id=basis
    )
    assert isinstance(typed[0], TargetSourceIdentity)
    assert targets == (D("110"), D("115"), D("120"))
    assert len(final) == 3


def test_048_coincident_numeric_target_retains_multiple_semantic_sources():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    entries = [_src("RANGE_MIDPOINT", "MID", 110), _src("FAILED_REVERSAL_ENTRY_PRICE", "FAIL", 110)]
    typed, basis = e._coalesce_target_identities(entries, signal_index=20)
    _, final, _ = e._arbitrate_target_identities(
        typed, entry=D("100"), direction="LONG", signal_index=20, basis_by_source_id=basis
    )
    assert len(final) == 1
    assert {s.source_id for s in final[0].sources} == {"MID", "FAIL"}


def test_048_input_order_change_does_not_change_semantic_origin_by_price():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    entries = [_src("RANGE_MIDPOINT", "MID", 110), _src("OPPOSITE_RANGE_BOUNDARY", "EDGE", 120)]
    def mapping(xs):
        typed, basis = e._coalesce_target_identities(xs, signal_index=20)
        _, final, _ = e._arbitrate_target_identities(
            typed, entry=D("100"), direction="LONG", signal_index=20, basis_by_source_id=basis
        )
        return {x.target_price: {s.source_id for s in x.sources} for x in final}
    assert mapping(entries) == mapping(list(reversed(entries)))


# ---------------------------------------------------------------------------
# BROOKS-GAP-049
# ---------------------------------------------------------------------------

def breakout_snapshot(long=True, close_beyond=True):
    cs = flat_bars(20, low=96, high=104, close=100)
    if long:
        cs.append(bar(20, 103, 106, 102, 105 if close_beyond else 103))
    else:
        cs.append(bar(20, 97, 98, 94, 95 if close_beyond else 97))
    return snap(cs)


def test_049_range_height_measured_move_uses_identified_range():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "BREAKOUT", metadata=range_md())
    plan = TargetPlanLifecycle("P", "BREAKOUT_TRANSITION", "LONG", 20, range_id="RANGE:0:19")
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            breakout_snapshot(True, True), c, entry=D("105.1"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=plan,
        )
    mm = next(x for x in out if x[1].source_type == "RANGE_HEIGHT_MEASURED_MOVE")
    assert mm[0] == D("112")
    assert mm[1].structure_id == "RANGE:0:19"


def test_049_return_inside_is_not_successful_range_breakout_projection():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "BREAKOUT", metadata=range_md())
    plan = TargetPlanLifecycle("P", "BREAKOUT_TRANSITION", "LONG", 20, range_id="RANGE:0:19")
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            breakout_snapshot(True, False), c, entry=D("104.1"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=plan,
        )
    assert not any(x[1].source_type == "RANGE_HEIGHT_MEASURED_MOVE" for x in out)


def test_049_short_range_height_mirror():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("SHORT", "BREAKOUT", metadata=range_md())
    plan = TargetPlanLifecycle("P", "BREAKOUT_TRANSITION", "SHORT", 20, range_id="RANGE:0:19")
    with patch.object(e, "_channel_target_sources", return_value=[]),          patch.object(e, "_failed_reversal_target_sources", return_value=[]):
        out = e._source_target_pool(
            breakout_snapshot(False, True), c, entry=D("94.9"), recent_average_range=D("4"),
            tick=D(".1"), advanced=adv_none(), target_plan=plan,
        )
    assert any(x[1].source_type == "RANGE_HEIGHT_MEASURED_MOVE" and x[0] == D("88") for x in out)


# ---------------------------------------------------------------------------
# BROOKS-GAP-050 + WAVE17 identity consumption
# ---------------------------------------------------------------------------

def test_050_range_trade_state():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TRADING_RANGE_FADE", metadata=range_md())
    x = e._target_plan_lifecycle(snap(flat_bars()), c, context=SimpleNamespace(regime="TRADING_RANGE"))
    assert x.state == "RANGE_TRADE" and x.range_id == "RANGE:0:19"


def test_050_breakout_transition_state():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "BREAKOUT", metadata=range_md())
    x = e._target_plan_lifecycle(breakout_snapshot(True, True), c, context=SimpleNamespace(regime="TRADING_RANGE"))
    assert x.state == "BREAKOUT_TRANSITION"
    assert x.transition_index == 20


def test_050_failed_breakout_restores_range_trade_semantic():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("SHORT", "FAILED_BREAKOUT", metadata=range_md())
    x = e._target_plan_lifecycle(snap(flat_bars()), c, context=SimpleNamespace(regime="TRADING_RANGE"))
    assert x.state == "FAILED_BREAKOUT_TRADE"


def test_050_w17_target_and_initial_stop_identity_are_consumed_directly():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TRADING_RANGE_FADE", metadata=range_md())
    src = TargetSourceEvidence("RANGE_MIDPOINT", "SRC:MID", 0, 19, "LONG", "RANGE:0:19")
    tid = TargetSourceIdentity(1, D("100"), (src,), 20)
    sid = StopSourceIdentity(D("94"), "INITIAL_PROTECTIVE_STOP", "STOP:ORIGIN", D("95"), 5, 20, "EXISTING", direction="LONG")
    x = e._target_plan_lifecycle(
        snap(flat_bars()), c, context=SimpleNamespace(regime="TRADING_RANGE"),
        target_source_identities=(tid,), stop_source_identity=sid,
    )
    assert x.target_source_ids == ("SRC:MID",)
    assert x.initial_stop_source_id == "STOP:ORIGIN"


def test_050_stop_price_without_stop_identity_is_not_reconstructed():
    e = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "TRADING_RANGE_FADE", metadata=range_md())
    x = e._target_plan_lifecycle(
        snap(flat_bars()), c, context=SimpleNamespace(regime="TRADING_RANGE"),
        target_source_identities=(), stop_source_identity=None,
    )
    assert x.initial_stop_source_id is None


def test_wave17_identity_and_wave18_plan_survive_core_to_paper_mapping():
    s = snap(flat_bars())
    src = TargetSourceEvidence("RANGE_MIDPOINT", "SRC:MID", 0, 19, "LONG", "RANGE:0:19")
    tid = TargetSourceIdentity(1, D("110"), (src,), 20)
    sid = StopSourceIdentity(D("94"), "INITIAL_PROTECTIVE_STOP", "STOP:1", D("95"), 5, 20, "EXISTING", direction="LONG")
    plan = TargetPlanLifecycle("PLAN:1", "RANGE_TRADE", "LONG", 20, range_id="RANGE:0:19", target_source_ids=("SRC:MID",), initial_stop_source_id="STOP:1")
    d = BrooksCoreDecision(
        "LONG", "sig", D("105"), D("94"), (D("110"),), "X", (), (), (), (),
        "e", "r", "c", s.snapshot_id, s.snapshot_hash, "chart.png", (tid,), sid, plan
    )
    paper = to_paper_candidate(snapshot=s, decision=d)
    assert paper.target_source_identities == (tid,)
    assert paper.stop_source_identity == sid
    assert paper.target_plan_lifecycle == plan


def test_no_signal_cannot_acquire_target_plan_identity():
    plan = TargetPlanLifecycle("P", "REVERSAL_OR_TRANSITION", "LONG", 20)
    with pytest.raises(ValueError, match="NO_SIGNAL"):
        BrooksEngineResult(
            "NO_SIGNAL", None, None, (), None, (), (), (), (), "e", "r", "c",
            target_plan_lifecycle=plan,
        )


def test_future_target_confirmation_cannot_backdate_availability():
    src = TargetSourceEvidence("RANGE_MIDPOINT", "FUTURE", 0, 21, "LONG", "R")
    with pytest.raises(ValueError, match="confirmed after"):
        TargetSourceIdentity(1, D("110"), (src,), 20)


def test_080_behavior_is_absent_from_wave18_contract_types():
    import app.modules.brooks_core.engine_contract as c
    names = set(dir(c))
    assert "ReversalOutcomeLifecycle" not in names
    assert "BrooksGap080Lifecycle" not in names


@pytest.mark.asyncio
async def test_repaired_tradeable_target_plan_propagates_engine_to_core_to_paper(tmp_path):
    from app.modules.brooks_core.analyzer_adapter import BrooksCoreAnalyzerAdapter

    from dataclasses import replace
    engine = BrooksTrilogyFullCoreEngine(policy=replace(P, enable_trade_decisions=True))
    snapshot = snap(flat_bars(80))
    c = candidate("LONG", "TRADING_RANGE_FADE", signal_index=79, metadata=(
        ("range_id", "RANGE:0:78"),
        ("range_low", "96"),
        ("range_high", "104"),
        ("entry_method", "LIMIT_OR_MARKET_FADE"),
        ("entry_trigger_semantic", "AT_OR_NEAR_CANONICAL_RANGE_EDGE"),
        ("entry_reference_price", "96"),
        ("economic_opportunity_id", "RANGE_FADE:R:LONG:79"),
    ))
    src = TargetSourceEvidence("RANGE_MIDPOINT", "SRC:MID:79", 0, 78, "LONG", "RANGE:0:78")
    tid = TargetSourceIdentity(1, D("100"), (src,), 79)
    sid = StopSourceIdentity(D("94"), "INITIAL_PROTECTIVE_STOP", "STOP:79", D("95"), 70, 79, "EXISTING", direction="LONG")
    plan = TargetPlanLifecycle(
        "PLAN:RANGE:79", "RANGE_TRADE", "LONG", 79,
        range_id="RANGE:0:78",
        target_source_ids=("SRC:MID:79",),
        initial_stop_source_id="STOP:79",
    )
    ctx = SimpleNamespace(regime="TRADING_RANGE", structure_direction="UNRESOLVED", always_in="LONG")
    probability = SimpleNamespace(band=SimpleNamespace(value="HIGHER"), reasons=("source-valid",))
    scan = BrooksPatternScan((c,), (), ())

    with patch("app.modules.brooks_core.books_full_engine.assess_books_context", return_value=ctx),          patch("app.modules.brooks_core.books_full_engine.assess_advanced_context", return_value=adv_none()),          patch("app.modules.brooks_core.books_full_engine.build_market_context", return_value=SimpleNamespace()),          patch("app.modules.brooks_core.books_full_engine.scan_full_brooks_patterns", return_value=scan),          patch("app.modules.brooks_core.books_full_engine.assess_higher_probability", return_value=probability),          patch.object(engine, "_context_contract_status", return_value=("PASS", "ok")),          patch.object(engine, "_barbwire_stop_entry_veto", return_value=False),          patch.object(engine, "_context_evidence", return_value=()),          patch.object(engine, "_observation_evidence", return_value=()),          patch.object(engine, "_candidate_evidence", return_value=()),          patch.object(engine, "_choose_candidate", return_value=c),          patch.object(engine, "_execution_geometry_with_identity", return_value=(D("96"), D("94"), (D("100"),), "existing", "range_midpoint", (tid,), sid)),          patch.object(engine, "_target_plan_lifecycle", return_value=plan):
        result = await engine.evaluate(snapshot)

    assert result.target_plan_lifecycle is plan
    assert result.target_source_identities == (tid,)
    assert result.stop_source_identity is sid

    class StubEngine:
        async def evaluate(self, _snapshot):
            return result

    class StubRenderer:
        def render(self, **kwargs):
            return tmp_path / "wave18.png"

    adapter = BrooksCoreAnalyzerAdapter(
        engine=StubEngine(), renderer=StubRenderer(), chart_directory=tmp_path
    )
    decision = await adapter.analyze(snapshot)
    assert decision.target_plan_lifecycle is plan
    assert decision.target_source_identities == (tid,)
    assert decision.stop_source_identity is sid

    paper = to_paper_candidate(snapshot=snapshot, decision=decision)
    assert paper is not None
    assert paper.target_plan_lifecycle is plan
    assert paper.target_source_identities == (tid,)
    assert paper.stop_source_identity is sid
    assert paper.entry_price == D("96")
    assert paper.targets == (D("100"),)
