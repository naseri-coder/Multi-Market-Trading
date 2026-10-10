"""Long-running development Brooks PAPER service: real controls, no production."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from naseri_markets import brooks_paper_service as service
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.trusted_custom import LocalCustomRefused

SOURCE = Path(__file__).resolve().parents[2] / "production_source"
START = datetime(2026, 1, 1, tzinfo=UTC)
CLOCK = START + timedelta(minutes=72 * 15 + 5)


def arm(folder):
    with EngineControlStore(folder) as host:
        core = host.get(BROOKS_ENGINE_ID)
        host.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=core.revision, actor_id=123)
        pref = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment",
            value="PAPER", expected_revision=pref["revision"], actor_id=123)


def revoke(folder):
    with EngineControlStore(folder) as host:
        core = host.get(BROOKS_ENGINE_ID)
        host.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=False,
            expected_revision=core.revision, actor_id=123)


def report(*, now=CLOCK, outcome="RECORDED", timeframe="15m"):
    return {
        "symbol": "PF_XBTUSD",
        "market_feed": "KRAKEN_FUTURES_TRADE_PUBLIC_HTTPS",
        "outcome": outcome, "decision": "NO_SIGNAL",
        "telegram_sent": False, "live_publication_enabled": False,
        "timeframe": timeframe,
        "last_closed_candle": (
            now - timedelta(minutes=5)).isoformat(),
    }


def test_absent_worker_never_claims_panel_is_running(tmp_path):
    with EngineControlStore(tmp_path / "state") as host:
        state = host.brooks_worker_status(now=int(CLOCK.timestamp()))
        assert state["phase"] == "NOT_INSTALLED"
        assert not state["connected"]
        assert not host.get(BROOKS_ENGINE_ID).enabled
    arm(tmp_path / "state")
    with EngineControlStore(tmp_path / "state") as host:
        assert not host.brooks_worker_status(now=int(CLOCK.timestamp()))["connected"]


def test_real_panel_control_drives_worker_no_hidden_start(tmp_path):
    folder = tmp_path / "state"
    seen = []
    current = [float(CLOCK.timestamp())]

    def fake_reader(**kwargs):
        seen.append(kwargs)
        return report(now=datetime.fromtimestamp(current[0], tz=UTC))

    worker = service.BrooksPaperService(
        state_dir=folder, legacy_source=SOURCE,
        reader=fake_reader, clock=lambda: current[0])
    worker.start()
    try:
        assert worker.step() == {"phase": "IDLE", "attempted": False}
        assert not seen
        with EngineControlStore(folder) as host:
            assert host.brooks_worker_status(now=int(current[0]))["connected"]
            assert host.brooks_worker_status(now=int(current[0]))["phase"] == "IDLE"
        arm(folder)
        result = worker.step()
        assert result["attempted"]
        assert result["outcome"] == "RECORDED"
        assert len(seen) == 1
        # No redundant per-second analysis on the same closed 15m bar.
        assert worker.step()["phase"] == "WAITING"
        assert len(seen) == 1
        with EngineControlStore(folder) as host:
            telemetry = host.brooks_worker_status(now=int(current[0]))
            assert telemetry["phase"] == "WAITING"
            assert telemetry["completed_cycles"] == 1
            assert telemetry["refused_cycles"] == 0
        revoke(folder)
        assert worker.step()["phase"] == "IDLE"
        assert len(seen) == 1
        arm(folder)
        assert worker.step()["attempted"] is True
        assert len(seen) == 2
        with EngineControlStore(folder) as host:
            assert not host.publication(BROOKS_ENGINE_ID)["effective_publication"]
            assert host.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
    finally:
        worker.shutdown()
    with EngineControlStore(folder) as host:
        after = host.brooks_worker_status(now=int(current[0]))
        assert after["phase"] == "STOPPED"
        assert not after["connected"]
        assert after["completed_cycles"] == 2


def test_worker_fails_closed_with_bounded_backoff_and_recovers(tmp_path):
    folder = tmp_path / "state"
    arm(folder)
    now = [CLOCK.timestamp()]
    calls = []

    def fake_reader(**kwargs):
        calls.append(True)
        if len(calls) == 1:
            from naseri_markets.brooks_kraken_feed import KrakenFeedRefused
            raise KrakenFeedRefused("KRAKEN_FEED_HTTP_429")
        return report(now=datetime.fromtimestamp(now[0], tz=UTC),
                      outcome="NO_SIGNAL")

    worker = service.BrooksPaperService(
        state_dir=folder, legacy_source=SOURCE,
        reader=fake_reader, clock=lambda: now[0])
    worker.start()
    try:
        assert worker.step()["phase"] == "DEGRADED"
        assert worker.next_attempt_at == CLOCK.timestamp() + 10
        assert worker.step()["phase"] == "WAITING"
        assert len(calls) == 1
        now[0] += 11
        assert worker.step()["outcome"] == "NO_SIGNAL"
        assert len(calls) == 2
        with EngineControlStore(folder) as host:
            assert host.brooks_worker_status(now=int(now[0]))["refused_cycles"] == 1
            assert host.brooks_worker_status(now=int(now[0]))["completed_cycles"] == 1
    finally:
        worker.shutdown()


def test_status_lease_stale_cas_and_duplicate_owner_fenced(tmp_path):
    folder = tmp_path / "state"
    id1, id2 = "a" * 32, "b" * 32
    with EngineControlStore(folder) as host:
        host.brooks_worker_claim(worker_id=id1, now=1000)
        with pytest.raises(LocalCustomRefused, match="ALREADY_RUNNING"):
            host.brooks_worker_claim(worker_id=id2, now=1001)
        host.brooks_worker_heartbeat(
            worker_id=id1, now=1002, phase="ANALYZING")
        assert host.brooks_worker_status(now=1010)["connected"]
        assert host.brooks_worker_status(now=1035)["phase"] == "STALE"
        assert not host.brooks_worker_status(now=1035)["connected"]
        host.brooks_worker_claim(worker_id=id2, now=1035)
        with pytest.raises(LocalCustomRefused, match="STALE_OWNER"):
            host.brooks_worker_heartbeat(worker_id=id1, now=1036, phase="IDLE")
        host.brooks_worker_heartbeat(worker_id=id2, now=1036, phase="STOPPED")
        assert not host.brooks_worker_status(now=1036)["connected"]


def test_singleton_file_lock_enforced(tmp_path):
    folder = tmp_path / "state"
    folder.mkdir()
    with service.exclusive_worker_lock(folder):
        with pytest.raises(service.BrooksServiceRefused, match="ALREADY_RUNNING"):
            with service.exclusive_worker_lock(folder):
                pass
    child = folder / ".brooks-kraken-paper-worker.lock"
    child.unlink()
    child.symlink_to(folder / "dummy")
    with pytest.raises(service.BrooksServiceRefused, match="LOCK_SYMLINK"):
        with service.exclusive_worker_lock(folder):
            pass


def test_startup_never_implicit_and_nonproduction_ack_required(tmp_path, monkeypatch):
    folder = tmp_path / "state"
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    assert service.main([
        "--state-dir", str(folder), "--legacy-source", str(SOURCE)]) == 2
    assert not folder.exists()
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    assert service.main([
        "--state-dir", str(folder), "--legacy-source", str(SOURCE),
        "--ack-nonproduction-standalone-paper", "--max-steps", "1"]) == 2
    assert not folder.exists()


def test_service_report_integrity_fails_closed_no_fake_success(tmp_path):
    folder = tmp_path / "state"
    arm(folder)
    worker = service.BrooksPaperService(
        state_dir=folder, legacy_source=SOURCE,
        reader=lambda **kwargs: {
            **report(), "telegram_sent": True,
        }, clock=lambda: CLOCK.timestamp())
    worker.start()
    try:
        step = worker.step()
        assert step["phase"] == "DEGRADED"
        assert step["reason"] == "BROOKS_WORKER_REPORT_INTEGRITY"
        with EngineControlStore(folder) as host:
            state = host.brooks_worker_status(now=int(CLOCK.timestamp()))
            assert state["completed_cycles"] == 0
            assert state["refused_cycles"] == 1
    finally:
        worker.shutdown()


@pytest.mark.asyncio
async def test_private_admin_panel_displays_actual_heartbeat_and_toggle(tmp_path):
    pytest.importorskip("telegram")
    from naseri_markets.custom_admin_panel import _token
    from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
    folder = tmp_path / "state"
    panel = IntegratedEnginePanel(
        state_dir=folder, admin_ids={123}, owner_ids={123})
    owner = "c" * 32
    with EngineControlStore(folder) as host:
        host.brooks_worker_claim(worker_id=owner, now=int(CLOCK.timestamp()))
        # Details must not claim an active worker when heartbeat becomes stale.
        assert "سرویس Kraken Futures: STALE" in panel.detail(
            host, BROOKS_ENGINE_ID)
    # For actual fresh state, use real wall-clock time in the lease.
    import time
    with EngineControlStore(folder) as host:
        host.brooks_worker_heartbeat(
            worker_id=owner, now=int(time.time()), phase="IDLE")
        assert "سرویس Kraken Futures: IDLE" in panel.detail(host, BROOKS_ENGINE_ID)
        keyboard = panel.keyboard(host, BROOKS_ENGINE_ID)
        actions = [b.callback_data for row in keyboard.inline_keyboard for b in row]
        assert f"cm:enable:{_token(BROOKS_ENGINE_ID)}:1" in actions
    token = _token(BROOKS_ENGINE_ID)
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=123, type="private"),
        effective_message=message,
        callback_query=SimpleNamespace(
            data=f"cm:enable:{token}:1",
            answer=AsyncMock(), message=message))
    await panel.callback(update, SimpleNamespace(user_data={}))
    with EngineControlStore(folder) as host:
        assert host.get(BROOKS_ENGINE_ID).requested_enabled
        assert not host.publication(BROOKS_ENGINE_ID)["effective_publication"]
        assert host.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
