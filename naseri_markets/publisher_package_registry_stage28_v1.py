"""Stage28 owner-reviewed publisher keys and bounded signed source ZIP intake.

This is an OFFLINE, trusted-operator-owned registry, NOT a public account-login
service, independent legal identity verification, or safe-to-execute scanner.
Publisher identity, keys, signed source and quarantine metadata are recorded
without importing or extracting untrusted code. Stage27 classifies and blocks
every successfully submitted core in the SAME Stage22 SQLite transaction.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .a24_publisher_admission import canonical, _ed25519
from .core_api_v1 import CoreBinding, CoreManifest, content_digest
from .durable_isolated_core_gate_stage22_v1 import DurableIsolatedCoreGate
from .signed_core_candidate_stage23_v1 import (
    SignedCandidateWitness, _PUBLISHER, _TENANT,
)
from .signed_public_intake_stage27_v1 import _insert_verified_public_locked

_ENROLL_DOMAIN = b"MMT-STAGE28-PUBLISHER-KEY-ENROLL-V1\x00"
_ROTATE_DOMAIN = b"MMT-STAGE28-PUBLISHER-KEY-ROTATE-V1\x00"
_KEY_ID = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FILES = frozenset({"source.py", "descriptor.json"})
_DESCRIPTOR_FIELDS = frozenset({
    "schema", "tenant_id", "publisher", "publisher_key_id", "binding_id",
    "source_sha256", "manifest_sha256", "binding_sha256",
    "candidate_sha256", "image",
})
_MAX_ARCHIVE_BYTES = 90000
_MAX_SOURCE = 65536
_MAX_DESCRIPTOR = 4096


class Stage28Refused(ValueError):
    """Sanitized refusal without source, developer PII or private keys."""


def _guard(ack: bool) -> None:
    if (ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise Stage28Refused("EXPLICIT_NONPRODUCTION_OWNER_ACK_REQUIRED")


def _identity(tenant: str, publisher: str, key_id: str) -> None:
    if (type(tenant) is not str or not _TENANT.fullmatch(tenant)
            or type(publisher) is not str or not _PUBLISHER.fullmatch(publisher)
            or type(key_id) is not str or not _KEY_ID.fullmatch(key_id)):
        raise Stage28Refused("VALID_OPERATOR_ASSIGNED_PUBLISHER_IDENTITY_REQUIRED")


def _private_dir(path: Path) -> None:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.is_dir()
            or path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise Stage28Refused("OWNER_PRIVATE_QUARANTINE_DIRECTORY_REQUIRED")


def _proof(public_key: bytes, signature: bytes, domain: bytes, message: dict) -> None:
    if (type(public_key) is not bytes or len(public_key) != 32
            or type(signature) is not bytes or len(signature) != 64):
        raise Stage28Refused("ED25519_PUBLIC_KEY_AND_PROOF_REQUIRED")
    try:
        _ed25519(public_key, signature, domain + canonical(message))
    except ValueError as exc:
        raise Stage28Refused("INVALID_PUBLISHER_PROOF_OF_POSSESSION") from exc


def _time(now: int, issued_at: int, nonce: str) -> None:
    if (type(now) is not int or type(issued_at) is not int
            or now < 1 or abs(now - issued_at) > 300
            or type(nonce) is not str or not _NONCE.fullmatch(nonce)):
        raise Stage28Refused("SHORT_LIVED_OPERATOR_CHALLENGE_REQUIRED")


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise Stage28Refused("DUPLICATE_DESCRIPTOR_FIELD")
        result[k] = v
    return result


def _decode_zip(payload: bytes) -> tuple[bytes, dict]:
    """Read two exact STORED ZIP members, no path extraction, nested files or exec."""
    if (type(payload) is not bytes or not 22 <= len(payload) <= _MAX_ARCHIVE_BYTES
            or payload[-22:-18] != b"PK\x05\x06" or payload[-2:] != b"\x00\x00"):
        raise Stage28Refused("EXACT_BOUNDED_NO_COMMENT_ZIP_REQUIRED")
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as z:
            items = z.infolist()
            if (len(items) != 2 or {v.filename for v in items} != _FILES
                    or z.comment or any(
                        v.is_dir() or v.flag_bits != 0
                        or v.compress_type != zipfile.ZIP_STORED
                        or v.file_size != v.compress_size
                        or v.extra or v.comment
                        or (v.external_attr >> 16 & 0o170000)
                            not in (0, stat.S_IFREG)
                        for v in items)):
                raise Stage28Refused("UNSUPPORTED_ARCHIVE_STRUCTURE")
            sizes = {v.filename: v.file_size for v in items}
            if (not 0 < sizes["source.py"] <= _MAX_SOURCE
                    or not 0 < sizes["descriptor.json"] <= _MAX_DESCRIPTOR):
                raise Stage28Refused("OVERSIZED_ARCHIVE_MEMBER")
            source = z.read("source.py")
            raw_descriptor = z.read("descriptor.json")
    except Stage28Refused:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError,
            UnicodeError) as exc:
        raise Stage28Refused("INVALID_OR_CORRUPT_ZIP") from exc
    try:
        descriptor = json.loads(
            raw_descriptor.decode("ascii"), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                Stage28Refused("NONFINITE_DESCRIPTOR")))
    except Stage28Refused:
        raise
    except (ValueError, UnicodeError) as exc:
        raise Stage28Refused("INVALID_DESCRIPTOR_JSON") from exc
    if (type(descriptor) is not dict or set(descriptor) != _DESCRIPTOR_FIELDS
            or canonical(descriptor) != raw_descriptor
            or type(descriptor["schema"]) is not int
            or descriptor["schema"] != 1):
        raise Stage28Refused("EXACT_CANONICAL_DESCRIPTOR_REQUIRED")
    return source, descriptor


@dataclass(frozen=True, slots=True)
class QuarantinedPackageReceipt:
    tenant_id: str
    publisher: str
    binding_id: str
    package_sha256: str
    source_sha256: str
    candidate_sha256: str
    state: str = "QUARANTINED_PUBLIC_SOURCE_NOT_EXECUTABLE"
    developer_external_identity_verified: bool = False
    package_executed: bool = False
    sandbox_certified: bool = False
    public_install_authorized: bool = False
    telegram_publish_authorized: bool = False
    broker_order_authorized: bool = False


class PublisherPackageRegistry:
    """Local owner-scoped publisher roster and public ZIP submission ledger.

    Stores ONLY publisher public keys (not private keys), hex digests and
    quarantine ZIP bytes. Registration+Stage27 deny and submission audit are
    one Stage22 SQLite transaction. File write occurs BEFORE that DB tx:
    interrupted writes may leave unusable orphan files, never permissions.
    """

    def __init__(self, stage22: DurableIsolatedCoreGate, quarantine_dir: Path,
                 *, operator_ack: bool = False) -> None:
        _guard(operator_ack)
        if type(stage22) is not DurableIsolatedCoreGate:
            raise Stage28Refused("EXACT_TRUSTED_STAGE22_REGISTRY_REQUIRED")
        _private_dir(quarantine_dir)
        self.stage22 = stage22
        self.quarantine_dir = quarantine_dir
        stage22.db.executescript("""
            CREATE TABLE IF NOT EXISTS secure28_publishers(
                tenant_id TEXT NOT NULL, publisher TEXT NOT NULL,
                revision INTEGER NOT NULL, state TEXT NOT NULL
                    CHECK(state IN ('ACTIVE','BLOCKED')),
                PRIMARY KEY(tenant_id,publisher)
            );
            CREATE TABLE IF NOT EXISTS secure28_keys(
                tenant_id TEXT NOT NULL, publisher TEXT NOT NULL,
                key_id TEXT NOT NULL, public_key BLOB NOT NULL,
                state TEXT NOT NULL CHECK(state IN
                    ('ACTIVE','RETIRED','REVOKED')),
                PRIMARY KEY(tenant_id,publisher,key_id),
                FOREIGN KEY(tenant_id,publisher) REFERENCES secure28_publishers
                    (tenant_id,publisher)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS secure28_one_active_key
                ON secure28_keys(tenant_id,publisher) WHERE state='ACTIVE';
            CREATE TABLE IF NOT EXISTS secure28_submissions(
                binding_id TEXT PRIMARY KEY REFERENCES secure22_bindings(binding_id),
                tenant_id TEXT NOT NULL, publisher TEXT NOT NULL,
                key_id TEXT NOT NULL, package_sha256 TEXT NOT NULL UNIQUE,
                source_sha256 TEXT NOT NULL, candidate_sha256 TEXT NOT NULL,
                key_revision INTEGER NOT NULL, created_at INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(state='QUARANTINED_NONEXECUTABLE')
            );
            CREATE TABLE IF NOT EXISTS secure28_audit(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL, publisher TEXT NOT NULL,
                action TEXT NOT NULL, subject TEXT NOT NULL,
                state_digest TEXT NOT NULL, recorded_at INTEGER NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS secure28_no_audit_rewrite
                BEFORE UPDATE ON secure28_audit
                BEGIN SELECT RAISE(ABORT,'STAGE28_IMMUTABLE_AUDIT'); END;
            CREATE TRIGGER IF NOT EXISTS secure28_no_audit_delete
                BEFORE DELETE ON secure28_audit
                BEGIN SELECT RAISE(ABORT,'STAGE28_IMMUTABLE_AUDIT'); END;
            CREATE TRIGGER IF NOT EXISTS secure28_no_submission_rewrite
                BEFORE UPDATE ON secure28_submissions
                BEGIN SELECT RAISE(ABORT,'STAGE28_IMMUTABLE_SUBMISSION'); END;
            CREATE TRIGGER IF NOT EXISTS secure28_no_submission_delete
                BEFORE DELETE ON secure28_submissions
                BEGIN SELECT RAISE(ABORT,'STAGE28_IMMUTABLE_SUBMISSION'); END;
        """)

    def _audit(self, tenant: str, publisher: str, action: str,
               subject: str, digest: str, now: int) -> None:
        self.stage22.db.execute(
            "INSERT INTO secure28_audit(tenant_id,publisher,action,subject,"
            "state_digest,recorded_at) VALUES(?,?,?,?,?,?)",
            (tenant,publisher,action,subject,digest,now))

    def _publisher(self, tenant: str, publisher: str):
        return self.stage22.db.execute(
            "SELECT * FROM secure28_publishers WHERE tenant_id=? AND publisher=?",
            (tenant,publisher)).fetchone()

    def enroll(self, *, tenant_id: str, publisher: str, key_id: str,
               public_key: bytes, proof_signature: bytes, nonce: str,
               issued_at: int, now: int, operator_ack: bool = False) -> dict:
        _guard(operator_ack)
        _identity(tenant_id,publisher,key_id)
        _time(now,issued_at,nonce)
        digest = hashlib.sha256(public_key).hexdigest() if type(public_key) is bytes else ""
        claim = dict(tenant_id=tenant_id,publisher=publisher,key_id=key_id,
                     key_sha256=digest,nonce=nonce,issued_at=issued_at)
        _proof(public_key,proof_signature,_ENROLL_DOMAIN,claim)
        with self.stage22._tx():
            if self._publisher(tenant_id,publisher):
                raise Stage28Refused("PUBLISHER_IDENTITY_ALREADY_REGISTERED")
            if self.stage22.db.execute(
                    "SELECT COUNT(*) FROM secure28_publishers").fetchone()[0] >= 64:
                raise Stage28Refused("PUBLISHER_REGISTRY_QUOTA")
            self.stage22.db.execute(
                "INSERT INTO secure28_publishers VALUES(?,?,1,'ACTIVE')",
                (tenant_id,publisher))
            self.stage22.db.execute(
                "INSERT INTO secure28_keys VALUES(?,?,?,?,'ACTIVE')",
                (tenant_id,publisher,key_id,public_key))
            self._audit(tenant_id,publisher,"ENROLLED",key_id,digest,now)
        return self.status(tenant_id,publisher)

    def rotate(self, *, tenant_id: str, publisher: str, old_key_id: str,
               new_key_id: str, new_public_key: bytes,
               old_signature: bytes, new_signature: bytes,
               expected_revision: int, nonce: str, issued_at: int,
               now: int, operator_ack: bool = False) -> dict:
        _guard(operator_ack)
        _identity(tenant_id,publisher,old_key_id)
        _identity(tenant_id,publisher,new_key_id)
        _time(now,issued_at,nonce)
        if (old_key_id == new_key_id or type(expected_revision) is not int
                or type(new_public_key) is not bytes or len(new_public_key) != 32):
            raise Stage28Refused("FRESH_ROTATION_ID_AND_KEY_REQUIRED")
        digest=hashlib.sha256(new_public_key).hexdigest()
        claim=dict(tenant_id=tenant_id,publisher=publisher,
                   old_key_id=old_key_id,new_key_id=new_key_id,
                   new_key_sha256=digest,revision=expected_revision,
                   nonce=nonce,issued_at=issued_at)
        with self.stage22._tx():
            person=self._publisher(tenant_id,publisher)
            old=self.stage22.db.execute(
                "SELECT * FROM secure28_keys WHERE tenant_id=? AND publisher=?"
                " AND key_id=?", (tenant_id,publisher,old_key_id)).fetchone()
            if (person is None or person["state"] != "ACTIVE"
                    or person["revision"] != expected_revision
                    or old is None or old["state"] != "ACTIVE"
                    or old["public_key"] == new_public_key
                    or self.stage22.db.execute(
                        "SELECT 1 FROM secure28_keys WHERE tenant_id=? "
                        "AND publisher=? AND key_id=?",
                        (tenant_id,publisher,new_key_id)).fetchone()):
                raise Stage28Refused("STALE_OR_REVOKED_ROTATION")
            _proof(old["public_key"],old_signature,_ROTATE_DOMAIN,claim)
            _proof(new_public_key,new_signature,_ROTATE_DOMAIN,claim)
            self.stage22.db.execute(
                "UPDATE secure28_keys SET state='RETIRED' WHERE "
                "tenant_id=? AND publisher=? AND key_id=?",
                (tenant_id,publisher,old_key_id))
            self.stage22.db.execute(
                "INSERT INTO secure28_keys VALUES(?,?,?,?,'ACTIVE')",
                (tenant_id,publisher,new_key_id,new_public_key))
            self.stage22.db.execute(
                "UPDATE secure28_publishers SET revision=revision+1 "
                "WHERE tenant_id=? AND publisher=?", (tenant_id,publisher))
            self._audit(tenant_id,publisher,"ROTATED",new_key_id,digest,now)
        return self.status(tenant_id,publisher)

    def revoke(self, *, tenant_id: str, publisher: str, key_id: str,
               expected_revision: int, now: int,
               operator_ack: bool = False) -> dict:
        _guard(operator_ack)
        _identity(tenant_id,publisher,key_id)
        if type(now) is not int or now < 1 or type(expected_revision) is not int:
            raise Stage28Refused("VALID_REVOCATION_REVISION_REQUIRED")
        with self.stage22._tx():
            person=self._publisher(tenant_id,publisher)
            key=self.stage22.db.execute(
                "SELECT * FROM secure28_keys WHERE tenant_id=? AND publisher=?"
                " AND key_id=?", (tenant_id,publisher,key_id)).fetchone()
            if (person is None or person["revision"] != expected_revision
                    or person["state"] != "ACTIVE" or key is None
                    or key["state"] == "REVOKED"):
                raise Stage28Refused("REVOKED_OR_STALE_KEY")
            self.stage22.db.execute(
                "UPDATE secure28_keys SET state='REVOKED' WHERE "
                "tenant_id=? AND publisher=? AND key_id=?",
                (tenant_id,publisher,key_id))
            if key["state"] == "ACTIVE":
                self.stage22.db.execute(
                    "UPDATE secure28_publishers SET state='BLOCKED',"
                    "revision=revision+1 WHERE tenant_id=? AND publisher=?",
                    (tenant_id,publisher))
            else:
                self.stage22.db.execute(
                    "UPDATE secure28_publishers SET revision=revision+1 "
                    "WHERE tenant_id=? AND publisher=?", (tenant_id,publisher))
            self._audit(tenant_id,publisher,"REVOKED",key_id,
                        hashlib.sha256(key["public_key"]).hexdigest(),now)
        return self.status(tenant_id,publisher)

    def status(self, tenant_id: str, publisher: str) -> dict:
        if (type(tenant_id) is not str or not _TENANT.fullmatch(tenant_id)
                or type(publisher) is not str or not _PUBLISHER.fullmatch(publisher)):
            raise Stage28Refused("OPERATOR_IDENTIFIED_PUBLISHER_REQUIRED")
        person=self._publisher(tenant_id,publisher)
        if person is None:
            raise Stage28Refused("PUBLISHER_NOT_REGISTERED")
        key=self.stage22.db.execute(
            "SELECT key_id FROM secure28_keys WHERE tenant_id=? "
            "AND publisher=? AND state='ACTIVE'", (tenant_id,publisher)).fetchone()
        return dict(tenant_id=tenant_id,publisher=publisher,
                    revision=person["revision"],state=person["state"],
                    active_key_id=key["key_id"] if key else None,
                    externally_verified_identity=False,
                    executable_publishing_authorized=False)

    def submit(self, *, tenant_id: str, publisher: str, key_id: str,
               stage23: SignedCandidateWitness, package: bytes,
               signed_candidate: bytes, manifest: CoreManifest,
               binding: CoreBinding, expected_image: str, now: int,
               operator_ack: bool = False,
               _auth_session_sha256: str | None = None) -> QuarantinedPackageReceipt:
        _guard(operator_ack)
        _identity(tenant_id,publisher,key_id)
        if (type(stage23) is not SignedCandidateWitness
                or type(manifest) is not CoreManifest
                or type(binding) is not CoreBinding
                or type(now) is not int or now < 1
                or type(signed_candidate) is not bytes):
            raise Stage28Refused("REVIEWED_SIGNED_PUBLIC_PACKAGE_REQUIRED")
        # Once Stage29 local intake policy is initialized, even the
        # pre-existing Stage28 operator-only path requires a valid session.
        # No executable plugin action can ever be granted by this policy.
        enforced=self.stage22.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='secure29_policy'").fetchone() is not None
        if enforced and (type(_auth_session_sha256) is not str
                         or not _SHA.fullmatch(_auth_session_sha256)):
            raise Stage28Refused("STAGE29_AUTHENTICATED_INTAKE_REQUIRED")
        if not enforced and _auth_session_sha256 is not None:
            raise Stage28Refused("STAGE29_POLICY_NOT_INITIALIZED")
        if enforced:
            self._check_session_locked(
                _auth_session_sha256, tenant_id, publisher, key_id, now,
                consume=False)
        source,descriptor=_decode_zip(package)
        package_sha=hashlib.sha256(package).hexdigest()
        source_sha=hashlib.sha256(source).hexdigest()
        manifest_sha=content_digest(manifest)
        binding_sha=content_digest(binding)
        candidate_sha=hashlib.sha256(signed_candidate).hexdigest()
        expected=dict(schema=1,tenant_id=tenant_id,publisher=publisher,
                      publisher_key_id=key_id,binding_id=binding.binding_id,
                      source_sha256=source_sha,manifest_sha256=manifest_sha,
                      binding_sha256=binding_sha,candidate_sha256=candidate_sha,
                      image=expected_image)
        if descriptor != expected:
            raise Stage28Refused("PACKAGE_DESCRIPTOR_OR_CONTENT_MISMATCH")
        # Stage23's public key must be exactly the ACTIVE registered key;
        # key status is rechecked under the same Stage22 write transaction.
        try:
            verdict=stage23.current(
                signed_candidate, source=source, manifest=manifest,
                binding=binding, tenant_id=tenant_id, publisher=publisher,
                publisher_key_id=key_id, image=expected_image, now=now)
        except (ValueError,TypeError) as exc:
            raise Stage28Refused("UNTRUSTED_SIGNED_CANDIDATE") from exc
        if not hmac.compare_digest(verdict.envelope_sha256,candidate_sha):
            raise Stage28Refused("CANDIDATE_SIGNATURE_DIGEST_MISMATCH")
        person=self._publisher(tenant_id,publisher)
        active=self.stage22.db.execute(
            "SELECT public_key,state FROM secure28_keys WHERE tenant_id=?"
            " AND publisher=? AND key_id=?",
            (tenant_id,publisher,key_id)).fetchone()
        if (person is None or person["state"]!="ACTIVE"
                or active is None or active["state"]!="ACTIVE"
                or active["public_key"]!=stage23.pub):
            raise Stage28Refused("INACTIVE_OR_UNVERIFIED_PUBLISHER")
        if sum(1 for _ in self.quarantine_dir.iterdir()) >= 128:
            raise Stage28Refused("QUARANTINE_FILE_QUOTA")
        archive_path=self.quarantine_dir / (package_sha+".zip")
        if archive_path.exists() or archive_path.is_symlink():
            raise Stage28Refused("PACKAGE_ALREADY_IN_QUARANTINE")
        try:
            fd=os.open(archive_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,
                       0o600)
            with os.fdopen(fd,"wb") as stream:
                stream.write(package)
                stream.flush()
                os.fsync(stream.fileno())
            with self.stage22._tx():
                if enforced:
                    # Stage29 token checks and single use happen in the SAME
                    # transaction as the signed Stage27+28 quarantine rows.
                    self._check_session_locked(
                        _auth_session_sha256, tenant_id, publisher, key_id,
                        now, consume=True)
                person=self._publisher(tenant_id,publisher)
                key=self.stage22.db.execute(
                    "SELECT public_key,state FROM secure28_keys WHERE tenant_id=?"
                    " AND publisher=? AND key_id=?",
                    (tenant_id,publisher,key_id)).fetchone()
                if (person is None or person["state"] != "ACTIVE"
                        or key is None or key["state"] != "ACTIVE"
                        or key["public_key"] != stage23.pub
                        or not self.stage22.host.policy.enabled
                        or self.stage22.host.policy.image != expected_image):
                    raise Stage28Refused("INACTIVE_OR_UNVERIFIED_PUBLISHER")
                # The signer's Stage23 revocation can race in another DB;
                # its *current* proof is rechecked before local commit.
                stage23.current(
                    signed_candidate,source=source,manifest=manifest,
                    binding=binding,tenant_id=tenant_id,publisher=publisher,
                    publisher_key_id=key_id,image=expected_image,now=now)
                _insert_verified_public_locked(
                    self.stage22,tenant_id=tenant_id,publisher=publisher,
                    publisher_key_id=key_id,manifest=manifest,binding=binding,
                    source_sha256=source_sha,candidate_sha256=candidate_sha,
                    expected_image=expected_image)
                self.stage22.db.execute(
                    "INSERT INTO secure28_submissions VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (binding.binding_id,tenant_id,publisher,key_id,package_sha,
                     source_sha,candidate_sha,person["revision"],now,
                     "QUARANTINED_NONEXECUTABLE"))
                self._audit(tenant_id,publisher,"SUBMITTED",binding.binding_id,
                            package_sha,now)
        except (OSError,ValueError,TypeError,sqlite3.DatabaseError) as exc:
            # If the transaction fails, no Stage22 public registration can
            # survive. A staging file may remain as a non-executable orphan.
            raise Stage28Refused("QUARANTINED_INTAKE_REFUSED_NO_EXECUTION") from exc
        return QuarantinedPackageReceipt(tenant_id,publisher,binding.binding_id,
                                         package_sha,source_sha,candidate_sha)

    def _check_session_locked(
            self, token_sha: str, tenant_id: str, publisher: str,
            key_id: str, now: int, *, consume: bool) -> None:
        """Stage29's local single-use admission fence; caller holds tx on consume.

        Not a public bearer-token endpoint. Untrusted callers never supply
        tenant/publisher identities to the Stage29 frontend.
        """
        if type(token_sha) is not str or not _SHA.fullmatch(token_sha):
            raise Stage28Refused("STAGE29_SESSION_DIGEST_REQUIRED")
        person=self._publisher(tenant_id,publisher)
        row=self.stage22.db.execute(
            "SELECT * FROM secure29_sessions WHERE session_sha256=?",
            (token_sha,)).fetchone()
        if (person is None or person["state"]!="ACTIVE"
                or row is None or row["state"]!="ACTIVE"
                or row["tenant_id"]!=tenant_id
                or row["publisher"]!=publisher
                or row["key_id"]!=key_id
                or row["publisher_revision"]!=person["revision"]
                or type(now) is not int
                or not row["issued_at"] <= now < row["expires_at"]):
            raise Stage28Refused("STAGE29_SESSION_EXPIRED_REVOKED_OR_WRONG_SCOPE")
        if consume:
            result=self.stage22.db.execute(
                "UPDATE secure29_sessions SET state='CONSUMED' "
                "WHERE session_sha256=? AND state='ACTIVE'", (token_sha,))
            if result.rowcount != 1:
                raise Stage28Refused("STAGE29_SESSION_ALREADY_USED")

    def inspect_submission(self, *, tenant_id: str, binding_id: str) -> dict:
        self.stage22._row(tenant_id,binding_id)
        row=self.stage22.db.execute(
            "SELECT * FROM secure28_submissions WHERE tenant_id=? "
            "AND binding_id=?", (tenant_id,binding_id)).fetchone()
        if row is None:
            raise Stage28Refused("TENANT_PACKAGE_NOT_FOUND")
        archive=self.quarantine_dir / (row["package_sha256"]+".zip")
        if archive.is_symlink() or not archive.is_file():
            raise Stage28Refused("QUARANTINE_EVIDENCE_MISSING")
        st=archive.lstat()
        if (st.st_nlink != 1 or st.st_uid != os.geteuid()
                or not stat.S_ISREG(st.st_mode)
                or stat.S_IMODE(st.st_mode) & 0o077
                or st.st_size > _MAX_ARCHIVE_BYTES):
            raise Stage28Refused("QUARANTINE_FILE_UNTRUSTED")
        fd=os.open(archive,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,"rb") as stream:
            raw=stream.read(_MAX_ARCHIVE_BYTES+1)
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),
                                   row["package_sha256"]):
            raise Stage28Refused("QUARANTINE_HASH_MISMATCH")
        key=self.stage22.db.execute(
            "SELECT state FROM secure28_keys WHERE tenant_id=? "
            "AND publisher=? AND key_id=?",
            (tenant_id,row["publisher"],row["key_id"])).fetchone()
        return dict(tenant_id=tenant_id,binding_id=binding_id,
                    state=row["state"],package_sha256=row["package_sha256"],
                    publisher_key_current=bool(key and key["state"]=="ACTIVE"),
                    stage27_initial_lock=True,
                    source_execution_authorized=False,public_install_authorized=False,
                    telegram_publish_authorized=False,broker_order_authorized=False)

    def audit(self, *, tenant_id: str, publisher: str) -> tuple[dict, ...]:
        self.status(tenant_id,publisher)
        rows=self.stage22.db.execute(
            "SELECT sequence,action,subject,state_digest,recorded_at "
            "FROM secure28_audit WHERE tenant_id=? AND publisher=? "
            "ORDER BY sequence",(tenant_id,publisher)).fetchall()
        return tuple(dict(r) for r in rows)


__all__ = [
    "Stage28Refused","QuarantinedPackageReceipt","PublisherPackageRegistry",
    "_ENROLL_DOMAIN","_ROTATE_DOMAIN",
]
