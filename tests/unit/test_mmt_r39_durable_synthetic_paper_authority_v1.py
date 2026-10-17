"""R39 durable synthetic-only operator handoff, crash and reopen contracts."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from naseri_markets import offline_authoritative_paper_journey_r39_v1 as r39

REAL_GATE = r39._gate


@pytest.fixture
def scratch(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    home = tmp_path / "owner"
    home.mkdir(mode=0o700)
    # Only the test gate is replaced so root CI can exercise disposable
    # SQLite contract logic; a real non-root operator acceptance is pending.
    def allow(*, operator_ack, writers_stopped=None):
        if operator_ack is not True or writers_stopped is False:
            raise r39.PaperAuthorityRefused("R39_TEST_ACK_REQUIRED")
    monkeypatch.setattr(r39, "_gate", allow)

    def report(dry):
        return {
            "mode": "STAGE20_SYNTHETIC_PAPER_ONLY",
            "core": "fixture.contract.check",
            "completed_jobs": 2,
            "closed_paper_trades": 2,
            "dry_run_commands": 2 if dry else 0,
            "exact_effects": 6 if dry else 4,
            "restart_verified": True,
            "integrity_verdict": "PASS",
            "release_verdict": "BLOCKED_NONPRODUCTION_UNATTESTED",
            "bindings": [
                {"symbol": symbol, "timeframe": timeframe,
                 "binding_id": "fixture_" + symbol,
                 "order_id": "paper_" + symbol, "status": "CLOSED"}
                for symbol, timeframe in (("BTCUSD", "5m"), ("ETHUSD", "15m"))
            ],
            "telegram_sent": False,
            "broker_order_sent": False,
            "real_feed_used": False,
            "live_trading_enabled": False,
            "profitability_proven": False,
            "public_release_authorized": False,
            "brooks_core_api_integrated": False,
        }

    def reopen(dry):
        return {
            "runtime_jobs_done": 2,
            "paper_orders": 2,
            "paper_plans": 2,
            "paper_exits": 2,
            "dry_signal_commands": 2 if dry else 0,
            "exact_initial_effects": 6 if dry else 4,
            "integrity_verdict": "PASS",
            "release_verdict": "BLOCKED_NONPRODUCTION_UNATTESTED",
            "reliability_sha256": "a" * 64,
            "recovery_decision_sha256": "b" * 64,
            "source_authenticated": False,
            "live_trading_enabled": False,
            "broker_order_sent": False,
            "telegram_sent": False,
            "profitability_proven": False,
            "public_release_authorized": False,
            "automatic_recovery_authorized": False,
            "exactly_once_guaranteed": False,
        }

    def fake_run(folder, *, dry_run_signals, **kwargs):
        folder.mkdir(mode=0o700)
        (folder / "synthetic.marker").write_text("fixture only")
        return report(dry_run_signals)

    def fake_reopen(directory, *, expected_dry_signals, **kwargs):
        assert directory.is_dir()
        return reopen(expected_dry_signals)

    monkeypatch.setattr(r39, "run_paper_pilot", fake_run)
    monkeypatch.setattr(r39, "inspect_installed_paper", fake_reopen)
    return home, report, reopen


def _done(home: Path, *, dry=True) -> Path:
    workspace = home / "job"
    result = r39.run_new(workspace, dry_run_signals=dry, operator_ack=True)
    assert result["status"] == "DONE"
    return workspace


def test_durable_done_with_saved_hash_and_release_denied(scratch):
    home, _, _ = scratch
    folder = _done(home)
    row = r39._read_state(folder)
    assert row["status"] == "DONE"
    assert row["fixture_id"] == r39._FIXTURE_ID
    assert row["report_sha256"]
    answer = r39.inspect(folder, dry_run_signals=True,
                         operator_ack=True, all_writers_stopped=True)
    assert answer["verdict"] == "R39_READONLY_PAPER_REOPEN_PASS_RELEASE_DENIED"
    assert answer["files_written"] is False
    assert answer["auto_retry_authorized"] is False
    assert answer["live_authorized"] is False


def test_readonly_reopen_does_not_modify_authority_bytes(scratch):
    home, _, _ = scratch
    folder = _done(home)
    before = (folder / "authority.sqlite").read_bytes()
    first = r39.inspect(folder, dry_run_signals=True,
                        operator_ack=True, all_writers_stopped=True)
    second = r39.inspect(folder, dry_run_signals=True,
                         operator_ack=True, all_writers_stopped=True)
    assert first == second
    assert before == (folder / "authority.sqlite").read_bytes()


def test_completed_job_cannot_be_rerun(scratch):
    home, _, _ = scratch
    folder = _done(home)
    with pytest.raises(r39.PaperAuthorityRefused, match="NEW_EXCLUSIVE"):
        r39.run_new(folder, operator_ack=True)
    assert r39._read_state(folder)["status"] == "DONE"


def test_failure_after_partial_downstream_write_is_quarantined(scratch, monkeypatch):
    home, _, _ = scratch
    def failed(folder, **kwargs):
        folder.mkdir(mode=0o700)
        (folder / "partial.marker").write_bytes(b"unknown effect")
        raise RuntimeError("simulated interrupted stage")
    monkeypatch.setattr(r39, "run_paper_pilot", failed)
    folder = home / "crash"
    with pytest.raises(r39.PaperAuthorityRefused, match="MANUAL_RECONCILIATION"):
        r39.run_new(folder, operator_ack=True)
    assert (folder / "pilot" / "partial.marker").exists()
    assert r39._read_state(folder)["status"] == "QUARANTINED"
    with pytest.raises(r39.PaperAuthorityRefused, match="MANUAL_RECOVERY_ONLY"):
        r39.inspect(folder, dry_run_signals=True, operator_ack=True,
                    all_writers_stopped=True)
    with pytest.raises(r39.PaperAuthorityRefused, match="NEW_EXCLUSIVE"):
        r39.run_new(folder, operator_ack=True)


def test_report_with_broker_order_flag_quarantined(scratch, monkeypatch):
    home, report, _ = scratch
    def unsafe(folder, *, dry_run_signals, **kwargs):
        folder.mkdir(mode=0o700)
        result = report(dry_run_signals)
        result["broker_order_sent"] = True
        return result
    monkeypatch.setattr(r39, "run_paper_pilot", unsafe)
    folder = home / "unsafe"
    with pytest.raises(r39.PaperAuthorityRefused, match="MANUAL_RECONCILIATION"):
        r39.run_new(folder, operator_ack=True)
    assert r39._read_state(folder)["status"] == "QUARANTINED"


def test_reopen_digest_drift_blocks_but_does_not_mutate(scratch, monkeypatch):
    home, _, reopen = scratch
    folder = _done(home)
    before = (folder / "authority.sqlite").read_bytes()
    def drift(*args, **kwargs):
        obj = reopen(kwargs["expected_dry_signals"])
        obj["reliability_sha256"] = "c" * 64
        return obj
    monkeypatch.setattr(r39, "inspect_installed_paper", drift)
    with pytest.raises(r39.PaperAuthorityRefused, match="REOPEN_EVIDENCE_DRIFT"):
        r39.inspect(folder, dry_run_signals=True, operator_ack=True,
                    all_writers_stopped=True)
    assert before == (folder / "authority.sqlite").read_bytes()


def test_request_mode_mismatch_refused(scratch):
    home, _, _ = scratch
    folder = _done(home)
    with pytest.raises(r39.PaperAuthorityRefused, match="REQUEST_MISMATCH"):
        r39.inspect(folder, dry_run_signals=False,
                    operator_ack=True, all_writers_stopped=True)


def test_corrupt_stored_report_detected(scratch):
    home, _, _ = scratch
    folder = _done(home)
    with sqlite3.connect(folder / "authority.sqlite") as db:
        db.execute("UPDATE r39_journeys SET report_json='{}'")
    with pytest.raises(r39.PaperAuthorityRefused, match="RECORDED_REPORT_DRIFT"):
        r39.inspect(folder, dry_run_signals=True,
                    operator_ack=True, all_writers_stopped=True)


def test_crash_before_done_commit_requires_manual_recovery(scratch):
    home, _, _ = scratch
    folder = _done(home)
    with sqlite3.connect(folder / "authority.sqlite") as db:
        db.execute("UPDATE r39_journeys SET status='PENDING'")
    with pytest.raises(r39.PaperAuthorityRefused, match="MANUAL_RECOVERY_ONLY"):
        r39.inspect(folder, dry_run_signals=True, operator_ack=True,
                    all_writers_stopped=True)


def test_no_dry_signal_mode_still_paper_only(scratch):
    home, _, _ = scratch
    folder = _done(home, dry=False)
    result = r39.inspect(folder, dry_run_signals=False,
                         operator_ack=True, all_writers_stopped=True)
    assert result["auto_retry_authorized"] is False
    assert result["live_authorized"] is False


def test_explicit_writers_stopped_ack_required(scratch):
    home, _, _ = scratch
    folder = _done(home)
    with pytest.raises(r39.PaperAuthorityRefused, match="TEST_ACK_REQUIRED"):
        r39.inspect(folder, dry_run_signals=True,
                    operator_ack=True, all_writers_stopped=False)


def test_invalid_dry_mode_refused_without_creating_workspace(scratch):
    home, _, _ = scratch
    folder = home / "invalid"
    with pytest.raises(r39.PaperAuthorityRefused, match="INVALID_DRY_RUN_MODE"):
        r39.run_new(folder, dry_run_signals=1, operator_ack=True)
    assert not folder.exists()


def test_nonprivate_parent_and_symlink_rejected(scratch):
    home, _, _ = scratch
    world = home / "world"
    world.mkdir(mode=0o755)
    with pytest.raises(r39.PaperAuthorityRefused, match="PRIVATE_OWNER_PARENT"):
        r39.run_new(world / "job", operator_ack=True)
    link = home / "linked"
    link.symlink_to(world, target_is_directory=True)
    with pytest.raises(r39.PaperAuthorityRefused, match="PRIVATE_OWNER_PARENT"):
        r39.run_new(link / "job", operator_ack=True)


@pytest.mark.parametrize("value", ["1", "0", "true", ""])
def test_original_production_gate_rejects_any_env_value(scratch, monkeypatch, value):
    monkeypatch.setenv("MMT_PRODUCTION", value)
    monkeypatch.setattr(r39.sys, "version_info", (3, 12, 3))
    monkeypatch.setattr(r39.os, "geteuid", lambda: 2000)
    # Bypass the fixture's test-only _gate replacement.
    with pytest.raises(r39.PaperAuthorityRefused, match="NONROOT_PY312_NONPRODUCTION"):
        REAL_GATE(operator_ack=True)


def test_real_stage20_and_stage10_integrated_synthetic_fixture(scratch, monkeypatch):
    """Real existing multi-DB synthetic pipeline, no external service or strategy."""
    from naseri_markets.unified_paper_pilot_stage20_v1 import run_paper_pilot
    from naseri_markets.installed_paper_pilot_stage10_v1 import inspect_installed_paper

    home, _, _ = scratch
    monkeypatch.setattr(r39, "run_paper_pilot", run_paper_pilot)
    monkeypatch.setattr(r39, "inspect_installed_paper", inspect_installed_paper)
    folder = home / "real_fixture"
    outcome = r39.run_new(folder, operator_ack=True)
    assert outcome["status"] == "DONE"
    assert outcome["broker_order_sent"] is False
    assert outcome["live_authorized"] is False
    assert r39.inspect(folder, dry_run_signals=True, operator_ack=True,
                       all_writers_stopped=True)["status"] == "DONE"


def test_cli_missing_ack_is_refused(scratch, capsys):
    home, _, _ = scratch
    path = home / "cli_missing_ack"
    assert r39.main(["--workspace", str(path), "--run-new"]) == 2
    assert not path.exists()
    assert "R39_PAPER_AUTHORITY_REFUSED" in capsys.readouterr().err


def test_cli_run_and_inspect_checked(scratch, capsys):
    home, _, _ = scratch
    path = home / "cli"
    assert r39.main(["--workspace", str(path), "--run-new",
                     "--ack-synthetic-offline"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "DONE"
    assert r39.main(["--workspace", str(path), "--inspect",
                     "--ack-synthetic-offline", "--ack-writers-stopped"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "DONE"
