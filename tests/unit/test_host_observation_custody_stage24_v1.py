"""Stage24: signed *observation*, not actual host certification or code execution."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import asdict

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.disposable_gvisor_canary_stage23_v1 import (
    CanaryReceipt, _CANARY, _REQUIRED,
)
from naseri_markets.host_observation_custody_stage24_v1 import (
    HostObservationLedger, Stage24Refused, _DOMAIN,
    read_admin_host_security_status,
)
from test_secure_plugin_runtime_v1 import IMAGE

HOST = "disposable_host_one"
NOW = 1000
OTHER = "registry.example.invalid/pinned@sha256:" + "b"*64


@pytest.fixture(autouse=True)
def safe(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def reviewer_key(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def raw_receipt(image=IMAGE, *, allowed=True):
    receipt = CanaryReceipt(
        "OBSERVED_SINGLE_DISPOSABLE_HOST_CANARY_NOT_SECURITY_CERTIFIED",
        image.rsplit("@sha256:", 1)[-1],
        sha(_CANARY.encode("utf-8")),
        {k: (True if allowed else k != "rootfs_readonly") for k in _REQUIRED},
        True)
    return json.dumps(asdict(receipt), sort_keys=True).encode("ascii")


def signed(key, receipt, *, image=IMAGE, **changes):
    data = json.loads(receipt)
    claim = {
        "version": 1, "kind": "disposable_host_canary_observation",
        "host_id": HOST, "image": image,
        "probe_sha256": data["probe_sha256"],
        "receipt_sha256": sha(receipt),
        "sequence": 1, "observed_at": NOW - 20,
        "expires_at": NOW + 500,
        "review_scope": "manual_single_run_no_security_certification",
        "observation_checks": data["checks"],
    }
    claim.update(changes)
    sig = base64.b64encode(key.sign(_DOMAIN + canonical(claim))).decode("ascii")
    return canonical({"claim": claim, "reviewer_signature_b64": sig})


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / "private"
    path.mkdir(mode=0o700)
    signer = Ed25519PrivateKey.generate()
    pub = reviewer_key(signer)
    dbpath = path / "stage24_host_observation.sqlite"
    with HostObservationLedger(
            dbpath, reviewer_public_key=pub,
            approved_reviewer_key_sha256=sha(pub), operator_ack=True) as store:
        yield store, signer, dbpath


def save(ledger, signed_data, receipt, *, image=IMAGE):
    return ledger.record(
        signed_data, receipt, expected_host_id=HOST,
        expected_image=image, now=NOW, operator_ack=True)


def test_reviewed_receipt_does_not_certify_runtime_or_activate_trading(ledger):
    store, signer, path = ledger
    rec = raw_receipt()
    statement = signed(signer, rec)
    result = save(store, statement, rec)
    assert result.status == "OBSERVATION_STATEMENT_RECORDED_NOT_RUNTIME_ATTESTED"
    assert result.sequence == 1
    assert result.receipt_sha256 == sha(rec)
    assert result.real_host_execution_proven is False
    assert result.independent_security_certification is False
    assert result.public_plugin_install_authorized is False
    assert result.telegram_publication_authorized is False
    assert result.live_trading_authorized is False
    assert store.current(
        statement, rec, expected_host_id=HOST, expected_image=IMAGE,
        now=NOW) == result
    view = read_admin_host_security_status(path.parent)
    assert view["observations"] == 1
    assert not view["reviewed_host_security"]
    assert not view["broker_order_authorized"]
    with pytest.raises(Stage24Refused, match="REVOKED_ROLLBACK"):
        save(store, statement, rec)


@pytest.mark.parametrize("changes", [
    {"review_scope": "certified_production_sandbox"},
    {"kind": "trusted_live_code_runner"},
    {"version": True},
    {"sequence": True},
    {"observed_at": 0},
    {"expires_at": NOW + 100000},
    {"host_id": "bad!id"},
    {"image": "python:latest"},
    {"probe_sha256": "0" * 64},
    {"receipt_sha256": "0" * 64},
    {"observation_checks": {"uid_unprivileged": True}},
    {"observation_checks": {k: (False if k == "no_capabilities" else True)
                            for k in _REQUIRED}},
])
def test_signed_wrong_security_scopes_not_accepted(ledger, changes):
    store, key, _ = ledger
    raw = raw_receipt()
    with pytest.raises(Stage24Refused):
        save(store, signed(key, raw, **changes), raw)


def test_untrusted_signer_tamper_key_rotation_and_replay(ledger):
    store, key, path = ledger
    rec = raw_receipt()
    wrong = signed(Ed25519PrivateKey.generate(), rec)
    with pytest.raises(Stage24Refused, match="UNTRUSTED_REVIEWER"):
        save(store, wrong, rec)
    statement = signed(key, rec)
    with pytest.raises(Stage24Refused, match="IDENTITY_OR_TIME"):
        save(store, statement, rec + b" ")
    save(store, statement, rec)
    with pytest.raises(Stage24Refused, match="REVOKED_ROLLBACK"):
        save(store, statement, rec)
    other = Ed25519PrivateKey.generate()
    pub = reviewer_key(other)
    with pytest.raises(Stage24Refused, match="REVIEWER_ANCHOR_CHANGED"):
        HostObservationLedger(
            path, reviewer_public_key=pub,
            approved_reviewer_key_sha256=sha(pub),
            operator_ack=True)


def test_new_sequence_same_host_allowed_only_same_image_and_probe(ledger):
    store, signer, _path = ledger
    rec = raw_receipt()
    save(store, signed(signer, rec), rec)
    second = signed(signer, rec, sequence=2, observed_at=NOW-10)
    assert save(store, second, rec).sequence == 2
    other = raw_receipt(OTHER)
    with pytest.raises(Stage24Refused, match="CHANGED_HOST_POLICY"):
        save(store, signed(signer, other, image=OTHER, sequence=3),
             other, image=OTHER)


def test_revocation_persists_and_invalidates_receipt(ledger):
    store, signer, _path = ledger
    rec = raw_receipt()
    statement = signed(signer, rec)
    save(store, statement, rec)
    store.revoke(HOST, operator_ack=True)
    with pytest.raises(Stage24Refused, match="HOST_OBSERVATION_NOT_CURRENT"):
        store.current(statement, rec, expected_host_id=HOST,
                      expected_image=IMAGE, now=NOW)
    assert read_admin_host_security_status(_path.parent)["observations"] == 0
    with pytest.raises(Stage24Refused, match="REVOKED_ROLLBACK"):
        save(store, signed(signer, rec, sequence=2), rec)


def test_unsafe_canary_failed_check_and_false_certification_rejected(ledger):
    store, signer, _ = ledger
    failed = raw_receipt(allowed=False)
    with pytest.raises(Stage24Refused, match="UNSAFE_OR_UNVERIFIED"):
        save(store, signed(signer, failed), failed)
    false_claim = json.loads(raw_receipt())
    false_claim["public_plugin_install_authorized"] = True
    payload = json.dumps(false_claim, sort_keys=True).encode()
    with pytest.raises(Stage24Refused, match="UNSAFE_OR_UNVERIFIED"):
        save(store, signed(signer, payload), payload)


def test_malformed_duplicate_json_and_wrong_timestamp_refused(ledger):
    store, signer, _ = ledger
    rec = raw_receipt()
    proof = signed(signer, rec)
    with pytest.raises(Stage24Refused, match="DUPLICATE"):
        save(store, proof.replace(b'{"claim":', b'{"claim":{},"claim":', 1), rec)
    with pytest.raises(Stage24Refused, match="CANONICAL"):
        save(store, json.dumps(json.loads(proof), indent=2).encode(), rec)
    with pytest.raises(Stage24Refused, match="IDENTITY_OR_TIME"):
        store.record(proof, rec, expected_host_id=HOST, expected_image=IMAGE,
                     now=NOW+600, operator_ack=True)


def test_admin_reader_never_creates_db_and_refuses_untrusted_paths(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir(mode=0o700)
    state = read_admin_host_security_status(folder)
    assert state["observations"] == 0
    assert not (folder / "stage24_host_observation.sqlite").exists()
    target = folder / "stage24_host_observation.sqlite"
    target.symlink_to(tmp_path / "missing.sqlite")
    with pytest.raises(Stage24Refused, match="UNTRUSTED_READONLY"):
        read_admin_host_security_status(folder)


def test_private_path_and_nonproduction_gate(tmp_path, monkeypatch):
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    pub = reviewer_key(Ed25519PrivateKey.generate())
    args = dict(reviewer_public_key=pub,
                approved_reviewer_key_sha256=sha(pub), operator_ack=True)
    folder.chmod(0o755)
    with pytest.raises(Stage24Refused, match="OWNER_PRIVATE"):
        HostObservationLedger(folder / "bad.db", **args)
    folder.chmod(0o700)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage24Refused, match="EXPLICIT_NONPRODUCTION"):
        HostObservationLedger(folder / "deny.db", **args)
    assert not (folder / "deny.db").exists()


def test_corrupted_ledger_does_not_claim_runtime_security(ledger):
    store, signer, path = ledger
    rec = raw_receipt()
    save(store, signed(signer, rec), rec)
    with sqlite3.connect(path) as other:
        other.execute(
            "UPDATE stage24_host_observations SET observation_sha256=? "
            "WHERE host_id=?", ("0" * 64, HOST))
    view = read_admin_host_security_status(path.parent)
    assert view["status"] == "HOST_RUNTIME_INDEPENDENTLY_UNVERIFIED"
    assert view["observations"] == 1
    with pytest.raises(Stage24Refused, match="HOST_OBSERVATION_NOT_CURRENT"):
        store.current(signed(signer, rec), rec,
                      expected_host_id=HOST, expected_image=IMAGE, now=NOW)
