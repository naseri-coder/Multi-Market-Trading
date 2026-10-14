"""CERT-A12: hash-verify exact historical Debian InRelease bytes + gpgv signatures.

Offline verification only: APT must first authenticate the signed indexes via
an exact Signed-By keyring in a digest-pinned base. The subsequent independent
gpgv invocation uses that SAME base keyring, NOT separate publisher custody.
Never run this on production, TELMIVO, license or trading servers.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path

_SOURCE = Path("/etc/apt/sources.list.d/mmt-cert-a12.sources")
_LOCK = Path("/opt/mmt/a12_signed_snapshot.json")
_LISTS = Path("/var/lib/apt/lists")
_KEY = Path("/usr/share/keyrings/debian-archive-keyring.gpg")
_SOURCES_DIR = Path("/etc/apt/sources.list.d")
_DEFAULT_LIST = Path("/etc/apt/sources.list")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE = re.compile(rb"\[GNUPG:\] VALIDSIG [A-Fa-f0-9]{40,64}(?:\s|$)")
_RELEASES = {
    "bookworm": (
        "snapshot.debian.org_archive_debian_20261014T000000Z_dists_bookworm_InRelease",
        "77737fa4b34f2693e982cc9ee35736816c35a7778fc2d326cc1bbf5b301fe1aa",
    ),
    "bookworm-updates": (
        "snapshot.debian.org_archive_debian_20261014T000000Z_dists_bookworm-updates_InRelease",
        "cad962818b6fc8955fc243553c75f2bfff73909e3516099b2fcd3476925abeb3",
    ),
    "bookworm-security": (
        "snapshot.debian.org_archive_debian-security_20261014T000000Z_dists_bookworm-security_InRelease",
        "9e5050b09604010af7190f3e8391739d9fc7dc11616d1a25e90c7e25565e4f92",
    ),
}
_BASE = (
    "python:3.12-slim-bookworm@sha256:"
    "34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258"
)
_SOURCES_CONTENT = """# CERT-A12: exact historical Debian snapshot sources; archival Valid-Until
# exception applies ONLY to these dated signed sources (not globally).
Types: deb
URIs: https://snapshot.debian.org/archive/debian/20261014T000000Z/
Suites: bookworm bookworm-updates
Components: main
Architectures: amd64
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no

