"""New installed preview operator: explicit initiation, health and clean stop."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from naseri_markets import dev_operator
from naseri_markets.engine_control_store import (
    BROOKS_ENGINE_ID, EngineControlStore,
)

SOURCE = Path(__file__).resolve().parents[2] / "production_source"


@pytest.fixture
def dev(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.delenv("MMT_DEV_BOT_TOKEN", raising=False)


def call(folder, *rest):
    return dev_operator.main(["--state-dir", str(folder), *rest])


def test_initializer_and_status_no_feed_no_telegram_no_order(tmp_path, dev, capsys):
    state = tmp_path / "private"
    assert call(state, "status") == 2
    assert not state.exists()
    assert call(state, "init") == 2
    assert not state.exists()
    assert call(state, "init", "--ack-nonproduction-init") == 0
    assert state.stat().st_mode & 0o777 == 0o700
    with EngineControlStore(state) as store:
        assert not store.get(BROOKS_ENGINE_ID).requested_enabled
        assert store.preferences(BROOKS_ENGINE_ID)["signal_environment"] == "OFF"
    assert call(state, "status") == 0
    answer = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert answer["worker_phase"] == "NOT_INSTALLED"
    assert answer["selected_feed_eligible"] is False
    assert answer["iran_futures_eligibility_verified"] is False
    assert answer["effective_channel_publication"] is False
    assert answer["real_orders_enabled"] is False
    assert answer["legacy_database_attached"] is False


def test_permission_and_symlink_denial(tmp_path, dev):
    state = tmp_path / "operator"
    assert call(state, "init", "--ack-nonproduction-init") == 0
    state.chmod(0o755)
    assert call(state, "status") == 2
    state.chmod(0o700)
    link = tmp_path / "alias"
    link.symlink_to(state)
    assert call(link, "status") == 2


def test_worker_genuine_frozen_source_idles_for_iran_and_stops(tmp_path, dev, capsys):
    state = tmp_path / "operator"
    assert call(state, "init", "--ack-nonproduction-init") == 0
    with EngineControlStore(state) as store:
        core = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=core.revision, actor_id=123)
        prefs = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=123)
    assert call(state, "worker", "--legacy-source", str(SOURCE),
                "--ack-nonproduction-worker", "--max-steps", "1") == 0
    with EngineControlStore(state) as store:
        assert store.brooks_worker_status()["phase"] == "STOPPED"
        assert store.brooks_replay_status()["scans"] == 0
        assert store.publication(BROOKS_ENGINE_ID)["effective_publication"] is False
    assert "BROOKS_IRAN_FUTURES_ELIGIBILITY_UNVERIFIED" in capsys.readouterr().out


def test_no_implicit_launch_or_untrusted_product_identity(tmp_path, dev, monkeypatch):
    state = tmp_path / "operator"
    monkeypatch.delenv("MMT_NONPRODUCTION")
    assert call(state, "init", "--ack-nonproduction-init") == 2
    assert not state.exists()
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    assert call(state, "init", "--ack-nonproduction-init") == 2
    assert not state.exists()
    monkeypatch.delenv("MMT_PRODUCTION")
    assert call(state, "init", "--ack-nonproduction-init") == 0
    assert call(state, "panel", "--admin-ids", "123",
                "--ack-nonproduction-panel") == 2
    assert call(state, "worker", "--legacy-source", str(SOURCE)) == 2
    assert call(state, "run", "--legacy-source", str(SOURCE),
                "--admin-ids", "123") == 2


def test_panel_application_mount_offline_without_network(tmp_path, dev):
    pytest.importorskip("telegram")
    from telegram.ext import CallbackQueryHandler, CommandHandler
    from naseri_markets.bot_admin_app import build_admin_application
    state = tmp_path / "operator"
    assert call(state, "init", "--ack-nonproduction-init") == 0
    app = build_admin_application(
        token="123456:NONPRODUCTION_TEST_TOKEN",
        state_dir=state, admin_ids={123}, owner_ids={123})
    handlers = [h for group in app.handlers.values() for h in group]
    command_names = set().union(*(
        h.commands for h in handlers if isinstance(h, CommandHandler)))
    assert {"engines", "custom"} <= command_names
    assert any(isinstance(h, CallbackQueryHandler) and
               h.pattern.match("ep:list:123456abcdef")
               for h in handlers)
    # Only checked PTB registration: no bot.initialize() or network polling.


def test_foreground_supervisor_terminates_both_peers_on_early_exit(
        tmp_path, dev, monkeypatch):
    state = tmp_path / "operator"
    assert call(state, "init", "--ack-nonproduction-init") == 0
    monkeypatch.setenv("MMT_DEV_BOT_TOKEN", "123456:NONPRODUCTION_TEST_TOKEN")
    monkeypatch.setattr(dev_operator, "_source", lambda path: SOURCE)
    history = []

    class FakeProcess:
        def __init__(self, argv):
            self.argv = argv
            self.waited = False
            self.terminated = False
            history.append(self)

        def poll(self):
            # Simulate panel failing on first liveness poll.
            return 3 if self is history[1] else (
                -15 if self.terminated else None)

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            self.waited = True
            return -15

        def kill(self):
            self.terminated = True

    monkeypatch.setattr(dev_operator.subprocess, "Popen", FakeProcess)
    code = call(state, "run", "--legacy-source", str(SOURCE),
                "--admin-ids", "123", "--owner-ids", "123",
                "--ack-nonproduction-suite")
    assert code == 2
    assert len(history) == 2
    assert history[0].terminated and history[0].waited and history[1].waited
    assert all("NONPRODUCTION_TEST_TOKEN" not in " ".join(x.argv)
               for x in history)


def test_supervisor_fails_before_any_spawn_on_missing_secrets(
        tmp_path, dev, monkeypatch):
    state = tmp_path / "operator"
    assert call(state, "init", "--ack-nonproduction-init") == 0
    child = []
    monkeypatch.setattr(
        dev_operator.subprocess, "Popen",
        lambda *a, **k: child.append(a))
    assert call(state, "run", "--legacy-source", str(SOURCE),
                "--admin-ids", "123",
                "--ack-nonproduction-suite") == 2
    assert child == []
