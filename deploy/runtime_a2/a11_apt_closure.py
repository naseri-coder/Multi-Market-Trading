"""CERT-A11: fail-closed Debian APT archive closure byte integrity.

ONLY pre-approved fixed Node.js/npm APT dependencies in disposable CI images.
This runs NO Debian maintainer scripts and grants NO Worker/trading execution.
Hash pins are source-controlled; they are NOT independent publisher custody.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path

_ARCHIVES = Path("/tmp/mmt-a11-apt/archives")
_LOCK_PATH = Path("/opt/mmt/a11_apt_closure.json")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]{0,95}\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,159}\Z")
_AUDIENCE = "MMT-CERT-A11-APT-DEB-ARCHIVE-CLOSURE-REVIEW"
_MAX_PACKAGES = 400
_MAX_DEB = 64 * 1024 * 1024
_ALLOWED_ROOT = ("/tmp/mmt-a11-apt/archives",)
_KEYS = frozenset({"package", "version", "architecture", "sha256"})


class A11Refused(ValueError):
    """Never include untrusted metadata or file contents in error messages."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise A11Refused("A11_DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _regular(path: Path, *, max_bytes: int) -> None:
    try:
        if path.is_symlink():
            raise A11Refused("A11_SYMLINK_ARCHIVE_REFUSED")
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= max_bytes):
            raise A11Refused("A11_ARCHIVE_SIZE_OR_TYPE_REFUSED")
    except OSError as exc:
        raise A11Refused("A11_ARCHIVE_MISSING") from exc


