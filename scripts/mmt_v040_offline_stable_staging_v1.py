"""Read-only source verification, then isolated test-only v0.4.0 stage copy.

This tool DOES NOT build/sign/install a wheel or authorize publication. Its
RC-to-stable metadata overlay is restricted to the NEW private staging copy.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import sys
import tomllib
from pathlib import Path

from scripts import mmt_v040_public_source_snapshot_audit_v1 as snap
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable

_RC_VERSION = 'version = "0.4.0rc1"'
_STABLE_VERSION = 'version = "0.4.0"'
_FORBIDDEN = frozenset({"private_nyfr_core", "r0_engine"})


class StableStageRefused(ValueError):
    """A constant refusal code with no customer data."""


def _metadata(repo: Path) -> tuple[bytes, bytes]:
    project = repo / "platform_release" / "pyproject.toml"
    readme = repo / "platform_release" / "README.md"
    for p in (project, readme):
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 100_000:
            raise StableStageRefused("V040_UNSAFE_SOURCE_METADATA")
    try:
        raw = project.read_bytes()
        config = tomllib.loads(raw.decode("utf-8"))
        fields = config["project"]
        if (fields["name"] != stable.DIST_NAME
                or fields["version"] != "0.4.0rc1"
                or fields["requires-python"] != ">=3.12,<3.13"
                or fields["dependencies"] != []
                or fields["scripts"] != stable._ALLOWED_COMMANDS
                or set(fields["optional-dependencies"]) != set(stable._ALLOWED_REQUIREMENTS)
                or any(len(fields["optional-dependencies"][k]) != len(v)
                       or {s.lower() for s in fields["optional-dependencies"][k]} != v
                       for k, v in stable._ALLOWED_REQUIREMENTS.items())
                or config["build-system"]["requires"] != ["setuptools==80.9.0", "wheel==0.45.1"]
                or config["build-system"]["build-backend"] != "setuptools.build_meta"
                or raw.count(_RC_VERSION.encode()) != 1):
            raise StableStageRefused("V040_RC_SOURCE_METADATA_DRIFT")
        new_meta = raw.replace(_RC_VERSION.encode(), _STABLE_VERSION.encode())
        assert new_meta != raw
        staged = tomllib.loads(new_meta.decode("utf-8"))
        if staged["project"]["version"] != "0.4.0":
            raise StableStageRefused("V040_OVERLAY_METADATA_DRIFT")
        return new_meta, readme.read_bytes()
    except StableStageRefused:
        raise
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, AssertionError,
            tomllib.TOMLDecodeError) as exc:
        raise StableStageRefused("V040_RC_SOURCE_METADATA_DRIFT") from exc


def _check_source_module(raw: bytes, path: str) -> None:
    try:
        tree = ast.parse(raw, filename=path)
    except (SyntaxError, UnicodeError, ValueError) as exc:
        raise StableStageRefused("V040_SOURCE_PYTHON_PARSE_DENIED") from exc
    for node in ast.walk(tree):
        names = ()
        if isinstance(node, ast.Import):
            names = (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = (node.module or "",)
        if any(name.split(".")[0] in _FORBIDDEN for name in names):
            raise StableStageRefused("V040_PRIVATE_IMPORT_DENIED")


def stage(*, repository: Path, destination: Path, expected_source_commit: str,
          expected_public_tree_sha1: str, expected_lock_sha256: str) -> dict:
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise StableStageRefused("V040_NONPRODUCTION_REQUIRED")
    if not isinstance(destination, Path) or not destination.is_absolute():
        raise StableStageRefused("V040_ABSOLUTE_NEW_DESTINATION_REQUIRED")
    if (destination.exists() or destination.is_symlink()
            or destination.parent.is_symlink()
            or not destination.parent.is_dir()
            or not (stat.S_IMODE(destination.parent.stat().st_mode) & 0o077 == 0)
            or destination.parent.stat().st_uid != os.geteuid()
            or repository == destination or repository in destination.parents):
        raise StableStageRefused("V040_PRIVATE_OUTSIDE_NEW_DESTINATION_REQUIRED")
    # Trust sources only after externally pinned, clean and 226-file Git proof.
    report = snap.audit(repository=repository,
                        expected_source_commit=expected_source_commit,
                        expected_public_tree_sha1=expected_public_tree_sha1,
                        expected_lock_sha256=expected_lock_sha256)
    if report["public_modules_verified"] != snap.EXPECTED_MODULES:
        raise StableStageRefused("V040_PUBLIC_MODULE_COUNT_DRIFT")
    meta, readme = _metadata(repository)
    lock = snap._read_snapshot(repository / snap.SNAPSHOT_PATH, expected_lock_sha256)
    blobs = {}
    for m in lock["modules"]:
        name = m["path"]
        file = repository / name
        if file.is_symlink() or not file.is_file():
            raise StableStageRefused("V040_SOURCE_FILE_REPLACED")
        raw = file.read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
        if digest != m["git_blob_sha1"] or len(raw) != m["size"]:
            raise StableStageRefused("V040_SOURCE_FILE_CHANGED")
        _check_source_module(raw, name)
        blobs[name] = raw
    if set(blobs) != {m["path"] for m in lock["modules"]}:
        raise StableStageRefused("V040_SOURCE_FILE_SET_CHANGED")
    if snap._git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise StableStageRefused("V040_SOURCE_CHANGED_AFTER_SCAN")
    # Exclusive-new directory, without a copy into / from historical source.
    try:
        destination.mkdir(mode=0o700)
        (destination / "naseri_markets").mkdir(mode=0o700)
        (destination / "pyproject.toml").write_bytes(meta)
        (destination / "README.md").write_bytes(readme)
        for name, raw in blobs.items():
            out = destination / name
            out.write_bytes(raw)
            if out.read_bytes() != raw:
                raise StableStageRefused("V040_STAGED_BYTES_MISMATCH")
    except OSError as exc:
        # Keep partially staged files for inspection; never auto delete.
        raise StableStageRefused("V040_NEW_STAGING_IO_REFUSED") from exc
    return {
        "verdict": "V040_ISOLATED_226_SOURCE_STAGING_PASS_PUBLIC_RELEASE_DENIED",
        "source_commit": expected_source_commit,
        "public_tree_sha1": expected_public_tree_sha1,
        "snapshot_sha256": expected_lock_sha256,
        "source_preview_version": "0.4.0rc1",
        "staged_version": "0.4.0",
        "staged_module_count": len(blobs),
        "staged_source_bytes": sum(map(len, blobs.values())),
        "staged_metadata_sha256": hashlib.sha256(meta).hexdigest(),
        "original_source_mutated": False,
        "wheel_built": False,
        "wheel_signed": False,
        "public_release_authorized": False,
        "installation_authorized": False,
        "live_trading_authorized": False,
        "telegram_publication_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-public-tree-sha1", required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    try:
        output = stage(**vars(parser.parse_args(argv)))
    except (StableStageRefused, snap.PublicSnapshotRefused, OSError) as exc:
        code = str(exc) if isinstance(exc, (StableStageRefused, snap.PublicSnapshotRefused)) else "V040_STAGING_IO_DENIED"
        print(json.dumps({"verdict": "V040_STAGING_REFUSED", "reason": code,
                          "public_release_authorized": False,
                          "live_trading_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
