"""A3 crash-persistent, no-auto-retry quarantine acceptance.

Mocked host only: these tests never launch Docker or execute an uploaded core.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle,
    CoreBinding,
    CoreEventType,
    CoreInput,
    DataOrigin,
)
from naseri_markets.durable_runtime_a3 import (
    DurableOfflineRuntime,
    DurableRuntimeLedger,
    DurableRuntimeRefused,
    _fingerprint,
)
from naseri_markets.multilang_runtime_a1 import (
    MultilangRefused,
    MultiLanguageOfflineHost,
    RuntimeKind,
)

FIXTURE = OfflineContractFixture()
NOW = datetime(2026, 10, 13, 10, tzinfo=UTC)
ARTIFACT = b"def evaluate(event):\n    return [{'decision_id': 'fixture', 'kind': 'no_setup'}]\n"
PIN = hashlib.sha256(ARTIFACT).hexdigest()


def _event(binding_id="synthetic_bind") -> CoreInput:
    binding = CoreBinding(
        "synthetic_inst", binding_id,
        Instrument(Market.CRYPTO, "synthetic_source", "ABCUSD", "UTC", "USD"),
        "15m",
    )
    candles = (
        ClosedCandle(
            NOW, NOW + timedelta(minutes=15), D(100), D(102),
            D(98), D(100), D(10),
        ),
        ClosedCandle(
            NOW + timedelta(minutes=15), NOW + timedelta(minutes=30),
            D(100), D(108), D(99), D(106), D(11),
        ),
    )
    return CoreInput(
        FIXTURE.manifest.core_id, FIXTURE.manifest.core_version,
        binding, CoreEventType.CLOSED_CANDLE, candles[-1].close_at,
        DataOrigin.SYNTHETIC, "fixed_research_fixture", candles,
    )


def _mock_host(monkeypatch, *, outcome="success"):
    host = MultiLanguageOfflineHost()
    monkeypatch.setattr(host, "status", lambda: {
        "python": "REVIEWED_WORKER_POLICY",
    })
    calls = []

    def perform(*args, **kwargs):
        calls.append((args, kwargs))
        if outcome == "fail":
            raise ValueError("MOCK_WORKER_FAILURE")
        if outcome == "interrupt":
            raise KeyboardInterrupt("SIMULATED_POWER_LOSS")
        return "INERT_TEST_RESULT"

    monkeypatch.setattr(host, "evaluate", perform)
    return host, calls


def _eval(host, ledger, event=None, *, ack=True):
    return DurableOfflineRuntime(host, ledger).evaluate(
        RuntimeKind.PYTHON, FIXTURE.manifest, event or _event(),
        artifact_name="test.py", artifact=ARTIFACT,
        approved_sha256=PIN, operator_ack=ack,
    )


def test_validated_success_is_recorded_before_result_return(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    ledger = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    host, calls = _mock_host(monkeypatch)
    event = _event()
    fingerprint = _fingerprint(FIXTURE.manifest, event)
    try:
        assert _eval(host, ledger, event) == "INERT_TEST_RESULT"
        first = ledger.status(fingerprint)
        assert first.state == "READY"
        assert first.revision == 1
        assert first.event_count == 2
        assert not first.retry_permitted
        assert not first.live_permitted
        assert not first.telegram_permitted
        assert len(calls) == 1
        assert _eval(host, ledger, event) == "INERT_TEST_RESULT"
        assert ledger.status(fingerprint).revision == 2
    finally:
        ledger.close()

    reopened = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    try:
        assert reopened.status(fingerprint).state == "READY"
        assert reopened.status(fingerprint).revision == 2
        assert reopened.status(fingerprint).event_count == 4
    finally:
        reopened.close()


def test_worker_failure_persists_quarantine_after_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    ledger = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    host, calls = _mock_host(monkeypatch, outcome="fail")
    event = _event()
    fingerprint = _fingerprint(FIXTURE.manifest, event)
    with pytest.raises(DurableRuntimeRefused, match="DURABLE_BINDING_QUARANTINED"):
        _eval(host, ledger, event)
    assert ledger.status(fingerprint).state == "QUARANTINED"
    ledger.close()
    reopened = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    try:
        clean_host, clean_calls = _mock_host(monkeypatch)
        with pytest.raises(DurableRuntimeRefused, match="PERSISTENT_BINDING_BLOCKED"):
            _eval(clean_host, reopened, event)
        assert len(clean_calls) == 0
        assert len(calls) == 1
    finally:
        reopened.close()


def test_interruption_leaves_running_lease_permanently_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    ledger = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    host, _ = _mock_host(monkeypatch, outcome="interrupt")
    event = _event()
    fingerprint = _fingerprint(FIXTURE.manifest, event)
    with pytest.raises(KeyboardInterrupt, match="SIMULATED_POWER_LOSS"):
        _eval(host, ledger, event)
    assert ledger.status(fingerprint).state == "RUNNING"
    ledger.close()
    second = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    try:
        host, calls = _mock_host(monkeypatch)
        with pytest.raises(DurableRuntimeRefused, match="PERSISTENT_BINDING_BLOCKED"):
            _eval(host, second, event)
        assert not calls
    finally:
        second.close()


def test_two_connections_cannot_start_same_binding(tmp_path):
    path = tmp_path / "a3.sqlite"
    first = DurableRuntimeLedger(path)
    second = DurableRuntimeLedger(path)
    finger = _fingerprint(FIXTURE.manifest, _event())
    try:
        first.start(finger, "a" * 64)
        with pytest.raises(DurableRuntimeRefused, match="PERSISTENT_BINDING_BLOCKED"):
            second.start(finger, "a" * 64)
        assert first.status(finger).state == "RUNNING"
    finally:
        first.close()
        second.close()


def test_audit_tampering_refused_even_if_sqlite_is_valid(tmp_path):
    path = tmp_path / "a3.sqlite"
    ledger = DurableRuntimeLedger(path)
    finger = _fingerprint(FIXTURE.manifest, _event())
    ledger.start(finger, "b" * 64)
    ledger.finish(finger, "b" * 64, success=False)
    ledger.close()
    with sqlite3.connect(path) as db:
        db.execute("UPDATE runtime_leases SET state='READY' WHERE fingerprint=?", (finger,))
    with pytest.raises(DurableRuntimeRefused, match="RUNTIME_LEASE_AUDIT_MISMATCH"):
        DurableRuntimeLedger(path)


def test_missing_audit_is_refused(tmp_path):
    path = tmp_path / "a3.sqlite"
    ledger = DurableRuntimeLedger(path)
    finger = _fingerprint(FIXTURE.manifest, _event())
    ledger.start(finger, "c" * 64)
    ledger.close()
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM runtime_audit")
    with pytest.raises(DurableRuntimeRefused, match="RUNTIME_LEASE_AUDIT_MISMATCH"):
        DurableRuntimeLedger(path)


def test_review_requires_admin_evidence_and_never_releases(tmp_path):
    ledger = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    finger = _fingerprint(FIXTURE.manifest, _event())
    ledger.start(finger, "a" * 64)
    kwargs = {
        "evidence_sha256": "e" * 64,
        "note": "No host attestation or cleanup verified",
        "operator_id": 101,
        "authorized_operator_ids": frozenset({101}),
        "operator_ack": True,
        "all_workers_stopped": True,
    }
    try:
        with pytest.raises(DurableRuntimeRefused, match="REVIEW_ADMIN"):
            ledger.record_review(finger, **{**kwargs, "operator_id": 102})
        with pytest.raises(DurableRuntimeRefused, match="REVIEW_ADMIN"):
            ledger.record_review(finger, **{**kwargs, "all_workers_stopped": False})
        record = ledger.record_review(finger, **kwargs)
        assert record["status"] == "REVIEW_RECORDED_NO_RELEASE"
        assert record["retry_permitted"] is False
        assert record["broker_order_sent"] is False
        assert ledger.status(finger).state == "RUNNING"
        assert ledger.status(finger).event_count == 2
        assert ledger.record_review(finger, **kwargs) == record
        assert ledger.status(finger).event_count == 2
        with pytest.raises(DurableRuntimeRefused, match="CONFLICTING_REVIEW_RECEIPT"):
            ledger.record_review(finger, **{**kwargs, "note": "Conflicting review note"})
    finally:
        ledger.close()


def test_no_profiles_or_environment_denies_without_claim(tmp_path, monkeypatch):
    path = tmp_path / "a3.sqlite"
    ledger = DurableRuntimeLedger(path)
    event = _event()
    fingerprint = _fingerprint(FIXTURE.manifest, event)
    host = MultiLanguageOfflineHost()
    try:
        monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
        with pytest.raises(DurableRuntimeRefused, match="NONPRODUCTION_ONLY"):
            _eval(host, ledger)
        monkeypatch.setenv("MMT_NONPRODUCTION", "1")
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(DurableRuntimeRefused, match="NONPRODUCTION_ONLY"):
            _eval(host, ledger)
        monkeypatch.delenv("MMT_PRODUCTION", raising=False)
        with pytest.raises(DurableRuntimeRefused, match="REVIEWED_WORKER_NOT_INSTALLED"):
            _eval(host, ledger)
        assert ledger.status(fingerprint).state == "ABSENT"
    finally:
        ledger.close()


def test_missing_ack_and_wrong_digest_are_refused_before_lease(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    ledger = DurableRuntimeLedger(tmp_path / "a3.sqlite")
    host, calls = _mock_host(monkeypatch)
    try:
        with pytest.raises(DurableRuntimeRefused, match="OPERATOR_APPROVAL_REQUIRED"):
            _eval(host, ledger, ack=False)
        with pytest.raises(MultilangRefused, match="APPROVED_SOURCE_DIGEST_REQUIRED"):
            DurableOfflineRuntime(host, ledger).evaluate(
                RuntimeKind.PYTHON, FIXTURE.manifest, _event(),
                artifact_name="test.py", artifact=ARTIFACT,
                approved_sha256="a" * 64, operator_ack=True,
            )
        assert not calls
    finally:
        ledger.close()


def test_symlink_world_readable_or_unrelated_database_refused(tmp_path):
    target = tmp_path / "target.sqlite"
    target.write_bytes(b"not-a-database")
    target.chmod(0o600)
    link = tmp_path / "link.sqlite"
    link.symlink_to(target)
    with pytest.raises(DurableRuntimeRefused, match="PRIVATE_ABSOLUTE"):
        DurableRuntimeLedger(link)
    path = tmp_path / "a3.sqlite"
    db = DurableRuntimeLedger(path)
    db.close()
    path.chmod(0o644)
    with pytest.raises(DurableRuntimeRefused, match="PRIVATE_OWNER_ONLY"):
        DurableRuntimeLedger(path)
    path.chmod(0o600)
    unknown = tmp_path / "unrelated.sqlite"
    with sqlite3.connect(unknown) as conn:
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
    unknown.chmod(0o600)
    with pytest.raises(DurableRuntimeRefused, match="UNKNOWN_LEDGER_DATABASE"):
        DurableRuntimeLedger(unknown)
