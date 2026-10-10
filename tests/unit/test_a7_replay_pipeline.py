"""A7 public/private data boundary and offline E2E tests; no real services."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from naseri_markets.contracts import (
    Direction, EngineDescriptor, EvidenceMode, Instrument, Market, SignalIntent,
)
from naseri_markets.delivery_ledger import IdentityConflict
from naseri_markets.external_abi import ExternalPaperEngine, parse_paper_envelope
from naseri_markets.paper_journal import PaperJournal
from naseri_markets.quotes import QuoteOrigin, QuoteTick, QuoteVerdict
from naseri_markets.registry import EngineRegistry
from naseri_markets.replay_pipeline import A7ReplayPipeline
from naseri_markets.runtime import EngineBinding, MultiEngineRunner
from naseri_markets.sessions import SessionPolicy, TradingWindow

NOW = datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)
INST = Instrument(Market.INDEX, "mt5:synthetic", "US30", "America/New_York", "USD")


def quote(*, at=NOW, origin=QuoteOrigin.SYNTHETIC):
    return QuoteTick(INST, at, Decimal("43000"), Decimal("43001"), origin)


def packet(tick=None, **override):
    tick = tick or quote()
    payload = {
        "abi_version": 1, "signal_id": "example-paper-1",
        "engine_id": "demo_external", "engine_version": "1.0.0",
        "market": tick.instrument.market.value,
        "provider": tick.instrument.provider,
        "symbol": tick.instrument.symbol,
        "timezone": tick.instrument.timezone,
        "quote_currency": tick.instrument.quote_currency,
        "direction": "long", "observed_at": tick.occurred_at.isoformat(),
        "entry": "43000", "stop": "42970", "targets": ["43060"],
        "evidence_mode": "paper",
    }
    payload.update(override)
    return json.dumps(payload).encode()


class FakeExternalProvider:
    def __init__(self, *, modification=None, failure=False):
        self.modification = modification or {}
        self.failure = failure
        self.calls = 0

    async def produce(self, tick):
        self.calls += 1
        if self.failure:
            raise RuntimeError("example adapter error")
        return packet(tick, **self.modification)


class FakePublicEngine:
    engine_id = "demo_public"
    engine_version = "1.0.0"

    async def on_quote(self, tick):
        return (SignalIntent(
            "public-paper-1", self.engine_id, self.engine_version,
            tick.instrument, Direction.LONG, tick.occurred_at,
            Decimal("43000"), Decimal("42970"), (Decimal("43060"),),
            EvidenceMode.PAPER,
        ),)


def session(*, verified=True):
    return SessionPolicy(
        "UTC", (TradingWindow(4, time(0), time(23, 59)),), verified=verified,
    )


def setup(tmp_path, *, enabled=True, session_ok=True, external=None, with_public=False):
    registry = EngineRegistry()
    runner = MultiEngineRunner(registry, active=True)
    engine = ExternalPaperEngine("demo_external", "1.0.0", external or FakeExternalProvider())
    descriptor = EngineDescriptor("demo_external", "1.0.0", frozenset({Market.INDEX}))
    registry.register(descriptor)
    runner.attach(EngineBinding(
        descriptor, frozenset({INST}), session(verified=session_ok), enabled=True,
    ), engine)
    if with_public:
        desc2 = EngineDescriptor("demo_public", "1.0.0", frozenset({Market.INDEX}))
        registry.register(desc2)
        runner.attach(EngineBinding(
            desc2, frozenset({INST}), session(), enabled=True,
        ), FakePublicEngine())
    db_path = tmp_path / "replay.db"
    journal = PaperJournal(db_path)
    return A7ReplayPipeline(runner, journal, enabled=enabled), journal, runner, db_path


@pytest.mark.asyncio
async def test_default_disabled_ignores_engine(tmp_path):
    provider = FakeExternalProvider()
    pipe, journal, _, _ = setup(tmp_path, enabled=False, external=provider)
    result = await pipe.process(quote(), now=NOW)
    assert result.status == "DISABLED"
    assert provider.calls == 0 and journal.count() == 0
    journal.close()


@pytest.mark.asyncio
async def test_synthetic_external_plus_public_engine_persists_across_restart(tmp_path):
    pipe, journal, _, path = setup(tmp_path, with_public=True)
    result = await pipe.process(quote(), now=NOW)
    assert result.status == "RECORDED" and result.stored == 2
    assert journal.get("demo_external", "example-paper-1")["evidence_mode"] == "paper"
    assert journal.get("demo_public", "public-paper-1") is not None
    journal.close()
    reopened = PaperJournal(path)
    assert reopened.count() == 2
    assert reopened.get("demo_external", "example-paper-1")["provider"] == "mt5:synthetic"
    reopened.close()


@pytest.mark.asyncio
async def test_replay_never_calls_telegram_or_creates_outbox(tmp_path):
    pipe, journal, _, path = setup(tmp_path)
    assert (await pipe.process(quote(), now=NOW)).stored == 1
    assert journal._db.execute(
        "SELECT name FROM sqlite_master WHERE name='signal_outbox'"
    ).fetchone() is None
    assert path.is_file()
    journal.close()


@pytest.mark.asyncio
async def test_replay_duplicate_tick_not_recorded_twice(tmp_path):
    pipe, journal, _, _ = setup(tmp_path)
    assert (await pipe.process(quote(), now=NOW)).stored == 1
    second = await pipe.process(quote(), now=NOW)
    assert second.quote_verdict is QuoteVerdict.DUPLICATE
    assert second.stored == 0 and journal.count() == 1
    journal.close()


@pytest.mark.asyncio
async def test_unverified_session_prevents_engine_callback(tmp_path):
    provider = FakeExternalProvider()
    pipe, journal, _, _ = setup(tmp_path, session_ok=False, external=provider)
    result = await pipe.process(quote(), now=NOW)
    assert result.stored == 0 and provider.calls == 0
    journal.close()


@pytest.mark.asyncio
async def test_stale_quote_is_quarantined_before_engine(tmp_path):
    provider = FakeExternalProvider()
    pipe, journal, _, _ = setup(tmp_path, external=provider)
    result = await pipe.process(quote(at=NOW - timedelta(seconds=90)), now=NOW)
    assert result.quote_verdict is QuoteVerdict.STALE
    assert provider.calls == 0 and journal.count() == 0
    journal.close()


@pytest.mark.asyncio
async def test_live_quote_is_explicitly_refused(tmp_path):
    pipe, journal, _, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="A7_LIVE_TICK_REFUSED"):
        await pipe.process(quote(origin=QuoteOrigin.LIVE), now=NOW)
    assert journal.count() == 0
    journal.close()


@pytest.mark.asyncio
async def test_bad_external_engine_is_quarantined_but_public_continues(tmp_path):
    provider = FakeExternalProvider(failure=True)
    pipe, journal, runner, _ = setup(
        tmp_path, external=provider, with_public=True,
    )
    result = await pipe.process(quote(), now=NOW)
    assert result.stored == 1
    assert result.faulted_engines == ("demo_external",)
    assert runner.state("demo_external") == (True, "RuntimeError")
    assert journal.count() == 1
    journal.close()


@pytest.mark.parametrize("corruption", [
    {"abi_version": 2},
    {"abi_version": True},
    {"market": "crypto"},
    {"provider": "mt5:other"},
    {"symbol": "EURUSD"},
    {"engine_id": "demo_public"},
    {"engine_version": "9.0.0"},
    {"evidence_mode": "forward"},
    {"observed_at": "2026-10-09T13:31:00+00:00"},
    {"entry": 43000.0},
    {"entry": "NaN"},
    {"stop": "43010"},
    {"targets": []},
    {"targets": ["43060"] * 6},
    {"direction": "neutral"},
    {"secret_formula": "should never be stored"},
])
def test_malformed_or_cross_engine_packet_rejected(corruption):
    with pytest.raises(ValueError):
        parse_paper_envelope(
            packet(**corruption), quote(),
            engine_id="demo_external", engine_version="1.0.0",
        )


def test_duplicate_json_keys_rejected():
    raw = packet().decode().replace('"abi_version": 1', '"abi_version": 1, "abi_version": 1')
    with pytest.raises(ValueError):
        parse_paper_envelope(
            raw.encode(), quote(), engine_id="demo_external", engine_version="1.0.0",
        )


def test_oversized_envelope_rejected():
    with pytest.raises(ValueError):
        parse_paper_envelope(
            b"x" * 8193, quote(), engine_id="demo_external", engine_version="1.0.0",
        )


def test_journal_refuses_forward_and_identity_conflict_atomically(tmp_path):
    path = tmp_path / "atomic.db"
    journal = PaperJournal(path)
    good = parse_paper_envelope(
        packet(), quote(), engine_id="demo_external", engine_version="1.0.0",
    )
    assert journal.record_batch([good]).inserted == 1
    assert journal.record_batch([good]).duplicate == 1
    collision = replace(good, entry=Decimal("43002"))
    another = replace(good, signal_id="example-paper-2")
    with pytest.raises(IdentityConflict):
        journal.record_batch([another, collision])
    assert journal.count() == 1 and journal.get("demo_external", "example-paper-2") is None
    with pytest.raises(ValueError, match="A7_PAPER_ONLY"):
        journal.record_batch([replace(good, evidence_mode=EvidenceMode.FORWARD)])
    journal.close()


def test_journal_symlink_fail_closed(tmp_path):
    actual = tmp_path / "actual.db"
    actual.write_bytes(b"")
    link = tmp_path / "linked.db"
    link.symlink_to(actual)
    with pytest.raises(ValueError, match="A7_NONREGULAR_JOURNAL_PATH"):
        PaperJournal(link)
