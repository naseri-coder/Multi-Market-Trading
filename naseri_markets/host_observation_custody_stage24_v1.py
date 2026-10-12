"""Stage24 offline signed *host-observation statement* custody, never host proof.

The reviewer signs a Stage23 CLI receipt hash. A reviewer signature is NOT
remote attestation, not a kernel/gVisor certification and not a plugin license.
It does not enable Stage22/23 source execution, public installation or trades.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .a24_publisher_admission import _ed25519, _signature, canonical
from .disposable_gvisor_canary_stage23_v1 import _REQUIRED
from .secure_plugin_runtime_v1 import _IMAGE

_DOMAIN = b"MMT-STAGE24-HOST-OBSERVATION-REVIEW-V1\x00"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_CLAIM = frozenset({
    "version", "kind", "host_id", "image", "probe_sha256",
    "receipt_sha256", "sequence", "observed_at", "expires_at",
    "review_scope", "observation_checks",
})
_ENVELOPE = frozenset({"claim", "reviewer_signature_b64"})
_RECEIPT = frozenset({
    "status", "image_digest", "probe_sha256", "checks", "complete",
    "actual_host_isolation_independently_audited", "publisher_trust_conferred",
    "user_code_executed", "public_plugin_install_authorized",
    "live_trading_authorized", "telegram_sent", "broker_order_sent",
})
_STATEMENT = "OBSERVATION_STATEMENT_RECORDED_NOT_RUNTIME_ATTESTED"


class Stage24Refused(ValueError):
    """Fail closed without leaking reviewer secrets, host path or receipts."""


def _guard(ack: bool) -> None:
    if (ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise Stage24Refused("EXPLICIT_NONPRODUCTION_REVIEW_REQUIRED")


def _unique(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise Stage24Refused("DUPLICATE_EVIDENCE_JSON_KEY")
        obj[k] = v
    return obj


def _json(raw: bytes, *, max_bytes: int) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= max_bytes:
        raise Stage24Refused("BOUNDED_HOST_EVIDENCE_REQUIRED")
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             Stage24Refused("NONFINITE_EVIDENCE_JSON")))
    except Stage24Refused:
        raise
    except (ValueError, UnicodeError) as exc:
        raise Stage24Refused("INVALID_HOST_EVIDENCE_JSON") from exc
    if type(obj) is not dict:
        raise Stage24Refused("EXACT_HOST_EVIDENCE_OBJECT_REQUIRED")
    return obj


def _valid_receipt(raw: bytes) -> tuple[dict, str]:
    item = _json(raw, max_bytes=4096)
    if (set(item) != _RECEIPT
            or item.get("status") != (
                "OBSERVED_SINGLE_DISPOSABLE_HOST_CANARY_NOT_SECURITY_CERTIFIED")
            or type(item.get("checks")) is not dict
            or set(item["checks"]) != _REQUIRED
            or any(v is not True for v in item["checks"].values())
            or any(type(v) is not bool for v in item["checks"].values())
            or item.get("complete") is not True
            or type(item.get("image_digest")) is not str
            or not _SHA.fullmatch(item["image_digest"])
            or type(item.get("probe_sha256")) is not str
            or not _SHA.fullmatch(item["probe_sha256"])
            or any(item.get(flag) is not False for flag in (
                "actual_host_isolation_independently_audited",
                "publisher_trust_conferred", "user_code_executed",
                "public_plugin_install_authorized", "live_trading_authorized",
                "telegram_sent", "broker_order_sent"))):
        raise Stage24Refused("UNSAFE_OR_UNVERIFIED_STAGE23_RECEIPT")
    return item, hashlib.sha256(raw).hexdigest()


def _claim(raw: bytes) -> tuple[dict, bytes, str]:
    obj = _json(raw, max_bytes=8192)
    if set(obj) != _ENVELOPE or canonical(obj) != raw:
        raise Stage24Refused("EXACT_CANONICAL_SIGNED_OBSERVATION_REQUIRED")
    claim = obj["claim"]
    if type(claim) is not dict or set(claim) != _CLAIM:
        raise Stage24Refused("EXACT_SIGNED_REVIEW_CLAIM_REQUIRED")
    if (type(claim["version"]) is not int or claim["version"] != 1
            or claim["kind"] != "disposable_host_canary_observation"
            or claim["review_scope"] != "manual_single_run_no_security_certification"
            or type(claim["host_id"]) is not str
            or not _HOST.fullmatch(claim["host_id"])
            or type(claim["image"]) is not str
            or not _IMAGE.fullmatch(claim["image"])
            or any(type(claim[key]) is not str or not _SHA.fullmatch(claim[key])
                   for key in ("probe_sha256", "receipt_sha256"))
            or type(claim["sequence"]) is not int
            or not 1 <= claim["sequence"] < 2**63
            or type(claim["observed_at"]) is not int
            or type(claim["expires_at"]) is not int
            or not 1 <= claim["observed_at"] < claim["expires_at"]
            or claim["expires_at"] - claim["observed_at"] > 86400
            or type(claim["observation_checks"]) is not dict
            or set(claim["observation_checks"]) != _REQUIRED
            or any(type(v) is not bool or v is not True
                   for v in claim["observation_checks"].values())):
        raise Stage24Refused("UNSUPPORTED_REVIEW_SCOPE_OR_CLAIM")
    try:
        signature = _signature(obj["reviewer_signature_b64"])
    except ValueError as exc:
        raise Stage24Refused("INVALID_REVIEW_SIGNATURE_ENCODING") from exc
    return claim, signature, hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ObservationReceipt:
    host_id: str
    sequence: int
    receipt_sha256: str
    reviewer_statement_sha256: str
    status: str = _STATEMENT
    real_host_execution_proven: bool = False
    independent_security_certification: bool = False
    public_plugin_install_authorized: bool = False
    telegram_publication_authorized: bool = False
    live_trading_authorized: bool = False


def _private_path(path: Path) -> bool:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.parent.is_dir()
            or path.parent.is_symlink()):
        return False
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
        return False
    if path.exists():
        data = path.lstat()
        return (stat.S_ISREG(data.st_mode) and data.st_nlink == 1
                and data.st_uid == os.geteuid()
                and not stat.S_IMODE(data.st_mode) & 0o077)
    return True


class HostObservationLedger:
    """Out-of-band reviewer key pin; local durable floor, not TPM attestation."""

    def __init__(self, path: Path, *, reviewer_public_key: bytes,
                 approved_reviewer_key_sha256: str,
                 operator_ack: bool = False) -> None:
        _guard(operator_ack)
        if not _private_path(path):
            raise Stage24Refused("OWNER_PRIVATE_OBSERVATION_LEDGER_REQUIRED")
        if (type(reviewer_public_key) is not bytes or len(reviewer_public_key) != 32
                or type(approved_reviewer_key_sha256) is not str
                or not _SHA.fullmatch(approved_reviewer_key_sha256)
                or not hmac.compare_digest(
                    hashlib.sha256(reviewer_public_key).hexdigest(),
                    approved_reviewer_key_sha256)):
            raise Stage24Refused("INDEPENDENT_REVIEWER_KEY_PIN_REQUIRED")
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                         | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(path, timeout=0.2, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.key = reviewer_public_key
        self.db.execute("""CREATE TABLE IF NOT EXISTS stage24_issuer(
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            public_key BLOB NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS stage24_host_observations(
            host_id TEXT PRIMARY KEY,
            image TEXT NOT NULL, probe_sha256 TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            observation_sha256 TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL,
            signed_statement BLOB NOT NULL,
            expired_at INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1)))""")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT public_key FROM stage24_issuer WHERE singleton=1"
            ).fetchone()
            if row is None:
                self.db.execute(
                    "INSERT INTO stage24_issuer VALUES(1,?)",
                    (reviewer_public_key,))
            elif not hmac.compare_digest(row["public_key"], reviewer_public_key):
                raise Stage24Refused("REVIEWER_ANCHOR_CHANGED")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self) -> None:
        self.db.close()

    def _verify(self, signed: bytes, receipt: bytes, *,
                expected_host_id: str, expected_image: str,
                now: int) -> tuple[dict, str, str]:
        claim, sig, statement_sha = _claim(signed)
        data, receipt_sha = _valid_receipt(receipt)
        if (type(expected_host_id) is not str
                or type(expected_image) is not str
                or type(now) is not int
                or claim["host_id"] != expected_host_id
                or claim["image"] != expected_image
                or claim["image"].rsplit("@sha256:", 1)[-1] != data["image_digest"]
                or claim["probe_sha256"] != data["probe_sha256"]
                or claim["observation_checks"] != data["checks"]
                or not hmac.compare_digest(claim["receipt_sha256"], receipt_sha)
                or not claim["observed_at"] <= now < claim["expires_at"]):
            raise Stage24Refused("REVIEWED_RECEIPT_IDENTITY_OR_TIME_MISMATCH")
        try:
            _ed25519(self.key, sig, _DOMAIN + canonical(claim))
        except ValueError as exc:
            raise Stage24Refused("UNTRUSTED_REVIEWER_SIGNATURE") from exc
        return claim, statement_sha, receipt_sha

    def record(self, signed: bytes, receipt: bytes, *,
               expected_host_id: str, expected_image: str,
               now: int, operator_ack: bool = False) -> ObservationReceipt:
        _guard(operator_ack)
        claim, sha, receipt_sha = self._verify(
            signed, receipt, expected_host_id=expected_host_id,
            expected_image=expected_image, now=now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT * FROM stage24_host_observations WHERE host_id=?",
                (expected_host_id,)).fetchone()
            if existing is not None and (
                    existing["revoked"] or claim["sequence"] <= existing["sequence"]
                    or existing["image"] != expected_image
                    or existing["probe_sha256"] != claim["probe_sha256"]):
                raise Stage24Refused("REVOKED_ROLLBACK_OR_CHANGED_HOST_POLICY")
            self.db.execute(
                "INSERT INTO stage24_host_observations VALUES "
                "(?,?,?,?,?,?,?,?,0) ON CONFLICT(host_id) DO UPDATE SET "
                "sequence=excluded.sequence,"
                "observation_sha256=excluded.observation_sha256,"
                "receipt_sha256=excluded.receipt_sha256,"
                "signed_statement=excluded.signed_statement,"
                "expired_at=excluded.expired_at",
                (expected_host_id, expected_image, claim["probe_sha256"],
                 claim["sequence"], sha, receipt_sha, signed,
                 claim["expires_at"]))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return ObservationReceipt(expected_host_id, claim["sequence"],
                                  receipt_sha, sha)

    def revoke(self, host_id: str, *, operator_ack: bool = False) -> None:
        _guard(operator_ack)
        if type(host_id) is not str or not _HOST.fullmatch(host_id):
            raise Stage24Refused("HOST_ID_REQUIRED")
        result = self.db.execute(
            "UPDATE stage24_host_observations SET revoked=1 WHERE host_id=?",
            (host_id,))
        if result.rowcount != 1:
            raise Stage24Refused("UNKNOWN_HOST_OBSERVATION")

    def current(self, signed: bytes, receipt: bytes, *,
                expected_host_id: str, expected_image: str,
                now: int) -> ObservationReceipt:
        claim, sha, receipt_sha = self._verify(
            signed, receipt, expected_host_id=expected_host_id,
            expected_image=expected_image, now=now)
        row = self.db.execute(
            "SELECT * FROM stage24_host_observations WHERE host_id=?",
            (expected_host_id,)).fetchone()
        if (row is None or row["revoked"] or row["sequence"] != claim["sequence"]
                or not hmac.compare_digest(row["observation_sha256"], sha)
                or not hmac.compare_digest(row["receipt_sha256"], receipt_sha)
                or not hmac.compare_digest(row["signed_statement"], signed)):
            raise Stage24Refused("HOST_OBSERVATION_NOT_CURRENT")
        return ObservationReceipt(expected_host_id, claim["sequence"],
                                  receipt_sha, sha)


def read_admin_host_security_status(state_dir: Path) -> dict:
    """No file creation, signer key loading, or external calls in Telegram.

    No keys, host IDs or receipt bytes are exposed. This summarizes *local*
    records as UNATTESTED even if an attacker controls the SQLite database.
    """
    path = Path(state_dir) / "stage24_host_observation.sqlite"
    denied = {
        "status": "HOST_RUNTIME_INDEPENDENTLY_UNVERIFIED",
        "observations": 0, "reviewed_host_security": False,
        "public_plugin_install_authorized": False,
        "telegram_publication_authorized": False,
        "broker_order_authorized": False,
    }
    if path.is_symlink():
        raise Stage24Refused("UNTRUSTED_READONLY_ADMIN_EVIDENCE")
    if not path.exists():
        return denied
    if not _private_path(path):
        raise Stage24Refused("UNTRUSTED_READONLY_ADMIN_EVIDENCE")
    uri = "file:" + quote(str(path.absolute()), safe="/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, isolation_level=None) as db:
            db.execute("PRAGMA query_only=ON")
            count = db.execute(
                "SELECT COUNT(*) FROM stage24_host_observations "
                "WHERE revoked=0").fetchone()[0]
        return {**denied, "observations": min(count, 64)}
    except (sqlite3.DatabaseError, ValueError) as exc:
        raise Stage24Refused("INVALID_READONLY_ADMIN_EVIDENCE") from exc


__all__ = [
    "Stage24Refused", "ObservationReceipt", "HostObservationLedger",
    "read_admin_host_security_status", "_DOMAIN",
]
