"""Public Brooks REAL V5 offline replay integration with the unified PAPER journal.

One genuine worker end-to-end and isolated mock transport tests. No network,
production database, Telegram send, private NYFR source or broker orders.
"""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from naseri_markets import brooks_replay
from naseri_markets.brooks_replay import (
    BrooksReplayRefused, canonical_snapshot_identity,
    parse_candle_replay, replay_once, verify_legacy_source,
)
from naseri_markets.engine_control_store import (
    BROOKS_ENGINE_ID, OWNER_CORE_ID, EngineControlStore,
)

LEGACY = Path(__file__).resolve().parents[2] / "production_source"
ENGINE_VERSION = "brooks-trilogy-full-core-v5-context-structural"


@pytest.fixture
def replay():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(72):
        opened = start + timedelta(minutes=15 * i)
        candles.append({
            "open_time": opened.isoformat(),
            "close_time": (opened + timedelta(minutes=15)).isoformat(),
            "open": "100", "high": "101", "low": "99", "close": "100",
            "volume": "10",
        })
    return {
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_replay", "symbol": "BTCUSDT",
        "timezone": "UTC", "quote_currency": "USDT",
        "exchange": "binance", "market_type": "futures",
        "timeframe": "15m", "candles": candles,
    }


def encoded(replay: dict) -> bytes:
    return json.dumps(replay, separators=(",", ":"), sort_keys=True).encode()


@pytest.fixture
def enabled(tmp_path):
    state = tmp_path / "private"
    with EngineControlStore(state) as host:
        before = host.get(BROOKS_ENGINE_ID)
        assert not before.requested_enabled
        host.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True, expected_revision=before.revision,
            actor_id=123)
        prefs = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=123)
    return state


def fake_worker_report(replay: dict, *, decision="LONG") -> bytes:
    raw, _, bars = parse_candle_replay(encoded(replay))
    snapshot_id, snapshot_hash = canonical_snapshot_identity(raw, bars)
    return json.dumps({
        "decision": decision, "entry": "101" if decision != "NO_SIGNAL" else None,
        "stop": "99" if decision != "NO_SIGNAL" else None,
        "targets": ["105"] if decision != "NO_SIGNAL" else [],
        "setup_type": "TEST_TRANSPORT_CONTRACT" if decision != "NO_SIGNAL" else None,
        "engine_version": ENGINE_VERSION,
        "rule_set_version": "brooks-trilogy-full-source-catalog-v6",
        "configuration_version": "books-full-policy-test",
        "rule_ids": ["BB-RNG-26-TWO-REASONS"],
        "snapshot_id": snapshot_id, "snapshot_hash": snapshot_hash,
    }, sort_keys=True).encode()


def test_actual_manifest_checks_all_legacy_source_files():
    manifest_hash = verify_legacy_source(LEGACY)
    assert len(manifest_hash) == 64
    assert manifest_hash == verify_legacy_source(LEGACY)


def test_closed_bars_and_exact_identity(replay):
    raw, instrument, bars = parse_candle_replay(encoded(replay))
    identity, digest = canonical_snapshot_identity(raw, bars)
    assert identity.endswith(str(int(bars[-1]["close_time"].timestamp() * 1000)))
    assert len(digest) == 64
    assert instrument.symbol == "BTCUSDT"
    assert len(bars) == 72


def test_genuine_frozen_brooks_engine_evaluates_real_candles_and_replays_idempotently(
        enabled, replay):
    result = replay_once(
        state_dir=enabled, legacy_source=LEGACY, replay_json=encoded(replay))
    assert result["mode"] == "OFFLINE_REPLAY_PAPER"
    assert result["decision"] in {"NO_SIGNAL", "LONG", "SHORT"}
    assert result["outcome"] in {"NO_SIGNAL", "RECORDED"}
    assert not result["telegram_sent"]
    assert not result["live_publication_enabled"]
    with EngineControlStore(enabled, owner_visible=False) as store:
        recorded = store.signals(BROOKS_ENGINE_ID)
        metrics = store.brooks_replay_status()
        assert metrics["scans"] == 1
        assert metrics["paper_signals"] == len(recorded)
        assert not metrics["live_runtime_connected"]
        assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        assert store.get(OWNER_CORE_ID) is None
        if result["decision"] == "NO_SIGNAL":
            assert recorded == []
            assert metrics["no_signal"] == 1
        else:
            assert len(recorded) == 1
            assert recorded[0]["evidence_mode"] == "paper"
            assert recorded[0]["engine_id"] == BROOKS_ENGINE_ID
    repeated = replay_once(
        state_dir=enabled, legacy_source=LEGACY, replay_json=encoded(replay))
    assert repeated["outcome"] == "DUPLICATE_SCAN"
    assert repeated["stored"] == 0
    with EngineControlStore(enabled) as store:
        assert store.brooks_replay_status()["scans"] == 1
        assert store.brooks_replay_status()["paper_signals"] == result["stored"]


