"""Stage 7: deterministic OFFLINE fan-out, controlled activation and isolation."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle, CoreBinding, CoreDecision, CoreEventType, CoreResult,
    DataOrigin, DecisionKind, OfflineCoreHarness,
)
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, MarketPacket, OfflineMarketDataEngine, PacketStatus,
    PriceBasis, VolumeSemantics,
)
from naseri_markets.strategy_orchestrator_v1 import (
    EvaluationStatus, OfflineStrategyOrchestrator, OrchestrationRefused,
    TrustedCoreEvaluator, IsolatedCoreEvaluator,
)
from naseri_markets.secure_plugin_runtime_v1 import (
    SecureOfflineCoreHost, SecurePluginPolicy,
)

T0 = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)
CORE = OfflineContractFixture()


def lane(feed_id="crypto_feed", market=Market.CRYPTO, provider="fake_crypto_venue",
         symbol="ALPHAUSD", timeframe="15m"):
    instrument = Instrument(market, provider, symbol, "UTC", "USD")
    return FeedDefinition(feed_id, instrument, timeframe, CoreEventType.CLOSED_CANDLE,
                          DataOrigin.REPLAY, "offline_fixture", PriceBasis.TRADE
                          if market is Market.CRYPTO else PriceBasis.BID,
                          VolumeSemantics.TRADED if market is Market.CRYPTO
                          else VolumeSemantics.TICK_COUNT)


def packet(feed, sequence=1, *, earlier=0, close="100", high="102", low="98"):
    mins = {"5m": 5, "15m": 15, "1h": 60}[feed.timeframe]
    start = T0 + timedelta(minutes=mins * earlier)
    bar = ClosedCandle(start, start + timedelta(minutes=mins), D("100"), D(high),
                       D(low), D(close), D("5"))
    return MarketPacket(feed.feed_id, sequence, bar.close_at + timedelta(seconds=2),
                        feed.source_ref, candle=bar)


def trusted():
    return TrustedCoreEvaluator(OfflineCoreHarness(CORE, enabled=True), CORE.manifest)


def manager(*feeds):
    data = OfflineMarketDataEngine(enabled=True)
    for feed in feeds:
        data.register_feed(feed)
    return OfflineStrategyOrchestrator(data, enabled=True)


def attach(o, feed, *, binding_id="binding_a", instance_id="instance_a",
           evaluator=None):
    binding = CoreBinding(instance_id, binding_id, feed.instrument, feed.timeframe)
    return o.attach(feed.feed_id, CORE.manifest, binding, evaluator or trusted())


def enable(o, binding_id, *, enabled=True):
    return o.set_enabled(binding_id, enabled=enabled,
                         expected_revision=o.state(binding_id).revision, operator_ack=True)


def evaluate_two(o, feed, *, start=1):
    first = o.ingest(packet(feed, start))
    second = o.ingest(packet(feed, start + 1, earlier=1, high="108", low="99", close="106"))
    return first, second


def test_disabled_by_default_and_no_implicit_signals():
    f = lane(); data = OfflineMarketDataEngine(enabled=True); data.register_feed(f)
    o = OfflineStrategyOrchestrator(data)
    attach(o, f)
    with pytest.raises(OrchestrationRefused, match="DISABLED"):
        o.ingest(packet(f))
    assert o.state("binding_a").revision == 1
    assert o.state("binding_a").completed_events == 0


def test_defaults_disabled_and_operator_only_toggle():
    f = lane(); o = manager(f); state = attach(o, f)
    assert not state.enabled and state.revision == 1
    with pytest.raises(OrchestrationRefused, match="EXPLICIT_OPERATOR"):
        o.set_enabled("binding_a", enabled=True, expected_revision=1)
    with pytest.raises(OrchestrationRefused, match="STALE_BINDING"):
        o.set_enabled("binding_a", enabled=True, expected_revision=5, operator_ack=True)
    assert enable(o, "binding_a").enabled
    assert enable(o, "binding_a", enabled=False).revision == 3
    assert not o.state("binding_a").enabled


def test_same_feed_two_bindings_and_one_core_produce_unique_identities():
    f = lane(); o = manager(f)
    attach(o, f, binding_id="binding_a", instance_id="account_a")
    attach(o, f, binding_id="binding_b", instance_id="account_b")
    enable(o, "binding_a"); enable(o, "binding_b")
    first, second = evaluate_two(o, f)
    assert first.packet_status is PacketStatus.WARMING
    assert first.waiting_bindings == ("binding_a", "binding_b")
    assert len(second.outcomes) == 2
    assert all(x.status is EvaluationStatus.EVALUATED for x in second.outcomes)
    assert second.outcomes[0].result.input_digest != second.outcomes[1].result.input_digest
    assert second.outcomes[0].actionable_decisions != second.outcomes[1].actionable_decisions
    assert o.state("binding_a").completed_events == o.state("binding_b").completed_events == 1
    assert not second.telegram_sent and not second.broker_order_sent


def test_independent_bindings_three_instruments_two_markets_and_timeframes():
    crypto = lane(); other = lane("crypto_b", symbol="BETAUSD", timeframe="5m")
    forex = lane("forex_a", Market.FOREX, "simulated_fx", "EURUSD", "1h")
    o = manager(crypto, other, forex)
    for f, ident in ((crypto, "aa"), (other, "bb"), (forex, "cc")):
        attach(o, f, binding_id=ident, instance_id="same_strategy")
        enable(o, ident)
    for f in (crypto, other, forex):
        _, outcome = evaluate_two(o, f)
        assert outcome.outcomes[0].status is EvaluationStatus.EVALUATED
    assert o.state("aa").feed_id == "crypto_feed"
    assert o.state("bb").feed_id == "crypto_b"
    assert o.state("cc").feed_id == "forex_a"
    assert o.state("cc").completed_events == 1


def test_disabled_binding_cannot_evaluate_but_other_works():
    f = lane(); o = manager(f)
    attach(o, f, binding_id="aa")
    attach(o, f, binding_id="bb")
    enable(o, "aa")
    _, receipt = evaluate_two(o, f)
    outcomes = {v.binding_id: v for v in receipt.outcomes}
    assert outcomes["aa"].status is EvaluationStatus.EVALUATED
    assert outcomes["bb"].status is EvaluationStatus.DISABLED
    assert outcomes["bb"].result is None
    assert o.state("bb").last_input_digest is None


def test_toggle_mid_feed_skips_old_history_and_only_future_event():
    f = lane(); o = manager(f); attach(o, f)
    evaluate_two(o, f)
    assert o.state("binding_a").completed_events == 0
    enable(o, "binding_a")
    next_one = o.ingest(packet(f, 3, earlier=2, close="100", high="102"))
    assert next_one.outcomes[0].status is EvaluationStatus.EVALUATED
    assert o.state("binding_a").completed_events == 1


def test_exact_replay_packet_suppressed_before_core_evaluation():
    f = lane(); o = manager(f); attach(o, f); enable(o, "binding_a")
    first, second = evaluate_two(o, f)
    again = o.ingest(packet(f, 2, earlier=1, high="108", low="99", close="106"))
    assert again.packet_status is PacketStatus.DUPLICATE
    assert again.outcomes == ()
    assert o.state("binding_a").completed_events == 1


def test_faulty_core_binding_quarantined_other_binding_still_evaluates():
    f = lane(); o = manager(f)

    class BadCore:
        manifest = CORE.manifest
        def evaluate(self, event):
            raise RuntimeError("a secret from bad source")

    bad = TrustedCoreEvaluator(OfflineCoreHarness(BadCore(), enabled=True), CORE.manifest)
    attach(o, f, binding_id="bad", evaluator=bad)
    attach(o, f, binding_id="good")
    enable(o, "bad"); enable(o, "good")
    _, receipt = evaluate_two(o, f)
    got = {x.binding_id: x for x in receipt.outcomes}
    assert got["bad"].status is EvaluationStatus.QUARANTINED
    assert got["bad"].result is None
    assert got["good"].status is EvaluationStatus.EVALUATED
    bad_state = o.state("bad")
    assert bad_state.quarantined and not bad_state.enabled
    assert bad_state.refused_events == 1
    assert "secret" not in bad_state.last_error_code
    assert not o.market_data.state(f.feed_id).quarantined
    with pytest.raises(OrchestrationRefused, match="QUARANTINED_BINDING"):
        enable(o, "bad")
    later = o.ingest(packet(f, 3, earlier=2))
    assert {x.binding_id:x.status for x in later.outcomes}["bad"] is EvaluationStatus.QUARANTINED
    assert o.state("good").completed_events == 2


def test_duplicate_actionable_id_across_different_events_quarantined():
    f = lane(); o = manager(f)

    class BadIdCore:
        manifest = CORE.manifest
        def evaluate(self, event):
            base = CORE.evaluate(event)
            d, = base.decisions
            if d.kind is DecisionKind.ENTRY_INTENT:
                d = replace(d, decision_id="STATIC_ACTION_ID")
            return replace(base, decisions=(d,))

    attach(o, f, evaluator=TrustedCoreEvaluator(OfflineCoreHarness(BadIdCore(), enabled=True), CORE.manifest))
    enable(o, "binding_a")
    _, first = evaluate_two(o, f)
    assert first.outcomes[0].status is EvaluationStatus.EVALUATED
    more = o.ingest(packet(f, 3, earlier=2, high="112", low="99", close="110"))
    assert more.outcomes[0].status is EvaluationStatus.QUARANTINED
    assert o.state("binding_a").refused_events == 1


def test_invalid_result_cross_binding_quarantined():
    f = lane(); o = manager(f)

    class BadIdentity:
        manifest = CORE.manifest
        def evaluate(self, event):
            return replace(CORE.evaluate(event), binding_id="someone_else")

    attach(o, f, evaluator=TrustedCoreEvaluator(OfflineCoreHarness(BadIdentity(), enabled=True), CORE.manifest))
    enable(o, "binding_a")
    _, r = evaluate_two(o, f)
    assert r.outcomes[0].status is EvaluationStatus.QUARANTINED
    assert o.state("binding_a").last_error_code == "EVALUATION_OR_RESULT_REJECTED"


def test_invalid_feed_quarantines_only_its_lane():
    f = lane(); other = lane("other", symbol="OTHERUSD"); o = manager(f, other)
    attach(o, f, binding_id="first"); attach(o, other, binding_id="second")
    enable(o, "first"); enable(o, "second")
    o.ingest(packet(f))
    with pytest.raises(OrchestrationRefused, match="MARKET_DATA_REFUSED"):
        o.ingest(packet(f, 3, earlier=1))
    assert o.market_data.state(f.feed_id).quarantined
    assert not o.market_data.state(other.feed_id).quarantined
    _, r = evaluate_two(o, other)
    assert r.outcomes[0].status is EvaluationStatus.EVALUATED


def test_binding_revision_and_no_implicit_recover():
    f = lane(); o = manager(f)
    attach(o, f)
    with pytest.raises(OrchestrationRefused, match="STALE"):
        o.set_enabled("binding_a", enabled=True, expected_revision=0, operator_ack=True)
    assert o.state("binding_a").revision == 1
    enable(o, "binding_a")
    assert o.state("binding_a").revision == 2


def test_reject_duplicate_bindings_and_cap():
    f = lane(); o = OfflineStrategyOrchestrator(OfflineMarketDataEngine(enabled=True),
                                               enabled=True, max_bindings=1)
    o.market_data.register_feed(f)
    attach(o, f)
    with pytest.raises(OrchestrationRefused, match="QUOTA"):
        attach(o, f, binding_id="bb")


def test_reject_mismatched_manifest_and_feed_binding():
    f = lane(); o = manager(f)
    wrong = CoreBinding("ii", "wrong", Instrument(Market.FOREX, "wrong_provider",
                        "EURUSD", "UTC", "USD"), "15m")
    with pytest.raises(OrchestrationRefused, match="FEED_BINDING_REJECTED"):
        o.attach(f.feed_id, CORE.manifest, wrong, trusted())
    with pytest.raises(OrchestrationRefused, match="UNKNOWN_BINDING"):
        o.state("wrong")


def test_invalid_raw_evaluator_refused():
    f = lane(); o = manager(f)
    with pytest.raises(OrchestrationRefused, match="INVALID_EVALUATOR"):
        o.attach(f.feed_id, CORE.manifest,
                 CoreBinding("ii", "bind", f.instrument, "15m"), CORE)


def test_secure_adapter_requires_explicit_enabled_host():
    with pytest.raises(OrchestrationRefused, match="ISOLATED_EVALUATOR_NOT_READY"):
        IsolatedCoreEvaluator(SecureOfflineCoreHost(SecurePluginPolicy()),
                              CORE.manifest, b"print(123)", "0" * 64)


def test_trusted_core_adapter_refuses_disabled_harness():
    with pytest.raises(OrchestrationRefused, match="TRUSTED_EVALUATOR_NOT_READY"):
        TrustedCoreEvaluator(OfflineCoreHarness(CORE), CORE.manifest)


def test_data_consumption_does_not_grant_trading_permissions():
    f = lane(); o = manager(f); state = attach(o, f)
    assert not state.telegram_enabled and not state.broker_orders_enabled
    enable(o, "binding_a")
    _, r = evaluate_two(o, f)
    assert len(r.outcomes[0].actionable_decisions) == 1
    assert not r.telegram_sent and not r.broker_order_sent
    state = o.state("binding_a")
    assert not state.telegram_enabled and not state.broker_orders_enabled


def test_market_data_requires_enabled_even_if_orchestrator_enabled():
    f = lane(); engine = OfflineMarketDataEngine()
    engine.register_feed(f)
    o = OfflineStrategyOrchestrator(engine, enabled=True)
    attach(o, f); enable(o, "binding_a")
    with pytest.raises(OrchestrationRefused, match="MARKET_DATA_REFUSED"):
        o.ingest(packet(f))


def test_unregistered_market_feed_rejected_without_mutating_binding():
    o = OfflineStrategyOrchestrator(OfflineMarketDataEngine(enabled=True), enabled=True)
    with pytest.raises(OrchestrationRefused, match="FEED_BINDING_REJECTED"):
        attach(o, lane())
    with pytest.raises(OrchestrationRefused, match="UNKNOWN_BINDING"):
        o.state("binding_a")


def test_quote_tick_feed_replay_works_if_core_declares_tick():
    from naseri_markets.core_api_v1 import CoreManifest, SetupSpec
    from naseri_markets.core_api_v1 import BidAskTick
    f = FeedDefinition("tick_feed", lane().instrument, "15m", CoreEventType.QUOTE_TICK,
                       DataOrigin.REPLAY, "offline_fixture", PriceBasis.BID_ASK)
    m = CoreManifest("quote_core", "1", (SetupSpec("tick", "tick"),),
                     frozenset({Market.CRYPTO}), frozenset({CoreEventType.QUOTE_TICK}))
    class TickCore:
        manifest=m
        def evaluate(self, event):
            return CoreResult(m.core_id,m.core_version,event.binding.instance_id,
                              event.binding.binding_id,event.observed_at,event.input_digest,
                              (CoreDecision("tick_no_signal",DecisionKind.NO_SETUP),))
    o = manager(f)
    b = CoreBinding("account_x", "bind_tick", f.instrument, "15m")
    o.attach(f.feed_id,m,b,TrustedCoreEvaluator(OfflineCoreHarness(TickCore(),enabled=True),m))
    enable(o,"bind_tick")
    r = o.ingest(MarketPacket("tick_feed",1,T0+timedelta(seconds=1),"offline_fixture",
                  tick=BidAskTick(T0,D("99"),D("100"))))
    assert r.outcomes[0].status is EvaluationStatus.EVALUATED
    assert r.outcomes[0].result.decisions[0].kind is DecisionKind.NO_SETUP


def test_same_timestamp_different_ticks_allowed_and_not_idempotent():
    from naseri_markets.core_api_v1 import CoreManifest, SetupSpec, BidAskTick
    f = FeedDefinition("tick_feed", lane().instrument, "15m", CoreEventType.QUOTE_TICK,
                       DataOrigin.REPLAY,"offline_fixture", PriceBasis.BID_ASK)
    m = CoreManifest("tickcore","1",(SetupSpec("one","one"),),
                     frozenset({Market.CRYPTO}),frozenset({CoreEventType.QUOTE_TICK}))
    class TickCore:
        manifest=m
        def evaluate(self,e):
            return CoreResult(m.core_id,m.core_version,e.binding.instance_id,e.binding.binding_id,
                              e.observed_at,e.input_digest,(CoreDecision("no",DecisionKind.NO_SETUP),))
    o=manager(f)
    o.attach(f.feed_id,m,CoreBinding("inst","tick_binding",f.instrument,"15m"),
             TrustedCoreEvaluator(OfflineCoreHarness(TickCore(),enabled=True),m))
    enable(o,"tick_binding")
    for n,bid in ((1,"99"),(2,"98")):
        r=o.ingest(MarketPacket("tick_feed",n,T0+timedelta(seconds=n),"offline_fixture",
                         tick=BidAskTick(T0,D(bid),D("100"))))
        assert r.outcomes[0].status is EvaluationStatus.EVALUATED
    assert o.state("tick_binding").completed_events == 2


@pytest.mark.parametrize("bad_value", [0,-1,True,1.2,"2"])
def test_invalid_binding_quota(bad_value):
    with pytest.raises(OrchestrationRefused):
        OfflineStrategyOrchestrator(OfflineMarketDataEngine(),max_bindings=bad_value)


def test_distinct_cores_share_same_feed_without_cross_strategy_identity():
    from naseri_markets.core_api_v1 import CoreManifest
    f = lane(); o = manager(f)
    alternate = replace(CORE.manifest, core_id="another.strategy")

    class OtherCore:
        manifest = alternate
        def evaluate(self, event):
            original = CORE.evaluate(event)
            return replace(original, core_id=alternate.core_id,
                           decisions=tuple(replace(d, decision_id="other_" + d.decision_id)
                                           for d in original.decisions))

    attach(o, f, binding_id="binding_original")
    o.attach(f.feed_id,alternate,CoreBinding("instance_other","binding_other",
                                           f.instrument,f.timeframe),
             TrustedCoreEvaluator(OfflineCoreHarness(OtherCore(), enabled=True),alternate))
    enable(o,"binding_original"); enable(o,"binding_other")
    _, receipt=evaluate_two(o,f)
    assert {v.result.core_id for v in receipt.outcomes} == {
        CORE.manifest.core_id, alternate.core_id}
    assert all(x.status is EvaluationStatus.EVALUATED for x in receipt.outcomes)
    assert not receipt.telegram_sent and not receipt.broker_order_sent


def test_restart_like_feed_reset_does_not_reemit_same_input():
    f=lane(); o=manager(f)
    attach(o,f); enable(o,"binding_a")
    evaluate_two(o,f)
    assert o.state("binding_a").completed_events==1
    o.market_data.reset_feed(f.feed_id,operator_ack=True)
    old=o.ingest(packet(f,1))
    assert old.packet_status is PacketStatus.WARMING
    repeated=o.ingest(packet(f,2,earlier=1,high="108",low="99",close="106"))
    assert repeated.outcomes[0].status is EvaluationStatus.DUPLICATE
    assert repeated.outcomes[0].result is None
    assert o.state("binding_a").completed_events==1
    assert o.ingest(packet(f,3,earlier=2)).outcomes[0].status is EvaluationStatus.EVALUATED


def test_no_indefinite_retry_of_quarantined_bad_core():
    f=lane(); o=manager(f)

    class Broken:
        manifest=CORE.manifest
        calls=0
        def evaluate(self,event):
            self.calls+=1
            raise ValueError("bad")

    bad=Broken()
    attach(o,f,evaluator=TrustedCoreEvaluator(OfflineCoreHarness(bad,enabled=True),CORE.manifest))
    enable(o,"binding_a")
    evaluate_two(o,f)
    for n in range(3,8):
        r=o.ingest(packet(f,n,earlier=n-1))
        assert r.outcomes[0].status is EvaluationStatus.QUARANTINED
    assert bad.calls==1
    assert o.state("binding_a").refused_events==1


def test_binding_level_duplicate_does_not_mask_market_stream_gap():
    f=lane(); o=manager(f); attach(o,f); enable(o,"binding_a")
    evaluate_two(o,f)
    with pytest.raises(OrchestrationRefused,match="MARKET_DATA_REFUSED"):
        o.ingest(packet(f,4,earlier=3))
    assert o.market_data.state(f.feed_id).quarantined
    assert o.state("binding_a").completed_events==1
