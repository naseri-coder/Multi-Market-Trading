"""Stage32: nonproduction, offline disposable-host readiness evidence.

Trust contract: a locally verified TEST-ONLY TLS certificate/key fixture plus
an operator-proposed static host policy may be reviewed and signed out of
band. The signature proves ownership of the REVIEWER KEY, not observation
of a real host. This module has no sockets, DNS, shell, Docker, TLS listener,
production writes, user-source imports or deployment permission.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import ssl
import stat
from dataclasses import dataclass
from pathlib import Path

from .a24_publisher_admission import _ed25519, canonical

_DOMAIN = b"MMT-STAGE32-DISPOSABLE-HOST-PREPARATION-V1\x00"
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DNS = re.compile(r"[a-z][a-z0-9-]{0,48}(?:\.[a-z0-9-]{1,48})+\Z")
_PROPOSAL_FIELDS = frozenset({
    "schema", "environment", "authority", "ingress_bind",
    "ingress_port", "tls_minimum", "accept_forwarded_headers",
    "public_ingress_enabled", "outbound_internet_enabled",
    "broker_credentials_present", "docker_socket_mounted",
    "untrusted_plugin_execution_enabled", "max_http_body_bytes",
})
_REVIEW_FIELDS = frozenset({
    "version", "kind", "host_alias", "sequence",
    "observed_at", "expires_at", "certificate_sha256",
    "proposed_policy_sha256", "review_scope",
    "actual_host_independently_verified",
    "internet_service_deployed", "untrusted_code_executed",
    "public_installer_authorized", "telegram_send_authorized",
    "broker_orders_authorized",
})


class Stage32Refused(ValueError):
    """Sanitized refusal; never expose certificate, key or host file paths."""


def _guard(operator_ack: bool) -> None:
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise Stage32Refused("EXPLICIT_NONPRODUCTION_HOST_PREP_REVIEW_REQUIRED")


def _private_dir(parent: Path) -> None:
    if (not isinstance(parent, Path) or not parent.is_absolute()
            or parent.is_symlink() or not parent.is_dir()):
        raise Stage32Refused("OWNER_PRIVATE_TEST_DIRECTORY_REQUIRED")
    s = parent.lstat()
    if (s.st_uid != os.geteuid()
            or stat.S_IMODE(s.st_mode) & 0o077):
        raise Stage32Refused("OWNER_PRIVATE_TEST_DIRECTORY_REQUIRED")


def _private_file(path: Path, *, max_bytes: int) -> bytes:
    _private_dir(path.parent)
    if path.is_symlink():
        raise Stage32Refused("NO_SYMLINKED_TEST_SECRETS")
    s = path.lstat()
    if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1
            or s.st_uid != os.geteuid()
            or stat.S_IMODE(s.st_mode) != 0o600
            or not 0 < s.st_size <= max_bytes):
        raise Stage32Refused("EXACT_OWNER_ONLY_TEST_FILE_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev != s.st_dev or opened.st_ino != s.st_ino
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600):
            raise Stage32Refused("TEST_FILE_CHANGED_DURING_OPEN")
        data = stream.read(max_bytes + 1)
    if not 0 < len(data) <= max_bytes:
        raise Stage32Refused("BOUNDED_TEST_FILE_REQUIRED")
    return data


@dataclass(frozen=True, slots=True)
class OfflineTlsFixture:
    hostname: str
    certificate_sha256: str
    certificate_expires_at: int
    state: str = "LOCAL_TEST_CERT_KEY_MATCH_NOT_HOST_PROOF"
    local_key_permissions_checked: bool = True
    local_certificate_key_correspondence_checked: bool = True
    real_tls_server_checked: bool = False
    live_certificate_chain_verified: bool = False
    network_access_policy_enforced: bool = False
    public_deployment_authorized: bool = False


def verify_local_test_certificate_pair(
    *, certificate_path: Path, private_key_path: Path,
    expected_hostname: str, expected_certificate_sha256: str,
    now: int, operator_ack: bool = False,
) -> OfflineTlsFixture:
    """Check *only* an owner-private, disposable TEST cert/key pair.

    Reads cert PEM and checks the key via SSLContext.load_cert_chain.
    No private key bytes are returned, hashed, logged or persisted.
    A successful SSLContext load is NOT a handshake or real TLS inspection.
    """
    _guard(operator_ack)
    if (not isinstance(certificate_path, Path)
            or not isinstance(private_key_path, Path)
            or not certificate_path.is_absolute()
            or not private_key_path.is_absolute()
            or certificate_path == private_key_path
            or type(expected_hostname) is not str
            or not _DNS.fullmatch(expected_hostname)
            or not expected_hostname.endswith((".invalid", ".test"))
            or type(expected_certificate_sha256) is not str
            or not _SHA.fullmatch(expected_certificate_sha256)
            or type(now) is not int or now < 1):
        raise Stage32Refused("PINNED_DISPOSABLE_TEST_FIXTURE_REQUIRED")
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    try:
        cert_data = _private_file(certificate_path, max_bytes=16384)
        _private_file(private_key_path, max_bytes=16384)  # permissions/size
        certificate = x509.load_pem_x509_certificate(cert_data)
        der = certificate.public_bytes(serialization.Encoding.DER)
        digest = hashlib.sha256(der).hexdigest()
        if not hmac.compare_digest(digest, expected_certificate_sha256):
            raise Stage32Refused("TEST_CERTIFICATE_PIN_MISMATCH")
        san = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value
        names = san.get_values_for_type(x509.DNSName)
        if names != [expected_hostname]:
            raise Stage32Refused("TEST_CERTIFICATE_SAN_MISMATCH")
        valid_from = int(certificate.not_valid_before_utc.timestamp())
        valid_to = int(certificate.not_valid_after_utc.timestamp())
        if (not valid_from <= now < valid_to
                or valid_to - now < 3600
                or valid_to - now > 30 * 86400
                or valid_to - valid_from > 31 * 86400):
            raise Stage32Refused("TEST_CERTIFICATE_EXPIRY_UNSAFE")
        try:
            ca = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints).value.ca
        except x509.ExtensionNotFound:
            ca = False
        public_key = certificate.public_key()
        if (ca or not (
            isinstance(public_key, rsa.RSAPublicKey)
            and public_key.key_size >= 2048
            or isinstance(public_key, ec.EllipticCurvePublicKey)
            and public_key.key_size >= 256)):
            raise Stage32Refused("UNACCEPTABLE_TEST_CERTIFICATE_KEY")
        sig_alg = certificate.signature_hash_algorithm
        if sig_alg is None or sig_alg.name.lower() not in (
                "sha256", "sha384", "sha512"):
            raise Stage32Refused("WEAK_TEST_CERTIFICATE_SIGNATURE")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(
            str(certificate_path), str(private_key_path))
    except Stage32Refused:
        raise
    except (OSError, ssl.SSLError, ValueError, TypeError, KeyError,
            x509.ExtensionNotFound) as exc:
        raise Stage32Refused("INVALID_PRIVATE_TEST_TLS_MATERIAL") from exc
    return OfflineTlsFixture(expected_hostname, digest, valid_to)


@dataclass(frozen=True, slots=True)
class ProposedHostPolicy:
    policy_sha256: str
    authority: str
    state: str = "PROPOSED_DISPOSABLE_POLICY_NOT_APPLIED"
    host_firewall_independently_checked: bool = False
    real_reverse_proxy_config_verified: bool = False
    public_ingress_authorized: bool = False
    source_execution_authorized: bool = False


def review_proposed_host_policy(
    proposal: dict, *, expected_hostname: str,
    operator_ack: bool = False,
) -> ProposedHostPolicy:
    """Reject permissive proposals, but do NOT assert these are host facts."""
    _guard(operator_ack)
    if (type(proposal) is not dict
            or set(proposal) != _PROPOSAL_FIELDS
            or type(expected_hostname) is not str
            or not _DNS.fullmatch(expected_hostname)
            or type(proposal["schema"]) is not int
            or proposal["schema"] != 1
            or proposal["environment"] != "isolated_disposable_nonproduction"
            or proposal["authority"] != expected_hostname
            or proposal["ingress_bind"] != "127.0.0.1"
            or type(proposal["ingress_port"]) is not int
            or proposal["ingress_port"] != 443
            or proposal["tls_minimum"] != "TLSv1.3"
            or proposal["max_http_body_bytes"] != 132000
            or type(proposal["max_http_body_bytes"]) is not int
            or any(proposal[k] is not False for k in (
                "accept_forwarded_headers", "public_ingress_enabled",
                "outbound_internet_enabled", "broker_credentials_present",
                "docker_socket_mounted", "untrusted_plugin_execution_enabled"))):
        raise Stage32Refused("PROPOSED_DISPOSABLE_HOST_POLICY_NOT_RESTRICTIVE")
    return ProposedHostPolicy(hashlib.sha256(canonical(proposal)).hexdigest(),
                              expected_hostname)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Stage32Refused("DUPLICATE_SIGNED_REVIEW_KEY")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class HostPreparationReceipt:
    host_alias: str
    sequence: int
    statement_sha256: str
    certificate_sha256: str
    policy_sha256: str
    state: str = "SIGNED_LOCAL_HOST_PREPARATION_NOT_LIVE_ATTESTED"
    actual_host_security_verified: bool = False
    actual_public_https_service_checked: bool = False
    public_port_opening_authorized: bool = False
    production_deployment_authorized: bool = False
    public_install_authorized: bool = False
    untrusted_core_execution_authorized: bool = False
    broker_orders_authorized: bool = False


class HostPreparationDossier:
    """Append-only SQLite custody for a separately pinned reviewer statement.

    The reviewer's signature attests to an *offline preparation claim*,
    not an independently observed remote host. No signer key generation.
    """

    def __init__(
        self, db_path: Path, *, reviewer_public_key: bytes,
        pinned_reviewer_public_key_sha256: str,
        operator_ack: bool = False,
    ) -> None:
        _guard(operator_ack)
        if (not isinstance(db_path, Path) or not db_path.is_absolute()
                or db_path.is_symlink()):
            raise Stage32Refused("PRIVATE_DOSSIER_PATH_REQUIRED")
        _private_dir(db_path.parent)
        if (type(reviewer_public_key) is not bytes
                or len(reviewer_public_key) != 32
                or type(pinned_reviewer_public_key_sha256) is not str
                or not _SHA.fullmatch(pinned_reviewer_public_key_sha256)
                or not hmac.compare_digest(
                    hashlib.sha256(reviewer_public_key).hexdigest(),
                    pinned_reviewer_public_key_sha256)):
            raise Stage32Refused("OUT_OF_BAND_REVIEWER_KEY_PIN_REQUIRED")
        if db_path.exists():
            _private_file(db_path, max_bytes=8_000_000)
        else:
            fd = os.open(
                db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600)
            os.close(fd)
        self.db = sqlite3.connect(db_path, isolation_level=None, timeout=0.5)
        self.db.row_factory = sqlite3.Row
        self.reviewer_public_key = reviewer_public_key
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS stage32_reviewer_pin(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1),
              reviewer_public_key BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stage32_signed_preparation(
              host_alias TEXT NOT NULL,
              sequence INTEGER NOT NULL,
              statement_sha256 TEXT NOT NULL UNIQUE,
              certificate_sha256 TEXT NOT NULL,
              policy_sha256 TEXT NOT NULL,
              observed_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              signed_envelope BLOB NOT NULL,
              PRIMARY KEY(host_alias,sequence)
            );
            CREATE TRIGGER IF NOT EXISTS stage32_no_record_update
            BEFORE UPDATE ON stage32_signed_preparation
            BEGIN SELECT RAISE(ABORT,'STAGE32_APPEND_ONLY'); END;
            CREATE TRIGGER IF NOT EXISTS stage32_no_record_delete
            BEFORE DELETE ON stage32_signed_preparation
            BEGIN SELECT RAISE(ABORT,'STAGE32_APPEND_ONLY'); END;
        """)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT reviewer_public_key FROM stage32_reviewer_pin"
                " WHERE singleton=1").fetchone()
            if row is None:
                self.db.execute(
                    "INSERT INTO stage32_reviewer_pin VALUES(1,?)",
                    (reviewer_public_key,))
            elif not hmac.compare_digest(
                    row["reviewer_public_key"], reviewer_public_key):
                raise Stage32Refused("REVIEWER_CUSTODY_ANCHOR_CHANGED")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        self.db.close()

    def record(
        self, signed_envelope: bytes, *, fixture: OfflineTlsFixture,
        proposed_policy: ProposedHostPolicy, now: int,
        operator_ack: bool = False,
    ) -> HostPreparationReceipt:
        _guard(operator_ack)
        if (type(signed_envelope) is not bytes
                or not 1 <= len(signed_envelope) <= 4096
                or type(fixture) is not OfflineTlsFixture
                or type(proposed_policy) is not ProposedHostPolicy
                or fixture.hostname != proposed_policy.authority
                or type(now) is not int or now < 1):
            raise Stage32Refused("COMPLETE_PINNED_LOCAL_PREPARATION_REQUIRED")
        try:
            obj = json.loads(
                signed_envelope.decode("ascii"), object_pairs_hook=_unique)
            if (type(obj) is not dict
                    or set(obj) != {"claim", "reviewer_signature_b64"}
                    or canonical(obj) != signed_envelope):
                raise Stage32Refused("CANONICAL_REVIEW_ENVELOPE_REQUIRED")
            claim = obj["claim"]
            if type(claim) is not dict or set(claim) != _REVIEW_FIELDS:
                raise Stage32Refused("EXACT_OFFLINE_REVIEW_CLAIM_REQUIRED")
            if (type(claim["version"]) is not int
                    or claim["version"] != 1
                    or claim["kind"] != "disposable_host_preparation_only"
                    or claim["review_scope"] != "static_local_fixture_and_proposal"
                    or type(claim["host_alias"]) is not str
                    or not _HOST.fullmatch(claim["host_alias"])
                    or type(claim["sequence"]) is not int
                    or not 1 <= claim["sequence"] < 2**63
                    or type(claim["observed_at"]) is not int
                    or type(claim["expires_at"]) is not int
                    or not 1 <= claim["observed_at"] <= now < claim["expires_at"]
                    or claim["expires_at"] - claim["observed_at"] > 3600
                    or claim["expires_at"] > fixture.certificate_expires_at
                    or claim["certificate_sha256"] != fixture.certificate_sha256
                    or claim["proposed_policy_sha256"] != proposed_policy.policy_sha256
                    or any(claim[k] is not False for k in (
                        "actual_host_independently_verified",
                        "internet_service_deployed", "untrusted_code_executed",
                        "public_installer_authorized", "telegram_send_authorized",
                        "broker_orders_authorized"))):
                raise Stage32Refused("FALSE_RUNTIME_ATTESTATION_OR_STALE_REVIEW")
            encoded = obj["reviewer_signature_b64"]
            if type(encoded) is not str or len(encoded) != 88:
                raise Stage32Refused("REVIEWER_SIGNATURE_REQUIRED")
            signature = base64.b64decode(encoded, validate=True)
            if (len(signature) != 64
                    or base64.b64encode(signature).decode("ascii") != encoded):
                raise Stage32Refused("EXACT_REVIEWER_SIGNATURE_REQUIRED")
            _ed25519(self.reviewer_public_key, signature,
                     _DOMAIN + canonical(claim))
        except Stage32Refused:
            raise
        except (ValueError, TypeError, UnicodeError, KeyError,
                AttributeError) as exc:
            raise Stage32Refused("UNTRUSTED_OFFLINE_REVIEW_SIGNATURE") from exc
        sha = hashlib.sha256(signed_envelope).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            last = self.db.execute(
                "SELECT MAX(sequence) FROM stage32_signed_preparation"
                " WHERE host_alias=?", (claim["host_alias"],)).fetchone()[0]
            if claim["sequence"] != (1 if last is None else last+1):
                raise Stage32Refused("DUPLICATE_GAP_OR_ROLLBACK_SEQUENCE")
            self.db.execute(
                "INSERT INTO stage32_signed_preparation VALUES(?,?,?,?,?,?,?,?)",
                (claim["host_alias"], claim["sequence"], sha,
                 fixture.certificate_sha256, proposed_policy.policy_sha256,
                 claim["observed_at"], claim["expires_at"], signed_envelope))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return HostPreparationReceipt(
            claim["host_alias"], claim["sequence"], sha,
            fixture.certificate_sha256, proposed_policy.policy_sha256)

    def summary(self, host_alias: str) -> dict:
        if type(host_alias) is not str or not _HOST.fullmatch(host_alias):
            raise Stage32Refused("HOST_ALIAS_REQUIRED")
        row = self.db.execute(
            "SELECT COUNT(*) AS total,MAX(sequence) AS latest "
            "FROM stage32_signed_preparation WHERE host_alias=?",
            (host_alias,)).fetchone()
        return {
            "host_alias": host_alias, "local_statements": row["total"],
            "latest_sequence": row["latest"],
            "actual_host_audited": False,
            "internet_deployment_authorized": False,
            "broker_order_authorized": False,
        }


__all__ = [
    "Stage32Refused", "OfflineTlsFixture", "ProposedHostPolicy",
    "HostPreparationReceipt", "HostPreparationDossier",
    "verify_local_test_certificate_pair", "review_proposed_host_policy",
    "_DOMAIN",
]
