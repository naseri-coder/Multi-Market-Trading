"""R35 public-only pinned Wheel check and opt-in isolated offline install.

This never installs the legacy runtime, Telegram extra, services or exchange
connections. Installing executes reviewed Python package code: use only a
throwaway nonproduction host. Check-only does not write to disk.
"""
from __future__ import annotations

import argparse
import configparser
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import venv
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath

VERSION = "0.4.0rc1"
NAME = "multi-market-trading"
FILE_NAME = "multi_market_trading-0.4.0rc1-py3-none-any.whl"
DIST = "multi_market_trading-0.4.0rc1.dist-info/"
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_WHEEL = 12_000_000
MAX_UNPACKED = 36_000_000
MAX_FILES = 750
INSTALL_TIMEOUT = 150
SOURCE_ROOT = Path(__file__).resolve().parents[1]


class R35Refused(ValueError):
    """Constant, non-secret reason codes; preserve fail-closed behavior."""


def _gate(*, install: bool, ack: bool) -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or sys.version_info[:2] != (3, 12)):
        raise R35Refused("R35_NONPRODUCTION_PY312_REQUIRED")
    if install and not ack:
        raise R35Refused("R35_EXPLICIT_OFFLINE_INSTALL_ACK_REQUIRED")
    if install and os.geteuid() == 0:
        raise R35Refused("R35_NONROOT_INSTALL_REQUIRED")


def _new_destination(path: Path) -> None:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or path.exists()
            or path.name in ("", ".", "..")
            or path.parent.is_symlink() or not path.parent.is_dir()
            or path.parent.resolve(strict=True) != path.parent
            or path == SOURCE_ROOT or SOURCE_ROOT in path.parents):
        raise R35Refused("R35_NEW_ABSOLUTE_OUTSIDE_CHECKOUT_REQUIRED")
    parent = path.parent.stat()
    if (parent.st_uid != os.geteuid() or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode) & 0o077):
        raise R35Refused("R35_PRIVATE_OWNED_PARENT_REQUIRED")


def _wheel_bytes(wheel: Path, pin: str) -> tuple[bytes, str, int]:
    if (not isinstance(wheel, Path) or not wheel.is_absolute()
            or wheel.name != FILE_NAME or wheel.is_symlink()
            or wheel.parent.is_symlink()
            or (wheel.is_file() and wheel.resolve(strict=True) != wheel)
            or type(pin) is not str or SHA.fullmatch(pin) is None):
        raise R35Refused("R35_ABSOLUTE_PINNED_WHEEL_REQUIRED")
    try:
        fd = os.open(wheel, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise R35Refused("R35_WHEEL_UNREADABLE") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 128 <= info.st_size <= MAX_WHEEL):
            raise R35Refused("R35_BOUNDED_REGULAR_WHEEL_REQUIRED")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_WHEEL + 1)
        if len(raw) != info.st_size:
            raise R35Refused("R35_WHEEL_SIZE_CHANGED")
    finally:
        os.close(fd)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pin:
        raise R35Refused("R35_WHEEL_SHA256_MISMATCH")
    return raw, digest, len(raw)


