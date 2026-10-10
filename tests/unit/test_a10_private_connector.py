"""A10 authenticated PAPER-only connector tests. No network or private source."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import datetime, time, timezone
from decimal import Decimal

import pytest

from naseri_markets.contracts import EngineDescriptor, Instrument, Market
from naseri_markets.external_abi import ExternalPaperEngine
from naseri_markets.paper_journal import PaperJournal
from naseri_markets.plugin_manager import PluginManager
from naseri_markets.plugin_runtime import ManagedPaperPlatform
from naseri_markets.private_connector import ConnectorKeys, PrivatePaperConnector
from naseri_markets.private_protocol import (
    ProtocolRefused, ReplayFence, sign_packet, verify_packet,
)
from naseri_markets.quotes import QuoteOrigin, QuoteTick
from naseri_markets.registry import EngineRegistry
from naseri_markets.runtime import EngineBinding, MultiEngineRunner
from naseri_markets.sessions import SessionPolicy, TradingWindow

NOW = 1791549000
UTC = datetime.fromtimestamp(NOW, tz=timezone.utc)
INSTRUMENT = Instrument(Market.INDEX, "fixture:quotes", "US30", "UTC", "USD")
C_KEY = b"client-fixture-only-1234567890----key"
O_KEY = b"owner-fixture-only-123456789012--key"
KEYS = ConnectorKeys("client_k1", C_KEY, "owner_k1", O_KEY)


def metadata(version="1.0.0"):
    return json.dumps({
        "schema_version": 1, "engine_id": "private_example",
        "engine_version": version, "publisher": "fixture.owner",
        "visibility": "private", "adapter": "external_contract",
        "abi_version": 1, "markets": ["index"],
        "permissions": ["paper_analysis"],
    }, sort_keys=True).encode()


def pin(blob):
    return hashlib.sha256(blob).hexdigest()


def tick(origin=QuoteOrigin.SYNTHETIC):
    return QuoteTick(INSTRUMENT, UTC, Decimal("43000"), Decimal("43001"), origin)


def signal_body(t):
    return {
        "abi_version": 1, "signal_id": "private-fixture-signal",
        "engine_id": "private_example", "engine_version": "1.0.0",
        "market": "index", "provider": INSTRUMENT.provider,
        "symbol": INSTRUMENT.symbol, "timezone": INSTRUMENT.timezone,
        "quote_currency": INSTRUMENT.quote_currency, "direction": "long",
        "observed_at": t.occurred_at.isoformat(),
        "entry": "43000", "stop": "42980", "targets": ["43070"],
        "evidence_mode": "paper",
    }


def response_body(request, *, seq=1, **overrides):
    req = json.loads(request)["body"]
    blob = json.dumps(signal_body(tick()), sort_keys=True).encode()
    payload = {
        "operation": "paper_analysis",
        "paper_envelope_b64": base64.b64encode(blob).decode(),
    }
    data = {
        "version": 1, "key_id": KEYS.owner_key_id, "direction": "to_bot",
        "engine_id": "private_example", "engine_version": "1.0.0",
        "nonce": f"{seq:032x}", "request_nonce": req["nonce"],
        "issued_at": NOW, "expires_at": NOW + 20, "payload": payload,
    }
    data.update(overrides)
    return data


def setup(tmp_path, *, enabled=True):
    mgr = PluginManager(tmp_path / "plugins.db")
    raw = metadata()
    state = mgr.register(raw, approved_sha256=pin(raw))
    if enabled:
        state = mgr.set_enabled(
            "private_example", enabled=True, expected_revision=state.revision,
        )
    fence = ReplayFence(tmp_path / "nonce-store.db")
    return mgr, fence, state


class OfflineOwnerFixture:
    """Simulates an independently keyed owner; never executes strategy code."""

    def __init__(self, *, mode="ok", reuse_nonce=False):
        self.calls = 0
        self.mode = mode
        self.reuse_nonce = reuse_nonce

    async def exchange(self, packet):
        self.calls += 1
        request = verify_packet(
            packet, key=C_KEY, key_id=KEYS.client_key_id,
            direction="to_owner", engine_id="private_example",
            engine_version="1.0.0", now=NOW,
        )
        assert request["payload"]["operation"] == "paper_analysis"
        assert request["payload"]["tick"]["origin"] == "synthetic"
        override = {}
        if self.mode == "wrong_challenge":
            override["request_nonce"] = "b" * 32
        if self.mode == "expired":
            override["issued_at"] = NOW - 60
            override["expires_at"] = NOW - 40
        if self.mode == "wrong_version":
            override["engine_version"] = "9.9.9"
        if self.mode == "wrong_key_id":
            override["key_id"] = "owner_k2"
        if self.mode == "wrong_direction":
            override["direction"] = "to_owner"
            override["request_nonce"] = ""
        if self.mode == "future":
            override["issued_at"] = NOW + 10
            override["expires_at"] = NOW + 20
        seq = 1 if self.reuse_nonce else self.calls
        answer = response_body(packet, seq=seq, **override)
        if self.mode in ("forward", "wrong_symbol", "corrupted_base64"):
            payload = answer["payload"]
            if self.mode == "corrupted_base64":
                payload["paper_envelope_b64"] = "%%%%"
            else:
                body = signal_body(tick())
                if self.mode == "forward":
                    body["evidence_mode"] = "forward"
                if self.mode == "wrong_symbol":
                    body["symbol"] = "BTCUSDT"
                payload["paper_envelope_b64"] = base64.b64encode(
                    json.dumps(body).encode()
                ).decode()
        reply = sign_packet(answer, key=O_KEY)
        if self.mode == "bad_mac":
            r = json.loads(reply)
            r["mac"] = "0" * 64
            return json.dumps(r).encode()
        return reply


def connector(manager, fence, owner, *, timeout=1.0):
    return PrivatePaperConnector(
        manager=manager, fence=fence, engine_id="private_example",
        engine_version="1.0.0", approved_digest=pin(metadata()),
        keys=KEYS, exchange=owner.exchange, timeout_seconds=timeout,
        now_seconds=lambda: NOW,
    )


def test_keys_must_be_independent_and_strong():
    with pytest.raises(ProtocolRefused):
        ConnectorKeys("a", b"x" * 32, "b", b"x" * 32)
    with pytest.raises(ProtocolRefused):
        ConnectorKeys("a", b"x", "b", b"y" * 32)
    with pytest.raises(ProtocolRefused):
        ConnectorKeys("a", b"x" * 32, "a", b"y" * 32)


def test_invalid_signed_packet_and_scope(tmp_path):
    request = {
        "version": 1, "key_id": "client_k1", "direction": "to_owner",
        "engine_id": "private_example", "engine_version": "1.0.0",
        "nonce": "a" * 32, "request_nonce": "",
        "issued_at": NOW, "expires_at": NOW + 20, "payload": {},
    }
    wire = sign_packet(request, key=C_KEY)
    assert verify_packet(
        wire, key=C_KEY, key_id="client_k1", direction="to_owner",
        engine_id="private_example", engine_version="1.0.0", now=NOW,
    )["nonce"] == "a" * 32
    for mismatch in (
        {"key": O_KEY}, {"key_id": "owner_k1"}, {"direction": "to_bot"},
        {"engine_id": "other"}, {"engine_version": "2.0.0"},
        {"now": NOW + 40},
    ):
        args = {
            "key": C_KEY, "key_id": "client_k1", "direction": "to_owner",
            "engine_id": "private_example", "engine_version": "1.0.0",
            "now": NOW,
        }
        args.update(mismatch)
        with pytest.raises(ProtocolRefused):
            verify_packet(wire, **args)
    bad = wire.replace(b'"nonce":"aaaaaaaa', b'"nonce":"bbbbbbbb')
    with pytest.raises(ProtocolRefused):
        verify_packet(
            bad, key=C_KEY, key_id="client_k1", direction="to_owner",
            engine_id="private_example", engine_version="1.0.0", now=NOW,
        )


@pytest.mark.parametrize("mutate", [
    {"expires_at": NOW + 40},
    {"expires_at": NOW},
    {"issued_at": True},
    {"version": 2},
    {"version": True},
    {"nonce": "../invalid"},
    {"request_nonce": "a" * 32},
    {"direction": "live_trade"},
    {"new_field": "not-allowed"},
])
def test_packet_signer_refuses_unsafe_structure(mutate):
    req = {
        "version": 1, "key_id": "client_k1", "direction": "to_owner",
        "engine_id": "private_example", "engine_version": "1.0.0",
        "nonce": "a" * 32, "request_nonce": "",
        "issued_at": NOW, "expires_at": NOW + 20, "payload": {},
    }
    req.update(mutate)
    with pytest.raises(ProtocolRefused):
        sign_packet(req, key=C_KEY)


@pytest.mark.parametrize("packet", [
    b"", b"x" * 20001, b"{not-json}",
    b'{"body":1,"mac":"foo"}',
    b'{"body":{},"body":{},"mac":"x"}',
    b'{"body":NaN,"mac":"x"}',
])
def test_malformed_packets_rejected(packet):
    with pytest.raises(ProtocolRefused):
        verify_packet(
            packet, key=C_KEY, key_id="client_k1", direction="to_owner",
            engine_id="private_example", engine_version="1.0.0", now=NOW,
        )


def test_replay_fence_persists_revocations_and_nonce(tmp_path):
    db = tmp_path / "replay.db"
    store = ReplayFence(db)
    store.consume(direction="to_bot", key_id="owner_k1", nonce="a" * 32)
    with pytest.raises(ProtocolRefused, match="REPLAY"):
        store.consume(direction="to_bot", key_id="owner_k1", nonce="a" * 32)
    store.revoke("owner_k1")
    store.close()
    later = ReplayFence(db)
    with pytest.raises(ProtocolRefused, match="REVOKED"):
        later.consume(direction="to_bot", key_id="owner_k1", nonce="b" * 32)
    assert later.is_revoked("owner_k1")
    later.close()


@pytest.mark.asyncio
async def test_authenticated_private_connector_end_to_end_paper_journal(tmp_path):
    manager, fence, _ = setup(tmp_path)
    owner = OfflineOwnerFixture()
    secured = connector(manager, fence, owner)
    external = ExternalPaperEngine("private_example", "1.0.0", secured)
    registry = EngineRegistry()
    runner = MultiEngineRunner(registry, active=True)
    journal = PaperJournal(tmp_path / "paper.db")
    platform = ManagedPaperPlatform(
        manager, registry, runner, journal, enabled=True,
    )
    binding = EngineBinding(
        EngineDescriptor("private_example", "1.0.0",
                         frozenset({Market.INDEX})),
        frozenset({INSTRUMENT}),
        SessionPolicy(
            "UTC", (TradingWindow(4, time(0), time(23, 59)),), verified=True,
        ),
        enabled=True,
    )
    platform.attach(binding, external)
    result = await platform.process(tick(), now=UTC)
    assert result.stored == 1 and result.status == "RECORDED"
    assert journal.count() == 1 and owner.calls == 1
    assert journal.get("private_example", "private-fixture-signal")["evidence_mode"] == "paper"
    assert secured.status.real_owner_authenticated is False
    assert secured.status.real_network_connected is False
    assert secured.status.trading_allowed is False
    journal.close()
    fence.close()
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [
    "wrong_challenge", "expired", "wrong_version", "wrong_key_id",
    "wrong_direction", "future", "forward", "wrong_symbol",
    "corrupted_base64", "bad_mac",
])
async def test_owner_responses_fail_closed(tmp_path, mode):
    mgr, fence, _ = setup(tmp_path)
    owner = OfflineOwnerFixture(mode=mode)
    secured = connector(mgr, fence, owner)
    with pytest.raises((ProtocolRefused, ValueError)):
        await secured.produce(tick())
    fence.close()
    mgr.close()


@pytest.mark.asyncio
async def test_replayed_signed_response_nonce_blocked(tmp_path):
    mgr, fence, _ = setup(tmp_path)
    owner = OfflineOwnerFixture(reuse_nonce=True)
    secured = connector(mgr, fence, owner)
    assert await secured.produce(tick())
    with pytest.raises(ProtocolRefused, match="REPLAY"):
        await secured.produce(tick())
    fence.close()
    mgr.close()


@pytest.mark.asyncio
async def test_key_revocation_blocks_pending_or_new_response(tmp_path):
    mgr, fence, _ = setup(tmp_path)
    owner = OfflineOwnerFixture()
    secured = connector(mgr, fence, owner)
    fence.revoke("owner_k1")
    with pytest.raises(ProtocolRefused, match="REVOKED"):
        await secured.produce(tick())
    assert owner.calls == 0
    fence.close()
    mgr.close()


@pytest.mark.asyncio
async def test_disable_during_exchange_drops_result(tmp_path):
    mgr, fence, initial = setup(tmp_path)
    entered = asyncio.Event()
    resume = asyncio.Event()
    owner = OfflineOwnerFixture()

    async def waiting_exchange(packet):
        entered.set()
        await resume.wait()
        return await owner.exchange(packet)

    secured = PrivatePaperConnector(
        manager=mgr, fence=fence, engine_id="private_example",
        engine_version="1.0.0", approved_digest=pin(metadata()),
        keys=KEYS, exchange=waiting_exchange, now_seconds=lambda: NOW,
    )
    job = asyncio.create_task(secured.produce(tick()))
    await asyncio.wait_for(entered.wait(), timeout=3)
    mgr.set_enabled(
        "private_example", enabled=False, expected_revision=initial.revision,
    )
    resume.set()
    with pytest.raises(ProtocolRefused, match="PLUGIN_DISABLED"):
        await job
    fence.close()
    mgr.close()


@pytest.mark.asyncio
async def test_remove_reinstall_cannot_revalidate_old_connector(tmp_path):
    mgr, fence, initial = setup(tmp_path)
    secured = connector(mgr, fence, OfflineOwnerFixture())
    off = mgr.set_enabled(
        "private_example", enabled=False, expected_revision=initial.revision,
    )
    mgr.unregister("private_example", expected_revision=off.revision)
    raw = metadata()
    re = mgr.register(raw, approved_sha256=pin(raw))
    mgr.set_enabled(
        "private_example", enabled=True, expected_revision=re.revision,
    )
    with pytest.raises(ProtocolRefused, match="PLUGIN_DISABLED"):
        await secured.produce(tick())
    fence.close()
    mgr.close()


@pytest.mark.asyncio
async def test_timeout_does_not_accept_partial_transport(tmp_path):
    mgr, fence, _ = setup(tmp_path)
    async def forever(_):
        await asyncio.sleep(5)
        return b""
    secured = PrivatePaperConnector(
        manager=mgr, fence=fence, engine_id="private_example",
        engine_version="1.0.0", approved_digest=pin(metadata()),
        keys=KEYS, exchange=forever, timeout_seconds=0.01,
        now_seconds=lambda: NOW,
    )
    with pytest.raises(ProtocolRefused, match="TRANSPORT_UNAVAILABLE"):
        await secured.produce(tick())
    fence.close()
    mgr.close()


@pytest.mark.asyncio
async def test_live_quotes_rejected_without_transport(tmp_path):
    mgr, fence, _ = setup(tmp_path)
    owner = OfflineOwnerFixture()
    secured = connector(mgr, fence, owner)
    with pytest.raises(ProtocolRefused, match="LIVE_DATA_FORBIDDEN"):
        await secured.produce(tick(QuoteOrigin.LIVE))
    assert owner.calls == 0
    fence.close()
    mgr.close()


def test_no_network_private_repository_or_trade_implementation():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "naseri_markets"
    for name in ("private_connector.py", "private_protocol.py"):
        code = (root / name).read_text()
        assert "import MetaTrader5" not in code
        assert "import requests" not in code
        assert "import socket" not in code
        assert "private_nyfr_core" not in code
        assert "order_send(" not in code
