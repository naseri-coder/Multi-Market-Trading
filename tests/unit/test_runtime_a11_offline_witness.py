"""RUNTIME-A11: inert external-witness simulation (never production trust)."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.runtime_a10_evidence_anchor import OfflineEvidenceLedger
from naseri_markets.runtime_a11_offline_witness import (
    A11Refused,
    OfflineWitnessLedger,
    compare_witness_receipt,
)

KEY = b"ci-fixture-only-operator-custodied-key-do-not-ever-deploy-2026"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
OPS = frozenset({101})
ACTOR = "review.operator.fixture"


def _start(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    live = OfflineEvidenceLedger(tmp_path / "a10.sqlite")
    witness_path = tmp_path / "witness.sqlite"
    witness = OfflineWitnessLedger(witness_path, signing_key=KEY)
    return live, witness, witness_path


def _a10(live, n):
    live.append_claim(
        kind="A9_SPENT_REVIEW",
        evidence_sha256=hashlib.sha256(f"fake-claim-{n}".encode()).hexdigest(),
        actor=ACTOR, at=NOW + timedelta(seconds=n),
        operator_id=101, authorized_operators=OPS, operator_ack=True,
    )
    return live.export_untrusted_anchor()


def _record(witness, pin, *, number=1, prior=None, **more):
    options = dict(
        at=NOW + timedelta(seconds=number),
        operator_id=101, authorized_operators=OPS,
        operator_ack=True, prior_receipt=prior,
    )
    options.update(more)
    return witness.record(pin, **options)


def _verify(witness, receipt, pin, *, floor=None, **extra):
    return compare_witness_receipt(
        receipt.envelope, pin, key=KEY,
        expected_witness_id=witness.witness_id(),
        trusted_floor_receipt=floor,
        **extra,
    )


def test_first_signed_receipt_is_inert(tmp_path, monkeypatch):
    live, witness, _ = _start(tmp_path, monkeypatch)
    try:
        pin = _a10(live, 1)
        r = _record(witness, pin)
        assert r.status == "A11_OFFLINE_WITNESS_RECEIPT_NOT_INDEPENDENTLY_STORED"
        assert r.witness_sequence == 1
        assert r.a10_sequence == 1
        assert len(r.receipt_sha256) == 64
        assert not r.worker_execution_authorized
        assert not r.quarantine_release_authorized
        assert not r.broker_authorized
        assert not r.telegram_authorized
        result = _verify(witness, r, pin)
        assert result.status == "A11_HMAC_REVIEW_WITHOUT_TRUSTED_FLOOR"
        assert result.signature_is_shared_key_claim
        assert not result.independent_custody_proven
        assert not result.verified_freshness_proven
        assert not result.distributed_rollback_resistance_proven
        assert not result.actual_host_isolation_proven
        assert not result.worker_execution_authorized
    finally:
        live.close()
        witness.close()


def test_append_requires_previous_and_rejects_stale_head(tmp_path, monkeypatch):
    live, witness, _ = _start(tmp_path, monkeypatch)
    try:
        first_pin = _a10(live, 1)
        r1 = _record(witness, first_pin)
        second_pin = _a10(live, 2)
        with pytest.raises(A11Refused, match="A11_PREVIOUS_RECEIPT_REQUIRED"):
            _record(witness, second_pin, number=2)
        with pytest.raises(A11Refused, match="A11_WITNESS_REGRESSION_OR_FORK"):
            _record(witness, first_pin, number=2, prior=r1.envelope)
        r2 = _record(witness, second_pin, number=2, prior=r1.envelope)
        assert r2.witness_sequence == r2.a10_sequence == 2
        newer = _verify(witness, r2, second_pin, floor=r1.envelope)
        assert newer.status == "A11_ONE_CONSECUTIVE_SUPPLIED_LINK_MATCHED"
        with pytest.raises(A11Refused, match="A11_STALE_RECEIPT_BELOW_FLOOR"):
            _verify(witness, r1, first_pin, floor=r2.envelope)
        same = _verify(witness, r2, second_pin, floor=r2.envelope)
        assert same.status == "A11_SAME_OPERATOR_SUPPLIED_FLOOR"
        # Returning old metadata to a system with a truly retained newer floor
        # is the attack the protocol must refuse.
    finally:
        live.close()
        witness.close()


def test_reboot_ledger_and_two_connections_share_counter(tmp_path, monkeypatch):
    live, first, db = _start(tmp_path, monkeypatch)
    second = OfflineWitnessLedger(db, signing_key=KEY)
    try:
        pin1 = _a10(live, 1)
        r1 = _record(first, pin1)
        pin2 = _a10(live, 2)
        r2 = _record(second, pin2, number=2, prior=r1.envelope)
        with pytest.raises(A11Refused, match="A11_PREVIOUS_RECEIPT_NOT_CURRENT"):
            _record(first, _a10(live, 3), number=3, prior=r1.envelope)
        r3 = _record(first, live.export_untrusted_anchor(),
                     number=3, prior=r2.envelope)
        assert r3.witness_sequence == 3
        first.close()
        second.close()
        reopened = OfflineWitnessLedger(db, signing_key=KEY)
        try:
            assert reopened.witness_id() == json.loads(r1.envelope)["payload"]["witness_id"]
            result = _verify(reopened, r3, live.export_untrusted_anchor(),
                             floor=r2.envelope)
            assert result.witness_sequence == 3
        finally:
            reopened.close()
    finally:
        live.close()


def test_full_witness_db_rollback_rejected_with_latest_retained_receipt(
    tmp_path, monkeypatch,
):
    live, witness, db = _start(tmp_path, monkeypatch)
    try:
        p1 = _a10(live, 1)
        r1 = _record(witness, p1)
    finally:
        witness.close()
    backup = tmp_path / "old-witness.sqlite"
    shutil.copy2(db, backup)
    newer_witness = OfflineWitnessLedger(db, signing_key=KEY)
    p2 = _a10(live, 2)
    r2 = _record(newer_witness, p2, number=2, prior=r1.envelope)
    newer_witness.close()
    shutil.copy2(backup, db)
    restored = OfflineWitnessLedger(db, signing_key=KEY)
    try:
        assert restored.witness_id() == json.loads(r1.envelope)["payload"]["witness_id"]
        with pytest.raises(A11Refused, match="A11_PREVIOUS_RECEIPT_NOT_CURRENT"):
            _record(restored, _a10(live, 3), number=3, prior=r2.envelope)
        assert _verify(restored, r2, p2, floor=r1.envelope).witness_sequence == 2
        with pytest.raises(A11Refused, match="A11_STALE_RECEIPT_BELOW_FLOOR"):
            _verify(restored, r1, p1, floor=r2.envelope)
        # Cryptographic receipt comparisons alone cannot authenticate the
        # actual physical media location or guarantee its honest state.
    finally:
        restored.close()
        live.close()


def test_corrupted_witness_chain_and_fake_hmac_fail(tmp_path, monkeypatch):
    live, witness, path = _start(tmp_path, monkeypatch)
    p = _a10(live, 1)
    r = _record(witness, p)
    witness.close()
    sql = sqlite3.connect(path)
    sql.execute("UPDATE witness_records SET a10_hash=? WHERE seq=1", ("f" * 64,))
    sql.commit()
    sql.close()
    with pytest.raises(A11Refused, match="A11_WITNESS_MAC_OR_CHAIN_TAMPER"):
        OfflineWitnessLedger(path, signing_key=KEY)
    with pytest.raises(A11Refused, match="A11_HMAC_MISMATCH"):
        compare_witness_receipt(
            r.envelope, p, key=b"a-different-key-" * 4,
            expected_witness_id=json.loads(r.envelope)["payload"]["witness_id"],
        )
    live.close()


def test_signature_tamper_and_malformed_receipts(tmp_path, monkeypatch):
    live, witness, _ = _start(tmp_path, monkeypatch)
    try:
        p = _a10(live, 1)
        r = _record(witness, p)
        obj = json.loads(r.envelope)
        obj["payload"]["a10_record_hash"] = "f" * 64
        tampered = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        with pytest.raises(A11Refused, match="A11_HMAC_MISMATCH"):
            compare_witness_receipt(
                tampered, p, key=KEY, expected_witness_id=witness.witness_id(),
            )
        bad = [
            b"",
            b"\xff",
            r.envelope + b"\n",
            r.envelope.replace(b'"payload":{', b'"payload":{},"payload":{'),
            r.envelope.replace(b'"schema":1', b'"schema":true'),
            r.envelope.replace(b'"schema":1', b'"schema":1.2'),
            r.envelope + b" " * 5000,
        ]
        for data in bad:
            with pytest.raises(A11Refused):
                compare_witness_receipt(
                    data, p, key=KEY, expected_witness_id=witness.witness_id(),
                )
    finally:
        live.close()
        witness.close()


def test_wrong_anchor_witness_key_or_floor_refused(tmp_path, monkeypatch):
    live, witness, _ = _start(tmp_path, monkeypatch)
    try:
        first_pin = _a10(live, 1)
        r1 = _record(witness, first_pin)
        newer_pin = _a10(live, 2)
        with pytest.raises(A11Refused, match="A11_WITNESS_OR_A10_PIN_SCOPE_MISMATCH"):
            _verify(witness, r1, newer_pin)
        with pytest.raises(A11Refused, match="A11_WITNESS_OR_A10_PIN_SCOPE_MISMATCH"):
            compare_witness_receipt(
                r1.envelope, first_pin, key=KEY, expected_witness_id="f" * 32,
            )
        with pytest.raises(A11Refused, match="A11_EXPLICIT_OUT_OF_BAND_KEY_REQUIRED"):
            compare_witness_receipt(
                r1.envelope, first_pin, key=b"short",
                expected_witness_id=witness.witness_id(),
            )
        with pytest.raises(A11Refused, match="A11_EXACT_A10_ANCHOR_REQUIRED"):
            _verify(witness, r1, b'{"not":"an a10 anchor"}')
    finally:
        live.close()
        witness.close()


def test_two_witnesses_cannot_share_receipt_identity(tmp_path, monkeypatch):
    live, witness, _ = _start(tmp_path, monkeypatch)
    other = OfflineWitnessLedger(tmp_path / "other.sqlite", signing_key=KEY)
    try:
        pin = _a10(live, 1)
        r = _record(witness, pin)
        with pytest.raises(A11Refused, match="A11_WITNESS_OR_A10_PIN_SCOPE_MISMATCH"):
            compare_witness_receipt(
                r.envelope, pin, key=KEY, expected_witness_id=other.witness_id(),
            )
        with pytest.raises(A11Refused, match="A11_FLOOR_DIFFERENT_WITNESS"):
            other_r = _record(other, pin)
            compare_witness_receipt(
                r.envelope, pin, key=KEY, expected_witness_id=witness.witness_id(),
                trusted_floor_receipt=other_r.envelope,
            )
    finally:
        live.close()
        witness.close()
        other.close()


def test_witness_prefix_gap_refused_without_intermediate_receipt(
    tmp_path, monkeypatch,
):
    live, witness, _ = _start(tmp_path, monkeypatch)
    try:
        p1 = _a10(live, 1)
        r1 = _record(witness, p1)
        p2 = _a10(live, 2)
        r2 = _record(witness, p2, number=2, prior=r1.envelope)
        p3 = _a10(live, 3)
        r3 = _record(witness, p3, number=3, prior=r2.envelope)
        with pytest.raises(A11Refused, match="A11_MISSING_OR_DIVERGENT_WITNESS_LINK"):
            _verify(witness, r3, p3, floor=r1.envelope)
    finally:
        live.close()
        witness.close()


def test_trust_gate_rejects_operator_and_production(tmp_path, monkeypatch):
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    with pytest.raises(Exception, match="NONPRODUCTION_ONLY"):
        OfflineWitnessLedger(tmp_path / "witness.sqlite", signing_key=KEY)
    live, witness, _ = _start(tmp_path, monkeypatch)
    try:
        pin = _a10(live, 1)
        with pytest.raises(Exception, match="OPERATOR_APPROVAL_REQUIRED"):
            _record(witness, pin, operator_ack=False)
        with pytest.raises(A11Refused, match="A11_EXPLICIT_OUT_OF_BAND_KEY_REQUIRED"):
            OfflineWitnessLedger(
                tmp_path / "wrong-key.sqlite", signing_key=b"short",
            )
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(Exception, match="NONPRODUCTION_ONLY"):
            _record(witness, pin)
        with pytest.raises(Exception, match="NONPRODUCTION_ONLY"):
            compare_witness_receipt(
                b"fake", pin, key=KEY, expected_witness_id=witness.witness_id(),
            )
    finally:
        live.close()
        witness.close()


def test_private_witness_file_and_symlink_refused(tmp_path, monkeypatch):
    live, witness, path = _start(tmp_path, monkeypatch)
    witness.close()
    path.chmod(0o644)
    with pytest.raises(Exception, match="PRIVATE_FILE_REQUIRED"):
        OfflineWitnessLedger(path, signing_key=KEY)
    path.chmod(0o600)
    link = tmp_path / "witness-link.sqlite"
    link.symlink_to(path)
    with pytest.raises(Exception, match="PRIVATE_ABSOLUTE_PATH_REQUIRED"):
        OfflineWitnessLedger(link, signing_key=KEY)
    live.close()


def test_never_execute_any_worker_or_release_a6(tmp_path, monkeypatch):
    from naseri_markets.runtime_a6_dispatch_fence import (
        RuntimeA6Denied,
        require_worker_launch,
    )

    def denied(*args, **kwargs):
        raise AssertionError("A11_MUST_NEVER_LAUNCH")

    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    live, witness, _ = _start(tmp_path, monkeypatch)
    try:
        pin = _a10(live, 1)
        r = _record(witness, pin)
        review = _verify(witness, r, pin)
        assert not review.worker_execution_authorized
        assert not review.quarantine_release_authorized
        assert not review.broker_authorized
        assert not review.telegram_authorized
        with pytest.raises(RuntimeA6Denied):
            require_worker_launch(None, b"")
    finally:
        live.close()
        witness.close()
