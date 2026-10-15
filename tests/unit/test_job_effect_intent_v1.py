"""Stage 19 exact-effect preflight, atomic record, audit and fail-closed recovery."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.core_api_v1 import ClosedCandle
from naseri_markets.job_effect_intent_v1 import (
    OfflineJobEffectLedger, IntentRefused,
    _paper_order_id,
)
from naseri_markets.job_effect_reconciliation_v1 import (
    EffectEvidencePaths, evaluate_effect_evidence,
)
from naseri_markets.offline_runtime_supervisor_v1 import ReplayJob


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _fixture(tmp_path):
    now = datetime(2026, 10, 12, 10, tzinfo=UTC)
    a = ClosedCandle(now, now + timedelta(minutes=15), D(100), D(102), D(98), D(100), D(10))
    b = ClosedCandle(a.close_at, a.close_at + timedelta(minutes=15), D(100), D(108), D(99), D(106), D(10))
    return ReplayJob("job17_" + "a" * 64, "sample_instance", "sample_binding", 3,
                     "stage19_synthetic", (a, b))


def test_disabled_and_unsafe_paths_rejected(tmp_path, monkeypatch):
    path = tmp_path / "effects.sqlite"
    with pytest.raises(IntentRefused, match="PRIVATE_ABSOLUTE_STATE"):
        OfflineJobEffectLedger(tmp_path / "missing" / "effects.sqlite", enabled=True)
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(IntentRefused, match="NONPRODUCTION"):
        OfflineJobEffectLedger(path, enabled=True)
    assert not path.exists()


def test_pre_call_durable_and_immutable_no_retry(tmp_path):
    job = _fixture(tmp_path)
    path = tmp_path / "effects.sqlite"
    with OfflineJobEffectLedger(path, enabled=True) as journal:
        ident = journal.prepare(job, kind="PAPER_RESERVE", target_id="pc8_demo",
                                request_digest="c" * 64, decision_id="decision_one",
                                event_digest="b" * 64)
        assert ident.startswith("ef19_")
        assert journal.intents()[0]["state"] == "PREPARED"
        with pytest.raises(IntentRefused, match="NO_AUTO_REPLAY"):
            journal.prepare(job, kind="PAPER_RESERVE", target_id="pc8_demo",
                            request_digest="c" * 64, decision_id="decision_one",
                            event_digest="b" * 64)
    with OfflineJobEffectLedger(path, enabled=True) as resumed:
        assert resumed.intents()[0]["state"] == "PREPARED"
        with pytest.raises(IntentRefused, match="NO_AUTO_REPLAY"):
            resumed.prepare(job, kind="PAPER_RESERVE", target_id="pc8_demo",
                            request_digest="c" * 64, decision_id="decision_one",
                            event_digest="b" * 64)
        resumed.recorded(ident, target_id="pc8_demo", receipt={"order_id": "pc8_demo"})
        assert resumed.intents()[0]["state"] == "RECORDED"
        with pytest.raises(IntentRefused, match="STALE_OR_MISMATCHED"):
            resumed.recorded(ident, target_id="pc8_demo", receipt={"order_id": "pc8_demo"})


def test_prepared_and_recorded_are_distinct(tmp_path):
    job = _fixture(tmp_path)
    with OfflineJobEffectLedger(tmp_path / "effects.sqlite", enabled=True) as led:
        item = led.prepare(job, kind="DRY_SIGNAL", target_id="d" * 64,
                           request_digest="e" * 64, decision_id="one",
                           event_digest="f" * 64)
        assert led.intents()[0]["receipt_sha256"] is None
        led.recorded(item, target_id="d" * 64, receipt={"revision": 1})
        assert len(led.db.execute("SELECT * FROM effect19_events").fetchall()) == 2


def test_reject_spoofed_receipt_and_invalid_intent(tmp_path):
    job = _fixture(tmp_path)
    with OfflineJobEffectLedger(tmp_path / "effects.sqlite", enabled=True) as led:
        with pytest.raises(IntentRefused, match="INVALID_EFFECT"):
            led.prepare(job, kind="BROKER_ORDER", target_id="external",
                        request_digest="a" * 64, decision_id="one",
                        event_digest="b" * 64)
        key = led.prepare(job, kind="PAPER_PLAN", target_id="pc8_test",
                          request_digest="a" * 64, decision_id="one",
                          event_digest="b" * 64)
        with pytest.raises(IntentRefused, match="MISMATCHED"):
            led.recorded(key, target_id="different", receipt={})
        assert led.intents()[0]["state"] == "PREPARED"


def _store(tmp_path, *, effect_kind="PAPER_RESERVE", recorded=False, remote=True,
           forged=False, runtime_state="DONE"):
    job = _fixture(tmp_path)
    paths = EffectEvidencePaths(tmp_path / "effects.sqlite",
                                tmp_path / "runtime.sqlite",
                                tmp_path / "paper.sqlite",
                                tmp_path / "signal.sqlite")
    kind = effect_kind
    target = {"PAPER_RESERVE": "pc8_test", "PAPER_PLAN": "pc8_plan",
              "DRY_SIGNAL": "signal_key"}[kind]
    digest = "b" * 64
    if kind == "PAPER_PLAN":
        from naseri_markets.job_effect_intent_v1 import _sha, _wire
        expected_plan = {"decision_id": "decision_one",
                         "instance_id": "sample_instance",
                         "binding_id": "sample_binding",
                         "source_ref": "stage19_synthetic"}
        digest = _sha(_wire(expected_plan))
    with OfflineJobEffectLedger(paths.effects, enabled=True) as led:
        iid = led.prepare(job, kind=kind, target_id=target,
                          request_digest=digest, decision_id="decision_one",
                          event_digest="a" * 64)
        if recorded:
            led.recorded(iid, target_id=target, receipt={"target": target})
    r = sqlite3.connect(paths.runtime)
    r.execute("CREATE TABLE runtime17_jobs(job_id TEXT PRIMARY KEY,status TEXT,instance_id TEXT,binding_id TEXT,payload TEXT)")
    r.execute("INSERT INTO runtime17_jobs VALUES(?,?,?,?,?)",
              (job.job_id, runtime_state, job.instance_id, job.binding_id, "{}"))
    r.commit(); r.close()
    p = sqlite3.connect(paths.paper)
    p.execute("CREATE TABLE paper_core_orders(order_id TEXT,instance_id TEXT,binding_id TEXT)")
    p.execute("CREATE TABLE paper_core_decisions(binding_id TEXT,decision_id TEXT,request_digest TEXT,order_id TEXT)")
    p.execute("CREATE TABLE paper_stage9_plans(order_id TEXT,plan_json TEXT,binding_digest TEXT)")
    if remote and kind == "PAPER_RESERVE":
        p.execute("INSERT INTO paper_core_orders VALUES('pc8_test','sample_instance','sample_binding')")
        p.execute("INSERT INTO paper_core_decisions VALUES(?,?,?,?)",
                  (job.binding_id, "decision_one", "c" * 64 if forged else "b" * 64,
                   target))
    if remote and kind == "PAPER_PLAN":
        from naseri_markets.job_effect_intent_v1 import _wire
        plan = {"decision_id": "decision_one", "instance_id": "sample_instance",
                "binding_id": "sample_binding", "source_ref": "stage19_synthetic"}
        p.execute("INSERT INTO paper_stage9_plans VALUES(?,?,?)",
                  (target, _wire(plan), "a" * 64))
    p.commit(); p.close()
    s = sqlite3.connect(paths.signal)
    s.execute("CREATE TABLE offline_signal_states(signal_key TEXT, initial_digest TEXT,instance_id TEXT,binding_id TEXT,decision_id TEXT,source_ref TEXT)")
    s.execute("CREATE TABLE offline_signal_commands(signal_key TEXT,state TEXT)")
    if remote and kind == "DRY_SIGNAL":
        s.execute("INSERT INTO offline_signal_states VALUES(?,?,?,?,?,?)",
                  (target, "c" * 64 if forged else "b" * 64,
                   "sample_instance", "sample_binding", "decision_one", "stage19_synthetic"))
    s.commit(); s.close()
    for evidence_file in (paths.runtime, paths.paper, paths.signal):
        evidence_file.chmod(0o600)
    return paths


@pytest.mark.parametrize("recorded,remote,expected", [
    (True, True, "EXACT_OFFLINE_EFFECT_CONFIRMED"),
    (False, True, "EFFECT_PRESENT_RECEIPT_GAP_MANUAL_REVIEW"),
    (False, False, "UNKNOWN_NO_TARGET_NOT_SAFE_TO_RETRY"),
    (True, False, "UNKNOWN_NO_TARGET_NOT_SAFE_TO_RETRY"),
])
def test_reconcile_exact_reserve(tmp_path, recorded, remote, expected):
    paths = _store(tmp_path, recorded=recorded, remote=remote)
    report = evaluate_effect_evidence(paths)
    assert report.findings[0].verdict == expected
    assert report.auto_retry_authorized is False
    assert report.broker_orders_authorized is False
    assert report.telegram_send_authorized is False
    assert report.live_trading_authorized is False


def test_reconcile_signal_evidence_and_ambiguous_state(tmp_path):
    paths = _store(tmp_path, effect_kind="DRY_SIGNAL", recorded=True)
    assert evaluate_effect_evidence(paths).exact_local_effects == 1
    with sqlite3.connect(paths.signal) as s:
        s.execute("INSERT INTO offline_signal_commands VALUES('signal_key','UNKNOWN')")
    assert evaluate_effect_evidence(paths).findings[0].verdict == "BLOCKED_AMBIGUOUS_DELIVERY"


def test_reconcile_detects_target_forgery(tmp_path):
    paths = _store(tmp_path, recorded=True, forged=True)
    assert evaluate_effect_evidence(paths).findings[0].verdict == "BLOCKED_INCONSISTENT_EVIDENCE"


def test_reconcile_refuses_chain_tamper(tmp_path):
    paths = _store(tmp_path, recorded=True)
    with sqlite3.connect(paths.effects) as e:
        e.execute("UPDATE effect19_events SET payload_hash=? WHERE seq=1", ("f" * 64,))
    with pytest.raises(IntentRefused, match="TAMPERED_EFFECT_AUDIT_CHAIN"):
        evaluate_effect_evidence(paths)


def test_reconcile_after_job_crash_never_authorizes_retry(tmp_path):
    paths = _store(tmp_path, recorded=False, remote=True, runtime_state="CLAIMED")
    report = evaluate_effect_evidence(paths)
    assert report.findings[0].verdict == "EFFECT_PRESENT_RECEIPT_GAP_MANUAL_REVIEW"
    assert report.operator_review_required


def test_prohibit_shared_file_roles_and_symlinks(tmp_path):
    paths = _store(tmp_path)
    with pytest.raises(IntentRefused, match="SHARED_EVIDENCE"):
        evaluate_effect_evidence(EffectEvidencePaths(paths.effects, paths.effects,
                                                      paths.paper, paths.signal))
    aliased = tmp_path / "alias.sqlite"
    aliased.symlink_to(paths.signal)
    with pytest.raises(IntentRefused, match="PRIVATE_ABSOLUTE"):
        evaluate_effect_evidence(EffectEvidencePaths(paths.effects, paths.runtime,
                                                      paths.paper, aliased))


def test_no_production_mode(tmp_path, monkeypatch):
    paths = _store(tmp_path)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(IntentRefused, match="NONPRODUCTION"):
        evaluate_effect_evidence(paths)


def test_exact_order_id_stable():
    assert _paper_order_id("binding_a", "decision_b") == _paper_order_id(
        "binding_a", "decision_b")
    assert _paper_order_id("binding_a", "decision_b") != _paper_order_id(
        "binding_a", "decision_c")


# Stage 9 deliberately exercises the EXISTING three Stage-19 effect kinds,
# with every crash cutpoint treated as local evidence, never as a retry permit.
def _stage9(paths, kind, *, stopped=True, ack=True, expected=None):
    from naseri_markets.job_effect_reconciliation_v1 import (
        evaluate_recovery_decisions,
    )

    job = _fixture(paths.effects.parent)
    return evaluate_recovery_decisions(
        paths,
        expected_effect_kinds_by_job={job.job_id: (kind,) if expected is None
                                      else expected},
        operator_ack=ack, all_writers_stopped=stopped,
    )


@pytest.mark.parametrize("kind", ["PAPER_RESERVE", "PAPER_PLAN", "DRY_SIGNAL"])
@pytest.mark.parametrize("recorded,remote,state,classification", [
    (False, False, "CLAIMED", "PREPARED_NO_TARGET_UNKNOWN"),
    (False, True, "QUARANTINED", "TARGET_EXISTS_RECEIPT_GAP"),
    (True, True, "CLAIMED", "EXACT_TARGET_JOB_UNFINISHED"),
    (True, True, "DONE", "EXACT_TARGET_AND_RECEIPT"),
    (True, False, "DONE", "RECORDED_TARGET_MISSING_CONFLICT"),
])
def test_stage9_crash_cutpoint_matrix_is_readonly_and_deterministic(
    tmp_path, kind, recorded, remote, state, classification,
):
    paths = _store(tmp_path, effect_kind=kind, recorded=recorded,
                   remote=remote, runtime_state=state)
    evidence_paths = (paths.effects, paths.runtime, paths.paper, paths.signal)
    frozen_bytes = tuple(p.read_bytes() for p in evidence_paths)
    report = _stage9(paths, kind)
    assert report == _stage9(paths, kind)
    assert report.decisions[0].classification == classification
    assert report.reviewed_jobs == 1
    assert len(report.source_evidence_sha256) == len(report.decision_sha256) == 64
    assert (report.blocking_decisions == 0) == (
        classification == "EXACT_TARGET_AND_RECEIPT"
    )
    assert report.operator_review_required == bool(report.blocking_decisions)
    assert not report.auto_retry_authorized
    assert not report.ledger_repair_authorized
    assert not report.telegram_send_authorized
    assert not report.broker_orders_authorized
    assert not report.live_trading_authorized
    assert not report.exactly_once_proven
    assert not report.cross_database_atomicity_proven
    assert not report.operator_expected_set_independently_attested
    assert frozen_bytes == tuple(p.read_bytes() for p in evidence_paths)


def test_stage9_missing_runtime_job_is_included_and_blocked(tmp_path):
    paths = _store(tmp_path, recorded=True, remote=True)
    with sqlite3.connect(paths.runtime) as db:
        db.execute("DELETE FROM runtime17_jobs")
    report = _stage9(paths, "PAPER_RESERVE")
    assert report.decisions[0].classification == "MISSING_JOB"
    assert report.blocking_decisions == 1


def test_stage9_ambiguous_signal_outbox_is_not_retryable(tmp_path):
    paths = _store(tmp_path, effect_kind="DRY_SIGNAL",
                   recorded=True, remote=True)
    with sqlite3.connect(paths.signal) as db:
        db.execute("INSERT INTO offline_signal_commands VALUES(?,?)",
                   ("signal_key", "CLAIMED"))
    report = _stage9(paths, "DRY_SIGNAL")
    assert report.decisions[0].classification == "AMBIGUOUS_SIGNAL_OUTBOX"
    assert report.decisions[0].action == "BLOCKED_OPERATOR_REVIEW"


@pytest.mark.parametrize("wrong_map", [
    {"another_job": ("PAPER_RESERVE",)},
    {},
    {"another_job": ("PAPER_RESERVE",), "unused": ("DRY_SIGNAL",)},
])
def test_stage9_incomplete_operator_job_inventory_refused(tmp_path, wrong_map):
    from naseri_markets.job_effect_reconciliation_v1 import (
        evaluate_recovery_decisions,
    )
    paths = _store(tmp_path, recorded=True, remote=True)
    with pytest.raises(IntentRefused, match="EXPECTED_JOB_MAP|JOB_INVENTORY"):
        evaluate_recovery_decisions(
            paths, expected_effect_kinds_by_job=wrong_map,
            operator_ack=True, all_writers_stopped=True,
        )


@pytest.mark.parametrize("expected", [
    ("PAPER_RESERVE", "PAPER_RESERVE"),
    ("PAPER_PLAN", "DRY_SIGNAL"),
    ("PAPER_RESERVE", "BAD_KIND"),
    ["PAPER_RESERVE"],
])
def test_stage9_noncanonical_expected_effect_list_refused(tmp_path, expected):
    paths = _store(tmp_path, recorded=True)
    with pytest.raises(IntentRefused, match="EXPECTED_EFFECT"):
        _stage9(paths, "PAPER_RESERVE", expected=expected)


def test_stage9_declared_but_missing_effect_detected_despite_done_job(tmp_path):
    paths = _store(tmp_path, recorded=True, remote=True)
    report = _stage9(paths, "PAPER_RESERVE",
                     expected=("PAPER_PLAN", "PAPER_RESERVE"))
    kinds = {(d.kind, d.classification) for d in report.decisions}
    assert ("PAPER_RESERVE", "EXACT_TARGET_AND_RECEIPT") in kinds
    assert ("PAPER_PLAN", "MISSING_EFFECT_INTENT") in kinds
    assert report.blocking_decisions == 1


def test_stage9_unexpected_effect_is_not_laundered_by_exact_receipt(tmp_path):
    paths = _store(tmp_path, recorded=True, remote=True)
    report = _stage9(paths, "PAPER_RESERVE", expected=())
    assert any(d.classification == "UNEXPECTED_OR_DUPLICATE_EFFECT_INTENT"
               for d in report.decisions)
    assert report.operator_review_required


def test_stage9_pending_empty_job_is_observed_without_safety_grant(tmp_path):
    from naseri_markets.job_effect_reconciliation_v1 import (
        evaluate_recovery_decisions,
    )
    paths = _store(tmp_path, recorded=True, remote=True)
    job = _fixture(tmp_path)
    extra_id = "job17_" + "f" * 64
    with sqlite3.connect(paths.runtime) as db:
        db.execute("INSERT INTO runtime17_jobs VALUES(?,?,?,?,?)",
                   (extra_id, "PENDING", "some_instance", "some_binding", "{}"))
    report = evaluate_recovery_decisions(
        paths,
        expected_effect_kinds_by_job={
            job.job_id: ("PAPER_RESERVE",),
            extra_id: (),
        },
        operator_ack=True, all_writers_stopped=True,
    )
    assert report.reviewed_jobs == 2
    assert any(d.classification == "PENDING_NO_DISPATCH" for d in report.decisions)
    assert report.blocking_decisions == 0
    assert not report.auto_retry_authorized


def test_stage9_done_job_without_effect_has_no_completion_proof(tmp_path):
    from naseri_markets.job_effect_reconciliation_v1 import (
        evaluate_recovery_decisions,
    )
    paths = _store(tmp_path, recorded=True, remote=True)
    job = _fixture(tmp_path)
    extra_id = "job17_" + "f" * 64
    with sqlite3.connect(paths.runtime) as db:
        db.execute("INSERT INTO runtime17_jobs VALUES(?,?,?,?,?)",
                   (extra_id, "DONE", "some_instance", "some_binding", "{}"))
    report = evaluate_recovery_decisions(
        paths,
        expected_effect_kinds_by_job={job.job_id: ("PAPER_RESERVE",), extra_id: ()},
        operator_ack=True, all_writers_stopped=True,
    )
    assert "JOB_HAS_NO_EFFECT_PROOF" in [d.classification for d in report.decisions]
    assert report.operator_review_required


def test_stage9_no_audit_without_stop_all_writers_and_ack(tmp_path):
    paths = _store(tmp_path, recorded=True, remote=True)
    for ack, stopped in ((False, True), (True, False), (False, False)):
        with pytest.raises(IntentRefused, match="STOP_WRITERS"):
            _stage9(paths, "PAPER_RESERVE", ack=ack, stopped=stopped)


def test_stage9_production_disabled_and_audit_chain_not_bypassed(tmp_path, monkeypatch):
    paths = _store(tmp_path, recorded=True, remote=True)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(IntentRefused, match="NONPRODUCTION"):
        _stage9(paths, "PAPER_RESERVE")
    monkeypatch.delenv("MMT_PRODUCTION")
    with sqlite3.connect(paths.effects) as db:
        db.execute("UPDATE effect19_events SET chain_hash=? WHERE seq=1",
                   ("f" * 64,))
    with pytest.raises(IntentRefused, match="TAMPERED_EFFECT_AUDIT_CHAIN"):
        _stage9(paths, "PAPER_RESERVE")


def test_stage9_operator_declared_set_changes_decision_digest(tmp_path):
    paths = _store(tmp_path, recorded=True, remote=True)
    baseline = _stage9(paths, "PAPER_RESERVE", expected=("PAPER_RESERVE",))
    changed = _stage9(paths, "PAPER_RESERVE",
                      expected=("PAPER_PLAN", "PAPER_RESERVE"))
    assert baseline.source_evidence_sha256 == changed.source_evidence_sha256
    assert baseline.decision_sha256 != changed.decision_sha256
