"""A9 non-executable one-time *review intent* tickets. No Worker grant.

A signed claim and a local SQLite replay ledger NEVER prove host isolation.
This module must not be imported by a runtime dispatcher as an allow gate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .durable_runtime_a3 import _approved_dir
from .multilang_runtime_a1 import RuntimeKind, RuntimeProfile
from .runtime_a4_security_evidence import _ID, _SHA, policy_digest
from .runtime_a5_nonce_custody import ConsumedReview

_APP_ID = 0x4D4D5439
_AUDIENCE = "MMT-RUNTIME-A9-INERT-REVIEW-V1"
_MAX_AGE = 300
_FIELDS = frozenset({
    "schema", "audience", "nonce", "kind", "policy", "worker",
    "source", "request", "a5_receipt", "host", "issuer", "issued", "expires",
})


class A9Refused(ValueError):
    """Fail closed without revealing the private ticket contents."""


@dataclass(frozen=True, slots=True)
class InertTicket:
    envelope: bytes
    ticket_sha256: str
    expires_at: datetime
    status: str = "A9_SIMULATED_REVIEW_ONLY"
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


@dataclass(frozen=True, slots=True)
class SpentReview:
    ticket_sha256: str
    request_sha256: str
    status: str = "A9_ONE_TIME_REVIEW_SPENT_NO_EXECUTION"
    host_isolation_certified: bool = False
    independent_custody_proved: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


def _nonproduction() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise A9Refused("A9_NONPRODUCTION_ONLY")


def _second(value: datetime) -> int:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() != timedelta(0) or value.microsecond):
        raise A9Refused("A9_EXACT_UTC_SECOND_REQUIRED")
    result = int(value.astimezone(UTC).timestamp())
    if result <= 0:
        raise A9Refused("A9_INVALID_TIME")
    return result


def _operator(who: int, allowed: frozenset[int], ack: bool) -> None:
    if (ack is not True or type(who) is not int or who <= 0
            or type(allowed) is not frozenset or who not in allowed):
        raise A9Refused("A9_AUTHORIZED_OPERATOR_ACK_REQUIRED")


def _key(key: bytes) -> None:
    if type(key) is not bytes or not 32 <= len(key) <= 4096:
        raise A9Refused("A9_OUT_OF_BAND_KEY_REQUIRED")


def _scope(
    profile: RuntimeProfile, a5: ConsumedReview, *,
    worker: str, source: str, request: str, host: str, issuer: str,
) -> str:
    try:
        policy = policy_digest(profile)
    except (TypeError, ValueError) as exc:
        raise A9Refused("A9_PROFILE_NOT_REVIEWED") from exc
    if (type(a5) is not ConsumedReview
            or a5.status != "EVIDENCE_CONSUMED_REVIEW_ONLY"
            or any(getattr(a5, attr) is not False for attr in (
                "host_isolation_certified", "worker_installed",
                "retry_permitted", "broker_enabled", "telegram_enabled",
                "execution_authorized",
            ))
            or type(a5.profile_sha256) is not str
            or not hmac.compare_digest(a5.profile_sha256, policy)
            or any(type(value) is not str or _SHA.fullmatch(value) is None for value in (
                a5.challenge_digest, a5.receipt_sha256,
                worker, source, request,
            ))
            or type(host) is not str or _ID.fullmatch(host) is None
            or type(issuer) is not str or _ID.fullmatch(issuer) is None):
        raise A9Refused("A9_EXACT_REVIEW_SCOPE_REQUIRED")
    return policy


def _json(data: object) -> bytes:
    try:
        return json.dumps(
            data, ensure_ascii=True, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise A9Refused("A9_NOT_CANONICAL_JSON") from exc


def _mac(payload: dict, key: bytes) -> str:
    return hmac.new(
        key, b"MMT-A9-REVIEW-ONLY-V1\x00" + _json(payload), hashlib.sha256,
    ).hexdigest()


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise A9Refused("A9_DUPLICATE_FIELD")
        result[name] = value
    return result


def _reject_float(_: str) -> None:
    raise A9Refused("A9_FLOAT_NOT_ALLOWED")


def _parse(envelope: bytes) -> tuple[dict, str]:
    if type(envelope) is not bytes or not 0 < len(envelope) <= 4096:
        raise A9Refused("A9_BOUNDED_ENVELOPE_REQUIRED")
    try:
        obj = json.loads(
            envelope.decode("ascii"), object_pairs_hook=_unique,
            parse_float=_reject_float, parse_constant=_reject_float,
        )
    except A9Refused:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise A9Refused("A9_BAD_JSON") from exc
    if type(obj) is not dict or set(obj) != {"payload", "mac_sha256"}:
        raise A9Refused("A9_BAD_ENVELOPE")
    p, mac = obj["payload"], obj["mac_sha256"]
    if type(p) is not dict or set(p) != _FIELDS:
        raise A9Refused("A9_BAD_PAYLOAD")
    if (type(mac) is not str or _SHA.fullmatch(mac) is None
            or type(p["schema"]) is not int or p["schema"] != 1
            or p["audience"] != _AUDIENCE
            or type(p["nonce"]) is not str or len(p["nonce"]) != 48
            or any(c not in "0123456789abcdef" for c in p["nonce"])
            or type(p["kind"]) is not str
            or p["kind"] not in {k.value for k in RuntimeKind}
            or any(type(p[key]) is not str
                   or _SHA.fullmatch(p[key]) is None for key in (
                       "policy", "worker", "source", "request", "a5_receipt",
                   ))
            or type(p["host"]) is not str or _ID.fullmatch(p["host"]) is None
            or type(p["issuer"]) is not str or _ID.fullmatch(p["issuer"]) is None
            or type(p["issued"]) is not int or type(p["expires"]) is not int
            or not 0 < p["expires"] - p["issued"] <= _MAX_AGE):
        raise A9Refused("A9_BAD_TICKET_FIELDS")
    return p, mac


class OfflineIntentLedger:
    """Crash-persistent, local review simulator with atomic one-time spends."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise A9Refused("A9_PRIVATE_PATH_REQUIRED")
        _approved_dir(path)
        existed = path.exists()
        if not existed:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(fd)
        self._db = sqlite3.connect(str(path), isolation_level=None, timeout=5)
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA trusted_schema=OFF")
            if existed:
                if self._db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID:
                    raise A9Refused("A9_UNKNOWN_LEDGER")
            else:
                self._db.execute(f"PRAGMA application_id={_APP_ID}")
                self._db.execute("""
                    CREATE TABLE tickets(
                      ticket_sha TEXT PRIMARY KEY,
                      kind TEXT NOT NULL, policy TEXT NOT NULL,
                      worker TEXT NOT NULL, source TEXT NOT NULL,
                      request TEXT NOT NULL, a5_receipt TEXT NOT NULL,
                      host TEXT NOT NULL, issuer TEXT NOT NULL,
                      issued INTEGER NOT NULL, expires INTEGER NOT NULL,
                      state TEXT NOT NULL CHECK(state IN
                        ('ISSUED','SPENT','REVOKED')),
                      spent_at INTEGER
                    )
                """)
            self._check()
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def _check(self) -> None:
        try:
            if self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise A9Refused("A9_LEDGER_CORRUPTION")
            for row in self._db.execute(
                "SELECT ticket_sha,kind,policy,worker,source,request,a5_receipt,"
                "host,issuer,issued,expires,state,spent_at FROM tickets"
            ):
                (ticket, kind, policy, worker, source, request, a5, host, issuer,
                 issued, expires, state, spent) = row
                if (any(type(v) is not str or _SHA.fullmatch(v) is None for v in (
                    ticket, policy, worker, source, request, a5,
                ))
                        or kind not in {k.value for k in RuntimeKind}
                        or type(host) is not str or _ID.fullmatch(host) is None
                        or type(issuer) is not str or _ID.fullmatch(issuer) is None
                        or type(issued) is not int or type(expires) is not int
                        or not 0 < expires - issued <= _MAX_AGE
                        or state not in {"ISSUED", "SPENT", "REVOKED"}
                        or (state == "SPENT") != (spent is not None)
                        or (spent is not None and (
                            type(spent) is not int or not issued <= spent < expires))):
                    raise A9Refused("A9_LEDGER_STATE_INVALID")
        except sqlite3.DatabaseError as exc:
            raise A9Refused("A9_LEDGER_UNREADABLE") from exc

    def _transaction(self, fn):
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._check()
                out = fn()
                self._db.execute("COMMIT")
                return out
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.DatabaseError as exc:
            raise A9Refused("A9_TRANSACTION_FAILED") from exc

    def issue(
        self, profile: RuntimeProfile, a5: ConsumedReview, *,
        worker: str, source: str, request: str, host: str, issuer: str,
        key: bytes, at: datetime, operator_id: int,
        allowed_operators: frozenset[int], operator_ack: bool = False,
        lifetime_seconds: int = _MAX_AGE,
    ) -> InertTicket:
        _nonproduction()
        _operator(operator_id, allowed_operators, operator_ack)
        _key(key)
        now = _second(at)
        if type(lifetime_seconds) is not int or not 1 <= lifetime_seconds <= _MAX_AGE:
            raise A9Refused("A9_LIFETIME_INVALID")
        policy = _scope(
            profile, a5, worker=worker, source=source, request=request,
            host=host, issuer=issuer,
        )
        payload = {
            "schema": 1, "audience": _AUDIENCE, "nonce": secrets.token_hex(24),
            "kind": profile.kind.value, "policy": policy,
            "worker": worker, "source": source, "request": request,
            "a5_receipt": a5.receipt_sha256, "host": host, "issuer": issuer,
            "issued": now, "expires": now + lifetime_seconds,
        }
        envelope = _json({"payload": payload, "mac_sha256": _mac(payload, key)})
        digest = hashlib.sha256(envelope).hexdigest()

        def insert() -> None:
            self._db.execute(
                "INSERT INTO tickets(ticket_sha,kind,policy,worker,source,"
                "request,a5_receipt,host,issuer,issued,expires,state) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,'ISSUED')",
                (digest, profile.kind.value, policy, worker, source, request,
                 a5.receipt_sha256, host, issuer, now, now + lifetime_seconds),
            )
        self._transaction(insert)
        return InertTicket(
            envelope, digest, datetime.fromtimestamp(now + lifetime_seconds, UTC),
        )

    def spend_review(
        self, envelope: bytes, *, profile: RuntimeProfile, a5: ConsumedReview,
        worker: str, source: str, request: str, host: str, issuer: str,
        key: bytes, at: datetime, operator_id: int,
        allowed_operators: frozenset[int], operator_ack: bool = False,
    ) -> SpentReview:
        """Only spend a review ticket: NO Worker invocation or grant."""
        _nonproduction()
        _operator(operator_id, allowed_operators, operator_ack)
        _key(key)
        now = _second(at)
        policy = _scope(
            profile, a5, worker=worker, source=source, request=request,
            host=host, issuer=issuer,
        )
        payload, mac = _parse(envelope)
        if not hmac.compare_digest(mac, _mac(payload, key)):
            raise A9Refused("A9_MAC_INVALID")
        if (payload["kind"] != profile.kind.value or payload["policy"] != policy
                or not hmac.compare_digest(payload["worker"], worker)
                or not hmac.compare_digest(payload["source"], source)
                or not hmac.compare_digest(payload["request"], request)
                or not hmac.compare_digest(payload["a5_receipt"], a5.receipt_sha256)
                or payload["host"] != host or payload["issuer"] != issuer
                or not payload["issued"] <= now < payload["expires"]):
            raise A9Refused("A9_SCOPE_OR_TIME_MISMATCH")
        digest = hashlib.sha256(envelope).hexdigest()
        expected = (
            profile.kind.value, policy, worker, source, request,
            a5.receipt_sha256, host, issuer, payload["issued"],
            payload["expires"], "ISSUED",
        )

        def consume() -> SpentReview:
            row = self._db.execute(
                "SELECT kind,policy,worker,source,request,a5_receipt,"
                "host,issuer,issued,expires,state FROM tickets WHERE ticket_sha=?",
                (digest,),
            ).fetchone()
            if row is None:
                raise A9Refused("A9_TICKET_NOT_ISSUED")
            if row != expected:
                raise A9Refused("A9_REVOKED_SPENT_OR_DRIFT")
            cur = self._db.execute(
                "UPDATE tickets SET state='SPENT',spent_at=? "
                "WHERE ticket_sha=? AND state='ISSUED'", (now, digest),
            )
            if cur.rowcount != 1:
                raise A9Refused("A9_ALREADY_SPENT")
            return SpentReview(digest, request)
        return self._transaction(consume)

    def revoke(
        self, ticket_sha256: str, *, operator_id: int,
        allowed_operators: frozenset[int], operator_ack: bool = False,
    ) -> None:
        _nonproduction()
        _operator(operator_id, allowed_operators, operator_ack)
        if type(ticket_sha256) is not str or _SHA.fullmatch(ticket_sha256) is None:
            raise A9Refused("A9_TICKET_DIGEST_REQUIRED")

        def cancel() -> None:
            cur = self._db.execute(
                "UPDATE tickets SET state='REVOKED' "
                "WHERE ticket_sha=? AND state='ISSUED'", (ticket_sha256,),
            )
            if cur.rowcount != 1:
                raise A9Refused("A9_UNKNOWN_OR_USED_TICKET")
        self._transaction(cancel)


__all__ = ["A9Refused", "InertTicket", "SpentReview", "OfflineIntentLedger"]
