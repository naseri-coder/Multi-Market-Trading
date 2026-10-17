"""RUNTIME-A6: mandatory fail-closed worker-dispatch launch boundary.

A4 authenticated claims and A5 consumed review receipts are *not* an
independently certified host attestation and never authorize a process start.
No production runtime integration, signing key, or launch grant is provided.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from .multilang_runtime_a1 import RuntimeProfile
    from .runtime_a5_nonce_custody import ConsumedReview

_MAX_FRAME = 192 * 1024


class RuntimeA6Denied(PermissionError):
    """Refuse an OCI launch before any host process or credential access."""


@dataclass(frozen=True, slots=True)
class WorkerLaunchReview:
    """Diagnostic-only preflight: never an execution capability."""

    language: str
    policy_sha256: str
    payload_sha256: str
    status: str = "A6_REVIEW_ONLY_EXTERNAL_HOST_CERTIFICATION_REQUIRED"
    independent_host_certified: bool = False
    a5_review_is_execution_grant: bool = False
    worker_launch_permitted: bool = False
    quarantine_release_permitted: bool = False
    live_permitted: bool = False
    broker_permitted: bool = False
    telegram_permitted: bool = False


def review_worker_launch(
    profile: RuntimeProfile, framed: bytes, *,
    a5_review: ConsumedReview | None = None,
) -> WorkerLaunchReview:
    """Validate inert dispatch scope; never mint an authorization token.

    This performs no filesystem, network, Docker, or subprocess operations.
    It deliberately refuses to infer host certification from A4/A5 signatures.
    """
    from .multilang_runtime_a1 import RuntimeProfile
    from .runtime_a4_security_evidence import policy_digest
    from .runtime_a5_nonce_custody import ConsumedReview

    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise RuntimeA6Denied("A6_NONPRODUCTION_ONLY")
    if not isinstance(profile, RuntimeProfile) or not profile.policy.enabled:
        raise RuntimeA6Denied("A6_REVIEWED_PROFILE_REQUIRED")
    if (type(framed) is not bytes or not 5 <= len(framed) <= _MAX_FRAME):
        raise RuntimeA6Denied("A6_BOUNDED_FRAME_REQUIRED")
    size = int.from_bytes(framed[:4], "big")
    if not 0 < size < len(framed) - 4:
        raise RuntimeA6Denied("A6_FRAME_LENGTH_INVALID")
    if a5_review is not None and (
        type(a5_review) is not ConsumedReview
        or a5_review.status != "EVIDENCE_CONSUMED_REVIEW_ONLY"
        or a5_review.execution_authorized is not False
        or a5_review.host_isolation_certified is not False
        or a5_review.worker_installed is not False
    ):
        raise RuntimeA6Denied("A6_INVALID_REVIEW_ONLY_CLAIM")
    # A1's framing contract validates source, manifest, replay origin and
    # digest before calling this function. Direct private _run_oci callers
    # still hit the same unconditional no-certification prohibition below.
    try:
        policy_sha256 = policy_digest(profile)
    except ValueError as exc:
        raise RuntimeA6Denied("A6_PINNED_POLICY_REQUIRED") from exc
    return WorkerLaunchReview(
        language=profile.kind.value,
        policy_sha256=policy_sha256,
        payload_sha256=hashlib.sha256(framed).hexdigest(),
    )


def require_worker_launch(profile: RuntimeProfile, framed: bytes) -> NoReturn:
    """Mandatory launch entry: no valid execution grant exists in A6.

    Even a correct A5 challenge and valid A4 HMAC proves only signed claims,
    not physical rootless Docker/gVisor confinement or independent custody.
    A future approved stage must replace this hard stop with verified, scoped,
    revocable capabilities and hard real-host evidence.
    """
    review_worker_launch(profile, framed)
    raise RuntimeA6Denied("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED")


__all__ = [
    "RuntimeA6Denied", "WorkerLaunchReview",
    "review_worker_launch", "require_worker_launch",
]
