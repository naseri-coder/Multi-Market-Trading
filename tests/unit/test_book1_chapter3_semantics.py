from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.correction_lifecycle import (
    build_breakout_attempt_identity,
    classify_breakout_lifecycle,
    classify_breakout_test,
)
from app.modules.brooks_core.structural_geometry import classify_structural_test

from app.modules.brooks_core.advanced_context import (
    classify_breakout_to_range_episode_link,
    classify_channel_opposing_flag_context,
    classify_channel_start_structural_test,
)
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import assess_range_identity_evidence
from app.modules.brooks_core.pattern_expansion import (
    scan_additional_context_observations,
    scan_breakout_lifecycle_observations,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 9, 1, tzinfo=UTC)
P = BrooksFullCorePolicy()


def bar(i, o, h, low, c):
    t = BASE + timedelta(minutes=15 * i)
    return Candle(
        t,
        t + timedelta(minutes=15),
        D(str(o)),
        D(str(h)),
        D(str(low)),
        D(str(c)),
        D("1"),
    )


def snap(candles, *, symbol="BTCUSDT", timeframe="15m"):
    return MarketSnapshot(
        "binance",
        "futures",
        symbol,
        timeframe,
        tuple(candles),
        candles[-1].close_time,
        "BOOK1_CH3_TEST",
    )


def breakout_prefix():
    candles = [
        bar(0, 98, 100, 97, 99),
        bar(1, 100, 106, 99, 105),
        bar(2, 103, 105, 99.5, 102),
    ]
    origin = build_breakout_attempt_identity(
        tuple(candles),
        direction="LONG",
        reference_id="SWING:0",
        reference_level=D("100"),
        attempt_index=1,
        engineering_strong=True,
    )
    assert origin is not None
    return candles, origin


def bull_channel():
    return [
        bar(0, 100, 106, 99, 105),
        bar(1, 105, 111, 104, 110),
        bar(2, 110, 111, 106, 107),
        bar(3, 107, 112, 106, 111),
        bar(4, 111, 113, 108, 112),
    ]


def bear_channel():
    return [
        bar(0, 120, 121, 114, 115),
        bar(1, 115, 116, 109, 110),
        bar(2, 110, 114, 109, 113),
        bar(3, 113, 114, 108, 109),
        bar(4, 109, 112, 107, 108),
    ]


def bull_channel_continuation_without_retrace():
    rows = bull_channel()[:4]
    rows.append(bar(4, 111, 114, 110.5, 112.5))
    return rows


def breakout_to_range():
    return [
        bar(0, 96, 98, 95, 97),
        bar(1, 97, 99, 96, 98),
        bar(2, 98, 100, 97, 98.5),
        bar(3, 98.5, 99, 97, 98),
        bar(4, 98, 99, 97, 98),
        bar(5, 98, 104, 97, 103),
        bar(6, 103, 109, 102, 108),
        bar(7, 108, 109, 104, 105),
        bar(8, 105, 110, 104, 109),
        bar(9, 109, 110, 105, 106),
        bar(10, 106, 109, 105, 108),
        bar(11, 108, 109, 104, 105),
        bar(12, 105, 108, 104, 107),
        bar(13, 107, 108, 103, 104),
        bar(14, 104, 107, 103, 106),
        bar(15, 106, 107, 103, 104.5),
        bar(16, 104.5, 106, 102.5, 104),
    ]


def range_context(candles):
    evidence = assess_range_identity_evidence(tuple(candles[7:]), P.context)
    return SimpleNamespace(
        regime="TRADING_RANGE",
        structure_direction="AMBIGUOUS",
        always_in="UNRESOLVED",
        breakout_direction="UNRESOLVED",
        range_evidence=evidence,
        metrics=SimpleNamespace(bar_overlap_rate=D("0.9")),
    )


