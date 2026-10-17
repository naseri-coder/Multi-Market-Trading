"""Synthetic two-role signing-policy regression suite."""
from __future__ import annotations

import hashlib
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_v040_operator_two_role_admission_v1 as gate


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    key = Ed25519PrivateKey.generate()
    publisher = Ed25519PrivateKey.generate()
    operator_spki = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    publisher_spki = publisher.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    operator_fp = _sha(operator_spki)
    publisher_fp = _sha(publisher_spki)
    now = int(time.time())
    data = {
        "schema": 1,
        "scope": gate.SCOPE,
        "source_commit": "a" * 40,
        "source_date_epoch": now - 60,
        "expires_epoch": now + 3600,
        "public_tree_sha1": "b" * 40,
        "source_snapshot_sha256": "c" * 64,
        "stable_overlay_sha256": "d" * 64,
        "wheel_sha256": "e" * 64,
        "manifest_sha256": "f" * 64,
        "publisher_key_spki_sha256": publisher_fp,
        "publisher_policy_sha256": "1" * 64,
    }
    policy = {
        "schema": 1, "revision": 3,
        "active_signers": [operator_fp], "revoked_signers": [],
        "min_source_date_epoch": now - 3600,
    }
    receipt = tmp_path / "operator-review.json"
    signature = tmp_path / "operator-review.sig"
    public = tmp_path / "reviewer-public.pem"
    trust = tmp_path / "reviewer-policy.json"
    public.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    args = {
        "receipt": receipt, "signature": signature,
        "operator_public_key": public, "operator_policy": trust,
        "expected_operator_key_spki_sha256": operator_fp,
        "expected_source_commit": data["source_commit"],
        "expected_public_tree_sha1": data["public_tree_sha1"],
        "expected_snapshot_sha256": data["source_snapshot_sha256"],
        "expected_overlay_sha256": data["stable_overlay_sha256"],
        "expected_wheel_sha256": data["wheel_sha256"],
        "expected_manifest_sha256": data["manifest_sha256"],
        "expected_publisher_key_spki_sha256": publisher_fp,
        "expected_publisher_policy_sha256": data["publisher_policy_sha256"],
    }

    def rewrite():
        raw = _canonical(data)
        trusted = _canonical(policy)
        receipt.write_bytes(raw)
        signature.write_bytes(key.sign(gate.DOMAIN + raw))
        trust.write_bytes(trusted)
        args["expected_receipt_sha256"] = _sha(raw)
        args["expected_operator_policy_sha256"] = _sha(trusted)

    rewrite()
    return args, data, policy, rewrite


def test_valid_two_role_signature_always_release_denied(bundle):
    args, _, _, _ = bundle
    result = gate.verify_operator_review(**args)
    assert result["role_separation_verified"] is True
    assert result["public_release_authorized"] is False
    assert result["human_identity_independently_established"] is False
    assert result["merge_authorized"] is False


def test_same_key_for_publisher_and_operator_refused(bundle):
    args, _, _, _ = bundle
    args["expected_publisher_key_spki_sha256"] = args["expected_operator_key_spki_sha256"]
    with pytest.raises(gate.OperatorReviewRefused, match="ROLE_COLLISION"):
        gate.verify_operator_review(**args)


def test_forged_operator_signature_refused(bundle):
    args, _, _, _ = bundle
    args["signature"].write_bytes(b"\x00" * 64)
    with pytest.raises(gate.OperatorReviewRefused, match="SIGNATURE_INVALID"):
        gate.verify_operator_review(**args)


def test_modified_receipt_with_stale_external_pin_refused(bundle):
    args, data, _, _ = bundle
    data["scope"] = "unauthorized"
    args["receipt"].write_bytes(_canonical(data))
    with pytest.raises(gate.OperatorReviewRefused, match="RECEIPT_EXTERNAL_PIN_MISMATCH"):
        gate.verify_operator_review(**args)


def test_valid_signature_on_different_wheel_is_refused(bundle):
    args, data, _, rewrite = bundle
    data["wheel_sha256"] = "2" * 64
    rewrite()
    with pytest.raises(gate.OperatorReviewRefused, match="APPROVED_ARTIFACT_MISMATCH"):
        gate.verify_operator_review(**args)


def test_revoked_reviewer_fails_closed(bundle):
    args, _, policy, rewrite = bundle
    fp = args["expected_operator_key_spki_sha256"]
    policy["active_signers"] = []
    policy["revoked_signers"] = [fp]
    rewrite()
    with pytest.raises(gate.OperatorReviewRefused, match="TRUST_POLICY_REFUSED"):
        gate.verify_operator_review(**args)


def test_unsigned_policy_swap_refused(bundle):
    args, _, policy, _ = bundle
    policy["revision"] += 1
    args["operator_policy"].write_bytes(_canonical(policy))
    with pytest.raises(gate.OperatorReviewRefused, match="POLICY_EXTERNAL_PIN_MISMATCH"):
        gate.verify_operator_review(**args)


def test_expired_attestation_refused(bundle):
    args, data, _, rewrite = bundle
    data["expires_epoch"] = int(time.time()) - 1
    rewrite()
    with pytest.raises(gate.OperatorReviewRefused, match="RECEIPT_VALUE_INVALID"):
        gate.verify_operator_review(**args)


@pytest.mark.parametrize("value", ["0", "false", ""])
def test_production_variable_presence_denied(bundle, monkeypatch, value):
    args, _, _, _ = bundle
    monkeypatch.setenv("MMT_PRODUCTION", value)
    with pytest.raises(gate.OperatorReviewRefused, match="NONPRODUCTION_REQUIRED"):
        gate.verify_operator_review(**args)


def test_nonproduction_optin_missing_denied(bundle, monkeypatch):
    args, _, _, _ = bundle
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(gate.OperatorReviewRefused, match="NONPRODUCTION_REQUIRED"):
        gate.verify_operator_review(**args)


def test_wrong_key_fingerprint_denied(bundle):
    args, _, _, _ = bundle
    args["expected_operator_key_spki_sha256"] = "5" * 64
    with pytest.raises(gate.OperatorReviewRefused, match="TRUST_POLICY_REFUSED"):
        gate.verify_operator_review(**args)


def test_duplicate_json_field_denied(bundle):
    args, _, _, _ = bundle
    corrupt = args["receipt"].read_bytes().replace(b'"schema":1,', b'"schema":1,"schema":1,')
    args["receipt"].write_bytes(corrupt)
    args["expected_receipt_sha256"] = _sha(corrupt)
    with pytest.raises(gate.OperatorReviewRefused, match="DUPLICATE_JSON_KEY"):
        gate.verify_operator_review(**args)


def test_review_domain_is_distinct_and_has_no_publish_method():
    assert gate.DOMAIN != gate.stable.DOMAIN
    assert not hasattr(gate, "publish")
    assert not hasattr(gate, "merge")
