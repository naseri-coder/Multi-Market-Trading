"""Stage 5 offline market data engine deterministic and fail-closed acceptance."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    CoreBinding, CoreEventType, DataOrigin, DecisionKind, OfflineCoreHarness,
)
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, MarketDataRefused, MarketPacket, OfflineMarketDataEngine,
    PacketStatus, PriceBasis, VolumeSemantics,
)
from naseri_markets.market_data_normalizers_v1 import (
    normalize_bidask_tick, normalize_crypto_bar, normalize_forex_bar,
)

BASE = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)
CORE = OfflineContractFixture()


def spec(market=Market.CRYPTO, provider='fixture_venue', symbol='ALPHAUSD',
         feed_id='feed_alpha', timeframe='15m', event=CoreEventType.CLOSED_CANDLE,
         origin=DataOrigin.REPLAY):
    return FeedDefinition(
        feed_id=feed_id, instrument=Instrument(market, provider, symbol, 'UTC', 'USD'),
        timeframe=timeframe, event=event, origin=origin, source_ref='offline_fixture_1',
        price_basis=(PriceBasis.BID_ASK if event is CoreEventType.QUOTE_TICK
                     else PriceBasis.TRADE if market is Market.CRYPTO else PriceBasis.BID),
        volume_semantics=(VolumeSemantics.TRADED if market is Market.CRYPTO
                          else VolumeSemantics.TICK_COUNT) if event is CoreEventType.CLOSED_CANDLE
                         else VolumeSemantics.UNKNOWN,
    )


def crypto_raw(t, *, low='98', high='102', close='100'):
    return dict(open_at=t.isoformat(), close_at=(t + timedelta(minutes=15)).isoformat(),
                open='100', high=high, low=low, close=close, volume='10')


def fx_raw(t):
    return dict(open_at=t.isoformat(), close_at=(t + timedelta(minutes=15)).isoformat(),
                open='1.0800', high='1.0850', low='1.0790', close='1.0820', tick_volume=72)


def packet(s, n, t, *, high='102', low='98', close='100'):
    if s.instrument.market is Market.CRYPTO:
        candle = normalize_crypto_bar(s, crypto_raw(t, high=high, low=low, close=close))
    else:
        candle = normalize_forex_bar(s, fx_raw(t))
    return MarketPacket(s.feed_id, n, candle.close_at + timedelta(seconds=2),
                        s.source_ref, candle=candle)


def subscribed(s=None, *, two=False):
    s = s or spec()
    engine = OfflineMarketDataEngine(enabled=True)
    engine.register_feed(s)
    b = CoreBinding('instance_one', 'binding_one', s.instrument, s.timeframe)
    engine.subscribe(s.feed_id, CORE.manifest, b)
    if two:
        b2 = CoreBinding('instance_two', 'binding_two', s.instrument, s.timeframe)
        engine.subscribe(s.feed_id, CORE.manifest, b2)
    return engine


def test_disabled_by_default_and_no_implicit_network():
    s = spec()
    engine = OfflineMarketDataEngine()
    engine.register_feed(s)
    with pytest.raises(MarketDataRefused, match='DISABLED'):
        engine.ingest(packet(s, 1, BASE))
    assert engine.state(s.feed_id).last_sequence is None


def test_crypto_two_bindings_single_feed_and_actual_stage3_evaluation():
    s = spec()
    engine = subscribed(s, two=True)
    one = engine.ingest(packet(s, 1, BASE))
    assert one.status is PacketStatus.WARMING
    assert one.deliveries == ()
    assert one.waiting_bindings == ('binding_one', 'binding_two')
    two = engine.ingest(packet(s, 2, BASE + timedelta(minutes=15), high='108', low='99', close='106'))
    assert two.status is PacketStatus.ACCEPTED
    assert len(two.deliveries) == 2
    assert {v.binding_id for v in two.deliveries} == {'binding_one', 'binding_two'}
    assert {v.event.input_digest for v in two.deliveries}.__len__() == 2
    assert all(v.event.binding.instrument.provider == 'fixture_venue' for v in two.deliveries)
    # Strategy execution is a separate, explicit, trusted OFFLINE action.
    result = OfflineCoreHarness(CORE, enabled=True).evaluate(two.deliveries[0].event)
    assert result.decisions[0].kind is DecisionKind.ENTRY_INTENT
    assert result.decisions[0].entry == D('106')
    assert engine.state(s.feed_id).subscriptions == 2


def test_same_core_on_separately_selected_forex_broker_without_core_changes():
    s = spec(Market.FOREX, 'demo_broker', 'EURUSD', 'fx_feed')
    engine = subscribed(s)
    assert engine.ingest(packet(s, 41, BASE)).status is PacketStatus.WARMING
    result = engine.ingest(packet(s, 42, BASE + timedelta(minutes=15)))
    assert len(result.deliveries) == 1
    assert result.deliveries[0].event.binding.instrument.provider == 'demo_broker'
    assert result.deliveries[0].event.origin is DataOrigin.REPLAY
    assert result.deliveries[0].event.candles[-1].volume == D(72)
    assert result.deliveries[0].volume_semantics is VolumeSemantics.TICK_COUNT
    assert result.deliveries[0].price_basis is PriceBasis.BID


def test_repeat_same_packet_is_idempotent():
    s = spec(); e = subscribed(s)
    p = packet(s, 1, BASE)
    e.ingest(p)
    result = e.ingest(p)
    assert result.status is PacketStatus.DUPLICATE
    assert result.deliveries == ()
    assert e.state(s.feed_id).retained_bars == 1


@pytest.mark.parametrize('case,pattern', [
    ('sequence_gap', 'SEQUENCE_GAP'),
    ('sequence_rollback', 'SEQUENCE_GAP'),
    ('candle_gap', 'CANDLE_GAP'),
    ('candle_overlap', 'CANDLE_GAP'),
    ('source_change', 'SOURCE_IDENTITY'),
    ('future_receipt', 'LATE_OR_FUTURE'),
    ('late_receipt', 'LATE_OR_FUTURE'),
    ('conflicting_duplicate', 'CONFLICTING_DUPLICATE'),
    ('timeframe_mismatch', 'CANDLE_TIMEFRAME'),
])
def test_quarantine_invalid_packet_and_never_dispatch(case, pattern):
    s = spec(); e = subscribed(s)
    first = packet(s, 2 if case == 'sequence_rollback' else 1, BASE)
    e.ingest(first)
    incoming = packet(s, 2, BASE + timedelta(minutes=15))
    if case == 'sequence_gap':
        incoming = packet(s, 4, BASE + timedelta(minutes=15))
    elif case == 'sequence_rollback':
        incoming = packet(s, 1, BASE + timedelta(minutes=15))
    elif case == 'candle_gap':
        incoming = packet(s, 2, BASE + timedelta(minutes=30))
    elif case == 'candle_overlap':
        incoming = packet(s, 2, BASE + timedelta(minutes=10))
    elif case == 'source_change':
        incoming = MarketPacket(s.feed_id, 2, incoming.received_at, 'different_source', candle=incoming.candle)
    elif case == 'future_receipt':
        incoming = MarketPacket(s.feed_id, 2, incoming.observed_at-timedelta(seconds=1),
                                s.source_ref, candle=incoming.candle)
    elif case == 'late_receipt':
        incoming = MarketPacket(s.feed_id, 2, incoming.observed_at+timedelta(seconds=121),
                                s.source_ref, candle=incoming.candle)
    elif case == 'conflicting_duplicate':
        incoming = packet(s, 1, BASE, close='101')
    elif case == 'timeframe_mismatch':
        from naseri_markets.core_api_v1 import ClosedCandle
        old = incoming.candle
        malformed = ClosedCandle(old.open_at, old.close_at-timedelta(minutes=1),
                                 old.open, old.high, old.low, old.close, old.volume)
        incoming = MarketPacket(s.feed_id, 2, malformed.close_at+timedelta(seconds=1),
                                s.source_ref, candle=malformed)
    with pytest.raises(MarketDataRefused, match=pattern):
        e.ingest(incoming)
    assert e.state(s.feed_id).quarantined
    assert e.state(s.feed_id).last_sequence == (2 if case == 'sequence_rollback' else 1)
    with pytest.raises(MarketDataRefused, match='QUARANTINED'):
        e.ingest(packet(s, 2, BASE+timedelta(minutes=15)))


def test_feed_failure_isolation_and_reset_ack():
    s1 = spec(); s2 = spec(feed_id='feed_beta', symbol='BETAUSD')
    e = OfflineMarketDataEngine(enabled=True)
    e.register_feed(s1); e.register_feed(s2)
    e.ingest(packet(s1, 1, BASE))
    with pytest.raises(MarketDataRefused):
        e.ingest(packet(s1, 3, BASE+timedelta(minutes=15)))
    assert e.ingest(packet(s2, 10, BASE)).status is PacketStatus.ACCEPTED
    with pytest.raises(MarketDataRefused, match='RESYNC'):
        e.reset_feed('feed_alpha')
    e.reset_feed('feed_alpha', operator_ack=True)
    assert e.state('feed_alpha').last_sequence is None
    assert not e.state('feed_alpha').quarantined


def test_incompatible_binding_and_duplicate_cannot_leak_other_market():
    s = spec(); e = OfflineMarketDataEngine(enabled=True); e.register_feed(s)
    wrong = CoreBinding('user_a', 'same_binding',
                        spec(Market.FOREX, 'different_broker', 'EURUSD').instrument, '15m')
    with pytest.raises(MarketDataRefused, match='INCOMPATIBLE'):
        e.subscribe(s.feed_id, CORE.manifest, wrong)
    good = CoreBinding('user_a', 'same_binding', s.instrument, '15m')
    e.subscribe(s.feed_id, CORE.manifest, good)
    with pytest.raises(MarketDataRefused, match='DUPLICATE'):
        e.subscribe(s.feed_id, CORE.manifest, good)


def test_no_delivery_until_minimum_candles():
    s = spec(); e = subscribed(s)
    r = e.ingest(packet(s, 7, BASE))
    assert r.deliveries == ()
    assert r.waiting_bindings == ('binding_one',)
    assert e.ingest(packet(s, 8, BASE+timedelta(minutes=15))).deliveries


@pytest.mark.parametrize('value', [0, -1, True, 1.0, '1'])
def test_invalid_sequence(value):
    with pytest.raises(MarketDataRefused, match='SEQUENCE'):
        MarketPacket('feed', value, BASE, 'offline_fixture_1', candle=None,
                     tick=normalize_bidask_tick(
                         spec(event=CoreEventType.QUOTE_TICK),
                         dict(occurred_at=BASE.isoformat(), bid='100', ask='101')))


def test_normalizers_reject_ambiguous_fx_volume_and_floats():
    fx = spec(Market.FOREX, 'fx_broker', 'EURUSD', 'fx')
    raw = fx_raw(BASE)
    raw['tick_volume'] = '72'
    with pytest.raises(MarketDataRefused, match='TICK_COUNT'):
        normalize_forex_bar(fx, raw)
    c = spec()
    raw = crypto_raw(BASE)
    raw['volume'] = 10.0
    with pytest.raises(MarketDataRefused, match='DECIMAL_STRING'):
        normalize_crypto_bar(c, raw)
    raw = crypto_raw(BASE)
    raw['open_at'] = '2026-10-11T10:00:00'
    with pytest.raises(ValueError, match='TIMESTAMP'):
        normalize_crypto_bar(c, raw)


def test_tick_both_crypto_and_forex_normalization_and_routing():
    from naseri_markets.core_api_v1 import CoreManifest, SetupSpec
    for market, provider, symbol, feed in (
            (Market.CRYPTO, 'fixture_venue', 'BTCUSDT', 'ctick'),
            (Market.FOREX, 'fx_demo', 'EURUSD', 'ftick')):
        s = spec(market, provider, symbol, feed, event=CoreEventType.QUOTE_TICK)
        e = OfflineMarketDataEngine(enabled=True)
        e.register_feed(s)
        manifest = CoreManifest('tick_core','1.0.0',(SetupSpec('one','Sample'),),
                                frozenset({market}),frozenset({CoreEventType.QUOTE_TICK}))
        e.subscribe(feed, manifest, CoreBinding('inst_'+feed, 'bind_'+feed, s.instrument, '15m'))
        tick = normalize_bidask_tick(s, dict(occurred_at=BASE.isoformat(), bid='100',ask='101'))
        p = MarketPacket(feed, 1, BASE+timedelta(seconds=1),s.source_ref,tick=tick)
        got=e.ingest(p)
        assert got.deliveries[0].event.tick == tick
        assert got.deliveries[0].event.origin is DataOrigin.REPLAY


def test_empty_feed_no_signals_and_no_authorization_fields():
    s = spec(); e = OfflineMarketDataEngine(enabled=True); e.register_feed(s)
    r=e.ingest(packet(s, 1, BASE))
    assert r.deliveries == ()
    assert not hasattr(r, 'execute')
    assert not hasattr(r, 'publish')


def test_price_basis_required_and_no_traded_volume_illusion():
    s = spec(Market.FOREX, 'demo_broker', 'EURUSD', 'fx')
    with pytest.raises(MarketDataRefused, match='FOREX_FEED_CONTRACT'):
        normalize_forex_bar(FeedDefinition(
            'inert', s.instrument, '15m', CoreEventType.CLOSED_CANDLE,
            DataOrigin.REPLAY, 'offline_fixture_1', PriceBasis.TRADE,
            VolumeSemantics.TICK_COUNT), fx_raw(BASE))
    with pytest.raises(MarketDataRefused, match='INVALID_PRICE_BASIS_FOR_EVENT'):
        FeedDefinition('inert', s.instrument, '15m', CoreEventType.QUOTE_TICK,
                       DataOrigin.REPLAY, 'offline_fixture_1', PriceBasis.BID)


def test_rollback_receipt_time_quarantined():
    s = spec(); e = subscribed(s)
    first = packet(s, 1, BASE)
    e.ingest(first)
    later = packet(s, 2, BASE+timedelta(minutes=15))
    # Receipt time is between the first close and the second close? It must
    # not be earlier than the second observation, regardless of sequencing.
    fake = MarketPacket(s.feed_id, later.sequence,
                        first.received_at-timedelta(seconds=1), s.source_ref,
                        candle=later.candle)
    with pytest.raises(MarketDataRefused, match='LATE_OR_FUTURE'):
        e.ingest(fake)
    assert e.state(s.feed_id).quarantined


def test_no_live_origin_in_core_api_v1():
    s = spec()
    with pytest.raises(MarketDataRefused, match='OFFLINE_ORIGIN'):
        FeedDefinition(s.feed_id, s.instrument, s.timeframe, s.event,
                       'live', s.source_ref, PriceBasis.TRADE, VolumeSemantics.TRADED)


def test_history_limit_and_explicit_reload():
    s = FeedDefinition('tiny', spec().instrument, '15m', CoreEventType.CLOSED_CANDLE,
                       DataOrigin.SYNTHETIC, 'offline_fixture_1', PriceBasis.TRADE,
                       VolumeSemantics.TRADED, history_limit=2)
    e = subscribed(s)
    for n in range(1, 5):
        result = e.ingest(packet(s, n, BASE+timedelta(minutes=15*(n-1))))
        assert e.state(s.feed_id).retained_bars <= 2
        if n >= 2:
            assert len(result.deliveries[0].event.candles) == 2
    e.reset_feed(s.feed_id, operator_ack=True)
    assert e.state(s.feed_id).retained_bars == 0
    assert e.state(s.feed_id).last_sequence is None