# B1C03-014: generic structural-test occurrence is independent of reaction/outcome.
def test_b1c03_014_generic_structural_test_occurrence_is_context_only():
    candles = (
        bar(0, 101, 103, 100.5, 102),
        bar(1, 102, 103, 99.5, 101),
    )
    test = classify_structural_test(
        candles,
        reference_id="SWING:0",
        reference_type="SWING_HIGH",
        zone_low=D("99"),
        zone_high=D("100"),
        search_start_index=1,
        direction="LONG",
        reference_level=D("100"),
        origin_episode_id="BREAKOUT:LONG:SWING:0:0",
    )
    assert test is not None
    assert test.occurrence_state == "TEST_OCCURRED"
    assert test.outcome_state == "PENDING"
    assert test.reference_id == "SWING:0"
    assert test.reference_type == "SWING_HIGH"
    assert test.origin_episode_id == "BREAKOUT:LONG:SWING:0:0"
    assert not test.trade_eligible


# B1C03-015 A/B/C prefixes: occurrence != later hold/failure outcome.
def test_b1c03_015_breakout_test_occurs_before_outcome_is_known():
    candles, origin = breakout_prefix()
    test = classify_breakout_test(
        tuple(candles),
        origin,
        zone_low=D("99"),
        zone_high=D("100"),
    )
    assert test is not None
    assert test.state == "TEST_OCCURRED"
    assert test.occurrence_state == "TEST_OCCURRED"
    assert test.outcome_state == "PENDING"
    assert test.outcome_index is None
    assert not test.trade_eligible


def test_b1c03_015_later_hold_preserves_same_test_identity():
    candles, origin = breakout_prefix()
    pending = classify_breakout_test(tuple(candles), origin, zone_low=D("99"), zone_high=D("100"))
    candles.append(bar(3, 102, 106, 101, 105))
    held = classify_breakout_test(tuple(candles), origin, zone_low=D("99"), zone_high=D("100"))
    assert pending is not None and held is not None
    assert held.test_id == pending.test_id
    assert held.test_index == pending.test_index == 2
    assert held.state == "TEST_HOLDS_BREAKOUT_SIDE"
    assert held.outcome_state == "HOLDS_BREAKOUT_SIDE"
    assert held.outcome_index == 3


def test_b1c03_015_later_failure_preserves_test_and_breakout_lifecycle():
    candles, origin = breakout_prefix()
    pending = classify_breakout_test(tuple(candles), origin, zone_low=D("99"), zone_high=D("100"))
    candles.append(bar(3, 102, 103, 97, 99))
    failed = classify_breakout_test(tuple(candles), origin, zone_low=D("99"), zone_high=D("100"))
    lifecycle = classify_breakout_lifecycle(tuple(candles), origin)
    assert pending is not None and failed is not None
    assert failed.test_id == pending.test_id
    assert failed.outcome_state == "FAILS_BREAKOUT_SIDE"
    assert failed.state == "TEST_FAILS_BREAKOUT_SIDE"
    assert lifecycle.reentry_index == 3
    assert lifecycle.state == "FAILED_FOLLOW_THROUGH_REENTRY"


def test_b1c03_015_future_hold_does_not_backdate_prefix():
    candles, origin = breakout_prefix()
    prefix = classify_breakout_test(tuple(candles), origin, zone_low=D("99"), zone_high=D("100"))
    candles.append(bar(3, 102, 106, 101, 105))
    future = classify_breakout_test(tuple(candles), origin, zone_low=D("99"), zone_high=D("100"))
    assert prefix is not None and future is not None
    assert prefix.outcome_state == "PENDING"
    assert prefix.outcome_index is None
    assert future.outcome_state == "HOLDS_BREAKOUT_SIDE"


# B1C03-007: channel-start structural test appears only on the causal return.
def test_b1c03_007_channel_start_test_not_backdated_and_preserves_episode():
    candles = bull_channel()
    before = classify_channel_start_structural_test(snap(candles[:4]), P)
    at_test = classify_channel_start_structural_test(snap(candles), P)
    assert before is None
    assert at_test is not None
    assert at_test.reference_type == "CHANNEL_START"
    assert at_test.occurrence_index == 4
    assert at_test.origin_episode_id == "SPIKE:LONG:0:1"
    assert at_test.occurrence_state == "TEST_OCCURRED"
    assert at_test.outcome_state == "PENDING"
    assert not at_test.trade_eligible


