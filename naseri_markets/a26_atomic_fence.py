"""A26 opt-in, NON-PRODUCTION transactional permission fencing for PAPER.

All protected writes use one SQLite BEGIN IMMEDIATE connection with the A7
journal, A24 trust and A25 bundle ledgers attached. Locks serialize local
revocation/sequence changes and PAPER commits. This is a concurrency
linearization point, NOT cross-file power-loss atomic durability in WAL mode.
No custom source, binary or NY First-Reversal is ever executed or installed.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .a24_publisher_admission import (
    OPERATOR_DOMAIN as AUTH_OPERATOR_DOMAIN,
    PUBLISHER_DOMAIN as AUTH_PUBLISHER_DOMAIN,
    _ed25519, _parse_envelope, canonical,
)
from .a25_bundle_admission import (
    OPERATOR_DOMAIN as BUNDLE_OPERATOR_DOMAIN,
    PUBLISHER_DOMAIN as BUNDLE_PUBLISHER_DOMAIN,
    A25GuardedFixedFixture, _parse_signed_bundle,
)
from .a22_custom_bridge import CustomPaperRuntimeBridge, CustomRuntimeRefused
from .contracts import EvidenceMode, SignalIntent
from .delivery_ledger import IdentityConflict, _wire_intent
from .paper_journal import JournalCounts, PaperJournal


class AtomicFenceRefused(CustomRuntimeRefused):
    """Invalid, revoked, stale, untrusted or uncommittable A26 PAPER intent."""


@dataclass(frozen=True, slots=True)
class AtomicFenceEvidence:
    engine_id: str
    installation_id: str
    journal_writes_protected: bool = True
    sqlite_cross_database_concurrency_fenced: bool = True
    power_failure_cross_database_atomicity_guaranteed: bool = False
    private_engine_installed: bool = False
    live_trading_permitted: bool = False


def _trusted_db_path(connection) -> Path:
    row = connection.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2]:
        raise AtomicFenceRefused("A26_REAL_SQLITE_WITNESS_REQUIRED")
    path = Path(row[2])
    temp = Path(tempfile.gettempdir()).resolve()
    if (not path.is_absolute() or path.is_symlink()
            or not path.is_file() or not path.parent.resolve().is_relative_to(temp)
            or path.parent.resolve() == temp):
        raise AtomicFenceRefused("A26_DISPOSABLE_FILE_BOUNDARY_REQUIRED")
    return path


class AtomicPaperCommitFence:
    """Fixed A24+A25 guarded admission, journal and exact A22 bridge identity.

    ATTACH is done once outside transactions. BEGIN IMMEDIATE takes SQLite
    writer reservations across attached ledgers before final permission checks
    and paper INSERT. Competing SQLite revokes must be serialized.
    """

    def __init__(self, fixture: A25GuardedFixedFixture,
                 bridge: CustomPaperRuntimeBridge):
        if (type(fixture) is not A25GuardedFixedFixture
                or type(bridge) is not CustomPaperRuntimeBridge
                or bridge._require_atomic_fence is not True
                or fixture.session.contract.engine_id not in bridge._contracts
                or bridge._contracts[fixture.session.contract.engine_id]
                != fixture.session.contract
                or fixture.session.catalog is not bridge._catalog
                or fixture.session.sandbox._contract != fixture.session.contract):
            raise AtomicFenceRefused("A26_EXACT_GUARDED_PUBLIC_CUSTOM_BRIDGE_REQUIRED")
        self.fixture = fixture
        self.bridge = bridge
        self.journal: PaperJournal = bridge._journal
        if type(self.journal) is not PaperJournal:
            raise AtomicFenceRefused("A26_EXACT_A7_PAPER_JOURNAL")
        self._db = self.journal._db
        auth = fixture.session.authority
        gate = fixture.gate
        authpath = _trusted_db_path(auth._db)
        gatepath = _trusted_db_path(gate._db)
        journalpath = _trusted_db_path(self._db)
        if len({authpath, gatepath, journalpath}) != 3:
            raise AtomicFenceRefused("A26_DISTINCT_TRUST_AND_JOURNAL_FILES_REQUIRED")
        attached = {row[1]: row[2] for row in self._db.execute(
            "PRAGMA database_list").fetchall()}
        if set(attached) != {"main"}:
            raise AtomicFenceRefused("A26_JOURNAL_CONNECTION_ALREADY_ATTACHED")
        self._db.execute("ATTACH DATABASE ? AS a26_auth", (str(authpath),))
        try:
            self._db.execute("ATTACH DATABASE ? AS a26_bundle", (str(gatepath),))
        except BaseException:
            self._db.execute("DETACH DATABASE a26_auth")
            raise
        observed = {row[1]: Path(row[2]) for row in self._db.execute(
            "PRAGMA database_list").fetchall()}
        if (observed != {"main": journalpath, "a26_auth": authpath,
                         "a26_bundle": gatepath}):
            raise AtomicFenceRefused("A26_FILE_BINDING_CHANGED")
        self._owner_id = fixture.session.contract.engine_id
        self._install_id = fixture.session.installation_id
        self.evidence = AtomicFenceEvidence(self._owner_id, self._install_id)

    def _verify_locked(self, *, now: int, a24_receipt, a25_receipt,
                       auth_claim: dict, bundle_claim: dict,
                       auth_pubsig: bytes, auth_opsig: bytes,
                       bundle_pubsig: bytes, bundle_opsig: bytes) -> None:
        """Call ONLY after BEGIN IMMEDIATE has locked all three SQLite files."""
        db = self._db
        claim = self.fixture.session.contract
        publisher = db.execute(
            "SELECT key_id,public_key,revoked FROM a26_auth.a24_publishers "
            "WHERE publisher=?", (claim.publisher,)).fetchone()
        owner = db.execute(
            "SELECT public_key FROM a26_auth.a24_operator WHERE singleton=1"
        ).fetchone()
        auth = db.execute(
            "SELECT sequence,digest,descriptor_sha256,publisher,revision,revoked "
            "FROM a26_auth.a24_admissions WHERE installation_id=? AND engine_id=?",
            (self._install_id, self._owner_id)).fetchone()
        bundle = db.execute(
            "SELECT sequence,release_sha256,bundle_sha256,descriptor_sha256,"
            "revision,revoked FROM a26_bundle.a25_floors "
            "WHERE installation_id=? AND engine_id=?",
            (self._install_id, self._owner_id)).fetchone()
        if (publisher is None or publisher["revoked"] or owner is None
                or owner["public_key"] != self.fixture.session.authority._operator
                or publisher["key_id"] != auth_claim["publisher_key_id"]
                or publisher["key_id"] != bundle_claim["publisher_key_id"]
                or auth is None or auth["revoked"] or bundle is None
                or bundle["revoked"]):
            raise AtomicFenceRefused("A26_REVOKED_OR_MISSING_TRUST")
        if (auth["sequence"] != a24_receipt.sequence
                or auth["revision"] != a24_receipt.revision
                or bundle["sequence"] != a25_receipt.bundle_sequence
                or bundle["revision"] != a25_receipt.revision
                or auth["digest"] != hashlib.sha256(
                    self.fixture.a24_envelope).hexdigest()
                or bundle["release_sha256"] != hashlib.sha256(
                    self.fixture.release).hexdigest()
                or not hmac.compare_digest(
                    auth["descriptor_sha256"], claim.approved_descriptor_sha256)
                or not hmac.compare_digest(
                    bundle["descriptor_sha256"], claim.approved_descriptor_sha256)
                or not hmac.compare_digest(
                    bundle["bundle_sha256"], a25_receipt.bundle_sha256)
                or auth["publisher"] != claim.publisher
                or bundle_claim["admission_sha256"] != auth["digest"]
                or auth_claim["engine_id"] != self._owner_id
                or bundle_claim["engine_id"] != self._owner_id
                or auth_claim["installation_id"] != self._install_id
                or bundle_claim["installation_id"] != self._install_id
                or not auth_claim["issued_at"] <= now < auth_claim["expires_at"]
                or not bundle_claim["issued_at"] <= now < bundle_claim["expires_at"]):
            raise AtomicFenceRefused("A26_STALE_OR_MISMATCHED_FENCING_TOKEN")
        _ed25519(publisher["public_key"], auth_pubsig,
                 AUTH_PUBLISHER_DOMAIN + canonical(auth_claim))
        _ed25519(owner["public_key"], auth_opsig, AUTH_OPERATOR_DOMAIN
                 + canonical({"claim": auth_claim, "publisher_signature_b64":
                              base64.b64encode(auth_pubsig).decode("ascii")}))
        _ed25519(publisher["public_key"], bundle_pubsig,
                 BUNDLE_PUBLISHER_DOMAIN + canonical(bundle_claim))
        _ed25519(owner["public_key"], bundle_opsig, BUNDLE_OPERATOR_DOMAIN
                 + canonical({"claim": bundle_claim, "publisher_signature_b64":
                              base64.b64encode(bundle_pubsig).decode("ascii")}))
        state = self.bridge.status(self._owner_id)
        if (not state.enabled or not self.bridge._paper_enabled
                or state.descriptor_sha256 != claim.approved_descriptor_sha256):
            raise AtomicFenceRefused("A26_PAPER_PERMISSION_REVOKED")

    def commit(self, signals: Sequence[SignalIntent], *, now: int) -> JournalCounts:
        """Single local concurrency linearization point for signed PAPER commit.

        No callback or await can run between locked checks and SQL commit.
        Old A7/A22 APIs are not globally secured; callers must opt into the
        explicitly fence-required A22 bridge and this admission wrapper.
        """
        if type(now) is not int or not isinstance(signals, (list, tuple)):
            raise AtomicFenceRefused("A26_EXPLICIT_SIGNED_CLOCK_AND_BATCH_REQUIRED")
        fixture = self.fixture
        receipt = fixture._check(now)
        authority_receipt = fixture.session.authority.current(
            fixture.a24_envelope, catalog=fixture.session.catalog,
            contract=fixture.session.contract,
            installation_id=self._install_id, now=now)
        auth_claim, auth_pubsig, auth_opsig, _ = _parse_envelope(
            fixture.a24_envelope)
        bundle_claim, bundle_pubsig, bundle_opsig, _ = _parse_signed_bundle(
            fixture.release)
        prepared = []
        for intent in signals:
            if (type(intent) is not SignalIntent
                    or intent.evidence_mode is not EvidenceMode.PAPER
                    or intent.engine_id != self._owner_id
                    or intent.engine_version != fixture.session.contract.engine_version
                    or intent.instrument.market not in fixture.session.contract.markets):
                raise AtomicFenceRefused("A26_EXACT_PUBLIC_PAPER_ENGINE_ONLY")
            payload = _wire_intent(intent)
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            prepared.append((intent.engine_id, intent.signal_id, digest, payload))
        inserted = duplicate = 0
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._verify_locked(
                now=now, a24_receipt=authority_receipt, a25_receipt=receipt,
                auth_claim=auth_claim, bundle_claim=bundle_claim,
                auth_pubsig=auth_pubsig, auth_opsig=auth_opsig,
                bundle_pubsig=bundle_pubsig, bundle_opsig=bundle_opsig)
            for engine_id, signal_id, digest, payload in prepared:
                row = self._db.execute(
                    "SELECT digest FROM main.a7_paper_intents "
                    "WHERE engine_id=? AND signal_id=?",
                    (engine_id, signal_id)).fetchone()
                if row is not None:
                    if row["digest"] != digest:
                        raise IdentityConflict("A26_PAPER_IDENTITY_CONFLICT")
                    duplicate += 1
                else:
                    self._db.execute(
                        "INSERT INTO main.a7_paper_intents VALUES (?,?,?,?)",
                        (engine_id, signal_id, digest, payload))
                    inserted += 1
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return JournalCounts(inserted, duplicate)


class AtomicGuardedFixedSession:
    """A25 trusted and A23 fixed relay + exact A26 fenced A22 commit."""

    def __init__(self, protected: A25GuardedFixedFixture,
                 bridge: CustomPaperRuntimeBridge):
        self.protected = protected
        self.bridge = bridge
        self.fence = AtomicPaperCommitFence(protected, bridge)

    def launch(self, *, now: int):
        return self.protected.launch(now=now)

    def heartbeat(self, *, now: int):
        return self.protected.heartbeat(now=now)

    async def dispatch(self, packet: bytes, *, tick, now: int,
                       expected_revision: int):
        self.protected._check(now)
        bridge = self.bridge
        engine_id = self.protected.session.contract.engine_id
        state = bridge.status(engine_id)
        if (not state.enabled or not bridge._paper_enabled
                or state.revision != expected_revision):
            raise AtomicFenceRefused("A26_STALE_A22_PERMISSION_REVISION")
        # Fixed known A23 relay. Never execute package-provided code.
        data = await asyncio.to_thread(
            self.protected.session.sandbox.relay, packet, tick=tick)
        self.protected._check(now)
        return await bridge.dispatch(
            tick, packets={engine_id: data},
            expected_revisions={engine_id: expected_revision},
            now=tick.occurred_at, atomic_fence=self.fence,
            authorization_now=now)

    def stop(self):
        return self.protected.stop()
