"""Stage 25: isolated, READ-ONLY pre-install evidence reconciliation.

Verifies separate Stage22 tenant reservation, Stage23 dual-signed publisher
candidate and Stage24 signed host observation. This is NOT a host security
certificate or an installation/execution authorization. Nothing can convert
these statements to an installer, an enabled core or live trading.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from .core_api_v1 import CoreBinding, CoreManifest, content_digest
from .durable_isolated_core_gate_stage22_v1 import DurableIsolatedCoreGate
from .host_observation_custody_stage24_v1 import HostObservationLedger
from .signed_core_candidate_stage23_v1 import SignedCandidateWitness


class PreinstallReviewRefused(ValueError):
    """Security validation refused; never disclose untrusted signed payloads."""


@dataclass(frozen=True, slots=True)
class PreinstallReviewReport:
    """Verified *local* chain, NOT approved runtime capability."""

    review_state: str
    tenant_id: str
    binding_id: str
    manifest_sha256: str
    source_sha256: str
    image_sha256: str
    candidate_envelope_sha256: str
    observation_sha256: str
    stage22_state: str
    stage22_revision: int
    chain_checks: tuple[str, ...]
    host_isolation_independently_verified: bool = False
    supply_chain_outside_local_state_verified: bool = False
    runtime_wiring_authorized: bool = False
    installation_authorized: bool = False
    activation_authorized: bool = False
    telegram_signal_authorized: bool = False
    broker_order_authorized: bool = False
    live_trading_authorized: bool = False


def review_preinstall_evidence(
    *, stage22: DurableIsolatedCoreGate,
    stage23: SignedCandidateWitness,
    stage24: HostObservationLedger,
    candidate: bytes, source: bytes,
    manifest: CoreManifest, binding: CoreBinding,
    observation: bytes, canary_receipt: bytes,
    tenant_id: str, publisher: str, publisher_key_id: str,
    host_id: str, expected_image: str, now: int,
    operator_ack: bool = False,
) -> PreinstallReviewReport:
    """Reconcile exact current evidence without state changes or execution.

    The caller MUST independently authenticate the tenant, publisher, reviewer
    key pin and physical host. The sources are typed, revocation checked,
    bounded and individually verified by their earlier stages. The Stage24
    statement only reports a self-asserted canary; cannot prove runtime safety.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise PreinstallReviewRefused("EXPLICIT_NONPRODUCTION_OPERATOR_REVIEW_REQUIRED")
    if (type(stage22) is not DurableIsolatedCoreGate
            or type(stage23) is not SignedCandidateWitness
            or type(stage24) is not HostObservationLedger
            or type(manifest) is not CoreManifest
            or type(binding) is not CoreBinding
            or type(source) is not bytes
            or type(candidate) is not bytes
            or type(observation) is not bytes
            or type(canary_receipt) is not bytes
            or type(now) is not int):
        raise PreinstallReviewRefused("VALID_REVIEW_ONLY_INPUTS_REQUIRED")
    try:
        # Trust is independently established by distinct Stage23 signing
        # domains + pinned keys and the Stage24 reviewer certificate domain.
        attestation = stage23.current(
            candidate, source=source, manifest=manifest, binding=binding,
            tenant_id=tenant_id, publisher=publisher,
            publisher_key_id=publisher_key_id, image=expected_image, now=now)
        host_statement = stage24.current(
            observation, canary_receipt, expected_host_id=host_id,
            expected_image=expected_image, now=now)
        stage22_state = stage22.state(tenant_id, binding.binding_id)
        row = stage22._row(tenant_id, binding.binding_id)
        # Stage22 execution is prohibited through Stage25, even if another
        # actor manually enabled Stage22 before the review.
        if stage22_state["state"] != "DISABLED":
            raise PreinstallReviewRefused("STAGE22_MUST_BE_DISABLED")
        if (row["core_id"] != manifest.core_id
                or row["core_version"] != manifest.core_version
                or row["instance_id"] != binding.instance_id
                or not hmac.compare_digest(
                    row["manifest_digest"], content_digest(manifest))
                or not hmac.compare_digest(
                    row["binding_digest"], content_digest(binding))
                or not hmac.compare_digest(
                    row["source_sha256"], hashlib.sha256(source).hexdigest())):
            raise PreinstallReviewRefused("STAGE22_ADMISSION_PIN_DRIFT")
        attempt_count = stage22.db.execute(
            "SELECT COUNT(*) FROM secure22_attempts WHERE binding_id=?",
            (binding.binding_id,)).fetchone()[0]
        if attempt_count or stage22_state["verified_evaluations"] != 0:
            raise PreinstallReviewRefused("PRIOR_EXECUTION_ATTEMPT_PRESENT")
        if (attestation.tenant_id != tenant_id
                or attestation.binding_id != binding.binding_id
                or not hmac.compare_digest(
                    attestation.source_sha256,
                    hashlib.sha256(source).hexdigest())
                or host_statement.host_id != host_id
                or host_statement.sequence <= 0
                or not expected_image.endswith(
                    "@sha256:" + expected_image.rsplit("@sha256:", 1)[-1])
                or not stage22.host.policy.enabled
                or stage22.host.policy.image != expected_image):
            raise PreinstallReviewRefused("ISOLATION_OR_PROVENANCE_BINDING_DRIFT")
    except PreinstallReviewRefused:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise PreinstallReviewRefused("INCOMPLETE_REVOKED_OR_INVALID_EVIDENCE") from exc
    return PreinstallReviewReport(
        review_state="LOCAL_CROSS_STAGE_EVIDENCE_MATCHED_NOT_AUTHORIZED",
        tenant_id=tenant_id, binding_id=binding.binding_id,
        manifest_sha256=content_digest(manifest),
        source_sha256=attestation.source_sha256,
        image_sha256=expected_image.rsplit("@sha256:", 1)[-1],
        candidate_envelope_sha256=attestation.envelope_sha256,
        observation_sha256=host_statement.reviewer_statement_sha256,
        stage22_state=stage22_state["state"],
        stage22_revision=stage22_state["revision"],
        chain_checks=(
            "STAGE22_OWNER_TENANT_DISABLED_AND_SOURCE_PIN",
            "STAGE23_DUAL_SIGNATURE_CURRENT",
            "STAGE24_SIGNED_OBSERVATION_CURRENT",
            "STAGE4_PINNED_IMAGE_MATCH",
            "NO_STAGE22_EXECUTION_ATTEMPTS",
        ),
    )


__all__ = [
    "PreinstallReviewRefused", "PreinstallReviewReport",
    "review_preinstall_evidence",
]
