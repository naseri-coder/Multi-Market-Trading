"""Stage26: atomically seal public untrusted candidates as NON-EXECUTABLE.

Local Stage22 SQLite transaction + SQLite triggers are a persistent denial for
Stage22 set_enabled/evaluate and raw state updates. Cross-DB Stage23/24 signature
reads are not a distributed atomic transaction; their revocation after review
cannot produce execution because the Stage26 lock is permanent. This is NOT a
global plugin installer, OS security boundary or real-host security attestation.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass

from .core_api_v1 import CoreBinding, CoreManifest, content_digest
from .durable_isolated_core_gate_stage22_v1 import DurableIsolatedCoreGate
from .host_observation_custody_stage24_v1 import HostObservationLedger
from .preinstall_evidence_stage25_v1 import (
    PreinstallReviewRefused, review_preinstall_evidence,
)
from .signed_core_candidate_stage23_v1 import SignedCandidateWitness


class PublicCandidateLockRefused(ValueError):
    """No secret-bearing signer or source details are exposed."""


@dataclass(frozen=True, slots=True)
class PublicCandidateLockReceipt:
    tenant_id: str
    binding_id: str
    candidate_sha256: str
    observation_sha256: str
    revision: int
    state: str = "SEALED_PUBLIC_UNTRUSTED_CANDIDATE_NO_EXECUTION"
    stage22_activation_authorized: bool = False
    stage22_evaluation_authorized: bool = False
    public_install_authorized: bool = False
    telegram_publish_authorized: bool = False
    broker_order_authorized: bool = False
    live_trading_authorized: bool = False
    independently_verified_host: bool = False


def seal_public_candidate(
    *, stage22: DurableIsolatedCoreGate,
    stage23: SignedCandidateWitness,
    stage24: HostObservationLedger,
    candidate: bytes, source: bytes,
    manifest: CoreManifest, binding: CoreBinding,
    observation: bytes, canary_receipt: bytes,
    tenant_id: str, publisher: str, publisher_key_id: str,
    host_id: str, expected_image: str, now: int,
    operator_ack: bool = False,
) -> PublicCandidateLockReceipt:
    """Transition a previously DISABLED research binding to PERMANENT DENY.

    The host caller must authenticate tenant/publisher/host independently.
    The preflight is performed BEFORE the Stage22 IMMEDIATE transaction;
    state, revision and every immutable pin are checked again inside the
    transaction. Other DBs are re-read while holding the Stage22 write lock,
    but not assumed to share one atomic revocation or trust database.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise PublicCandidateLockRefused(
            "EXPLICIT_NONPRODUCTION_PUBLIC_CANDIDATE_LOCK_REQUIRED")
    if (type(stage22) is not DurableIsolatedCoreGate
            or type(stage23) is not SignedCandidateWitness
            or type(stage24) is not HostObservationLedger):
        raise PublicCandidateLockRefused("EXACT_REVIEWED_SECURITY_LEDGER_REQUIRED")
    opts = dict(
        stage22=stage22, stage23=stage23, stage24=stage24,
        candidate=candidate, source=source, manifest=manifest, binding=binding,
        observation=observation, canary_receipt=canary_receipt,
        tenant_id=tenant_id, publisher=publisher,
        publisher_key_id=publisher_key_id, host_id=host_id,
        expected_image=expected_image, now=now, operator_ack=True)
    try:
        report = review_preinstall_evidence(**opts)
        if (report.review_state !=
                "LOCAL_CROSS_STAGE_EVIDENCE_MATCHED_NOT_AUTHORIZED"
                or report.stage22_state != "DISABLED"
                or report.host_isolation_independently_verified
                or report.installation_authorized
                or report.activation_authorized
                or report.runtime_wiring_authorized
                or report.live_trading_authorized):
            raise PublicCandidateLockRefused("NOT_SAFE_TO_SEAL_PUBLIC_CANDIDATE")
        with stage22._tx():
            row = stage22._row(tenant_id, binding.binding_id)
            if (row["state"] != "DISABLED"
                    or row["revision"] != report.stage22_revision
                    or row["verified_evaluations"] != 0
                    or not hmac.compare_digest(
                        row["source_sha256"], hashlib.sha256(source).hexdigest())
                    or not hmac.compare_digest(
                        row["manifest_digest"], content_digest(manifest))
                    or not hmac.compare_digest(
                        row["binding_digest"], content_digest(binding))
                    or stage22.db.execute(
                        "SELECT 1 FROM secure22_attempts WHERE binding_id=?",
                        (binding.binding_id,)).fetchone()
                    or stage22.db.execute(
                        "SELECT 1 FROM secure26_public_fence WHERE binding_id=?",
                        (binding.binding_id,)).fetchone()):
                raise PublicCandidateLockRefused("CAS_OR_EXECUTION_HISTORY_CHANGED")
            # Recheck signed current status inside the Stage22 transaction.
            # A revocation in another DB immediately afterwards is safe:
            # the sealed Stage22 binding cannot become executable.
            stage23.current(
                candidate, source=source, manifest=manifest, binding=binding,
                tenant_id=tenant_id, publisher=publisher,
                publisher_key_id=publisher_key_id,
                image=expected_image, now=now)
            stage24.current(
                observation, canary_receipt=canary_receipt,
                expected_host_id=host_id,
                expected_image=expected_image, now=now)
            stage22.db.execute(
                "INSERT INTO secure26_public_fence("
                "binding_id,tenant_id,candidate_sha256,observation_sha256,"
                "source_sha256,sealed_revision,state) VALUES(?,?,?,?,?,?,?)",
                (binding.binding_id, tenant_id,
                 report.candidate_envelope_sha256, report.observation_sha256,
                 report.source_sha256, report.stage22_revision,
                 "PENDING_INDEPENDENT_HOST_REVIEW"))
    except PublicCandidateLockRefused:
        raise
    except (PreinstallReviewRefused, ValueError, KeyError, TypeError,
            sqlite3.DatabaseError, AttributeError) as exc:
        raise PublicCandidateLockRefused("INVALID_REVOKED_OR_CONFLICTING_REVIEW") from exc
    return PublicCandidateLockReceipt(
        tenant_id, binding.binding_id, report.candidate_envelope_sha256,
        report.observation_sha256, report.stage22_revision)


def inspect_public_candidate_lock(stage22: DurableIsolatedCoreGate, *,
                                  tenant_id: str, binding_id: str) -> dict:
    """No writes; owner-scoped status, no source or reviewer secrets."""
    if type(stage22) is not DurableIsolatedCoreGate:
        raise PublicCandidateLockRefused("REVIEW_LEDGER_REQUIRED")
    row = stage22._row(tenant_id, binding_id)
    sealed = stage22.db.execute(
        "SELECT state,sealed_revision FROM secure26_public_fence "
        "WHERE binding_id=? AND tenant_id=?", (binding_id, tenant_id)).fetchone()
    return {
        "binding_id": binding_id,
        "tenant_id": tenant_id,
        "local_state": row["state"],
        "sealed": bool(sealed),
        "sealed_state": sealed["state"] if sealed else None,
        "operator_revision": row["revision"],
        "third_party_public_install_authorized": False,
        "stage22_execute_authorized": False if sealed else None,
        "live_trading_authorized": False,
    }


__all__ = [
    "PublicCandidateLockRefused", "PublicCandidateLockReceipt",
    "seal_public_candidate", "inspect_public_candidate_lock",
]
