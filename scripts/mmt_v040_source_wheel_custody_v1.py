"""Source-to-signed-stable-wheel custody auditor; read-only and fail-closed.

Independently pin a clean Git checkout and external signer trust before
comparing every reviewed public module byte against the signed wheel.
Never builds, installs, imports package modules, starts workers or trades.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path

from scripts import mmt_v040_signed_artifact_preflight_v1 as stable

COMMIT = re.compile(r"[0-9a-f]{40}\Z")
MAX_SOURCE_MODULES = 500
MAX_MODULE_SIZE = 1_000_000


class SourceCustodyRefused(ValueError):
    """Fail-closed error, without leaking private source or file paths."""


def _git(root: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, check=False, timeout=20,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceCustodyRefused("V040_GIT_READ_FAILED") from exc
    if proc.returncode != 0 or len(proc.stdout) > 1_000_000 or proc.stderr:
        raise SourceCustodyRefused("V040_GIT_READ_FAILED")
    return proc.stdout


def _source_inventory(
    repository: Path, expected_source_commit: str,
) -> tuple[dict[str, bytes], dict]:
    if (not isinstance(repository, Path) or not repository.is_absolute()
            or repository.is_symlink() or not repository.is_dir()
            or type(expected_source_commit) is not str
            or not COMMIT.fullmatch(expected_source_commit)):
        raise SourceCustodyRefused("V040_SOURCE_AND_EXTERNAL_PIN_REQUIRED")
    if (_git(repository, "rev-parse", "--verify", "HEAD").strip().decode("ascii")
            != expected_source_commit):
        raise SourceCustodyRefused("V040_SOURCE_COMMIT_PIN_MISMATCH")
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise SourceCustodyRefused("V040_SOURCE_CHECKOUT_NOT_CLEAN")
    project = repository / "platform_release" / "pyproject.toml"
    readme = repository / "platform_release" / "README.md"
    package = repository / "naseri_markets"
    if (not package.is_dir() or package.is_symlink()
            or any(not file.is_file() or file.is_symlink() for file in (project, readme))):
        raise SourceCustodyRefused("V040_PUBLIC_SOURCE_MISSING_OR_SYMLINK")
    try:
        config = tomllib.loads(project.read_text(encoding="utf-8"))
        declaration = config["project"]
        if (declaration["name"] != stable.DIST_NAME
                or declaration["version"] != stable.VERSION
                or declaration["requires-python"] != ">=3.12,<3.13"
                or declaration["dependencies"] != []
                or declaration["scripts"] != stable._ALLOWED_COMMANDS
                or set(declaration["optional-dependencies"]) != set(stable._ALLOWED_REQUIREMENTS)
                or any(set(d.lower() for d in declaration["optional-dependencies"][extra]) != pins
                       or len(declaration["optional-dependencies"][extra]) != len(pins)
                       for extra, pins in stable._ALLOWED_REQUIREMENTS.items())
                or config["build-system"]["requires"] != ["setuptools==80.9.0", "wheel==0.45.1"]
                or config["build-system"]["build-backend"] != "setuptools.build_meta"):
            raise SourceCustodyRefused("V040_SOURCE_METADATA_DRIFT")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        if isinstance(exc, SourceCustodyRefused):
            raise
        raise SourceCustodyRefused("V040_SOURCE_METADATA_DRIFT") from exc
    try:
        tracked_bytes = _git(repository, "ls-files", "-z", "--", "naseri_markets")
        paths = [p.decode("utf-8") for p in tracked_bytes.split(b"\x00") if p]
        if (not paths or len(paths) > MAX_SOURCE_MODULES
                or len(paths) != len(set(paths))):
            raise SourceCustodyRefused("V040_PUBLIC_SOURCE_SET_INVALID")
        modules: dict[str, bytes] = {}
        for name in paths:
            item = Path(name)
            if (len(item.parts) != 2 or item.parts[0] != "naseri_markets"
                    or item.suffix != ".py" or name.startswith("/")
                    or "\\" in name):
                raise SourceCustodyRefused("V040_UNREVIEWED_SOURCE_MEMBER")
            source = repository / item
            if (not source.is_file() or source.is_symlink()
                    or not 0 <= source.stat().st_size <= MAX_MODULE_SIZE):
                raise SourceCustodyRefused("V040_PUBLIC_SOURCE_UNSAFE")
            modules[name] = source.read_bytes()
        if "naseri_markets/platform_cli.py" not in modules or len(modules) < 2:
            raise SourceCustodyRefused("V040_REQUIRED_PUBLIC_MODULE_MISSING")
        if set(modules) != {"naseri_markets/" + p.name for p in package.glob("*.py")}:
            raise SourceCustodyRefused("V040_UNTRACKED_OR_MISSING_SOURCE")
        return modules, declaration
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, SourceCustodyRefused):
            raise
        raise SourceCustodyRefused("V040_PUBLIC_SOURCE_READ_FAILED") from exc


def audit(*, repository: Path, manifest: Path, signature: Path, wheel: Path,
          trusted_public_key: Path, trusted_public_key_spki_sha256: str,
          policy: Path, expected_policy_sha256: str,
          expected_manifest_sha256: str, expected_source_commit: str) -> dict:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise SourceCustodyRefused("V040_NONPRODUCTION_REQUIRED")
    signed = stable.verify(
        manifest=manifest, signature=signature, wheel=wheel,
        trusted_public_key=trusted_public_key,
        trusted_public_key_spki_sha256=trusted_public_key_spki_sha256,
        policy=policy, expected_policy_sha256=expected_policy_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_source_commit=expected_source_commit,
    )
    modules, _ = _source_inventory(repository, expected_source_commit)
    raw = stable._read(wheel, stable.MAX_WHEEL)
    if hashlib.sha256(raw).hexdigest() != signed["wheel_sha256"]:
        raise SourceCustodyRefused("V040_SIGNED_WHEEL_CHANGED")
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
            wheel_modules = {name for name in archive.namelist()
                             if name.startswith("naseri_markets/")}
            if set(modules) != wheel_modules:
                raise SourceCustodyRefused("V040_SOURCE_WHEEL_MODULE_SET_MISMATCH")
            for path, data in modules.items():
                if archive.read(path) != data:
                    raise SourceCustodyRefused("V040_SOURCE_WHEEL_MODULE_BYTES_MISMATCH")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        if isinstance(exc, SourceCustodyRefused):
            raise
        raise SourceCustodyRefused("V040_SOURCE_WHEEL_COMPARISON_FAILED") from exc
    return {
        "verdict": "V040_SIGNED_WHEEL_CLEAN_SOURCE_MATCH_PASS_RELEASE_DENIED",
        "source_commit": expected_source_commit,
        "wheel_sha256": signed["wheel_sha256"],
        "public_modules_byte_verified": len(modules),
        "signer_spki_sha256": signed["signer_spki_sha256"],
        "wheel_record_verified": signed["record_verified"],
        "writes_performed": False,
        "install_authorized": False,
        "public_release_authorized": False,
        "live_trading_authorized": False,
        "telegram_publication_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    for name in ("manifest", "signature", "wheel", "trusted-public-key", "policy"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("trusted-public-key-spki-sha256", "expected-policy-sha256",
                 "expected-manifest-sha256", "expected-source-commit"):
        parser.add_argument("--" + name, required=True)
    opts = vars(parser.parse_args(argv))
    opts = {key.replace("-", "_"): val for key, val in opts.items()}
    try:
        result = audit(**opts)
    except (SourceCustodyRefused, stable.StableArtifactRefused, OSError) as exc:
        code = (str(exc) if isinstance(exc, (SourceCustodyRefused, stable.StableArtifactRefused))
                else "V040_SOURCE_AUDIT_IO_REFUSED")
        print(json.dumps({"verdict": "V040_SOURCE_CUSTODY_REFUSED", "reason": code,
                          "install_authorized": False,
                          "public_release_authorized": False,
                          "live_trading_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
