"""R40: read-only installed synthetic PAPER acceptance, Brooks explicitly deferred.

No worker, strategy, market connection, reconciliation write, restart, signal,
order, deployment, migration or release entitlement is ever invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from . import offline_authoritative_paper_journey_r39_v1 as r39

_WHEEL_DISTRIBUTION = "multi-market-trading"
_WHEEL_VERSION = "0.4.0rc1"
_R39_RELATIVE = "naseri_markets/offline_authoritative_paper_journey_r39_v1.py"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_STATE_FILE = 32 * 1024 * 1024
_FILES = (
    "authority.sqlite",
    "pilot/control.sqlite",
    "pilot/paper.sqlite",
    "pilot/signals.sqlite",
    "pilot/runtime.sqlite",
    "pilot/effects.sqlite",
)


class R40Refused(ValueError):
    """Fixed, non-sensitive failure codes: no permission to repair or retry."""


def _gate(*, operator_ack: bool, writers_stopped: bool) -> None:
    if (operator_ack is not True or writers_stopped is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or sys.version_info[:2] != (3, 12)
            or os.geteuid() == 0):
        raise R40Refused("R40_NONROOT_PY312_STOPPED_WRITERS_ACK_REQUIRED")


def _regular_sha256(path: Path, *, limit: int, owner_only: bool) -> str:
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise R40Refused("R40_ABSOLUTE_UNLINKED_REGULAR_FILE_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise R40Refused("R40_EVIDENCE_FILE_UNREADABLE") from exc
    try:
        start = os.fstat(fd)
        if (not stat.S_ISREG(start.st_mode) or start.st_nlink != 1
                or not 1 <= start.st_size <= limit
                or (owner_only and (
                    start.st_uid != os.geteuid()
                    or stat.S_IMODE(start.st_mode) != 0o600))):
            raise R40Refused("R40_UNSAFE_EVIDENCE_FILE")
        sha = hashlib.sha256()
        count = 0
        while count < start.st_size:
            part = os.read(fd, min(65536, start.st_size - count))
            if not part:
                raise R40Refused("R40_EVIDENCE_TRUNCATED")
            sha.update(part)
            count += len(part)
        end = os.fstat(fd)
        if ((start.st_dev, start.st_ino, start.st_size, start.st_mtime_ns)
                != (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns)):
            raise R40Refused("R40_EVIDENCE_CHANGED_DURING_READ")
        return sha.hexdigest()
    finally:
        os.close(fd)


def _installed_identity(expected_module_sha256: str) -> dict:
    """Require an ordinary *wheel-installed* R39 module, not an editable tree."""
    if type(expected_module_sha256) is not str or not _SHA.fullmatch(
        expected_module_sha256
    ):
        raise R40Refused("R40_INDEPENDENT_R39_MODULE_PIN_REQUIRED")
    try:
        dist = distribution(_WHEEL_DISTRIBUTION)
    except PackageNotFoundError as exc:
        raise R40Refused("R40_INSTALLED_WHEEL_DISTRIBUTION_REQUIRED") from exc
    if dist.version != _WHEEL_VERSION:
        raise R40Refused("R40_PREVIEW_VERSION_MISMATCH")
    members = dist.files
    if members is None or _R39_RELATIVE not in {str(name) for name in members}:
        raise R40Refused("R40_INSTALLED_R39_MODULE_MISSING")
    # Editable installs are not independently packaged Wheel artifacts.
    direct_url = dist.read_text("direct_url.json")
    if direct_url is not None:
        try:
            record = json.loads(direct_url)
        except (ValueError, TypeError) as exc:
            raise R40Refused("R40_INSTALLED_DIRECT_URL_INVALID") from exc
        if type(record) is not dict:
            raise R40Refused("R40_INSTALLED_DIRECT_URL_INVALID")
        dir_info = record.get("dir_info", {})
        if type(dir_info) is not dict:
            raise R40Refused("R40_INSTALLED_DIRECT_URL_INVALID")
        if dir_info.get("editable") is True:
            raise R40Refused("R40_EDITABLE_SOURCE_INSTALL_REFUSED")
    expected_path = Path(dist.locate_file(_R39_RELATIVE))
    loaded_path = Path(r39.__file__)
    if (not expected_path.is_absolute()
            or not loaded_path.is_absolute()
            or loaded_path.is_symlink()
            or expected_path.resolve() != loaded_path.resolve()):
        raise R40Refused("R40_UNTRUSTED_INSTALLED_MODULE_LOCATION")
    actual = _regular_sha256(loaded_path, limit=256_000, owner_only=False)
    if actual != expected_module_sha256:
        raise R40Refused("R40_INSTALLED_MODULE_SHA256_MISMATCH")
    return {
        "distribution": _WHEEL_DISTRIBUTION,
        "version": _WHEEL_VERSION,
        "r39_module_sha256": actual,
        "module_identity_verified": True,
    }


def _workspace_snapshot(directory: Path) -> dict[str, str]:
    """Snapshot ONLY an owner-owned private, stopped six-ledger fixture."""
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or directory.is_symlink() or not directory.is_dir()
            or directory.stat().st_uid != os.geteuid()
            or stat.S_IMODE(directory.stat().st_mode) != 0o700):
        raise R40Refused("R40_PRIVATE_WORKSPACE_REQUIRED")
    pilot = directory / "pilot"
    if (pilot.is_symlink() or not pilot.is_dir()
            or pilot.stat().st_uid != os.geteuid()
            or stat.S_IMODE(pilot.stat().st_mode) != 0o700):
        raise R40Refused("R40_PRIVATE_PILOT_DIRECTORY_REQUIRED")
    seen = set()
    out = {}
    for relative in _FILES:
        file = directory / relative
        digest = _regular_sha256(
            file, limit=_MAX_STATE_FILE, owner_only=True,
        )
        info = file.stat()
        identity = (info.st_dev, info.st_ino)
        if identity in seen:
            raise R40Refused("R40_SHARED_EVIDENCE_FILE_IDENTITY")
        seen.add(identity)
        out[relative] = digest
    return out


def inspect(*, workspace: Path, expected_r39_module_sha256: str,
            dry_run_signals: bool, operator_ack: bool = False,
            all_writers_stopped: bool = False) -> dict:
    _gate(operator_ack=operator_ack, writers_stopped=all_writers_stopped)
    if type(dry_run_signals) is not bool:
        raise R40Refused("R40_EXACT_SYNTHETIC_MODE_REQUIRED")
    identity = _installed_identity(expected_r39_module_sha256)
    before = _workspace_snapshot(workspace)
    first = r39.inspect(
        workspace, dry_run_signals=dry_run_signals,
        operator_ack=True, all_writers_stopped=True,
    )
    second = r39.inspect(
        workspace, dry_run_signals=dry_run_signals,
        operator_ack=True, all_writers_stopped=True,
    )
    after = _workspace_snapshot(workspace)
    if (first != second or before != after
            or first.get("verdict")
                != "R39_READONLY_PAPER_REOPEN_PASS_RELEASE_DENIED"
            or first.get("status") != "DONE"
            or first.get("files_written") is not False
            or first.get("auto_retry_authorized") is not False
            or first.get("live_authorized") is not False
            or first.get("public_release_authorized") is not False
            or any(type(first.get(k)) is not str or not _SHA.fullmatch(first[k])
                   for k in ("report_sha256", "reliability_sha256",
                             "recovery_decision_sha256"))):
        raise R40Refused("R40_READONLY_REOPEN_OR_EVIDENCE_DRIFT")
    return {
        "verdict": "R40_INSTALLED_SYNTHETIC_PAPER_EVIDENCE_PASS_BROOKS_DEFERRED",
        **identity,
        "authority_report_sha256": first["report_sha256"],
        "ledger_sha256": dict(sorted(after.items())),
        "reliability_sha256": first["reliability_sha256"],
        "recovery_decision_sha256": first["recovery_decision_sha256"],
        "stage39_reopen_checks": 2,
        "files_written": False,
        "brooks_full_core_verdict": "DEFERRED_R27_FROZEN",
        "independent_brooks_verification": False,
        "real_market_data_used": False,
        "broker_order_sent": False,
        "telegram_sent": False,
        "auto_retry_authorized": False,
        "production_release_authorized": False,
        "live_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--expected-r39-module-sha256", required=True)
    parser.add_argument("--without-dry-signals", action="store_true")
    parser.add_argument("--ack-synthetic-offline", action="store_true")
    parser.add_argument("--ack-writers-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = inspect(
            workspace=args.workspace,
            expected_r39_module_sha256=args.expected_r39_module_sha256,
            dry_run_signals=not args.without_dry_signals,
            operator_ack=args.ack_synthetic_offline,
            all_writers_stopped=args.ack_writers_stopped,
        )
    except (R40Refused, r39.PaperAuthorityRefused, ValueError,
            OSError, RuntimeError, KeyError):
        print("R40_PAPER_ACCEPTANCE_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
