"""A9 offline lifecycle, settings service, CLI, restart and ABA safety."""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from naseri_markets.contracts import (
    Direction, EngineDescriptor, EvidenceMode, Instrument, Market, SignalIntent,
)
from naseri_markets.paper_journal import PaperJournal
from naseri_markets.plugin_manager import (
    PluginConflict, PluginManager, RevisionConflict,
)
from naseri_markets.plugin_runtime import ManagedPaperPlatform
from naseri_markets.plugin_settings import OperatorDenied, PluginSettingsService
from naseri_markets.quotes import QuoteOrigin, QuoteTick
from naseri_markets.registry import EngineRegistry
from naseri_markets.runtime import EngineBinding, MultiEngineRunner
from naseri_markets.sessions import SessionPolicy, TradingWindow

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)
INSTRUMENT = Instrument(Market.INDEX, "mt5:synthetic", "US30", "UTC", "USD")


def manifest(engine_id="public_demo", *, version="1.0.0",
             private=False):
    return json.dumps({
        "schema_version": 1,
        "engine_id": engine_id, "engine_version": version,
        "publisher": "approved.public" if not private else "approved.private",
        "visibility": "private" if private else "public",
        "adapter": "external_contract" if private else "in_process",
        "abi_version": 1, "markets": ["index"], "permissions": ["paper_analysis"],
    }, sort_keys=True).encode()


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def tick(at=NOW):
    return QuoteTick(INSTRUMENT, at, Decimal("43000"), Decimal("43001"),
                     QuoteOrigin.SYNTHETIC)


def make_binding(engine_id="public_demo", version="1.0.0"):
    return EngineBinding(
        EngineDescriptor(engine_id, version, frozenset({Market.INDEX})),
        frozenset({INSTRUMENT}),
        SessionPolicy(
            "UTC", (TradingWindow(4, time(0), time(23, 59)),), verified=True,
        ), enabled=True,
    )


class FixtureEngine:
    engine_id = "public_demo"
    engine_version = "1.0.0"

    def __init__(self):
        self.calls = 0

    async def on_quote(self, quote):
        self.calls += 1
        return (SignalIntent(
            f"a9-{self.calls}", self.engine_id, self.engine_version,
            quote.instrument, Direction.LONG, quote.occurred_at,
            Decimal("43000"), Decimal("42980"),
            (Decimal("43050"),), EvidenceMode.PAPER,
        ),)


def build(tmp_path):
    m = PluginManager(tmp_path / "settings.db")
    x = manifest()
    initial = m.register(x, approved_sha256=sha(x))
    registry = EngineRegistry()
    runner = MultiEngineRunner(registry, active=True)
    journal = PaperJournal(tmp_path / "paper.db")
    platform = ManagedPaperPlatform(m, registry, runner, journal, enabled=True)
    engine = FixtureEngine()
    platform.attach(make_binding(), engine)
    return m, initial, platform, journal, engine


def test_safe_unregister_requires_disable_then_tombstone(tmp_path):
    m, initial, _, journal, _ = build(tmp_path)
    enabled = m.set_enabled("public_demo", enabled=True, expected_revision=1)
    with pytest.raises(PluginConflict, match="DISABLE_BEFORE"):
        m.unregister("public_demo", expected_revision=2)
    assert m.get("public_demo").enabled
    disabled = m.set_enabled("public_demo", enabled=False, expected_revision=2)
    with pytest.raises(RevisionConflict):
        m.unregister("public_demo", expected_revision=enabled.revision)
    fence = m.unregister("public_demo", expected_revision=disabled.revision)
    assert fence == 4
    assert m.get("public_demo") is None
    assert m.incarnation("public_demo") == fence
    with pytest.raises(RevisionConflict):
        m.unregister("public_demo", expected_revision=disabled.revision)
    assert [x["action"] for x in m.audit_history("public_demo")] == [
        "REGISTER", "ENABLE_PAPER", "DISABLE_PAPER", "UNREGISTER_METADATA",
    ]
    m.close()
    journal.close()


def test_reregister_monotonic_revision_and_off_after_restart(tmp_path):
    m, old, _, journal, _ = build(tmp_path)
    assert old.revision == 1
    fence = m.unregister("public_demo", expected_revision=1)
    same = manifest()
    updated = m.register(same, approved_sha256=sha(same))
    assert updated.revision == fence + 1
    assert updated.enabled is False
    assert m.incarnation("public_demo") == fence
    m.close()
    reopened = PluginManager(tmp_path / "settings.db")
    assert reopened.get("public_demo") == updated
    assert reopened.incarnation("public_demo") == fence
    assert len(reopened.audit_history("public_demo")) == 3
    reopened.close()
    journal.close()