@pytest.mark.parametrize("change,reason", [
    (lambda x: x.update(origin="forward"), "OFFLINE"),
    (lambda x: x.update(market="forex"), "OFFLINE"),
    (lambda x: x.update(schema_version=True), "VERSION"),
    (lambda x: x.update(timeframe="2m"), "UNSUPPORTED"),
    (lambda x: x.update(timeframe=["15m"]), "UNSUPPORTED"),
    (lambda x: x.update(candles=x["candles"][:30]), "CANDLE_COUNT"),
    (lambda x: x["candles"][-1].update(open="NaN"), "INVALID_DECIMAL"),
    (lambda x: x["candles"][-1].update(close="102"), "GEOMETRY"),
    (lambda x: x["candles"][-1].update(close_time="2026-01-02T00:00:00+00:00"),
     "CANDLE_GAP"),
])
def test_invalid_noncausal_or_wrong_market_replay_rejected(replay, change, reason):
    change(replay)
    with pytest.raises(BrooksReplayRefused, match=reason):
        parse_candle_replay(encoded(replay))


def test_reject_duplicate_json_keys_and_unverified_source(replay, enabled, tmp_path):
    raw = encoded(replay).replace(b'"origin":"replay"', b'"origin":"replay","origin":"replay"')
    with pytest.raises(BrooksReplayRefused, match="DUPLICATE"):
        parse_candle_replay(raw)
    with pytest.raises(BrooksReplayRefused, match="FROZEN_SOURCE"):
        replay_once(
            state_dir=enabled, legacy_source=tmp_path / "bad",
            replay_json=encoded(replay))


def test_permission_off_timeframe_and_market_scope_block_without_worker(
        tmp_path, replay):
    state = tmp_path / "state"
    with pytest.raises(BrooksReplayRefused, match="NOT_ENABLED"):
        replay_once(state_dir=state, legacy_source=LEGACY, replay_json=encoded(replay))
    with EngineControlStore(state) as host:
        host.toggle_as_admin(BROOKS_ENGINE_ID, enabled=True,
                             expected_revision=1, actor_id=123)
    with pytest.raises(BrooksReplayRefused, match="NOT_ENABLED"):
        replay_once(state_dir=state, legacy_source=LEGACY, replay_json=encoded(replay))
    with EngineControlStore(state) as host:
        pref = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(BROOKS_ENGINE_ID, field="signal_environment",
                               value="PAPER", expected_revision=pref["revision"],
                               actor_id=123)
        pref = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(BROOKS_ENGINE_ID, field="timeframe",
                               value="1h", expected_revision=pref["revision"],
                               actor_id=123)
    with pytest.raises(BrooksReplayRefused, match="NOT_ENABLED"):
        replay_once(state_dir=state, legacy_source=LEGACY, replay_json=encoded(replay))
    with EngineControlStore(state) as host:
        pref = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(BROOKS_ENGINE_ID, field="timeframe",
                               value="15m", expected_revision=pref["revision"],
                               actor_id=123)
        pref = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(BROOKS_ENGINE_ID, field="market_scope",
                               value="forex", expected_revision=pref["revision"],
                               actor_id=123)
    with pytest.raises(BrooksReplayRefused, match="NOT_ENABLED"):
        replay_once(state_dir=state, legacy_source=LEGACY, replay_json=encoded(replay))


