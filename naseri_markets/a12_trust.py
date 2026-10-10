"""A12 offline owner trust, monotonic certificate pins and signed PAPER grants.

Public Multi Market Trading: no issuer secrets, real CA, network, plugins or
Production license endpoints. Ed25519 verification requires an optional,
independently installed cryptography package; missing dependency fails CLOSED.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .delivery_ledger import open_sqlite

DOMAIN = b"MULTI-MARKET-TRADING-A12-ED25519-PAPER-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_DNS = re.compile(r"[a-z0-9-]{1,60}\.fixture\Z")
_SERIAL = re.compile(r"[0-9a-f]{32}\Z")
POLICY_FIELDS = frozenset({
    "schema_version", "generation", "engine_id", "engine_version",
    "manifest_sha256", "owner_dns", "ca_sha256", "owner_cert_sha256",
    "issuer_key_id", "issuer_public_key_b64",
})
GRANT_FIELDS = frozenset({
    "schema_version", "serial", "generation", "engine_id", "engine_version",
    "manifest_sha256", "owner_dns", "installation_id", "issuer_key_id",
    "issued_at", "expires_at", "permissions",
})


class AdmissionRefused(ValueError):
    """Fail-closed A12 identity, certificate, signature or license error."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise AdmissionRefused("A12_DUPLICATE_KEY")
        obj[key] = value
    return obj


def _json(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= 8192:
        raise AdmissionRefused("A12_INVALID_INPUT_SIZE")
    try:
        obj = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                AdmissionRefused("A12_NONFINITE")
            ),
        )
    except (UnicodeError, ValueError) as exc:
        raise AdmissionRefused("A12_INVALID_JSON") from exc
    if not isinstance(obj, dict):
        raise AdmissionRefused("A12_OBJECT_REQUIRED")
    return obj


def _b64(value: object, *, size: int) -> bytes:
    if type(value) is not str or not 0 < len(value) <= 256:
        raise AdmissionRefused("A12_BASE64_REQUIRED")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AdmissionRefused("A12_BAD_BASE64") from exc
    if len(raw) != size or base64.b64encode(raw).decode() != value:
        raise AdmissionRefused("A12_BASE64_NONCANONICAL")
    return raw


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("ascii")


def parse_policy(raw: bytes, *, approved_sha256: str) -> dict:
    """Independent operator hash approval; NOT a publisher signature."""
    if type(approved_sha256) is not str or not _SHA.fullmatch(approved_sha256):
        raise AdmissionRefused("A12_INDEPENDENT_APPROVAL_REQUIRED")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), approved_sha256):
        raise AdmissionRefused("A12_PIN_MISMATCH")
    p = _json(raw)
    if set(p) != POLICY_FIELDS or type(p["schema_version"]) is not int or p["schema_version"] != 1:
        raise AdmissionRefused("A12_POLICY_SCHEMA")
    if type(p["generation"]) is not int or p["generation"] < 1:
        raise AdmissionRefused("A12_GENERATION")
    if type(p["engine_id"]) is not str or not _ID.fullmatch(p["engine_id"]):
        raise AdmissionRefused("A12_ENGINE")
    if type(p["engine_version"]) is not str or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", p["engine_version"]
    ):
        raise AdmissionRefused("A12_VERSION")
    if type(p["owner_dns"]) is not str or not _DNS.fullmatch(p["owner_dns"]):
        raise AdmissionRefused("A12_FIXTURE_ONLY")
    if type(p["issuer_key_id"]) is not str or not _ID.fullmatch(p["issuer_key_id"]):
        raise AdmissionRefused("A12_ISSUER")
    for key in ("manifest_sha256", "ca_sha256", "owner_cert_sha256"):
        if type(p[key]) is not str or not _SHA.fullmatch(p[key]):
            raise AdmissionRefused("A12_SHA256")
    _b64(p["issuer_public_key_b64"], size=32)
    return p


