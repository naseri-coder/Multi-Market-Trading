"""Stage39 offline reconciliation of Stage37 DECLARED policy and Stage38 self-report.

Requires the full Stage36/37 independently-pinned evidence chain and a fourth
separately pinned review signature. Does not sample a real host or establish
the origin of the Stage38 JSON. Cannot authorize installation or execution.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass, fields

from .a24_publisher_admission import _ed25519, canonical
from .disposable_host_preflight_stage32_v1 import _guard
from .offline_host_controls_stage37_v1 import (
    Stage37Refused, _load, verify_offline_host_controls,
)
from .passive_kernel_posture_stage38_v1 import PassiveKernelObservationReceipt
from .portable_evidence_verifier_stage36_v1 import _packed
from .self_observation_evidence_chain_stage35_v1 import _canonical_json

_DOMAIN = b"MMT-STAGE39-OFFLINE-DECLARED-RUNTIME-OBSERVATION-BIND-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_FIELDS = frozenset(f.name for f in fields(PassiveKernelObservationReceipt))
_REVIEW_FIELDS = frozenset({
    "schema", "kind", "scope", "host_alias", "nodename", "challenge",
    "stage35_binding_sha256", "stage37_review_sha256",
    "stage38_self_report_sha256", "self_observed_at",
    "issued_at", "expires_at", "independent_host_attested",
    "runtime_isolation_independently_verified",
    "actual_firewall_verified", "public_deployment_authorized",
    "plugin_execution_authorized", "telegram_send_authorized",
    "broker_order_authorized",
})
_FALSE_FLAGS = (
    "independent_host_identity_verified",
    "nftables_active_ruleset_independently_verified",
    "network_egress_independently_blocked",
    "other_container_gvisor_verified",
    "gvisor_escape_containment_certified",
    "public_api_deployment_authorized",
    "plugin_execution_authorized",
    "telegram_publish_authorized",
    "broker_order_authorized",
)


class Stage39Refused(ValueError):
    """Static-only refusal. Never echo source, process data or credentials."""


def _guard39(ack: bool) -> None:
    try:
        _guard(ack)
    except ValueError as exc:
        raise Stage39Refused("EXPLICIT_NONPRODUCTION_RECONCILIATION_ACK_REQUIRED") from exc


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _signed_review(raw: bytes) -> tuple[dict, bytes]:
    doc = _canonical_json(raw, limit=4096)
    if set(doc) != {"review", "signature_b64"}:
        raise Stage39Refused("EXACT_FOURTH_REVIEW_ENVELOPE_REQUIRED")
    statement = doc["review"]
    if type(statement) is not dict or set(statement) != _REVIEW_FIELDS:
        raise Stage39Refused("EXACT_FOURTH_REVIEW_CLAIM_REQUIRED")
    signature = doc["signature_b64"]
    if type(signature) is not str or len(signature) != 88:
        raise Stage39Refused("FOURTH_REVIEW_SIGNATURE_REQUIRED")
    try:
        sig = base64.b64decode(signature, validate=True)
    except ValueError as exc:
        raise Stage39Refused("INVALID_FOURTH_REVIEW_SIGNATURE") from exc
    if (len(sig) != 64
            or base64.b64encode(sig).decode("ascii") != signature):
        raise Stage39Refused("NONCANONICAL_FOURTH_REVIEW_SIGNATURE")
    return statement, sig


def _self_report(
    raw: bytes, *, host: str, nodename: str, now: int,
    expected_uid: int, expected_gid: int,
    stage34_measured_at: int,
) -> dict:
    obj = _canonical_json(raw, limit=4096)
    if (set(obj) != _FIELDS
            or obj["state"] !=
            "LOCAL_PROCESS_KERNEL_POSTURE_ONLY_NO_RUNTIME_ATTESTATION"
            or obj["host_alias"] != host
            or obj["nodename"] != nodename
            or obj["local_process_restrictive_snapshot"] is not True
            or type(obj["process_uid"]) is not int
            or type(obj["process_gid"]) is not int
            or obj["process_uid"] != expected_uid
            or obj["process_gid"] != expected_gid
            or type(obj["measured_at"]) is not int
            or not now-300 <= obj["measured_at"] <= now
            or not stage34_measured_at <= obj["measured_at"]
            or obj["measured_at"]-stage34_measured_at > 300
            or type(obj["loopback_routes_seen"]) is not int
            or not 0 <= obj["loopback_routes_seen"] <= 256
            or any(type(obj[name]) is not str or not _SHA.fullmatch(obj[name])
                   for name in (
                       "proc_status_sha256", "proc_mountinfo_sha256",
                       "proc_ipv4_routes_sha256", "proc_ipv6_routes_sha256"))
            or any(obj[name] is not False for name in _FALSE_FLAGS)):
        raise Stage39Refused("SELF_OBSERVATION_POLICY_OR_FRESHNESS_CONFLICT")
    return obj


@dataclass(frozen=True, slots=True)
class StaticProcessAlignmentReceipt:
    host_alias: str
    nodename: str
    stage35_binding_sha256: str
    stage37_review_sha256: str
    stage38_self_report_sha256: str
    signed_alignment_sha256: str
    state: str = "SIGNED_OFFLINE_POLICY_ALIGNMENT_NOT_HOST_ATTESTED"
    actual_gvisor_sandbox_observed: bool = False
    self_report_origin_authenticated: bool = False
    actual_host_independently_verified: bool = False
    firewall_rules_actually_enforced: bool = False
    outbound_network_deny_verified: bool = False
    code_containment_certified: bool = False
    public_deployment_authorized: bool = False
    public_plugin_execution_authorized: bool = False
    telegram_publish_authorized: bool = False
    broker_order_authorized: bool = False


def verify_offline_runtime_alignment(
    bundle: bytes, *, stage37_options: dict,
    stage38_self_report: bytes, signed_alignment: bytes,
    witness_public_key: bytes, witness_public_key_sha256: str,
    expected_host_alias: str, expected_nodename: str,
    expected_challenge: str, now: int,
    operator_ack: bool = False,
) -> StaticProcessAlignmentReceipt:
    """Confirm *consistency* of declared policy and self-report, NOT truth.

    No network, procfs reads, cryptographic key creation, database writes,
    gVisor invocation, installation, public deployment or broker operations.
    An externally anchored Stage35 checkpoint, the Stage37 reviewer key and
    a separate fourth witness key are required out of band.
    """
    _guard39(operator_ack)
    if (type(now) is not int or now < 1
            or type(stage37_options) is not dict
            or type(expected_host_alias) is not str
            or not _HOST.fullmatch(expected_host_alias)
            or type(expected_nodename) is not str
            or not _NODE.fullmatch(expected_nodename)
            or type(expected_challenge) is not str
            or not _NONCE.fullmatch(expected_challenge)
            or type(witness_public_key) is not bytes
            or len(witness_public_key) != 32
            or type(witness_public_key_sha256) is not str
            or not _SHA.fullmatch(witness_public_key_sha256)
            or not hmac.compare_digest(
                _digest(witness_public_key), witness_public_key_sha256)):
        raise Stage39Refused("EXTERNALLY_PINNED_FOURTH_WITNESS_REQUIRED")
    prior = stage37_options.get("stage36_verification")
    if (type(prior) is not dict
            or stage37_options.get("expected_host_alias") != expected_host_alias
            or stage37_options.get("now") != now
            or stage37_options.get("operator_ack") is not True
            or prior.get("expected_nodename") != expected_nodename
            or prior.get("pinned_stage35_sha256") is None
            or any(witness_public_key == key for key in (
                prior.get("reviewer_public_key"),
                prior.get("auditor_public_key"),
                stage37_options.get("reviewer_public_key")))):
        raise Stage39Refused("PRIOR_PROVENANCE_OR_SIGNER_ROLES_NOT_PINNED")
    try:
        review37 = verify_offline_host_controls(bundle, **stage37_options)
    except (Stage37Refused, TypeError, ValueError) as exc:
        raise Stage39Refused("REJECTED_STAGE37_OFFLINE_POLICY_CHAIN") from exc
    try:
        # A Stage36 archive can only be used with its separate out-of-band pin.
        archive = _canonical_json(bundle, limit=38000)
        raw34 = _packed(archive["stage34_probe_b64"], max_bytes=4096)
        prior_probe = _canonical_json(raw34, limit=4096)
        runtime = _load(stage37_options["runtime_snapshot"], 4096)
        uid, gid = (int(x) for x in runtime["user"].split(":"))
        observation = _self_report(
            stage38_self_report, host=expected_host_alias,
            nodename=expected_nodename, now=now,
            expected_uid=uid, expected_gid=gid,
            stage34_measured_at=prior_probe["measured_at"])
        prior_review = _canonical_json(
            stage37_options["signed_review"], limit=4096)["review"]
        claim, sig = _signed_review(signed_alignment)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise Stage39Refused("INVALID_OR_MISSING_OFFLINE_OBSERVATION") from exc
    if (type(claim["schema"]) is not int or claim["schema"] != 1
            or claim["kind"] != "static_runsc_to_self_process_alignment"
            or claim["scope"] != "signed_self_report_not_runtime_attestation"
            or claim["host_alias"] != expected_host_alias
            or claim["nodename"] != expected_nodename
            or claim["stage35_binding_sha256"] !=
               review37.stage35_binding_sha256
            or claim["stage37_review_sha256"] !=
               _digest(stage37_options["signed_review"])
            or claim["stage38_self_report_sha256"] !=
               _digest(stage38_self_report)
            or claim["challenge"] != expected_challenge
            or type(claim["self_observed_at"]) is not int
            or claim["self_observed_at"] != observation["measured_at"]
            or type(claim["issued_at"]) is not int
            or type(claim["expires_at"]) is not int
            or not observation["measured_at"] <= claim["issued_at"] <= now
            or not prior_review["issued_at"] <= claim["issued_at"]
            or not now < claim["expires_at"] <= claim["issued_at"]+300
            or any(claim[name] is not False for name in (
                "independent_host_attested",
                "runtime_isolation_independently_verified",
                "actual_firewall_verified", "public_deployment_authorized",
                "plugin_execution_authorized", "telegram_send_authorized",
                "broker_order_authorized"))):
        raise Stage39Refused("ESCALATED_OR_MISMATCHED_FOURTH_WITNESS_CLAIM")
    try:
        _ed25519(
            witness_public_key, sig, _DOMAIN + canonical(claim))
    except (TypeError, ValueError) as exc:
        raise Stage39Refused("INVALID_FOURTH_WITNESS_SIGNATURE") from exc
    return StaticProcessAlignmentReceipt(
        expected_host_alias, expected_nodename,
        review37.stage35_binding_sha256,
        _digest(stage37_options["signed_review"]),
        _digest(stage38_self_report), _digest(signed_alignment))


__all__ = [
    "Stage39Refused", "StaticProcessAlignmentReceipt",
    "verify_offline_runtime_alignment", "_DOMAIN",
]
