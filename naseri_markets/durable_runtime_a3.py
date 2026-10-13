"""RUNTIME-A3: durable fail-closed execution lease and quarantine review.

Nonproduction only. Never starts a worker except through separately supplied
RUNTIME-A1 operator-reviewed host; never releases an interrupted/quarantined
binding. Human review receipts DO NOT constitute a release.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from .core_api_v1 import CoreInput, CoreManifest
from .multilang_runtime_a1 import (
    MultiLanguageOfflineHost,
    RuntimeKind,
    RuntimeResult,
    prepare_framed_request,
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_APP_ID = 0x4D4D5433  # MMT3; refuses unrelated SQLite files.
_STATES = frozenset({"RUNNING", "READY", "QUARANTINED"})
_EVENTS = frozenset({"START", "SUCCESS", "QUARANTINE", "REVIEW_ONLY"})
_ZERO = "0" * 64


class DurableRuntimeRefused(ValueError):
    """Fails closed without echoing strategy source, credentials or market data."""


@dataclass(frozen=True, slots=True)
class RuntimeLeaseStatus:
    binding_fingerprint: str
    state: str
    revision: int
    event_count: int
    retry_permitted: bool = False
    live_permitted: bool = False
    telegram_permitted: bool = False
    broker_permitted: bool = False


def _approved_dir(path: Path) -> None:
    if (not path.is_absolute() or path.is_symlink() or
            not path.parent.is_dir() or path.parent.is_symlink()):
        raise DurableRuntimeRefused("PRIVATE_ABSOLUTE_LEDGER_PATH_REQUIRED")
    root = path.parent.stat()
    if (root.st_uid != os.geteuid()
            or stat.S_IMODE(root.st_mode) & 0o077):
        raise DurableRuntimeRefused("PRIVATE_OWNER_ONLY_DIRECTORY_REQUIRED")
    if path.exists():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077):
            raise DurableRuntimeRefused("PRIVATE_OWNER_ONLY_LEDGER_FILE_REQUIRED")


def _fingerprint(manifest: CoreManifest, event: CoreInput) -> str:
    if not isinstance(manifest, CoreManifest) or not isinstance(event, CoreInput):
        raise DurableRuntimeRefused("MANIFEST_AND_EVENT_REQUIRED")
    components = (
        manifest.core_id, manifest.core_version, event.binding.instance_id,
        event.binding.binding_id,
    )
    if any(type(x) is not str or not 1 <= len(x) <= 160 for x in components):
        raise DurableRuntimeRefused("INVALID_BINDING_IDENTITY")
    # Length-prefixed components remove ambiguous separator collisions.
    payload = b"".join(len(x.encode()).to_bytes(4, "big") + x.encode()
                       for x in components)
    return hashlib.sha256(payload).hexdigest()


def _audit_hash(seq: int, before: str, fingerprint: str,
                transition: str, digest: str) -> str:
    return hashlib.sha256(
        f"{seq}|{before}|{fingerprint}|{transition}|{digest}".encode("ascii")
    ).hexdigest()


class DurableRuntimeLedger:
    """Synchronous FULL SQLite local fence with a detectably chained journal.

    The journal has no external signed checkpoint; a malicious local database
    owner may rewrite it. Disk and host integrity remain independent controls.
    """

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise DurableRuntimeRefused("EXPLICIT_LEDGER_PATH_REQUIRED")
        _approved_dir(path)
        existed = path.exists()
        if not existed:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                os.close(fd)
            except OSError as exc:
                raise DurableRuntimeRefused("LEDGER_CREATE_FAILED") from exc
        self._db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA trusted_schema=OFF")
            if existed:
                if self._db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID:
                    raise DurableRuntimeRefused("UNKNOWN_LEDGER_DATABASE")
            else:
                self._db.execute(f"PRAGMA application_id={_APP_ID}")
                self._db.execute("""
                    CREATE TABLE runtime_leases (
                      fingerprint TEXT PRIMARY KEY,
                      state TEXT NOT NULL CHECK(state IN
                        ('RUNNING','READY','QUARANTINED')),
                      last_digest TEXT NOT NULL,
                      revision INTEGER NOT NULL CHECK(revision >= 1)
                    )""")
                self._db.execute("""
                    CREATE TABLE runtime_audit (
                      seq INTEGER PRIMARY KEY,
                      fingerprint TEXT NOT NULL,
                      transition TEXT NOT NULL,
                      digest TEXT NOT NULL,
                      prev_hash TEXT NOT NULL,
                      record_hash TEXT NOT NULL
                    )""")
                self._db.execute("""
                    CREATE TABLE runtime_reviews (
                      fingerprint TEXT NOT NULL,
                      evidence_hash TEXT NOT NULL,
                      note_hash TEXT NOT NULL,
                      operator_id INTEGER NOT NULL,
                      PRIMARY KEY (fingerprint, evidence_hash)
                    )""")
            self._verify()
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def _verify(self) -> None:
        try:
            if self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise DurableRuntimeRefused("LEDGER_CORRUPTED")
            previous = _ZERO
            last_event: dict[str, tuple[str, str, int]] = {}
            starts: dict[str, int] = {}
            previous_seq = 0
            for seq, finger, event, digest, stored_prev, stored_hash in (
                self._db.execute(
                    "SELECT seq, fingerprint, transition, digest, prev_hash, "
                    "record_hash FROM runtime_audit ORDER BY seq")
            ):
                if (type(seq) is not int or seq != previous_seq + 1
                        or not _SHA.fullmatch(finger or "")
                        or event not in _EVENTS or not _SHA.fullmatch(digest or "")
                        or stored_prev != previous
                        or stored_hash != _audit_hash(seq, previous, finger, event, digest)):
                    raise DurableRuntimeRefused("RUNTIME_AUDIT_DRIFT")
                previous = stored_hash
                previous_seq = seq
                if event == "START":
                    starts[finger] = starts.get(finger, 0) + 1
                    last_event[finger] = ("RUNNING", digest, starts[finger])
                elif event in {"SUCCESS", "QUARANTINE"}:
                    prior = last_event.get(finger)
                    if prior is None or prior[0] != "RUNNING" or prior[1] != digest:
                        raise DurableRuntimeRefused("RUNTIME_AUDIT_TRANSITION_DRIFT")
                    last_event[finger] = (
                        "READY" if event == "SUCCESS" else "QUARANTINED",
                        digest, starts[finger],
                    )
                elif finger not in last_event or last_event[finger][0] not in (
                        "RUNNING", "QUARANTINED"):
                    raise DurableRuntimeRefused("INVALID_RUNTIME_REVIEW_HISTORY")
            actual = {
                fingerprint: (state, digest, revision)
                for fingerprint, state, digest, revision in self._db.execute(
                    "SELECT fingerprint,state,last_digest,revision FROM runtime_leases")
            }
            if actual != last_event:
                raise DurableRuntimeRefused("RUNTIME_LEASE_AUDIT_MISMATCH")
            for finger, state in actual.items():
                if (not _SHA.fullmatch(finger) or state[0] not in _STATES
                        or not _SHA.fullmatch(state[1]) or state[2] < 1):
                    raise DurableRuntimeRefused("RUNTIME_STATE_CORRUPTED")
        except sqlite3.DatabaseError as exc:
            raise DurableRuntimeRefused("LEDGER_UNREADABLE") from exc

    def _append(self, fingerprint: str, transition: str, digest: str) -> None:
        prior = self._db.execute(
            "SELECT seq,record_hash FROM runtime_audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        seq = 1 if prior is None else prior[0] + 1
        before = _ZERO if prior is None else prior[1]
        self._db.execute(
            "INSERT INTO runtime_audit "
            "(seq,fingerprint,transition,digest,prev_hash,record_hash)"
            "VALUES(?,?,?,?,?,?)",
            (seq, fingerprint, transition, digest, before,
             _audit_hash(seq, before, fingerprint, transition, digest)),
        )

    def _transaction(self, operation):
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._verify()
                output = operation()
                self._db.execute("COMMIT")
                return output
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.DatabaseError as exc:
            raise DurableRuntimeRefused("LEDGER_TRANSACTION_FAILED") from exc

    def status(self, fingerprint: str) -> RuntimeLeaseStatus:
        if type(fingerprint) is not str or not _SHA.fullmatch(fingerprint):
            raise DurableRuntimeRefused("INVALID_BINDING_FINGERPRINT")
        self._verify()
        record = self._db.execute(
            "SELECT state,revision FROM runtime_leases WHERE fingerprint=?",
            (fingerprint,),
        ).fetchone()
        count = self._db.execute(
            "SELECT count(*) FROM runtime_audit WHERE fingerprint=?",
            (fingerprint,),
        ).fetchone()[0]
        return RuntimeLeaseStatus(
            fingerprint, "ABSENT" if record is None else record[0],
            0 if record is None else record[1], count,
        )

    def start(self, fingerprint: str, digest: str) -> None:
        if (type(fingerprint) is not str or not _SHA.fullmatch(fingerprint)
                or type(digest) is not str or not _SHA.fullmatch(digest)):
            raise DurableRuntimeRefused("INVALID_ATTEMPT_IDENTITY")

        def mutate() -> None:
            prior = self._db.execute(
                "SELECT state, revision FROM runtime_leases WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if prior is not None and prior[0] != "READY":
                raise DurableRuntimeRefused("PERSISTENT_BINDING_BLOCKED")
            if prior is None:
                self._db.execute(
                    "INSERT INTO runtime_leases VALUES(?,?,?,1)",
                    (fingerprint, "RUNNING", digest),
                )
            else:
                self._db.execute(
                    "UPDATE runtime_leases SET state='RUNNING',last_digest=?,revision=? "
                    "WHERE fingerprint=?",
                    (digest, prior[1] + 1, fingerprint),
                )
            self._append(fingerprint, "START", digest)
        self._transaction(mutate)

    def finish(self, fingerprint: str, digest: str, *, success: bool) -> None:
        if type(success) is not bool:
            raise DurableRuntimeRefused("EXPLICIT_OUTCOME_REQUIRED")

        def mutate() -> None:
            prior = self._db.execute(
                "SELECT state,last_digest FROM runtime_leases WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if prior != ("RUNNING", digest):
                raise DurableRuntimeRefused("STALE_ATTEMPT_CANNOT_FINALIZE")
            self._db.execute(
                "UPDATE runtime_leases SET state=? WHERE fingerprint=?",
                ("READY" if success else "QUARANTINED", fingerprint),
            )
            self._append(fingerprint, "SUCCESS" if success else "QUARANTINE",
                         digest)
        self._transaction(mutate)

    def record_review(
        self, fingerprint: str, *, evidence_sha256: str, note: str,
        operator_id: int, authorized_operator_ids: frozenset[int],
        operator_ack: bool = False, all_workers_stopped: bool = False,
    ) -> dict:
        if (type(fingerprint) is not str or not _SHA.fullmatch(fingerprint)
                or operator_ack is not True or all_workers_stopped is not True
                or type(operator_id) is not int or operator_id <= 0
                or operator_id not in authorized_operator_ids):
            raise DurableRuntimeRefused("REVIEW_ADMIN_AND_STOP_ACK_REQUIRED")
        if (type(evidence_sha256) is not str
                or not _SHA.fullmatch(evidence_sha256)
                or type(note) is not str or not 12 <= len(note) <= 240
                or not note.isprintable() or "\n" in note or "\r" in note):
            raise DurableRuntimeRefused("REVIEW_EVIDENCE_AND_NOTE_REQUIRED")
        note_hash = hashlib.sha256(note.encode()).hexdigest()

        def mutate() -> None:
            state = self._db.execute(
                "SELECT state FROM runtime_leases WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if state is None or state[0] not in ("RUNNING", "QUARANTINED"):
                raise DurableRuntimeRefused("NOT_BLOCKED_NO_REVIEW")
            previous = self._db.execute(
                "SELECT note_hash,operator_id FROM runtime_reviews "
                "WHERE fingerprint=? AND evidence_hash=?",
                (fingerprint, evidence_sha256),
            ).fetchone()
            if previous is None:
                self._db.execute(
                    "INSERT INTO runtime_reviews VALUES(?,?,?,?)",
                    (fingerprint, evidence_sha256, note_hash, operator_id),
                )
                self._append(fingerprint, "REVIEW_ONLY", evidence_sha256)
            elif previous != (note_hash, operator_id):
                raise DurableRuntimeRefused("CONFLICTING_REVIEW_RECEIPT")
        self._transaction(mutate)
        return {
            "status": "REVIEW_RECORDED_NO_RELEASE",
            "fingerprint": fingerprint,
            "runtime_state_changed": False,
            "retry_permitted": False,
            "live_permitted": False,
            "broker_order_sent": False,
            "telegram_sent": False,
        }


class DurableOfflineRuntime:
    """Transparent default-deny wrapper with crash-persistent lease fencing."""

    def __init__(self, host: MultiLanguageOfflineHost,
                 ledger: DurableRuntimeLedger) -> None:
        if (not isinstance(host, MultiLanguageOfflineHost)
                or not isinstance(ledger, DurableRuntimeLedger)):
            raise DurableRuntimeRefused("EXPLICIT_HOST_AND_LEDGER_REQUIRED")
        self._host = host
        self._ledger = ledger

    def evaluate(
        self, kind: RuntimeKind, manifest: CoreManifest, event: CoreInput,
        *, artifact_name: str, artifact: bytes, approved_sha256: str,
        operator_ack: bool = False,
    ) -> RuntimeResult:
        if (os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_PRODUCTION") == "1"):
            raise DurableRuntimeRefused("NONPRODUCTION_ONLY")
        if operator_ack is not True:
            raise DurableRuntimeRefused("OPERATOR_APPROVAL_REQUIRED")
        if (not isinstance(kind, RuntimeKind)
                or self._host.status().get(kind.value) != "REVIEWED_WORKER_POLICY"):
            raise DurableRuntimeRefused("REVIEWED_WORKER_NOT_INSTALLED")
        # Validate before START; malformed requests do not create leases.
        prepare_framed_request(
            kind, manifest, event, artifact_name=artifact_name,
            artifact=artifact, approved_sha256=approved_sha256,
        )
        fingerprint = _fingerprint(manifest, event)
        digest = event.input_digest
        self._ledger.start(fingerprint, digest)  # FULL commit before execution.
        try:
            result = self._host.evaluate(
                kind, manifest, event, artifact_name=artifact_name,
                artifact=artifact, approved_sha256=approved_sha256,
            )
        except Exception as exc:
            self._ledger.finish(fingerprint, digest, success=False)
            raise DurableRuntimeRefused("DURABLE_BINDING_QUARANTINED") from exc
        # If this commit fails, NEVER return a plausible successful CoreResult.
        self._ledger.finish(fingerprint, digest, success=True)
        return result


__all__ = [
    "DurableOfflineRuntime", "DurableRuntimeLedger", "DurableRuntimeRefused",
    "RuntimeLeaseStatus",
]
