"""Stage 3: genuine V5 evidence and atomic receipt / risk journal restart tests."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from naseri_markets import brooks_replay
from naseri_markets.brooks_replay import (
    replay_once, canonical_snapshot_identity, parse_candle_replay,
)
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore

SOURCE = Path(__file__).resolve().parents[2] / "production_source"
VERSION = "brooks-trilogy-full-core-v5-context-structural"


def payload():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(72):
        opened = start + timedelta(minutes=15 * i)
        bars.append({
            "open_time": opened.isoformat(),
            "close_time": (opened + timedelta(minutes=15)).isoformat(),
            "open": "100", "high": "101", "low": "99",
            "close": "100", "volume": "10"})
    return {
        "schema_version": 1, "origin": "replay",
        "market": "crypto", "provider": "binance_replay",
        "symbol": "BTCUSDT", "timezone": "UTC", "quote_currency": "USDT",
        "exchange": "binance", "market_type": "futures",
        "timeframe": "15m", "candles": bars,
    }


def wire(data):
    return json.dumps(data, sort_keys=True).encode()


def enable(state):
    with EngineControlStore(state) as host:
        s = host.get(BROOKS_ENGINE_ID)
        host.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True, actor_id=123,
            expected_revision=s.revision)
        pref = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment",
            value="PAPER", actor_id=123,
            expected_revision=pref["revision"])


def fake_result(data, decision):
    raw, _, bars = parse_candle_replay(wire(data))
    identity, hashvalue = canonical_snapshot_identity(raw, bars)
    return json.dumps({
        "decision": decision,
        "entry": "101" if decision != "NO_SIGNAL" else None,
        "stop": "99" if decision != "NO_SIGNAL" else None,
        "targets": ["105"] if decision != "NO_SIGNAL" else [],
        "setup_type": "FIXTURE_ONLY" if decision != "NO_SIGNAL" else None,
        "engine_version": VERSION,
        "configuration_version": "unit-only",
        "rule_ids": [],
        "snapshot_id": identity, "snapshot_hash": hashvalue,
    }).encode()


def test_real_frozen_v5_records_atomic_no_signal_or_risk_and_restarts(tmp_path):
    state = tmp_path / "private"
    enable(state)
    data = payload()
    first = replay_once(state_dir=state, legacy_source=SOURCE, replay_json=wire(data))
    with EngineControlStore(state) as host:
        receipt = host.brooks_paper_receipts(limit=1)[0]
        assert receipt["scan_id"] == first["scan_id"]
        assert receipt["decision"] == first["decision"]
        assert receipt["symbol"] == "BTCUSDT"
        assert receipt["timeframe"] == "15m"
        assert receipt["market_type"] == "futures"
        assert receipt["telegram_delivery_authorized"] is False
        assert receipt["broker_order_authorized"] is False
        assert host.brooks_replay_status()["receipts"] == 1
    # Simulates fresh process after crash/restart: reopen durable SQLite
    # and replay the identical source without duplicating scans or receipts.
    another = replay_once(state_dir=state, legacy_source=SOURCE, replay_json=wire(data))
    assert another["outcome"] == "DUPLICATE_SCAN"
    with EngineControlStore(state) as host:
        assert host.brooks_replay_status()["scans"] == 1
        assert host.brooks_replay_status()["receipts"] == 1
        assert host.brooks_paper_receipts(limit=1)[0] == receipt


def test_valid_long_paper_r_is_diagnostic_not_new_trading_threshold(
        tmp_path, monkeypatch):
    state = tmp_path / "private"
    enable(state)
    data = payload()
    packet = fake_result(data, "LONG")
    monkeypatch.setattr(
        brooks_replay.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=packet))
    result = replay_once(state_dir=state, legacy_source=SOURCE, replay_json=wire(data))
    assert result["outcome"] == "RECORDED"
    with EngineControlStore(state) as host:
        assert len(host.signals(BROOKS_ENGINE_ID)) == 1
        receipt = host.brooks_paper_receipts(limit=1)[0]
        assert receipt["risk_check"] == "VALIDATED_GEOMETRY"
        assert receipt["per_unit_risk"] == "2"
        assert receipt["target_reward_r"] == ["2"]
        assert receipt["signal_id"] == result["signal_id"]
        assert receipt["outcome"] == "RECORDED"
        assert host.publication(BROOKS_ENGINE_ID)["effective_publication"] is False
        assert host.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"


def test_atomic_failure_rolls_back_scan_signal_and_receipt(tmp_path, monkeypatch):
    state = tmp_path / "private"
    enable(state)
    data = payload()
    packet = fake_result(data, "LONG")
    monkeypatch.setattr(
        brooks_replay.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=packet))
    def refuse(_db, _receipt):
        raise ValueError("TEST_RECEIPT_STORAGE_FAILURE")
    monkeypatch.setattr(brooks_replay, "record_receipt", refuse)
    with pytest.raises(ValueError, match="TEST_RECEIPT_STORAGE_FAILURE"):
        replay_once(state_dir=state, legacy_source=SOURCE, replay_json=wire(data))
    with EngineControlStore(state) as host:
        assert host.brooks_replay_status()["scans"] == 0
        assert host.brooks_replay_status()["receipts"] == 0
        assert host.brooks_replay_status()["paper_signals"] == 0


def test_receipt_corruption_detected_on_read(tmp_path, monkeypatch):
    state = tmp_path / "private"
    enable(state)
    data = payload()
    monkeypatch.setattr(
        brooks_replay.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=fake_result(data, "NO_SIGNAL")))
    replay_once(state_dir=state, legacy_source=SOURCE, replay_json=wire(data))
    with EngineControlStore(state) as host:
        host._db.execute(
            "UPDATE brooks_paper_receipts SET receipt_json='{}'")
    with EngineControlStore(state) as host:
        with pytest.raises(ValueError, match="CORRUPTED"):
            host.brooks_paper_receipts()


def test_old_scan_is_retained_without_invented_receipt(tmp_path):
    state = tmp_path / "private"
    with EngineControlStore(state) as host:
        host._db.execute(
            "INSERT INTO brooks_replay_scans "
            "(scan_id,snapshot_hash,decision,setup_type,signal_id,source_sha256)"
            "VALUES(?,?,?,?,?,?)",
            ("old", "0" * 64, "NO_SIGNAL", None, None, "1" * 64))
    with EngineControlStore(state) as reopened:
        assert reopened.brooks_replay_status()["scans"] == 1
        assert reopened.brooks_replay_status()["receipts"] == 0
        assert reopened.brooks_paper_receipts() == []


@pytest.mark.asyncio
async def test_private_admin_displays_new_receipt_and_R_no_telegram(
        tmp_path, monkeypatch):
    pytest.importorskip("telegram")
    from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
    state = tmp_path / "private"
    enable(state)
    data = payload()
    packet = fake_result(data, "LONG")
    monkeypatch.setattr(
        brooks_replay.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=packet))
    replay_once(state_dir=state, legacy_source=SOURCE, replay_json=wire(data))
    panel = IntegratedEnginePanel(state_dir=state, admin_ids={123}, owner_ids={123})
    with EngineControlStore(state) as host:
        details = panel.detail(host, BROOKS_ENGINE_ID)
        assert "رسید حسابرسی PAPER: 1" in details
        assert "اعتبارسنجی ریسک: VALIDATED_GEOMETRY" in details
        assert "R هدف اول: 2" in details
        assert "انتشار به کانال: 🔒 DISABLED" in details


def test_dev_operator_status_and_bounded_receipt_query(tmp_path, monkeypatch,
                                                       capsys):
    from naseri_markets.dev_operator import main
    state = tmp_path / "private"
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    assert main(["--state-dir", str(state), "init",
                 "--ack-nonproduction-init"]) == 0
    assert main(["--state-dir", str(state), "receipts", "--limit", "2"]) == 0
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert output["mode"] == "OFFLINE_PAPER_AUDIT_ONLY"
    assert output["receipts"] == []
    assert output["telegram_sent"] is False
    assert main(["--state-dir", str(state), "receipts", "--limit", "0"]) == 2
