"""RUNTIME-A10: offline prefix-anchor checks only; NO external custody assumed."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

import naseri_markets.runtime_a10_evidence_anchor as a10

WHEN = datetime(2026, 10, 14, 8, tzinfo=UTC)
WHO = frozenset({101})
ACTOR = "operator.fixture.test"


def _start(monkeypatch, tmp_path):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    path = tmp_path / "a10-local-evidence.sqlite"
    return a10.OfflineEvidenceLedger(path), path


def _add(ledger, number=1, kind="A9_SPENT_REVIEW", **overrides):
    values = dict(
        kind=kind,
        evidence_sha256=hashlib.sha256(f"claim:{number}".encode()).hexdigest(),
        actor=ACTOR,
        at=WHEN + timedelta(seconds=number),
        operator_id=101, authorized_operators=WHO, operator_ack=True,
    )
    values.update(overrides)
    return ledger.append_claim(**values)


def test_local_hash_chain_and_untrusted_export(tmp_path, monkeypatch):
    ledger, db = _start(monkeypatch, tmp_path)
    try:
        first = _add(ledger, 1, "A5_CONSUMED_REVIEW")
        second = _add(ledger, 2, "A8_SOURCE_LOCK")
        assert first.sequence == 1
        assert second.sequence == 2
        assert second.record_hash != first.record_hash
        assert ledger.local_head() == second
        assert first.status == "A10_UNANCHORED_LOCAL_HASH_CHAIN_ONLY"
        assert first.external_custody_proven is False
        assert first.worker_execution_authorized is False
        assert second.broker_authorized is False
        anchor = ledger.export_untrusted_anchor()
        assert anchor == a10._canonical(json.loads(anchor))
        assert b"LOCAL_EXPORT_NOT_INDEPENDENTLY_STORED" in anchor
        assert second.record_hash.encode() in anchor
        assert b"claim:" not in db.read_bytes()
        comparison = ledger.compare_supplied_anchor(anchor)
        assert comparison.pinned_sequence == comparison.local_sequence == 2
        assert comparison.independent_custody_proven is False
        assert comparison.distributed_rollback_resistance_proven is False
        assert comparison.worker_execution_authorized is False
        assert comparison.quarantine_release_authorized is False
        assert comparison.telegram_authorized is False
    finally:
        ledger.close()


@pytest.mark.parametrize("kind", [
    "A5_CONSUMED_REVIEW", "A7_HOST_OBSERVATION",
    "A8_SOURCE_LOCK", "A9_SPENT_REVIEW",
])
def test_all_claim_kinds_can_be_pinned_not_certified(tmp_path, monkeypatch, kind):
    ledger, _ = _start(monkeypatch, tmp_path)
    try:
        _add(ledger, 1, kind)
        result = ledger.compare_supplied_anchor(ledger.export_untrusted_anchor())
        assert result.status == "A10_SUPPLIED_PIN_MATCHES_LOCAL_PREFIX_ONLY"
        assert not result.worker_execution_authorized
    finally:
        ledger.close()


def test_saved_old_anchor_is_only_prefix_not_current_head(tmp_path, monkeypatch):
    ledger, _ = _start(monkeypatch, tmp_path)
    try:
        _add(ledger, 1)
        old = ledger.export_untrusted_anchor()
        _add(ledger, 2)
        out = ledger.compare_supplied_anchor(old)
        assert out.pinned_sequence == 1
        assert out.local_sequence == 2
        assert out.independent_custody_proven is False
        assert out.status == "A10_SUPPLIED_PIN_MATCHES_LOCAL_PREFIX_ONLY"
    finally:
        ledger.close()


def test_rollback_restored_db_is_rejected_against_newer_external_pin(
    tmp_path, monkeypatch,
):
    ledger, db = _start(monkeypatch, tmp_path)
    try:
        _add(ledger, 1)
        early = ledger.export_untrusted_anchor()
    finally:
        ledger.close()
    saved = tmp_path / "pre-event-copy.sqlite"
    shutil.copy2(db, saved)
    reopened = a10.OfflineEvidenceLedger(db)
    try:
        _add(reopened, 2)
        anchored_later = reopened.export_untrusted_anchor()
    finally:
        reopened.close()
    shutil.copy2(saved, db)
    rollback = a10.OfflineEvidenceLedger(db)
    try:
        with pytest.raises(a10.A10Refused, match="A10_ROLLBACK_BELOW_SUPPLIED_ANCHOR"):
            rollback.compare_supplied_anchor(anchored_later)
        # An old/compromised pin does not prove anything about later records.
        assert rollback.compare_supplied_anchor(early).pinned_sequence == 1
    finally:
        rollback.close()


def test_rewritten_valid_local_chain_diverges_from_independent_pin(
    tmp_path, monkeypatch,
):
    ledger, db = _start(monkeypatch, tmp_path)
    try:
        _add(ledger, 1)
        trusted = ledger.export_untrusted_anchor()
    finally:
        ledger.close()
    sql = sqlite3.connect(db)
    new_digest = "a" * 64
    epoch = int((WHEN + timedelta(seconds=1)).timestamp())
    fake_hash = a10._record_hash(
        1, a10._GENESIS, "A9_SPENT_REVIEW", new_digest, ACTOR, epoch,
    )
    sql.execute(
        "UPDATE entries SET evidence_sha=?, record_hash=? WHERE sequence=1",
        (new_digest, fake_hash),
    )
    sql.commit()
    sql.close()
    reopened = a10.OfflineEvidenceLedger(db)
    try:
        # Locally consistent forged rewrite passes *local* inspection.
        assert reopened.local_head().record_hash == fake_hash
        with pytest.raises(a10.A10Refused, match="A10_SUPPLIED_ANCHOR_HASH_DIVERGENCE"):
            reopened.compare_supplied_anchor(trusted)
    finally:
        reopened.close()


def test_corrupt_local_hash_chain_denied(tmp_path, monkeypatch):
    ledger, db = _start(monkeypatch, tmp_path)
    _add(ledger, 1)
    ledger.close()
    sql = sqlite3.connect(db)
    sql.execute(
        "UPDATE entries SET evidence_sha=? WHERE sequence=1", ("f" * 64,),
    )
    sql.commit()
    sql.close()
    with pytest.raises(a10.A10Refused, match="A10_LOCAL_CHAIN_TAMPER_OR_GAP"):
        a10.OfflineEvidenceLedger(db)


def test_missing_seq_is_detected(tmp_path, monkeypatch):
    ledger, db = _start(monkeypatch, tmp_path)
    _add(ledger, 1)
    _add(ledger, 2)
    ledger.close()
    sql = sqlite3.connect(db)
    sql.execute("DELETE FROM entries WHERE sequence=1")
    sql.commit()
    sql.close()
    with pytest.raises(a10.A10Refused, match="A10_LOCAL_CHAIN_TAMPER_OR_GAP"):
        a10.OfflineEvidenceLedger(db)


def test_external_anchor_malformed_duplicate_invalid_scope_rejected(
    tmp_path, monkeypatch,
):
    ledger, _ = _start(monkeypatch, tmp_path)
    try:
        _add(ledger, 1)
        good = ledger.export_untrusted_anchor()
        pins = [
            good.replace(b'"sequence":1', b'"sequence":2'),
            good.replace(
                b'"ledger_id":', b'"ledger_id":"0" ,"ledger_id":',
            ),
            good.replace(b'"sequence":1', b'"sequence":true'),
            good.replace(b'"sequence":1', b'"sequence":1.0'),
            good.replace(b'"record_hash":', b'"fake_permission":true,"record_hash":'),
            good + b"\n",
            b"", b"\xff\xfe",
        ]
        for pin in pins:
            with pytest.raises(a10.A10Refused):
                ledger.compare_supplied_anchor(pin)
        different = json.loads(good)
        different["ledger_id"] = "a" * 32
        with pytest.raises(a10.A10Refused, match="A10_ANCHOR_WRONG_LEDGER"):
            ledger.compare_supplied_anchor(a10._canonical(different))
    finally:
        ledger.close()


def test_empty_chain_cannot_be_exported(tmp_path, monkeypatch):
    ledger, _ = _start(monkeypatch, tmp_path)
    try:
        with pytest.raises(a10.A10Refused, match="A10_EMPTY_CHAIN_CANNOT_EXPORT"):
            ledger.export_untrusted_anchor()
    finally:
        ledger.close()


def test_two_handles_append_contiguously_and_restart(tmp_path, monkeypatch):
    first, db = _start(monkeypatch, tmp_path)
    second = a10.OfflineEvidenceLedger(db)
    try:
        assert _add(first, 1).sequence == 1
        assert _add(second, 2).sequence == 2
        assert _add(first, 3).sequence == 3
        pin = second.export_untrusted_anchor()
    finally:
        first.close()
        second.close()
    reopened = a10.OfflineEvidenceLedger(db)
    try:
        result = reopened.compare_supplied_anchor(pin)
        assert result.local_sequence == 3
        assert _add(reopened, 4).sequence == 4
    finally:
        reopened.close()


def test_rewind_caller_time_rejected(tmp_path, monkeypatch):
    ledger, _ = _start(monkeypatch, tmp_path)
    try:
        _add(ledger, 2)
        with pytest.raises(a10.A10Refused, match="A10_LOCAL_TIME_REGRESSION"):
            _add(ledger, 1)
    finally:
        ledger.close()


def test_wrong_operator_environment_and_unpinned_kind(tmp_path, monkeypatch):
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    with pytest.raises(a10.A10Refused, match="A10_NONPRODUCTION_ONLY"):
        a10.OfflineEvidenceLedger(tmp_path / "a10.sqlite")
    ledger, _ = _start(monkeypatch, tmp_path)
    try:
        with pytest.raises(a10.A10Refused, match="A10_OPERATOR_APPROVAL_REQUIRED"):
            _add(ledger, 1, operator_ack=False)
        with pytest.raises(a10.A10Refused, match="A10_EXACT_DIGEST_CLAIM_SCOPE_REQUIRED"):
            _add(ledger, 1, "WORKER_LAUNCH_ALLOWED")
        with pytest.raises(a10.A10Refused, match="A10_EXACT_DIGEST_CLAIM_SCOPE_REQUIRED"):
            _add(ledger, 1, evidence_sha256="not-a-digest")
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(a10.A10Refused, match="A10_NONPRODUCTION_ONLY"):
            _add(ledger, 1)
        with pytest.raises(a10.A10Refused, match="A10_NONPRODUCTION_ONLY"):
            ledger.local_head()
    finally:
        ledger.close()


def test_private_file_and_symlinks_rejected(tmp_path, monkeypatch):
    ledger, db = _start(monkeypatch, tmp_path)
    ledger.close()
    db.chmod(0o644)
    with pytest.raises(a10.A10Refused, match="A10_PRIVATE_FILE_REQUIRED"):
        a10.OfflineEvidenceLedger(db)
    db.chmod(0o600)
    alias = tmp_path / "symlink.sqlite"
    alias.symlink_to(db)
    with pytest.raises(a10.A10Refused, match="A10_PRIVATE_ABSOLUTE_PATH_REQUIRED"):
        a10.OfflineEvidenceLedger(alias)


def test_no_process_or_execution_in_any_path(tmp_path, monkeypatch):
    from naseri_markets.runtime_a6_dispatch_fence import (
        RuntimeA6Denied,
        require_worker_launch,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("A10_MUST_NEVER_LAUNCH_OR_NETWORK")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    ledger, _ = _start(monkeypatch, tmp_path)
    try:
        _add(ledger, 1)
        pin = ledger.export_untrusted_anchor()
        assert not ledger.compare_supplied_anchor(pin).worker_execution_authorized
        # A6's no-certification barrier is unaffected by A10 comparisons.
        with pytest.raises(RuntimeA6Denied):
            require_worker_launch(None, b"")  # blocked before any subprocess
    finally:
        ledger.close()