def test_b1c03_007_channel_start_test_is_not_reversal_or_entry():
    test = classify_channel_start_structural_test(snap(bull_channel()), P)
    assert test is not None
    assert "REVERSAL" not in test.occurrence_state
    assert "ENTRY" not in test.occurrence_state
    assert test.outcome_state == "PENDING"
    assert not test.trade_eligible


# B1C03-008: established channels expose opposing-flag/retracement risk in both directions.
def test_b1c03_008_bull_channel_is_potential_bear_flag_context_only():
    context = classify_channel_opposing_flag_context(snap(bull_channel()[:4]), P)
    assert context is not None
    assert context.direction == "LONG"
    assert context.opposing_direction == "SHORT"
    assert context.state == "POTENTIAL_BEAR_FLAG_RETRACEMENT_RISK"
    assert not context.trade_eligible
    assert "REVERSAL" not in context.state
    assert "ENTRY" not in context.state


def test_b1c03_008_bear_channel_is_potential_bull_flag_context_only():
    context = classify_channel_opposing_flag_context(snap(bear_channel()[:4]), P)
    assert context is not None
    assert context.direction == "SHORT"
    assert context.opposing_direction == "LONG"
    assert context.state == "POTENTIAL_BULL_FLAG_RETRACEMENT_RISK"
    assert not context.trade_eligible


def test_b1c03_008_channel_can_continue_without_forced_retracement():
    snapshot = snap(bull_channel_continuation_without_retrace())
    context = classify_channel_opposing_flag_context(snapshot, P)
    test = classify_channel_start_structural_test(snapshot, P)
    assert context is not None
    assert context.state == "POTENTIAL_BEAR_FLAG_RETRACEMENT_RISK"
    assert test is None
    assert not context.trade_eligible


# B1C03-018: breakout/spike/range identities remain distinct but linked.
def test_b1c03_018_range_keeps_own_identity_and_origin_linkage():
    candles = breakout_to_range()
    link = classify_breakout_to_range_episode_link(
        snap(candles),
        P,
        current_range_supported=True,
    )
    assert link is not None
    assert link.range_id.startswith("RANGE:CH3:BTCUSDT:15m:")
    assert link.origin_breakout_id == "BREAKOUT:LONG:SWING:2:5"
    assert link.origin_spike_episode_id == "SPIKE:LONG:5:6"
    assert link.parent_evolution_episode_id == "TREND_RANGE:LONG:5"
    assert link.range_id != link.origin_breakout_id
    assert link.range_id != link.origin_spike_episode_id
    assert not link.trade_eligible


def test_b1c03_018_range_link_is_prefix_causal():
    candles = breakout_to_range()
    before = classify_breakout_to_range_episode_link(
        snap(candles[:15]),
        P,
        current_range_supported=True,
    )
    after = classify_breakout_to_range_episode_link(
        snap(candles),
        P,
        current_range_supported=True,
    )
    assert before is None
    assert after is not None
    assert after.range_established_index == 16


def test_b1c03_018_unrelated_later_range_does_not_inherit_stale_origin():
    candles = breakout_to_range()
    start = len(candles)
    for offset in range(20):
        i = start + offset
        close = 200.2 if offset % 2 == 0 else 199.8
        candles.append(bar(i, 200, 201, 199, close))
    link = classify_breakout_to_range_episode_link(
        snap(candles),
        P,
        current_range_supported=True,
    )
    assert link is None


def test_b1c03_018_symbol_timeframe_identity_isolated():
    candles = breakout_to_range()
    btc = classify_breakout_to_range_episode_link(
        snap(candles, symbol="BTCUSDT", timeframe="15m"),
        P,
        current_range_supported=True,
    )
    eth = classify_breakout_to_range_episode_link(
        snap(candles, symbol="ETHUSDT", timeframe="1h"),
        P,
        current_range_supported=True,
    )
    assert btc is not None and eth is not None
    assert btc.range_id != eth.range_id
    assert btc.link_id != eth.link_id
    assert (btc.symbol, btc.timeframe) == ("BTCUSDT", "15m")
    assert (eth.symbol, eth.timeframe) == ("ETHUSDT", "1h")


