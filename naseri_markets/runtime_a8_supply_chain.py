"""RUNTIME-A8: offline exact-source pins and OCI blob integrity inspection.

Cryptographic equality to committed pins is NOT publisher provenance,
signer trust, host attestation or permission to launch a Worker.
There is no network, Docker, shell, import, deployment, or key access.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ALLOWED_FILES = (
    "deploy/runtime_a2/Dockerfile",
    "scripts/runtime_a2_worker.py",
    "naseri_markets/multilang_runtime_a1.py",
)
_AUDIENCE = "MMT-RUNTIME-A8-OFFLINE-REVIEW-ONLY"
_LOCK_KEYS = frozenset({
    "schema", "audience", "baseline_commit", "lock_state", "source_files",
    "oci_manifest_digest", "independent_publisher_attestation",
    "host_isolation_certified", "execution_authorized",
})
_MAX_SOURCE = 256 * 1024
_MAX_BLOB = 1_073_741_824  # 1 GiB per file; streaming, no image execution
_OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
_OCI_CONFIG = "application/vnd.oci.image.config.v1+json"
_OCI_LAYERS = frozenset({
    "application/vnd.oci.image.layer.v1.tar",
    "application/vnd.oci.image.layer.v1.tar+gzip",
    "application/vnd.oci.image.layer.v1.tar+zstd",
})


class A8Refused(ValueError):
    """Refuse malformed / unpinned input without exposing local file contents."""


@dataclass(frozen=True, slots=True)
class SourceLockReview:
    checked_files: int
    baseline_commit: str
    status: str = "A8_SOURCE_SHA256_MATCH_EXTERNAL_MATERIALS_UNVERIFIED"
    external_dependency_provenance_verified: bool = False
    verified_worker_image_available: bool = False
    independently_attested: bool = False
    worker_execution_authorized: bool = False
    live_orders_authorized: bool = False
    telegram_authorized: bool = False


@dataclass(frozen=True, slots=True)
class OciLayoutReview:
    manifest_digest: str
    verified_blobs: int
    status: str = "A8_LOCAL_OCI_BLOBS_MATCH_NOT_PUBLISHER_VERIFIED"
    publisher_signature_verified: bool = False
    independently_attested: bool = False
    runnable_worker_approved: bool = False
    production_authorized: bool = False


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise A8Refused("A8_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _deny_number(_: str) -> None:
    raise A8Refused("A8_UNEXPECTED_FLOAT_OR_CONSTANT")


def _json(raw: bytes, *, max_size: int = 64 * 1024) -> object:
    if type(raw) is not bytes or not 0 < len(raw) <= max_size:
        raise A8Refused("A8_JSON_BYTE_LIMIT")
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_float=_deny_number, parse_constant=_deny_number,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, A8Refused):
            raise
        raise A8Refused("A8_JSON_MALFORMED") from exc


def _sha64(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _safe_blob(path: Path, root: Path, *, limit: int, exact_size: int | None = None) -> str:
    """Stream only owner-designated regular files, with no symlink components."""
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise A8Refused("A8_EXPLICIT_REAL_DIRECTORY_REQUIRED")
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise A8Refused("A8_PATH_OUTSIDE_ROOT") from exc
    current = root
    for part in path.relative_to(root).parts:
        if part in ("..", ".") or not part:
            raise A8Refused("A8_PATH_TRAVERSAL")
        current = current / part
        if current.is_symlink():
            raise A8Refused("A8_SYMLINK_REFUSED")
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= limit
                or exact_size is not None and info.st_size != exact_size):
            raise A8Refused("A8_FILE_TYPE_SIZE_REFUSED")
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for piece in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(piece)
    except OSError as exc:
        raise A8Refused("A8_FILE_UNAVAILABLE") from exc
    return digest.hexdigest()


def verify_source_lock(root: Path, lock_file: Path) -> SourceLockReview:
    """Match actual repository file bytes to explicit baseline pins, read-only."""
    if not isinstance(root, Path) or not isinstance(lock_file, Path):
        raise A8Refused("A8_EXPLICIT_PATHS_REQUIRED")
    root = root.absolute()
    lock_file = lock_file.absolute()
    if lock_file != root / "deploy/runtime_a2/a8_source_lock.json":
        raise A8Refused("A8_FIXED_LOCK_PATH_REQUIRED")
    _safe_blob(lock_file, root, limit=16 * 1024)
    document = _json(lock_file.read_bytes(), max_size=16 * 1024)
    if type(document) is not dict or set(document) != _LOCK_KEYS:
        raise A8Refused("A8_LOCK_SCHEMA_INVALID")
    if (type(document["schema"]) is not int or document["schema"] != 1
            or document["audience"] != _AUDIENCE
            or document["lock_state"] != "SOURCE_ONLY_EXTERNAL_UNVERIFIED"
            or type(document["baseline_commit"]) is not str
            or re.fullmatch(r"[a-f0-9]{40}", document["baseline_commit"]) is None
            or len(document["baseline_commit"]) != 40
            or document["oci_manifest_digest"] is not None
            or document["independent_publisher_attestation"] is not None
            or document["host_isolation_certified"] is not False
            or document["execution_authorized"] is not False):
        raise A8Refused("A8_UNTRUSTED_OR_PREMATURE_CERTIFICATION")
    files = document["source_files"]
    if type(files) is not list or len(files) != len(_ALLOWED_FILES):
        raise A8Refused("A8_SOURCE_FILE_SET_INVALID")
    for item, expected_path in zip(files, _ALLOWED_FILES, strict=True):
        if (type(item) is not dict or set(item) != {"path", "sha256"}
                or item["path"] != expected_path or not _sha64(item["sha256"])):
            raise A8Refused("A8_SOURCE_PIN_INVALID")
        found = _safe_blob(root / expected_path, root, limit=_MAX_SOURCE)
        if found != item["sha256"]:
            raise A8Refused("A8_SOURCE_DIGEST_MISMATCH")
    return SourceLockReview(len(files), document["baseline_commit"])


def _descriptor(item: object, *, kind: str) -> tuple[str, int]:
    valid_media = {_OCI_CONFIG} if kind == "config" else _OCI_LAYERS
    if (type(item) is not dict or set(item) != {"mediaType", "digest", "size"}
            or type(item["mediaType"]) is not str
            or item["mediaType"] not in valid_media
            or type(item["size"]) is not int
            or not 0 < item["size"] <= _MAX_BLOB
            or type(item["digest"]) is not str
            or not item["digest"].startswith("sha256:")
            or not _sha64(item["digest"][7:])):
        raise A8Refused("A8_OCI_DESCRIPTOR_INVALID")
    return item["digest"][7:], item["size"]


def verify_local_oci_layout(root: Path, manifest_sha256: str) -> OciLayoutReview:
    """Verify local OCI digest-addressed manifest/config/layers without running them.

    The expected manifest digest must be pinned by an independent operator.
    Even success does NOT establish a trusted publisher or an actual sandbox.
    """
    if not isinstance(root, Path) or not _sha64(manifest_sha256):
        raise A8Refused("A8_EXPLICIT_OCI_MANIFEST_PIN_REQUIRED")
    root = root.absolute()
    layout_path = root / "oci-layout"
    _safe_blob(layout_path, root, limit=4096)
    layout = _json(layout_path.read_bytes(), max_size=4096)
    if type(layout) is not dict or layout != {"imageLayoutVersion": "1.0.0"}:
        raise A8Refused("A8_OCI_LAYOUT_VERSION_INVALID")
    index_path = root / "index.json"
    _safe_blob(index_path, root, limit=64 * 1024)
    index = _json(index_path.read_bytes())
    if (type(index) is not dict or set(index) != {"schemaVersion", "manifests"}
            or type(index["schemaVersion"]) is not int
            or index["schemaVersion"] != 2
            or type(index["manifests"]) is not list
            or len(index["manifests"]) != 1):
        raise A8Refused("A8_OCI_INDEX_INVALID")
    ref = index["manifests"][0]
    if (type(ref) is not dict or set(ref) != {"mediaType", "digest", "size"}
            or ref["mediaType"] != _OCI_MANIFEST
            or ref["digest"] != f"sha256:{manifest_sha256}"
            or type(ref["size"]) is not int
            or not 0 < ref["size"] <= 1024 * 1024):
        raise A8Refused("A8_OCI_INDEX_PIN_INVALID")
    manifest_path = root / "blobs/sha256" / manifest_sha256
    found = _safe_blob(
        manifest_path, root, limit=1024 * 1024, exact_size=ref["size"],
    )
    if found != manifest_sha256:
        raise A8Refused("A8_OCI_MANIFEST_HASH_MISMATCH")
    manifest = _json(manifest_path.read_bytes(), max_size=1024 * 1024)
    if (type(manifest) is not dict
            or set(manifest) != {"schemaVersion", "mediaType", "config", "layers"}
            or type(manifest["schemaVersion"]) is not int
            or manifest["schemaVersion"] != 2
            or manifest["mediaType"] != _OCI_MANIFEST
            or type(manifest["layers"]) is not list
            or not 1 <= len(manifest["layers"]) <= 64):
        raise A8Refused("A8_OCI_MANIFEST_SCHEMA_INVALID")
    entries = [_descriptor(manifest["config"], kind="config")]
    entries += [_descriptor(x, kind="layer") for x in manifest["layers"]]
    if len({sha for sha, _ in entries}) != len(entries):
        raise A8Refused("A8_OCI_DUPLICATE_BLOB_DIGEST")
    for digest, size in entries:
        path = root / "blobs/sha256" / digest
        if _safe_blob(path, root, limit=_MAX_BLOB, exact_size=size) != digest:
            raise A8Refused("A8_OCI_LAYER_OR_CONFIG_HASH_MISMATCH")
    return OciLayoutReview(manifest_sha256, len(entries) + 1)


__all__ = [
    "A8Refused", "SourceLockReview", "OciLayoutReview",
    "verify_source_lock", "verify_local_oci_layout",
]
