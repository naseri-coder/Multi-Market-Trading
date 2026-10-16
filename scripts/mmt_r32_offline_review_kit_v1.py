"""R32 offline, pinned-source REVIEW package: never an install or release grant.

Copies only specifically named public R28-R31 review files into a NEW private
directory. No code import, shell install, network, credential, DB read/write,
service activation, restore or automatic retry. A local git commit is NOT a
trusted publisher signature or release approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

PROTOCOL = "MMT_R32_OFFLINE_SOURCE_REVIEW_KIT_V1"
LIMIT = 1_048_576
SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
FILES = (
    "naseri_markets/mmt_r28_unified_offline_runtime_v1.py",
    "naseri_markets/brooks_future_shadow_paper_mmt_r29_v1.py",
    "naseri_markets/mmt_r29_shadow_session_audit_v1.py",
    "naseri_markets/mmt_r30_offline_risk_order_preflight_v1.py",
    "naseri_markets/mmt_r31_private_admin_console_v1.py",
    "scripts/mmt_r29_manual_future_shadow.py",
    "scripts/mmt_r29_manual_shadow_audit.py",
    "tests/unit/test_mmt_r29_real_source_shadow_paper_v1.py",
    "tests/unit/test_mmt_r30_offline_risk_order_preflight_v1.py",
    "tests/unit/test_mmt_r31_private_admin_console_v1.py",
    "docs/MMT_R28_UNIFIED_OFFLINE_RUNTIME_AND_RECOVERY_FENCE.md",
    "docs/MMT_R29_REAL_SOURCE_MANUAL_SHADOW_PAPER.md",
    "docs/MMT_R30_OFFLINE_RISK_AND_ORDER_STATE_GATES.md",
    "docs/MMT_R31_PRIVATE_ADMIN_HEALTH_AND_SIGNAL_REVIEW.md",
)
NOTE = (
    "MMT-R32: OFFLINE SOURCE REVIEW KIT ONLY\n"
    "THIS IS NOT AN INSTALLER, DEPLOYMENT, ACTIVITY CERTIFICATE OR BACKUP.\n"
    "The included sources are a non-runnable partial code snapshot.\n"
    "No main merge, service launch, broker order, LIVE or Telegram signal send.\n"
    "Git SHA and SHA256 integrity do NOT attest independent publisher identity.\n"
    "Review the stacked Draft PRs, tests, original data and release gates.\n"
)


class R32KitRefused(ValueError):
    """Constant, non-secret error codes."""


def _canon(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=True,
    ).encode("ascii")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gate(operator_ack: bool) -> None:
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise R32KitRefused("R32_EXPLICIT_OFFLINE_ACK_REQUIRED")


def _secure_parent(path: Path) -> Path:
    if (type(path) is not Path or not path.is_absolute()
            or path.is_symlink() or not path.is_dir()
            or path.resolve(strict=True) != path):
        raise R32KitRefused("R32_EXISTING_PRIVATE_PARENT_REQUIRED")
    st = path.stat()
    if (st.st_uid != os.geteuid()
            or stat.S_IMODE(st.st_mode) & 0o077):
        raise R32KitRefused("R32_EXISTING_PRIVATE_PARENT_REQUIRED")
    return path


def _git(root: Path, *args: str) -> str:
    try:
        p = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, check=False, timeout=8,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0",
                 "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise R32KitRefused("R32_LOCAL_GIT_UNAVAILABLE") from exc
    if p.returncode != 0 or len(p.stdout) > 32_768:
        raise R32KitRefused("R32_GIT_VERIFICATION_REFUSED")
    return p.stdout.strip()


def _source(root: Path, expected_head: str) -> None:
    if (type(root) is not Path or not root.is_absolute()
            or root.is_symlink() or not root.is_dir()
            or root.resolve(strict=True) != root
            or type(expected_head) is not str
            or SHA.fullmatch(expected_head) is None):
        raise R32KitRefused("R32_ABSOLUTE_ROOT_AND_PIN_REQUIRED")
    if (Path(_git(root, "rev-parse", "--show-toplevel")) != root
            or _git(root, "rev-parse", "HEAD") != expected_head):
        raise R32KitRefused("R32_EXACT_CHECKOUT_SHA_MISMATCH")
    # No hidden dirty/untracked files are silently packaged. Run entirely
    # outside the checkout; git status includes submodule status by default.
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise R32KitRefused("R32_DIRTY_CHECKOUT_REFUSED")


def _read(path: Path, base: Path, *, max_bytes: int = LIMIT) -> bytes:
    if (not path.is_relative_to(base)
            or any(p.is_symlink() for p in (
                path, *(parent for parent in path.parents if
                        parent != base and parent.is_relative_to(base))
            ))):
        raise R32KitRefused("R32_SYMLINK_OR_PATH_ESCAPE")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or not 1 <= st.st_size <= max_bytes):
                raise R32KitRefused("R32_REGULAR_BOUNDED_FILE_REQUIRED")
            with os.fdopen(fd, "rb", closefd=False) as f:
                data = f.read(max_bytes + 1)
            if len(data) != st.st_size:
                raise R32KitRefused("R32_FILE_CHANGED_DURING_READ")
            return data
        finally:
            os.close(fd)
    except OSError as exc:
        raise R32KitRefused("R32_FILE_READ_REFUSED") from exc


def _create(path: Path, data: bytes) -> None:
    if type(data) is not bytes:
        raise R32KitRefused("R32_BYTES_REQUIRED")
    try:
        fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:
        raise R32KitRefused("R32_EXCLUSIVE_WRITE_REFUSED") from exc


def prepare_r32_review_kit(
    *, source_root: Path, destination: Path, expected_head: str,
    operator_ack: bool = False,
) -> dict:
    """Only a fresh, owned and private out-of-checkout directory is changed.

    This is source custody tooling, not a production deployment or recovery.
    On any failure, files are kept for explicit human review rather than an
    unsafe recursive deletion of a potentially replaced/symlinked directory.
    """
    _gate(operator_ack)
    _source(source_root, expected_head)
    if type(destination) is not Path or not destination.is_absolute():
        raise R32KitRefused("R32_ABSOLUTE_NEW_DESTINATION_REQUIRED")
    if destination.is_relative_to(source_root):
        raise R32KitRefused("R32_NEVER_WRITE_WITHIN_CHECKOUT")
    _secure_parent(destination.parent)
    try:
        os.mkdir(destination, 0o700)
    except OSError as exc:
        raise R32KitRefused("R32_NEW_DESTINATION_ONLY") from exc
    os.mkdir(destination / "review-files", 0o700)
    records = {}
    for relative in FILES:
        path = source_root / relative
        data = _read(path, source_root)
        out = destination / "review-files" / relative
        out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _create(out, data)
        records[relative] = {"sha256": _digest(data), "size": len(data)}
    manifest = {
        "protocol": PROTOCOL, "schema": 1, "review_commit": expected_head,
        "partial_review_files": records,
        "independent_signer_verified": False,
        "artifact_reproducibility_certified": False,
        "supply_chain_security_certified": False,
        "complete_application_included": False,
        "real_installer_included": False,
        "production_install_allowed": False,
        "paper_or_live_enabled": False,
        "broker_orders_enabled": False, "telegram_sending_enabled": False,
        "restore_authorized": False,
    }
    _create(destination / "manifest.json", _canon(manifest))
    _create(destination / "READ_ME_NOT_AN_INSTALLER.txt", NOTE.encode("ascii"))
    return verify_r32_review_kit(destination, operator_ack=True)


def verify_r32_review_kit(
    directory: Path, *, operator_ack: bool = False,
) -> dict:
    """Verify a complete local kit against its included SHA manifest.

    Malicious replacement of both files and manifest is NOT detectable unless
    an independent reviewer retains and checks the report SHA out of band.
    """
    _gate(operator_ack)
    _secure_parent(directory)
    raw = _read(directory / "manifest.json", directory, max_bytes=8192)
    try:
        obj = json.loads(raw.decode("ascii"))
    except (ValueError, UnicodeError, TypeError) as exc:
        raise R32KitRefused("R32_MANIFEST_INVALID") from exc
    if (type(obj) is not dict or _canon(obj) != raw
            or obj.get("protocol") != PROTOCOL
            or obj.get("schema") != 1
            or type(obj.get("review_commit")) is not str
            or SHA.fullmatch(obj["review_commit"]) is None
            or any(obj.get(field) is not False for field in (
                "independent_signer_verified", "artifact_reproducibility_certified",
                "supply_chain_security_certified", "complete_application_included",
                "real_installer_included", "production_install_allowed",
                "paper_or_live_enabled", "broker_orders_enabled",
                "telegram_sending_enabled", "restore_authorized",
            ))):
        raise R32KitRefused("R32_REVIEW_ONLY_MANIFEST_REQUIRED")
    expected = obj.get("partial_review_files")
    if type(expected) is not dict or tuple(sorted(expected)) != tuple(sorted(FILES)):
        raise R32KitRefused("R32_COMPLETE_REVIEW_FILE_SET_REQUIRED")
    if set(p.name for p in directory.iterdir()) != {
        "review-files", "manifest.json", "READ_ME_NOT_AN_INSTALLER.txt",
    }:
        raise R32KitRefused("R32_UNEXPECTED_TOP_LEVEL_ENTRIES")
    payload = directory / "review-files"
    if payload.is_symlink() or not payload.is_dir():
        raise R32KitRefused("R32_PAYLOAD_DIR_INVALID")
    found = set()
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise R32KitRefused("R32_SYMLINK_IN_PACKAGE")
        if path.is_file():
            found.add(path.relative_to(payload).as_posix())
        elif not path.is_dir():
            raise R32KitRefused("R32_UNEXPECTED_PACKAGE_NODE")
    if found != set(FILES):
        raise R32KitRefused("R32_FILE_LIST_MISMATCH")
    for name in FILES:
        entry = expected[name]
        if (type(entry) is not dict or set(entry) != {"sha256", "size"}
                or type(entry["sha256"]) is not str
                or _DIGEST.fullmatch(entry["sha256"]) is None
                or type(entry["size"]) is not int
                or not 1 <= entry["size"] <= LIMIT):
            raise R32KitRefused("R32_BAD_MANIFEST_ENTRY")
        data = _read(payload / name, payload)
        if len(data) != entry["size"] or _digest(data) != entry["sha256"]:
            raise R32KitRefused("R32_PACKAGE_CONTENT_MISMATCH")
    if _read(directory / "READ_ME_NOT_AN_INSTALLER.txt", directory) != NOTE.encode("ascii"):
        raise R32KitRefused("R32_README_TAMPERED")
    return {
        "protocol": PROTOCOL,
        "review_commit": obj["review_commit"],
        "review_files": len(FILES),
        "local_manifest_sha256": _digest(raw),
        "local_content_integrity": "MATCHES_MUTABLE_LOCAL_MANIFEST_ONLY",
        "standalone_install_ready": False,
        "publisher_identity_attested": False,
        "code_security_proven": False,
        "production_install_allowed": False,
        "restore_authorized": False,
        "broker_order_authorized": False,
        "telegram_send_authorized": False,
        "live_trading_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R32 offline source review kit (NO INSTALL)")
    sub = parser.add_subparsers(dest="mode", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--source-root", type=Path, required=True)
    prep.add_argument("--destination", type=Path, required=True)
    prep.add_argument("--expected-head", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--directory", type=Path, required=True)
    for cmd in (prep, check):
        cmd.add_argument("--ack-review-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "prepare":
            result = prepare_r32_review_kit(
                source_root=args.source_root.absolute(),
                destination=args.destination.absolute(),
                expected_head=args.expected_head,
                operator_ack=args.ack_review_only,
            )
        else:
            result = verify_r32_review_kit(
                args.directory.absolute(), operator_ack=args.ack_review_only,
            )
    except (R32KitRefused, OSError):
        print(_canon({"status": "REFUSED_REVIEW_REQUIRED",
                      "production_install_allowed": False}).decode("ascii"))
        return 2
    print(_canon(result).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
