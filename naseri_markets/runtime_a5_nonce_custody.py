"""RUNTIME-A5: one-time, crash-persistent A4 evidence review (never execution).

An operator-issued nonce is stored by SHA-256 in a local private SQLite file.
A signed A4 claim may be consumed exactly once, scoped to one pinned worker,
host, issuer, OCI policy and short deadline. No path grants runtime privileges.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .durable_runtime_a3 import _approved_dir
from .multilang_runtime_a1 import RuntimeKind, RuntimeProfile
from .runtime_a4_security_evidence import (
    _ID,
    _SHA,
    _parse,
    policy_digest,
    verify_security_evidence,
)

_APP_ID = 0x4D4D5435
_MAX_CHALLENGE_AGE_SECONDS = 900


class RuntimeChallengeRefused(ValueError):
    """Non-disclosing challenge or evidence review failure."""


@dataclass(frozen=True, slots=True)
class Challenge:
    """Operator must deliver nonce independently; only its hash is persisted."""

    nonce: str
    challenge_digest: str
    expires_at: datetime
    status: str = "ISSUED_REVIEW_ONLY"
    execution_authorized: bool = False


@dataclass(frozen=True, slots=True)
class ConsumedReview:
    challenge_digest: str
    receipt_sha256: str
    profile_sha256: str
    status: str = "EVIDENCE_CONSUMED_REVIEW_ONLY"
    host_isolation_certified: bool = False
    worker_installed: bool = False
    retry_permitted: bool = False
    broker_enabled: bool = False
    telegram_enabled: bool = False
    execution_authorized: bool = False


def _nonproduction() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise RuntimeChallengeRefused("NONPRODUCTION_ONLY")


def _utc_second(at: datetime) -> int:
    if (not isinstance(at, datetime) or at.tzinfo is None
            or at.utcoffset() != timedelta(0) or at.microsecond != 0):
        raise RuntimeChallengeRefused("EXACT_UTC_SECOND_REQUIRED")
    return int(at.astimezone(UTC).timestamp())


def _operator(operator_id: int, authorized_operator_ids: frozenset[int],
              operator_ack: bool) -> None:
    if (operator_ack is not True or type(operator_id) is not int
            or operator_id <= 0 or type(authorized_operator_ids) is not frozenset
            or operator_id not in authorized_operator_ids):
        raise RuntimeChallengeRefused("EXPLICIT_AUTHORIZED_OPERATOR_REQUIRED")


class RuntimeChallengeLedger:
    """Atomic, local replay fence; not an independently attested host ledger."""

    def __init__(self, path: Path) -> None:
        if type(path) is not Path:
            raise RuntimeChallengeRefused("EXPLICIT_LOCAL_PATH_REQUIRED")
        _approved_dir(path)
        existed = path.exists()
        if not existed:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(fd)
        self._db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA trusted_schema=OFF")
            if existed:
                if self._db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID:
                    raise RuntimeChallengeRefused("UNKNOWN_CHALLENGE_LEDGER")
            else:
                self._db.execute(f"PRAGMA application_id={_APP_ID}")
                self._db.execute("""
                    CREATE TABLE challenges (
                      nonce_hash TEXT PRIMARY KEY,
                      kind TEXT NOT NULL,
                      policy_hash TEXT NOT NULL,
                      worker_hash TEXT NOT NULL,
                      host_id TEXT NOT NULL,
                      issuer_id TEXT NOT NULL,
                      issued_epoch INTEGER NOT NULL,
                      expiry_epoch INTEGER NOT NULL,
                      state TEXT NOT NULL CHECK(state IN
                        ('ISSUED','CONSUMED','REVOKED')),
                      receipt_hash TEXT NOT NULL DEFAULT ''
                    )
                """)
            self._verify()
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def _verify(self) -> None:
        try:
            if self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeChallengeRefused("CHALLENGE_LEDGER_CORRUPTED")
            for row in self._db.execute(
                "SELECT nonce_hash,kind,policy_hash,worker_hash,host_id,"
                "issuer_id,issued_epoch,expiry_epoch,state,receipt_hash "
                "FROM challenges"
            ):
                nonce, kind, policy, worker, host, issuer, issued, expiry, state, receipt = row
                if (not _SHA.fullmatch(nonce or "")
                        or kind not in {k.value for k in RuntimeKind}
                        or not _SHA.fullmatch(policy or "")
                        or not _SHA.fullmatch(worker or "")
                        or _ID.fullmatch(host or "") is None
                        or _ID.fullmatch(issuer or "") is None
                        or type(issued) is not int or type(expiry) is not int
                        or not 0 < expiry - issued <= _MAX_CHALLENGE_AGE_SECONDS
                        or state not in {"ISSUED", "CONSUMED", "REVOKED"}
                        or (state == "CONSUMED") != bool(receipt)
                        or (receipt and not _SHA.fullmatch(receipt))):
                    raise RuntimeChallengeRefused("CHALLENGE_LEDGER_DRIFT")
        except sqlite3.DatabaseError as exc:
            raise RuntimeChallengeRefused("CHALLENGE_LEDGER_UNREADABLE") from exc

    def _transaction(self, operation):
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._verify()
                result = operation()
                self._db.execute("COMMIT")
                return result
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.DatabaseError as exc:
            raise RuntimeChallengeRefused("CHALLENGE_TRANSACTION_FAILED") from exc

    def issue(
        self, profile: RuntimeProfile, *, worker_sha256: str,
        host_id: str, issuer_id: str, at: datetime,
        operator_id: int, authorized_operator_ids: frozenset[int],
        operator_ack: bool = False,
        lifetime_seconds: int = _MAX_CHALLENGE_AGE_SECONDS,
    ) -> Challenge:
        _nonproduction()
        _operator(operator_id, authorized_operator_ids, operator_ack)
        issued = _utc_second(at)
        if (type(worker_sha256) is not str or _SHA.fullmatch(worker_sha256) is None
                or type(host_id) is not str or _ID.fullmatch(host_id) is None
                or type(issuer_id) is not str or _ID.fullmatch(issuer_id) is None
                or type(lifetime_seconds) is not int
                or not 1 <= lifetime_seconds <= _MAX_CHALLENGE_AGE_SECONDS):
            raise RuntimeChallengeRefused("INVALID_PINNED_CHALLENGE_SCOPE")
        pinned = policy_digest(profile)
        nonce = secrets.token_hex(24)
        digest = hashlib.sha256(nonce.encode("ascii")).hexdigest()

        def insert() -> None:
            self._db.execute(
                "INSERT INTO challenges "
                "(nonce_hash,kind,policy_hash,worker_hash,host_id,"
                "issuer_id,issued_epoch,expiry_epoch,state) "
                "VALUES(?,?,?,?,?,?,?,?, 'ISSUED')",
                (digest, profile.kind.value, pinned, worker_sha256,
                 host_id, issuer_id, issued, issued + lifetime_seconds),
            )
        self._transaction(insert)
        return Challenge(nonce, digest,
                         datetime.fromtimestamp(issued + lifetime_seconds, tz=UTC))

    def consume(
        self, receipt: bytes, *, nonce: str, profile: RuntimeProfile,
        review_key: bytes, host_id: str, issuer_id: str, at: datetime,
        operator_id: int, authorized_operator_ids: frozenset[int],
        operator_ack: bool = False,
    ) -> ConsumedReview:
        _nonproduction()
        _operator(operator_id, authorized_operator_ids, operator_ack)
        now = _utc_second(at)
        if type(nonce) is not str or len(nonce) != 48:
            raise RuntimeChallengeRefused("CHALLENGE_NONCE_INVALID")
        nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        # Validate A4 MAC, complete policy/host/nonce and deadline BEFORE
        # writing a consumed receipt. Failed signatures do not burn a nonce.
        review = verify_security_evidence(
            receipt, profile=profile, review_key=review_key,
            trusted_issuer_id=issuer_id, expected_host_id=host_id,
            expected_nonce=nonce, at=at,
        )
        evidence = _parse(receipt)["payload"]
        worker_hash = evidence["worker_digest"]

        def spend() -> ConsumedReview:
            row = self._db.execute(
                "SELECT kind,policy_hash,worker_hash,host_id,issuer_id,"
                "issued_epoch,expiry_epoch,state FROM challenges "
                "WHERE nonce_hash=?", (nonce_hash,),
            ).fetchone()
            if row is None:
                raise RuntimeChallengeRefused("UNISSUED_NONCE")
            kind, policy, worker, host, issuer, issued, expires, state = row
            if state != "ISSUED":
                raise RuntimeChallengeRefused("CHALLENGE_ALREADY_SPENT_OR_REVOKED")
            if (kind != profile.kind.value or policy != review.profile_sha256
                    or not hmac.compare_digest(worker, worker_hash)
                    or host != host_id or issuer != issuer_id
                    or not issued <= now <= expires):
                raise RuntimeChallengeRefused("CHALLENGE_SCOPE_OR_TIME_DRIFT")
            changed = self._db.execute(
                "UPDATE challenges SET state='CONSUMED', receipt_hash=? "
                "WHERE nonce_hash=? AND state='ISSUED'",
                (review.receipt_sha256, nonce_hash),
            )
            if changed.rowcount != 1:
                raise RuntimeChallengeRefused("CHALLENGE_ALREADY_SPENT")
            return ConsumedReview(nonce_hash, review.receipt_sha256,
                                  review.profile_sha256)
        return self._transaction(spend)

    def revoke(
        self, nonce_hash: str, *, operator_id: int,
        authorized_operator_ids: frozenset[int], operator_ack: bool = False,
    ) -> None:
        _nonproduction()
        _operator(operator_id, authorized_operator_ids, operator_ack)
        if type(nonce_hash) is not str or _SHA.fullmatch(nonce_hash) is None:
            raise RuntimeChallengeRefused("INVALID_CHALLENGE_HASH")

        def cancel() -> None:
            cur = self._db.execute(
                "UPDATE challenges SET state='REVOKED' "
                "WHERE nonce_hash=? AND state='ISSUED'", (nonce_hash,),
            )
            if cur.rowcount != 1:
                raise RuntimeChallengeRefused("UNKNOWN_OR_SPENT_CHALLENGE")
        self._transaction(cancel)


__all__ = [
    "Challenge", "ConsumedReview", "RuntimeChallengeLedger",
    "RuntimeChallengeRefused",
]
