"""Read-only, fail-closed signed stable v0.4.0 wheel verification.

Validates externally pinned artifact, signer and revocation policy. Does NOT
install, execute a wheel, activate a bot, place orders or grant LIVE access.
Unlike the historical R35-R38 preview tools, stable artifacts have a distinct
signature domain, filename, version, manifest schema and verification path.
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
import stat
import sys
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath

DOMAIN = b"MMT-V0.4.0-STABLE-ARTIFACT-MANIFEST-V1\n"
VERSION = "0.4.0"
DIST_NAME = "multi-market-trading"
WHEEL_NAME = "multi_market_trading-0.4.0-py3-none-any.whl"
DIST = "multi_market_trading-0.4.0.dist-info/"
MANIFEST_FIELDS = frozenset({
    "schema", "distribution", "version", "purpose", "source_commit",
    "source_date_epoch", "wheel_filename", "wheel_sha256", "wheel_size",
    "wheel_record_sha256",
})
POLICY_FIELDS = frozenset({
    "schema", "revision", "active_signers", "revoked_signers",
    "min_source_date_epoch",
})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
MAX_WHEEL = 12_000_000
MAX_UNPACKED = 36_000_000
MAX_MEMBERS = 750
_ALLOWED_DIST = frozenset({
    DIST + "METADATA", DIST + "WHEEL", DIST + "entry_points.txt",
    DIST + "top_level.txt", DIST + "RECORD",
})
_ALLOWED_REQUIREMENTS = {
    "telegram-admin": frozenset({"python-telegram-bot==22.8"}),
    "brooks-offline": frozenset({
        "alembic==1.20.0", "asyncpg==0.31.0", "httpx==0.28.1",
        "matplotlib==3.11.2", "numpy==2.5.3",
        "pydantic-settings==2.15.0", "python-telegram-bot==22.8",
        "sqlalchemy[asyncio]==2.0.54", "tzdata==2026.4",
    }),
}
_OPTIONAL_SPEC = re.compile(
    r"([^;\s]+)\s*;\s*extra\s*==\s*([\"'])(telegram-admin|brooks-offline)\2\s*\Z"
)
_ALLOWED_COMMANDS = {
    "naseri-markets": "naseri_markets.platform_cli:main",
    "naseri-custom": "naseri_markets.custom_cli:main",
    "naseri-paper-demo": "naseri_markets.paper_demo_cli_v1:main",
    "naseri-paper-pilot": "naseri_markets.installed_paper_pilot_stage10_v1:main",
    "naseri-engine-admin": "naseri_markets.bot_admin_app:main",
    "naseri-brooks-replay": "naseri_markets.brooks_replay:main",
    "naseri-brooks-market": "naseri_markets.brooks_market_feed:main",
    "naseri-brooks-kraken-paper": "naseri_markets.brooks_kraken_feed:main",
    "naseri-brooks-paper-service": "naseri_markets.brooks_paper_service:main",
}


class StableArtifactRefused(ValueError):
    """Fixed failure classification; no caller secrets or payload are returned."""


def _read(path: Path, limit: int) -> bytes:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or path.parent.is_symlink()):
        raise StableArtifactRefused("V040_ABSOLUTE_REGULAR_FILE_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise StableArtifactRefused("V040_FILE_UNREADABLE") from exc
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or not 1 <= st.st_size <= limit):
            raise StableArtifactRefused("V040_BOUNDED_SINGLE_LINK_REQUIRED")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        if (len(raw) != st.st_size or len(raw) > limit
                or os.fstat(fd).st_size != st.st_size):
            raise StableArtifactRefused("V040_FILE_CHANGED_OR_TOO_LARGE")
        return raw
    finally:
        os.close(fd)


def _pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise StableArtifactRefused("V040_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _canonical_json(raw: bytes, required_fields: frozenset[str]) -> dict:
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except StableArtifactRefused:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise StableArtifactRefused("V040_JSON_INVALID") from exc
    if type(obj) is not dict or set(obj) != required_fields:
        raise StableArtifactRefused("V040_JSON_SCHEMA_INVALID")
    try:
        canonical = (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n")
    except (ValueError, TypeError, RecursionError) as exc:
        raise StableArtifactRefused("V040_JSON_INVALID") from exc
    if canonical != raw:
        raise StableArtifactRefused("V040_JSON_NONCANONICAL")
    return obj


def _pin(pin: str) -> bool:
    return type(pin) is str and SHA256.fullmatch(pin) is not None


def _manifest(raw: bytes) -> dict:
    data = _canonical_json(raw, MANIFEST_FIELDS)
    if (type(data["schema"]) is not int or data["schema"] != 1
            or data["distribution"] != DIST_NAME
            or data["version"] != VERSION
            or data["purpose"] != "offline-paper-release-only"
            or type(data["source_commit"]) is not str
            or not COMMIT.fullmatch(data["source_commit"])
            or type(data["source_date_epoch"]) is not int
            or not 315532800 <= data["source_date_epoch"] <= 4102444800
            or data["wheel_filename"] != WHEEL_NAME
            or not _pin(data["wheel_sha256"])
            or not _pin(data["wheel_record_sha256"])
            or type(data["wheel_size"]) is not int
            or not 128 <= data["wheel_size"] <= MAX_WHEEL):
        raise StableArtifactRefused("V040_MANIFEST_VALUE_INVALID")
    return data


def _policy(raw: bytes, fingerprint: str, manifest: dict) -> dict:
    data = _canonical_json(raw, POLICY_FIELDS)
    active, revoked = data["active_signers"], data["revoked_signers"]
    if (type(data["schema"]) is not int or data["schema"] != 1
            or type(data["revision"]) is not int or data["revision"] < 1
            or type(data["min_source_date_epoch"]) is not int
            or not 315532800 <= data["min_source_date_epoch"] <= 4102444800
            or type(active) is not list or type(revoked) is not list
            or len(active) > 32 or len(revoked) > 128
            or not all(_pin(item) for item in [*active, *revoked])
            or active != sorted(set(active))
            or revoked != sorted(set(revoked))
            or set(active) & set(revoked)):
        raise StableArtifactRefused("V040_POLICY_VALUE_INVALID")
    if fingerprint in revoked:
        raise StableArtifactRefused("V040_SIGNER_REVOKED")
    if fingerprint not in active:
        raise StableArtifactRefused("V040_SIGNER_NOT_TRUSTED")
    if manifest["source_date_epoch"] < data["min_source_date_epoch"]:
        raise StableArtifactRefused("V040_STALE_MANIFEST_DENIED")
    return data


def _safe_member(name: str, info: zipfile.ZipInfo) -> bool:
    if (not name or "\\" in name or "\x00" in name
            or name.startswith("/") or "//" in name
            or any(p in (".", "..", "") for p in name.split("/"))):
        return False
    path = PurePosixPath(name)
    if path.as_posix() != name or path.is_absolute():
        return False
    if info.flag_bits & 1:
        return False
    if ("private_nyfr_core" in name or "r0_engine" in name
            or ".env" in path.parts):
        return False
    unix_type = stat.S_IFMT(info.external_attr >> 16)
    if unix_type not in (0, stat.S_IFREG):
        return False
    if name.startswith("naseri_markets/"):
        return len(path.parts) == 2 and name.endswith(".py") and len(path.name) > 3
    return name in _ALLOWED_DIST


def _check_record(members: dict[str, bytes]) -> None:
    try:
        rows = list(csv.reader(io.StringIO(members[DIST + "RECORD"].decode("utf-8"))))
    except (KeyError, UnicodeError, csv.Error) as exc:
        raise StableArtifactRefused("V040_RECORD_INVALID") from exc
    if len(rows) != len(members):
        raise StableArtifactRefused("V040_RECORD_COUNT_INVALID")
    seen = set()
    for row in rows:
        if len(row) != 3:
            raise StableArtifactRefused("V040_RECORD_ROW_INVALID")
        name, digest, size = row
        if name not in members or name in seen:
            raise StableArtifactRefused("V040_RECORD_DUPLICATE_OR_UNKNOWN")
        seen.add(name)
        if name == DIST + "RECORD":
            if digest or size:
                raise StableArtifactRefused("V040_RECORD_SELF_HASH_INVALID")
            continue
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(members[name]).digest()).rstrip(b"=").decode("ascii")
        if digest != "sha256=" + expected or size != str(len(members[name])):
            raise StableArtifactRefused("V040_RECORD_MEMBER_HASH_INVALID")
    if seen != set(members):
        raise StableArtifactRefused("V040_RECORD_MEMBER_SET_INVALID")


def _wheel(raw: bytes, record_pin: str) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if not 6 <= len(infos) <= MAX_MEMBERS:
                raise StableArtifactRefused("V040_WHEEL_MEMBER_COUNT_INVALID")
            if (len({i.filename for i in infos}) != len(infos)
                    or sum(i.file_size for i in infos) > MAX_UNPACKED
                    or any(not _safe_member(i.filename, i) for i in infos)):
                raise StableArtifactRefused("V040_WHEEL_MEMBER_UNSAFE")
            members = {i.filename: archive.read(i) for i in infos}
            if (not _ALLOWED_DIST.issubset(members)
                    or "naseri_markets/platform_cli.py" not in members
                    or "naseri_markets/platform_version_policy_v1.py" not in members):
                raise StableArtifactRefused("V040_WHEEL_REQUIRED_MODULE_MISSING")
            record = members[DIST + "RECORD"]
            if hashlib.sha256(record).hexdigest() != record_pin:
                raise StableArtifactRefused("V040_RECORD_INDEPENDENT_PIN_MISMATCH")
            _check_record(members)
            metadata = Parser().parsestr(members[DIST + "METADATA"].decode("utf-8"))
            if (len(metadata.get_all("Name", [])) != 1
                    or len(metadata.get_all("Version", [])) != 1
                    or len(metadata.get_all("Requires-Python", [])) != 1
                    or metadata.get("Name") != DIST_NAME
                    or metadata.get("Version") != VERSION
                    or metadata.get("Requires-Python") != ">=3.12,<3.13"):
                raise StableArtifactRefused("V040_WHEEL_IDENTITY_INVALID")
            # Enforce the exact approved optional-dependency closure. Never
            # infer an allowed extra from an untrusted marker substring.
            extras = {name: set() for name in _ALLOWED_REQUIREMENTS}
            for required in metadata.get_all("Requires-Dist", []):
                matched = _OPTIONAL_SPEC.fullmatch(required)
                if matched is None:
                    raise StableArtifactRefused("V040_WHEEL_BASE_DEPENDENCY_INVALID")
                spec, _, extra = matched.groups()
                normalized = spec.lower()
                if (normalized not in _ALLOWED_REQUIREMENTS[extra]
                        or normalized in extras[extra]):
                    raise StableArtifactRefused("V040_WHEEL_BASE_DEPENDENCY_INVALID")
                extras[extra].add(normalized)
            if any(extras[name] != expected
                   for name, expected in _ALLOWED_REQUIREMENTS.items()):
                raise StableArtifactRefused("V040_WHEEL_OPTIONAL_LOCK_INCOMPLETE")
            if ("Tag: py3-none-any" not in members[DIST + "WHEEL"].decode("utf-8")
                    or "Root-Is-Purelib: true" not in members[DIST + "WHEEL"].decode("utf-8")):
                raise StableArtifactRefused("V040_WHEEL_TAG_INVALID")
            ini = configparser.ConfigParser(interpolation=None)
            ini.read_string(members[DIST + "entry_points.txt"].decode("utf-8"))
            if not ini.has_section("console_scripts") or dict(ini.items("console_scripts")) != _ALLOWED_COMMANDS:
                raise StableArtifactRefused("V040_ENTRYPOINT_SET_INVALID")
            if members[DIST + "top_level.txt"].strip() != b"naseri_markets":
                raise StableArtifactRefused("V040_TOP_LEVEL_PACKAGE_INVALID")
            return {"members_verified": len(members), "record_verified": True}
    except StableArtifactRefused:
        raise
    except (OSError, UnicodeError, ValueError, KeyError, RecursionError,
            configparser.Error, zipfile.BadZipFile, RuntimeError, OverflowError) as exc:
        raise StableArtifactRefused("V040_WHEEL_FORMAT_INVALID") from exc


def verify(*, manifest: Path, signature: Path, wheel: Path,
           trusted_public_key: Path, trusted_public_key_spki_sha256: str,
           policy: Path, expected_policy_sha256: str,
           expected_manifest_sha256: str, expected_source_commit: str) -> dict:
    """Read only; output never grants installation, publication, LIVE or trade."""
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise StableArtifactRefused("V040_NONPRODUCTION_REQUIRED")
    if (not _pin(trusted_public_key_spki_sha256)
            or not _pin(expected_policy_sha256)
            or not _pin(expected_manifest_sha256)
            or type(expected_source_commit) is not str
            or not COMMIT.fullmatch(expected_source_commit)):
        raise StableArtifactRefused("V040_EXTERNAL_TRUST_PINS_REQUIRED")
    if wheel.name != WHEEL_NAME:
        raise StableArtifactRefused("V040_STABLE_WHEEL_FILENAME_REQUIRED")
    manifest_raw = _read(manifest, 4096)
    if hashlib.sha256(manifest_raw).hexdigest() != expected_manifest_sha256:
        raise StableArtifactRefused("V040_MANIFEST_EXTERNAL_PIN_MISMATCH")
    evidence = _manifest(manifest_raw)
    if evidence["source_commit"] != expected_source_commit:
        raise StableArtifactRefused("V040_SOURCE_COMMIT_MISMATCH")
    policy_raw = _read(policy, 8192)
    if hashlib.sha256(policy_raw).hexdigest() != expected_policy_sha256:
        raise StableArtifactRefused("V040_POLICY_EXTERNAL_PIN_MISMATCH")
    _policy(policy_raw, trusted_public_key_spki_sha256, evidence)
    key_data = _read(trusted_public_key, 4096)
    signature_raw = _read(signature, 64)
    if len(signature_raw) != 64:
        raise StableArtifactRefused("V040_SIGNATURE_SIZE_INVALID")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = serialization.load_pem_public_key(key_data)
        if not isinstance(key, Ed25519PublicKey):
            raise StableArtifactRefused("V040_ED25519_SIGNER_REQUIRED")
        spki = key.public_bytes(serialization.Encoding.DER,
                                serialization.PublicFormat.SubjectPublicKeyInfo)
        if hashlib.sha256(spki).hexdigest() != trusted_public_key_spki_sha256:
            raise StableArtifactRefused("V040_SIGNER_FINGERPRINT_MISMATCH")
        key.verify(signature_raw, DOMAIN + manifest_raw)
    except ImportError as exc:
        raise StableArtifactRefused("V040_CRYPTOGRAPHY_AUDITOR_MISSING") from exc
    except (InvalidSignature, ValueError, TypeError) as exc:
        if isinstance(exc, StableArtifactRefused):
            raise
        raise StableArtifactRefused("V040_SIGNATURE_VERIFICATION_FAILED") from exc
    raw = _read(wheel, MAX_WHEEL)
    if (hashlib.sha256(raw).hexdigest() != evidence["wheel_sha256"]
            or len(raw) != evidence["wheel_size"]):
        raise StableArtifactRefused("V040_WHEEL_BYTES_MISMATCH")
    package = _wheel(raw, evidence["wheel_record_sha256"])
    return {
        "verdict": "V040_OFFLINE_STABLE_ARTIFACT_CRYPTOGRAPHIC_PREFLIGHT_PASS_RELEASE_DENIED",
        "source_commit": expected_source_commit,
        "wheel_sha256": evidence["wheel_sha256"],
        "signer_spki_sha256": trusted_public_key_spki_sha256,
        "policy_revision": _canonical_json(policy_raw, POLICY_FIELDS)["revision"],
        **package,
        "writes_performed": False,
        "install_authorized": False,
        "public_release_authorized": False,
        "live_trading_authorized": False,
        "telegram_publication_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "signature", "wheel", "trusted-public-key", "policy"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("trusted-public-key-spki-sha256", "expected-policy-sha256",
                 "expected-manifest-sha256", "expected-source-commit"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(
            manifest=args.manifest, signature=args.signature, wheel=args.wheel,
            trusted_public_key=args.trusted_public_key,
            trusted_public_key_spki_sha256=args.trusted_public_key_spki_sha256,
            policy=args.policy, expected_policy_sha256=args.expected_policy_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_source_commit=args.expected_source_commit,
        )
    except (StableArtifactRefused, OSError) as exc:
        reason = str(exc) if isinstance(exc, StableArtifactRefused) else "V040_IO_REFUSED"
        print(json.dumps({"verdict": "V040_ARTIFACT_REFUSED", "reason": reason,
                          "install_authorized": False,
                          "public_release_authorized": False,
                          "live_trading_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
