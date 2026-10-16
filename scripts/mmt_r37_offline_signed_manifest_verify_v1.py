"""R37 strictly read-only Ed25519 detached offline-preview manifest verifier.

Requires separately pinned, operator-trusted public key fingerprint. Never
signs, installs, executes, trades, or authorizes a public/production release.
Cryptography is an audit-tool-only dependency, not a platform dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

DOMAIN = b"MMT-R37-OFFLINE-PREVIEW-MANIFEST-V1\n"
WHEEL_NAME = "multi_market_trading-0.4.0rc1-py3-none-any.whl"
SHA256 = re.compile(r"[a-f0-9]{64}\\Z")
COMMIT = re.compile(r"[a-f0-9]{40}\\Z")
FIELDS = frozenset({
    "schema", "distribution", "version", "purpose", "source_commit",
    "source_date_epoch", "wheel_filename", "wheel_sha256", "wheel_size",
})


class R37Refused(ValueError):
    """Fail closed with constant, non-sensitive refusal codes."""


def _read(path: Path, limit: int) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise R37Refused("R37_ABSOLUTE_REGULAR_FILE_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise R37Refused("R37_FILE_UNREADABLE") from exc
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or not 1 <= metadata.st_size <= limit):
            raise R37Refused("R37_BOUNDED_SINGLE_LINK_FILE_REQUIRED")
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise R37Refused("R37_FILE_SIZE_LIMIT")
        if total != metadata.st_size or os.fstat(fd).st_size != total:
            raise R37Refused("R37_FILE_CHANGED_DURING_READ")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise R37Refused("R37_DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def _manifest(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, R37Refused):
            raise
        raise R37Refused("R37_INVALID_MANIFEST_JSON") from exc
    if type(value) is not dict or set(value) != FIELDS:
        raise R37Refused("R37_MANIFEST_SCHEMA_FIELDS_INVALID")
    if json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n" != raw:
        raise R37Refused("R37_NONCANONICAL_MANIFEST")
    if (type(value["schema"]) is not int or value["schema"] != 1
            or value["distribution"] != "multi-market-trading"
            or value["version"] != "0.4.0rc1"
            or value["purpose"] != "offline-preview-only"
            or type(value["source_commit"]) is not str
            or not COMMIT.fullmatch(value["source_commit"])
            or type(value["source_date_epoch"]) is not int
            or not 315532800 <= value["source_date_epoch"] <= 4102444800
            or value["wheel_filename"] != WHEEL_NAME
            or type(value["wheel_sha256"]) is not str
            or not SHA256.fullmatch(value["wheel_sha256"])
            or type(value["wheel_size"]) is not int
            or not 128 <= value["wheel_size"] <= 12_000_000):
        raise R37Refused("R37_MANIFEST_VALUES_INVALID")
    return value


def verify(*, manifest: Path, signature: Path, wheel: Path,
           trusted_public_key: Path, trusted_public_key_spki_sha256: str,
           expected_source_commit: str) -> dict:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or sys.version_info[:2] != (3, 12)):
        raise R37Refused("R37_NONPRODUCTION_PY312_REQUIRED")
    if (type(trusted_public_key_spki_sha256) is not str
            or not SHA256.fullmatch(trusted_public_key_spki_sha256)
            or type(expected_source_commit) is not str
            or not COMMIT.fullmatch(expected_source_commit)):
        raise R37Refused("R37_EXTERNAL_TRUST_PINS_REQUIRED")
    data = _read(manifest, 4096)
    description = _manifest(data)
    if description["source_commit"] != expected_source_commit:
        raise R37Refused("R37_SOURCE_PIN_MISMATCH")
    if wheel.name != WHEEL_NAME:
        raise R37Refused("R37_WHEEL_FILENAME_INVALID")
    sig = _read(signature, 64)
    if len(sig) != 64:
        raise R37Refused("R37_ED25519_SIGNATURE_LENGTH_INVALID")
    key_bytes = _read(trusted_public_key, 4096)
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(key, Ed25519PublicKey):
            raise R37Refused("R37_ED25519_PUBLIC_KEY_REQUIRED")
        spki = key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if hashlib.sha256(spki).hexdigest() != trusted_public_key_spki_sha256:
            raise R37Refused("R37_TRUSTED_KEY_PIN_MISMATCH")
        key.verify(sig, DOMAIN + data)
    except ImportError as exc:
        raise R37Refused("R37_CRYPTOGRAPHY_AUDITOR_NOT_INSTALLED") from exc
    except (InvalidSignature, ValueError, TypeError) as exc:
        if isinstance(exc, R37Refused):
            raise
        raise R37Refused("R37_INVALID_ED25519_SIGNATURE_OR_KEY") from exc
    raw_wheel = _read(wheel, 12_000_000)
    if len(raw_wheel) != description["wheel_size"]:
        raise R37Refused("R37_SIGNED_WHEEL_SIZE_MISMATCH")
    digest = hashlib.sha256(raw_wheel).hexdigest()
    if digest != description["wheel_sha256"]:
        raise R37Refused("R37_SIGNED_WHEEL_HASH_MISMATCH")
    return {
        "verdict": "R37_SIGNED_OFFLINE_PREVIEW_MANIFEST_VALID_RELEASE_DENIED",
        "wheel_sha256": digest,
        "source_commit": expected_source_commit,
        "trusted_key_spki_sha256": trusted_public_key_spki_sha256,
        "manifest_signature_valid": True,
        "files_written": False,
        "install_authorized": False,
        "public_release_authorized": False,
        "live_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "signature", "wheel", "trusted-public-key"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--trusted-public-key-spki-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    args = parser.parse_args(argv)
    try:
        answer = verify(
            manifest=args.manifest, signature=args.signature,
            wheel=args.wheel, trusted_public_key=args.trusted_public_key,
            trusted_public_key_spki_sha256=args.trusted_public_key_spki_sha256,
            expected_source_commit=args.expected_source_commit,
        )
    except (R37Refused, OSError) as exc:
        print(json.dumps({
            "verdict": "R37_SIGNATURE_AUDIT_REFUSED",
            "reason": str(exc) if isinstance(exc, R37Refused) else "R37_IO_REFUSED",
            "public_release_authorized": False,
            "live_authorized": False,
            "files_written": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(answer, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
