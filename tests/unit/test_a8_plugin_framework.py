"""A8 offline plugin lifecycle, privacy, independent settings and E2E regression."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from naseri_markets.contracts import (
    Direction, EngineDescriptor, EvidenceMode, Instrument, Market, SignalIntent,
)
from naseri_markets.external_abi import ExternalPaperEngine
from naseri_markets.paper_journal import PaperJournal
from naseri_markets.plugin_descriptor import parse_descriptor
from naseri_markets.plugin_manager import PluginConflict, PluginManager, RevisionConflict
from naseri_markets.plugin_runtime import ManagedPaperPlatform
from naseri_markets.quotes import QuoteOrigin, QuoteTick, QuoteVerdict
from naseri_markets.registry import EngineRegistry
from naseri_markets.runtime import EngineBinding, MultiEngineRunner
from naseri_markets.sessions import SessionPolicy, TradingWindow

ROOT = Path(__file__).resolve().parents[2]
TS = datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)
INST = Instrument(Market.INDEX, "mt5:synthetic", "US30", "America/New_York", "USD")


def manifest(kind="public", **modification):
    data = {
        "schema_version": 1, "engine_id": (
            "public_demo" if kind == "public" else "private_example"
        ),
        "engine_version": "1.0.0",
        "publisher": "community.demo" if kind == "public" else "owner.private",
        "visibility": kind,
        "adapter": "in_process" if kind == "public" else "external_contract",
        "abi_version": 1, "markets": ["index"], "permissions": ["paper_analysis"],
    }
    data.update(modification)
    return json.dumps(data, sort_keys=True).encode("utf-8")


def pinned(raw):
    return hashlib.sha256(raw).hexdigest()


def q(at=TS, origin=QuoteOrigin.SYNTHETIC):
    return QuoteTick(INST, at, Decimal("43000"), Decimal("43001"), origin)


def session():
    return SessionPolicy(
        "UTC", (TradingWindow(4, time(0), time(23, 59)),), verified=True
    )


class PublicEngine:
    engine_id = "public_demo"
    engine_version = "1.0.0"

    def __init__(self):
        self.calls = 0

    async def on_quote(self, tick):
        self.calls += 1
        return (SignalIntent(
            f"public-{self.calls}", self.engine_id, self.engine_version,
            tick.instrument, Direction.LONG, tick.occurred_at,
            Decimal("43000"), Decimal("42970"), (Decimal("43060"),),
            EvidenceMode.PAPER,
        ),)


class PrivateFixture:
    """A stand-in for an owner-operated adapter; NO actual private NYFR."""

    def __init__(self):
        self.calls = 0

    async def produce(self, tick):
        self.calls += 1
        return json.dumps({
            "abi_version": 1, "signal_id": f"private-{self.calls}",
            "engine_id": "private_example", "engine_version": "1.0.0",
            "market": "index", "provider": tick.instrument.provider,
            "symbol": tick.instrument.symbol, "timezone": tick.instrument.timezone,
            "quote_currency": tick.instrument.quote_currency, "direction": "long",
            "observed_at": tick.occurred_at.isoformat(),
            "entry": "43000", "stop": "42970", "targets": ["43060"],
            "evidence_mode": "paper",
        }).encode("utf-8")


def setup(tmp_path, *, active=True):
    manager = PluginManager(tmp_path / "settings.db")
    registry = EngineRegistry()
    runner = MultiEngineRunner(registry, active=True)
    journal = PaperJournal(tmp_path / "paper.db")
    platform = ManagedPaperPlatform(
        manager, registry, runner, journal, enabled=active
    )
    public = PublicEngine()
    private = PrivateFixture()
    for kind, engine in (
        ("public", public),
        ("private", ExternalPaperEngine("private_example", "1.0.0", private)),
    ):
        raw = manifest(kind)
        state = manager.register(raw, approved_sha256=pinned(raw))
        descriptor = EngineDescriptor(
            state.engine_id, state.engine_version, frozenset({Market.INDEX})
        )
        platform.attach(
            EngineBinding(descriptor, frozenset({INST}), session(), enabled=True),
            engine,
        )
    return manager, journal, platform, public, private


def test_examples_are_exact_pinned_descriptors():
    for kind in ("public", "private"):
        path = ROOT / "examples/plugins" / f"{kind}-example.json"
        blob = path.read_bytes()
        item = parse_descriptor(blob, approved_sha256=pinned(blob))
        assert item.visibility == kind
        assert item.adapter == (
            "in_process" if kind == "public" else "external_contract"
        )
        assert item.engine_descriptor().supported_markets == frozenset({Market.INDEX})


@pytest.mark.parametrize("mutated", [
    {"schema_version": 2}, {"schema_version": True}, {"abi_version": 2},
    {"engine_id": "../path"}, {"engine_version": "bad"},
    {"publisher": "../owner"}, {"visibility": "unknown"},
    {"visibility": "private"}, {"adapter": "external_contract"},
    {"markets": []}, {"markets": ["index", "index"]},
    {"markets": ["invalid"]}, {"markets": ["index", True]},
    {"permissions": ["live_trading"]}, {"permissions": []},
    {"url": "https://untrusted.example"}, {"import": "module:main"},
    {"token": "not-allowed"}, {"entrypoint": "shell"},
])
def test_descriptor_rejects_non_contract_metadata(mutated):
    raw = manifest(**mutated)
    with pytest.raises(ValueError):
        parse_descriptor(raw, approved_sha256=pinned(raw))


def test_digest_not_self_authorizing():
    raw = manifest()
    with pytest.raises(ValueError, match="PIN_MISMATCH"):
        parse_descriptor(raw, approved_sha256="0" * 64)
    with pytest.raises(ValueError, match="PIN_INVALID"):
        parse_descriptor(raw, approved_sha256="UNVERIFIED")


@pytest.mark.parametrize("raw", [
    b"{}",
    b"x" * 8193,
    b'{"schema_version":1,"schema_version":1}',
    b'{"schema_version":NaN}',
    b"\xff",
])
def test_descriptor_rejects_malformed_and_duplicate(raw):
    with pytest.raises(ValueError):
        parse_descriptor(raw, approved_sha256=pinned(raw))


def test_metadata_registration_is_off_and_persistent(tmp_path):
    db = tmp_path / "settings.db"
    m = PluginManager(db)
    raw = manifest()
    first = m.register(raw, approved_sha256=pinned(raw))
    assert first.enabled is False and first.revision == 1
    assert first.status == "OFFLINE_PAPER_DISABLED"
    assert m.register(raw, approved_sha256=pinned(raw)) == first
    m.close()
    again = PluginManager(db)
    assert again.get("public_demo") == first
    assert again.list() == (first,)
    again.close()


def test_each_engine_has_independent_toggle_and_cas(tmp_path):
    m, journal, _, _, _ = setup(tmp_path)
    a = m.get("public_demo")
    b = m.get("private_example")
    assert not a.enabled and not b.enabled
    a = m.set_enabled("public_demo", enabled=True, expected_revision=a.revision)
    assert a.enabled and a.revision == 2
    assert not m.get("private_example").enabled
    with pytest.raises(RevisionConflict):
        m.set_enabled("public_demo", enabled=False, expected_revision=1)
    assert m.get("public_demo").enabled
    assert m.set_enabled(
        "public_demo", enabled=True, expected_revision=2
    ).revision == 2
    a = m.set_enabled("public_demo", enabled=False, expected_revision=2)
    assert not a.enabled and a.revision == 3
    m.close()
    journal.close()


def test_update_requires_disabled_and_explicit_pin(tmp_path):
    m = PluginManager(tmp_path / "settings.db")
    initial = manifest()
    m.register(initial, approved_sha256=pinned(initial))
    enabled = m.set_enabled("public_demo", enabled=True, expected_revision=1)
    candidate = manifest(engine_version="1.0.1")
    with pytest.raises(PluginConflict):
        m.replace(candidate, approved_sha256=pinned(candidate),
                  expected_revision=enabled.revision)
    disabled = m.set_enabled("public_demo", enabled=False,
                             expected_revision=enabled.revision)
    upgraded = m.replace(candidate, approved_sha256=pinned(candidate),
                         expected_revision=disabled.revision)
    assert upgraded.engine_version == "1.0.1"
    assert not upgraded.enabled and upgraded.revision == 4
    with pytest.raises(RevisionConflict):
        m.replace(candidate, approved_sha256=pinned(candidate),
                  expected_revision=3)
    m.close()


def test_register_conflicting_payload_must_use_upgrade(tmp_path):
    m = PluginManager(tmp_path / "s.db")
    original = manifest()
    m.register(original, approved_sha256=pinned(original))
    change = manifest(engine_version="2.0.0")
    with pytest.raises(PluginConflict):
        m.register(change, approved_sha256=pinned(change))
    assert m.get("public_demo").engine_version == "1.0.0"
    m.close()


def test_sqlite_other_connection_sees_toggles(tmp_path):
    file = tmp_path / "state.db"
    a, b = PluginManager(file), PluginManager(file)
    raw = manifest()
    a.register(raw, approved_sha256=pinned(raw))
    a.set_enabled("public_demo", enabled=True, expected_revision=1)
    assert b.get("public_demo").enabled
    with pytest.raises(RevisionConflict):
        b.set_enabled("public_demo", enabled=False, expected_revision=1)
    a.close()
    b.close()


def test_settings_api_rejects_wrong_types(tmp_path):
    m = PluginManager(tmp_path / "state.db")
    raw = manifest()
    m.register(raw, approved_sha256=pinned(raw))
    for bad in (1, "true", None):
        with pytest.raises(ValueError):
            m.set_enabled("public_demo", enabled=bad, expected_revision=1)
    for bad in (True, 0, "1"):
        with pytest.raises(ValueError):
            m.set_enabled("public_demo", enabled=True, expected_revision=bad)
    with pytest.raises(ValueError):
        m.set_enabled("not_registered", enabled=True, expected_revision=1)
    m.close()


def test_symlinked_settings_file_is_rejected(tmp_path):
    target = tmp_path / "real"
    target.write_bytes(b"")
    symlink = tmp_path / "link"
    symlink.symlink_to(target)
    with pytest.raises(ValueError, match="SETTINGS_FILE_UNSAFE"):
        PluginManager(symlink)


def test_private_adapter_contract_enforced(tmp_path):
    m = PluginManager(tmp_path / "state.db")
    raw = manifest("private")
    m.register(raw, approved_sha256=pinned(raw))
    registry = EngineRegistry()
    platform = ManagedPaperPlatform(
        m, registry, MultiEngineRunner(registry, active=True),
        PaperJournal(tmp_path / "journal.db"),
    )
    descriptor = EngineDescriptor(
        "private_example", "1.0.0", frozenset({Market.INDEX})
    )
    with pytest.raises(ValueError, match="PRIVATE_EXTERNAL_CONTRACT"):
        platform.attach(
            EngineBinding(descriptor, frozenset({INST}), session(), enabled=True),
            PublicEngine(),
        )
    m.close()


@pytest.mark.asyncio
async def test_manager_and_pipeline_disabled_by_default(tmp_path):
    m, journal, platform, public, private = setup(tmp_path, active=False)
    assert (await platform.process(q(), now=TS)).status == "DISABLED"
    assert journal.count() == 0
    assert public.calls == 0 and private.calls == 0
    m.close()
    journal.close()


@pytest.mark.asyncio
async def test_both_off_then_public_then_private_then_public_off(tmp_path):
    m, journal, platform, public, private = setup(tmp_path)
    assert (await platform.process(q(), now=TS)).status == "NO_ENABLED_BOUND_ENGINES"
    assert public.calls == 0 and private.calls == 0
    one = m.set_enabled("public_demo", enabled=True, expected_revision=1)
    result = await platform.process(q(), now=TS)
    assert result.stored == 1 and public.calls == 1 and private.calls == 0
    m.set_enabled("private_example", enabled=True, expected_revision=1)
    second = await platform.process(q(TS + timedelta(seconds=1)),
                                    now=TS + timedelta(seconds=1))
    assert second.stored == 2 and public.calls == 2 and private.calls == 1
    m.set_enabled("public_demo", enabled=False, expected_revision=one.revision)
    third = await platform.process(q(TS + timedelta(seconds=2)),
                                   now=TS + timedelta(seconds=2))
    assert third.stored == 1 and public.calls == 2 and private.calls == 2
    assert journal.count() == 4
    journal.close()
    m.close()
    re = PluginManager(tmp_path / "settings.db")
    saved = PaperJournal(tmp_path / "paper.db")
    assert re.get("private_example").enabled
    assert not re.get("public_demo").enabled
    assert saved.count() == 4
    assert saved.get("private_example", "private-2")["evidence_mode"] == "paper"
    assert saved._db.execute(
        "SELECT name FROM sqlite_master WHERE name='signal_outbox'"
    ).fetchone() is None
    saved.close()
    re.close()


@pytest.mark.asyncio
async def test_disabled_plugin_callback_not_invoked_even_if_runner_attached(tmp_path):
    m, journal, platform, public, private = setup(tmp_path)
    m.set_enabled("private_example", enabled=True, expected_revision=1)
    assert (await platform.process(q(), now=TS)).stored == 1
    assert public.calls == 0 and private.calls == 1
    journal.close()
    m.close()


@pytest.mark.asyncio
async def test_live_ticks_never_accepted(tmp_path):
    m, journal, platform, public, private = setup(tmp_path)
    m.set_enabled("public_demo", enabled=True, expected_revision=1)
    with pytest.raises(ValueError, match="LIVE_QUOTES_FORBIDDEN"):
        await platform.process(q(origin=QuoteOrigin.LIVE), now=TS)
    assert not public.calls and not private.calls and journal.count() == 0
    journal.close()
    m.close()


@pytest.mark.asyncio
async def test_stale_tick_prevents_callback(tmp_path):
    m, journal, platform, public, _ = setup(tmp_path)
    m.set_enabled("public_demo", enabled=True, expected_revision=1)
    result = await platform.process(q(TS - timedelta(seconds=90)), now=TS)
    assert result.quote_verdict is QuoteVerdict.STALE
    assert public.calls == 0 and journal.count() == 0
    journal.close()
    m.close()


@pytest.mark.asyncio
async def test_settings_toggle_during_await_discards_pending_batch(tmp_path):
    m, journal, platform, _, _ = setup(tmp_path)
    entered = asyncio.Event()
    resume = asyncio.Event()

    class SlowPublic:
        engine_id = "slow_demo"
        engine_version = "1.0.0"

        async def on_quote(self, tick):
            entered.set()
            await resume.wait()
            return (SignalIntent(
                "late-paper", self.engine_id, self.engine_version,
                tick.instrument, Direction.LONG, tick.occurred_at,
                Decimal("43000"), Decimal("42970"), (Decimal("43060"),),
                EvidenceMode.PAPER,
            ),)

    raw = manifest(engine_id="slow_demo")
    m.register(raw, approved_sha256=pinned(raw))
    engine = SlowPublic()
    binding = EngineBinding(
        EngineDescriptor("slow_demo", "1.0.0", frozenset({Market.INDEX})),
        frozenset({INST}), session(), enabled=True,
    )
    platform.attach(binding, engine)
    m.set_enabled("slow_demo", enabled=True, expected_revision=1)
    task = asyncio.create_task(platform.process(q(), now=TS))
    await asyncio.wait_for(entered.wait(), timeout=3)
    m.set_enabled("slow_demo", enabled=False, expected_revision=2)
    resume.set()
    outcome = await asyncio.wait_for(task, timeout=3)
    assert outcome.status == "SETTINGS_CHANGED_IN_FLIGHT"
    assert journal.count() == 0
    journal.close()
    m.close()


def test_public_template_has_no_strategies_or_secret_download():
    template = (ROOT / "examples/plugins/public_template.py").read_text()
    assert "async def on_quote(" in template
    assert "return ()" in template
    assert "import private_nyfr_core" not in template
