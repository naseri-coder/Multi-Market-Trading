"""A24 NON-PRODUCTION public Custom publisher trust and metadata admission.

Independent operator-pinned Ed25519 publisher/operator keys, double-signed
metadata admission, sequence floor, revoke/expiry, and optional A23 fixed
PAPER sandbox orchestration. NEVER downloads/installs/executes plugins.
NY First-Reversal remains OWNER_ONLY and outside all public admission paths.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .a21_custom_contract import CustomContractCatalog, CustomEngineContract
from .a22_custom_bridge import CustomPaperRuntimeBridge
from .a23_sandbox_adapter import FixedCustomSandbox
from .delivery_ledger import open_sqlite

PUBLISHER_DOMAIN = b"MMT-A24-PUBLIC-CUSTOM-PUBLISHER-V1\x00"
OPERATOR_DOMAIN = b"MMT-A24-INSTALL-OPERATOR-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_KEY_ID = re.compile(r"[a-z][a-z0-9_]{2,39}\Z")
_INSTALL = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_PUBLISHER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
_CLAIM_FIELDS = frozenset({
    "schema_version", "kind", "engine_id", "engine_version",
    "publisher", "publisher_key_id", "installation_id", "descriptor_sha256",
    "sequence", "issued_at", "expires_at", "permissions", "execution_kind",
    "artifact_policy", "runtime_mode",
})
_ENVELOPE_FIELDS = frozenset({
    "claim", "publisher_signature_b64", "operator_signature_b64",
})


class PublisherAdmissionRefused(ValueError):
    """Issuer, signer, identity, revocation, order, or time was invalid."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise PublisherAdmissionRefused("A24_DUPLICATE_JSON_FIELD")
        out[k] = v
    return out


def _signature(raw: object) -> bytes:
    if type(raw) is not str or len(raw) != 88:
        raise PublisherAdmissionRefused("A24_NONCANONICAL_SIGNATURE")
    try:
        value = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise PublisherAdmissionRefused("A24_BAD_BASE64") from exc
    if len(value) != 64 or base64.b64encode(value).decode("ascii") != raw:
        raise PublisherAdmissionRefused("A24_NONCANONICAL_SIGNATURE")
    return value


def _ed25519(public_key: bytes, signature: bytes, message: bytes) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise PublisherAdmissionRefused("A24_CRYPTOGRAPHY_REQUIRED") from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise PublisherAdmissionRefused("A24_INVALID_ED25519_SIGNATURE") from exc


def _parse_envelope(raw: bytes) -> tuple[dict, bytes, bytes, str]:
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise PublisherAdmissionRefused("A24_SMALL_SIGNED_METADATA_ONLY")
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             PublisherAdmissionRefused("A24_NONFINITE")))
    except (UnicodeError, ValueError) as exc:
        raise PublisherAdmissionRefused("A24_INVALID_ENVELOPE") from exc
    if type(obj) is not dict or set(obj) != _ENVELOPE_FIELDS:
        raise PublisherAdmissionRefused("A24_EXACT_ENVELOPE_FIELDS")
    claim = obj["claim"]
    if type(claim) is not dict or set(claim) != _CLAIM_FIELDS:
        raise PublisherAdmissionRefused("A24_EXACT_CLAIM_FIELDS")
    if canonical(obj) != raw:
        raise PublisherAdmissionRefused("A24_CANONICAL_BYTES_REQUIRED")
    if (type(claim["schema_version"]) is not int or claim["schema_version"] != 1
            or claim["kind"] != "public_custom_paper_metadata"
            or claim["permissions"] != ["paper_analysis"]
            or claim["artifact_policy"] != "no_executable_or_ciphertext"
            or claim["execution_kind"] != "fixed_a23_data_relay_only"
            or claim["runtime_mode"] != "ephemeral_ci_paper"):
        raise PublisherAdmissionRefused("A24_PUBLIC_PAPER_METADATA_ONLY")
    if (type(claim["engine_id"]) is not str or
            not _KEY_ID.fullmatch(claim["engine_id"])
            or type(claim["publisher"]) is not str
            or not _PUBLISHER.fullmatch(claim["publisher"])
            or type(claim["publisher_key_id"]) is not str
            or not _KEY_ID.fullmatch(claim["publisher_key_id"])
            or type(claim["installation_id"]) is not str
            or not _INSTALL.fullmatch(claim["installation_id"])
            or type(claim["descriptor_sha256"]) is not str
            or not _SHA.fullmatch(claim["descriptor_sha256"])):
        raise PublisherAdmissionRefused("A24_INVALID_IDENTITIES_OR_PIN")
    if (type(claim["sequence"]) is not int
            or not 1 <= claim["sequence"] <= 2**63 - 1
            or type(claim["issued_at"]) is not int
            or type(claim["expires_at"]) is not int
            or claim["issued_at"] < 1
            or not 0 < claim["expires_at"] - claim["issued_at"] <= 86400):
        raise PublisherAdmissionRefused("A24_INVALID_TIME_OR_SEQUENCE")
    pub = _signature(obj["publisher_signature_b64"])
    op = _signature(obj["operator_signature_b64"])
    return claim, pub, op, hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionReceipt:
    installation_id: str
    engine_id: str
    sequence: int
    descriptor_sha256: str
    revision: int
    state: str = "SIGNED_METADATA_ADMITTED_NO_INSTALL"
    executable_installed: bool = False
    private_engine_loaded: bool = False
    live_trading_permitted: bool = False
    commercial_license_issued: bool = False


