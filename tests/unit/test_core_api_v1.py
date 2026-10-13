"""Additive Stage-3 contract regression: OFFLINE, never a real market test."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Direction, EvidenceMode, Instrument, Market
from naseri_markets.core_api_v1 import (
    ABI_MAJOR, ClosedCandle, CoreBinding, CoreContractError, CoreDecision,
    CoreEventType, CoreInput, CoreManifest, CoreResult, DataOrigin,
    DecisionKind, ExitAction, ManagementAction, OfflineCoreHarness,
    PositionSnapshot, SetupSpec, BidAskTick, to_legacy_paper_intent,
    validate_core_result,
)
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CORE = OfflineContractFixture()


def binding(provider="provider_x", symbol="ABCUSD", timeframe="15m", market=Market.CRYPTO,
            binding_id="binding_one") -> CoreBinding:
    return CoreBinding("instance_main", binding_id,
                       Instrument(market, provider, symbol, "UTC", "USD"), timeframe)


def candle(start, o, h, l, c, *, minutes=15):
    return ClosedCandle(start, start + timedelta(minutes=minutes),
                        D(str(o)), D(str(h)), D(str(l)), D(str(c)), D("10"))


def event_for(latest="long", current_binding=None) -> CoreInput:
    b = current_binding or binding()
    mins = {"1m":1,"5m":5,"15m":15,"30m":30,"1h":60,"4h":240,"12h":720,"1d":1440}[b.timeframe]
    previous = candle(T0, 100, 102, 98, 100, minutes=mins)
    nxt = (candle(T0 + timedelta(minutes=mins), 100, 108, 99, 106, minutes=mins)
           if latest == "long" else
           candle(T0 + timedelta(minutes=mins), 100, 101, 93, 94, minutes=mins)
           if latest == "short" else
           candle(T0 + timedelta(minutes=mins), 100, 101, 99, 100, minutes=mins))
    return CoreInput(CORE.manifest.core_id, CORE.manifest.core_version, b,
                     CoreEventType.CLOSED_CANDLE, nxt.close_at, DataOrigin.SYNTHETIC,
                     "offline_test_fixture", (previous, nxt))


def result_for(event):
    return CORE.evaluate(event)


def test_exact_abi_version_and_unknown_minor_refused():
    assert ABI_MAJOR == 1
    for major, minor in [(2, 0), (1, 1), (1, -1), (True, 0)]:
        with pytest.raises(CoreContractError, match="UNSUPPORTED_CORE_ABI"):
            replace(CORE.manifest, abi_major=major, abi_minor=minor)


def test_harness_default_disabled_and_no_side_effects():
    e = event_for()
    with pytest.raises(CoreContractError, match="OFFLINE_CORE_DISABLED"):
        OfflineCoreHarness(CORE).evaluate(e)
    assert OfflineCoreHarness(CORE, enabled=True).evaluate(e) == CORE.evaluate(e)


@pytest.mark.parametrize("style,side,setup", [
    ("long", Direction.LONG, "fixture_long_case"),
    ("short", Direction.SHORT, "fixture_short_case"),
])
def test_two_independent_setups(style, side, setup):
    e = event_for(style)
    out = OfflineCoreHarness(CORE, enabled=True).evaluate(e)
    d, = out.decisions
    assert d.kind is DecisionKind.ENTRY_INTENT
    assert d.direction is side and d.setup_id == setup
    assert d.entry > d.stop if side is Direction.LONG else d.entry < d.stop


def test_no_setup_has_no_trade_fields():
    e = event_for("none")
    d, = OfflineCoreHarness(CORE, enabled=True).evaluate(e).decisions
    assert d.kind is DecisionKind.NO_SETUP
    assert d.setup_id is None and d.targets == () and d.entry is None


def test_same_code_two_market_bindings_no_hardcoded_venue_or_pair():
    a = event_for("long", binding("crypto_a", "ABCUSD", "15m", Market.CRYPTO, "id_crypto"))
    b = event_for("long", binding("fx_broker_b", "EURUSD", "1h", Market.FOREX, "id_forex"))
    first = OfflineCoreHarness(CORE, enabled=True).evaluate(a)
    second = OfflineCoreHarness(CORE, enabled=True).evaluate(b)
    assert first.decisions[0].setup_id == second.decisions[0].setup_id
    assert first.decisions[0].decision_id != second.decisions[0].decision_id
    assert first.binding_id != second.binding_id
    assert first.input_digest != second.input_digest
    assert first.decisions[0].entry == second.decisions[0].entry


def test_deterministic_replay_and_legacy_bridge_data_only():
    e = event_for()
    result = result_for(e)
    assert result == result_for(e)
    legacy = to_legacy_paper_intent(CORE.manifest, e, result, result.decisions[0])
    assert legacy.evidence_mode is EvidenceMode.PAPER
    assert legacy.instrument == e.binding.instrument
    assert legacy.signal_id == result.decisions[0].decision_id


def test_invalid_candle_future_or_overlapping_refused():
    e = event_for()
    with pytest.raises(CoreContractError, match="FUTURE_CANDLE"):
        replace(e, observed_at=e.observed_at - timedelta(minutes=1))
    with pytest.raises(CoreContractError, match="OVERLAPPING"):
        replace(e, candles=(e.candles[0], e.candles[0]))
    with pytest.raises(CoreContractError, match="INVALID_OHLC"):
        candle(T0, 100, 90, 95, 100)


def test_host_binding_timeframe_is_enforced_and_not_just_metadata():
    e = event_for()
    bad = candle(T0 + timedelta(minutes=15), 100, 108, 99, 106, minutes=5)
    with pytest.raises(CoreContractError, match="CANDLE_TIMEFRAME_MISMATCH"):
        replace(e, candles=(e.candles[0], bad))


def test_empty_future_unclosed_event_refused():
    e = event_for()
    with pytest.raises(CoreContractError, match="INVALID_CLOSED_CANDLE_EVENT"):
        replace(e, candles=())
    with pytest.raises(CoreContractError, match="INVALID_CLOSED_CANDLE_EVENT"):
        replace(e, observed_at=e.observed_at + timedelta(minutes=1))


def test_result_belongs_to_exact_binding_version_and_digest():
    e = event_for()
    out = result_for(e)
    for bad in (replace(out, binding_id="other_binding"),
                replace(out, core_version="1.2.3"),
                replace(out, input_digest="0"*64),
                replace(out, observed_at=out.observed_at + timedelta(seconds=1))):
        with pytest.raises(CoreContractError, match="IDENTITY_OR_PROVENANCE"):
            validate_core_result(CORE.manifest, e, bad)


def test_unknown_setup_and_duplicate_decision_refused():
    e = event_for()
    result = result_for(e)
    d, = result.decisions
    with pytest.raises(CoreContractError, match="UNKNOWN_SETUP"):
        validate_core_result(CORE.manifest, e, replace(result,
            decisions=(replace(d, setup_id="unregistered"),)))
    with pytest.raises(CoreContractError, match="DUPLICATE_DECISION"):
        validate_core_result(CORE.manifest, e, replace(result, decisions=(d, d)))


def test_bad_entry_geometry_or_missing_targets_refused():
    e = event_for()
    d, = result_for(e).decisions
    for bad in ({"stop":d.entry+1}, {"targets":()}, {"targets":(D("NaN"),)}):
        with pytest.raises(CoreContractError):
            replace(d, **bad)


def test_outdated_intent_expiry_refused():
    e = event_for()
    result = result_for(e)
    old = replace(result.decisions[0], expires_at=e.observed_at)
    with pytest.raises(CoreContractError, match="EXPIRED_ENTRY"):
        validate_core_result(CORE.manifest, e, replace(result, decisions=(old,)))


def test_position_trailing_only_if_declared_and_monotonic():
    e = event_for()
    p = PositionSnapshot("position_1", "fixture_long_case", Direction.LONG,
                         D("106"), D("99"), D("99"), 7)
    candles = (e.candles[0], candle(e.observed_at, 105, 115, 104, 114))
    pos_event = replace(e, event=CoreEventType.POSITION_UPDATE,
                        observed_at=candles[-1].close_at, candles=candles, position=p)
    out = OfflineCoreHarness(CORE, enabled=True).evaluate(pos_event)
    d, = out.decisions
    assert d.kind is DecisionKind.MANAGEMENT_INTENT
    assert d.action is ManagementAction.MOVE_STOP and d.new_stop == p.entry
    with pytest.raises(CoreContractError, match="STOP_NOT_TIGHTENED"):
        validate_core_result(CORE.manifest, pos_event, replace(out,
            decisions=(replace(d, new_stop=D("98")),)))
    with pytest.raises(CoreContractError, match="UNDECLARED_TRAILING_STOP"):
        validate_core_result(replace(CORE.manifest, setups=(
            SetupSpec("fixture_long_case", "No management"),
            CORE.manifest.setups[1],)), pos_event, out)


def test_short_setup_has_no_trailing_stop():
    e = event_for("short")
    p = PositionSnapshot("pos_short", "fixture_short_case", Direction.SHORT,
                         D("94"), D("101"), D("101"), 0)
    candles = (e.candles[0], candle(e.observed_at, 94, 96, 86, 88))
    pos_event = replace(e, event=CoreEventType.POSITION_UPDATE,
                        observed_at=candles[-1].close_at, candles=candles, position=p)
    d, = OfflineCoreHarness(CORE, enabled=True).evaluate(pos_event).decisions
    assert d.kind is DecisionKind.NO_SETUP


def test_mismatched_position_revision_refused():
    e = event_for()
    p = PositionSnapshot("position_1", "fixture_long_case", Direction.LONG,
                         D("106"), D("99"), D("99"), 2)
    candles = (e.candles[0], candle(e.observed_at, 105, 115, 104, 114))
    pos = replace(e, event=CoreEventType.POSITION_UPDATE,
                  observed_at=candles[-1].close_at, candles=candles, position=p)
    out = result_for(pos)
    with pytest.raises(CoreContractError, match="STALE_OR_CROSS_POSITION"):
        validate_core_result(CORE.manifest, pos, replace(out,
            decisions=(replace(out.decisions[0], expected_position_revision=1),)))


def test_exit_and_cancel_contract():
    e = event_for()
    p = PositionSnapshot("pos_one", "fixture_long_case", Direction.LONG,
                         D("106"), D("99"), D("99"), 1)
    candles = (e.candles[0], candle(e.observed_at, 105, 115, 104, 114))
    pos = replace(e, event=CoreEventType.POSITION_UPDATE,
                  observed_at=candles[-1].close_at, candles=candles, position=p)
    out = result_for(pos)
    close = CoreDecision("close_x", DecisionKind.EXIT_INTENT,
                         "fixture_long_case", action=ExitAction.CLOSE_POSITION,
                         position_id="pos_one", expected_position_revision=1)
    validate_core_result(CORE.manifest, pos, replace(out, decisions=(close,)))
    cancel = CoreDecision("cancel_x", DecisionKind.EXIT_INTENT,
                         "fixture_long_case", action=ExitAction.CANCEL_PENDING_ENTRY,
                         pending_entry_id="pending_1")
    validate_core_result(CORE.manifest, e, replace(result_for(e), decisions=(cancel,)))


def test_bad_core_quarantined_without_signal():
    class BadCore:
        manifest = CORE.manifest
        def evaluate(self, event):
            return replace(CORE.evaluate(event), input_digest="0"*64)
    e = event_for()
    host = OfflineCoreHarness(BadCore(), enabled=True)
    with pytest.raises(CoreContractError, match="CORE_QUARANTINED"):
        host.evaluate(e)
    assert "binding_one" in host.quarantined_bindings
    with pytest.raises(CoreContractError, match="BINDING_QUARANTINED"):
        host.evaluate(e)


def test_no_signal_can_not_be_converted_to_legacy():
    e = event_for("none")
    out = result_for(e)
    with pytest.raises(CoreContractError, match="PAPER_ENTRY_ONLY"):
        to_legacy_paper_intent(CORE.manifest, e, out, out.decisions[0])


def test_live_cannot_enter_offline_event_contract():
    e = event_for()
    with pytest.raises(CoreContractError, match="UNVERIFIED_ORIGIN"):
        replace(e, origin="live_provider")
    with pytest.raises(CoreContractError, match="INVALID_TICK_EVENT"):
        replace(e, event=CoreEventType.QUOTE_TICK, candles=())
    tick = BidAskTick(e.observed_at, D("100"), D("100.1"))
    tick_e = replace(e, event=CoreEventType.QUOTE_TICK, candles=(), tick=tick)
    original = result_for(e)
    validate_core_result(replace(CORE.manifest, accepted_events=frozenset({CoreEventType.QUOTE_TICK})),
                         tick_e, replace(original, input_digest=tick_e.input_digest))
