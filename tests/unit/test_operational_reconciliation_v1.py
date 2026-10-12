"""Stage 18 read-only four-ledger safety, crash triage and human review."""
from __future__ import annotations

import os
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from naseri_markets.core_api_v1 import CoreEventType, CoreInput, DataOrigin
from naseri_markets.market_data_engine_v1 import PriceBasis, VolumeSemantics
from naseri_markets.offline_recovery_review_v1 import record_operator_review
from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from naseri_markets.offline_runtime_supervisor_v1 import OfflineRuntimeSupervisor
from naseri_markets.operational_reconciliation_v1 import (
    RecoveryPaths, RecoveryRefused, evaluate_operational_recovery,
)
from test_offline_runtime_supervisor_v1 import (
    CORE, bars, panel_fixture, receipt, scheduled,
)


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def evidence(tmp_path, *, job_status="PENDING"):
    control, binding, view = panel_fixture(tmp_path, signals=True)
    runtime = tmp_path / "runtime.sqlite"
    paper = tmp_path / "paper.sqlite"
    signal = tmp_path / "signal.sqlite"
    with OfflineRuntimeSupervisor(runtime, panel=control, actor_id=123,
                                  enabled=True) as supervisor:
        job = scheduled(supervisor, binding, view)
        if job_status == "DONE":
            assert supervisor.run_due(receipt, now=bars()[-1].close_at,
                                      operator_ack=True)[0]["status"] == "DONE"
        if job_status == "CLAIMED":
            class SimulatedCrash(BaseException):
                pass
            def stop(_):
                raise SimulatedCrash()
            with pytest.raises(SimulatedCrash):
                supervisor.run_due(stop, now=bars()[-1].close_at, operator_ack=True)
        if job_status == "QUARANTINED":
            assert supervisor.run_due(lambda _: (_ for _ in ()).throw(OSError()),
                now=bars()[-1].close_at, operator_ack=True)[0]["status"] == "QUARANTINED"
    with sqlite3.connect(paper) as db:
        db.executescript("""
        CREATE TABLE paper_core_orders(order_id TEXT,instance_id TEXT,binding_id TEXT,account_id TEXT);
        CREATE TABLE paper_core_allocations(instance_id TEXT,policy_json TEXT);
        CREATE TABLE paper_core_bindings(binding_id TEXT,instance_id TEXT);
        CREATE TABLE paper_core_decisions(order_id TEXT);
        CREATE TABLE paper_risk_reservations(order_id TEXT);
        CREATE TABLE paper_orders(order_id TEXT,snapshot TEXT);
        CREATE TABLE paper_stage9_plans(order_id TEXT);
        CREATE TABLE paper_stage9_exits(order_id TEXT);
        CREATE TABLE paper_stage9_bars(order_id TEXT);
        """)
    with OfflineSignalLifecycle(signal, enabled=True):
        pass
    for name in (runtime, paper, signal, tmp_path / 'panel.sqlite'):
        name.chmod(0o600)
    return RecoveryPaths(runtime, tmp_path / "panel.sqlite", paper, signal), job, control, binding


def test_pending_not_claimed_complete(tmp_path):
    paths, job, control, _ = evidence(tmp_path)
    report = evaluate_operational_recovery(paths)
    assert report.jobs[0].job_id == job
    assert report.jobs[0].verdict == "PENDING_NOT_EXECUTED"
    assert report.cross_ledger_verdict != "PASS"  # no output is not a success
    assert not report.replay_authorized and not report.telegram_authorized
    assert report == evaluate_operational_recovery(paths)
    control.close()


def test_done_hash_not_exact_cross_ledger_proof(tmp_path):
    paths, _, control, _ = evidence(tmp_path, job_status="DONE")
    report = evaluate_operational_recovery(paths)
    assert report.jobs[0].verdict == "DONE_UNVERIFIED_CROSS_LEDGER"
    assert "NO_EXACT_JOB_TO_OUTPUT_ATTESTATION" in report.jobs[0].issues
    assert report.unverified_done_jobs == 1
    assert report.operator_review_required
    control.close()


def test_crash_requires_manual_reconciliation_not_auto_retry(tmp_path):
    paths, _, control, _ = evidence(tmp_path, job_status="CLAIMED")
    report = evaluate_operational_recovery(paths)
    assert report.status == "BLOCKED_MANUAL_RECONCILIATION"
    assert report.jobs[0].status == "CLAIMED"
    assert report.blocking_jobs == 1
    assert report.jobs[0].candidate_paper_orders == 0
    control.close()


