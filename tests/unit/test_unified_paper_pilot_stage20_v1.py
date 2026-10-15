"""Stage 20 operator-driven, two-binding integrated PAPER test corpus."""
from __future__ import annotations

import json

import pytest

from naseri_markets.unified_paper_pilot_stage20_v1 import main, run_paper_pilot


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def test_two_distinct_bindings_complete_closed_trades_and_audit(tmp_path):
    path = tmp_path / "first"
    report = run_paper_pilot(
        path, first_symbol="BTCUSD", second_symbol="ETHUSD",
        first_timeframe="5m", second_timeframe="1h")
    assert report["mode"] == "STAGE20_SYNTHETIC_PAPER_ONLY"
    assert report["core"] == "fixture.contract.check"
    assert report["completed_jobs"] == report["closed_paper_trades"] == 2
    assert report["dry_run_commands"] == 2
    assert report["exact_effects"] == 6
    assert report["restart_verified"]
    assert report["integrity_verdict"] == "PASS"
    assert report["release_verdict"] == "BLOCKED_NONPRODUCTION_UNATTESTED"
    assert {b["symbol"] for b in report["bindings"]} == {"BTCUSD", "ETHUSD"}
    assert {b["timeframe"] for b in report["bindings"]} == {"5m", "1h"}
    assert len({b["binding_id"] for b in report["bindings"]}) == 2
    assert len({b["order_id"] for b in report["bindings"]}) == 2
    assert {b["status"] for b in report["bindings"]} == {"CLOSED"}
    for flag in ("telegram_sent", "broker_order_sent", "real_feed_used",
                 "live_trading_enabled", "profitability_proven",
                 "public_release_authorized", "brooks_core_api_integrated"):
        assert report[flag] is False
    with pytest.raises(ValueError, match="NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED"):
        run_paper_pilot(path)


def test_paper_remains_on_when_no_send_intent_off(tmp_path):
    report = run_paper_pilot(tmp_path / "without_signals", dry_run_signals=False)
    assert report["closed_paper_trades"] == 2
    assert report["dry_run_commands"] == 0
    assert report["exact_effects"] == 4
    assert report["integrity_verdict"] == "PASS"


def test_production_and_invalid_specs_refused_without_writes(tmp_path, monkeypatch):
    path = tmp_path / "must_not_exist"
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(ValueError, match="NONPRODUCTION_REQUIRED"):
        run_paper_pilot(path)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="NONPRODUCTION_REQUIRED"):
        run_paper_pilot(path)
    monkeypatch.delenv("MMT_PRODUCTION")
    for kwargs in (
        {"first_symbol": "BTC/USDT"},
        {"second_symbol": "ABCUSD"},
        {"second_timeframe": "7m"},
    ):
        with pytest.raises(ValueError, match="TWO_DISTINCT_SYNTHETIC_BINDINGS_REQUIRED"):
            run_paper_pilot(path, **kwargs)
    assert not path.exists()
    actual = tmp_path / "actual"
    actual.mkdir()
    symlink = tmp_path / "alias"
    symlink.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED"):
        run_paper_pilot(symlink)


def test_operator_explicit_cli_ack(tmp_path, capsys):
    path = tmp_path / "cli"
    assert main(["--state-dir", str(path)]) == 2
    assert not path.exists()
    assert "STAGE20_PILOT_REFUSED" in capsys.readouterr().err
    assert main(["--state-dir", str(path), "--ack-synthetic-offline"]) == 0
    assert json.loads(capsys.readouterr().out)["completed_jobs"] == 2


def test_stage9_real_two_binding_pilot_receipts_and_frozen_crash_snapshots(tmp_path):
    """Real Stage-20 synthetic execution; Stage-9 observes only closed immutable copies."""
    import shutil
    import sqlite3

    from naseri_markets.job_effect_reconciliation_v1 import (
        EffectEvidencePaths, evaluate_recovery_decisions,
    )

    pilot = tmp_path / "stage20"
    run_paper_pilot(pilot, first_symbol="BTCUSD", second_symbol="ETHUSD",
                    first_timeframe="5m", second_timeframe="1h")
    paths = EffectEvidencePaths(
        pilot / "effects.sqlite", pilot / "runtime.sqlite",
        pilot / "paper.sqlite", pilot / "signals.sqlite",
    )
    with sqlite3.connect("file:" + str(paths.runtime) + "?mode=ro", uri=True) as db:
        jobs = [row[0] for row in db.execute(
            "SELECT job_id FROM runtime17_jobs ORDER BY job_id")]
    assert len(jobs) == len(set(jobs)) == 2
    expected = {
        job_id: ("DRY_SIGNAL", "PAPER_PLAN", "PAPER_RESERVE")
        for job_id in jobs
    }
    before = tuple(p.read_bytes() for p in (
        paths.effects, paths.runtime, paths.paper, paths.signal,
    ))
    outcome = evaluate_recovery_decisions(
        paths, expected_effect_kinds_by_job=expected,
        all_writers_stopped=True, operator_ack=True,
    )
    assert outcome == evaluate_recovery_decisions(
        paths, expected_effect_kinds_by_job=expected,
        all_writers_stopped=True, operator_ack=True,
    )
    assert outcome.reviewed_jobs == 2
    assert len(outcome.decisions) == 6
    assert not outcome.operator_review_required
    assert outcome.blocking_decisions == 0
    assert {d.classification for d in outcome.decisions} == {
        "EXACT_TARGET_AND_RECEIPT"
    }
    assert not outcome.auto_retry_authorized
    assert not outcome.cross_database_atomicity_proven
    assert before == tuple(p.read_bytes() for p in (
        paths.effects, paths.runtime, paths.paper, paths.signal,
    ))

    # Simulate a durable target commit followed by a failed job finalization
    # on an ISOLATED COPIED SNAPSHOT. Original Stage-20 evidence stays pristine.
    copy_dir = tmp_path / "crash_copy"
    copy_dir.mkdir(mode=0o700)
    for original in (paths.effects, paths.runtime, paths.paper, paths.signal):
        shutil.copy2(original, copy_dir / original.name)
    snapshot = EffectEvidencePaths(
        copy_dir / "effects.sqlite", copy_dir / "runtime.sqlite",
        copy_dir / "paper.sqlite", copy_dir / "signals.sqlite",
    )
    with sqlite3.connect(snapshot.runtime) as db:
        db.execute("UPDATE runtime17_jobs SET status='QUARANTINED' WHERE job_id=?",
                   (jobs[0],))
    snapshot_result = evaluate_recovery_decisions(
        snapshot, expected_effect_kinds_by_job=expected,
        all_writers_stopped=True, operator_ack=True,
    )
    assert snapshot_result.reviewed_jobs == 2
    assert snapshot_result.blocking_decisions >= 3
    assert any(
        d.job_id == jobs[0] and d.classification == "EXACT_TARGET_JOB_UNFINISHED"
        for d in snapshot_result.decisions
    )
    assert snapshot_result.decision_sha256 != outcome.decision_sha256
    assert not snapshot_result.auto_retry_authorized
    assert not snapshot_result.ledger_repair_authorized
    assert before == tuple(p.read_bytes() for p in (
        paths.effects, paths.runtime, paths.paper, paths.signal,
    ))
