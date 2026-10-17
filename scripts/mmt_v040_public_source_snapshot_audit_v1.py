"""Read-only exact Git source inventory vs independently pinned GitHub snapshot.

Does not build, sign, install, execute project modules, connect to networks,
start workers or authorize the release. A full Wheel remains a separate gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

SNAPSHOT_PATH = Path("docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json")
FIELDS = frozenset({
    "schema_version", "distribution", "release_candidate", "provenance",
    "github_repository", "snapshot_commit", "public_subtree_sha1",
    "expected_module_count", "source_bytes", "modules",
})
MEMBER_FIELDS = frozenset({"path", "git_blob_sha1", "size"})
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_SNAPSHOT_BYTES = 100_000
MAX_MODULE_BYTES = 1_000_000
EXPECTED_MODULES = 226


class PublicSnapshotRefused(ValueError):
    """Fixed refusal codes; never return source content or credentials."""


def _git(repository: Path, *args: str) -> bytes:
    try:
        p = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True, check=False, timeout=20,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicSnapshotRefused("V040_GIT_SNAPSHOT_READ_FAILED") from exc
    if p.returncode or p.stderr or len(p.stdout) > 100_000:
        raise PublicSnapshotRefused("V040_GIT_SNAPSHOT_READ_FAILED")
    return p.stdout


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise PublicSnapshotRefused("V040_DUPLICATE_SNAPSHOT_KEY")
        result[key] = value
    return result


def _read_snapshot(path: Path, expected_sha256: str) -> dict:
    if (not path.is_absolute() or path.is_symlink() or path.parent.is_symlink()
            or type(expected_sha256) is not str or not HEX64.fullmatch(expected_sha256)):
        raise PublicSnapshotRefused("V040_EXTERNAL_SNAPSHOT_PIN_REQUIRED")
    try:
        metadata = path.stat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or not 1 <= metadata.st_size <= MAX_SNAPSHOT_BYTES):
            raise PublicSnapshotRefused("V040_SNAPSHOT_FILE_UNSAFE")
        raw = path.read_bytes()
    except OSError as exc:
        raise PublicSnapshotRefused("V040_SNAPSHOT_UNREADABLE") from exc
    if len(raw) != metadata.st_size or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise PublicSnapshotRefused("V040_SNAPSHOT_EXTERNAL_SHA256_MISMATCH")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except PublicSnapshotRefused:
        raise
    except (ValueError, UnicodeError, RecursionError, TypeError) as exc:
        raise PublicSnapshotRefused("V040_SNAPSHOT_JSON_INVALID") from exc
    if type(obj) is not dict or set(obj) != FIELDS:
        raise PublicSnapshotRefused("V040_SNAPSHOT_SCHEMA_INVALID")
    return obj


def audit(*, repository: Path, expected_source_commit: str,
          expected_public_tree_sha1: str, expected_lock_sha256: str) -> dict:
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise PublicSnapshotRefused("V040_NONPRODUCTION_REQUIRED")
    if (not isinstance(repository, Path) or not repository.is_absolute()
            or repository.is_symlink() or not repository.is_dir()
            or type(expected_source_commit) is not str
            or not HEX40.fullmatch(expected_source_commit)
            or type(expected_public_tree_sha1) is not str
            or not HEX40.fullmatch(expected_public_tree_sha1)):
        raise PublicSnapshotRefused("V040_INDEPENDENT_GIT_PINS_REQUIRED")
    if _git(repository, "rev-parse", "--verify", "HEAD").strip().decode("ascii") != expected_source_commit:
        raise PublicSnapshotRefused("V040_GIT_COMMIT_PIN_MISMATCH")
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PublicSnapshotRefused("V040_GIT_NOT_CLEAN")
    current_tree = _git(repository, "rev-parse", "HEAD:naseri_markets").strip().decode("ascii")
    if current_tree != expected_public_tree_sha1:
        raise PublicSnapshotRefused("V040_PUBLIC_TREE_PIN_MISMATCH")
    snapshot = _read_snapshot(repository / SNAPSHOT_PATH, expected_lock_sha256)
    if (type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1
            or snapshot["distribution"] != "multi-market-trading"
            or snapshot["release_candidate"] != "v0.4.0"
            or snapshot["provenance"] != "GITHUB_TREE_SNAPSHOT__NOT_RELEASE_APPROVAL"
            or snapshot["github_repository"] != "naseri-coder/Multi-Market-Trading"
            or type(snapshot["snapshot_commit"]) is not str
            or not HEX40.fullmatch(snapshot["snapshot_commit"])
            or snapshot["public_subtree_sha1"] != current_tree
            or type(snapshot["expected_module_count"]) is not int
            or snapshot["expected_module_count"] != EXPECTED_MODULES
            or type(snapshot["source_bytes"]) is not int or snapshot["source_bytes"] < 1
            or type(snapshot["modules"]) is not list
            or len(snapshot["modules"]) != EXPECTED_MODULES):
        raise PublicSnapshotRefused("V040_SNAPSHOT_IDENTITY_INVALID")
    entries = snapshot["modules"]
    if any(type(m) is not dict or set(m) != MEMBER_FIELDS
           or type(m["path"]) is not str
           or not m["path"].startswith("naseri_markets/")
           or len(Path(m["path"]).parts) != 2
           or Path(m["path"]).suffix != ".py"
           or "\\" in m["path"] or "/../" in m["path"]
           or type(m["git_blob_sha1"]) is not str
           or not HEX40.fullmatch(m["git_blob_sha1"])
           or type(m["size"]) is not int or not 0 <= m["size"] <= MAX_MODULE_BYTES
           for m in entries):
        raise PublicSnapshotRefused("V040_SNAPSHOT_MEMBER_INVALID")
    by_path = {m["path"]: m for m in entries}
    if len(by_path) != EXPECTED_MODULES or list(by_path) != sorted(by_path):
        raise PublicSnapshotRefused("V040_SNAPSHOT_MEMBER_ORDER_INVALID")
    tracked = _git(repository, "ls-files", "-z", "--", "naseri_markets")
    try:
        names = [b.decode("utf-8") for b in tracked.split(b"\0") if b]
    except UnicodeError as exc:
        raise PublicSnapshotRefused("V040_SNAPSHOT_GIT_MEMBER_SET_MISMATCH") from exc
    if set(names) != set(by_path) or len(names) != EXPECTED_MODULES:
        raise PublicSnapshotRefused("V040_SNAPSHOT_GIT_MEMBER_SET_MISMATCH")
    pkg = repository / "naseri_markets"
    if pkg.is_symlink() or not pkg.is_dir():
        raise PublicSnapshotRefused("V040_SNAPSHOT_PACKAGE_UNSAFE")
    total = 0
    for name in sorted(names):
        file = repository / name
        try:
            metadata = file.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise PublicSnapshotRefused("V040_SNAPSHOT_MODULE_UNSAFE")
            raw = file.read_bytes()
        except OSError as exc:
            raise PublicSnapshotRefused("V040_SNAPSHOT_MODULE_UNREADABLE") from exc
        expected = by_path[name]
        if len(raw) != expected["size"] or len(raw) != metadata.st_size:
            raise PublicSnapshotRefused("V040_SNAPSHOT_MODULE_SIZE_MISMATCH")
        calculated = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if calculated != expected["git_blob_sha1"]:
            raise PublicSnapshotRefused("V040_SNAPSHOT_MODULE_BLOB_MISMATCH")
        total += len(raw)
    if total != snapshot["source_bytes"]:
        raise PublicSnapshotRefused("V040_SNAPSHOT_TOTAL_BYTES_MISMATCH")
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PublicSnapshotRefused("V040_GIT_CHANGED_DURING_AUDIT")
    return {
        "verdict": "V040_PUBLIC_SOURCE_SNAPSHOT_226_MATCH_RELEASE_DENIED",
        "git_source_commit": expected_source_commit,
        "public_tree_sha1": current_tree,
        "public_modules_verified": len(names),
        "source_bytes_verified": total,
        "writes_performed": False,
        "install_authorized": False,
        "public_release_authorized": False,
        "live_trading_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-public-tree-sha1", required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    try:
        result = audit(**vars(parser.parse_args(argv)))
    except (PublicSnapshotRefused, OSError, UnicodeError) as exc:
        reason = str(exc) if isinstance(exc, PublicSnapshotRefused) else "V040_SNAPSHOT_AUDIT_IO_REFUSED"
        print(json.dumps({"verdict": "V040_PUBLIC_SNAPSHOT_REFUSED", "reason": reason,
                          "public_release_authorized": False,
                          "live_trading_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
