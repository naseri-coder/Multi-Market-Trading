"""CERT-A10: offline fail-closed review of fixed Worker image artifact pins.

No network, Docker, subprocesses, cryptographic publisher signing, or launch
permissions. Repository-controlled SHA pins do not establish upstream custody.
"""
from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path

_EXPECTED = {
    "schema": 1,
    "audience": "MMT-CERT-A10-NONPRODUCTION-ARCHIVE-BYTE-PINS",
    "runtime_platform": "linux/amd64",
    "base_image": "python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258",
    "typescript": {
        "version": "5.9.3",
        "tarball_url": "https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz",
        "sha512": "8e5d6f6733c38a72ebf5e52ddc9feded5e8580d130f508ef04f772b33f4a7d00c3e357d0ac2d98e2f290762694a454f86d795bd511e12e9a7cc2d9ba3394e04b",
    },
    "wasmtime": {
        "version": "49.0.0",
        "wheel": "wasmtime-49.0.0-py3-none-manylinux1_x86_64.whl",
        "sha256": "94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a",
    },
    "apt_snapshot_pinned": False,
    "independent_publisher_verified": False,
    "host_isolation_certified": False,
    "execution_authorized": False,
}
_PIN_FILE = "deploy/runtime_a2/a10_archive_pins.json"
_RECIPE = "deploy/runtime_a2/Dockerfile"
_WHEEL = "deploy/runtime_a2/a10_wasmtime.lock"


class CertA10Refused(ValueError):
    """Never emit private source content in denial messages."""


@dataclass(frozen=True, slots=True)
class ArchivePinReview:
    pinned_artifact_entries: int = 3
    status: str = "CERT_A10_BASE_NPM_WHEEL_BYTE_PINS_AUDITED_APT_OPEN"
    actual_apt_package_sha_verified: bool = False
    independent_registry_signature_verified: bool = False
    verified_provenance_custody: bool = False
    gvisor_host_certified: bool = False
    arbitrary_worker_execution_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    production_authorized: bool = False


def _read(root: Path, relative: str, max_bytes: int) -> bytes:
    path = root
    try:
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise CertA10Refused("CERT_A10_ABSOLUTE_REAL_ROOT_REQUIRED")
        for segment in relative.split("/"):
            if not re.fullmatch("[a-zA-Z0-9_.-]+", segment):
                raise CertA10Refused("CERT_A10_INVALID_FIXED_PATH")
            path = path / segment
            if path.is_symlink():
                raise CertA10Refused("CERT_A10_SYMLINK_NOT_ALLOWED")
        mode = path.lstat()
        if (not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1
                or not 0 < mode.st_size <= max_bytes):
            raise CertA10Refused("CERT_A10_FILE_SIZE_OR_TYPE_REFUSED")
        return path.read_bytes()
    except OSError as exc:
        raise CertA10Refused("CERT_A10_PIN_FILE_MISSING") from exc


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found = {}
    for key, value in pairs:
        if key in found:
            raise CertA10Refused("CERT_A10_DUPLICATE_JSON_FIELD")
        found[key] = value
    return found


def review_archive_pins(root: Path) -> ArchivePinReview:
    """Check static exact known pins and candidate Docker recipe, no execution."""
    if not isinstance(root, Path):
        raise CertA10Refused("CERT_A10_REAL_ROOT_REQUIRED")
    root = root.absolute()
    try:
        record = json.loads(
            _read(root, _PIN_FILE, 4096).decode("ascii"),
            object_pairs_hook=_unique,
        )
        docker = _read(root, _RECIPE, 8192).decode("ascii")
        wheel = _read(root, _WHEEL, 1024).decode("ascii")
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, CertA10Refused):
            raise
        raise CertA10Refused("CERT_A10_INVALID_PIN_CONTENT") from exc
    if record != _EXPECTED:
        raise CertA10Refused("CERT_A10_ARCHIVE_PINS_CHANGED_OR_UNTRUSTED")
    lines = docker.splitlines()
    from_lines = [line for line in lines if line.startswith("FROM ")]
    if from_lines != ["FROM " + _EXPECTED["base_image"]]:
        raise CertA10Refused("CERT_A10_BASE_DIGEST_NOT_ENFORCED")
    if (docker.count(_EXPECTED["typescript"]["sha512"]) != 1
            or docker.count(_EXPECTED["typescript"]["tarball_url"]) != 1
            or "--offline --no-audit --no-fund /tmp/typescript-5.9.3.tgz" not in docker
            or "--ignore-scripts" not in docker):
        raise CertA10Refused("CERT_A10_NPM_ARCHIVE_VERIFICATION_MISSING")
    if ("--only-binary=:all:" not in docker
            or "--require-hashes -r /tmp/a10_wasmtime.lock" not in docker
            or "COPY deploy/runtime_a2/a10_wasmtime.lock /tmp/a10_wasmtime.lock"
            not in docker):
        raise CertA10Refused("CERT_A10_WHEEL_HASH_CHECK_MISSING")
    non_comments = [
        line.strip() for line in wheel.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if non_comments != [
        "wasmtime==49.0.0 \\",
        "    --hash=sha256:" + _EXPECTED["wasmtime"]["sha256"],
    ]:
        raise CertA10Refused("CERT_A10_WHEEL_SHA256_CHANGED")
    return ArchivePinReview()


__all__ = ["CertA10Refused", "ArchivePinReview", "review_archive_pins"]