def _inspect_wheel(raw: bytes) -> int:
    """Bound ZIP metadata, reject executable wheel extras and private source."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            files = bundle.infolist()
            names = [item.filename for item in files]
            if len(files) > MAX_FILES or len(set(names)) != len(names):
                raise R35Refused("R35_WHEEL_MEMBER_SET_INVALID")
            if sum(item.file_size for item in files) > MAX_UNPACKED:
                raise R35Refused("R35_WHEEL_EXTRACT_SIZE_LIMIT")
            for item in files:
                name = PurePosixPath(item.filename)
                mode = item.external_attr >> 16
                if (not item.filename or name.is_absolute()
                        or item.filename.startswith("/") or "\\" in item.filename
                        or not name.parts
                        or any(p in (".", "..") for p in item.filename.split("/"))
                        or "//" in item.filename
                        or item.flag_bits & 0x1
                        or (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                        or name.parts[0] not in ("naseri_markets", DIST.rstrip("/"))
                        or name.suffix in (".pth", ".so", ".dll", ".exe")
                        or "private_nyfr_core" in item.filename
                        or "r0_engine" in item.filename
                        or ".env" in name.parts):
                    raise R35Refused("R35_UNSAFE_WHEEL_MEMBER")
            if "naseri_markets/platform_cli.py" not in names:
                raise R35Refused("R35_PUBLIC_PREVIEW_MODULE_MISSING")
            metadata_name = DIST + "METADATA"
            entry_name = DIST + "entry_points.txt"
            if metadata_name not in names or entry_name not in names:
                raise R35Refused("R35_WHEEL_METADATA_MISSING")
            metadata = Parser().parsestr(bundle.read(metadata_name).decode("utf-8"))
            requirements = metadata.get_all("Requires-Dist", [])
            if (metadata.get("Name", "").lower() != NAME
                    or metadata.get("Version") != VERSION
                    or any('extra == "telegram-admin"' not in x
                           and "extra == 'telegram-admin'" not in x
                           for x in requirements)):
                raise R35Refused("R35_UNEXPECTED_DISTRIBUTION_OR_DEPENDENCY")
            cp = configparser.ConfigParser(interpolation=None)
            cp.read_string(bundle.read(entry_name).decode("utf-8"))
            if (not cp.has_section("console_scripts")
                    or cp.get("console_scripts", "naseri-markets", fallback="")
                    != "naseri_markets.platform_cli:main"
                    or cp.get("console_scripts", "naseri-paper-demo", fallback="")
                    != "naseri_markets.paper_demo_cli_v1:main"):
                raise R35Refused("R35_UNEXPECTED_CLI_ENTRYPOINT")
            return len(files)
    except (zipfile.BadZipFile, UnicodeError, configparser.Error, KeyError) as exc:
        raise R35Refused("R35_WHEEL_ZIP_OR_METADATA_INVALID") from exc


def _run(argv: list[str], env: dict[str, str], timeout: int = 60) -> str:
    try:
        proc = subprocess.run(argv, env=env, capture_output=True,
                              text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise R35Refused("R35_ISOLATED_PROCESS_FAILED") from exc
    if proc.returncode or len(proc.stdout) > 8192 or len(proc.stderr) > 8192:
        raise R35Refused("R35_ISOLATED_PROCESS_REJECTED")
    return proc.stdout


def check(*, wheel: Path, sha256: str, destination: Path) -> dict:
    """Read-only, even when called from a disposable root PRoot test host."""
    _gate(install=False, ack=False)
    _new_destination(destination)
    raw, digest, size = _wheel_bytes(wheel, sha256)
    count = _inspect_wheel(raw)
    return {
        "verdict": "R35_OFFLINE_WHEEL_PREFLIGHT_PASS",
        "version": VERSION, "wheel_sha256": digest, "wheel_bytes": size,
        "wheel_members": count, "writes_performed": False,
        "telegram_enabled": False, "broker_orders_enabled": False,
        "live_authorized": False, "production_install_allowed": False,
    }


def install(*, wheel: Path, sha256: str, destination: Path, ack: bool) -> dict:
    _gate(install=True, ack=ack)
    preflight = check(wheel=wheel, sha256=sha256, destination=destination)
    # No overwrite; failures leave the new directory for operator inspection.
    try:
        os.mkdir(destination, mode=0o700)
    except OSError as exc:
        raise R35Refused("R35_EXCLUSIVE_DESTINATION_CREATE_FAILED") from exc
    venv_dir = destination / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=False,
                    clear=False, symlinks=False).create(venv_dir)
    local_wheel = destination / FILE_NAME
    raw, _, _ = _wheel_bytes(wheel, sha256)
    fd = os.open(local_wheel, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    python = str(venv_dir / "bin/python")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(destination),
           "MMT_NONPRODUCTION": "1", "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "PIP_NO_INDEX": "1",
           "PIP_CONFIG_FILE": os.devnull, "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    _run([python, "-m", "pip", "install", "--no-index", "--no-deps",
          "--no-cache-dir", str(local_wheel)], env, timeout=INSTALL_TIMEOUT)
    _run([python, "-m", "pip", "check"], env)
    response = json.loads(_run([str(venv_dir / "bin/naseri-markets"), "--check"], env))
    if (response.get("distribution") != NAME or response.get("version") != VERSION
            or response.get("mode") != "OFFLINE_PREVIEW"
            or any(response.get(n) is not False for n in
                   ("network_enabled", "orders_enabled", "telegram_enabled",
                    "legacy_database_attached"))):
        raise R35Refused("R35_INSTALLED_CLI_UNSAFE")
    # No PAPER replay, Telegram admin, services or connected market data.
    answer = dict(preflight)
    answer.update(verdict="R35_INSTALLED_OFFLINE_PREVIEW_PASS_RELEASE_DENIED",
                  writes_performed=True, installation_isolated=True)
    manifest = destination / "offline-install-report.json"
    fd = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(answer, stream, sort_keys=True)
        stream.write("\n")
    return answer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--install", action="store_true")
    parser.add_argument("--ack-offline-preview-install", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.install:
            result = install(wheel=args.wheel, sha256=args.sha256,
                             destination=args.destination,
                             ack=args.ack_offline_preview_install)
        else:
            result = check(wheel=args.wheel, sha256=args.sha256,
                           destination=args.destination)
    except (R35Refused, OSError, ValueError, RuntimeError) as exc:
        code = str(exc) if isinstance(exc, R35Refused) else "R35_OFFLINE_PREVIEW_INSTALL_REFUSED"
        print(json.dumps({"verdict": "R35_INSTALL_REFUSED", "reason": code,
                          "production_install_allowed": False,
                          "live_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
