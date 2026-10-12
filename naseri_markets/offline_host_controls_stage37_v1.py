"""Stage37 fail-closed STATIC review of offline firewall and gVisor snapshots.

The inputs are NOT live host measurements. This module parses a deliberately
restrictive subset of nftables JSON and a bounded operator-normalized runtime
configuration, binds their exact bytes to a separately pinned Ed25519 review,
and rechecks Stage36's independent portable evidence chain. It never executes
commands, connects to a machine, loads code, or authorizes public deployment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass

from .a24_publisher_admission import _ed25519, canonical
from .portable_evidence_verifier_stage36_v1 import (
    Stage36Refused, verify_signed_offline_bundle,
)
from .disposable_host_preflight_stage32_v1 import _guard

_DOMAIN = b"MMT-STAGE37-OFFLINE-CONTROLS-REVIEW-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_REVIEW_KEYS = frozenset({
    "schema", "scope", "host_alias", "stage35_binding_sha256",
    "firewall_snapshot_sha256", "runtime_snapshot_sha256", "challenge",
    "issued_at", "expires_at", "real_host_attested",
    "public_deployment_authorized", "plugin_execution_authorized",
    "telegram_send_authorized", "broker_order_authorized",
})
_RUNTIME_KEYS = frozenset({
    "runtime", "network_mode", "rootfs_readonly", "privileged", "user",
    "cap_add", "cap_drop", "bind_mounts", "devices", "published_ports",
    "security_opt", "pids_limit", "memory_limit_bytes", "nano_cpus",
    "ipc_mode", "pid_mode", "cgroupns_mode", "init_process_kind",
})


class Stage37Refused(ValueError):
    """Sanitized security-review refusal; no raw host configuration exposed."""


def _guard37(ack: bool) -> None:
    try:
        _guard(ack)
    except ValueError as exc:
        raise Stage37Refused("EXPLICIT_NONPRODUCTION_REVIEW_ACK_REQUIRED") from exc


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Stage37Refused("DUPLICATE_STATIC_CONFIG_KEY")
        result[key] = value
    return result


def _load(raw: bytes, limit: int):
    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        raise Stage37Refused("BOUNDED_OFFLINE_CONFIG_REQUIRED")
    try:
        return json.loads(
            raw.decode("ascii"), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                Stage37Refused("NONFINITE_CONFIG_VALUE")))
    except Stage37Refused:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Stage37Refused("INVALID_OFFLINE_CONFIG_JSON") from exc


def _limited_keys(value: dict, required: set[str], optional=()) -> bool:
    return (type(value) is dict and set(value).issuperset(required)
            and set(value).issubset(required | set(optional)))


def review_nftables_static_snapshot(raw: bytes) -> int:
    """Review a tiny, deliberate nftables template, never actual firewall state.

    Require ONLY inet/mmt_disposable input/output/forward base chains
    with DROP defaults. Only input/output interface==lo ACCEPT rules
    are permitted. Other families, NAT, chains, target, verdict,
    unknown expressions and incomplete tables fail closed.
    """
    obj = _load(raw, 32768)
    if type(obj) is not dict or set(obj) != {"nftables"}:
        raise Stage37Refused("EXACT_NFTABLES_WRAPPER_REQUIRED")
    entries = obj["nftables"]
    if type(entries) is not list or not 4 <= len(entries) <= 10:
        raise Stage37Refused("BOUNDED_NFTABLES_BASE_CHAINS_REQUIRED")
    table = False
    chains = set()
    rules = set()
    for entry in entries:
        if type(entry) is not dict or len(entry) != 1:
            raise Stage37Refused("UNEXPECTED_FIREWALL_ENTRY")
        kind, value = next(iter(entry.items()))
        if kind == "metainfo":
            if type(value) is not dict:
                raise Stage37Refused("INVALID_NFTABLES_METADATA")
            continue
        if kind == "table":
            if (table or not _limited_keys(
                    value, {"family", "name"}, {"handle"})
                    or value["family"] != "inet"
                    or value["name"] != "mmt_disposable"):
                raise Stage37Refused("UNREVIEWED_FIREWALL_TABLE")
            table = True
            continue
        if kind == "chain":
            if (not _limited_keys(
                    value, {"family", "table", "name", "type", "hook",
                            "prio", "policy"}, {"handle", "dev"})
                    or value["family"] != "inet"
                    or value["table"] != "mmt_disposable"
                    or type(value["name"]) is not str
                    or value["name"] not in ("input", "output", "forward")
                    or value["name"] in chains
                    or value["type"] != "filter"
                    or value["hook"] != value["name"]
                    or type(value["prio"]) is not int
                    or value["prio"] != 0
                    or value["policy"] != "drop"
                    or "dev" in value):
                raise Stage37Refused("NON_DROP_BASE_CHAIN_OR_UNSAFE_HOOK")
            chains.add(value["name"])
            continue
        if kind == "rule":
            if not _limited_keys(
                    value, {"family", "table", "chain", "expr"},
                    {"handle", "comment"}):
                raise Stage37Refused("UNREVIEWED_FIREWALL_RULE_FIELDS")
            chain = value["chain"]
            if (value["family"] != "inet"
                    or value["table"] != "mmt_disposable"
                    or type(chain) is not str
                    or chain not in ("input", "output")
                    or chain in rules):
                raise Stage37Refused("UNSAFE_OR_DUPLICATE_FIREWALL_ACCEPT")
            expected = "iifname" if chain == "input" else "oifname"
            expression = [
                {"match": {"left": {"meta": {"key": expected}},
                           "op": "==", "right": "lo"}},
                {"accept": None},
            ]
            if value["expr"] != expression:
                raise Stage37Refused("NON_LOOPBACK_FIREWALL_ACCEPT")
            rules.add(chain)
            continue
        raise Stage37Refused("UNREVIEWED_NFTABLES_FEATURE")
    if not table or chains != {"input", "output", "forward"} or rules != {
            "input", "output"}:
        raise Stage37Refused("MISSING_DROP_OR_LOOPBACK_CHAIN")
    return len(chains)


def review_gvisor_static_snapshot(raw: bytes) -> str:
    """Validate one operator-projected runsc policy; never a running process."""
    cfg = _load(raw, 4096)
    if (type(cfg) is not dict or set(cfg) != _RUNTIME_KEYS
            or cfg["runtime"] != "runsc"
            or cfg["network_mode"] != "none"
            or cfg["rootfs_readonly"] is not True
            or cfg["privileged"] is not False
            or cfg["user"] != "65534:65534"
            or cfg["cap_add"] != []
            or cfg["cap_drop"] != ["ALL"]
            or cfg["bind_mounts"] != []
            or cfg["devices"] != []
            or cfg["published_ports"] != {}
            or cfg["security_opt"] != ["no-new-privileges"]
            or type(cfg["pids_limit"]) is not int
            or not 1 <= cfg["pids_limit"] <= 32
            or type(cfg["memory_limit_bytes"]) is not int
            or not 128 * 1024**2 <= cfg["memory_limit_bytes"] <= 512 * 1024**2
            or type(cfg["nano_cpus"]) is not int
            or not 1 <= cfg["nano_cpus"] <= 1_000_000_000
            or cfg["ipc_mode"] != "private"
            or cfg["pid_mode"] != ""
            or cfg["cgroupns_mode"] != "private"
            or cfg["init_process_kind"] != "fixed_harmless_canary_no_user_code"):
        raise Stage37Refused("NONCONFORMING_RUNSC_REVIEW_TEMPLATE")
    return "STATIC_GVISOR_POLICY_REVIEWED_NOT_RUNTIME_VERIFIED"


@dataclass(frozen=True, slots=True)
class OfflineHostControlsReceipt:
    host_alias: str
    stage35_binding_sha256: str
    firewall_snapshot_sha256: str
    runtime_snapshot_sha256: str
    accepted_drop_chains: int
    state: str = "STATIC_CONTROL_TEMPLATES_REVIEWED_NOT_HOST_ACCEPTED"
    actual_host_independently_attested: bool = False
    tls_endpoint_independently_verified: bool = False
    firewall_actually_enforced: bool = False
    runtime_gvisor_actually_verified: bool = False
    hostile_code_containment_certified: bool = False
    public_deployment_authorized: bool = False
    third_party_core_execution_authorized: bool = False
    telegram_signal_authorized: bool = False
    broker_order_authorized: bool = False


def verify_offline_host_controls(
    bundle: bytes, *, stage36_verification: dict,
    firewall_snapshot: bytes, runtime_snapshot: bytes,
    signed_review: bytes, reviewer_public_key: bytes,
    reviewer_public_key_sha256: str,
    expected_host_alias: str, expected_challenge: str,
    now: int, operator_ack: bool = False,
) -> OfflineHostControlsReceipt:
    """Offline Stage36+37 validation, no execution and no release permission.

    The *entire* stage36_verification dict is trusted-operator supplied, not
    read from bundle or request payload. Out-of-band 35 pin and reviewer
    key/challenge must come from independent custody, never self-bootstrap.
    """
    _guard37(operator_ack)
    if (type(stage36_verification) is not dict
            or type(now) is not int or now < 1
            or type(expected_host_alias) is not str
            or not _HOST.fullmatch(expected_host_alias)
            or type(expected_challenge) is not str
            or not _NONCE.fullmatch(expected_challenge)
            or type(reviewer_public_key) is not bytes
            or len(reviewer_public_key) != 32
            or type(reviewer_public_key_sha256) is not str
            or not _SHA.fullmatch(reviewer_public_key_sha256)
            or not hmac.compare_digest(
                hashlib.sha256(reviewer_public_key).hexdigest(),
                reviewer_public_key_sha256)
            or reviewer_public_key in (
                stage36_verification.get("reviewer_public_key"),
                stage36_verification.get("auditor_public_key"))):
        raise Stage37Refused("SEPARATELY_PINNED_REVIEWER_AND_NONCE_REQUIRED")
    if (stage36_verification.get("expected_host_alias") != expected_host_alias
            or stage36_verification.get("now") != now
            or stage36_verification.get("operator_ack") is not True):
        raise Stage37Refused("OPERATOR_STAGE36_HOST_OR_TIME_MISMATCH")
    try:
        chain = verify_signed_offline_bundle(bundle, **stage36_verification)
    except (Stage36Refused, TypeError) as exc:
        raise Stage37Refused("INVALID_PRIOR_SIGNED_PROVENANCE") from exc
    nft_chains = review_nftables_static_snapshot(firewall_snapshot)
    review_gvisor_static_snapshot(runtime_snapshot)
    claim = _load(signed_review, 4096)
    if (type(claim) is not dict
            or set(claim) != {"review", "signature_b64"}
            or canonical(claim) != signed_review):
        raise Stage37Refused("CANONICAL_REVIEW_ENVELOPE_REQUIRED")
    statement = claim["review"]
    if (type(statement) is not dict or set(statement) != _REVIEW_KEYS
            or type(statement["schema"]) is not int
            or statement["schema"] != 1
            or statement["scope"] != "static_snapshot_review_only"
            or statement["host_alias"] != expected_host_alias
            or statement["stage35_binding_sha256"] !=
               chain.pinned_stage35_sha256
            or statement["firewall_snapshot_sha256"] !=
               hashlib.sha256(firewall_snapshot).hexdigest()
            or statement["runtime_snapshot_sha256"] !=
               hashlib.sha256(runtime_snapshot).hexdigest()
            or statement["challenge"] != expected_challenge
            or type(statement["issued_at"]) is not int
            or type(statement["expires_at"]) is not int
            or not now-300 <= statement["issued_at"] <= now
            or not now < statement["expires_at"] <= statement["issued_at"]+300
            or any(statement[k] is not False for k in (
                "real_host_attested", "public_deployment_authorized",
                "plugin_execution_authorized", "telegram_send_authorized",
                "broker_order_authorized"))):
        raise Stage37Refused("MISMATCHED_OR_PRIVILEGED_CONTROL_REVIEW")
    try:
        signature = claim["signature_b64"]
        if type(signature) is not str or len(signature) != 88:
            raise ValueError
        import base64
        sig = base64.b64decode(signature, validate=True)
        if (len(sig) != 64
                or base64.b64encode(sig).decode("ascii") != signature):
            raise ValueError
        _ed25519(reviewer_public_key, sig, _DOMAIN + canonical(statement))
    except (ValueError, TypeError) as exc:
        raise Stage37Refused("INVALID_THIRD_REVIEWER_SIGNATURE") from exc
    return OfflineHostControlsReceipt(
        expected_host_alias, chain.pinned_stage35_sha256,
        hashlib.sha256(firewall_snapshot).hexdigest(),
        hashlib.sha256(runtime_snapshot).hexdigest(), nft_chains)


__all__ = [
    "Stage37Refused", "OfflineHostControlsReceipt",
    "review_nftables_static_snapshot", "review_gvisor_static_snapshot",
    "verify_offline_host_controls", "_DOMAIN",
]
