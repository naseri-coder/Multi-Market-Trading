"""Pure, offline safety tests for the new, public multi-market platform boundary."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from naseri_markets import (
    ChannelRoute, Direction, EngineDescriptor, EngineRegistry, EvidenceMode,
    Instrument, Market, SignalIntent, decide_delivery,
)


def instrument(market=Market.INDEX):
    return Instrument(market, "wm-demo", "US30", "America/New_York", "USD")


def signal(direction=Direction.LONG, market=Market.INDEX):
    return SignalIntent(
        "nyfr-20261009-1", "nyfr", "0.1.0", instrument(market),
        direction, datetime(2026, 10, 9, 13, 31, tzinfo=timezone.utc),
        Decimal("43000"), Decimal("42970"), (Decimal("43060"),),
        EvidenceMode.FORWARD,
    )


def registry():
    r = EngineRegistry()
    r.register(EngineDescriptor("nyfr", "0.1.0", frozenset({Market.INDEX})))
    return r


def valid_route():
    return ChannelRoute("nyfr", Market.INDEX, -1001234567890, True, True, True)


def test_registry_separates_engines_and_markets():
    r = registry()
    r.register(EngineDescriptor("brooks", "3.0", frozenset({Market.CRYPTO})))
    assert [e.engine_id for e in r.engines_for(Market.CRYPTO)] == ["brooks"]
    assert [e.engine_id for e in r.engines_for(Market.INDEX)] == ["nyfr"]


def test_duplicate_engine_is_rejected():
    r = registry()
    with pytest.raises(ValueError, match="duplicate"):
        r.register(EngineDescriptor("nyfr", "0.1.0", frozenset({Market.INDEX})))


@pytest.mark.parametrize("engine_id", ["", "a", "../secret", "space id"])
def test_bad_engine_identity_rejected(engine_id):
    with pytest.raises(ValueError):
        EngineDescriptor(engine_id, "0.1", frozenset({Market.INDEX}))


def test_unregistered_and_wrong_market_rejected():
    r = registry()
    with pytest.raises(ValueError, match="market"):
        r.validate_intent(signal(market=Market.FOREX))
    with pytest.raises(ValueError, match="version"):
        r.validate_intent(replace(signal(), engine_version="0.2.0"))


def test_invalid_market_timezone_rejected():
    with pytest.raises(ValueError):
        instrument("unknown")
    with pytest.raises(ValueError):
        replace(instrument(), timezone="This/DoesNotExist")


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone aware"):
        replace(signal(), observed_at=datetime(2026, 10, 9))


def test_invalid_long_geometry_rejected():
    with pytest.raises(ValueError):
        replace(signal(), stop=Decimal("43010"))


def test_invalid_short_geometry_rejected():
    with pytest.raises(ValueError):
        replace(signal(direction=Direction.SHORT), stop=Decimal("42970"))


def test_invalid_price_type_rejected():
    with pytest.raises(ValueError):
        replace(signal(), entry=43000.0)


def test_registry_does_not_send_or_execute():
    assert not hasattr(registry(), "send_message")
    assert not hasattr(registry(), "place_order")


def test_delivery_defaults_to_disabled():
    decision = decide_delivery(signal(), registry(), ChannelRoute("nyfr", Market.INDEX))
    assert not decision.allowed and decision.reason == "ROUTE_DISABLED"


def test_delivery_requires_verified_channel_and_feed():
    for route in (
        replace(valid_route(), channel_verified_private=False),
        replace(valid_route(), realtime_feed_verified=False),
        replace(valid_route(), private_channel_id=123),
        replace(valid_route(), private_channel_id=None),
    ):
        assert not decide_delivery(signal(), registry(), route).allowed


def test_historical_cannot_publish_as_forward():
    intent = replace(signal(), evidence_mode=EvidenceMode.HISTORICAL)
    assert decide_delivery(intent, registry(), valid_route()).reason == "NOT_FORWARD_OBSERVATION"


def test_route_cross_engine_and_market_blocked():
    for route in (
        replace(valid_route(), engine_id="brooks"),
        replace(valid_route(), market=Market.CRYPTO),
    ):
        assert decide_delivery(signal(), registry(), route).reason == "ROUTE_IDENTITY_MISMATCH"


def test_explicitly_verified_forward_can_route_without_sending():
    decision = decide_delivery(signal(), registry(), valid_route())
    assert decision.allowed and decision.channel_id == -1001234567890
