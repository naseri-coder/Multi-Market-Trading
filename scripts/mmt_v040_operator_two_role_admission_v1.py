"""Two-role release-review evidence gate for v0.4.0 (read-only, no publish).

A genuine release needs an externally pinned publisher signature AND a separate
operator approval, each independently checked against its own trust policy.
Test-key successes are not real-world authority and never grant merge/release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

from scripts import mmt_v040_rc_overlay_signed_custody_v1 as custody
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable

DOMAIN = b"MMT-V0.4.0-INDEPENDENT-OPERATOR-REVIEW-V1\n"
SCOPE = "multi-market-trading-v0.4.0-offline-paper"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = frozenset({
    "schema", "scope", "source_commit", "source_date_epoch", "expires_epoch",
    "public_tree_sha1", "source_snapshot_sha256", "stable_overlay_sha256",
    "wheel_sha256", "manifest_sha256", "publisher_key_spki_sha256",
    "publisher_policy_sha256",
})


class OperatorReviewRefused(ValueError):
    """Safe, fixed refusal reason."""


def _read(path: Path, limit: int) -> bytes:
    try:
        return stable._read(path, limit)
    except stable.StableArtifactRefused as exc:
        raise OperatorReviewRefused("V040_OPERATOR_FILE_REFUSED") from exc


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise OperatorReviewRefused("V040_OPERATOR_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _canonical(raw: bytes, fields: frozenset[str]) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if type(data) is not dict or set(data) != fields:
            raise OperatorReviewRefused("V040_OPERATOR_SCHEMA_MISMATCH")
        check = (json.dumps(data, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
        if check != raw:
            raise OperatorReviewRefused("V040_OPERATOR_NONCANONICAL")
        return data
    except OperatorReviewRefused:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise OperatorReviewRefused("V040_OPERATOR_JSON_INVALID") from exc


def verify_operator_review(
    *, receipt: Path, signature: Path, operator_public_key: Path,
    operator_policy: Path, expected_receipt_sha256: str,
    expected_operator_key_spki_sha256: str, expected_operator_policy_sha256: str,
    expected_source_commit: str, expected_public_tree_sha1: str,
    expected_snapshot_sha256: str, expected_overlay_sha256: str,
    expected_wheel_sha256: str, expected_manifest_sha256: str,
    expected_publisher_key_spki_sha256: str, expected_publisher_policy_sha256: str,
) -> dict:
    """Verify a separate human-controlled, independently pinned review signature.

    Returns technical evidence only. No release authorization can be inferred.
    """
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise OperatorReviewRefused("V040_OPERATOR_NONPRODUCTION_REQUIRED")
    pins = (
        expected_receipt_sha256, expected_operator_key_spki_sha256,
        expected_operator_policy_sha256, expected_snapshot_sha256,
        expected_overlay_sha256, expected_wheel_sha256, expected_manifest_sha256,
        expected_publisher_key_spki_sha256, expected_publisher_policy_sha256,
    )
    if any(type(pin) is not str or HEX64.fullmatch(pin) is None for pin in pins):
        raise OperatorReviewRefused("V040_OPERATOR_EXTERNAL_SHA256_PINS_REQUIRED")
    if (type(expected_source_commit) is not str
            or HEX40.fullmatch(expected_source_commit) is None
            or type(expected_public_tree_sha1) is not str
            or HEX40.fullmatch(expected_public_tree_sha1) is None):
        raise OperatorReviewRefused("V040_OPERATOR_EXTERNAL_GIT_PINS_REQUIRED")
    if expected_operator_key_spki_sha256 == expected_publisher_key_spki_sha256:
        raise OperatorReviewRefused("V040_OPERATOR_PUBLISHER_ROLE_COLLISION")

    raw = _read(receipt, 4096)
    if hashlib.sha256(raw).hexdigest() != expected_receipt_sha256:
        raise OperatorReviewRefused("V040_OPERATOR_RECEIPT_EXTERNAL_PIN_MISMATCH")
    review = _canonical(raw, FIELDS)
    now = int(time.time())
    if (type(review["schema"]) is not int or review["schema"] != 1
            or review["scope"] != SCOPE
            or type(review["source_date_epoch"]) is not int
            or not 315532800 <= review["source_date_epoch"] <= 4102444800
            or type(review["expires_epoch"]) is not int
            or not now < review["expires_epoch"] <= review["source_date_epoch"] + 366 * 86400):
        raise OperatorReviewRefused("V040_OPERATOR_RECEIPT_VALUE_INVALID")
    expected = {
        "source_commit": expected_source_commit,
        "public_tree_sha1": expected_public_tree_sha1,
        "source_snapshot_sha256": expected_snapshot_sha256,
        "stable_overlay_sha256": expected_overlay_sha256,
        "wheel_sha256": expected_wheel_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "publisher_key_spki_sha256": expected_publisher_key_spki_sha256,
        "publisher_policy_sha256": expected_publisher_policy_sha256,
    }
    if any(review[key] != value for key, value in expected.items()):
        raise OperatorReviewRefused("V040_OPERATOR_APPROVED_ARTIFACT_MISMATCH")

    policy_raw = _read(operator_policy, 8192)
    if hashlib.sha256(policy_raw).hexdigest() != expected_operator_policy_sha256:
        raise OperatorReviewRefused("V040_OPERATOR_POLICY_EXTERNAL_PIN_MISMATCH")
    try:
        policy = stable._policy(
            policy_raw, expected_operator_key_spki_sha256,
            {"source_date_epoch": review["source_date_epoch"]},
        )
    except stable.StableArtifactRefused as exc:
        raise OperatorReviewRefused("V040_OPERATOR_TRUST_POLICY_REFUSED") from exc
    key_bytes = _read(operator_public_key, 4096)
    signature_bytes = _read(signature, 64)
    if len(signature_bytes) != 64:
        raise OperatorReviewRefused("V040_OPERATOR_SIGNATURE_SIZE_INVALID")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        public = serialization.load_pem_public_key(key_bytes)
        if not isinstance(public, Ed25519PublicKey):
            raise OperatorReviewRefused("V040_OPERATOR_ED25519_REQUIRED")
        spki = public.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if hashlib.sha256(spki).hexdigest() != expected_operator_key_spki_sha256:
            raise OperatorReviewRefused("V040_OPERATOR_KEY_FINGERPRINT_MISMATCH")
        public.verify(signature_bytes, DOMAIN + raw)
    except (ValueError, TypeError, InvalidSignature) as exc:
        if isinstance(exc, OperatorReviewRefused):
            raise
        raise OperatorReviewRefused("V040_OPERATOR_SIGNATURE_INVALID") from exc

    return {
        "verdict": "V040_OPERATOR_REVIEW_CRYPTOGRAPHIC_CHECK_PASS_RELEASE_BLOCKED",
        "source_commit": expected_source_commit,
        "reviewer_key_spki_sha256": expected_operator_key_spki_sha256,
        "publisher_key_spki_sha256": expected_publisher_key_spki_sha256,
        "role_separation_verified": True,
        "operator_policy_revision": policy["revision"],
        "approved_artifact_pins_match": True,
        "human_identity_independently_established": False,
        "public_release_authorized": False,
        "merge_authorized": False,
        "live_trading_authorized": False,
    }


def verify_full_custody(
    *, repository: Path, receipt: Path, signature: Path,
    operator_public_key: Path, operator_policy: Path,
    expected_receipt_sha256: str, expected_operator_key_spki_sha256: str,
    expected_operator_policy_sha256: str,
    manifest: Path, publisher_signature: Path, wheel: Path,
    publisher_public_key: Path, publisher_policy: Path,
    expected_manifest_sha256: str, expected_publisher_key_spki_sha256: str,
    expected_publisher_policy_sha256: str, expected_wheel_sha256: str,
    expected_source_commit: str, expected_public_tree_sha1: str,
    expected_snapshot_sha256: str, expected_overlay_sha256: str,
) -> dict:
    """Require BOTH externally pinned roles and actual Git-to-Wheel custody."""
    review = verify_operator_review(
        receipt=receipt, signature=signature,
        operator_public_key=operator_public_key, operator_policy=operator_policy,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_operator_key_spki_sha256=expected_operator_key_spki_sha256,
        expected_operator_policy_sha256=expected_operator_policy_sha256,
        expected_source_commit=expected_source_commit,
        expected_public_tree_sha1=expected_public_tree_sha1,
        expected_snapshot_sha256=expected_snapshot_sha256,
        expected_overlay_sha256=expected_overlay_sha256,
        expected_wheel_sha256=expected_wheel_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_publisher_key_spki_sha256=expected_publisher_key_spki_sha256,
        expected_publisher_policy_sha256=expected_publisher_policy_sha256,
    )
    result = custody.audit(
        repository=repository, manifest=manifest, signature=publisher_signature,
        wheel=wheel, trusted_public_key=publisher_public_key,
        trusted_public_key_spki_sha256=expected_publisher_key_spki_sha256,
        policy=publisher_policy,
        expected_policy_sha256=expected_publisher_policy_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_source_commit=expected_source_commit,
        expected_public_tree_sha1=expected_public_tree_sha1,
        expected_lock_sha256=expected_snapshot_sha256,
        expected_overlay_sha256=expected_overlay_sha256,
    )
    if result["signed_stable_wheel_sha256"] != expected_wheel_sha256:
        raise OperatorReviewRefused("V040_OPERATOR_WHEEL_MISMATCH_AFTER_CUSTODY")
    return {
        **review, "verdict": "V040_DUAL_ROLE_SIGNED_CUSTODY_PASS_RELEASE_STILL_REQUIRES_HUMAN_APPROVAL",
        "public_modules_verified": result["public_modules_verified"],
        "source_to_wheel_verified": True,
        "human_identity_independently_established": False,
        "public_release_authorized": False, "merge_authorized": False,
        "live_trading_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    paths = ("receipt", "signature", "operator_public_key", "operator_policy",
             "manifest", "publisher_signature", "wheel", "publisher_public_key",
             "publisher_policy")
    pins = ("expected_receipt_sha256", "expected_operator_key_spki_sha256",
            "expected_operator_policy_sha256", "expected_manifest_sha256",
            "expected_publisher_key_spki_sha256", "expected_publisher_policy_sha256",
            "expected_wheel_sha256", "expected_source_commit",
            "expected_public_tree_sha1", "expected_snapshot_sha256",
            "expected_overlay_sha256")
    for name in paths:
        parser.add_argument("--" + name.replace("_", "-"), required=True, type=Path)
    for name in pins:
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    args = vars(parser.parse_args(argv))
    try:
        outcome = verify_full_custody(**args)
    except (OperatorReviewRefused, stable.StableArtifactRefused,
            custody.OverlayCustodyRefused, OSError) as exc:
        reason = str(exc) if isinstance(exc, OperatorReviewRefused) else "V040_OPERATOR_OR_SOURCE_CUSTODY_REFUSED"
        print(json.dumps({"verdict": "V040_OPERATOR_ADMISSION_REFUSED",
                          "reason": reason, "public_release_authorized": False,
                          "merge_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
