"""Stage35: bind Stage34 SELF-observation to an existing signed Stage33 claim.

This does not run the probe, access a host, make a network connection, start
a server or grant public execution. Signed chain custody is not proof that
a receipt was captured on a real host. The Stage33 auditor signs a separate
domain-bound reference, WITHOUT receiving authority to activate plug-ins.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, fields

from .a24_publisher_admission import _ed25519, canonical
from .designated_host_readonly_probe_stage34_v1 import HostLocalProbeReceipt
from .disconnected_host_evidence_stage33_v1 import (
    DisconnectedHostEvidenceLedger, Stage33Refused, _check_report,
    _decode_sig, _signed_object, _DOMAIN as _D33,
)
from .disposable_host_preflight_stage32_v1 import Stage32Refused, _guard
from .tls_boundary_stage31_v1 import _TLS13_CIPHERS

_DOMAIN = b"MMT-STAGE35-SELF-OBSERVATION-AUDITOR-BIND-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_FIELDS = frozenset(f.name for f in fields(HostLocalProbeReceipt))
_FALSE_FLAGS = frozenset({
    "host_designation_independently_verified",
    "external_tls_or_dns_verified",
    "firewall_policy_independently_verified",
    "outbound_network_denial_verified",
    "reverse_proxy_verified",
    "gvisor_isolation_verified",
    "hostile_source_executed",
    "public_deployment_authorized",
    "plugin_install_authorized",
    "telegram_signal_authorized",
    "broker_order_authorized",
})
_CLAIM_FIELDS = frozenset({
    "version", "kind", "host_alias", "nodename", "sequence",
    "stage32_preparation_sha256", "stage33_claim_sha256",
    "stage34_probe_sha256", "probe_measured_at", "issued_at",
    "expires_at", "scope", "independent_host_attested",
    "public_deployment_authorized", "plugin_install_authorized",
    "broker_order_authorized", "telegram_send_authorized",
})


class Stage35Refused(ValueError):
    """Sanitized refusal; never display host keys, internal DB or raw probe."""


def _guard35(ack: bool) -> None:
    try:
        _guard(ack)
    except Stage32Refused as exc:
        raise Stage35Refused("EXPLICIT_NONPRODUCTION_REVIEW_ACK_REQUIRED") from exc


def _unique(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise Stage35Refused("DUPLICATE_CANONICAL_EVIDENCE_FIELD")
        result[key] = val
    return result


def _canonical_json(raw: bytes, *, limit: int) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        raise Stage35Refused("BOUNDED_EVIDENCE_REQUIRED")
    try:
        obj = json.loads(
            raw.decode("ascii"), object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                Stage35Refused("NONFINITE_EVIDENCE_FORBIDDEN")))
        if type(obj) is not dict or canonical(obj) != raw:
            raise Stage35Refused("CANONICAL_JSON_EVIDENCE_REQUIRED")
        return obj
    except Stage35Refused:
        raise
    except (ValueError, UnicodeError, RecursionError, TypeError) as exc:
        raise Stage35Refused("INVALID_OR_NONCANONICAL_EVIDENCE") from exc


def _probe(raw: bytes, *, host_alias: str, expected_nodename: str,
           now: int) -> dict:
    """Stage34 fields, types, freshness and _explicitly false_ authorizations."""
    obj = _canonical_json(raw, limit=4096)
    if (set(obj) != _FIELDS
            or type(obj["host_alias"]) is not str
            or obj["host_alias"] != host_alias
            or type(obj["nodename"]) is not str
            or obj["nodename"] != expected_nodename
            or type(obj["measured_at"]) is not int
            or not now - 600 <= obj["measured_at"] <= now
            or type(obj["listener_snapshot_sha256"]) is not str
            or not _SHA.fullmatch(obj["listener_snapshot_sha256"])
            or type(obj["local_listener_count"]) is not int
            or not 1 <= obj["local_listener_count"] <= 128
            or type(obj["local_tls_cert_sha256"]) is not str
            or not _SHA.fullmatch(obj["local_tls_cert_sha256"])
            or type(obj["local_tls_cipher"]) is not str
            or obj["local_tls_cipher"] not in _TLS13_CIPHERS
            or obj["state"] !=
               "ON_HOST_SELF_OBSERVATION_NOT_INDEPENDENT_ATTESTATION"
            or obj["real_loopback_tls_handshake_observed"] is not True
            or any(obj[k] is not False for k in _FALSE_FLAGS)):
        raise Stage35Refused("STAGE34_RECEIPT_SCOPE_OR_FRESHNESS_REJECTED")
    return obj


def _signed_packet(raw: bytes) -> tuple[dict, bytes]:
    obj = _canonical_json(raw, limit=4096)
    if set(obj) != {"claim", "auditor_signature_b64"}:
        raise Stage35Refused("EXACT_SIGNED_BINDING_ENVELOPE_REQUIRED")
    claim = obj["claim"]
    if type(claim) is not dict or set(claim) != _CLAIM_FIELDS:
        raise Stage35Refused("EXACT_SIGNED_BINDING_CLAIM_REQUIRED")
    try:
        sig = _decode_sig(obj["auditor_signature_b64"])
    except (Stage33Refused, ValueError) as exc:
        raise Stage35Refused("INVALID_STAGE35_AUDITOR_SIGNATURE") from exc
    return claim, sig


@dataclass(frozen=True, slots=True)
class Stage35ChainReceipt:
    host_alias: str
    sequence: int
    stage32_preparation_sha256: str
    stage33_claim_sha256: str
    stage34_probe_sha256: str
    signed_binding_sha256: str
    state: str = "STAGE34_SELF_OBSERVATION_CHAINED_NOT_HOST_ATTESTED"
    actual_host_independently_attested: bool = False
    real_public_tls_verified: bool = False
    firewall_independently_verified: bool = False
    gvisor_isolation_verified: bool = False
    public_deployment_authorized: bool = False
    public_installer_authorized: bool = False
    untrusted_source_execution_authorized: bool = False
    telegram_send_authorized: bool = False
    broker_order_authorized: bool = False


class SelfObservationEvidenceChain:
    """Append-only Stage35 link attached to the SAME Stage32/33 private DB.

    Caller must separately pin the expected nodename and present Stage34
    canonical bytes. All Stage33/32 signatures are revalidated on record.
    Local-only guarantees: no remote attestation or custody of probe origin.
    """

    def __init__(self, stage33: DisconnectedHostEvidenceLedger, *,
                 operator_ack: bool = False) -> None:
        _guard35(operator_ack)
        if type(stage33) is not DisconnectedHostEvidenceLedger:
            raise Stage35Refused("TRUSTED_STAGE33_SIGNED_LEDGER_REQUIRED")
        self.stage33 = stage33
        self.db = stage33.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS stage35_self_observation_bindings(
                host_alias TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                stage32_preparation_sha256 TEXT NOT NULL,
                stage33_claim_sha256 TEXT NOT NULL UNIQUE,
                stage34_probe_sha256 TEXT NOT NULL UNIQUE,
                signed_binding_sha256 TEXT NOT NULL UNIQUE,
                signed_binding BLOB NOT NULL,
                probe_bytes BLOB NOT NULL,
                PRIMARY KEY(host_alias,sequence)
            );
            CREATE TRIGGER IF NOT EXISTS stage35_no_update
            BEFORE UPDATE ON stage35_self_observation_bindings
            BEGIN SELECT RAISE(ABORT,'STAGE35_IMMUTABLE_CHAIN'); END;
            CREATE TRIGGER IF NOT EXISTS stage35_no_delete
            BEFORE DELETE ON stage35_self_observation_bindings
            BEGIN SELECT RAISE(ABORT,'STAGE35_IMMUTABLE_CHAIN'); END;
        """)

    def record(
        self, *, stage34_probe: bytes, signed_binding: bytes,
        expected_nodename: str, now: int, operator_ack: bool = False,
    ) -> Stage35ChainReceipt:
        _guard35(operator_ack)
        if (type(now) is not int or now < 1
                or type(expected_nodename) is not str
                or not _NODE.fullmatch(expected_nodename)):
            raise Stage35Refused("OPERATOR_PINNED_NODENAME_AND_CLOCK_REQUIRED")
        claim, signature = _signed_packet(signed_binding)
        if (type(claim["version"]) is not int or claim["version"] != 1
                or claim["kind"] != "stage34_self_observation_binding"
                or claim["scope"] != "local_evidence_custody_not_host_attestation"
                or type(claim["host_alias"]) is not str
                or not _HOST.fullmatch(claim["host_alias"])
                or type(claim["nodename"]) is not str
                or claim["nodename"] != expected_nodename
                or type(claim["sequence"]) is not int
                or not 1 <= claim["sequence"] < 2**63
                or type(claim["issued_at"]) is not int
                or type(claim["expires_at"]) is not int
                or not 1 <= claim["issued_at"] <= now < claim["expires_at"]
                or claim["expires_at"] - claim["issued_at"] > 600
                or type(claim["probe_measured_at"]) is not int
                or any(claim[k] is not False for k in (
                    "independent_host_attested", "public_deployment_authorized",
                    "plugin_install_authorized", "broker_order_authorized",
                    "telegram_send_authorized"))
                or any(type(claim[k]) is not str or not _SHA.fullmatch(claim[k])
                       for k in (
                           "stage32_preparation_sha256",
                           "stage33_claim_sha256", "stage34_probe_sha256"))):
            raise Stage35Refused("ESCALATED_OR_INVALID_BINDING_STATEMENT")
        try:
            _ed25519(self.stage33.auditor_public_key, signature,
                     _DOMAIN + canonical(claim))
        except (ValueError, TypeError) as exc:
            raise Stage35Refused("WRONG_STAGE35_AUDITOR_SIGNATURE") from exc
        host_alias = claim["host_alias"]
        probe = _probe(stage34_probe, host_alias=host_alias,
                       expected_nodename=expected_nodename, now=now)
        if (claim["probe_measured_at"] != probe["measured_at"]
                or not hmac.compare_digest(
                    hashlib.sha256(stage34_probe).hexdigest(),
                    claim["stage34_probe_sha256"])):
            raise Stage35Refused("STAGE34_EVIDENCE_DIGEST_OR_TIME_CHANGED")
        signed_hash = hashlib.sha256(signed_binding).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT * FROM stage33_signed_host_claims "
                "WHERE host_alias=? AND signed_sha256=?",
                (host_alias, claim["stage33_claim_sha256"])).fetchone()
            if row is None:
                raise Stage35Refused("STAGE33_CLAIM_NOT_FOUND")
            # Do not attach older Stage33 claims after a newer signed
            # assessment exists: single latest reviewer snapshot only.
            last33 = self.db.execute(
                "SELECT MAX(sequence) FROM stage33_signed_host_claims "
                "WHERE host_alias=?", (host_alias,)).fetchone()[0]
            if row["sequence"] != last33:
                raise Stage35Refused("SUPERSEDED_STAGE33_ASSESSMENT")
            signed33 = _signed_object(row["signed_envelope"])
            report = signed33["report"]
            try:
                _ed25519(self.stage33.auditor_public_key,
                         _decode_sig(signed33["auditor_signature_b64"]),
                         _D33 + canonical(report))
                _check_report(report, now=now,
                              preparation_sha=claim[
                                  "stage32_preparation_sha256"])
                self.stage33._preparation_row(
                    host_alias, claim["stage32_preparation_sha256"], now)
            except (Stage33Refused, ValueError, TypeError, KeyError) as exc:
                raise Stage35Refused("STAGE32_33_PROVENANCE_RECHECK_FAILED") from exc
            if (report["host_alias"] != host_alias
                    or report["sequence"] != row["sequence"]
                    or row["stage32_preparation_sha256"] !=
                       claim["stage32_preparation_sha256"]
                    or report["issued_at"] > probe["measured_at"]
                    or not probe["measured_at"] <= report["expires_at"]
                    or claim["expires_at"] > report["expires_at"]):
                raise Stage35Refused("CROSS_STAGE_TIMELINE_OR_IDENTITY_MISMATCH")
            prep = self.db.execute(
                "SELECT certificate_sha256 FROM stage32_signed_preparation "
                "WHERE host_alias=? AND statement_sha256=?",
                (host_alias, claim["stage32_preparation_sha256"])).fetchone()
            if (prep is None or not hmac.compare_digest(
                    prep["certificate_sha256"],
                    probe["local_tls_cert_sha256"])):
                raise Stage35Refused("STAGE32_CERTIFICATE_PROBE_PIN_MISMATCH")
            prev = self.db.execute(
                "SELECT MAX(sequence) FROM stage35_self_observation_bindings "
                "WHERE host_alias=?", (host_alias,)).fetchone()[0]
            if claim["sequence"] != (1 if prev is None else prev + 1):
                raise Stage35Refused("STAGE35_SEQUENCE_REPLAY_OR_GAP")
            self.db.execute(
                "INSERT INTO stage35_self_observation_bindings VALUES("
                "?,?,?,?,?,?,?,?)",
                (host_alias, claim["sequence"],
                 claim["stage32_preparation_sha256"],
                 claim["stage33_claim_sha256"],
                 claim["stage34_probe_sha256"], signed_hash,
                 signed_binding, stage34_probe))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return Stage35ChainReceipt(
            host_alias, claim["sequence"],
            claim["stage32_preparation_sha256"],
            claim["stage33_claim_sha256"],
            claim["stage34_probe_sha256"], signed_hash)

    def status(self, host_alias: str) -> dict:
        if type(host_alias) is not str or not _HOST.fullmatch(host_alias):
            raise Stage35Refused("VALID_HOST_ALIAS_REQUIRED")
        row = self.db.execute(
            "SELECT COUNT(*) AS n, MAX(sequence) AS last "
            "FROM stage35_self_observation_bindings WHERE host_alias=?",
            (host_alias,)).fetchone()
        return {
            "host_alias": host_alias,
            "linked_self_observations": row["n"],
            "latest_sequence": row["last"],
            "real_host_independently_verified": False,
            "actual_firewall_verified": False,
            "gvisor_isolation_certified": False,
            "public_api_authorized": False,
            "public_plugin_install_authorized": False,
            "telegram_send_authorized": False,
            "broker_order_authorized": False,
        }


__all__ = [
    "Stage35Refused", "Stage35ChainReceipt", "SelfObservationEvidenceChain",
    "_DOMAIN",
]