def _package_fields(path: Path) -> tuple[str, str, str]:
    try:
        result = subprocess.run(
            ("/usr/bin/dpkg-deb", "--field", str(path), "Package", "Version",
             "Architecture"),
            stdin=subprocess.DEVNULL, capture_output=True, shell=False,
            close_fds=True, timeout=5, check=False,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise A11Refused("A11_DPKG_ARCHIVE_INSPECTION_FAILED") from exc
    if result.returncode != 0 or not 0 < len(result.stdout) <= 1024:
        raise A11Refused("A11_DPKG_ARCHIVE_HEADER_INVALID")
    try:
        fields = result.stdout.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise A11Refused("A11_DPKG_ARCHIVE_ENCODING_INVALID") from exc
    if len(fields) != 3:
        raise A11Refused("A11_DPKG_ARCHIVE_FIELD_COUNT")
    package, version, arch = fields
    if (_PACKAGE.fullmatch(package) is None
            or _VERSION.fullmatch(version) is None
            or arch not in {"all", "amd64"}):
        raise A11Refused("A11_PACKAGE_VERSION_ARCH_INVALID")
    return package, version, arch


def inspect_archives(root: Path = _ARCHIVES) -> list[dict[str, str]]:
    """Read the fixed APT download cache and SHA every .deb before install."""
    if root != _ARCHIVES or not root.is_absolute() or root.is_symlink():
        raise A11Refused("A11_FIXED_ARCHIVE_ROOT_REQUIRED")
    try:
        if not root.is_dir():
            raise A11Refused("A11_ARCHIVE_DIRECTORY_MISSING")
        candidates = [p for p in root.iterdir() if p.suffix == ".deb"]
        # Refuse unrelated blobs; APT may create 'lock' and 'partial' only.
        for p in root.iterdir():
            if p.suffix != ".deb" and p.name not in {"partial", "lock"}:
                raise A11Refused("A11_UNKNOWN_APT_CACHE_FILE")
    except OSError as exc:
        raise A11Refused("A11_APT_CACHE_UNREADABLE") from exc
    if not 1 <= len(candidates) <= _MAX_PACKAGES:
        raise A11Refused("A11_APT_ARCHIVE_COUNT_OUT_OF_BOUNDS")
    entries = []
    seen = set()
    for p in candidates:
        _regular(p, max_bytes=_MAX_DEB)
        package, version, arch = _package_fields(p)
        if package in seen:
            raise A11Refused("A11_DUPLICATE_PACKAGE_ARCHIVE")
        seen.add(package)
        digest = hashlib.sha256()
        try:
            with p.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise A11Refused("A11_UNREADABLE_DEB_BYTES") from exc
        entries.append({
            "package": package, "version": version, "architecture": arch,
            "sha256": digest.hexdigest(),
        })
    return sorted(entries, key=lambda x: x["package"])


def _canonical(entries: list[dict[str, str]]) -> bytes:
    return json.dumps(
        entries, separators=(",", ":"), sort_keys=True, ensure_ascii=True,
    ).encode("ascii")


def _closure_sha(entries: list[dict[str, str]]) -> str:
    return hashlib.sha256(
        b"MMT-A11-APT-ARCHIVE-CLOSURE-V1\x00" + _canonical(entries),
    ).hexdigest()


def candidate_lock(entries: list[dict[str, str]]) -> dict[str, object]:
    return {
        "schema": 1,
        "audience": _AUDIENCE,
        "base_arch": "linux/amd64",
        "root_packages": ["nodejs", "npm"],
        "packages": entries,
        "closure_sha256": _closure_sha(entries),
        "apt_snapshot_pinned": False,
        "debian_publisher_independently_verified": False,
        "host_certified": False,
        "worker_execution_authorized": False,
        "production_authorized": False,
    }


def validate_lock(locked: object, observed: list[dict[str, str]]) -> None:
    if type(locked) is not dict or set(locked) != set(candidate_lock(observed)):
        raise A11Refused("A11_LOCK_SCHEMA_INVALID")
    if (type(locked["schema"]) is not int or locked["schema"] != 1
            or locked["audience"] != _AUDIENCE
            or locked["base_arch"] != "linux/amd64"
            or locked["root_packages"] != ["nodejs", "npm"]
            or locked["apt_snapshot_pinned"] is not False
            or locked["debian_publisher_independently_verified"] is not False
            or locked["host_certified"] is not False
            or locked["worker_execution_authorized"] is not False
            or locked["production_authorized"] is not False):
        raise A11Refused("A11_LOCK_UNTRUSTED_RELEASE_ASSERTIONS")
    pinned = locked["packages"]
    if type(pinned) is not list or not 1 <= len(pinned) <= _MAX_PACKAGES:
        raise A11Refused("A11_LOCK_PACKAGE_SET_INVALID")
    for item in pinned:
        if (type(item) is not dict or set(item) != _KEYS
                or type(item["package"]) is not str
                or _PACKAGE.fullmatch(item["package"]) is None
                or type(item["version"]) is not str
                or _VERSION.fullmatch(item["version"]) is None
                or item["architecture"] not in ("all", "amd64")
                or type(item["sha256"]) is not str
                or _SHA.fullmatch(item["sha256"]) is None):
            raise A11Refused("A11_INVALID_ARCHIVE_LOCK_ENTRY")
    if (type(locked["closure_sha256"]) is not str
            or _SHA.fullmatch(locked["closure_sha256"]) is None
            or locked["closure_sha256"] != _closure_sha(pinned)
            or pinned != observed):
        raise A11Refused("A11_APT_ARCHIVE_HASH_OR_CLOSURE_DRIFT")


def _read_lock(path: Path) -> object:
    if path != _LOCK_PATH:
        raise A11Refused("A11_FIXED_LOCK_PATH_REQUIRED")
    _regular(path, max_bytes=128 * 1024)
    try:
        return json.loads(path.read_text(encoding="ascii"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, A11Refused):
            raise
        raise A11Refused("A11_APT_LOCK_NOT_VALID_JSON") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="CERT-A11 APT archive bytes only")
    parser.add_argument("mode", choices=("discover", "verify"))
    args = parser.parse_args()
    try:
        entries = inspect_archives()
        if args.mode == "discover":
            lock = candidate_lock(entries)
            print("A11_LOCK_JSON_BEGIN")
            print(json.dumps(lock, sort_keys=True, separators=(",", ":")))
            print("A11_LOCK_JSON_END")
            print(f"A11_DISCOVERY_PACKAGE_COUNT={len(entries)}")
            print(f"A11_DISCOVERY_CLOSURE_SHA256={lock['closure_sha256']}")
            print("A11_DISCOVERY_ONLY_NOT_INDEPENDENTLY_ATTESTED")
        else:
            validate_lock(_read_lock(_LOCK_PATH), entries)
            print(f"A11_DOWNLOADED_DEB_COUNT={len(entries)}")
            print(f"A11_PINNED_DEB_CLOSURE_SHA256={_closure_sha(entries)}")
            print("A11_ALL_DOWNLOADED_DEB_BYTES_PINNED_NOT_PUBLISHER_ATTESTED")
    except A11Refused as exc:
        parser.exit(2, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