def parse_grant(raw: bytes) -> tuple[dict, bytes]:
    obj = _json(raw)
    if set(obj) != {"grant", "signature_b64"}:
        raise AdmissionRefused("A12_GRANT_ENVELOPE")
    grant = obj["grant"]
    if not isinstance(grant, dict) or set(grant) != GRANT_FIELDS:
        raise AdmissionRefused("A12_GRANT_FIELDS")
    if type(grant["schema_version"]) is not int or grant["schema_version"] != 1:
        raise AdmissionRefused("A12_GRANT_VERSION")
    if type(grant["serial"]) is not str or not _SERIAL.fullmatch(grant["serial"]):
        raise AdmissionRefused("A12_SERIAL")
    if type(grant["generation"]) is not int or grant["generation"] < 1:
        raise AdmissionRefused("A12_GRANT_GENERATION")
    for name in ("installation_id", "issuer_key_id"):
        if type(grant[name]) is not str or not _ID.fullmatch(grant[name]):
            raise AdmissionRefused("A12_GRANT_ID")
    for name in ("engine_id", "engine_version", "manifest_sha256", "owner_dns"):
        if type(grant[name]) is not str or not 1 <= len(grant[name]) <= 100:
            raise AdmissionRefused("A12_GRANT_SCOPE")
    if type(grant["permissions"]) is not list or grant["permissions"] != ["paper_analysis"]:
        raise AdmissionRefused("A12_PAPER_ONLY")
    if type(grant["issued_at"]) is not int or type(grant["expires_at"]) is not int:
        raise AdmissionRefused("A12_CLOCK_REQUIRED")
    if not 0 < grant["expires_at"] - grant["issued_at"] <= 86400:
        raise AdmissionRefused("A12_GRANT_TTL")
    return grant, _b64(obj["signature_b64"], size=64)


@dataclass(frozen=True, slots=True)
class AdmissionSnapshot:
    engine_id: str
    engine_version: str
    manifest_sha256: str
    generation: int
    serial: str
    license_expires_at: int
    owner_dns: str
    owner_cert_sha256: str
    ca_sha256: str