def test_quarantine_still_requires_operator(tmp_path):
    paths, _, control, _ = evidence(tmp_path, job_status="QUARANTINED")
    report = evaluate_operational_recovery(paths)
    assert report.jobs[0].verdict == "BLOCKED_MANUAL_RECONCILIATION"
    control.close()


def test_digest_tamper_blocks_no_false_clean(tmp_path):
    paths, job, control, _ = evidence(tmp_path, job_status="DONE")
    with sqlite3.connect(paths.runtime) as db:
        db.execute("UPDATE runtime17_jobs SET payload='{}' WHERE job_id=?", (job,))
    report = evaluate_operational_recovery(paths)
    assert report.jobs[0].verdict == "BLOCKED_EVIDENCE_INVALID"
    control.close()


def test_cross_ledger_candidate_does_not_prove_job(tmp_path):
    paths, _, control, binding = evidence(tmp_path, job_status="DONE")
    with sqlite3.connect(paths.paper) as db:
        db.execute("INSERT INTO paper_core_orders VALUES(?,?,?,?)",
                   ("candidate_order", "demo_instance", binding.binding_id, "demo_account"))
    report = evaluate_operational_recovery(paths)
    assert report.jobs[0].candidate_paper_orders == 1
    assert report.jobs[0].verdict == "DONE_UNVERIFIED_CROSS_LEDGER"
    control.close()


def test_ambiguous_signal_claim_blocks(tmp_path):
    paths, _, control, binding = evidence(tmp_path, job_status="DONE")
    event = CoreInput(CORE.manifest.core_id, CORE.manifest.core_version,
                      binding, CoreEventType.CLOSED_CANDLE, bars()[-1].close_at,
                      DataOrigin.SYNTHETIC, "synthetic_fixture", bars())
    result = CORE.evaluate(event)
    with OfflineSignalLifecycle(paths.signal, enabled=True) as lifecycle:
        entry = result.decisions[0]
        s = lifecycle.register(CORE.manifest, event, result, entry,
                               channel_id=-10016, price_basis=PriceBasis.TRADE,
                               volume_semantics=VolumeSemantics.TRADED,
                               expires_at=event.observed_at + timedelta(minutes=30),
                               operator_ack=True)
        assert lifecycle.claim_dry_run(s.key, operator_ack=True)
    report = evaluate_operational_recovery(paths)
    assert report.jobs[0].candidate_signals == 1
    assert report.jobs[0].verdict == "BLOCKED_EVIDENCE_INVALID"
    assert "AMBIGUOUS_SIGNAL_DELIVERY_STATE" in report.jobs[0].issues
    control.close()


def test_review_requires_stop_ack_evidence_hash_and_is_idempotent(tmp_path):
    paths, job, control, _ = evidence(tmp_path, job_status="CLAIMED")
    report = evaluate_operational_recovery(paths)
    review_file = tmp_path / "review.sqlite"
    kwargs = dict(job_id=job, evidence_sha256=report.evidence_sha256,
                  note="Reviewed local crash; no retry approved", operator_id=123,
                  operator_ack=True, all_workers_stopped=True)
    with pytest.raises(RecoveryRefused, match="STOPPED_WORKERS"):
        record_operator_review(paths, review_file, **{**kwargs, "all_workers_stopped": False})
    assert not review_file.exists()
    out = record_operator_review(paths, review_file, **kwargs)
    assert out["status"] == "REVIEW_RECORDED_NO_RETRY"
    assert out == record_operator_review(paths, review_file, **kwargs)
    assert evaluate_operational_recovery(paths) == report
    with pytest.raises(RecoveryRefused, match="CONFLICTING_MANUAL_REVIEW"):
        record_operator_review(paths, review_file, **{**kwargs, "note": "Changed review note"})
    control.close()


def test_review_cannot_approve_done_or_change_evidence(tmp_path):
    paths, job, control, _ = evidence(tmp_path, job_status="DONE")
    report = evaluate_operational_recovery(paths)
    opts = dict(job_id=job, evidence_sha256=report.evidence_sha256,
                note="Manual review is restricted", operator_id=123,
                operator_ack=True, all_workers_stopped=True)
    with pytest.raises(RecoveryRefused, match="ONLY_INTERRUPTED"):
        record_operator_review(paths, tmp_path / "review.sqlite", **opts)
    with sqlite3.connect(paths.runtime) as db:
        db.execute("UPDATE runtime17_jobs SET error_code='new_evidence' WHERE job_id=?", (job,))
    with pytest.raises(RecoveryRefused, match="EVIDENCE_CHANGED"):
        record_operator_review(paths, tmp_path / "review.sqlite", **opts)
    control.close()


