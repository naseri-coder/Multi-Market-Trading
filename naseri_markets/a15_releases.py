"""A15 NON-PRODUCTION signed synthetic releases with independent local rollback witness.

A15 never signs on behalf of a private publisher or embeds private keys.
Authority store must be separately retained from A14 temporary release state.
This is local witness custody, NOT host-compromise-resistant monotonic storage.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .a14_packages import MockPackageDeploymentManager, PackageRefused, inspect_bundle
from .delivery_ledger import open_sqlite

DOMAIN = b"MULTI-MARKET-TRADING-A15-RELEASE-ED25519-V1\x00"
ROTATION_DOMAIN = b"MULTI-MARKET-TRADING-A15-ROTATION-V1\x00"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_FIELDS = frozenset({
    "schema_version", "kind", "mode", "engine_id", "engine_version",
    "installation_id", "manifest_sha256", "trust_generation",
    "release", "release_sequence", "artifact_sha256", "publisher_key_id",
    "publisher_generation", "issued_at", "expires_at",
})


class ReleaseRefused(PackageRefused):
    """Signed release, trusted publisher or independent floor was not valid."""


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise ReleaseRefused("A15_DUPLICATE_FIELD")
        obj[key] = value
    return obj


def _parse(raw: bytes, max_size: int = 8192) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= max_size:
        raise ReleaseRefused("A15_INVALID_SIZE")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             ReleaseRefused("A15_NONFINITE")))
    except (ValueError, UnicodeError) as exc:
        raise ReleaseRefused("A15_BAD_JSON") from exc
    if type(obj) is not dict:
        raise ReleaseRefused("A15_OBJECT_REQUIRED")
    return obj


def _b64(raw: object, size: int) -> bytes:
    if type(raw) is not str or not 0 < len(raw) <= 128:
        raise ReleaseRefused("A15_BAD_BASE64")
    try:
        value = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ReleaseRefused("A15_BAD_BASE64") from exc
    if len(value) != size or base64.b64encode(value).decode("ascii") != raw:
        raise ReleaseRefused("A15_NONCANONICAL_BASE64")
    return value


def parse_signed_release(raw: bytes) -> tuple[dict, bytes]:
    envelope = _parse(raw)
    if set(envelope) != {"release", "signature_b64"}:
        raise ReleaseRefused("A15_ENVELOPE_FIELDS")
    value = envelope["release"]
    if type(value) is not dict or set(value) != _FIELDS:
        raise ReleaseRefused("A15_RELEASE_FIELDS")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["kind"] != "synthetic_private_data"
            or value["mode"] != "offline_paper_only"
            or type(value["release_sequence"]) is not int
            or not 1 <= value["release_sequence"] <= 2**63 - 1
            or type(value["trust_generation"]) is not int
            or value["trust_generation"] < 1
            or type(value["publisher_generation"]) is not int
            or value["publisher_generation"] < 1
            or type(value["issued_at"]) is not int
            or type(value["expires_at"]) is not int
            or value["issued_at"] < 1
            or not value["issued_at"] < value["expires_at"]
            or value["expires_at"] - value["issued_at"] > 604800):
        raise ReleaseRefused("A15_RELEASE_POLICY")
    for name in ("engine_id", "installation_id", "publisher_key_id"):
        if type(value[name]) is not str or not _ID.fullmatch(value[name]):
            raise ReleaseRefused("A15_INVALID_IDENTITY")
    for name in ("engine_version", "release"):
        if type(value[name]) is not str or not _VERSION.fullmatch(value[name]):
            raise ReleaseRefused("A15_INVALID_VERSION")
    for name in ("manifest_sha256", "artifact_sha256"):
        if type(value[name]) is not str or not _HASH.fullmatch(value[name]):
            raise ReleaseRefused("A15_INVALID_SHA256")
    return value, _b64(envelope["signature_b64"], 64)


def _verify_ed25519(pub: bytes, sig: bytes, message: bytes):
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ReleaseRefused("A15_CRYPTOGRAPHY_REQUIRED") from exc
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, message)
    except (InvalidSignature, ValueError) as exc:
        raise ReleaseRefused("A15_SIGNATURE_INVALID") from exc


@dataclass(frozen=True, slots=True)
class ReleaseFloor:
    sequence: int
    artifact_sha256: str
    publisher_generation: int


class SignedReleaseAuthority:
    """Operator-pinned public Ed25519 key + independent persistent local floor.

    State should be stored OUTSIDE the A14 disposable instance. SQLite with
    full sync is not an externally trusted counter and must never be called one.
    """

    def __init__(self, witness_path: str | Path, *, engine_id: str,
                 installation_id: str, publisher_key_id: str,
                 publisher_public_key: bytes, approved_key_sha256: str,
                 publisher_generation: int = 1):
        path = Path(witness_path)
        if (not path.is_absolute() or path.is_symlink()
                or path.parent.is_symlink()
                or not path.parent.resolve().is_relative_to(
                    Path(tempfile.gettempdir()).resolve())
                or (path.exists() and not path.is_file())):
            raise ReleaseRefused("A15_WITNESS_MUST_BE_SEPARATE_TEMP_FILE")
        if (any(type(x) is not str or not _ID.fullmatch(x) for x in
                (engine_id, installation_id, publisher_key_id))
                or type(publisher_generation) is not int or publisher_generation < 1
                or type(publisher_public_key) is not bytes
                or len(publisher_public_key) != 32
                or type(approved_key_sha256) is not str
                or not _HASH.fullmatch(approved_key_sha256)
                or not hmac.compare_digest(
                    hashlib.sha256(publisher_public_key).hexdigest(),
                    approved_key_sha256)):
            raise ReleaseRefused("A15_INDEPENDENT_PUBLISHER_PIN_REQUIRED")
        first = not path.exists()
        self._db = open_sqlite(path)
        if first:
            path.chmod(0o600)
        elif path.stat().st_mode & 0o077:
            self._db.close()
            raise ReleaseRefused("A15_UNSAFE_WITNESS_PERMISSIONS")
        self.engine_id = engine_id
        self.installation_id = installation_id
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a15_authority (
                engine_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL,
                generation INTEGER NOT NULL, key_id TEXT NOT NULL,
                public_key BLOB NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a15_floor (
                engine_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL,
                digest TEXT NOT NULL, generation INTEGER NOT NULL)
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a15_receipts (
                digest TEXT PRIMARY KEY, engine_id TEXT NOT NULL,
                sequence INTEGER NOT NULL, envelope BLOB NOT NULL)
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a15_audit (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                engine_id TEXT NOT NULL, event TEXT NOT NULL,
                floor_sequence INTEGER NOT NULL, created_at TEXT
                NOT NULL DEFAULT CURRENT_TIMESTAMP)
        """)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute("SELECT * FROM a15_authority WHERE engine_id=?",
                                   (engine_id,)).fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO a15_authority VALUES(?,?,?,?,?,0)",
                    (engine_id, installation_id, publisher_generation,
                     publisher_key_id, publisher_public_key))
            elif (row["installation_id"] != installation_id
                    or row["generation"] != publisher_generation
                    or row["key_id"] != publisher_key_id
                    or not hmac.compare_digest(
                        row["public_key"], publisher_public_key)):
                raise ReleaseRefused("A15_TRUST_PIN_CHANGE_REJECTED")
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            self._db.close()
            raise

    def close(self):
        self._db.close()

    def _authority(self):
        row = self._db.execute(
            "SELECT * FROM a15_authority WHERE engine_id=?",
            (self.engine_id,)).fetchone()
        if row is None or row["revoked"]:
            raise ReleaseRefused("A15_PUBLISHER_REVOKED_OR_MISSING")
        return row

    def floor(self) -> ReleaseFloor | None:
        row = self._db.execute(
            "SELECT * FROM a15_floor WHERE engine_id=?", (self.engine_id,),
        ).fetchone()
        return (ReleaseFloor(row["sequence"], row["digest"], row["generation"])
                if row else None)

    def _check(self, signed_envelope: bytes, *, now: int, record,
               artifact_sha256: str, manifest: dict) -> dict:
        if type(now) is not int or now < 1:
            raise ReleaseRefused("A15_TRUSTED_CLOCK_REQUIRED")
        release, signature = parse_signed_release(signed_envelope)
        row = self._authority()
        if (release["publisher_generation"] != row["generation"]
                or release["publisher_key_id"] != row["key_id"]):
            raise ReleaseRefused("A15_PUBLISHER_GENERATION_MISMATCH")
        _verify_ed25519(row["public_key"], signature, DOMAIN + canonical(release))
        if release["issued_at"] > now + 5 or release["expires_at"] <= now:
            raise ReleaseRefused("A15_RELEASE_EXPIRED_OR_FUTURE")
        if (release["engine_id"] != self.engine_id
                or release["installation_id"] != self.installation_id
                or release["manifest_sha256"] != record.manifest_sha256
                or release["trust_generation"] != record.generation
                or release["artifact_sha256"] != artifact_sha256):
            raise ReleaseRefused("A15_SCOPE_MISMATCH")
        for field in ("engine_id", "engine_version", "installation_id",
                      "manifest_sha256", "trust_generation", "release"):
            if release[field] != manifest[field]:
                raise ReleaseRefused("A15_PACKAGE_RELEASE_MISMATCH")
        return release

    def promote(self, signed_envelope: bytes, *, now: int, record,
                archive: bytes) -> str:
        release, _ = parse_signed_release(signed_envelope)
        digest = hashlib.sha256(archive).hexdigest()
        manifest, _ = inspect_bundle(archive, approved_sha256=digest)
        validated = self._check(signed_envelope, now=now, record=record,
                                artifact_sha256=digest, manifest=manifest)
        assert validated == release
        self._db.execute("BEGIN IMMEDIATE")
        try:
            # Recheck authority under the write transaction; rotations and
            # revocation are serialized with floor promotion.
            self._check(signed_envelope, now=now, record=record,
                        artifact_sha256=digest, manifest=manifest)
            old = self.floor()
            seq = release["release_sequence"]
            if old is not None and (seq < old.sequence or
                    (seq == old.sequence and digest != old.artifact_sha256)):
                raise ReleaseRefused("A15_ROLLBACK_OR_EQUIVOCATION_REJECTED")
            existing = self._db.execute(
                "SELECT envelope FROM a15_receipts WHERE digest=?", (digest,),
            ).fetchone()
            if existing is not None and existing["envelope"] != signed_envelope:
                raise ReleaseRefused("A15_ARTIFACT_RECEIPT_CONFLICT")
            if existing is None:
                self._db.execute(
                    "INSERT INTO a15_receipts VALUES(?,?,?,?)",
                    (digest, self.engine_id, seq, signed_envelope))
            if old is None or seq > old.sequence:
                self._db.execute(
                    "INSERT INTO a15_floor VALUES(?,?,?,?) "
                    "ON CONFLICT(engine_id) DO UPDATE SET "
                    "sequence=excluded.sequence,digest=excluded.digest,"
                    "generation=excluded.generation",
                    (self.engine_id, seq, digest, release["publisher_generation"]))
                self._db.execute(
                    "INSERT INTO a15_audit(engine_id,event,floor_sequence) "
                    "VALUES(?,?,?)", (self.engine_id, "PROMOTE_PINNED_RELEASE", seq))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return digest

    def require_current(self, digest: str, *, now: int, record, manifest: dict):
        floor = self.floor()
        if floor is None or digest != floor.artifact_sha256:
            raise ReleaseRefused("A15_EXTERNAL_FLOOR_BLOCKS_ROLLBACK")
        row = self._db.execute(
            "SELECT envelope,sequence,engine_id FROM a15_receipts WHERE digest=?",
            (digest,)).fetchone()
        if row is None or row["engine_id"] != self.engine_id or row["sequence"] != floor.sequence:
            raise ReleaseRefused("A15_SIGNED_RECEIPT_REQUIRED")
        release = self._check(row["envelope"], now=now, record=record,
                              artifact_sha256=digest, manifest=manifest)
        if (release["release_sequence"] != floor.sequence
                or release["publisher_generation"] != floor.publisher_generation):
            raise ReleaseRefused("A15_RECEIPT_FLOOR_MISMATCH")

    def revoke_publisher(self, *, expected_generation: int):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._authority()
            if type(expected_generation) is not int or row["generation"] != expected_generation:
                raise ReleaseRefused("A15_REVOCATION_CAS")
            self._db.execute(
                "UPDATE a15_authority SET revoked=1 WHERE engine_id=?",
                (self.engine_id,))
            floor = self.floor()
            self._db.execute(
                "INSERT INTO a15_audit(engine_id,event,floor_sequence) VALUES(?,?,?)",
                (self.engine_id, "REVOKE_PUBLISHER", floor.sequence if floor else 0))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def rotate_publisher(self, *, new_key_id: str, new_public_key: bytes,
                         approved_key_sha256: str, expected_generation: int,
                         old_key_signature_b64: str):
        if (type(new_key_id) is not str or not _ID.fullmatch(new_key_id)
                or type(new_public_key) is not bytes or len(new_public_key) != 32
                or type(approved_key_sha256) is not str or not _HASH.fullmatch(approved_key_sha256)
                or not hmac.compare_digest(hashlib.sha256(new_public_key).hexdigest(),
                                           approved_key_sha256)
                or type(expected_generation) is not int or expected_generation < 1):
            raise ReleaseRefused("A15_ROTATION_INDEPENDENT_APPROVAL_REQUIRED")
        message = {
            "engine_id": self.engine_id, "installation_id": self.installation_id,
            "from_generation": expected_generation, "to_generation": expected_generation + 1,
            "new_key_id": new_key_id, "new_key_sha256": approved_key_sha256,
        }
        signature = _b64(old_key_signature_b64, 64)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            old = self._authority()
            if old["generation"] != expected_generation or old["key_id"] == new_key_id:
                raise ReleaseRefused("A15_ROTATION_CAS_OR_SAME_KEY")
            _verify_ed25519(old["public_key"], signature,
                            ROTATION_DOMAIN + canonical(message))
            self._db.execute(
                "UPDATE a15_authority SET generation=?,key_id=?,public_key=? "
                "WHERE engine_id=?",
                (expected_generation + 1, new_key_id, new_public_key, self.engine_id))
            floor = self.floor()
            self._db.execute(
                "INSERT INTO a15_audit(engine_id,event,floor_sequence) VALUES(?,?,?)",
                (self.engine_id, "ROTATE_SIGNER", floor.sequence if floor else 0))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise


class SignedMockDeploymentManager:
    """A15-only facade. Direct A14 API remains a mock, not production admission."""

    def __init__(self, mock: MockPackageDeploymentManager, authority: SignedReleaseAuthority):
        if (mock._engine_id != authority.engine_id
                or mock._installation_id != authority.installation_id
                or Path(authority._db.execute("PRAGMA database_list").fetchone()["file"])
                .resolve().is_relative_to(mock._root.resolve())):
            raise ReleaseRefused("A15_WITNESS_MUST_BE_INDEPENDENT_OF_A14_ROOT")
        self._mock = mock
        self._authority = authority

    def install(self, archive: bytes, signed_envelope: bytes, *,
                expected_revision: int, admission, now: int):
        status = self._mock.status()
        if (status.revision != expected_revision or status.state != "STOPPED"):
            raise ReleaseRefused("A15_STOP_AND_CAS_REQUIRED")
        record = self._mock._admit(admission, now)
        digest = self._authority.promote(signed_envelope, now=now,
                                         record=record, archive=archive)
        # Safety first: the independent floor advances BEFORE A14 activation.
        # On crash between these steps old code CANNOT restart through A15.
        return self._mock.install(
            archive, approved_sha256=digest, expected_revision=expected_revision,
            admission=admission, now=now)

    def start(self, *, expected_revision: int, admission, now: int):
        state = self._mock.status()
        if (state.revision != expected_revision or state.active is None
                or state.state != "STOPPED"):
            raise ReleaseRefused("A15_START_CAS_OR_STATE")
        record = self._mock._admit(admission, now)
        manifest = self._mock._verified_release(state.active, record)
        self._authority.require_current(state.active, now=now,
                                        record=record, manifest=manifest)
        return self._mock.start(expected_revision=expected_revision,
                                admission=admission, now=now)

    def rollback(self, *, expected_revision: int, admission, now: int):
        state = self._mock.status()
        if (state.revision != expected_revision or state.state != "STOPPED"
                or state.previous is None):
            raise ReleaseRefused("A15_ROLLBACK_STATE_OR_CAS")
        record = self._mock._admit(admission, now)
        manifest = self._mock._verified_release(state.previous, record)
        self._authority.require_current(state.previous, now=now,
                                        record=record, manifest=manifest)
        return self._mock.rollback(expected_revision=expected_revision,
                                   admission=admission, now=now)

    def stop(self, *, expected_revision: int):
        # Always possible even if publisher/license is revoked.
        return self._mock.stop(expected_revision=expected_revision)

    def status(self):
        return self._mock.status()