@pytest.mark.asyncio
async def test_old_adapter_never_runs_after_remove_and_reregister(tmp_path):
    m, _, platform, journal, engine = build(tmp_path)
    m.set_enabled("public_demo", enabled=True, expected_revision=1)
    result = await platform.process(tick(), now=NOW)
    assert result.stored == 1 and engine.calls == 1
    m.set_enabled("public_demo", enabled=False, expected_revision=2)
    m.unregister("public_demo", expected_revision=3)
    raw = manifest()
    new_state = m.register(raw, approved_sha256=sha(raw))
    m.set_enabled("public_demo", enabled=True, expected_revision=new_state.revision)
    result2 = await platform.process(tick(NOW + timedelta(seconds=1)),
                                     now=NOW + timedelta(seconds=1))
    assert result2.status == "NO_ENABLED_BOUND_ENGINES"
    assert engine.calls == 1 and journal.count() == 1
    journal.close()
    m.close()


@pytest.mark.asyncio
async def test_uninstall_during_callback_disposes_result(tmp_path):
    m, _, platform, journal, _ = build(tmp_path)
    entered = asyncio.Event()
    resume = asyncio.Event()

    class Slow:
        engine_id = "slow_public"
        engine_version = "1.0.0"
        async def on_quote(self, q):
            entered.set()
            await resume.wait()
            return (SignalIntent(
                "slow-result", self.engine_id, self.engine_version,
                q.instrument, Direction.LONG, q.occurred_at,
                Decimal("43000"), Decimal("42980"),
                (Decimal("43050"),), EvidenceMode.PAPER,
            ),)

    raw = manifest("slow_public")
    m.register(raw, approved_sha256=sha(raw))
    platform.attach(make_binding("slow_public"), Slow())
    m.set_enabled("slow_public", enabled=True, expected_revision=1)
    task = asyncio.create_task(platform.process(tick(), now=NOW))
    await asyncio.wait_for(entered.wait(), timeout=3)
    m.set_enabled("slow_public", enabled=False, expected_revision=2)
    m.unregister("slow_public", expected_revision=3)
    x = m.register(raw, approved_sha256=sha(raw))
    m.set_enabled("slow_public", enabled=True, expected_revision=x.revision)
    resume.set()
    result = await asyncio.wait_for(task, timeout=3)
    assert result.status == "SETTINGS_CHANGED_IN_FLIGHT"
    assert journal.count() == 0
    journal.close()
    m.close()


def test_separate_plugins_survive_neighbor_removal(tmp_path):
    m = PluginManager(tmp_path / "db")
    a = manifest("alpha_demo")
    b = manifest("beta_demo")
    m.register(a, approved_sha256=sha(a))
    m.register(b, approved_sha256=sha(b))
    m.set_enabled("beta_demo", enabled=True, expected_revision=1)
    m.unregister("alpha_demo", expected_revision=1)
    assert m.get("alpha_demo") is None
    assert m.get("beta_demo").enabled is True
    assert m.audit_history("beta_demo")[-1]["action"] == "ENABLE_PAPER"
    m.close()


def test_settings_api_denies_untrusted_id_before_mutations(tmp_path):
    m, _, _, journal, _ = build(tmp_path)
    svc = PluginSettingsService(m, operator_ids=frozenset({777}))
    for invalid in (0, 42, True, "777", None):
        with pytest.raises(OperatorDenied):
            svc.inventory(invalid)
        with pytest.raises(OperatorDenied):
            svc.set_paper_enabled(invalid, "public_demo",
                                  enabled=True, expected_revision=1)
        with pytest.raises(OperatorDenied):
            svc.unregister(invalid, "public_demo", expected_revision=1)
    assert not m.get("public_demo").enabled
    m.close()
    journal.close()


@pytest.mark.parametrize("ids", [frozenset(), {777}, frozenset({True}),
                                frozenset({0}), frozenset({"777"})])
def test_settings_requires_positive_trusted_operator_ids(tmp_path, ids):
    m = PluginManager(tmp_path / "db")
    with pytest.raises(ValueError, match="TRUSTED_OPERATOR"):
        PluginSettingsService(m, operator_ids=ids)
    m.close()