# Runtime reachability: new semantics travel through canonical observations -> evidence.
def test_chapter3_context_observations_reach_runtime_evidence_without_trade_promotion():
    candles = breakout_to_range()
    context = range_context(candles)
    observations = scan_additional_context_observations(snap(candles), context, P)
    wanted = {
        "CHANNEL_START_STRUCTURAL_TEST",
        "CHANNEL_OPPOSING_FLAG_CONTEXT",
        "BREAKOUT_RANGE_EPISODE_LINK",
    }
    found = {item.pattern_id for item in observations}
    assert wanted <= found
    for item in observations:
        if item.pattern_id in wanted:
            assert dict(item.metadata)["trade_eligible"] == "false"

    engine = BrooksTrilogyFullCoreEngine(policy=P)
    evidence = engine._observation_evidence(observations, context)
    evidence_patterns = {
        dict(row.evidence).get("pattern_id")
        for row in evidence
    }
    assert wanted <= evidence_patterns


def test_breakout_test_runtime_observation_exposes_occurrence_and_outcome_separately():
    candles = [
        bar(0, 96, 98, 95, 97),
        bar(1, 97, 99, 96, 98),
        bar(2, 98, 100, 97, 98.5),
        bar(3, 98.5, 99, 97, 98),
        bar(4, 98, 99, 97, 98),
        bar(5, 98, 104, 97, 103),
        bar(6, 99.5, 100, 98.5, 99.5),
    ]
    context = SimpleNamespace(regime="TRADING_RANGE")
    observations = scan_breakout_lifecycle_observations(snap(candles), context, P)
    tests = [item for item in observations if item.pattern_id == "BREAKOUT_TEST_LONG"]
    assert tests
    metadata = dict(tests[-1].metadata)
    assert metadata["occurrence_state"] == "TEST_OCCURRED"
    assert metadata["outcome_state"] == "PENDING"
    assert metadata["trade_eligible"] == "false"
    assert metadata["test_id"] != metadata["structure_id"]



def test_chapter3_explicit_anti_conflation_contracts():
    # Structural test occurrence is neither reaction nor an already-known hold/failure.
    structural = classify_structural_test(
        tuple(breakout_prefix()[0]),
        reference_id="SWING:0",
        reference_type="BREAKOUT_REFERENCE",
        zone_low=D("99"),
        zone_high=D("100"),
        search_start_index=2,
        direction="LONG",
        reference_level=D("100"),
        origin_episode_id="BREAKOUT:LONG:SWING:0:1",
        evaluated_index=2,
    )
    assert structural is not None
    assert structural.occurrence_state == "TEST_OCCURRED"
    assert structural.outcome_state == "PENDING"
    assert structural.outcome_state not in {"HOLDS_BREAKOUT_SIDE", "FAILS_BREAKOUT_SIDE"}
    assert not structural.trade_eligible

    # An established channel can carry opposing-flag risk without changing Always-In
    # or becoming an entry/candidate.  Continuation is still possible.
    candles = bull_channel_continuation_without_retrace()
    snapshot = snap(candles)
    context = SimpleNamespace(
        regime="BULL_TREND",
        structure_direction="BULL_TREND",
        always_in="LONG",
        breakout_direction="LONG",
        range_evidence=None,
        metrics=SimpleNamespace(bar_overlap_rate=D("0.25")),
    )
    observations = scan_additional_context_observations(snapshot, context, P)
    opposing = [
        item for item in observations
        if item.pattern_id == "CHANNEL_OPPOSING_FLAG_CONTEXT"
    ]
    assert opposing
    assert context.always_in == "LONG"
    assert all(not hasattr(item, "setup_type") for item in opposing)
    assert all(not hasattr(item, "entry_price") for item in opposing)
    assert all(dict(item.metadata)["trade_eligible"] == "false" for item in opposing)
    assert all("REVERSAL" not in dict(item.metadata)["state"] for item in opposing)

    # Channel context does not itself establish a range or force a retracement.
    assert classify_breakout_to_range_episode_link(
        snapshot,
        P,
        current_range_supported=False,
    ) is None
    assert classify_channel_start_structural_test(snapshot, P) is None
