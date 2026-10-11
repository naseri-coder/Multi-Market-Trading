"""Stage 14: offline Ed25519 artifact signatures + review-required certification.

Verifying a signature proves only that a trusted *key* signed exact bytes.
It does NOT authorize installation, plugin execution, Telegram, or trading.
No signing key, trust root or certification state is stored in this module.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from .core_developer_sdk_v1 import (
    _parse_json,
    _wire,
    inspect_package,
)

_DOMAIN = b"MMT_STAGE14_CORE_ARTIFACT_ED25519_V1\x00"
_KEY_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE_FIELDS = frozenset({"schema_version", "algorithm", "key_id", "artifact_sha256", "signature_b64"})


class CertificationRefused(ValueError):
    """Signature/trust validation or package integrity was rejected."""


def _ed25519():
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:
        raise CertificationRefused("ED25519_DEPENDENCY_NOT_INSTALLED") from exc
    return InvalidSignature, Ed25519PrivateKey, Ed25519PublicKey


def _message(bundle: bytes) -> bytes:
    return _DOMAIN + hashlib.sha256(bundle).digest()


def sign_package(bundle: bytes, *, key_id: str, private_seed: bytes) -> bytes:
    """Operator-only detached signature, using independently provisioned key.

    `private_seed` is exactly 32 secret bytes; NEVER put it in Git, logs,
    package, manifest, CI, or response JSON. No key generation is performed.
    """
    if (type(key_id) is not str or not _KEY_ID.fullmatch(key_id) or
            type(private_seed) is not bytes or len(private_seed) != 32):
        raise CertificationRefused("SIGNER_ID_OR_KEY_INVALID")
    inspection = inspect_package(bundle)
    if inspection.warnings:
        raise CertificationRefused("STATIC_REVIEW_FINDINGS")
    _, PrivateKey, _ = _ed25519()
    signature = PrivateKey.from_private_bytes(private_seed).sign(_message(bundle))
    envelope = {
        "schema_version": 1, "algorithm": "Ed25519", "key_id": key_id,
        "artifact_sha256": inspection.sha256,
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    return _wire(envelope)


def verify_signature(bundle: bytes, signature: bytes, *,
                     trust_roots: Mapping[str, bytes],
                     revoked_key_ids: frozenset[str] = frozenset()) -> str:
    """Verify pinned publisher public key; no implicit/system/global trust."""
    if not isinstance(trust_roots, Mapping) or not isinstance(revoked_key_ids, frozenset):
        raise CertificationRefused("EXPLICIT_TRUST_POLICY_REQUIRED")
    inspection = inspect_package(bundle)
    env = _parse_json(signature, max_size=1_024)
    if set(env) != _SIGNATURE_FIELDS or _wire(env) != signature:
        raise CertificationRefused("SIGNATURE_SCHEMA_INVALID")
    if (type(env["schema_version"]) is not int or env["schema_version"] != 1 or
            env["algorithm"] != "Ed25519" or
            type(env["key_id"]) is not str or not _KEY_ID.fullmatch(env["key_id"]) or
            type(env["artifact_sha256"]) is not str or not _HEX.fullmatch(env["artifact_sha256"])):
        raise CertificationRefused("SIGNATURE_CONTRACT_INVALID")
    if env["artifact_sha256"] != inspection.sha256:
        raise CertificationRefused("SIGNATURE_ARTIFACT_MISMATCH")
    key_id = env["key_id"]
    if key_id in revoked_key_ids or key_id not in trust_roots:
        raise CertificationRefused("PUBLISHER_NOT_TRUSTED_OR_REVOKED")
    pubkey = trust_roots[key_id]
    if type(pubkey) is not bytes or len(pubkey) != 32:
        raise CertificationRefused("TRUST_ROOT_INVALID")
    if type(env["signature_b64"]) is not str or len(env["signature_b64"]) != 88:
        raise CertificationRefused("SIGNATURE_ENCODING_INVALID")
    try:
        sig = base64.b64decode(env["signature_b64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CertificationRefused("SIGNATURE_ENCODING_INVALID") from exc
    if len(sig) != 64 or base64.b64encode(sig).decode("ascii") != env["signature_b64"]:
        raise CertificationRefused("SIGNATURE_ENCODING_INVALID")
    InvalidSignature, _, PublicKey = _ed25519()
    try:
        PublicKey.from_public_bytes(pubkey).verify(sig, _message(bundle))
    except (InvalidSignature, ValueError) as exc:
        raise CertificationRefused("SIGNATURE_VERIFICATION_FAILED") from exc
    return key_id


@dataclass(frozen=True, slots=True)
class CertificationReport:
    artifact_sha256: str
    source_sha256: str
    core_id: str
    core_version: str
    publisher_key_id: str | None
    checks: tuple[str, ...]
    blockers: tuple[str, ...]
    approved_for_public_distribution: bool = False
    approved_for_execution: bool = False
    approved_for_trading: bool = False
    approved_for_telegram: bool = False
    status: str = "REVIEW_REQUIRED_NONPRODUCTION"


def evaluate_candidate(bundle: bytes, *, signature: bytes | None = None,
                       trust_roots: Mapping[str, bytes] | None = None,
                       revoked_key_ids: frozenset[str] = frozenset()) -> CertificationReport:
    """Fail closed. This function CANNOT approve public distribution.

    A future independent process needs: pinned key lifecycle, human source
    review, reproducible build evidence, *actual* gVisor containment tests,
    malicious-plugin trials, version rollback policy and provenance audit.
    """
    x = inspect_package(bundle)
    checks = ["EXACT_CORE_ABI_V1", "DETERMINISTIC_ARCHIVE", "SOURCE_DIGEST_VERIFIED"]
    blockers = ["INDEPENDENT_SECURITY_REVIEW_REQUIRED",
                "ACTUAL_ISOLATED_HOST_ATTESTATION_REQUIRED",
                "DISTRIBUTION_AND_RUNTIME_POLICY_NOT_IMPLEMENTED"]
    publisher = None
    if x.warnings:
        blockers.append("STATIC_SOURCE_FINDINGS")
    if signature is None:
        blockers.append("PUBLISHER_SIGNATURE_MISSING")
    else:
        # Verification failures are NOT silently downgraded to unsigned.
        if trust_roots is None:
            raise CertificationRefused("EXPLICIT_TRUST_ROOTS_REQUIRED")
        publisher = verify_signature(bundle, signature, trust_roots=trust_roots,
                                     revoked_key_ids=revoked_key_ids)
        checks.append("TRUSTED_PUBLISHER_SIGNATURE_VALID")
    return CertificationReport(
        artifact_sha256=x.sha256, source_sha256=x.source_sha256,
        core_id=x.manifest.core_id, core_version=x.manifest.core_version,
        publisher_key_id=publisher, checks=tuple(checks), blockers=tuple(blockers),
    )


__all__ = ["CertificationRefused", "CertificationReport", "evaluate_candidate",
           "sign_package", "verify_signature"]