class PublisherAdmissionAuthority:
    """Temp-local independent operator trust ledger, NOT production PKI.

    Operator public key is independently pinned on initialization. Publisher
    trust is explicitly pinned separately and is never obtained from incoming
    signed documents. No private signing keys are stored here.
    """

    def __init__(self, witness: str | Path, *, operator_public_key: bytes,
                 approved_operator_key_sha256: str):
        path = Path(witness)
        temp = Path(tempfile.gettempdir()).resolve()
        if (not path.is_absolute() or path.is_symlink()
                or path.parent.is_symlink() or not path.parent.is_dir()
                or not path.parent.resolve().is_relative_to(temp)
                or path.parent.resolve() == temp
                or (path.exists() and not path.is_file())):
            raise PublisherAdmissionRefused("A24_SEPARATE_DISPOSABLE_TRUST_LEDGER")
        if (type(operator_public_key) is not bytes or len(operator_public_key) != 32
                or type(approved_operator_key_sha256) is not str
                or not _SHA.fullmatch(approved_operator_key_sha256)
                or not hmac.compare_digest(
                    hashlib.sha256(operator_public_key).hexdigest(),
                    approved_operator_key_sha256)):
            raise PublisherAdmissionRefused("A24_INDEPENDENT_OPERATOR_KEY_PIN")
        first = not path.exists()
        self._db = open_sqlite(path)
        if first:
            path.chmod(0o600)
        elif path.stat().st_mode & 0o077:
            self._db.close()
            raise PublisherAdmissionRefused("A24_UNSAFE_TRUST_LEDGER_PERMISSIONS")
        self._db.execute("""CREATE TABLE IF NOT EXISTS a24_operator (
            singleton INTEGER PRIMARY KEY CHECK (singleton=1),
            public_key BLOB NOT NULL)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS a24_publishers (
            publisher TEXT PRIMARY KEY, key_id TEXT NOT NULL,
            public_key BLOB NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
            CHECK(revoked IN (0,1)))""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS a24_admissions (
            installation_id TEXT NOT NULL, engine_id TEXT NOT NULL,
            sequence INTEGER NOT NULL, digest TEXT NOT NULL,
            descriptor_sha256 TEXT NOT NULL, publisher TEXT NOT NULL,
            revision INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
            CHECK(revoked IN (0,1)),
            PRIMARY KEY(installation_id,engine_id))""")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            existing = self._db.execute(
                "SELECT public_key FROM a24_operator WHERE singleton=1").fetchone()
            if existing is None:
                self._db.execute("INSERT INTO a24_operator VALUES(1,?)",
                                 (operator_public_key,))
            elif existing["public_key"] != operator_public_key:
                raise PublisherAdmissionRefused("A24_OPERATOR_PIN_CHANGED")
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            self._db.close()
            raise
        self._operator = operator_public_key

    def close(self):
        self._db.close()

    def register_publisher(self, publisher: str, key_id: str,
                           public_key: bytes, *, approved_key_sha256: str):
        if (type(publisher) is not str or not _PUBLISHER.fullmatch(publisher)
                or type(key_id) is not str or not _KEY_ID.fullmatch(key_id)
                or type(public_key) is not bytes or len(public_key) != 32
                or public_key == self._operator
                or type(approved_key_sha256) is not str
                or not _SHA.fullmatch(approved_key_sha256)
                or not hmac.compare_digest(hashlib.sha256(public_key).hexdigest(),
                                           approved_key_sha256)):
            raise PublisherAdmissionRefused("A24_INDEPENDENT_PUBLISHER_KEY_PIN")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            previous = self._db.execute(
                "SELECT * FROM a24_publishers WHERE publisher=?",
                (publisher,)).fetchone()
            if previous is None:
                self._db.execute(
                    "INSERT INTO a24_publishers(publisher,key_id,public_key) VALUES(?,?,?)",
                    (publisher, key_id, public_key))
            elif (previous["key_id"] != key_id
                  or previous["public_key"] != public_key
                  or previous["revoked"]):
                raise PublisherAdmissionRefused("A24_PUBLISHER_LOCKED_OR_REVOKED")
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def revoke_publisher(self, publisher: str) -> None:
        result = self._db.execute(
            "UPDATE a24_publishers SET revoked=1 WHERE publisher=?", (publisher,))
        if result.rowcount != 1:
            raise PublisherAdmissionRefused("A24_UNKNOWN_PUBLISHER")

    def revoke_installation(self, installation_id: str, engine_id: str) -> None:
        result = self._db.execute(
            "UPDATE a24_admissions SET revoked=1 WHERE installation_id=? AND engine_id=?",
            (installation_id, engine_id))
        if result.rowcount != 1:
            raise PublisherAdmissionRefused("A24_UNKNOWN_INSTALLATION")

    def _verify(self, raw: bytes, *, catalog: CustomContractCatalog,
                contract: CustomEngineContract, installation_id: str,
                now: int) -> tuple[dict, str]:
        claim, publisher_signature, operator_signature, digest = _parse_envelope(raw)
        if (type(catalog) is not CustomContractCatalog
                or type(contract) is not CustomEngineContract
                or contract.access_policy != "public_custom"
                or contract.strategy_family != "generic_custom"
                or contract.protected_owner_core
                or not contract.publicly_discoverable
                or catalog.public_lookup(contract.engine_id) is None
                or contract not in catalog.owner_inventory()):
            raise PublisherAdmissionRefused("A24_OWNER_PRIVATE_AND_UNKNOWN_DENIED")
        if (type(installation_id) is not str
                or claim["installation_id"] != installation_id
                or claim["engine_id"] != contract.engine_id
                or claim["engine_version"] != contract.engine_version
                or claim["publisher"] != contract.publisher
                or not hmac.compare_digest(claim["descriptor_sha256"],
                                           contract.approved_descriptor_sha256)):
            raise PublisherAdmissionRefused("A24_INSTALLATION_OR_CONTRACT_MISMATCH")
        if (type(now) is not int or not
                claim["issued_at"] <= now < claim["expires_at"]):
            raise PublisherAdmissionRefused("A24_EXPIRED_OR_NOT_YET_VALID")
        key = self._db.execute(
            "SELECT * FROM a24_publishers WHERE publisher=?",
            (contract.publisher,)).fetchone()
        if key is None or key["revoked"] or key["key_id"] != claim["publisher_key_id"]:
            raise PublisherAdmissionRefused("A24_UNTRUSTED_OR_REVOKED_PUBLISHER")
        _ed25519(key["public_key"], publisher_signature,
                 PUBLISHER_DOMAIN + canonical(claim))
        _ed25519(self._operator, operator_signature, OPERATOR_DOMAIN
                 + canonical({"claim": claim,
                              "publisher_signature_b64":
                              base64.b64encode(publisher_signature).decode("ascii")}))
        return claim, digest

    def admit(self, raw: bytes, *, catalog: CustomContractCatalog,
              contract: CustomEngineContract, installation_id: str,
              now: int) -> AdmissionReceipt:
        claim, digest = self._verify(raw, catalog=catalog, contract=contract,
                                     installation_id=installation_id, now=now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            prev = self._db.execute(
                "SELECT * FROM a24_admissions WHERE installation_id=? AND engine_id=?",
                (installation_id, contract.engine_id)).fetchone()
            if prev is not None and (prev["revoked"] or
                                     claim["sequence"] <= prev["sequence"]):
                raise PublisherAdmissionRefused("A24_REVOKED_OR_REPLAY_SEQUENCE")
            revision = 1 if prev is None else prev["revision"] + 1
            self._db.execute("""INSERT INTO a24_admissions
                (installation_id,engine_id,sequence,digest,descriptor_sha256,
                 publisher,revision,revoked) VALUES(?,?,?,?,?,?,?,0)
                ON CONFLICT(installation_id,engine_id) DO UPDATE SET
                sequence=excluded.sequence,digest=excluded.digest,
                descriptor_sha256=excluded.descriptor_sha256,
                publisher=excluded.publisher,revision=excluded.revision,revoked=0""",
                (installation_id, contract.engine_id, claim["sequence"], digest,
                 contract.approved_descriptor_sha256, contract.publisher, revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return AdmissionReceipt(installation_id, contract.engine_id,
                                claim["sequence"],
                                contract.approved_descriptor_sha256, revision)

    def current(self, raw: bytes, *, catalog: CustomContractCatalog,
                contract: CustomEngineContract, installation_id: str,
                now: int) -> AdmissionReceipt:
        claim, digest = self._verify(raw, catalog=catalog, contract=contract,
                                     installation_id=installation_id, now=now)
        row = self._db.execute(
            "SELECT * FROM a24_admissions WHERE installation_id=? AND engine_id=?",
            (installation_id, contract.engine_id)).fetchone()
        if (row is None or row["revoked"] or
                row["sequence"] != claim["sequence"] or
                not hmac.compare_digest(row["digest"], digest) or
                not hmac.compare_digest(row["descriptor_sha256"],
                                       contract.approved_descriptor_sha256) or
                row["publisher"] != contract.publisher):
            raise PublisherAdmissionRefused("A24_NOT_ADMITTED_OR_STALE_PROOF")
        return AdmissionReceipt(installation_id, contract.engine_id,
                                row["sequence"], row["descriptor_sha256"],
                                row["revision"])


class AdmittedFixedCustomSession:
    """Optional A24-gated A23 fixed sandbox, no generic plugin installer.

    Existing A23 remains a separate earlier-stage development fixture.
    This wrapper is the A24 admission-controlled integration path.
    """

    def __init__(self, authority: PublisherAdmissionAuthority, *,
                 catalog: CustomContractCatalog, contract: CustomEngineContract,
                 sandbox: FixedCustomSandbox, installation_id: str,
                 signed_admission: bytes):
        if (type(authority) is not PublisherAdmissionAuthority
                or type(sandbox) is not FixedCustomSandbox
                or sandbox._contract != contract
                or sandbox._catalog is not catalog
                or type(signed_admission) is not bytes):
            raise PublisherAdmissionRefused("A24_EXACT_FIXED_SANDBOX_REQUIRED")
        self.authority = authority
        self.catalog = catalog
        self.contract = contract
        self.sandbox = sandbox
        self.installation_id = installation_id
        self.signed_admission = signed_admission

    def _check(self, now: int) -> AdmissionReceipt:
        try:
            return self.authority.current(
                self.signed_admission, catalog=self.catalog,
                contract=self.contract, installation_id=self.installation_id,
                now=now)
        except PublisherAdmissionRefused:
            # Revoked/expired signed admission stops the owned fixed relay.
            if self.sandbox.status().state == "RUNNING":
                self.sandbox.stop()
            raise

    def launch(self, *, now: int):
        self._check(now)
        return self.sandbox.launch(
            approved_sha256=self.contract.approved_descriptor_sha256)

    def heartbeat(self, *, now: int):
        self._check(now)
        return self.sandbox.heartbeat()

    async def dispatch(self, bridge: CustomPaperRuntimeBridge, packet: bytes,
                       *, tick, expected_revision: int, now: int):
        self._check(now)
        # A23 relays exact A7 bytes in a fixed nonroot seccomp child;
        # re-verify admission immediately after the asynchronous relay.
        transmitted = await asyncio.to_thread(self.sandbox.relay, packet, tick=tick)
        self._check(now)
        return await bridge.dispatch(
            tick, packets={self.contract.engine_id: transmitted},
            expected_revisions={self.contract.engine_id: expected_revision},
            now=tick.occurred_at)

    def stop(self):
        return self.sandbox.stop()
