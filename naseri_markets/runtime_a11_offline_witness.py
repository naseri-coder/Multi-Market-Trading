"""RUNTIME-A11: offline, operator-carried witness receipts (NONPRODUCTION ONLY).

No independent media has been designated. HMAC proves only knowledge of a
shared test key. A11 never issues an execution capability or lifts A6.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .runtime_a10_evidence_anchor import (
    A10Refused,
    _canonical,
    _nonproduction,
    _operator,
    _parse_anchor,
    _private_path,
    _second,
)

_APP_ID = 0x4D4D544B
_AUDIENCE = "MMT-RUNTIME-A11-OFFLINE-WITNESS-REVIEW-V1"
_STATUS = "OPERATOR_CARRIED_CLAIM_NO_INDEPENDENT_CUSTODY"
_GENESIS = "0" * 64
_KEYS = frozenset({
    "schema", "audience", "status", "witness_id", "witness_sequence",
    "previous_receipt_sha256", "a10_anchor_sha256", "a10_ledger_id",
    "a10_sequence", "a10_record_hash", "witness_epoch",
})
_MAX_BYTES = 4096


class A11Refused(ValueError):
    """Stable, non-disclosing validation or custody simulation refusal."""


@dataclass(frozen=True, slots=True)
class WitnessReceipt:
    envelope: bytes
    receipt_sha256: str
    witness_sequence: int
    a10_sequence: int
    status: str = "A11_OFFLINE_WITNESS_RECEIPT_NOT_INDEPENDENTLY_STORED"
    independent_custody_proven: bool = False
    monotonic_hardware_proven: bool = False
    actual_host_isolation_proven: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


@dataclass(frozen=True, slots=True)
class WitnessComparison:
    witness_sequence: int
    a10_sequence: int
    receipt_sha256: str
    status: str
    signature_is_shared_key_claim: bool = True
    independent_custody_proven: bool = False
    verified_freshness_proven: bool = False
    distributed_rollback_resistance_proven: bool = False
    actual_host_isolation_proven: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


def _key(value: bytes) -> None:
    if type(value) is not bytes or not 32 <= len(value) <= 4096:
        raise A11Refused("A11_EXPLICIT_OUT_OF_BAND_KEY_REQUIRED")


def _sha(value: object, length: int = 64) -> bool:
    return (type(value) is str and len(value) == length
            and all(c in "0123456789abcdef" for c in value))


def _mac(payload: dict, key: bytes) -> str:
    return hmac.new(
        key, b"MMT-A11-OFFLINE-WITNESS-V1\x00" + _canonical(payload),
        hashlib.sha256,
    ).hexdigest()


def _receipt_bytes(payload: dict, key: bytes) -> bytes:
    return _canonical({"payload": payload, "mac_sha256": _mac(payload, key)})


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise A11Refused("A11_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_float(_: str) -> None:
    raise A11Refused("A11_NONINTEGER_NUMBER")


def _parse_signed(raw: bytes, key: bytes) -> dict:
    _key(key)
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
        raise A11Refused("A11_BOUNDED_RECEIPT_REQUIRED")
    try:
        value = json.loads(
            raw.decode("ascii"), object_pairs_hook=_unique,
            parse_float=_reject_float, parse_constant=_reject_float,
        )
    except A11Refused:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise A11Refused("A11_MALFORMED_RECEIPT") from exc
    if (type(value) is not dict or set(value) != {"payload", "mac_sha256"}
            or type(value["payload"]) is not dict
            or set(value["payload"]) != _KEYS
            or not _sha(value["mac_sha256"])
            or _canonical(value) != raw):
        raise A11Refused("A11_NONCANONICAL_RECEIPT")
    p = value["payload"]
    if (type(p["schema"]) is not int or p["schema"] != 1
            or p["audience"] != _AUDIENCE or p["status"] != _STATUS
            or not _sha(p["witness_id"], 32)
            or type(p["witness_sequence"]) is not int
            or p["witness_sequence"] <= 0
            or not _sha(p["previous_receipt_sha256"])
            or not _sha(p["a10_anchor_sha256"])
            or not _sha(p["a10_ledger_id"], 32)
            or type(p["a10_sequence"]) is not int or p["a10_sequence"] <= 0
            or not _sha(p["a10_record_hash"])
            or type(p["witness_epoch"]) is not int or p["witness_epoch"] <= 0
            or (p["witness_sequence"] == 1
                and p["previous_receipt_sha256"] != _GENESIS)):
        raise A11Refused("A11_RECEIPT_SCHEMA_OR_SCOPE_INVALID")
    if not hmac.compare_digest(value["mac_sha256"], _mac(p, key)):
        raise A11Refused("A11_HMAC_MISMATCH")
    return p


def _anchor(raw: bytes) -> dict:
    try:
        return _parse_anchor(raw)
    except A10Refused as exc:
        raise A11Refused("A11_EXACT_A10_ANCHOR_REQUIRED") from exc


def compare_witness_receipt(
    receipt: bytes, anchor: bytes, *, key: bytes,
    expected_witness_id: str, trusted_floor_receipt: bytes | None = None,
) -> WitnessComparison:
    """Authenticate claims and compare to an explicitly operator-supplied floor.

    A verified MAC plus caller-supplied floor is NOT independent media custody.
    A missing floor cannot detect stale but authentic receipts.
    """
    _nonproduction()
    p = _parse_signed(receipt, key)
    a = _anchor(anchor)
    if not _sha(expected_witness_id, 32):
        raise A11Refused("A11_PINNED_WITNESS_ID_REQUIRED")
    if (p["witness_id"] != expected_witness_id
            or p["a10_ledger_id"] != a["ledger_id"]
            or p["a10_sequence"] != a["sequence"]
            or p["a10_record_hash"] != a["record_hash"]
            or not hmac.compare_digest(
                p["a10_anchor_sha256"], hashlib.sha256(anchor).hexdigest(),
            )):
        raise A11Refused("A11_WITNESS_OR_A10_PIN_SCOPE_MISMATCH")
    status = "A11_HMAC_REVIEW_WITHOUT_TRUSTED_FLOOR"
    if trusted_floor_receipt is not None:
        floor = _parse_signed(trusted_floor_receipt, key)
        if floor["witness_id"] != expected_witness_id:
            raise A11Refused("A11_FLOOR_DIFFERENT_WITNESS")
        if p["witness_sequence"] < floor["witness_sequence"]:
            raise A11Refused("A11_STALE_RECEIPT_BELOW_FLOOR")
        if p["witness_sequence"] == floor["witness_sequence"]:
            if not hmac.compare_digest(
                hashlib.sha256(receipt).hexdigest(),
                hashlib.sha256(trusted_floor_receipt).hexdigest(),
            ):
                raise A11Refused("A11_SAME_SEQUENCE_FORK")
            status = "A11_SAME_OPERATOR_SUPPLIED_FLOOR"
        elif (p["witness_sequence"] != floor["witness_sequence"] + 1
              or p["previous_receipt_sha256"]
              != hashlib.sha256(trusted_floor_receipt).hexdigest()
              or p["a10_sequence"] <= floor["a10_sequence"]
              or p["a10_ledger_id"] != floor["a10_ledger_id"]):
            raise A11Refused("A11_MISSING_OR_DIVERGENT_WITNESS_LINK")
        else:
            status = "A11_ONE_CONSECUTIVE_SUPPLIED_LINK_MATCHED"
    return WitnessComparison(
        p["witness_sequence"], p["a10_sequence"],
        hashlib.sha256(receipt).hexdigest(), status,
    )


class OfflineWitnessLedger:
    """Private SQLite witness exercise, to run ONLY on separately held media.

    This class does not test separation and cannot prevent privileged rollback.
    """

    def __init__(self, path: Path, *, signing_key: bytes) -> None:
        _nonproduction()
        _key(signing_key)
        _private_path(path)
        self._key = signing_key
        existed = path.exists()
        if not existed:
            try:
                fd = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                    0o600,
                )
                os.close(fd)
            except OSError as exc:
                raise A11Refused("A11_PRIVATE_LEDGER_CREATE_FAILED") from exc
        self._db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA trusted_schema=OFF")
            if existed:
                if self._db.execute("PRAGMA application_id").fetchone()[0] != _APP_ID:
                    raise A11Refused("A11_UNKNOWN_WITNESS_LEDGER")
            else:
                self._db.execute(f"PRAGMA application_id={_APP_ID}")
                self._db.execute("CREATE TABLE witness_identity(id TEXT NOT NULL)")
                self._db.execute(
                    "INSERT INTO witness_identity(id) VALUES(?)",
                    (secrets.token_hex(16),),
                )
                self._db.execute("""
                    CREATE TABLE witness_records(
                      seq INTEGER PRIMARY KEY, a10_id TEXT NOT NULL,
                      a10_seq INTEGER NOT NULL, a10_hash TEXT NOT NULL,
                      anchor_sha TEXT NOT NULL, previous_receipt TEXT NOT NULL,
                      mac_sha TEXT NOT NULL, receipt_sha TEXT NOT NULL,
                      observed_epoch INTEGER NOT NULL
                    )
                """)
            self._check()
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def _check(self) -> tuple[str, int, str, int, str, int]:
        try:
            if self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise A11Refused("A11_SQLITE_INTEGRITY_FAILURE")
            ids = self._db.execute("SELECT id FROM witness_identity").fetchall()
            if len(ids) != 1 or not _sha(ids[0][0], 32):
                raise A11Refused("A11_WITNESS_IDENTITY_DRIFT")
            witness = ids[0][0]
            seq, prior, prior_a10, a10_id, epoch = 0, _GENESIS, 0, "", 0
            for row in self._db.execute(
                "SELECT seq,a10_id,a10_seq,a10_hash,anchor_sha,"
                "previous_receipt,mac_sha,receipt_sha,observed_epoch "
                "FROM witness_records ORDER BY seq"
            ):
                n, led_id, aseq, ahash, anchor_sha, before, mac, receipt, when = row
                if (type(n) is not int or n != seq + 1
                        or not _sha(led_id, 32)
                        or (seq > 0 and led_id != a10_id)
                        or type(aseq) is not int or aseq <= prior_a10
                        or not _sha(ahash) or not _sha(anchor_sha)
                        or before != prior or not _sha(mac) or not _sha(receipt)
                        or type(when) is not int or when <= 0 or when < epoch):
                    raise A11Refused("A11_WITNESS_CHAIN_DRIFT")
                payload = self._payload(
                    witness, n, before, anchor_sha, led_id, aseq, ahash, when,
                )
                if (not hmac.compare_digest(mac, _mac(payload, self._key))
                        or not hmac.compare_digest(
                            receipt,
                            hashlib.sha256(
                                _canonical({"payload": payload, "mac_sha256": mac}),
                            ).hexdigest(),
                        )):
                    raise A11Refused("A11_WITNESS_MAC_OR_CHAIN_TAMPER")
                seq, prior, prior_a10, a10_id, epoch = (
                    n, receipt, aseq, led_id, when,
                )
            return witness, seq, prior, prior_a10, a10_id, epoch
        except sqlite3.DatabaseError as exc:
            raise A11Refused("A11_WITNESS_LEDGER_UNREADABLE") from exc

    @staticmethod
    def _payload(
        witness: str, seq: int, prior: str, anchor_sha: str, ledger: str,
        aseq: int, ahash: str, epoch: int,
    ) -> dict:
        return {
            "schema": 1, "audience": _AUDIENCE, "status": _STATUS,
            "witness_id": witness, "witness_sequence": seq,
            "previous_receipt_sha256": prior, "a10_anchor_sha256": anchor_sha,
            "a10_ledger_id": ledger, "a10_sequence": aseq,
            "a10_record_hash": ahash, "witness_epoch": epoch,
        }

    def witness_id(self) -> str:
        _nonproduction()
        return self._check()[0]

    def record(
        self, anchor: bytes, *, at: datetime, operator_id: int,
        authorized_operators: frozenset[int], operator_ack: bool = False,
        prior_receipt: bytes | None = None,
    ) -> WitnessReceipt:
        """Append if newer A10 seq; requires prior receipt on subsequent entries."""
        _nonproduction()
        _operator(operator_id, authorized_operators, operator_ack)
        timestamp = _second(at)
        a = _anchor(anchor)
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                witness, n, last, prior_seq, a10_id, epoch = self._check()
                if n:
                    if prior_receipt is None:
                        raise A11Refused("A11_PREVIOUS_RECEIPT_REQUIRED")
                    p = _parse_signed(prior_receipt, self._key)
                    if (p["witness_id"] != witness
                            or p["witness_sequence"] != n
                            or not hmac.compare_digest(
                                hashlib.sha256(prior_receipt).hexdigest(), last,
                            )):
                        raise A11Refused("A11_PREVIOUS_RECEIPT_NOT_CURRENT")
                elif prior_receipt is not None:
                    raise A11Refused("A11_UNEXPECTED_GENESIS_PRIOR_RECEIPT")
                if (a["sequence"] <= prior_seq or timestamp < epoch
                        or n and a["ledger_id"] != a10_id):
                    raise A11Refused("A11_WITNESS_REGRESSION_OR_FORK")
                payload = self._payload(
                    witness, n + 1, last,
                    hashlib.sha256(anchor).hexdigest(), a["ledger_id"],
                    a["sequence"], a["record_hash"], timestamp,
                )
                envelope = _receipt_bytes(payload, self._key)
                digest = hashlib.sha256(envelope).hexdigest()
                self._db.execute(
                    "INSERT INTO witness_records(seq,a10_id,a10_seq,a10_hash,"
                    "anchor_sha,previous_receipt,mac_sha,receipt_sha,observed_epoch)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (n + 1, a["ledger_id"], a["sequence"], a["record_hash"],
                     payload["a10_anchor_sha256"], last, _mac(payload, self._key),
                     digest, timestamp),
                )
                self._db.execute("COMMIT")
                return WitnessReceipt(envelope, digest, n + 1, a["sequence"])
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.DatabaseError as exc:
            raise A11Refused("A11_WITNESS_TRANSACTION_FAILED") from exc


__all__ = [
    "A11Refused", "WitnessReceipt", "WitnessComparison",
    "OfflineWitnessLedger", "compare_witness_receipt",
]
