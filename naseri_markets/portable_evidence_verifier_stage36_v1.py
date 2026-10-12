"""Stage36 portable offline verification of Stage32–35 signed claim custody.

The exporter reads an existing owner-private Stage35 SQLite ledger; the
verifier needs NO database, server or network. An OUT-OF-BAND reviewer/auditor
public-key pin and exact binding digest/sequence anchor are mandatory.
A self-consistent, signed bundle is NOT physical host attestation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass

from .a24_publisher_admission import _ed25519, canonical
from .disconnected_host_evidence_stage33_v1 import (
    Stage33Refused, _check_report, _decode_sig, _DOMAIN as _D33,
)
from .disposable_host_preflight_stage32_v1 import (
    _DOMAIN as _D32, _REVIEW_FIELDS, _guard,
)
from .self_observation_evidence_chain_stage35_v1 import (
    SelfObservationEvidenceChain, Stage35Refused, _canonical_json,
    _probe, _signed_packet, _DOMAIN as _D35,
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_BUNDLE_FIELDS = frozenset({
    "schema", "kind", "host_alias", "stage35_sequence",
    "stage32_signed_b64", "stage33_signed_b64",
    "stage34_probe_b64", "stage35_signed_b64",
})
_BYTES = {
    "stage32_signed_b64": 4096,
    "stage33_signed_b64": 12000,
    "stage34_probe_b64": 4096,
    "stage35_signed_b64": 4096,
}


class Stage36Refused(ValueError):
    """Refuse an incomplete or unanchored dossier without leaking raw data."""


def _guard36(ack: bool) -> None:
    try:
        _guard(ack)
    except ValueError as exc:
        raise Stage36Refused("NONPRODUCTION_OFFLINE_AUDIT_ACK_REQUIRED") from exc


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _pin(public: bytes, digest: str) -> None:
    if (type(public) is not bytes or len(public) != 32
            or type(digest) is not str or not _SHA.fullmatch(digest)
            or not hmac.compare_digest(_digest(public), digest)):
        raise Stage36Refused("INDEPENDENT_ED25519_PUBLIC_KEY_PIN_REQUIRED")


def _packed(value: str, *, max_bytes: int) -> bytes:
    if (type(value) is not str
            or not 1 <= len(value) <= ((max_bytes+2)//3)*4):
        raise Stage36Refused("BOUNDED_BASE64_BUNDLE_MEMBER_REQUIRED")
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise Stage36Refused("INVALID_BUNDLE_MEMBER_ENCODING") from exc
    if (not 1 <= len(raw) <= max_bytes
            or base64.b64encode(raw).decode("ascii") != value):
        raise Stage36Refused("NONCANONICAL_BASE64_BUNDLE_MEMBER")
    return raw


def _verified_signature(public: bytes, signature: bytes,
                        domain: bytes, body: dict) -> None:
    try:
        _ed25519(public, signature, domain + canonical(body))
    except (ValueError, TypeError) as exc:
        raise Stage36Refused("INVALID_PINNED_REVIEWER_OR_AUDITOR_SIGNATURE") from exc


@dataclass(frozen=True, slots=True)
class OfflineBundleVerdict:
    host_alias: str
    sequence: int
    pinned_stage35_sha256: str
    stage32_sha256: str
    stage33_sha256: str
    stage34_sha256: str
    state: str = "INDEPENDENT_SIGNATURE_AND_HASH_CUSTODY_VERIFIED_ONLY"
    original_probe_origin_authenticated: bool = False
    actual_host_independently_attested: bool = False
    live_firewall_verified: bool = False
    gvisor_isolation_certified: bool = False
    public_api_deployment_authorized: bool = False
    third_party_plugin_execution_authorized: bool = False
    telegram_send_authorized: bool = False
    broker_order_authorized: bool = False


def export_signed_offline_bundle(
    chain: SelfObservationEvidenceChain, *, host_alias: str,
    sequence: int, operator_ack: bool = False,
) -> bytes:
    """Select one linked self-observation and exact 32/33 signed bytes.

    No file creation or publication. This DOES NOT authenticate that the
    underlying Stage34 receipt was recorded on a physical host. Never
    export the Stage32 TLS private key or any secret from the DB.
    """
    _guard36(operator_ack)
    if (type(chain) is not SelfObservationEvidenceChain
            or type(host_alias) is not str or not _HOST.fullmatch(host_alias)
            or type(sequence) is not int or not 1 <= sequence < 2**63):
        raise Stage36Refused("TRUSTED_EXISTING_CHAIN_SELECTION_REQUIRED")
    db = chain.db
    # Exact single read-only snapshot across all three tables. All mutating
    # writes use the same Stage32 SQLite DB, so an exporter never mixes
    # separate before/after records.
    db.execute("BEGIN")
    try:
        row = db.execute(
            "SELECT * FROM stage35_self_observation_bindings "
            "WHERE host_alias=? AND sequence=?", (host_alias, sequence)
        ).fetchone()
        if row is None:
            raise Stage36Refused("SIGNED_STAGE35_LINK_NOT_FOUND")
        signed33 = db.execute(
            "SELECT signed_envelope FROM stage33_signed_host_claims "
            "WHERE host_alias=? AND signed_sha256=?",
            (host_alias, row["stage33_claim_sha256"]),
        ).fetchone()
        signed32 = db.execute(
            "SELECT signed_envelope FROM stage32_signed_preparation "
            "WHERE host_alias=? AND statement_sha256=?",
            (host_alias, row["stage32_preparation_sha256"]),
        ).fetchone()
        if signed33 is None or signed32 is None:
            raise Stage36Refused("INCOMPLETE_SIGNED_PROVENANCE_CHAIN")
        parts = {
            "stage32_signed_b64": signed32["signed_envelope"],
            "stage33_signed_b64": signed33["signed_envelope"],
            "stage34_probe_b64": row["probe_bytes"],
            "stage35_signed_b64": row["signed_binding"],
        }
        if (not hmac.compare_digest(_digest(parts["stage32_signed_b64"]),
                                    row["stage32_preparation_sha256"])
                or not hmac.compare_digest(_digest(parts["stage33_signed_b64"]),
                                           row["stage33_claim_sha256"])
                or not hmac.compare_digest(_digest(parts["stage34_probe_b64"]),
                                           row["stage34_probe_sha256"])
                or not hmac.compare_digest(_digest(parts["stage35_signed_b64"]),
                                           row["signed_binding_sha256"])
                or any(type(raw) is not bytes or not 1 <= len(raw) <= _BYTES[key]
                       for key, raw in parts.items())):
            raise Stage36Refused("ALTERED_OR_OVERSIZED_LEDGER_MEMBER")
        bundle = canonical({
            "schema": 1, "kind": "stage32_35_offline_custody_bundle",
            "host_alias": host_alias, "stage35_sequence": sequence,
            **{key: base64.b64encode(raw).decode("ascii")
               for key, raw in parts.items()},
        })
        if len(bundle) > 38000:
            raise Stage36Refused("OFFLINE_ARCHIVE_SIZE_BUDGET_EXCEEDED")
        return bundle
    finally:
        db.execute("ROLLBACK")  # ends read snapshot, NEVER mutates evidence


def verify_signed_offline_bundle(
    bundle: bytes, *, reviewer_public_key: bytes,
    reviewer_key_sha256: str, auditor_public_key: bytes,
    auditor_key_sha256: str, expected_host_alias: str,
    expected_nodename: str, pinned_stage35_sha256: str,
    pinned_stage35_sequence: int, now: int,
    operator_ack: bool = False,
) -> OfflineBundleVerdict:
    """Verify all 3 signatures, 4 source hashes and external rollback pin.

    The binding SHA+sequence MUST be received over an independent trusted
    channel. A caller who simply copies them from the bundle has no
    independent rollback protection. Even success is never host attestation.
    """
    _guard36(operator_ack)
    _pin(reviewer_public_key, reviewer_key_sha256)
    _pin(auditor_public_key, auditor_key_sha256)
    if hmac.compare_digest(reviewer_public_key, auditor_public_key):
        raise Stage36Refused("SEPARATE_REVIEW_AND_AUDIT_KEYS_REQUIRED")
    if (type(now) is not int or now < 1
            or type(expected_host_alias) is not str
            or not _HOST.fullmatch(expected_host_alias)
            or type(expected_nodename) is not str
            or not _NODE.fullmatch(expected_nodename)
            or type(pinned_stage35_sha256) is not str
            or not _SHA.fullmatch(pinned_stage35_sha256)
            or type(pinned_stage35_sequence) is not int
            or not 1 <= pinned_stage35_sequence < 2**63):
        raise Stage36Refused("EXTERNALLY_PINNED_BINDING_FLOOR_REQUIRED")
    try:
        archive = _canonical_json(bundle, limit=38000)
        if (set(archive) != _BUNDLE_FIELDS
                or type(archive["schema"]) is not int
                or archive["schema"] != 1
                or archive["kind"] != "stage32_35_offline_custody_bundle"
                or archive["host_alias"] != expected_host_alias
                or type(archive["stage35_sequence"]) is not int
                or archive["stage35_sequence"] != pinned_stage35_sequence):
            raise Stage36Refused("WRONG_HOST_OR_NONCANONICAL_ARCHIVE_SCHEMA")
        parts = {
            key: _packed(archive[key], max_bytes=limit)
            for key, limit in _BYTES.items()
        }
        stage32 = _canonical_json(parts["stage32_signed_b64"], limit=4096)
        stage33 = _canonical_json(parts["stage33_signed_b64"], limit=12000)
        probe_bytes = parts["stage34_probe_b64"]
        binding_bytes = parts["stage35_signed_b64"]
        stage35, stage35_sig = _signed_packet(binding_bytes)
        if (set(stage32) != {"claim", "reviewer_signature_b64"}
                or type(stage32["claim"]) is not dict
                or set(stage32["claim"]) != _REVIEW_FIELDS
                or set(stage33) != {"report", "auditor_signature_b64"}
                or type(stage33["report"]) is not dict):
            raise Stage36Refused("INCOMPLETE_PRIOR_SIGNED_CLAIMS")
        s32 = stage32["claim"]
        s33 = stage33["report"]
        if (type(s32["version"]) is not int or s32["version"] != 1
                or s32["kind"] != "disposable_host_preparation_only"
                or s32["review_scope"] != "static_local_fixture_and_proposal"
                or s32["host_alias"] != expected_host_alias
                or type(s32["sequence"]) is not int or s32["sequence"] < 1
                or type(s32["observed_at"]) is not int
                or type(s32["expires_at"]) is not int
                or not 1 <= s32["observed_at"] <= now < s32["expires_at"]
                or s32["expires_at"] - s32["observed_at"] > 3600
                or any(s32[k] is not False for k in (
                    "actual_host_independently_verified", "internet_service_deployed",
                    "untrusted_code_executed", "public_installer_authorized",
                    "telegram_send_authorized", "broker_orders_authorized"))
                or any(type(s32[k]) is not str or not _SHA.fullmatch(s32[k])
                       for k in ("certificate_sha256", "proposed_policy_sha256"))):
            raise Stage36Refused("INVALID_OR_EXPIRED_STAGE32_PREPARATION")
        _verified_signature(
            reviewer_public_key, _decode_sig(stage32["reviewer_signature_b64"]),
            _D32, s32)
        _verified_signature(
            auditor_public_key, _decode_sig(stage33["auditor_signature_b64"]),
            _D33, s33)
        _check_report(s33, now=now, preparation_sha=_digest(parts["stage32_signed_b64"]))
        _verified_signature(auditor_public_key, stage35_sig, _D35, stage35)
        obs = _probe(probe_bytes, host_alias=expected_host_alias,
                     expected_nodename=expected_nodename, now=now)
        if (type(stage35["version"]) is not int or stage35["version"] != 1
                or stage35["kind"] != "stage34_self_observation_binding"
                or stage35["scope"] != "local_evidence_custody_not_host_attestation"
                or stage35["host_alias"] != expected_host_alias
                or stage35["nodename"] != expected_nodename
                or type(stage35["sequence"]) is not int
                or stage35["sequence"] != pinned_stage35_sequence
                or type(stage35["probe_measured_at"]) is not int
                or stage35["probe_measured_at"] != obs["measured_at"]
                or type(stage35["issued_at"]) is not int
                or type(stage35["expires_at"]) is not int
                or not 1 <= stage35["issued_at"] <= now < stage35["expires_at"]
                or stage35["expires_at"] - stage35["issued_at"] > 600
                or any(stage35[k] is not False for k in (
                    "independent_host_attested", "public_deployment_authorized",
                    "plugin_install_authorized", "broker_order_authorized",
                    "telegram_send_authorized"))
                or not hmac.compare_digest(_digest(binding_bytes),
                                           pinned_stage35_sha256)
                or not hmac.compare_digest(
                    stage35["stage32_preparation_sha256"],
                    _digest(parts["stage32_signed_b64"]))
                or not hmac.compare_digest(
                    stage35["stage33_claim_sha256"],
                    _digest(parts["stage33_signed_b64"]))
                or not hmac.compare_digest(
                    stage35["stage34_probe_sha256"], _digest(probe_bytes))
                or s33["host_alias"] != expected_host_alias
                or s33["stage32_preparation_sha256"] !=
                   _digest(parts["stage32_signed_b64"])
                or obs["measured_at"] > s33["issued_at"]
                or not obs["measured_at"] <= s33["expires_at"]
                or stage35["expires_at"] > s33["expires_at"]
                or s33["expires_at"] > s32["expires_at"]
                or not hmac.compare_digest(
                    obs["local_tls_cert_sha256"], s32["certificate_sha256"])):
            raise Stage36Refused("CROSS_STAGE_PROVENANCE_OR_EXTERNAL_PIN_MISMATCH")
        return OfflineBundleVerdict(
            expected_host_alias, pinned_stage35_sequence, pinned_stage35_sha256,
            _digest(parts["stage32_signed_b64"]),
            _digest(parts["stage33_signed_b64"]), _digest(probe_bytes))
    except Stage36Refused:
        raise
    except (Stage33Refused, Stage35Refused, TypeError, ValueError,
            KeyError, AttributeError) as exc:
        raise Stage36Refused("INVALID_SIGNED_CUSTODY_BUNDLE") from exc


__all__ = [
    "Stage36Refused", "OfflineBundleVerdict",
    "export_signed_offline_bundle", "verify_signed_offline_bundle",
]
