"""R36 read-only local Git-source / public Wheel byte-provenance audit.

No service, installation, network, private source or signing key access.
SHA pins MUST be independently supplied by the operator. This does not
verify an authenticated publisher signature or grant release permission.
"""
from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

from scripts.mmt_r35_offline_preview_install_v1 import (
    DIST,
    R35Refused,
    _inspect_wheel,
    _wheel_bytes,
)

COMMIT = re.compile(r"[0-9a-f]{40}\Z")
EXPECTED_DIST_FILES = frozenset({
    DIST + "METADATA",
    DIST + "WHEEL",
    DIST + "entry_points.txt",
    DIST + "top_level.txt",
    DIST + "RECORD",
})


class R36Refused(ValueError):
    """Fail closed with bounded, non-secret reason codes."""


def _git(repository: Path, expected_commit: str) -> str:
    if not isinstance(repository, Path) or not repository.is_absolute():
        raise R36Refused("R36_ABSOLUTE_REPOSITORY_REQUIRED")
    if repository.is_symlink() or not repository.is_dir():
        raise R36Refused("R36_REGULAR_REPOSITORY_REQUIRED")
    if not isinstance(expected_commit, str) or not COMMIT.fullmatch(expected_commit):
        raise R36Refused("R36_EXTERNAL_COMMIT_PIN_REQUIRED")
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        head = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, check=False, timeout=15, env=env,
        )
        if head.returncode != 0 or head.stdout.strip() != expected_commit:
            raise R36Refused("R36_SOURCE_COMMIT_PIN_MISMATCH")
        dirty = subprocess.run(
            ["git", "-C", str(repository), "status", "--porcelain",
             "--untracked-files=all", "--", "naseri_markets", "platform_release"],
            capture_output=True, text=True, check=False, timeout=15, env=env,
        )
        if dirty.returncode != 0 or dirty.stdout or dirty.stderr:
            raise R36Refused("R36_PUBLIC_SOURCE_NOT_CLEAN")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise R36Refused("R36_READONLY_GIT_CHECK_FAILED") from exc
    return expected_commit


def _public_files(repository: Path) -> tuple[dict[str, bytes], dict]:
    package = repository / "naseri_markets"
    project = repository / "platform_release" / "pyproject.toml"
    readme = repository / "platform_release" / "README.md"
    if not package.is_dir() or package.is_symlink():
        raise R36Refused("R36_PUBLIC_SOURCE_FOLDER_MISSING")
    files: dict[str, bytes] = {}
    modules = sorted(package.glob("*.py"))
    if not modules or len(modules) > 500:
        raise R36Refused("R36_PUBLIC_MODULE_SET_INVALID")
    for file in [*modules, project, readme]:
        if not file.is_file() or file.is_symlink():
            raise R36Refused("R36_PUBLIC_FILE_MISSING_OR_SYMLINK")
        if file.stat().st_size > 1_000_000:
            raise R36Refused("R36_PUBLIC_FILE_OVERSIZED")
        relative = file.relative_to(repository).as_posix()
        files[relative] = file.read_bytes()
    if "naseri_markets/platform_cli.py" not in files:
        raise R36Refused("R36_MAIN_MODULE_MISSING")
    try:
        metadata = tomllib.loads(files["platform_release/pyproject.toml"].decode())
        project_data = metadata["project"]
        if (project_data["name"] != "multi-market-trading"
                or project_data["version"] != "0.4.0rc1"
                or project_data["dependencies"] != []
                or not isinstance(project_data["scripts"], dict)):
            raise R36Refused("R36_PUBLIC_METADATA_INVALID")
    except (KeyError, UnicodeError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise R36Refused("R36_PUBLIC_METADATA_INVALID") from exc
    return files, project_data


def _digest_members(members: dict[str, bytes]) -> str:
    """Deterministic logical contents digest independent of ZIP timestamps."""
    h = hashlib.sha256()
    for name in sorted(members):
        h.update(name.encode("utf-8") + b"\x00")
        h.update(hashlib.sha256(members[name]).digest())
    return h.hexdigest()


def _record_valid(bundle: zipfile.ZipFile, members: dict[str, bytes]) -> None:
    try:
        raw_record = members[DIST + "RECORD"].decode("utf-8")
        rows = list(csv.reader(io.StringIO(raw_record)))
    except (UnicodeError, csv.Error, KeyError) as exc:
        raise R36Refused("R36_WHEEL_RECORD_INVALID") from exc
    if len(rows) != len(members):
        raise R36Refused("R36_RECORD_FILE_COUNT_MISMATCH")
    seen: set[str] = set()
    for row in rows:
        if len(row) != 3:
            raise R36Refused("R36_RECORD_ROW_INVALID")
        name, digest, size = row
        if name not in members or name in seen:
            raise R36Refused("R36_RECORD_MEMBER_UNKNOWN_OR_DUPLICATE")
        seen.add(name)
        if name == DIST + "RECORD":
            if digest or size:
                raise R36Refused("R36_RECORD_SELF_HASH_MUST_BE_EMPTY")
            continue
        if not digest.startswith("sha256=") or not size.isdecimal():
            raise R36Refused("R36_RECORD_HASH_OR_SIZE_MISSING")
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(members[name]).digest()
        ).rstrip(b"=").decode("ascii")
        if digest != "sha256=" + expected or int(size) != len(members[name]):
            raise R36Refused("R36_RECORD_HASH_OR_SIZE_MISMATCH")
    if seen != set(members):
        raise R36Refused("R36_RECORD_INCOMPLETE")


