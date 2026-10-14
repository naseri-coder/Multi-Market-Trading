"""A12 recovery/key-rotation REHEARSAL: mock-only; never admit Workers."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.runtime_a10_evidence_anchor import OfflineEvidenceLedger
from naseri_markets.runtime_a11_offline_witness import OfflineWitnessLedger
from naseri_markets.runtime_a12_offline_recovery import (
    A12Refused,
    block_lost_media,
    propose_key_rotation,
    verify_key_rotation,
    verify_replacement_witness,
)

OLD_KEY = b"a12-old-witness-key-fake-test-fixture-only-not-a-production-key"
NEW_KEY = b"a12-new-witness-key-fake-test-fixture-only-not-a-production-key"
OPS = frozenset({101})
NOW = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)


def _make(monkeypatch, tmp_path):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    a10 = OfflineEvidenceLedger(tmp_path / "a10.sqlite")
    old = OfflineWitnessLedger(
        tmp_path / "old-witness.sqlite", signing_key=OLD_KEY,
    )
    new = OfflineWitnessLedger(
        tmp_path / "replacement-witness.sqlite", signing_key=NEW_KEY,
    )
    return a10, old, new


def _anchor(a10, n):
    a10.append_claim(
        kind="A9_SPENT_REVIEW",
        evidence_sha256=hashlib.sha256(f"synthetic-evidence-{n}".encode()).hexdigest(),
        actor="fixture.review.operator",
        at=NOW + timedelta(seconds=n),
        operator_id=101, authorized_operators=OPS, operator_ack=True,
    )
    return a10.export_untrusted_anchor()


def _receipt(witness, anchor, n, prior=None):
    return witness.record(
        anchor, at=NOW + timedelta(seconds=n),
        operator_id=101, authorized_operators=OPS, operator_ack=True,
        prior_receipt=prior,
    )


def _proposal(old_receipt, old_anchor, new_id, **overrides):
    args = dict(
        old_receipt=old_receipt.envelope, old_anchor=old_anchor,
        retained_old_floor=old_receipt.envelope,
        old_key=OLD_KEY, new_key=NEW_KEY, new_witness_id=new_id,
        previous_key_epoch=1, at=NOW + timedelta(seconds=3),
        operator_id=101, authorized_operators=OPS, operator_ack=True,
    )
    args.update(overrides)
    return propose_key_rotation(**args)


def _verify(proposal, old_receipt, old_anchor, new_id, **overrides):
    args = dict(
        old_receipt=old_receipt.envelope,
        retained_old_floor=old_receipt.envelope,
        old_anchor=old_anchor, old_key=OLD_KEY, new_key=NEW_KEY,
        expected_new_witness_id=new_id, pinned_previous_key_epoch=1,
    )
    args.update(overrides)
    return verify_key_rotation(proposal.envelope, **args)


def _replacement(proposal, old_receipt, old_anchor, new_id, next_receipt,
                 next_anchor, **overrides):
    args = dict(
        old_receipt=old_receipt.envelope, retained_old_floor=old_receipt.envelope,
        old_anchor=old_anchor, old_key=OLD_KEY, new_key=NEW_KEY,
        expected_new_witness_id=new_id, pinned_previous_key_epoch=1,
        replacement_receipt=next_receipt.envelope,
        replacement_anchor=next_anchor,
    )
    args.update(overrides)
    return verify_replacement_witness(proposal.envelope, **args)


def test_two_key_handoff_new_witness_is_review_only(tmp_path, monkeypatch):
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        bridge = _proposal(r1, a1, new.witness_id())
        assert bridge.new_key_epoch == 2
        assert bridge.sha256 == hashlib.sha256(bridge.envelope).hexdigest()
        assert bridge.status == "A12_DUAL_MAC_PROPOSAL_NOT_INDEPENDENTLY_CUSTODIED"
        assert not bridge.recovery_activated
        assert not bridge.prior_key_retired
        assert not bridge.worker_execution_authorized
        assert not bridge.broker_authorized
        p = _verify(bridge, r1, a1, new.witness_id())
        assert p["old_a10_sequence"] == 1
        assert p["new_key_epoch"] == 2
        a2 = _anchor(a10, 2)
        r2 = _receipt(new, a2, 2)
        reviewed = _replacement(
            bridge, r1, a1, new.witness_id(), r2, a2,
        )
        assert reviewed.status == "A12_REPLACEMENT_WITNESS_SIMULATION_ONLY"
        assert reviewed.old_a10_sequence == 1
        assert reviewed.new_a10_sequence == 2
        assert reviewed.new_witness_id == new.witness_id()
        assert not reviewed.media_independence_proven
        assert not reviewed.trusted_key_rotation_proven
        assert not reviewed.external_latest_floor_authenticated
        assert not reviewed.recovery_activated
        assert not reviewed.worker_execution_authorized
        assert not reviewed.telegram_authorized
    finally:
        a10.close()
        old.close()
        new.close()


@pytest.mark.parametrize("media,floor", [
    (False, False), (False, True), (True, False), (True, True),
])
def test_media_loss_never_auto_recovers(monkeypatch, media, floor):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    outcome = block_lost_media(
        media_accessible=media, authentic_latest_floor_available=floor,
    )
    assert outcome.status == "A12_MEDIA_LOSS_BLOCKED_INDEPENDENT_EVIDENCE_REQUIRED"
    assert not outcome.automatic_recovery_permitted
    assert not outcome.key_rotation_performed
    assert not outcome.worker_execution_authorized
    assert not outcome.quarantine_release_authorized


def test_stale_checkpoint_rejected_against_retained_latest_floor(
    tmp_path, monkeypatch,
):
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        a2 = _anchor(a10, 2)
        r2 = _receipt(old, a2, 2, r1.envelope)
        with pytest.raises(A12Refused, match="A12_STALE_OLD_RECEIPT"):
            _proposal(
                r1, a1, new.witness_id(),
                retained_old_floor=r2.envelope,
            )
        # In the absence of a genuine separately retained floor, a malicious
        # caller can simply supply the old r1 bytes. No false trust assertion.
        assert not _proposal(r1, a1, new.witness_id()).media_independence_proven
    finally:
        a10.close()
        old.close()
        new.close()


def test_lost_old_database_can_only_stage_unactivated_bridge(
    tmp_path, monkeypatch,
):
    a10, old, new = _make(monkeypatch, tmp_path)
    a1 = _anchor(a10, 1)
    r1 = _receipt(old, a1, 1)
    old_path = tmp_path / "old-witness.sqlite"
    old.close()
    old_path.unlink()
    try:
        bridge = _proposal(r1, a1, new.witness_id())
        assert not bridge.recovery_activated
        assert not bridge.media_independence_proven
        assert _verify(bridge, r1, a1, new.witness_id())["new_key_epoch"] == 2
    finally:
        new.close()
        a10.close()


def test_old_key_unavailable_and_key_reuse_fail_closed(tmp_path, monkeypatch):
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        with pytest.raises(A12Refused, match="A12_EXACT_TWO_KEYS_REQUIRED"):
            _proposal(r1, a1, new.witness_id(), old_key=b"lost-key")
        with pytest.raises(A12Refused, match="A12_KEY_REUSE_FORBIDDEN"):
            _proposal(r1, a1, new.witness_id(), new_key=OLD_KEY)
        with pytest.raises(A12Refused, match="A12_OLD_FLOOR_NOT_VERIFIED"):
            _proposal(r1, a1, new.witness_id(), old_key=NEW_KEY,
                      new_key=OLD_KEY)
    finally:
        a10.close()
        old.close()
        new.close()


def test_forged_bridge_mac_or_scope_is_rejected(tmp_path, monkeypatch):
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        bridge = _proposal(r1, a1, new.witness_id())
        body = json.loads(bridge.envelope)
        body["payload"]["new_witness_id"] = "f" * 32
        tampered = json.dumps(
            body, sort_keys=True, separators=(",", ":"),
        ).encode()
        with pytest.raises(A12Refused, match="A12_DUAL_MAC_MISMATCH"):
            verify_key_rotation(
                tampered, old_receipt=r1.envelope,
                retained_old_floor=r1.envelope, old_anchor=a1,
                old_key=OLD_KEY, new_key=NEW_KEY,
                expected_new_witness_id=new.witness_id(),
                pinned_previous_key_epoch=1,
            )
        with pytest.raises(A12Refused, match="A12_HANDOFF_OUT_OF_BAND_PIN_MISMATCH"):
            _verify(bridge, r1, a1, "f" * 32)
        with pytest.raises(A12Refused, match="A12_HANDOFF_OUT_OF_BAND_PIN_MISMATCH"):
            _verify(bridge, r1, a1, new.witness_id(),
                    pinned_previous_key_epoch=2)
    finally:
        a10.close()
        old.close()
        new.close()


@pytest.mark.parametrize("wrong", [
    "extra-field", "duplicate-field", "bool-epoch", "float-epoch",
    "wrong-audience", "noncanonical", "oversized",
])
def test_schema_smuggling_refused(tmp_path, monkeypatch, wrong):
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        bridge = _proposal(r1, a1, new.witness_id())
        body = json.loads(bridge.envelope)
        if wrong == "extra-field":
            body["new_permission"] = True
        elif wrong == "duplicate-field":
            raw = bridge.envelope.replace(
                b'"payload":{', b'"payload":{},"payload":{',
            )
        elif wrong == "bool-epoch":
            body["payload"]["new_key_epoch"] = True
        elif wrong == "float-epoch":
            raw = bridge.envelope.replace(b'"new_key_epoch":2', b'"new_key_epoch":2.2')
        elif wrong == "wrong-audience":
            body["payload"]["audience"] = "MMT-WORKER-LAUNCH"
        elif wrong == "noncanonical":
            raw = bridge.envelope + b"\n"
        elif wrong == "oversized":
            raw = bridge.envelope + b" " * 5000
        if wrong in {"extra-field", "bool-epoch", "wrong-audience"}:
            raw = json.dumps(
                body, sort_keys=True, separators=(",", ":"),
            ).encode()
        with pytest.raises(A12Refused):
            verify_key_rotation(
                raw, old_receipt=r1.envelope,
                retained_old_floor=r1.envelope, old_anchor=a1,
                old_key=OLD_KEY, new_key=NEW_KEY,
                expected_new_witness_id=new.witness_id(),
                pinned_previous_key_epoch=1,
            )
    finally:
        a10.close()
        old.close()
        new.close()


def test_wrong_a10_ledger_or_rollback_replacement_denied(
    tmp_path, monkeypatch,
):
    a10, old, new = _make(monkeypatch, tmp_path)
    other = OfflineEvidenceLedger(tmp_path / "different-a10.sqlite")
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        bridge = _proposal(r1, a1, new.witness_id())
        with pytest.raises(A12Refused, match="A12_RECOVERY_A10_ROLLBACK"):
            _replacement(bridge, r1, a1, new.witness_id(), r1, a1)
        alternate = _anchor(other, 1)
        other.append_claim(
            kind="A9_SPENT_REVIEW", evidence_sha256="a" * 64,
            actor="fixture.review.operator", at=NOW + timedelta(seconds=2),
            operator_id=101, authorized_operators=OPS, operator_ack=True,
        )
        alternate2 = other.export_untrusted_anchor()
        assert alternate != alternate2
        with pytest.raises(A12Refused, match="A12_RECOVERY_A10_ROLLBACK"):
            _replacement(bridge, r1, a1, new.witness_id(), r1, alternate2)
    finally:
        a10.close()
        old.close()
        new.close()
        other.close()


def test_new_witness_non_genesis_is_rejected(tmp_path, monkeypatch):
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        bridge = _proposal(r1, a1, new.witness_id())
        a2 = _anchor(a10, 2)
        rr1 = _receipt(new, a2, 2)
        a3 = _anchor(a10, 3)
        rr2 = _receipt(new, a3, 3, rr1.envelope)
        with pytest.raises(A12Refused, match="A12_REPLACEMENT_NOT_FRESH_GENESIS"):
            _replacement(bridge, r1, a1, new.witness_id(), rr2, a3)
    finally:
        a10.close()
        old.close()
        new.close()


def test_unauthorized_operator_or_production_denied(
    tmp_path, monkeypatch,
):
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        with pytest.raises(A12Refused, match="A12_OPERATOR_ACK_REQUIRED"):
            _proposal(r1, a1, new.witness_id(), operator_ack=False)
        with pytest.raises(A12Refused, match="A12_PINNED_KEY_EPOCH_REQUIRED"):
            _proposal(r1, a1, new.witness_id(), previous_key_epoch=True)
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(A12Refused, match="A12_NONPRODUCTION_ONLY"):
            _proposal(r1, a1, new.witness_id())
        with pytest.raises(A12Refused, match="A12_NONPRODUCTION_ONLY"):
            block_lost_media(media_accessible=False,
                             authentic_latest_floor_available=False)
    finally:
        a10.close()
        old.close()
        new.close()


def test_no_runtime_process_or_a6_unlock(tmp_path, monkeypatch):
    from naseri_markets.runtime_a6_dispatch_fence import (
        RuntimeA6Denied,
        require_worker_launch,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("A12_MUST_NOT_EXECUTE_A_WORKER")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    a10, old, new = _make(monkeypatch, tmp_path)
    try:
        a1 = _anchor(a10, 1)
        r1 = _receipt(old, a1, 1)
        bridge = _proposal(r1, a1, new.witness_id())
        assert not bridge.worker_execution_authorized
        with pytest.raises(RuntimeA6Denied):
            require_worker_launch(None, b"")
    finally:
        a10.close()
        old.close()
        new.close()
