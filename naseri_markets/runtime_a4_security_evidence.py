"""RUNTIME-A4: strictly offline, non-authorizing security-evidence validator.

A valid MAC means the caller possessed the out-of-band review key. It does NOT
prove that the claimed security checks really ran, and NEVER authorizes
running third-party code, registering worker profiles or starting a container.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from .multilang_runtime_a1 import RuntimeKind, RuntimeProfile

_MAX_BYTES = 16384
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{3,95}\Z")
_NONCE = re.compile(r"[a-f0-9]{32,64}\Z")
_AUDIENCE = "MMT-RUNTIME-A4-RESEARCH-ONLY"
_SCHEMA = 1
_REQUIRED_CHECKS = (
    "rootless_daemon_verified",
    "runsc_runtime_verified",
    "network_denied_verified",
    "readonly_root_verified",
    "no_mounts_verified",
    "no_privileges_verified",
    "nonroot_uid_verified",
    "cpu_memory_pid_limits_verified",
    "no_credentials_verified",
    "oci_cleanup_verified",
    "fixed_fixture_abi_verified",
)
_FIELDS = frozenset({
    "schema_version", "audience", "issuer_id", "host_id",
    "runtime_kind", "image_digest", "policy_digest", "worker_digest",
    "issued_at", "expires_at", "nonce", "checks",
})


class RuntimeEvidenceRefused(ValueError):
    """Reject evidence without revealing its contents or shared verifier key."""


@dataclass(frozen=True, slots=True)
class EvidenceReview:
    """An inert evidence result; success never grants code execution."""

    receipt_sha256: str
    profile_sha256: str
    host_id: str
    runtime_kind: RuntimeKind
    expires_at: datetime
    status: str = "SIGNED_CLAIMS_MATCH_REVIEW_ONLY"
    evidence_claims_authenticated: bool = True
    host_isolation_certified: bool = False
    untrusted_code_execution_permitted: bool = False
    worker_installed: bool = False
    live_enabled: bool = False
    broker_enabled: bool = False
    telegram_enabled: bool = False


def _canonical(data: object) -> bytes:
    try:
        return json.dumps(
            data, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeEvidenceRefused("INVALID_CANONICAL_EVIDENCE") from exc


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise RuntimeEvidenceRefused("DUPLICATE_EVIDENCE_FIELD")
        out[key] = value
    return out


def _deny_float(_: str) -> None:
    raise RuntimeEvidenceRefused("NONINTEGER_EVIDENCE_NUMBER")


def _parse(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
        raise RuntimeEvidenceRefused("EVIDENCE_BYTE_LIMIT")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                         parse_float=_deny_float, parse_constant=_deny_float)
    except RuntimeEvidenceRefused:
        raise
    except (UnicodeError, ValueError, RecursionError, TypeError) as exc:
        raise RuntimeEvidenceRefused("INVALID_EVIDENCE_JSON") from exc
    if type(obj) is not dict or set(obj) != {"payload", "mac_sha256"}:
        raise RuntimeEvidenceRefused("EVIDENCE_ENVELOPE_INVALID")
    return obj


def _timestamp(value: object) -> datetime:
    if type(value) is not str or len(value) != 20:
        raise RuntimeEvidenceRefused("UTC_TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise RuntimeEvidenceRefused("UTC_TIMESTAMP_REQUIRED") from exc
    return parsed.replace(tzinfo=UTC)


def policy_digest(profile: RuntimeProfile) -> str:
    """Bind evidence to the complete original OCI policy and worker selection."""
    if not isinstance(profile, RuntimeProfile) or not profile.policy.enabled:
        raise RuntimeEvidenceRefused("REVIEWED_PROFILE_REQUIRED")
    if (profile.worker_reviewed is not True or
            profile.policy.image != (
                profile.policy.image.split("@sha256:")[0]
                + "@sha256:" + profile.reviewed_image_sha256)):
        raise RuntimeEvidenceRefused("REVIEWED_IMAGE_PIN_REQUIRED")
    return hashlib.sha256(_canonical({
        "kind": profile.kind.value,
        "protocol": profile.protocol_version,
        "worker_reviewed": profile.worker_reviewed,
        "image": profile.policy.image,
        "reviewed_image_sha256": profile.reviewed_image_sha256,
        "oci_policy": asdict(profile.policy),
    })).hexdigest()


def verify_security_evidence(
    receipt: bytes,
    *,
    profile: RuntimeProfile,
    review_key: bytes,
    trusted_issuer_id: str,
    expected_host_id: str,
    expected_nonce: str,
    at: datetime,
) -> EvidenceReview:
    """Verify signed claims, never infer that the underlying probes are genuine.

    The trusted HMAC key and expected host/nonce must be supplied out-of-band
    by the operator; neither appears in the repository or worker artifact.
    """
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise RuntimeEvidenceRefused("NONPRODUCTION_ONLY")
    if (type(review_key) is not bytes or len(review_key) < 32
            or type(trusted_issuer_id) is not str
            or _ID.fullmatch(trusted_issuer_id) is None
            or type(expected_host_id) is not str
            or _ID.fullmatch(expected_host_id) is None
            or type(expected_nonce) is not str
            or _NONCE.fullmatch(expected_nonce) is None
            or not isinstance(at, datetime) or at.tzinfo is None
            or at.utcoffset() != timedelta(0)):
        raise RuntimeEvidenceRefused("OUT_OF_BAND_TRUST_INPUT_REQUIRED")
    pinned = policy_digest(profile)
    envelope = _parse(receipt)
    payload = envelope["payload"]
    mac = envelope["mac_sha256"]
    if (type(payload) is not dict or set(payload) != _FIELDS
            or type(mac) is not str or _SHA.fullmatch(mac) is None):
        raise RuntimeEvidenceRefused("SIGNED_EVIDENCE_SCHEMA_INVALID")
    expected_mac = hmac.new(review_key, _canonical(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_mac, mac):
        raise RuntimeEvidenceRefused("EVIDENCE_MAC_INVALID")
    if (type(payload["schema_version"]) is not int
            or payload["schema_version"] != _SCHEMA
            or payload["audience"] != _AUDIENCE
            or payload["issuer_id"] != trusted_issuer_id
            or payload["host_id"] != expected_host_id
            or payload["nonce"] != expected_nonce
            or payload["runtime_kind"] != profile.kind.value
            or payload["image_digest"] != profile.reviewed_image_sha256
            or payload["policy_digest"] != pinned
            or type(payload["worker_digest"]) is not str
            or _SHA.fullmatch(payload["worker_digest"]) is None):
        raise RuntimeEvidenceRefused("EVIDENCE_PIN_OR_SCOPE_MISMATCH")
    checks = payload["checks"]
    if (type(checks) is not dict or set(checks) != set(_REQUIRED_CHECKS)
            or any(value is not True for value in checks.values())):
        raise RuntimeEvidenceRefused("MANDATORY_PROBE_CLAIMS_MISSING")
    issued, expires = _timestamp(payload["issued_at"]), _timestamp(payload["expires_at"])
    at = at.astimezone(UTC)
    if (issued > at or expires < at or expires <= issued
            or expires - issued > timedelta(minutes=15)):
        raise RuntimeEvidenceRefused("EVIDENCE_OUTSIDE_VALIDITY_WINDOW")
    return EvidenceReview(
        receipt_sha256=hashlib.sha256(receipt).hexdigest(),
        profile_sha256=pinned,
        host_id=expected_host_id,
        runtime_kind=profile.kind,
        expires_at=expires,
    )


__all__ = [
    "EvidenceReview", "RuntimeEvidenceRefused",
    "policy_digest", "verify_security_evidence",
]