def test_mock_transport_long_persists_real_typed_paper_intent_and_no_telegram(
        monkeypatch, enabled, replay):
    # This is a transport-contract test stub, NOT a claim that this replay
    # organically produced a Brooks setup. Actual engine is tested above.
    packet = fake_worker_report(replay)
    monkeypatch.setattr(
        brooks_replay.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=packet))
    result = replay_once(
        state_dir=enabled, legacy_source=LEGACY, replay_json=encoded(replay))
    assert result["decision"] == "LONG"
    assert result["outcome"] == "RECORDED"
    assert result["stored"] == 1
    assert result["signal_id"].startswith("brooks-")
    with EngineControlStore(enabled) as store:
        signal = store.signals(BROOKS_ENGINE_ID)[0]
        assert signal["direction"] == "long"
        assert signal["evidence_mode"] == "paper"
        assert signal["entry"] == "101"
        assert signal["stop"] == "99"
        assert store.route(BROOKS_ENGINE_ID)["live_publication_enabled"] is False
        assert store.publication(BROOKS_ENGINE_ID)["effective_publication"] is False


def test_worker_snapshot_forgery_fails_closed_without_journal(
        monkeypatch, enabled, replay):
    obj = json.loads(fake_worker_report(replay))
    obj["snapshot_hash"] = "0" * 64
    monkeypatch.setattr(
        brooks_replay.subprocess, "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout=json.dumps(obj).encode()))
    with pytest.raises(BrooksReplayRefused, match="SNAPSHOT_MISMATCH"):
        replay_once(state_dir=enabled, legacy_source=LEGACY, replay_json=encoded(replay))
    with EngineControlStore(enabled) as host:
        assert host.brooks_replay_status()["scans"] == 0
        assert host.signals(BROOKS_ENGINE_ID) == []


def test_revoked_engine_mid_scan_fails_closed_and_no_signals(
        monkeypatch, enabled, replay):
    packet = fake_worker_report(replay)
    def revoke(*args, **kwargs):
        with EngineControlStore(enabled) as host:
            state = host.get(BROOKS_ENGINE_ID)
            host.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=False, expected_revision=state.revision,
                actor_id=123)
        return SimpleNamespace(returncode=0, stdout=packet)
    monkeypatch.setattr(brooks_replay.subprocess, "run", revoke)
    with pytest.raises(BrooksReplayRefused, match="NOT_ENABLED"):
        replay_once(state_dir=enabled, legacy_source=LEGACY, replay_json=encoded(replay))
    with EngineControlStore(enabled) as host:
        assert host.brooks_replay_status()["scans"] == 0
        assert host.signals(BROOKS_ENGINE_ID) == []


def test_mid_scan_setting_change_fails_closed(monkeypatch, enabled, replay):
    packet = fake_worker_report(replay)
    def change(*args, **kwargs):
        with EngineControlStore(enabled) as host:
            pref = host.preferences(BROOKS_ENGINE_ID)
            host.change_preference(BROOKS_ENGINE_ID,
                                   field="timeframe", value="1h",
                                   expected_revision=pref["revision"],
                                   actor_id=123)
        return SimpleNamespace(returncode=0, stdout=packet)
    monkeypatch.setattr(brooks_replay.subprocess, "run", change)
    with pytest.raises(BrooksReplayRefused, match="NOT_ENABLED"):
        replay_once(state_dir=enabled, legacy_source=LEGACY, replay_json=encoded(replay))
    with EngineControlStore(enabled) as host:
        assert host.brooks_replay_status()["scans"] == 0


def test_legacy_engine_worker_no_source_install_if_bad_manifest(
        tmp_path, replay):
    fake = tmp_path / "not-legacy"
    fake.mkdir()
    (fake / "SHA256SUMS").write_text("invalid")
    with pytest.raises(BrooksReplayRefused, match="MANIFEST_COUNT"):
        verify_legacy_source(fake)


def test_public_cli_offline_and_bounded_replay(enabled, replay, tmp_path):
    from naseri_markets.brooks_replay import main
    path = tmp_path / "replay.json"
    path.write_bytes(encoded(replay))
    assert main([
        "--state-dir", str(enabled),
        "--legacy-source", str(LEGACY),
        "--replay", str(path),
    ]) == 0