def test_denies_missing_file_symlinks_and_shared_roles(tmp_path):
    paths, _, control, _ = evidence(tmp_path)
    with pytest.raises(RecoveryRefused, match="SHARED_EVIDENCE"):
        evaluate_operational_recovery(RecoveryPaths(paths.runtime, paths.runtime,
                                                    paths.paper, paths.signal))
    missing = tmp_path / 'not_there.sqlite'
    with pytest.raises(RecoveryRefused, match="PRIVATE_EXISTING"):
        evaluate_operational_recovery(RecoveryPaths(missing, paths.control,
                                                    paths.paper, paths.signal))
    assert not missing.exists()
    link = tmp_path / "alias.sqlite"
    link.symlink_to(paths.runtime)
    with pytest.raises(RecoveryRefused, match="PRIVATE_EXISTING"):
        evaluate_operational_recovery(RecoveryPaths(link, paths.control,
                                                    paths.paper, paths.signal))
    control.close()


def test_production_env_blocks_read(tmp_path, monkeypatch):
    paths, _, control, _ = evidence(tmp_path)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(RecoveryRefused, match="NONPRODUCTION"):
        evaluate_operational_recovery(paths)
    control.close()


def test_actual_child_process_crash_persists_claimed_state(tmp_path):
    """Real process exit after durable Stage-17 claim, no implicit retry."""
    import subprocess
    import sys

    paths, job, control, _ = evidence(tmp_path)
    child_code = '''
import os
from datetime import UTC,datetime
from decimal import Decimal as D
from pathlib import Path
from naseri_markets.contracts import Market
from naseri_markets.example_dual_setup_core_v1 import DualSetupExampleCore
from naseri_markets.instrument_registry_v1 import InstrumentMetadata,ListingStatus,MetadataOrigin,ProviderSnapshot,ResearchInstrumentCatalog
from naseri_markets.offline_runtime_supervisor_v1 import OfflineRuntimeSupervisor
from naseri_markets.trading_control_center_v1 import CoreListing,OfflineTradingControlCenter
core=DualSetupExampleCore()
start=datetime(2026,10,12,10,tzinfo=UTC)
cat=ResearchInstrumentCatalog(max_age_seconds=86400)
origin=MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
meta=InstrumentMetadata("synthetic_provider",Market.CRYPTO,"ABCUSD","UTC","USD",D("0.01"),origin,ListingStatus.OPEN,start,"SYNTHETIC_FIXTURE")
cat.replace(ProviderSnapshot("synthetic_provider",origin,start,(meta,),"a"*64))
panel=OfflineTradingControlCenter(Path(os.environ["CONTROL"]),admin_ids={123},enabled=True,catalog=cat,listings=(CoreListing(core.manifest.core_id,"Public Demonstration Core",core.manifest.core_version,manifest=core.manifest),))
with OfflineRuntimeSupervisor(Path(os.environ["RUNTIME"]),panel=panel,actor_id=123,enabled=True) as scheduler:
    scheduler.run_due(lambda job: os._exit(77),now=start.replace(hour=11),operator_ack=True)
'''
    env = dict(os.environ, RUNTIME=str(paths.runtime), CONTROL=str(paths.control),
               PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    child = subprocess.run([sys.executable, "-c", child_code], env=env,
                           capture_output=True, timeout=8, check=False)
    assert child.returncode == 77, child.stderr.decode(errors="replace")[:200]
    report = evaluate_operational_recovery(paths)
    assert report.jobs[0].job_id == job
    assert report.jobs[0].status == "CLAIMED"
    assert report.status == "BLOCKED_MANUAL_RECONCILIATION"
    control.close()


def test_review_does_not_mutate_other_existing_database(tmp_path):
    paths, job, control, _ = evidence(tmp_path, job_status="CLAIMED")
    report = evaluate_operational_recovery(paths)
    unrelated = tmp_path / "other_private.sqlite"
    with sqlite3.connect(unrelated) as db:
        db.execute("CREATE TABLE application_data(value INTEGER)")
        db.execute("INSERT INTO application_data VALUES(123)")
    unrelated.chmod(0o600)
    with pytest.raises(RecoveryRefused, match="UNRELATED_REVIEW_DATABASE"):
        record_operator_review(
            paths, unrelated, job_id=job,
            evidence_sha256=report.evidence_sha256,
            note="Reviewed manually no restart", operator_id=123,
            operator_ack=True, all_workers_stopped=True)
    with sqlite3.connect(unrelated) as db:
        assert [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")] == ["application_data"]
        assert db.execute("SELECT value FROM application_data").fetchone() == (123,)
    control.close()
