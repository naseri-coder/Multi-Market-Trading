"""A10 offline authenticated envelope protocol (no socket, no private source).

HMAC-SHA256 proves possession of an independently provisioned symmetric key;
it is NOT asymmetric publisher provenance, TLS, a licensing authority, or a
security sandbox. Production would require audited mTLS, key custody and an
owner-controlled external execution service in a separate authorization.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from pathlib import Path

from .delivery_ledger import open_sqlite

DOMAIN = b"NASERI-MARKETS-A10-HMAC-SHA256-V1\x00"
MAX_PACKET = 20000
MAX_TTL = 30
MAX_CLOCK_SKEW = 5
_FIELDS = frozenset({
    "version", "key_id", "direction", "engine_id", "engine_version",
    "nonce", "request_nonce", "issued_at", "expires_at", "payload",
})
_KEY_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_MAC = re.compile(r"[0-9a-f]{64}\Z")


class ProtocolRefused(ValueError):
    """Invalid, unauthorized, replayed, revoked or expired A10 packet."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolRefused("A10_DUPLICATE_KEY")
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _validate_body(body: object) -> dict:
    if not isinstance(body, dict) or set(body) != _FIELDS:
        raise ProtocolRefused("A10_FIELDS")
    if type(body["version"]) is not int or body["version"] != 1:
        raise ProtocolRefused("A10_VERSION")
    if type(body["key_id"]) is not str or not _KEY_ID.fullmatch(body["key_id"]):
        raise ProtocolRefused("A10_KEY_ID")
    if body["direction"] not in ("to_owner", "to_bot") or type(body["direction"]) is not str:
        raise ProtocolRefused("A10_DIRECTION")
    for key in ("engine_id", "engine_version"):
        if type(body[key]) is not str or not 1 <= len(body[key]) <= 80:
            raise ProtocolRefused("A10_IDENTITY")
    if type(body["nonce"]) is not str or not _NONCE.fullmatch(body["nonce"]):
        raise ProtocolRefused("A10_NONCE")
    if type(body["request_nonce"]) is not str or (
        body["request_nonce"] != "" and not _NONCE.fullmatch(body["request_nonce"])
    ):
        raise ProtocolRefused("A10_REQUEST_NONCE")
    if type(body["issued_at"]) is not int or type(body["expires_at"]) is not int:
        raise ProtocolRefused("A10_CLOCK")
    if not 0 < body["expires_at"] - body["issued_at"] <= MAX_TTL:
        raise ProtocolRefused("A10_TTL")
    if not isinstance(body["payload"], dict):
        raise ProtocolRefused("A10_PAYLOAD")
    if body["direction"] == "to_owner" and body["request_nonce"] != "":
        raise ProtocolRefused("A10_REQUEST_LINK")
    if body["direction"] == "to_bot" and body["request_nonce"] == "":
        raise ProtocolRefused("A10_RESPONSE_LINK")
    return body


def sign_packet(body: dict, *, key: bytes) -> bytes:
    """Caller must provision a *distinct* >=32-byte key per direction.

    This function never generates, stores, logs or transmits key material.
    """
    if type(key) is not bytes or len(key) < 32:
        raise ProtocolRefused("A10_WEAK_OR_MISSING_KEY")
    _validate_body(body)
    blob = _canonical(body)
    tag = hmac.new(key, DOMAIN + blob, hashlib.sha256).hexdigest()
    packet = _canonical({"body": body, "mac": tag})
    if len(packet) > MAX_PACKET:
        raise ProtocolRefused("A10_PACKET_TOO_LARGE")
    return packet


def verify_packet(
    packet: bytes, *, key: bytes, key_id: str,
    direction: str, engine_id: str, engine_version: str, now: int,
) -> dict:
    """Strict parse + constant-time message authentication + expiry."""
    if type(key) is not bytes or len(key) < 32:
        raise ProtocolRefused("A10_WEAK_OR_MISSING_KEY")
    if type(now) is not int or now <= 0:
        raise ProtocolRefused("A10_NOW_REQUIRED")
    if type(packet) is not bytes or not 0 < len(packet) <= MAX_PACKET:
        raise ProtocolRefused("A10_PACKET_SIZE")
    try:
        parsed = json.loads(
            packet.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ProtocolRefused("A10_NONFINITE")),
        )
    except (UnicodeError, ValueError) as exc:
        raise ProtocolRefused("A10_BAD_JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"body", "mac"}:
        raise ProtocolRefused("A10_WIRE_FIELDS")
    body = _validate_body(parsed["body"])
    if type(parsed["mac"]) is not str or not _MAC.fullmatch(parsed["mac"]):
        raise ProtocolRefused("A10_MAC_FORMAT")
    expected = hmac.new(key, DOMAIN + _canonical(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parsed["mac"]):
        raise ProtocolRefused("A10_MAC")
    if (
        body["key_id"] != key_id or body["direction"] != direction
        or body["engine_id"] != engine_id
        or body["engine_version"] != engine_version
    ):
        raise ProtocolRefused("A10_IDENTITY_SCOPE")
    if body["issued_at"] > now + MAX_CLOCK_SKEW or body["expires_at"] < now:
        raise ProtocolRefused("A10_EXPIRED_OR_FUTURE")
    return body


class ReplayFence:
    """Persistent nonce ledger and operator revocation, separate from signals.

    Revocation is durable and checked transactionally before accepting
    one signed response. Never truncates previously seen nonces by expiry;
    operational retention must be defined separately before production.
    """

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ProtocolRefused("A10_UNSAFE_FENCE_PATH")
        self._db = open_sqlite(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS a10_seen("
            "direction TEXT NOT NULL, key_id TEXT NOT NULL,"
            "nonce TEXT NOT NULL, PRIMARY KEY(direction,key_id,nonce))"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS a10_revoked("
            "key_id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL"
            " DEFAULT CURRENT_TIMESTAMP)"
        )

    def close(self) -> None:
        self._db.close()

    def require_active(self, key_id: str) -> None:
        if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
            raise ProtocolRefused("A10_KEY_ID")
        row = self._db.execute(
            "SELECT 1 FROM a10_revoked WHERE key_id=?", (key_id,)
        ).fetchone()
        if row is not None:
            raise ProtocolRefused("A10_REVOKED")

    def revoke(self, key_id: str) -> None:
        if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
            raise ProtocolRefused("A10_KEY_ID")
        self._db.execute(
            "INSERT OR IGNORE INTO a10_revoked(key_id) VALUES(?)",
            (key_id,),
        )

    def consume(self, *, direction: str, key_id: str, nonce: str) -> None:
        if direction not in ("to_owner", "to_bot") or type(direction) is not str:
            raise ProtocolRefused("A10_DIRECTION")
        if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
            raise ProtocolRefused("A10_KEY_ID")
        if type(nonce) is not str or not _NONCE.fullmatch(nonce):
            raise ProtocolRefused("A10_NONCE")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self.require_active(key_id)
            try:
                self._db.execute(
                    "INSERT INTO a10_seen(direction,key_id,nonce) VALUES(?,?,?)",
                    (direction, key_id, nonce),
                )
            except sqlite3.IntegrityError as exc:
                raise ProtocolRefused("A10_REPLAY") from exc
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def is_revoked(self, key_id: str) -> bool:
        try:
            self.require_active(key_id)
        except ProtocolRefused:
            return True
        return False