def test_settings_service_inventory_health_and_scope(tmp_path):
    m = PluginManager(tmp_path / "db")
    svc = PluginSettingsService(m, operator_ids=frozenset({777}))
    for engine_id, private in (("public_demo", False), ("private_example", True)):
        x = manifest(engine_id, private=private)
        svc.register(777, x, approved_sha256=sha(x))
    inventory = svc.inventory(777)
    assert len(inventory) == 2
    assert not any(x.enabled_for_paper for x in inventory)
    assert not any(x.code_installed for x in inventory)
    report = svc.health_report(777)
    assert report["scope"] == "OFFLINE_METADATA_ONLY"
    assert report["private_engine_attested"] is False
    assert report["live_feed_verified"] is False
    assert report["telegram_publication_enabled"] is False
    assert report["broker_order_execution_enabled"] is False
    assert any(x["operational_health"] == "PRIVATE_OWNER_NOT_ATTESTED"
               for x in report["plugins"])
    svc.set_paper_enabled(777, "public_demo", enabled=True, expected_revision=1)
    assert svc.inspect(777, "public_demo").enabled_for_paper
    assert not svc.inspect(777, "private_example").enabled_for_paper
    assert svc.audit(777, "public_demo")[-1]["action"] == "ENABLE_PAPER"
    m.close()


def test_service_upgrade_and_unregister_requires_revision(tmp_path):
    m = PluginManager(tmp_path / "db")
    svc = PluginSettingsService(m, operator_ids=frozenset({8}))
    raw = manifest()
    svc.register(8, raw, approved_sha256=sha(raw))
    upgraded = manifest(version="1.0.1")
    with pytest.raises(RevisionConflict):
        svc.upgrade(8, upgraded, approved_sha256=sha(upgraded), expected_revision=9)
    after = svc.upgrade(
        8, upgraded, approved_sha256=sha(upgraded), expected_revision=1,
    )
    assert after.engine_version == "1.0.1" and after.revision == 2
    assert svc.unregister(8, "public_demo", expected_revision=2) == 3
    with pytest.raises(ValueError, match="PLUGIN_UNKNOWN"):
        svc.inspect(8, "public_demo")
    m.close()


def _cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "naseri_markets.plugin_admin",
         "--db", str(tmp_path / "plugins.db"), *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


def test_cli_offline_metadata_lifecycle_and_restart(tmp_path):
    raw = manifest()
    file = tmp_path / "manifest.json"
    file.write_bytes(raw)
    assert _cli(tmp_path, "inventory").returncode == 0
    refused = _cli(tmp_path, "register", str(file), "--sha256", sha(raw))
    assert refused.returncode == 2
    assert "CONFIRM" in refused.stderr
    added = _cli(
        tmp_path, "--allow-metadata-writes", "register",
        str(file), "--sha256", sha(raw),
    )
    assert added.returncode == 0
    assert json.loads(added.stdout)["revision"] == 1
    before = json.loads(_cli(tmp_path, "health").stdout)
    assert before["plugins"][0]["code_installed"] is False
    changed = _cli(
        tmp_path, "--allow-metadata-writes", "enable",
        "public_demo", "--revision", "1",
    )
    assert json.loads(changed.stdout)["enabled_for_paper"] is True
    bad = _cli(
        tmp_path, "--allow-metadata-writes", "disable",
        "public_demo", "--revision", "1",
    )
    assert bad.returncode == 2
    off = _cli(
        tmp_path, "--allow-metadata-writes", "disable",
        "public_demo", "--revision", "2",
    )
    assert json.loads(off.stdout)["revision"] == 3
    deleted = _cli(
        tmp_path, "--allow-metadata-writes", "unregister",
        "public_demo", "--revision", "3",
    )
    assert json.loads(deleted.stdout) == {
        "engine_id": "public_demo", "removed_revision": 4,
        "code_deleted": False,
    }
    assert json.loads(_cli(tmp_path, "inventory").stdout) == []
    assert len(json.loads(_cli(tmp_path, "audit", "public_demo").stdout)) == 4


def test_cli_untrusted_descriptor_pin_and_symlink_fail_closed(tmp_path):
    raw = manifest()
    candidate = tmp_path / "manifest.json"
    candidate.write_bytes(raw)
    alias = tmp_path / "symlink"
    alias.symlink_to(candidate)
    a = _cli(tmp_path, "--allow-metadata-writes", "register",
             str(candidate), "--sha256", "0" * 64)
    b = _cli(tmp_path, "--allow-metadata-writes", "register",
             str(alias), "--sha256", sha(raw))
    assert a.returncode == 2 and b.returncode == 2
    assert json.loads(_cli(tmp_path, "inventory").stdout) == []


def test_no_live_or_private_code_retrieval_imports():
    roots = ROOT / "naseri_markets"
    contents = [ (roots / f).read_text() for f in (
        "plugin_admin.py", "plugin_manager.py", "plugin_settings.py",
    )]
    combined = "\n".join(contents)
    assert "private_nyfr_core" not in combined
    assert "subprocess.run(" not in combined
    assert "MetaTrader5" not in combined
