"""Stage33 disconnected disposable-host assessment CLAIM custody.

NO host designated: reports in this module are reviewer-signed DECLARATIONS,
not observed independent network, TLS, OS isolation or gVisor attestation.
An operator must supply evidence from an explicitly authorized host later.
Even all declared PASSes produce NO installation/deployment authorization.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
from dataclasses import dataclass

from .a24_publisher_admission import _ed25519, canonical
from .disposable_host_preflight_stage32_v1 import (
    HostPreparationDossier, Stage32Refused, _guard,
)

_DOMAIN = b"MMT-STAGE33-DISCONNECTED-HOST-EVIDENCE-REVIEW-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_CHECKS = frozenset({
    "designated_disposable_host_custody",
    "os_and_runtime_provenance",
    "tls13_real_endpoint_handshake",
    "certificate_chain_hostname_expiry",
    "private_key_and_secret_permissions",
    "firewall_loopback_only_ingress",
    "outbound_network_deny",
    "proxy_client_identity_boundary",
    "no_broker_or_telegram_credentials",
    "gvisor_runtime_and_cgroup_isolation",
    "hostile_source_escape_negative_tests",
    "log_redaction_and_evidence_integrity",
})
_STATUS = frozenset({"NOT_RUN", "DECLARED_PASS", "DECLARED_FAIL"})
_REPORT_FIELDS = frozenset({
    "version", "kind", "host_alias", "sequence", "issued_at", "expires_at",
    "stage32_preparation_sha256", "checks", "scope",
    "public_deployment_authorized", "plugin_install_authorized",
    "strategy_source_executed", "telegram_signal_authorized",
    "broker_order_authorized",
})


class Stage33Refused(ValueError):
    """Sanitized offline-security boundary refusal."""


def _guard33(ack: bool) -> None:
    try:
        _guard(ack)
    except Stage32Refused as exc:
        raise Stage33Refused("EXPLICIT_NONPRODUCTION_OPERATOR_EVIDENCE_REVIEW") from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Stage33Refused("DUPLICATE_SIGNED_EVIDENCE_FIELD")
        result[key] = value
    return result


def _signed_object(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= 12000:
        raise Stage33Refused("BOUNDED_CANONICAL_REVIEW_REQUIRED")
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             Stage33Refused("NONFINITE_REPORT_FIELD")))
    except Stage33Refused:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Stage33Refused("INVALID_SIGNED_REVIEW_ENCODING") from exc
    if (type(obj) is not dict or set(obj) != {
            "report", "auditor_signature_b64"} or canonical(obj) != raw):
        raise Stage33Refused("EXACT_SIGNED_REVIEW_ENVELOPE_REQUIRED")
    return obj


def _decode_sig(encoded) -> bytes:
    if type(encoded) is not str or len(encoded) != 88:
        raise Stage33Refused("AUDITOR_SIGNATURE_REQUIRED")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise Stage33Refused("INVALID_AUDITOR_SIGNATURE") from exc
    if (len(raw) != 64 or
            base64.b64encode(raw).decode("ascii") != encoded):
        raise Stage33Refused("CANONICAL_AUDITOR_SIGNATURE_REQUIRED")
    return raw


def _check_report(report: dict, *, now: int, preparation_sha: str) -> tuple[int, int]:
    if (type(report) is not dict or set(report) != _REPORT_FIELDS
            or type(now) is not int or now < 1
            or type(report["version"]) is not int or report["version"] != 1
            or report["kind"] != "disconnected_host_assessment_claims"
            or report["scope"] != "signed_claims_only_no_remote_attestation"
            or type(report["host_alias"]) is not str
            or not _HOST.fullmatch(report["host_alias"])
            or type(report["sequence"]) is not int
            or not 1 <= report["sequence"] < 2**63
            or type(report["issued_at"]) is not int
            or type(report["expires_at"]) is not int
            or not 1 <= report["issued_at"] <= now < report["expires_at"]
            or report["expires_at"] - report["issued_at"] > 3600
            or type(report["stage32_preparation_sha256"]) is not str
            or not _SHA.fullmatch(report["stage32_preparation_sha256"])
            or not hmac.compare_digest(
                report["stage32_preparation_sha256"], preparation_sha)
            or any(report[k] is not False for k in (
                "public_deployment_authorized", "plugin_install_authorized",
                "strategy_source_executed", "telegram_signal_authorized",
                "broker_order_authorized"))):
        raise Stage33Refused("UNSUPPORTED_OR_FALSE_HOST_SECURITY_CLAIM")
    checks = report["checks"]
    if type(checks) is not dict or set(checks) != _CHECKS:
        raise Stage33Refused("ALL_REQUIRED_HOST_CHECKS_MUST_BE_DECLARED")
    declared_pass = declared_fail = 0
    for name in _CHECKS:
        entry = checks[name]
        if (type(entry) is not dict
                or set(entry) != {"status", "evidence_sha256"}
                or type(entry["status"]) is not str
                or entry["status"] not in _STATUS):
            raise Stage33Refused("INVALID_CHECK_STATUS")
        digest = entry["evidence_sha256"]
        if entry["status"] == "NOT_RUN":
            if digest is not None:
                raise Stage33Refused("NO_EVIDENCE_FOR_UNRUN_CHECK")
        elif type(digest) is not str or not _SHA.fullmatch(digest):
            raise Stage33Refused("DECLARED_CHECK_NEEDS_EVIDENCE_DIGEST")
        if entry["status"] == "DECLARED_PASS":
            declared_pass += 1
        if entry["status"] == "DECLARED_FAIL":
            declared_fail += 1
    return declared_pass, declared_fail


@dataclass(frozen=True, slots=True)
class DisconnectedHostReviewReceipt:
    host_alias: str
    sequence: int
    signed_report_sha256: str
    stage32_preparation_sha256: str
    declared_pass_checks: int
    declared_failed_checks: int
    remaining_unrun_checks: int
    state: str = "SIGNED_CLAIMS_NOT_INDEPENDENTLY_VERIFIED"
    actual_host_independently_verified: bool = False
    actual_tls_endpoint_verified: bool = False
    network_policy_enforced: bool = False
    gvisor_isolation_certified: bool = False
    public_ingress_authorized: bool = False
    public_installer_authorized: bool = False
    telegram_send_authorized: bool = False
    broker_order_authorized: bool = False


def host_assessment_checklist() -> tuple[str, ...]:
    """Immutable checklist to hand to a separately authorized host reviewer."""
    return tuple(sorted(_CHECKS))


class DisconnectedHostEvidenceLedger:
    """Signed offline snapshot review in Stage32's SAME owner-private SQLite.

    Stage32 preparation signature must already be recorded. Stage33 verifier
    checks Stage32's stored reviewer signature again using its pinned key.
    An independent auditor Ed25519 signing key is also pinned out of band.
    The resulting report still cannot establish that claimed measurements
    were captured from a genuinely authorized host.
    """

    def __init__(
        self, preparation: HostPreparationDossier, *,
        auditor_public_key: bytes, pinned_auditor_sha256: str,
        operator_ack: bool = False,
    ) -> None:
        _guard33(operator_ack)
        if type(preparation) is not HostPreparationDossier:
            raise Stage33Refused("EXACT_STAGE32_PREPARATION_LEDGER_REQUIRED")
        if (type(auditor_public_key) is not bytes
                or len(auditor_public_key) != 32
                or type(pinned_auditor_sha256) is not str
                or not _SHA.fullmatch(pinned_auditor_sha256)
                or not hmac.compare_digest(
                    hashlib.sha256(auditor_public_key).hexdigest(),
                    pinned_auditor_sha256)
                or hmac.compare_digest(
                    auditor_public_key, preparation.reviewer_public_key)):
            raise Stage33Refused("SEPARATE_OUT_OF_BAND_AUDITOR_KEY_REQUIRED")
        self.preparation = preparation
        self.db = preparation.db
        self.auditor_public_key = auditor_public_key
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS stage33_auditor_pin(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                public_key BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stage33_signed_host_claims(
                host_alias TEXT NOT NULL, sequence INTEGER NOT NULL,
                signed_sha256 TEXT NOT NULL UNIQUE,
                stage32_preparation_sha256 TEXT NOT NULL,
                declared_pass INTEGER NOT NULL,
                declared_fail INTEGER NOT NULL,
                unrun INTEGER NOT NULL,
                signed_envelope BLOB NOT NULL,
                PRIMARY KEY(host_alias,sequence)
            );
            CREATE TRIGGER IF NOT EXISTS stage33_no_edit
            BEFORE UPDATE ON stage33_signed_host_claims
            BEGIN SELECT RAISE(ABORT,'STAGE33_APPEND_ONLY'); END;
            CREATE TRIGGER IF NOT EXISTS stage33_no_delete
            BEFORE DELETE ON stage33_signed_host_claims
            BEGIN SELECT RAISE(ABORT,'STAGE33_APPEND_ONLY'); END;
        """)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT public_key FROM stage33_auditor_pin WHERE singleton=1"
            ).fetchone()
            if existing is None:
                self.db.execute(
                    "INSERT INTO stage33_auditor_pin VALUES(1,?)",
                    (auditor_public_key,))
            elif not hmac.compare_digest(existing["public_key"],
                                          auditor_public_key):
                raise Stage33Refused("AUDITOR_PIN_CHANGED")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _preparation_row(self, host_alias: str, prep_sha: str, now: int):
        # The Stage32 prep must be CURRENT and its stored signature still
        # valid under the pinned key, not just a caller-built dataclass.
        row = self.db.execute(
            "SELECT * FROM stage32_signed_preparation "
            "WHERE host_alias=? AND statement_sha256=?",
            (host_alias, prep_sha)).fetchone()
        if (row is None or not row["observed_at"] <= now < row["expires_at"]
                or not hmac.compare_digest(
                    hashlib.sha256(row["signed_envelope"]).hexdigest(),
                    prep_sha)):
            raise Stage33Refused("STAGE32_PREPARATION_NOT_CURRENT")
        from .disposable_host_preflight_stage32_v1 import _DOMAIN as D32
        signed = json.loads(row["signed_envelope"].decode("ascii"),
                            object_pairs_hook=_unique)
        if (type(signed) is not dict
                or set(signed) != {"claim", "reviewer_signature_b64"}
                or canonical(signed) != row["signed_envelope"]
                or signed["claim"]["host_alias"] != host_alias
                or signed["claim"]["certificate_sha256"] != row["certificate_sha256"]
                or signed["claim"]["proposed_policy_sha256"] != row["policy_sha256"]):
            raise Stage33Refused("STAGE32_STORED_STATEMENT_DRIFT")
        _ed25519(self.preparation.reviewer_public_key,
                 _decode_sig(signed["reviewer_signature_b64"]),
                 D32 + canonical(signed["claim"]))
        return row

    def record(
        self, envelope: bytes, *, now: int,
        operator_ack: bool = False,
    ) -> DisconnectedHostReviewReceipt:
        _guard33(operator_ack)
        parsed = _signed_object(envelope)
        report = parsed["report"]
        if (type(report) is not dict
                or type(report.get("stage32_preparation_sha256")) is not str
                or type(report.get("host_alias")) is not str
                or not _HOST.fullmatch(report["host_alias"])
                or not _SHA.fullmatch(report["stage32_preparation_sha256"])):
            raise Stage33Refused("PINNED_STAGE32_REPORT_REFERENCE_REQUIRED")
        # This signature attests to the *claim bytes*, not their truth.
        try:
            _ed25519(self.auditor_public_key,
                     _decode_sig(parsed["auditor_signature_b64"]),
                     _DOMAIN + canonical(report))
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise Stage33Refused("INVALID_INDEPENDENT_AUDITOR_SIGNATURE") from exc
        passed, failed = _check_report(
            report, now=now,
            preparation_sha=report["stage32_preparation_sha256"])
        sha = hashlib.sha256(envelope).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self._preparation_row(
                report["host_alias"], report["stage32_preparation_sha256"], now)
            if report["expires_at"] > row["expires_at"]:
                raise Stage33Refused("REPORT_OUTLIVES_STAGE32_PREPARATION")
            latest = self.db.execute(
                "SELECT MAX(sequence) FROM stage33_signed_host_claims "
                "WHERE host_alias=?", (report["host_alias"],)).fetchone()[0]
            if report["sequence"] != (1 if latest is None else latest+1):
                raise Stage33Refused("REPLAY_GAP_OR_ROLLBACK_SEQUENCE")
            self.db.execute(
                "INSERT INTO stage33_signed_host_claims VALUES(?,?,?,?,?,?,?,?)",
                (report["host_alias"], report["sequence"], sha,
                 report["stage32_preparation_sha256"], passed, failed,
                 len(_CHECKS)-passed-failed, envelope))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return DisconnectedHostReviewReceipt(
            report["host_alias"], report["sequence"], sha,
            report["stage32_preparation_sha256"],
            passed, failed, len(_CHECKS)-passed-failed)

    def status(self, host_alias: str) -> dict:
        if type(host_alias) is not str or not _HOST.fullmatch(host_alias):
            raise Stage33Refused("VALID_HOST_ALIAS_REQUIRED")
        row = self.db.execute(
            "SELECT COUNT(*) AS n,MAX(sequence) AS last "
            "FROM stage33_signed_host_claims WHERE host_alias=?",
            (host_alias,)).fetchone()
        return {
            "host_alias": host_alias,
            "recorded_claims": row["n"],
            "last_sequence": row["last"],
            "host_designated_and_independently_attested": False,
            "live_tls_verified": False,
            "firewall_tested": False,
            "gvisor_validated": False,
            "public_api_deployment_authorized": False,
            "untrusted_source_execution_authorized": False,
            "telegram_send_authorized": False,
            "broker_order_authorized": False,
        }


__all__ = [
    "Stage33Refused", "DisconnectedHostEvidenceLedger",
    "DisconnectedHostReviewReceipt", "host_assessment_checklist", "_DOMAIN",
]