def _validate_wheel(raw: bytes, files: dict[str, bytes], project: dict) -> tuple[str, int]:
    _inspect_wheel(raw)  # R35 bounded ZIP, member type and package identity fences
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            items = bundle.namelist()
            source_modules = {
                name: data for name, data in files.items()
                if name.startswith("naseri_markets/")
            }
            unexpected = set(items) - (set(source_modules) | EXPECTED_DIST_FILES)
            if unexpected or set(source_modules) - set(items):
                raise R36Refused("R36_WHEEL_SOURCE_MEMBER_SET_MISMATCH")
            members = {name: bundle.read(name) for name in items}
            for name, data in source_modules.items():
                if members[name] != data:
                    raise R36Refused("R36_WHEEL_MODULE_BYTES_DIFFER")
            _record_valid(bundle, members)
            wheel_metadata = members[DIST + "WHEEL"].decode()
            if ("Tag: py3-none-any" not in wheel_metadata
                    or "Root-Is-Purelib: true" not in wheel_metadata):
                raise R36Refused("R36_WHEEL_PLATFORM_TAG_UNEXPECTED")
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(members[DIST + "entry_points.txt"].decode())
            if not parser.has_section("console_scripts"):
                raise R36Refused("R36_CONSOLE_SCRIPTS_MISSING")
            expected_scripts = project["scripts"]
            actual_scripts = dict(parser.items("console_scripts"))
            if actual_scripts != expected_scripts:
                raise R36Refused("R36_ENTRYPOINTS_SOURCE_MISMATCH")
            return _digest_members({
                k: v for k, v in members.items() if k != DIST + "RECORD"
            }), len(source_modules)
    except (KeyError, UnicodeError, ValueError, configparser.Error,
            zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, R36Refused):
            raise
        raise R36Refused("R36_WHEEL_STRUCTURE_INVALID") from exc


def audit(*, repository: Path, wheel: Path, expected_wheel_sha256: str,
          expected_source_commit: str, compare_wheel: Path | None = None
          ) -> dict:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or sys.version_info[:2] != (3, 12)):
        raise R36Refused("R36_OFFLINE_PY312_ONLY")
    pinned_commit = _git(repository, expected_source_commit)
    sources, project = _public_files(repository)
    try:
        raw, digest, size = _wheel_bytes(wheel, expected_wheel_sha256)
        payload, count = _validate_wheel(raw, sources, project)
    except R35Refused as exc:
        raise R36Refused("R36_BOUNDED_R35_WHEEL_CHECK_REFUSED") from exc
    source_digest = _digest_members(sources)
    result = {
        "verdict": "R36_LOCAL_SOURCE_WHEEL_EQUIVALENCE_PASS_RELEASE_DENIED",
        "source_commit": pinned_commit,
        "source_tree_sha256": source_digest,
        "wheel_sha256": digest,
        "wheel_bytes": size,
        "public_modules_verified": count,
        "wheel_payload_sha256": payload,
        "wheel_record_verified": True,
        "source_module_bytes_match": True,
        "files_written": False,
        "publisher_signature_verified": False,
        "independent_provenance_verified": False,
        "production_release_authorized": False,
        "live_authorized": False,
    }
    if compare_wheel is not None:
        # Second Wheel receives the same independent operator-reviewed pin
        # only for the original artifact. This establishes content equality,
        # not the identity or origin of a second builder.
        try:
            if compare_wheel == wheel or compare_wheel.is_symlink():
                raise R36Refused("R36_INDEPENDENT_COMPARISON_WHEEL_REQUIRED")
            if not compare_wheel.is_absolute() or compare_wheel.name != wheel.name:
                raise R36Refused("R36_INDEPENDENT_COMPARISON_WHEEL_REQUIRED")
            if not compare_wheel.is_file() or compare_wheel.stat().st_size > 12_000_000:
                raise R36Refused("R36_COMPARISON_WHEEL_UNSAFE")
            other = compare_wheel.read_bytes()
            other_payload, other_count = _validate_wheel(other, sources, project)
            if other_payload != payload or other_count != count:
                raise R36Refused("R36_SECOND_BUILD_PAYLOAD_DIFFERS")
        except (R35Refused, OSError) as exc:
            raise R36Refused("R36_COMPARISON_WHEEL_INVALID") from exc
        byte_equal = hashlib.sha256(other).hexdigest() == digest
        result["second_wheel_sha256"] = hashlib.sha256(other).hexdigest()
        result["second_wheel_same_payload"] = True
        result["second_wheel_identical_bytes"] = byte_equal
        result["verdict"] = (
            "R36_SECOND_WHEEL_BYTE_IDENTICAL_PASS_RELEASE_DENIED"
            if byte_equal
            else "R36_SECOND_WHEEL_PAYLOAD_EQUAL_BYTES_DIFFER_RELEASE_DENIED"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-wheel-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--compare-wheel", type=Path)
    args = parser.parse_args(argv)
    try:
        verdict = audit(
            repository=args.repository, wheel=args.wheel,
            expected_wheel_sha256=args.expected_wheel_sha256,
            expected_source_commit=args.expected_source_commit,
            compare_wheel=args.compare_wheel,
        )
    except (R36Refused, OSError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, R36Refused) else "R36_AUDIT_REFUSED"
        print(json.dumps({"verdict": "R36_AUDIT_REFUSED", "reason": reason,
                          "live_authorized": False, "files_written": False},
                         sort_keys=True))
        return 2
    print(json.dumps(verdict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
