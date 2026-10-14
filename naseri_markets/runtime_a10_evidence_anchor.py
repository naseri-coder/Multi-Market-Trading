"""RUNTIME-A10: nonproduction offline hash-chain + external-anchor COMPARISON.

This records SHA256 *claims* from earlier review stages. An independently
stored checkpoint must be supplied out-of-band to detect local database rollback.
There is no external storage connector, signer, Docker launch or runtime allow.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

_APP_ID = 0x4D4D544A
_AUDIENCE = "MMT-RUNTIME-A10-OFFLINE-ANCHOR-REVIEW-V1"
_GENESIS = "0" * 64
_KINDS = frozenset({
    "A5_CONSUMED_REVIEW", "A7_HOST_OBSERVATION",
    "A8_SOURCE_LOCK", "A9_SPENT_REVIEW",
})
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_LEDGER_ID = re.compile(r"[a-f0-9]{32}\Z")
_ACTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{3,95}\Z")
_PIN_KEYS = frozenset({
    "schema", "audience", "ledger_id", "sequence", "record_hash",
    "custody_state",
})


class A10Refused(ValueError):
    """Bounded non-disclosing evidence refusal."""


@dataclass(frozen=True, slots=True)
class LocalEvidenceHead:
    ledger_id: str
    sequence: int
    record_hash: str
    status: str = "A10_UNANCHORED_LOCAL_HASH_CHAIN_ONLY"
    external_custody_proven: bool = False
    independent_signer_proven: bool = False
    rollback_resistance_proven: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


@dataclass(frozen=True, slots=True)
class ExternalPinComparison:
    pinned_sequence: int
    local_sequence: int
    pinned_record_hash: str
    status: str = "A10_SUPPLIED_PIN_MATCHES_LOCAL_PREFIX_ONLY"
    independent_custody_proven: bool = False
    trusted_time_proven: bool = False
    distributed_rollback_resistance_proven: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


def _nonproduction() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise A10Refused("A10_NONPRODUCTION_ONLY")


def _second(at: datetime) -> int:
    if (not isinstance(at, datetime) or at.tzinfo is None
            or at.utcoffset() != timedelta(0) or at.microsecond != 0):
        raise A10Refused("A10_EXACT_UTC_SECOND_REQUIRED")
    epoch = int(at.timestamp())
    if epoch <= 0:
        raise A10Refused("A10_TIME_OUT_OF_RANGE")
    return epoch


def _operator(operator_id: int, allowed: frozenset[int], ack: bool) -> None:
    if (ack is not True or type(operator_id) is not int or operator_id <= 0
            or type(allowed) is not frozenset or operator_id not in allowed):
        raise A10Refused("A10_OPERATOR_APPROVAL_REQUIRED")


def _private_path(path: Path) -> None:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.parent.is_dir()
            or path.parent.is_symlink()):
        raise A10Refused("A10_PRIVATE_ABSOLUTE_PATH_REQUIRED")
    d = path.parent.stat()
    if d.st_uid != os.geteuid() or stat.S_IMODE(d.st_mode) & 0o077:
        raise A10Refused("A10_OWNER_ONLY_DIRECTORY_REQUIRED")
    if path.exists():
        s = path.lstat()
        if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1
                or s.st_uid != os.geteuid()
                or stat.S_IMODE(s.st_mode) & 0o077):
            raise A10Refused("A10_PRIVATE_FILE_REQUIRED")


def _canonical(payload: object) -> bytes:
    try:
        return json.dumps(
            payload, sort_keys=True, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise A10Refused("A10_CANONICAL_ENCODING_REFUSED") from exc


def _record_hash(seq: int, prev: str, kind: str,
                 digest: str, actor: str, epoch: int) -> str:
    return hashlib.sha256(
        b"MMT-A10-EVIDENCE-CHAIN-V1\x00" + _canonical({
            "sequence": seq, "previous": prev, "kind": kind,
            "digest": digest, "actor": actor, "utc_epoch": epoch,
        }),
    ).hexdigest()


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise A10Refused("A10_DUPLICATE_ANCHOR_KEY")
        output[key] = value
    return output


def _reject_number(_: str) -> None:
    raise A10Refused("A10_NONINTEGER_ANCHOR_VALUE")


def _parse_anchor(data: bytes) -> dict:
    if type(data) is not bytes or not 0 < len(data) <= 1024:
        raise A10Refused("A10_EXTERNAL_PIN_BYTES_REQUIRED")
    try:
        obj = json.loads(
            data.decode("ascii"), object_pairs_hook=_unique,
            parse_float=_reject_number, parse_constant=_reject_number,
        )
    except A10Refused:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise A10Refused("A10_INVALID_EXTERNAL_PIN_JSON") from exc
    if (type(obj) is not dict or set(obj) != _PIN_KEYS
            or type(obj["schema"]) is not int or obj["schema"] != 1
            or obj["audience"] != _AUDIENCE
            or obj["custody_state"] != "LOCAL_EXPORT_NOT_INDEPENDENTLY_STORED"
            or type(obj["ledger_id"]) is not str
            or _LEDGER_ID.fullmatch(obj["ledger_id"]) is None
            or type(obj["sequence"]) is not int or obj["sequence"] <= 0
            or type(obj["record_hash"]) is not str
            or _SHA.fullmatch(obj["record_hash"]) is None
            or _canonical(obj) != data):
        raise A10Refused("A10_INVALID_EXTERNAL_PIN_SCHEMA")
    return obj


class OfflineEvidenceLedger:
    """Local SQLite chain; external custody cannot be created by this class.

    Privileged file rewrites, rollback and forged operator-supplied PINs
    require controls outside the host. Do not use this as a signing authority.
    """

    def __init__(self, path: Path) -> None:
        _nonproduction()
        _private_path(path)
        existed = path.exists()
        if not existed:
            try:
                fd = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                    0o600,
                )
                os.close(fd)
            except OSError as exc:
                raise A10Refused("A10_LEDGER_CREATE_FAILED") from exc
        self._db = sqlite3.connect(str(path), isolation_level=None, timeout=5)
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA trusted_schema=OFF")
            if existed:
                if self._db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID:
                    raise A10Refused("A10_UNRECOGNIZED_LEDGER")
            else:
                self._db.execute(f"PRAGMA application_id={_APP_ID}")
                self._db.execute(
                    "CREATE TABLE identity(ledger_id TEXT NOT NULL)"
                )
                self._db.execute(
                    "INSERT INTO identity(ledger_id) VALUES(?)",
                    (secrets.token_hex(16),),
                )
                self._db.execute("""
                    CREATE TABLE entries(
                      sequence INTEGER PRIMARY KEY, previous TEXT NOT NULL,
                      record_hash TEXT NOT NULL, kind TEXT NOT NULL,
                      evidence_sha TEXT NOT NULL, actor TEXT NOT NULL,
                      observed_epoch INTEGER NOT NULL
                    )
                """)
            self._check()
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def _check(self) -> tuple[str, int, str]:
        """Check EVERY local row, contiguous chain and exact state schema."""
        try:
            if self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise A10Refused("A10_SQLITE_INTEGRITY_FAILURE")
            if {r[1] for r in self._db.execute("PRAGMA table_info(entries)")} != {
                "sequence", "previous", "record_hash", "kind",
                "evidence_sha", "actor", "observed_epoch",
            }:
                raise A10Refused("A10_ENTRIES_SCHEMA_DRIFT")
            identity_rows = self._db.execute(
                "SELECT ledger_id FROM identity",
            ).fetchall()
            if (len(identity_rows) != 1 or type(identity_rows[0][0]) is not str
                    or _LEDGER_ID.fullmatch(identity_rows[0][0]) is None):
                raise A10Refused("A10_LEDGER_IDENTITY_DRIFT")
            ledger_id = identity_rows[0][0]
            seq, prev, last_epoch = 0, _GENESIS, 0
            for row in self._db.execute(
                "SELECT sequence, previous, record_hash, kind, evidence_sha,"
                "actor, observed_epoch FROM entries ORDER BY sequence"
            ):
                n, before, claimed, kind, evidence, actor, epoch = row
                if (type(n) is not int or n != seq + 1
                        or type(before) is not str or before != prev
                        or type(claimed) is not str or _SHA.fullmatch(claimed) is None
                        or type(kind) is not str or kind not in _KINDS
                        or type(evidence) is not str or _SHA.fullmatch(evidence) is None
                        or type(actor) is not str or _ACTOR.fullmatch(actor) is None
                        or type(epoch) is not int or epoch <= 0
                        or epoch < last_epoch
                        or not hmac.compare_digest(
                            claimed, _record_hash(n, before, kind, evidence, actor, epoch),
                        )):
                    raise A10Refused("A10_LOCAL_CHAIN_TAMPER_OR_GAP")
                seq, prev, last_epoch = n, claimed, epoch
            return ledger_id, seq, prev
        except sqlite3.DatabaseError as exc:
            raise A10Refused("A10_LEDGER_UNREADABLE") from exc

    def _atomic(self, fn):
        _nonproduction()
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._check()
                value = fn()
                self._db.execute("COMMIT")
                return value
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.DatabaseError as exc:
            raise A10Refused("A10_TRANSACTION_FAILED") from exc

    def append_claim(
        self, *, kind: str, evidence_sha256: str,
        actor: str, at: datetime, operator_id: int,
        authorized_operators: frozenset[int], operator_ack: bool = False,
    ) -> LocalEvidenceHead:
        """Record only a claim DIGEST, not its source contents or authorization."""
        _nonproduction()
        _operator(operator_id, authorized_operators, operator_ack)
        epoch = _second(at)
        if (type(kind) is not str or kind not in _KINDS
                or type(evidence_sha256) is not str
                or _SHA.fullmatch(evidence_sha256) is None
                or type(actor) is not str or _ACTOR.fullmatch(actor) is None):
            raise A10Refused("A10_EXACT_DIGEST_CLAIM_SCOPE_REQUIRED")

        def append() -> LocalEvidenceHead:
            ledger_id, sequence, previous = self._check()
            last = self._db.execute(
                "SELECT observed_epoch FROM entries ORDER BY sequence DESC LIMIT 1",
            ).fetchone()
            if last is not None and epoch < last[0]:
                raise A10Refused("A10_LOCAL_TIME_REGRESSION")
            next_seq = sequence + 1
            record = _record_hash(
                next_seq, previous, kind, evidence_sha256, actor, epoch,
            )
            self._db.execute(
                "INSERT INTO entries(sequence,previous,record_hash,kind,"
                "evidence_sha,actor,observed_epoch) VALUES(?,?,?,?,?,?,?)",
                (next_seq, previous, record, kind, evidence_sha256, actor, epoch),
            )
            return LocalEvidenceHead(ledger_id, next_seq, record)
        return self._atomic(append)

    def local_head(self) -> LocalEvidenceHead:
        _nonproduction()
        ledger_id, seq, digest = self._check()
        return LocalEvidenceHead(ledger_id, seq, digest)

    def export_untrusted_anchor(self) -> bytes:
        """Operator must transfer this exact byte string OUTSIDE this host."""
        _nonproduction()
        head = self.local_head()
        if head.sequence <= 0:
            raise A10Refused("A10_EMPTY_CHAIN_CANNOT_EXPORT")
        return _canonical({
            "schema": 1, "audience": _AUDIENCE,
            "ledger_id": head.ledger_id, "sequence": head.sequence,
            "record_hash": head.record_hash,
            "custody_state": "LOCAL_EXPORT_NOT_INDEPENDENTLY_STORED",
        })

    def compare_supplied_anchor(self, external_bytes: bytes) -> ExternalPinComparison:
        """Compare operator-supplied bytes; CANNOT prove their external origin."""
        _nonproduction()
        pin = _parse_anchor(external_bytes)
        ledger_id, seq, _ = self._check()
        if pin["ledger_id"] != ledger_id:
            raise A10Refused("A10_ANCHOR_WRONG_LEDGER")
        if seq < pin["sequence"]:
            raise A10Refused("A10_ROLLBACK_BELOW_SUPPLIED_ANCHOR")
        stored = self._db.execute(
            "SELECT record_hash FROM entries WHERE sequence=?",
            (pin["sequence"],),
        ).fetchone()
        if (stored is None or not hmac.compare_digest(
            stored[0], pin["record_hash"],
        )):
            raise A10Refused("A10_SUPPLIED_ANCHOR_HASH_DIVERGENCE")
        return ExternalPinComparison(
            pinned_sequence=pin["sequence"],
            local_sequence=seq,
            pinned_record_hash=pin["record_hash"],
        )


__all__ = [
    "A10Refused", "LocalEvidenceHead", "ExternalPinComparison",
    "OfflineEvidenceLedger",
]
