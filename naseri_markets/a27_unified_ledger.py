"""A27 NON-PRODUCTION: one-file SQLite authorization + PAPER journal.

An explicitly cut-over A27 ledger serializes its own revocations, grant
generations and PAPER records with ONE database's BEGIN IMMEDIATE / COMMIT.
SQLite DELETE journal + FULL synchronous for single-file crash consistency.
Old A24/A25 authorities are input provenance proofs, not parallel runtime
writers; their independent later revocations are NOT automatically fenced.
No public private-engine transport, arbitrary code, broker or live trading.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .a21_custom_contract import CustomContractCatalog, CustomEngineContract
from .a22_custom_bridge import CustomPaperRuntimeBridge, CustomRuntimeRefused
from .a23_sandbox_adapter import FixedCustomSandbox
from .a24_publisher_admission import PublisherAdmissionAuthority
from .a25_bundle_admission import InertBundleAdmissionGate
from .contracts import EvidenceMode, SignalIntent
from .delivery_ledger import IdentityConflict, _wire_intent
from .paper_journal import JournalCounts, PaperJournal


class RecoveryFenceRefused(CustomRuntimeRefused):
    """A27 single-ledger admission, recovery or publication denied."""


@dataclass(frozen=True, slots=True)
class RecoveryReceipt:
    installation_id: str
    engine_id: str
    generation: int
    admission_sequence: int
    release_sequence: int
    state: str
    armed_this_process: bool
    single_file_commit: bool = True
    off_host_rollback_protected: bool = False
    live_trading_permitted: bool = False
    private_engine_installed: bool = False


class UnifiedAuthorizationLedger:
    """Local, owner-managed cutover; no simultaneous A24/A25 runtime writers.

    A24/A25 are verified once at import and each explicit process recovery.
    During A27 service life, revocation MUST use revoke() on this ledger;
    legacy A24/A25 mutation is not coordinated after cutover. This is an
    explicit, isolated nonproduction proof-of-architecture.
    """

    def __init__(self, path: str | Path, *, catalog: CustomContractCatalog,
                 contract: CustomEngineContract, installation_id: str,
                 authority: PublisherAdmissionAuthority,
                 gate: InertBundleAdmissionGate, a24_envelope: bytes,
                 release: bytes, package: bytes, now: int):
        if (type(catalog) is not CustomContractCatalog
                or type(contract) is not CustomEngineContract
                or contract.access_policy != "public_custom"
                or contract.strategy_family != "generic_custom"
                or contract.protected_owner_core
                or catalog.public_lookup(contract.engine_id) is None
                or contract not in catalog.owner_inventory()
                or type(authority) is not PublisherAdmissionAuthority
                or type(gate) is not InertBundleAdmissionGate
                or gate._authority is not authority
                or type(installation_id) is not str
                or type(a24_envelope) is not bytes
                or type(release) is not bytes or type(package) is not bytes):
            raise RecoveryFenceRefused("A27_EXACT_SIGNED_PUBLIC_GENERIC_CONTEXT")
        self.catalog = catalog
        self.contract = contract
        self.installation_id = installation_id
        self.authority = authority
        self.gate = gate
        self.a24_envelope = a24_envelope
        self.release = release
        self.package = package
        self._auth = self._verify_legacy(now)
        path = Path(path)
        tmp = Path(tempfile.gettempdir()).resolve()
        if (not path.is_absolute() or path.is_symlink() or not path.parent.is_dir()
                or path.parent.is_symlink() or path.parent.resolve() == tmp
                or not path.parent.resolve().is_relative_to(tmp)
                or (path.exists() and not path.is_file())):
            raise RecoveryFenceRefused("A27_DISPOSABLE_SINGLE_FILE_ONLY")
        self._path = path
        existed = path.exists()
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._armed_generation: int | None = None
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.execute("PRAGMA foreign_keys=ON")
            if self._db.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                raise RecoveryFenceRefused("A27_ROLLBACK_JOURNAL_REQUIRED")
            self._db.execute("PRAGMA synchronous=FULL")
            if self._db.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise RecoveryFenceRefused("A27_FULL_SYNC_REQUIRED")
            if self._db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RecoveryFenceRefused("A27_CORRUPT_LEDGER")
            if existed:
                if path.stat().st_mode & 0o077:
                    raise RecoveryFenceRefused("A27_UNSAFE_FILE_PERMISSIONS")
            else:
                path.chmod(0o600)
            self._db.execute("""CREATE TABLE IF NOT EXISTS a27_grant (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                installation_id TEXT NOT NULL, engine_id TEXT NOT NULL,
                descriptor_sha256 TEXT NOT NULL,
                a24_sha256 TEXT NOT NULL, a25_sha256 TEXT NOT NULL,
                a24_sequence INTEGER NOT NULL, a25_sequence INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                generation INTEGER NOT NULL CHECK(generation>0),
                state TEXT NOT NULL CHECK(state IN ('SEALED','ACTIVE','REVOKED'))
            )""")
            self._db.execute("""CREATE TABLE IF NOT EXISTS a27_paper_intents (
                engine_id TEXT NOT NULL, signal_id TEXT NOT NULL,
                digest TEXT NOT NULL, payload TEXT NOT NULL,
                generation INTEGER NOT NULL, PRIMARY KEY(engine_id,signal_id)
            )""")
            self._db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._db.execute(
                    "SELECT * FROM a27_grant WHERE singleton=1").fetchone()
                if previous is None:
                    self._db.execute(
                        "INSERT INTO a27_grant VALUES (1,?,?,?,?,?,?,?,?,?,'SEALED')",
                        (installation_id, contract.engine_id,
                         contract.approved_descriptor_sha256,
                         hashlib.sha256(a24_envelope).hexdigest(),
                         hashlib.sha256(release).hexdigest(),
                         self._auth[0], self._auth[1], self._auth[2], 1))
                else:
                    if not self._matches(previous):
                        raise RecoveryFenceRefused("A27_EXISTING_GRANT_IDENTITY_CHANGED")
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except BaseException:
            self._db.close()
            raise

    def _verify_legacy(self, now: int) -> tuple[int, int, int]:
        if type(now) is not int:
            raise RecoveryFenceRefused("A27_TRUSTED_TEST_CLOCK_REQUIRED")
        a24 = self.authority.current(
            self.a24_envelope, catalog=self.catalog,
            contract=self.contract, installation_id=self.installation_id, now=now)
        a25 = self.gate.current(
            package=self.package, release=self.release,
            a24_envelope=self.a24_envelope, catalog=self.catalog,
            contract=self.contract, installation_id=self.installation_id,
            now=now)
        from .a24_publisher_admission import _parse_envelope
        from .a25_bundle_admission import _parse_signed_bundle
        claim24 = _parse_envelope(self.a24_envelope)[0]
        claim25 = _parse_signed_bundle(self.release)[0]
        return (a24.sequence, a25.bundle_sequence,
                min(claim24["expires_at"], claim25["expires_at"]))

    def _matches(self, row) -> bool:
        return (row["installation_id"] == self.installation_id
                and row["engine_id"] == self.contract.engine_id
                and hmac.compare_digest(
                    row["descriptor_sha256"], self.contract.approved_descriptor_sha256)
                and hmac.compare_digest(
                    row["a24_sha256"], hashlib.sha256(self.a24_envelope).hexdigest())
                and hmac.compare_digest(
                    row["a25_sha256"], hashlib.sha256(self.release).hexdigest())
                and row["a24_sequence"] == self._auth[0]
                and row["a25_sequence"] == self._auth[1]
                and row["expires_at"] == self._auth[2])

    def receipt(self) -> RecoveryReceipt:
        row = self._db.execute("SELECT * FROM a27_grant WHERE singleton=1").fetchone()
        if row is None or not self._matches(row):
            raise RecoveryFenceRefused("A27_MISSING_OR_TAMPERED_GRANT")
        return RecoveryReceipt(
            self.installation_id, self.contract.engine_id,
            row["generation"], row["a24_sequence"], row["a25_sequence"],
            row["state"], self._armed_generation == row["generation"])

    def recover(self, *, now: int, approved_sha256: str,
                expected_generation: int) -> RecoveryReceipt:
        """Explicit fresh cutover/recovery; never implicitly adopt a prior run."""
        if (type(approved_sha256) is not str
                or not hmac.compare_digest(approved_sha256,
                                          self.contract.approved_descriptor_sha256)
                or type(expected_generation) is not int):
            raise RecoveryFenceRefused("A27_OPERATOR_PIN_AND_CAS_REQUIRED")
        self._verify_legacy(now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM a27_grant WHERE singleton=1").fetchone()
            if (row is None or not self._matches(row)
                    or row["state"] == "REVOKED"
                    or row["generation"] != expected_generation
                    or now >= row["expires_at"]):
                raise RecoveryFenceRefused("A27_RECOVERY_REVOKED_OR_STALE")
            # Recovery always rotates generation, including after clean exit.
            generation = row["generation"] + 1
            self._db.execute(
                "UPDATE a27_grant SET state='ACTIVE',generation=? WHERE singleton=1",
                (generation,))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._armed_generation = generation
        return self.receipt()

    def revoke(self) -> RecoveryReceipt:
        """Revocation and subsequent journal commits share ONE SQLite writer."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT generation FROM a27_grant WHERE singleton=1").fetchone()
            if row is None:
                raise RecoveryFenceRefused("A27_NO_GRANT")
            self._db.execute(
                "UPDATE a27_grant SET state='REVOKED',generation=? WHERE singleton=1",
                (row["generation"] + 1,))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._armed_generation = None
        return self.receipt()

    def seal(self) -> RecoveryReceipt:
        """Voluntary stop; persisted ACTIVE becomes SEALED, no automatic resume."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute("SELECT * FROM a27_grant WHERE singleton=1").fetchone()
            if row is None or row["state"] == "REVOKED":
                raise RecoveryFenceRefused("A27_REVOKED_CANNOT_SEAL")
            self._db.execute(
                "UPDATE a27_grant SET state='SEALED',generation=? WHERE singleton=1",
                (row["generation"] + 1,))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._armed_generation = None
        return self.receipt()

    def commit(self, intents: Sequence[SignalIntent], *, now: int,
               bridge: CustomPaperRuntimeBridge,
               expected_generation: int) -> JournalCounts:
        if (type(bridge) is not CustomPaperRuntimeBridge
                or not bridge._require_atomic_fence
                or bridge._atomic_fence_kind != "a27"
                or bridge._contracts.get(self.contract.engine_id) != self.contract
                or not bridge._paper_enabled
                or self._armed_generation is None
                or type(expected_generation) is not int
                or expected_generation != self._armed_generation
                or type(now) is not int
                or type(intents) not in (tuple, list)):
            raise RecoveryFenceRefused("A27_EXACT_ARMED_PAPER_BRIDGE_REQUIRED")
        prepared = []
        for intent in intents:
            if (type(intent) is not SignalIntent
                    or intent.engine_id != self.contract.engine_id
                    or intent.engine_version != self.contract.engine_version
                    or intent.instrument.market not in self.contract.markets
                    or intent.evidence_mode is not EvidenceMode.PAPER):
                raise RecoveryFenceRefused("A27_PUBLIC_PAPER_ONLY")
            payload = _wire_intent(intent)
            prepared.append((intent.engine_id, intent.signal_id,
                             hashlib.sha256(payload.encode()).hexdigest(), payload))
        inserted = duplicate = 0
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM a27_grant WHERE singleton=1").fetchone()
            state = bridge.status(self.contract.engine_id)
            if (row is None or not self._matches(row)
                    or row["state"] != "ACTIVE"
                    or row["generation"] != expected_generation
                    or not state.enabled
                    or state.descriptor_sha256 != self.contract.approved_descriptor_sha256
                    or not bridge._paper_enabled
                    or not 0 < now < row["expires_at"]):
                raise RecoveryFenceRefused("A27_REVOKED_STALE_OR_EXPIRED_AT_COMMIT")
            for engine_id, signal_id, digest, payload in prepared:
                old = self._db.execute(
                    "SELECT digest FROM a27_paper_intents WHERE engine_id=? AND signal_id=?",
                    (engine_id, signal_id)).fetchone()
                if old is not None:
                    if old["digest"] != digest:
                        raise IdentityConflict("A27_PAPER_IDENTITY_CONFLICT")
                    duplicate += 1
                else:
                    self._db.execute(
                        "INSERT INTO a27_paper_intents VALUES(?,?,?,?,?)",
                        (engine_id, signal_id, digest, payload, expected_generation))
                    inserted += 1
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return JournalCounts(inserted, duplicate)

    def count(self) -> int:
        return self._db.execute(
            "SELECT count(*) FROM a27_paper_intents").fetchone()[0]

    def close(self) -> None:
        self._armed_generation = None
        self._db.close()


class UnifiedPaperCommitFence:
    """Exact A27-only adapter for the existing fixed A22 runner."""

    def __init__(self, ledger: UnifiedAuthorizationLedger,
                 bridge: CustomPaperRuntimeBridge):
        if (type(ledger) is not UnifiedAuthorizationLedger
                or type(bridge) is not CustomPaperRuntimeBridge
                or not bridge._require_atomic_fence
                or bridge._atomic_fence_kind != "a27"
                or ledger.catalog is not bridge._catalog
                or ledger.contract != bridge._contracts.get(ledger.contract.engine_id)):
            raise RecoveryFenceRefused("A27_INVALID_FENCED_BRIDGE_BINDING")
        self.ledger = ledger
        self.bridge = bridge
        self.journal: PaperJournal = bridge._journal

    def commit(self, intents: Sequence[SignalIntent], *, now: int) -> JournalCounts:
        receipt = self.ledger.receipt()
        return self.ledger.commit(
            intents, now=now, bridge=self.bridge,
            expected_generation=receipt.generation)


class RecoveredFixedPaperSession:
    """A27 unified grant + A23 fixed scoped relay + A22 PAPER bridge only."""

    def __init__(self, ledger: UnifiedAuthorizationLedger,
                 sandbox: FixedCustomSandbox,
                 bridge: CustomPaperRuntimeBridge):
        if (type(sandbox) is not FixedCustomSandbox
                or sandbox._contract != ledger.contract
                or sandbox._catalog is not ledger.catalog):
            raise RecoveryFenceRefused("A27_FIXED_PUBLIC_SANDBOX_ONLY")
        self.ledger = ledger
        self.sandbox = sandbox
        self.bridge = bridge
        self.fence = UnifiedPaperCommitFence(ledger, bridge)

    def launch(self, *, now: int):
        receipt = self.ledger.receipt()
        if (not receipt.armed_this_process or receipt.state != "ACTIVE"
                or now >= self.ledger._auth[2]):
            raise RecoveryFenceRefused("A27_OPERATOR_RECOVERY_REQUIRED")
        return self.sandbox.launch(
            approved_sha256=self.ledger.contract.approved_descriptor_sha256)

    async def dispatch(self, packet: bytes, *, tick,
                       now: int, expected_revision: int):
        receipt = self.ledger.receipt()
        if not receipt.armed_this_process or receipt.state != "ACTIVE":
            raise RecoveryFenceRefused("A27_NOT_RECOVERED")
        if not self.bridge.status(self.ledger.contract.engine_id).enabled:
            raise RecoveryFenceRefused("A27_ENGINE_DISABLED")
        data = await asyncio.to_thread(self.sandbox.relay, packet, tick=tick)
        if self.ledger.receipt().generation != receipt.generation:
            raise RecoveryFenceRefused("A27_GENERATION_CHANGED_IN_FLIGHT")
        return await self.bridge.dispatch(
            tick, packets={self.ledger.contract.engine_id: data},
            expected_revisions={self.ledger.contract.engine_id: expected_revision},
            now=tick.occurred_at, atomic_fence=self.fence,
            authorization_now=now)

    def stop(self):
        return self.sandbox.stop()
