"""Stage27: one signed PUBLIC-candidate intake with atomic initial deny.

This does NOT authenticate a web session, certify gVisor or grant execution.
An independently trusted host supplies the tenant/publisher identities and
already admitted Stage23 two-issuer claim. Registration and execution-denial
classification commit atomically in the owner-private Stage22 SQLite.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass

from .core_api_v1 import CoreBinding, CoreManifest, content_digest
from .durable_isolated_core_gate_stage22_v1 import DurableIsolatedCoreGate
from .signed_core_candidate_stage23_v1 import SignedCandidateWitness


class PublicIntakeRefused(ValueError):
    """Sanitized fail-closed refusal for public developer admission."""


@dataclass(frozen=True, slots=True)
class PublicIntakeReceipt:
    tenant_id: str
    binding_id: str
    candidate_sha256: str
    source_sha256: str
    stage22_revision: int
    status: str = "SIGNED_PUBLIC_UNTRUSTED_INTAKE_BLOCKED"
    classified_public: bool = True
    signed_publisher_claim_current: bool = True
    runtime_execution_authorized: bool = False
    public_installer_authorized: bool = False
    telegram_signal_authorized: bool = False
    broker_order_authorized: bool = False
    live_trading_authorized: bool = False
    independent_host_isolation_verified: bool = False


def _insert_verified_public_locked(
    stage22: DurableIsolatedCoreGate, *,
    tenant_id: str, publisher: str, publisher_key_id: str,
    manifest: CoreManifest, binding: CoreBinding,
    source_sha256: str, candidate_sha256: str,
    expected_image: str,
) -> None:
    """Caller MUST hold the Stage22 BEGIN IMMEDIATE transaction.

    Stage23 current signature checks are performed by the trusted caller;
    this internal helper ONLY writes a disabled Stage22 registration and
    an immutable Stage27 public classification in the same transaction.
    """
    manifest_digest = content_digest(manifest)
    binding_digest = content_digest(binding)
    stage22._insert_disabled_locked(
        tenant_id, manifest, binding, manifest_digest, source_sha256)
    stage22.db.execute(
        "INSERT INTO secure27_public_intake("
        "binding_id,tenant_id,publisher_id,publisher_key_id,"
        "candidate_sha256,source_sha256,manifest_sha256,"
        "binding_sha256,image_sha256,registration_revision,state)"
        " VALUES(?,?,?,?,?,?,?,?,?,1,?)",
        (binding.binding_id, tenant_id, publisher, publisher_key_id,
         candidate_sha256, source_sha256, manifest_digest, binding_digest,
         expected_image.rsplit("@sha256:", 1)[-1],
         "PUBLIC_UNTRUSTED_PENDING_INDEPENDENT_HOST"))


def register_signed_public_candidate(
    *, stage22: DurableIsolatedCoreGate,
    stage23: SignedCandidateWitness,
    tenant_id: str, publisher: str, publisher_key_id: str,
    manifest: CoreManifest, binding: CoreBinding, source: bytes,
    signed_candidate: bytes, expected_image: str, now: int,
    operator_ack: bool = False,
) -> PublicIntakeReceipt:
    """No instant where a newly registered public binding is executable.

    Stage23 must have admitted the exact independently pinned publisher and
    operator Ed25519 signatures. No Stage24 synthetic host review is treated
    as a permission. This does not call the Stage4 isolated worker.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise PublicIntakeRefused("EXPLICIT_NONPRODUCTION_PUBLIC_INTAKE_REQUIRED")
    if (type(stage22) is not DurableIsolatedCoreGate
            or type(stage23) is not SignedCandidateWitness
            or type(manifest) is not CoreManifest
            or type(binding) is not CoreBinding
            or type(source) is not bytes or not 0 < len(source) <= 65536
            or type(signed_candidate) is not bytes or type(now) is not int):
        raise PublicIntakeRefused("EXACT_SIGNED_SOURCE_AND_BINDING_REQUIRED")
    if not stage22.host.policy.enabled or stage22.host.policy.image != expected_image:
        raise PublicIntakeRefused("PINNED_ISOLATED_IMAGE_MISMATCH")
    digest = hashlib.sha256(source).hexdigest()
    try:
        verified = stage23.current(
            signed_candidate, source=source, manifest=manifest,
            binding=binding, tenant_id=tenant_id, publisher=publisher,
            publisher_key_id=publisher_key_id,
            image=expected_image, now=now)
        if (verified.binding_id != binding.binding_id
                or verified.tenant_id != tenant_id
                or not hmac.compare_digest(verified.source_sha256, digest)):
            raise PublicIntakeRefused("SIGNATURE_IDENTITY_AND_CODE_MISMATCH")
        with stage22._tx():
            # Re-read Stage23 in the same local Stage22 transaction. Stage23
            # remains a separate witness DB; this is NOT cross-DB atomicity.
            verified = stage23.current(
                signed_candidate, source=source, manifest=manifest,
                binding=binding, tenant_id=tenant_id, publisher=publisher,
                publisher_key_id=publisher_key_id, image=expected_image,
                now=now)
            _insert_verified_public_locked(
                stage22, tenant_id=tenant_id, publisher=publisher,
                publisher_key_id=publisher_key_id, manifest=manifest,
                binding=binding, source_sha256=digest,
                candidate_sha256=verified.envelope_sha256,
                expected_image=expected_image)
    except PublicIntakeRefused:
        raise
    except (ValueError, TypeError, KeyError, sqlite3.DatabaseError) as exc:
        raise PublicIntakeRefused("PUBLIC_IDENTITY_OR_ATOMIC_INTAKE_FAILED") from exc
    return PublicIntakeReceipt(
        tenant_id, binding.binding_id, verified.envelope_sha256, digest, 1)


def inspect_public_intake(stage22: DurableIsolatedCoreGate, *,
                          tenant_id: str, binding_id: str) -> dict:
    """Tenant-fenced safe status. No keys, source, signer or file paths."""
    if type(stage22) is not DurableIsolatedCoreGate:
        raise PublicIntakeRefused("EXACT_REGISTERED_HOST_REQUIRED")
    row = stage22._row(tenant_id, binding_id)
    intake = stage22.db.execute(
        "SELECT state,registration_revision FROM secure27_public_intake "
        "WHERE tenant_id=? AND binding_id=?", (tenant_id, binding_id)).fetchone()
    return {
        "binding_id": binding_id,
        "tenant_id": tenant_id,
        "stage22_state": row["state"],
        "public_classified": intake is not None,
        "public_intake_status": intake["state"] if intake else None,
        "public_install_authorized": False,
        "stage22_execution_authorized": False if intake else None,
        "telegram_send_authorized": False,
        "broker_order_authorized": False,
    }


__all__ = [
    "PublicIntakeRefused", "PublicIntakeReceipt",
    "register_signed_public_candidate", "inspect_public_intake",
]
