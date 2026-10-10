"""A25 public Custom inert-package supply-chain admission — NON-PRODUCTION.

Only an exact, data-only, uncompressed synthetic ZIP fixture is accepted.
Distinct A25 domain-separated publisher + installation-operator Ed25519
signatures bind the artifact to CURRENT A24 admission and A21 metadata.
No package extraction, imports, code execution, install or private core.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .a21_custom_contract import CustomContractCatalog, CustomEngineContract
from .a24_publisher_admission import (
    AdmittedFixedCustomSession, PublisherAdmissionAuthority,
    PublisherAdmissionRefused, _ed25519, _parse_envelope, _signature, canonical,
)
from .delivery_ledger import open_sqlite

PUBLISHER_DOMAIN = b"MMT-A25-INERT-BUNDLE-PUBLISHER-V1\x00"
OPERATOR_DOMAIN = b"MMT-A25-INERT-BUNDLE-OPERATOR-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BUNDLE = 16384
_FILES = frozenset({"manifest.json", "payload.json"})
_MANIFEST = frozenset({
    "schema_version", "kind", "engine_id", "engine_version",
    "publisher", "descriptor_sha256", "package_version",
    "payload_sha256", "abi_version", "artifact_policy", "distribution",
})
_PAYLOAD = frozenset({"schema_version", "kind", "engine_id",
                      "engine_version", "behavior"})
_CLAIM = frozenset({
    "schema_version", "kind", "engine_id", "engine_version",
    "publisher", "publisher_key_id", "installation_id",
    "descriptor_sha256", "admission_sha256", "bundle_sha256",
    "payload_sha256", "package_version", "bundle_sequence",
    "issued_at", "expires_at", "capabilities", "artifact_policy",
})
_ENVELOPE = frozenset({"claim", "publisher_signature_b64",
                       "operator_signature_b64"})


class BundleAdmissionRefused(PublisherAdmissionRefused):
    """Inert artifact or package authorization failed closed."""


def _unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise BundleAdmissionRefused("A25_DUPLICATE_JSON_FIELD")
        data[key] = value
    return data


def _exact_json(raw: bytes, fields: frozenset[str], max_size: int) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= max_size:
        raise BundleAdmissionRefused("A25_BOUNDED_JSON_REQUIRED")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               BundleAdmissionRefused("A25_NONFINITE_JSON")))
    except BundleAdmissionRefused:
        raise
    except (UnicodeError, ValueError) as exc:
        raise BundleAdmissionRefused("A25_INVALID_JSON") from exc
    if type(value) is not dict or set(value) != fields:
        raise BundleAdmissionRefused("A25_EXACT_DATA_FIELDS_REQUIRED")
    if raw != canonical(value):
        raise BundleAdmissionRefused("A25_CANONICAL_DATA_REQUIRED")
    return value


@dataclass(frozen=True, slots=True)
class InertBundleProof:
    engine_id: str
    package_version: str
    bundle_sha256: str
    payload_sha256: str
    safe_data_only: bool = True
    encrypted_payload: bool = False
    executable_payload: bool = False
    private_nyfr_included: bool = False


@dataclass(frozen=True, slots=True)
class BundleAdmissionReceipt:
    installation_id: str
    engine_id: str
    bundle_sequence: int
    bundle_sha256: str
    descriptor_sha256: str
    revision: int
    state: str = "SIGNED_INERT_BUNDLE_ADMITTED_NO_INSTALL"
    executable_installed: bool = False
    strategy_code_executed: bool = False
    live_trading_permitted: bool = False
    private_nyfr_included: bool = False


def inspect_inert_bundle(data: bytes, *, approved_sha256: str,
                         contract: CustomEngineContract) -> InertBundleProof:
    """No extraction ever. Reject all executable/ciphertext and ZIP ambiguity."""
    if (type(contract) is not CustomEngineContract
            or contract.access_policy != "public_custom"
            or contract.strategy_family != "generic_custom"
            or contract.protected_owner_core):
        raise BundleAdmissionRefused("A25_PRIVATE_AND_OWNER_BUNDLES_DENIED")
    if (type(data) is not bytes or not 0 < len(data) <= _MAX_BUNDLE
            or type(approved_sha256) is not str
            or not _SHA.fullmatch(approved_sha256)
            or not hmac.compare_digest(hashlib.sha256(data).hexdigest(),
                                       approved_sha256)):
        raise BundleAdmissionRefused("A25_INDEPENDENT_BUNDLE_PIN_REQUIRED")
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            entries = archive.infolist()
            if (len(entries) != 2 or {entry.filename for entry in entries} != _FILES
                    or archive.comment or len({x.filename for x in entries}) != 2):
                raise BundleAdmissionRefused("A25_EXACT_TWO_INERT_MEMBERS")
            for entry in entries:
                mode = entry.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if (entry.filename not in _FILES or entry.is_dir()
                        or entry.flag_bits != 0 or entry.extra or entry.comment
                        or entry.compress_type != zipfile.ZIP_STORED
                        or entry.file_size <= 0 or entry.file_size > 4096
                        or entry.compress_size != entry.file_size
                        or kind not in (0, stat.S_IFREG)
                        or mode & 0o111):
                    raise BundleAdmissionRefused("A25_UNSAFE_ZIP_ENTRY_OR_MODE")
            manifest_data = archive.read("manifest.json")
            payload_data = archive.read("payload.json")
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError) as exc:
        raise BundleAdmissionRefused("A25_MALFORMED_OR_TAMPERED_ZIP") from exc
    manifest = _exact_json(manifest_data, _MANIFEST, 4096)
    payload = _exact_json(payload_data, _PAYLOAD, 4096)
    if (type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or manifest["kind"] != "public_custom_inert_bundle"
            or manifest["engine_id"] != contract.engine_id
            or manifest["engine_version"] != contract.engine_version
            or manifest["publisher"] != contract.publisher
            or manifest["descriptor_sha256"] != contract.approved_descriptor_sha256
            or manifest["package_version"] != contract.engine_version
            or type(manifest["abi_version"]) is not int
            or manifest["abi_version"] != 1
            or manifest["artifact_policy"] != "data_only_no_executable_or_ciphertext"
            or manifest["distribution"] != "ephemeral_ci_rehearsal"
            or type(manifest["payload_sha256"]) is not str
            or not _SHA.fullmatch(manifest["payload_sha256"])
            or not hmac.compare_digest(hashlib.sha256(payload_data).hexdigest(),
                                       manifest["payload_sha256"])):
        raise BundleAdmissionRefused("A25_MANIFEST_CONTRACT_OR_PAYLOAD_MISMATCH")
    if (type(payload["schema_version"]) is not int
            or payload["schema_version"] != 1
            or payload["kind"] != "synthetic_no_signal_data"
            or payload["engine_id"] != contract.engine_id
            or payload["engine_version"] != contract.engine_version
            or payload["behavior"] != "no_signal"):
        raise BundleAdmissionRefused("A25_NO_EXECUTABLE_CONTENT_ALLOWED")
    return InertBundleProof(contract.engine_id, contract.engine_version,
                            approved_sha256, manifest["payload_sha256"])


def _parse_signed_bundle(raw: bytes) -> tuple[dict, bytes, bytes, str]:
    envelope = _exact_json(raw, _ENVELOPE, 4096)
    claim = envelope["claim"]
    if type(claim) is not dict or set(claim) != _CLAIM:
        raise BundleAdmissionRefused("A25_EXACT_SIGNED_CLAIM_REQUIRED")
    if (type(claim["schema_version"]) is not int or claim["schema_version"] != 1
            or claim["kind"] != "public_custom_inert_bundle"
            or claim["capabilities"] != ["inert_paper_data_only"]
            or claim["artifact_policy"] != "no_executable_or_ciphertext"
            or type(claim["bundle_sequence"]) is not int
            or not 1 <= claim["bundle_sequence"] <= 2**63 - 1
            or type(claim["issued_at"]) is not int
            or type(claim["expires_at"]) is not int
            or claim["issued_at"] < 1
            or not 0 < claim["expires_at"]-claim["issued_at"] <= 86400):
        raise BundleAdmissionRefused("A25_SIGNED_INERT_POLICY_REQUIRED")
    for key in ("descriptor_sha256", "admission_sha256",
                "bundle_sha256", "payload_sha256"):
        if type(claim[key]) is not str or not _SHA.fullmatch(claim[key]):
            raise BundleAdmissionRefused("A25_INVALID_SIGNED_DIGEST")
    for key in ("engine_id", "engine_version", "publisher",
                "publisher_key_id", "installation_id", "package_version"):
        if type(claim[key]) is not str or not 1 <= len(claim[key]) <= 80:
            raise BundleAdmissionRefused("A25_INVALID_CLAIM_IDENTITY")
    return (claim, _signature(envelope["publisher_signature_b64"]),
            _signature(envelope["operator_signature_b64"]),
            hashlib.sha256(raw).hexdigest())


class InertBundleAdmissionGate:
    """Local independent package sequence witness; no extraction or execution."""

    def __init__(self, witness: str | Path, *,
                 authority: PublisherAdmissionAuthority):
        if type(authority) is not PublisherAdmissionAuthority:
            raise BundleAdmissionRefused("A25_INDEPENDENT_A24_AUTHORITY_REQUIRED")
        path = Path(witness)
        temp = Path(tempfile.gettempdir()).resolve()
        if (not path.is_absolute() or path.is_symlink()
                or path.parent.is_symlink() or not path.parent.is_dir()
                or path.parent.resolve() == temp
                or not path.parent.resolve().is_relative_to(temp)
                or (path.exists() and not path.is_file())):
            raise BundleAdmissionRefused("A25_DISPOSABLE_INDEPENDENT_WITNESS_ONLY")
        first = not path.exists()
        self._db = open_sqlite(path)
        if first:
            path.chmod(0o600)
        elif path.stat().st_mode & 0o077:
            self._db.close()
            raise BundleAdmissionRefused("A25_UNSAFE_WITNESS_FILE")
        self._authority = authority
        self._db.execute("""CREATE TABLE IF NOT EXISTS a25_floors(
            installation_id TEXT NOT NULL, engine_id TEXT NOT NULL,
            sequence INTEGER NOT NULL, release_sha256 TEXT NOT NULL,
            bundle_sha256 TEXT NOT NULL, descriptor_sha256 TEXT NOT NULL,
            revision INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
              CHECK(revoked IN (0,1)),
            PRIMARY KEY(installation_id, engine_id))""")

    def close(self):
        self._db.close()

    def revoke(self, installation_id: str, engine_id: str) -> None:
        row = self._db.execute(
            "UPDATE a25_floors SET revoked=1 WHERE installation_id=? AND engine_id=?",
            (installation_id, engine_id))
        if row.rowcount != 1:
            raise BundleAdmissionRefused("A25_UNKNOWN_ADMISSION")

    def _check(self, *, package: bytes, release: bytes, a24_envelope: bytes,
               catalog: CustomContractCatalog, contract: CustomEngineContract,
               installation_id: str, now: int) -> tuple[dict, str, InertBundleProof]:
        # First authenticate CURRENT A24 license/installation/issuer revocation.
        current = self._authority.current(
            a24_envelope, catalog=catalog, contract=contract,
            installation_id=installation_id, now=now)
        claim, pub_sig, op_sig, release_digest = _parse_signed_bundle(release)
        archive = inspect_inert_bundle(package, approved_sha256=claim["bundle_sha256"],
                                       contract=contract)
        a24_claim, _, _, _ = _parse_envelope(a24_envelope)
        if (claim["engine_id"] != contract.engine_id
                or claim["engine_version"] != contract.engine_version
                or claim["publisher"] != contract.publisher
                or claim["publisher_key_id"] != a24_claim["publisher_key_id"]
                or claim["installation_id"] != current.installation_id
                or claim["descriptor_sha256"] != current.descriptor_sha256
                or claim["package_version"] != archive.package_version
                or claim["payload_sha256"] != archive.payload_sha256
                or not hmac.compare_digest(
                    claim["admission_sha256"], hashlib.sha256(a24_envelope).hexdigest())):
            raise BundleAdmissionRefused("A25_BINDING_OR_SIGNED_DIGEST_MISMATCH")
        if type(now) is not int or not claim["issued_at"] <= now < claim["expires_at"]:
            raise BundleAdmissionRefused("A25_EXPIRED_OR_FUTURE_RELEASE")
        key = self._authority._db.execute(
            "SELECT * FROM a24_publishers WHERE publisher=?",
            (contract.publisher,)).fetchone()
        if (key is None or key["revoked"]
                or key["key_id"] != claim["publisher_key_id"]):
            raise BundleAdmissionRefused("A25_REVOKED_OR_UNKNOWN_PUBLISHER")
        _ed25519(key["public_key"], pub_sig, PUBLISHER_DOMAIN + canonical(claim))
        _ed25519(self._authority._operator, op_sig, OPERATOR_DOMAIN
                 + canonical({"claim": claim, "publisher_signature_b64":
                              base64.b64encode(pub_sig).decode("ascii")}))
        return claim, release_digest, archive

    def admit(self, *, package: bytes, release: bytes, a24_envelope: bytes,
              catalog: CustomContractCatalog, contract: CustomEngineContract,
              installation_id: str, now: int) -> BundleAdmissionReceipt:
        claim, digest, _ = self._check(
            package=package, release=release, a24_envelope=a24_envelope,
            catalog=catalog, contract=contract,
            installation_id=installation_id, now=now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            old = self._db.execute(
                "SELECT * FROM a25_floors WHERE installation_id=? AND engine_id=?",
                (installation_id, contract.engine_id)).fetchone()
            if old is not None and (old["revoked"] or
                                   claim["bundle_sequence"] <= old["sequence"]):
                raise BundleAdmissionRefused("A25_ROLLBACK_OR_REVOKED")
            revision = 1 if old is None else old["revision"] + 1
            self._db.execute("""INSERT INTO a25_floors
                (installation_id,engine_id,sequence,release_sha256,bundle_sha256,
                 descriptor_sha256,revision,revoked) VALUES(?,?,?,?,?,?,?,0)
                ON CONFLICT(installation_id,engine_id) DO UPDATE SET
                sequence=excluded.sequence, release_sha256=excluded.release_sha256,
                bundle_sha256=excluded.bundle_sha256,
                descriptor_sha256=excluded.descriptor_sha256,
                revision=excluded.revision, revoked=0""",
                (installation_id, contract.engine_id, claim["bundle_sequence"],
                 digest, claim["bundle_sha256"], contract.approved_descriptor_sha256,
                 revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return BundleAdmissionReceipt(installation_id, contract.engine_id,
                                      claim["bundle_sequence"],
                                      claim["bundle_sha256"],
                                      contract.approved_descriptor_sha256, revision)

    def current(self, *, package: bytes, release: bytes, a24_envelope: bytes,
                catalog: CustomContractCatalog, contract: CustomEngineContract,
                installation_id: str, now: int) -> BundleAdmissionReceipt:
        claim, digest, _ = self._check(
            package=package, release=release, a24_envelope=a24_envelope,
            catalog=catalog, contract=contract,
            installation_id=installation_id, now=now)
        row = self._db.execute(
            "SELECT * FROM a25_floors WHERE installation_id=? AND engine_id=?",
            (installation_id, contract.engine_id)).fetchone()
        if (row is None or row["revoked"] or row["sequence"] != claim["bundle_sequence"]
                or not hmac.compare_digest(row["release_sha256"], digest)
                or not hmac.compare_digest(row["bundle_sha256"], claim["bundle_sha256"])
                or not hmac.compare_digest(row["descriptor_sha256"],
                                           contract.approved_descriptor_sha256)):
            raise BundleAdmissionRefused("A25_UNADMITTED_OR_SUPERSEDED")
        return BundleAdmissionReceipt(installation_id, contract.engine_id,
                                      row["sequence"], row["bundle_sha256"],
                                      row["descriptor_sha256"], row["revision"])


class A25GuardedFixedFixture:
    """A24+A25 signed proof gates the *fixed* A23 mock, never a package binary."""

    def __init__(self, session: AdmittedFixedCustomSession, *,
                 gate: InertBundleAdmissionGate, package: bytes, release: bytes,
                 a24_envelope: bytes):
        if (type(session) is not AdmittedFixedCustomSession
                or type(gate) is not InertBundleAdmissionGate
                or gate._authority is not session.authority
                or type(package) is not bytes or type(release) is not bytes
                or type(a24_envelope) is not bytes
                or a24_envelope != session.signed_admission):
            raise BundleAdmissionRefused("A25_FIXED_SIGNED_SESSION_ONLY")
        self.session = session
        self.gate = gate
        self.package = package
        self.release = release
        self.a24_envelope = a24_envelope

    def _check(self, now: int) -> BundleAdmissionReceipt:
        try:
            return self.gate.current(
                package=self.package, release=self.release,
                a24_envelope=self.a24_envelope, catalog=self.session.catalog,
                contract=self.session.contract,
                installation_id=self.session.installation_id, now=now)
        except PublisherAdmissionRefused:
            if self.session.sandbox.status().state == "RUNNING":
                self.session.stop()
            raise

    def launch(self, *, now: int):
        self._check(now)
        return self.session.launch(now=now)

    def heartbeat(self, *, now: int):
        self._check(now)
        return self.session.heartbeat(now=now)

    async def dispatch(self, bridge, packet: bytes, *, tick,
                       expected_revision: int, now: int):
        self._check(now)
        # A24 itself checks twice; A25 rechecks after its awaited call too.
        result = await self.session.dispatch(
            bridge, packet, tick=tick, expected_revision=expected_revision, now=now)
        self._check(now)
        return result

    def stop(self):
        return self.session.stop()