Types: deb
URIs: https://snapshot.debian.org/archive/debian-security/20261014T000000Z/
Suites: bookworm-security
Components: main
Architectures: amd64
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no
"""
_KEYS = frozenset({
    "schema", "audience", "snapshot_timestamp", "base_image",
    "debian_archive_keyring", "apt_closure_sha256", "release_files",
    "archival_valid_until_scope_only", "independent_debian_publisher_custody",
    "independent_release_timestamp_witness", "image_reproducibly_attested",
    "rootless_gvisor_host_certified", "worker_execution_authorized",
    "broker_authorized", "telegram_authorized", "production_authorized",
})


class A12Refused(ValueError):
    """Fixed codes only; never expose untrusted subprocess output."""


def _regular(path: Path, limit: int) -> bytes:
    try:
        if path.is_symlink():
            raise A12Refused("A12_SYMLINK_INPUT_REFUSED")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise A12Refused("A12_INPUT_FILE_NOT_REGULAR")
        if not 0 < info.st_size <= limit:
            raise A12Refused("A12_INPUT_SIZE_INVALID")
        return path.read_bytes()
    except OSError as exc:
        raise A12Refused("A12_INPUT_FILE_NOT_AVAILABLE") from exc


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise A12Refused("A12_DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def validate_manifest(obj: object) -> None:
    if type(obj) is not dict or set(obj) != _KEYS:
        raise A12Refused("A12_MANIFEST_SCHEMA_INVALID")
    if (type(obj["schema"]) is not int or obj["schema"] != 1
            or obj["audience"] != "MMT-CERT-A12-SIGNED-DEBIAN-SNAPSHOT-NONPRODUCTION"
            or obj["snapshot_timestamp"] != "20261014T000000Z"
            or obj["base_image"] != _BASE
            or obj["debian_archive_keyring"] != str(_KEY)
            or obj["apt_closure_sha256"]
            != "47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872"
            or obj["archival_valid_until_scope_only"] is not True
            or any(obj[field] is not False for field in (
                "independent_debian_publisher_custody",
                "independent_release_timestamp_witness",
                "image_reproducibly_attested", "rootless_gvisor_host_certified",
                "worker_execution_authorized", "broker_authorized",
                "telegram_authorized", "production_authorized",
            ))):
        raise A12Refused("A12_MANIFEST_UNTRUSTED_AUTHORITY")
    entries = obj["release_files"]
    if type(entries) is not list or len(entries) != 3:
        raise A12Refused("A12_INRELEASE_COUNT_INVALID")
    observed = {}
    for entry in entries:
        if (type(entry) is not dict
                or set(entry) != {"suite", "apt_list_filename", "sha256"}
                or any(type(val) is not str for val in entry.values())
                or entry["suite"] in observed):
            raise A12Refused("A12_INRELEASE_MANIFEST_ENTRY_INVALID")
        observed[entry["suite"]] = (entry["apt_list_filename"], entry["sha256"])
    if observed != _RELEASES:
        raise A12Refused("A12_SIGNED_INDEX_HASH_OR_FILENAME_DRIFT")


def _load_manifest() -> None:
    try:
        obj = json.loads(_regular(_LOCK, 8192).decode("ascii"),
                         object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, A12Refused):
            raise
        raise A12Refused("A12_MANIFEST_PARSING_FAILED") from exc
    validate_manifest(obj)


def verify_sources() -> None:
    _load_manifest()
    if _regular(_SOURCE, 2048) != _SOURCES_CONTENT.encode("ascii"):
        raise A12Refused("A12_DEBIAN_SOURCES_CHANGED")
    try:
        if _DEFAULT_LIST.exists() or _DEFAULT_LIST.is_symlink():
            raise A12Refused("A12_UNEXPECTED_DEFAULT_APT_SOURCES")
        for other in _SOURCES_DIR.iterdir():
            if other.suffix in {".sources", ".list"} and other != _SOURCE:
                raise A12Refused("A12_UNTRUSTED_ADDITIONAL_APT_SOURCE")
    except OSError as exc:
        raise A12Refused("A12_CANNOT_CHECK_APT_SOURCES") from exc


def _verify_one_index(path: Path, expected_sha: str) -> None:
    before = _regular(path, 1024 * 1024)
    if hashlib.sha256(before).hexdigest() != expected_sha:
        raise A12Refused("A12_INRELEASE_BYTES_DIFFER_FROM_PIN")
    try:
        response = subprocess.run(
            ("/usr/bin/gpgv", "--keyring", str(_KEY),
             "--status-fd", "1", str(path)),
            stdin=subprocess.DEVNULL, capture_output=True,
            shell=False, close_fds=True, timeout=12, check=False,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise A12Refused("A12_GPGV_UNAVAILABLE_OR_TIMEOUT") from exc
    if (response.returncode != 0 or not 0 < len(response.stdout) <= 8192
            or _SIGNATURE.search(response.stdout) is None
            or b"[GNUPG:] BADSIG" in response.stdout
            or b"[GNUPG:] REVKEYSIG" in response.stdout):
        raise A12Refused("A12_INRELEASE_SIGNATURE_NOT_VALIDATED")
    after = _regular(path, 1024 * 1024)
    if hashlib.sha256(after).hexdigest() != expected_sha:
        raise A12Refused("A12_SIGNED_INDEX_CHANGED_WHILE_CHECKING")


def verify_signed_indexes() -> int:
    verify_sources()
    _regular(_KEY, 1024 * 1024)
    expected = {name for name, _ in _RELEASES.values()}
    try:
        found = {p.name for p in _LISTS.iterdir() if p.name.endswith("_InRelease")}
    except OSError as exc:
        raise A12Refused("A12_APT_LIST_DIRECTORY_UNREADABLE") from exc
    if found != expected:
        raise A12Refused("A12_MISSING_OR_EXTRA_SIGNED_INDEX")
    for filename, expected_sha in _RELEASES.values():
        _verify_one_index(_LISTS / filename, expected_sha)
    return len(_RELEASES)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"sources", "indexes"}:
        print("A12_FIXED_MODE_REQUIRED", file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == "sources":
            verify_sources()
            print("A12_THREE_FIXED_SIGNED_ARCHIVAL_SOURCES_ONLY")
        else:
            count = verify_signed_indexes()
            print(f"A12_HASH_MATCHED_GPGV_SIGNED_INRELEASE={count}")
            print("A12_APT_INDEX_BYTES_AND_BASE_KEYRING_SIGNATURES_MATCHED")
            print("A12_NOT_INDEPENDENT_SIGNER_CUSTODY_OR_GVISOR_CERTIFIED")
    except A12Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