class TrustStore:
    """Atomic, local-only trust rotation and revocation.

    SQLite cannot protect against restoring an older DB snapshot. Production
    needs an external/TPM backed nonrollback counter and revocation service.
    """

    def __init__(self, path: str | Path):
        path = Path(path)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise AdmissionRefused("A12_UNSAFE_STORE")
        self._db = open_sqlite(path)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a12_policy (
                engine_id TEXT, generation INTEGER, raw TEXT, pin TEXT,
                state TEXT, PRIMARY KEY(engine_id,generation)
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a12_floor (
                engine_id TEXT PRIMARY KEY, generation INTEGER NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a12_revoked_serial (serial TEXT PRIMARY KEY)
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a12_revoked_issuer (key_id TEXT PRIMARY KEY)
        """)

    def close(self):
        self._db.close()

    def stage(self, raw: bytes, *, approved_sha256: str) -> None:
        policy = parse_policy(raw, approved_sha256=approved_sha256)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            floor = self._db.execute(
                "SELECT generation FROM a12_floor WHERE engine_id=?",
                (policy["engine_id"],),
            ).fetchone()
            if floor and policy["generation"] <= floor["generation"]:
                raise AdmissionRefused("A12_ROLLBACK")
            if self._db.execute(
                "SELECT 1 FROM a12_policy WHERE engine_id=? AND state='STAGED'",
                (policy["engine_id"],),
            ).fetchone():
                raise AdmissionRefused("A12_ALREADY_STAGED")
            self._db.execute(
                "INSERT INTO a12_policy VALUES (?,?,?,?,'STAGED')",
                (policy["engine_id"], policy["generation"],
                 raw.decode(), approved_sha256),
            )
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def promote(self, engine_id: str, *, generation: int, expected_active: int):
        if (type(generation) is not int or generation <= 0
                or type(expected_active) is not int or expected_active < 0):
            raise AdmissionRefused("A12_EXPECTED_GENERATION_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT generation FROM a12_policy "
                "WHERE engine_id=? AND state='ACTIVE'", (engine_id,),
            ).fetchone()
            if (row["generation"] if row else 0) != expected_active:
                raise AdmissionRefused("A12_STALE_CAS")
            if generation <= expected_active or not self._db.execute(
                "SELECT 1 FROM a12_policy WHERE engine_id=? "
                "AND generation=? AND state='STAGED'", (engine_id, generation),
            ).fetchone():
                raise AdmissionRefused("A12_INVALID_ROTATION")
            self._db.execute(
                "UPDATE a12_policy SET state='RETIRED' "
                "WHERE engine_id=? AND state='ACTIVE'", (engine_id,),
            )
            self._db.execute(
                "UPDATE a12_policy SET state='ACTIVE' WHERE "
                "engine_id=? AND generation=?", (engine_id, generation),
            )
            self._db.execute(
                "INSERT INTO a12_floor(engine_id,generation) VALUES(?,?) "
                "ON CONFLICT(engine_id) DO UPDATE SET generation=excluded.generation",
                (engine_id, generation),
            )
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def active(self, engine_id: str) -> dict:
        row = self._db.execute(
            "SELECT raw,pin,generation FROM a12_policy WHERE "
            "engine_id=? AND state='ACTIVE'", (engine_id,),
        ).fetchone()
        floor = self._db.execute(
            "SELECT generation FROM a12_floor WHERE engine_id=?", (engine_id,),
        ).fetchone()
        if not row or not floor or row["generation"] != floor["generation"]:
            raise AdmissionRefused("A12_NO_ACTIVE_TRUST")
        return parse_policy(row["raw"].encode(), approved_sha256=row["pin"])

    def revoke_policy(self, engine_id: str, *, expected_generation: int):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT generation FROM a12_policy WHERE engine_id=? "
                "AND state='ACTIVE'", (engine_id,),
            ).fetchone()
            if not row or row["generation"] != expected_generation:
                raise AdmissionRefused("A12_REVOKE_CAS")
            self._db.execute(
                "UPDATE a12_policy SET state='REVOKED' WHERE "
                "engine_id=? AND generation=?", (engine_id, expected_generation),
            )
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def revoke_serial(self, serial: str):
        if type(serial) is not str or not _SERIAL.fullmatch(serial):
            raise AdmissionRefused("A12_BAD_SERIAL")
        self._db.execute(
            "INSERT OR IGNORE INTO a12_revoked_serial VALUES(?)", (serial,),
        )

    def revoke_issuer(self, key_id: str):
        if type(key_id) is not str or not _ID.fullmatch(key_id):
            raise AdmissionRefused("A12_BAD_ISSUER")
        self._db.execute(
            "INSERT OR IGNORE INTO a12_revoked_issuer VALUES(?)", (key_id,),
        )

    def check_revocations(self, serial: str, issuer: str):
        if self._db.execute(
            "SELECT 1 FROM a12_revoked_serial WHERE serial=?", (serial,),
        ).fetchone():
            raise AdmissionRefused("A12_SERIAL_REVOKED")
        if self._db.execute(
            "SELECT 1 FROM a12_revoked_issuer WHERE key_id=?", (issuer,),
        ).fetchone():
            raise AdmissionRefused("A12_ISSUER_REVOKED")


def verify_grant(raw: bytes, *, policy: dict, installation_id: str,
                 now: int, store: TrustStore) -> AdmissionSnapshot:
    grant, signature = parse_grant(raw)
    if type(now) is not int or now < 1:
        raise AdmissionRefused("A12_CURRENT_CLOCK_REQUIRED")
    for name in ("engine_id", "engine_version", "manifest_sha256",
                 "owner_dns", "issuer_key_id", "generation"):
        if type(grant[name]) is not type(policy[name]) or grant[name] != policy[name]:
            raise AdmissionRefused("A12_GRANT_SCOPE_MISMATCH")
    if grant["installation_id"] != installation_id:
        raise AdmissionRefused("A12_WRONG_INSTALLATION")
    if grant["issued_at"] > now + 5 or grant["expires_at"] <= now:
        raise AdmissionRefused("A12_EXPIRED_OR_FUTURE")
    store.check_revocations(grant["serial"], grant["issuer_key_id"])
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise AdmissionRefused("A12_CRYPTOGRAPHY_REQUIRED") from exc
    verifier = Ed25519PublicKey.from_public_bytes(
        _b64(policy["issuer_public_key_b64"], size=32)
    )
    try:
        verifier.verify(signature, DOMAIN + canonical(grant))
    except InvalidSignature as exc:
        raise AdmissionRefused("A12_SIGNATURE_INVALID") from exc
    return AdmissionSnapshot(
        grant["engine_id"], grant["engine_version"],
        grant["manifest_sha256"], grant["generation"], grant["serial"],
        grant["expires_at"], grant["owner_dns"],
        policy["owner_cert_sha256"], policy["ca_sha256"],
    )


class OfflineAdmission:
    """Pinned cert bytes + cryptographic PAPER grant; TLS chain still required."""

    def __init__(self, store: TrustStore, *, engine_id: str,
                 installation_id: str, signed_grant: bytes,
                 ca_pem: bytes, owner_cert_der: bytes):
        self._store = store
        self._engine_id = engine_id
        self._installation_id = installation_id
        self._grant = signed_grant
        self._ca = ca_pem
        self._leaf = owner_cert_der

    def snapshot(self, *, now: int) -> AdmissionSnapshot:
        p = self._store.active(self._engine_id)
        if not hmac.compare_digest(
            hashlib.sha256(self._ca).hexdigest(), p["ca_sha256"]
        ) or not hmac.compare_digest(
            hashlib.sha256(self._leaf).hexdigest(), p["owner_cert_sha256"]
        ):
            raise AdmissionRefused("A12_CERT_PIN_MISMATCH")
        # A11 mTLS independently validates the cert chain/hostname/expiry;
        # a fingerprint alone does not prove any X.509 validity or owner.
        return verify_grant(
            self._grant, policy=p, installation_id=self._installation_id,
            now=now, store=self._store,
        )
