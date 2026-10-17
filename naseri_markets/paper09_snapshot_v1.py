"""Explicit offline, dual-ledger PAPER snapshot and isolated restore rehearsal.

No production, broker, Telegram, migrations, live deployment or hidden retry.
BOTH old SQLite writer locks are taken before copies to fence local writers.
The manifest uses checksums for corruption detection, NOT signatures.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
from contextlib import ExitStack, closing
from pathlib import Path
from urllib.parse import quote

from .brooks_stage10_recovery_v1 import reconcile_stage10_paper

DATABASES = ("custom_paper.db", "brooks_stage10_paper.sqlite")
MAX_BYTES = 64 * 1024 * 1024


class Paper09SnapshotRefused(ValueError):
    """Safe stop: leave existing source/bundle untouched."""


def _consent() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or os.geteuid() == 0):
        raise Paper09SnapshotRefused("P09_NONROOT_NONPRODUCTION_ACK_REQUIRED")


def _private_dir(path: Path) -> Path:
    p = path.absolute()
    if p.is_symlink() or not p.is_dir():
        raise Paper09SnapshotRefused("P09_PRIVATE_DIRECTORY_REQUIRED")
    info = p.stat()
    if (info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise Paper09SnapshotRefused("P09_PRIVATE_DIRECTORY_0700_REQUIRED")
    return p


def _file(path: Path, *, maximum: int = MAX_BYTES) -> Path:
    if path.is_symlink() or not path.is_file():
        raise Paper09SnapshotRefused("P09_REGULAR_FILE_REQUIRED")
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or not 0 < info.st_size <= maximum):
        raise Paper09SnapshotRefused("P09_PRIVATE_BOUNDED_FILE_REQUIRED")
    return path


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for data in iter(lambda: source.read(1 << 20), b""):
            digest.update(data)
    return digest.hexdigest()


def _sqlite_uri(path: Path, mode: str) -> str:
    return "file:" + quote(str(path.absolute()), safe="/") + "?mode=" + mode


def _verified_sqlite(path: Path) -> None:
    _file(path)
    with closing(sqlite3.connect(
        _sqlite_uri(path, "ro"), uri=True, timeout=5,
    )) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise Paper09SnapshotRefused("P09_SQLITE_INTEGRITY_REFUSED")


def _canonical(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _unique(pairs):
    output = {}
    for name, value in pairs:
        if name in output:
            raise Paper09SnapshotRefused("P09_DUPLICATE_MANIFEST_KEYS")
        output[name] = value
    return output


def _create_private(parent: Path, name: str) -> Path:
    _private_dir(parent)
    target = parent / name
    if target.exists() or target.is_symlink():
        raise Paper09SnapshotRefused("P09_NO_OVERWRITE")
    target.mkdir(mode=0o700)
    return target


def snapshot_pair(state_dir: str | Path, bundle_parent: str | Path,
                  name: str = "p09-backup") -> dict:
    """Create one NEW owner-private offline copy under shared two-DB locks.

    SQLite BEGIN IMMEDIATE on both files is deliberately ordered. Existing
    writer activity is rejected after bounded wait; no incomplete output
    remains if the backup is interrupted. Source databases are not changed.
    """
    _consent()
    state = _private_dir(Path(state_dir))
    parent = _private_dir(Path(bundle_parent))
    if state == parent or state in parent.parents or parent in state.parents:
        raise Paper09SnapshotRefused("P09_SEPARATE_BACKUP_PARENT_REQUIRED")
    if name != "p09-backup":
        raise Paper09SnapshotRefused("P09_FIXED_BACKUP_NAME_REQUIRED")
    files = [_file(state / n) for n in DATABASES]
    if reconcile_stage10_paper(state)["status"] not in (
        "MATCHED_PAPER_ORDER", "CLEAN_NO_SIGNALS",
    ):
        raise Paper09SnapshotRefused("P09_SOURCE_NEEDS_MANUAL_RECONCILIATION")
    destination = _create_private(parent, name)
    try:
        with ExitStack() as opened:
            locks = []
            for path in files:
                db = sqlite3.connect(_sqlite_uri(path, "rw"), uri=True,
                                     timeout=2, isolation_level=None)
                opened.callback(db.close)
                db.execute("PRAGMA busy_timeout=2000")
                db.execute("BEGIN IMMEDIATE")
                locks.append(db)
            entries = {}
            for path in files:
                copy = destination / path.name
                with closing(sqlite3.connect(
                    _sqlite_uri(path, "ro"), uri=True, timeout=2,
                )) as read, closing(sqlite3.connect(str(copy))) as write:
                    read.backup(write)
                os.chmod(copy, 0o600)
                # Backup API preserves the source WAL journal mode. Seal
                # only the detached snapshot copy to DELETE journal mode,
                # checkpointing WAL into its database before hashing.
                # Never checkpoint or mutate the operator's source ledger.
                with closing(sqlite3.connect(str(copy), timeout=2)) as local:
                    mode = local.execute("PRAGMA journal_mode=DELETE").fetchone()
                    if mode is None or mode[0].lower() != "delete":
                        raise Paper09SnapshotRefused("P09_COPIED_SQLITE_NOT_SEALED")
                _verified_sqlite(copy)
                entries[path.name] = {
                    "sha256": _sha(copy), "bytes": copy.stat().st_size,
                }
            if reconcile_stage10_paper(destination)["status"] not in (
                "MATCHED_PAPER_ORDER", "CLEAN_NO_SIGNALS",
            ):
                raise Paper09SnapshotRefused("P09_BACKUP_PAIR_DISAGREES")
            manifest = {
                "schema_version": 1,
                "scope": "TWO_EXISTING_OFFLINE_BROOKS_STAGE10_SQLITE",
                "files": entries,
                "production_authorized": False,
                "automatic_recovery_authorized": False,
            }
            meta = destination / "manifest.json"
            with meta.open("xb") as output:
                os.chmod(meta, 0o600)
                output.write(_canonical(manifest))
                output.flush()
                os.fsync(output.fileno())
            for db in locks:
                db.execute("ROLLBACK")  # release write fences, no mutations
        return {
            "verdict": "P09_OFFLINE_SNAPSHOT_CREATED",
            "manifest_sha256": _sha(meta),
            "files": sorted(entries),
            "automatic_recovery_authorized": False,
            "production_authorized": False,
        }
    except BaseException:
        shutil.rmtree(destination)
        raise


def _load_manifest(bundle: Path) -> dict:
    # Snapshot is a fixed allowlisted bundle, never an arbitrary directory.
    # Extra sidecars, symlinks and unexpected payloads fail closed.
    if {entry.name for entry in bundle.iterdir()} != (
        set(DATABASES) | {"manifest.json"}
    ):
        raise Paper09SnapshotRefused("P09_SNAPSHOT_UNEXPECTED_FILE")
    raw = _file(bundle / "manifest.json", maximum=16 * 1024).read_bytes()
    try:
        obj = json.loads(raw, object_pairs_hook=_unique)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise Paper09SnapshotRefused("P09_MANIFEST_INVALID") from exc
    if (type(obj) is not dict
            or set(obj) != {
                "schema_version", "scope", "files", "production_authorized",
                "automatic_recovery_authorized",
            }
            or obj["schema_version"] != 1
            or obj["scope"] != "TWO_EXISTING_OFFLINE_BROOKS_STAGE10_SQLITE"
            or obj["production_authorized"] is not False
            or obj["automatic_recovery_authorized"] is not False
            or type(obj["files"]) is not dict
            or set(obj["files"]) != set(DATABASES)):
        raise Paper09SnapshotRefused("P09_MANIFEST_SCHEMA_INVALID")
    for name in DATABASES:
        row = obj["files"][name]
        if (type(row) is not dict or set(row) != {"sha256", "bytes"}
                or type(row["sha256"]) is not str
                or len(row["sha256"]) != 64
                or not all(ch in "0123456789abcdef" for ch in row["sha256"])
                or type(row["bytes"]) is not int
                or not 0 < row["bytes"] <= MAX_BYTES):
            raise Paper09SnapshotRefused("P09_FILE_MANIFEST_INVALID")
        path = _file(bundle / name)
        if path.stat().st_size != row["bytes"] or _sha(path) != row["sha256"]:
            raise Paper09SnapshotRefused("P09_SNAPSHOT_DIGEST_MISMATCH")
        _verified_sqlite(path)
    return obj


def restore_pair(bundle_dir: str | Path, target_parent: str | Path,
                 name: str = "p09-restored") -> dict:
    """Validate the complete snapshot, then restore into NEW empty directory.

    No rewriting an existing database and no automatic execution or trading.
    A failed candidate restore is removed without touching the bundle/source.
    """
    _consent()
    bundle = _private_dir(Path(bundle_dir))
    parent = _private_dir(Path(target_parent))
    if bundle == parent or bundle in parent.parents or parent in bundle.parents:
        raise Paper09SnapshotRefused("P09_SEPARATE_RESTORE_PARENT_REQUIRED")
    if name != "p09-restored":
        raise Paper09SnapshotRefused("P09_FIXED_RESTORE_NAME_REQUIRED")
    manifest = _load_manifest(bundle)
    target = _create_private(parent, name)
    try:
        for filename in DATABASES:
            dest = target / filename
            with (bundle / filename).open("rb") as source, dest.open("xb") as output:
                os.chmod(dest, 0o600)
                shutil.copyfileobj(source, output, length=1 << 20)
                output.flush()
                os.fsync(output.fileno())
            if _sha(dest) != manifest["files"][filename]["sha256"]:
                raise Paper09SnapshotRefused("P09_RESTORED_DIGEST_MISMATCH")
            _verified_sqlite(dest)
        result = reconcile_stage10_paper(target)
        if result["status"] not in ("MATCHED_PAPER_ORDER", "CLEAN_NO_SIGNALS"):
            raise Paper09SnapshotRefused("P09_RESTORED_PAIR_NEEDS_MANUAL_REVIEW")
        return {
            "verdict": "P09_OFFLINE_RESTORE_REHEARSAL_PASS",
            "reconciliation_status": result["status"],
            "manifest_sha256": _sha(bundle / "manifest.json"),
            "automatic_recovery_authorized": False,
            "production_authorized": False,
            "broker_orders_sent": False,
            "telegram_sent": False,
        }
    except BaseException:
        shutil.rmtree(target)
        raise
