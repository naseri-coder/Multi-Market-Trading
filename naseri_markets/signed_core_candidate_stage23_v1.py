"""Stage 23: separately pinned dual-signed EXECUTABLE-source candidate review.

A24/A25 *inert-only* grants MUST NOT be upgraded by interpretation.
This is an independent, opt-in nonproduction candidate proof that still
authorizes NO source execution, installation, public upload, or trades.
A real hostile-plugin deployment needs distinct runtime acceptance.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from .a24_publisher_admission import canonical, _ed25519, _signature
from .core_api_v1 import CoreBinding, CoreManifest, content_digest
from .secure_plugin_runtime_v1 import _IMAGE

_P = re.compile(r"[0-9a-f]{64}\Z")
_TENANT = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")
_PUBLISHER = re.compile(r"[a-z][a-z0-9_.-]{2,79}\Z")
_FIELDS = frozenset({
    "schema", "kind", "visibility", "tenant_id", "binding_id", "core_id",
    "core_version", "publisher", "publisher_key_id", "manifest_sha256",
    "binding_sha256", "source_sha256", "image", "sequence", "issued_at",
    "expires_at", "capabilities", "execution_mode",
})
_ENVELOPE = frozenset({"claim", "publisher_signature_b64",
                       "operator_signature_b64"})
_PUB_DOMAIN = b"MMT-STAGE23-SOURCE-CANDIDATE-PUBLISHER-V1\x00"
_OP_DOMAIN = b"MMT-STAGE23-SOURCE-CANDIDATE-OPERATOR-V1\x00"


class SignedCandidateRefused(ValueError):
    """No untrusted signer input or source bytes are disclosed on refusal."""


def _gate(ack: bool) -> None:
    if ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1" or (
            os.environ.get("MMT_PRODUCTION") == "1"):
        raise SignedCandidateRefused("NONPRODUCTION_OPERATOR_ACK_REQUIRED")


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise SignedCandidateRefused("DUPLICATE_SIGNED_JSON_FIELD")
        out[key] = value
    return out


def _parse(raw: bytes) -> tuple[dict, bytes, bytes, str]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 4096:
        raise SignedCandidateRefused("BOUNDED_SIGNED_CANDIDATE_REQUIRED")
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             SignedCandidateRefused("NONFINITE_SIGNED_JSON")))
    except SignedCandidateRefused:
        raise
    except (ValueError, UnicodeError) as exc:
        raise SignedCandidateRefused("MALFORMED_SIGNED_CANDIDATE") from exc
    if type(obj) is not dict or set(obj) != _ENVELOPE or (
            canonical(obj) != raw):
        raise SignedCandidateRefused("CANONICAL_EXACT_SIGNED_ENVELOPE_REQUIRED")
    claim = obj["claim"]
    if type(claim) is not dict or set(claim) != _FIELDS:
        raise SignedCandidateRefused("UNKNOWN_OR_MISSING_CANDIDATE_FIELDS")
    if (type(claim["schema"]) is not int or claim["schema"] != 1
            or claim["kind"] != "public_generic_source_candidate"
            or claim["visibility"] != "public"
            or claim["capabilities"] != ["offline_core_decision_only"]
            or claim["execution_mode"] != "untrusted_gvisor_only_pending_proof"
            or type(claim["tenant_id"]) is not str
            or not _TENANT.fullmatch(claim["tenant_id"])
            or type(claim["publisher"]) is not str
            or not _PUBLISHER.fullmatch(claim["publisher"])
            or type(claim["publisher_key_id"]) is not str
            or not _TENANT.fullmatch(claim["publisher_key_id"])
            or type(claim["binding_id"]) is not str
            or not 1 <= len(claim["binding_id"]) <= 128
            or type(claim["core_id"]) is not str
            or not 1 <= len(claim["core_id"]) <= 128
            or type(claim["core_version"]) is not str
            or not 1 <= len(claim["core_version"]) <= 64
            or type(claim["image"]) is not str
            or not _IMAGE.fullmatch(claim["image"])
            or type(claim["sequence"]) is not int
            or not 1 <= claim["sequence"] < 2**63
            or type(claim["issued_at"]) is not int
            or type(claim["expires_at"]) is not int
            or not 1 <= claim["issued_at"] < claim["expires_at"]
            or claim["expires_at"] - claim["issued_at"] > 86400):
        raise SignedCandidateRefused("UNSUPPORTED_CANDIDATE_CAPABILITY_OR_IDENTITY")
    if any(type(claim[key]) is not str or not _P.fullmatch(claim[key])
           for key in ("manifest_sha256","binding_sha256","source_sha256")):
        raise SignedCandidateRefused("EXACT_DIGEST_PIN_REQUIRED")
    if any(tag in (claim["core_id"]+" "+claim["binding_id"]).lower()
           for tag in ("ny_first_reversal", "nyfr", "owner_only", "private_core")):
        raise SignedCandidateRefused("OWNER_PRIVATE_SOURCE_NEVER_PUBLIC")
    try:
        pub = _signature(obj["publisher_signature_b64"])
        op = _signature(obj["operator_signature_b64"])
    except ValueError as exc:
        raise SignedCandidateRefused("NONCANONICAL_SIGNATURE_REQUIRED") from exc
    return claim, pub, op, hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateReceipt:
    tenant_id: str
    binding_id: str
    sequence: int
    envelope_sha256: str
    source_sha256: str
    state: str = "SIGNED_EXECUTABLE_CANDIDATE_REVIEWED_NO_INSTALL"
    gvisor_observed_on_real_host: bool = False
    executable_installed: bool = False
    executable_run_authorized: bool = False
    public_marketplace_authorized: bool = False
    trading_authorized: bool = False


class SignedCandidateWitness:
    """Explicit operator-pinned trust keys, durable rollback floor and revoke.

    Construct on isolated owner-private 0700 folder; tenant and publisher
    key identities MUST come from independently authenticated operator state.
    No private keys, source bytes or execution capabilities stored.
    """

    def __init__(self, path: Path, *, publisher_public_key: bytes,
                 publisher_key_sha256: str, operator_public_key: bytes,
                 operator_key_sha256: str, operator_ack: bool = False):
        _gate(operator_ack)
        if (not isinstance(path, Path) or not path.is_absolute()
                or path.is_symlink() or not path.parent.is_dir()
                or path.parent.is_symlink()
                or path.parent.stat().st_uid != os.geteuid()
                or stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
            raise SignedCandidateRefused("OWNER_PRIVATE_WITNESS_REQUIRED")
        for key, digest in ((publisher_public_key, publisher_key_sha256),
                            (operator_public_key, operator_key_sha256)):
            if (type(key) is not bytes or len(key) != 32
                    or type(digest) is not str or not _P.fullmatch(digest)
                    or not hmac.compare_digest(hashlib.sha256(key).hexdigest(),
                                               digest)):
                raise SignedCandidateRefused("INDEPENDENT_ED25519_KEY_PIN_REQUIRED")
        if publisher_public_key == operator_public_key:
            raise SignedCandidateRefused("TWO_DISTINCT_TRUST_ISSUERS_REQUIRED")
        if path.exists():
            st = path.lstat()
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or st.st_uid != os.geteuid()
                    or stat.S_IMODE(st.st_mode) & 0o077):
                raise SignedCandidateRefused("OWNER_PRIVATE_WITNESS_FILE_REQUIRED")
        else:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                         0o600)
            os.close(fd)
        self.db = sqlite3.connect(path, isolation_level=None, timeout=0.2)
        self.db.row_factory = sqlite3.Row
        self.pub = publisher_public_key
        self.op = operator_public_key
        self.db.execute("""CREATE TABLE IF NOT EXISTS stage23_issuer_pins(
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            publisher_key_sha256 TEXT NOT NULL,
            operator_key_sha256 TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS stage23_floors(
            tenant_id TEXT NOT NULL, binding_id TEXT NOT NULL,
            sequence INTEGER NOT NULL, envelope_sha256 TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL, binding_sha256 TEXT NOT NULL,
            image TEXT NOT NULL, publisher TEXT NOT NULL,
            publisher_key_id TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1)),
            PRIMARY KEY(tenant_id,binding_id))""")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT * FROM stage23_issuer_pins WHERE singleton=1").fetchone()
            if existing is None:
                self.db.execute(
                    "INSERT INTO stage23_issuer_pins VALUES(1,?,?)",
                    (publisher_key_sha256,operator_key_sha256))
            elif (existing["publisher_key_sha256"] != publisher_key_sha256
                  or existing["operator_key_sha256"] != operator_key_sha256):
                raise SignedCandidateRefused("ISSUER_KEYS_CHANGED_ON_REOPEN")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _verified(self, raw: bytes, *, source: bytes,
                  manifest: CoreManifest, binding: CoreBinding,
                  tenant_id: str, publisher: str, publisher_key_id: str,
                  image: str, now: int) -> tuple[dict, str]:
        claim, pub, op, digest = _parse(raw)
        if (type(source) is not bytes or not 1 <= len(source) <= 65536
                or type(manifest) is not CoreManifest
                or type(binding) is not CoreBinding
                or type(now) is not int or not claim["issued_at"] <= now < claim["expires_at"]
                or claim["tenant_id"] != tenant_id
                or claim["publisher"] != publisher
                or claim["publisher_key_id"] != publisher_key_id
                or claim["image"] != image
                or claim["core_id"] != manifest.core_id
                or claim["core_version"] != manifest.core_version
                or claim["binding_id"] != binding.binding_id
                or binding.instrument.market not in manifest.supported_markets
                or not hmac.compare_digest(claim["manifest_sha256"],
                                           content_digest(manifest))
                or not hmac.compare_digest(claim["binding_sha256"],
                                           content_digest(binding))
                or not hmac.compare_digest(claim["source_sha256"],
                                           hashlib.sha256(source).hexdigest())):
            raise SignedCandidateRefused("CANDIDATE_BINDING_OR_SOURCE_DRIFT")
        try:
            _ed25519(self.pub, pub, _PUB_DOMAIN + canonical(claim))
            _ed25519(self.op, op, _OP_DOMAIN + canonical({
                "claim": claim,
                "publisher_signature_b64":
                    base64.b64encode(pub).decode("ascii")}))
        except ValueError as exc:
            raise SignedCandidateRefused("INVALID_DUAL_ISSUER_SIGNATURE") from exc
        return claim, digest

    def admit(self, raw: bytes, *, source: bytes, manifest: CoreManifest,
              binding: CoreBinding, tenant_id: str, publisher: str,
              publisher_key_id: str, image: str, now: int,
              operator_ack: bool = False) -> CandidateReceipt:
        _gate(operator_ack)
        claim, digest = self._verified(
            raw, source=source, manifest=manifest, binding=binding,
            tenant_id=tenant_id, publisher=publisher,
            publisher_key_id=publisher_key_id, image=image, now=now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute(
                "SELECT * FROM stage23_floors WHERE tenant_id=? AND binding_id=?",
                (tenant_id, binding.binding_id)).fetchone()
            if old and (old["revoked"] or claim["sequence"] <= old["sequence"]):
                raise SignedCandidateRefused("REVOKED_OR_ROLLBACK_CANDIDATE")
            if old and any(old[key] != claim[key] for key in (
                    "source_sha256", "manifest_sha256", "binding_sha256",
                    "image", "publisher", "publisher_key_id")):
                raise SignedCandidateRefused("SOURCE_CHANGE_REQUIRES_NEW_BINDING")
            self.db.execute(
                "INSERT INTO stage23_floors VALUES (?,?,?,?,?,?,?,?,?,?,0)"
                " ON CONFLICT(tenant_id,binding_id) DO UPDATE SET "
                "sequence=excluded.sequence,"
                "envelope_sha256=excluded.envelope_sha256,revoked=0",
                (tenant_id, binding.binding_id, claim["sequence"], digest,
                 claim["source_sha256"],claim["manifest_sha256"],
                 claim["binding_sha256"],claim["image"],claim["publisher"],
                 claim["publisher_key_id"]))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return CandidateReceipt(tenant_id, binding.binding_id, claim["sequence"],
                                digest, claim["source_sha256"])

    def current(self, raw: bytes, *, source: bytes, manifest: CoreManifest,
                binding: CoreBinding, tenant_id: str, publisher: str,
                publisher_key_id: str, image: str, now: int) -> CandidateReceipt:
        claim, digest = self._verified(
            raw, source=source, manifest=manifest, binding=binding,
            tenant_id=tenant_id, publisher=publisher,
            publisher_key_id=publisher_key_id, image=image, now=now)
        row = self.db.execute(
            "SELECT * FROM stage23_floors WHERE tenant_id=? AND binding_id=?",
            (tenant_id, binding.binding_id)).fetchone()
        if (row is None or row["revoked"] or row["sequence"] != claim["sequence"]
                or not hmac.compare_digest(row["envelope_sha256"], digest)
                or not hmac.compare_digest(row["source_sha256"],
                                           claim["source_sha256"])):
            raise SignedCandidateRefused("CANDIDATE_NOT_CURRENT_OR_REVOKED")
        return CandidateReceipt(tenant_id, binding.binding_id, claim["sequence"],
                                digest, claim["source_sha256"])

    def revoke(self, tenant_id: str, binding_id: str, *,
               operator_ack: bool = False) -> None:
        _gate(operator_ack)
        result = self.db.execute(
            "UPDATE stage23_floors SET revoked=1 WHERE tenant_id=? AND binding_id=?",
            (tenant_id, binding_id))
        if result.rowcount != 1:
            raise SignedCandidateRefused("CANDIDATE_NOT_KNOWN")


__all__ = ["SignedCandidateRefused", "CandidateReceipt",
           "SignedCandidateWitness", "_PUB_DOMAIN", "_OP_DOMAIN"]
