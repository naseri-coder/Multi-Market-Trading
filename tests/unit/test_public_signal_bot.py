"""Public bot tests use only fake providers, never Telegram or brokerage I/O."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from naseri_markets.contracts import (
    Direction, EngineDescriptor, EvidenceMode, Instrument, Market, SignalIntent,
)
from naseri_markets.delivery_ledger import SignalLedger
from naseri_markets.public_signal_bot import PublicSignalBot, format_signal
from naseri_markets.registry import EngineRegistry
from naseri_markets.routing import ChannelRoute

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=timezone.utc)


class FakeTelegram:
    def __init__(self, valid=True, throws=False):
        self.valid, self.throws = valid, throws
        self.send_count = 0
        self.last = None

    def verify_private_channel(self, channel_id):
        return self.valid

    def send_message(self, channel_id, body):
        self.send_count += 1
        self.last = (channel_id, body)
        if self.throws:
            raise OSError("synthetic network error")
        return 1234


def fixtures(tmp_path):
    r = EngineRegistry()
    r.register(EngineDescriptor("example_core", "1.0", frozenset({Market.FOREX})))
    instrument = Instrument(
        Market.FOREX, "mt5:example", "EURUSD", "America/New_York", "USD"
    )
    intent = SignalIntent(
        "example-1", "example_core", "1.0", instrument, Direction.LONG, NOW,
        Decimal("1.1000"), Decimal("1.0990"),
        (Decimal("1.1020"),), EvidenceMode.FORWARD,
    )
    route = ChannelRoute(
        "example_core", Market.FOREX, -1001112223334, True, True, True
    )
    return r, intent, route, tmp_path / "bot.db"


def test_bot_default_off_no_network(tmp_path):
    registry, intent, route, path = fixtures(tmp_path)
    ledger = SignalLedger(path)
    transport = FakeTelegram()
    result = PublicSignalBot(ledger, registry, transport).publish(
        intent, route, now=NOW, verified_live_feed=True
    )
    assert result.status == "BOT_DISABLED" and transport.send_count == 0
    assert ledger.get(intent.engine_id, intent.signal_id) is None
    ledger.close()


def test_publish_once_and_persistent_restart(tmp_path):
    registry, intent, route, path = fixtures(tmp_path)
    ledger = SignalLedger(path)
    transport = FakeTelegram()
    bot = PublicSignalBot(ledger, registry, transport, enabled=True)
    result = bot.publish(intent, route, now=NOW, verified_live_feed=True)
    assert result.status == "SENT" and result.message_id == 1234
    assert transport.send_count == 1
    ledger.close()
    ledger = SignalLedger(path)
    bot = PublicSignalBot(ledger, registry, transport, enabled=True)
    result = bot.publish(intent, route, now=NOW, verified_live_feed=True)
    assert result.status == "ALREADY_HANDLED" and transport.send_count == 1
    ledger.close()


def test_ambiguous_network_result_never_auto_resends(tmp_path):
    registry, intent, route, path = fixtures(tmp_path)
    ledger = SignalLedger(path)
    transport = FakeTelegram(throws=True)
    bot = PublicSignalBot(ledger, registry, transport, enabled=True)
    assert bot.publish(
        intent, route, now=NOW, verified_live_feed=True
    ).status == "DELIVERY_UNKNOWN_MANUAL_REVIEW"
    assert ledger.get(intent.engine_id, intent.signal_id).state == "CLAIMED"
    ledger.close()
    ledger = SignalLedger(path)
    transport.throws = False
    bot = PublicSignalBot(ledger, registry, transport, enabled=True)
    assert ledger.get(intent.engine_id, intent.signal_id).state == "UNKNOWN"
    assert bot.publish(
        intent, route, now=NOW, verified_live_feed=True
    ).status == "DELIVERY_UNKNOWN_MANUAL_REVIEW"
    assert transport.send_count == 1
    ledger.close()


@pytest.mark.parametrize("overrides,reason", [
    ({"enabled": False}, "ROUTE_DISABLED"),
    ({"channel_verified_private": False}, "PRIVATE_CHANNEL_NOT_VERIFIED"),
    ({"realtime_feed_verified": False}, "FEED_NOT_VERIFIED"),
])
def test_route_disabled_or_unverified(tmp_path, overrides, reason):
    registry, intent, route, path = fixtures(tmp_path)
    ledger = SignalLedger(path)
    transport = FakeTelegram()
    result = PublicSignalBot(ledger, registry, transport, enabled=True).publish(
        intent, replace(route, **overrides), now=NOW, verified_live_feed=True
    )
    assert result.status == reason and transport.send_count == 0
    ledger.close()


def test_private_channel_preflight_fails_closed(tmp_path):
    registry, intent, route, path = fixtures(tmp_path)
    ledger = SignalLedger(path)
    transport = FakeTelegram(valid=False)
    result = PublicSignalBot(ledger, registry, transport, enabled=True).publish(
        intent, route, now=NOW, verified_live_feed=True
    )
    assert result.status == "CHANNEL_NOT_PRIVATE_OR_NOT_ADMIN"
    assert transport.send_count == 0
    ledger.close()


def test_expired_not_published(tmp_path):
    registry, intent, route, path = fixtures(tmp_path)
    ledger = SignalLedger(path)
    transport = FakeTelegram()
    result = PublicSignalBot(ledger, registry, transport, enabled=True).publish(
        intent, route, now=NOW + timedelta(minutes=2), verified_live_feed=True
    )
    assert result.status == "SIGNAL_STALE_OR_FUTURE" and transport.send_count == 0
    ledger.close()


def test_paper_cannot_masquerade_as_forward(tmp_path):
    registry, intent, route, path = fixtures(tmp_path)
    ledger = SignalLedger(path)
    transport = FakeTelegram()
    result = PublicSignalBot(ledger, registry, transport, enabled=True).publish(
        replace(intent, evidence_mode=EvidenceMode.PAPER), route,
        now=NOW, verified_live_feed=True
    )
    assert result.status == "NOT_FORWARD_OBSERVATION"
    assert transport.send_count == 0
    ledger.close()


def test_formatting_contains_no_proprietary_logic(tmp_path):
    _, intent, _, _ = fixtures(tmp_path)
    msg = format_signal(intent)
    assert "example_core" in msg
    assert "US30" not in msg
    assert "breakout" not in msg.lower()



def test_private_channel_verifier_requires_real_private_admin(monkeypatch):
    from naseri_markets.public_signal_bot import TelegramPrivateChannel
    client = TelegramPrivateChannel("fixture-token")
    calls = []

    def mocked(method, payload):
        calls.append(method)
        if method == "getMe":
            return {"id": 123}
        if method == "getChat":
            return {"type": "channel", "id": -1001112223334}
        if method == "getChatMember":
            return {"status": "administrator", "can_post_messages": True}
        raise AssertionError(method)

    monkeypatch.setattr(client, "_api", mocked)
    assert client.verify_private_channel(-1001112223334)
    assert calls == ["getMe", "getChat", "getChatMember"]


@pytest.mark.parametrize("chat, member", [
    ({"type": "supergroup"}, {"status": "administrator", "can_post_messages": True}),
    ({"type": "channel", "username": "public_chan"}, {"status": "administrator", "can_post_messages": True}),
    ({"type": "channel"}, {"status": "member"}),
    ({"type": "channel"}, {"status": "administrator", "can_post_messages": False}),
])
def test_telegram_channel_privacy_and_post_permission_fail_closed(monkeypatch, chat, member):
    from naseri_markets.public_signal_bot import TelegramPrivateChannel
    client = TelegramPrivateChannel("fixture-token")

    def fake(method, payload):
        if method == "getMe":
            return {"id": 123}
        if method == "getChat":
            return chat
        return member

    monkeypatch.setattr(client, "_api", fake)
    assert not client.verify_private_channel(-1001112223334)


def test_no_proprietary_strategy_imports_in_public_bot():
    import inspect
    import naseri_markets.public_signal_bot as public_bot
    source = inspect.getsource(public_bot)
    assert "from r0_engine" not in source
    assert "import private_nyfr_core" not in source
    assert "order_send(" not in source
