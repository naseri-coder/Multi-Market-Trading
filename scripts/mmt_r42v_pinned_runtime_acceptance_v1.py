"""R42-V bounded offline Python3.12/Ruff acceptance, never a trading grant.

This tool is intentionally NOT a provider, strategy, broker, release or deploy tool.
Only a reviewed, clean, nonroot nonproduction checkout may execute the two
pinned R42 auditor/test files. A source-only preflight always exits nonzero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

PARENT_COMMIT = "a3686c13699e52a026c06c4e97fdf5ff3304d8d3"
PINS = {
    "scripts/mmt_r42_offline_market_account_evidence_v1.py": (
        "070c56bd8774372c40bb61f8316c92988e8c9b35",
        "d4d1aebca64bf81977f5ee5f60cfc1d3833fa2008551378ec8e86916ffdd953d",
    ),
    "tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py": (
        "eab305facdc6ce9406f3a488a602f2b5b62a1b19",
        "89eda2c803415e129deaf705cbf5ca60c2053b287b801c0735783568165d420f",
    ),
    "tests/unit/test_mmt_r42v_pinned_runtime_acceptance_v1.py": (
        "ae7ec4f16caf89e9c2dcfc564f9faa9b75874a6a",
        "dffef2f52bb52794e04d73eedc27cc38f2b7b041531b6ebeb991f589d7e9e5e6",
    ),
}
EXPECTED_TESTS = 59


class AcceptanceBlocked(RuntimeError):
    """Fixed, non-sensitive denial code."""


def _checked_source(root: Path) -> dict:
    result = {}
    for name, (git_sha, sha256) in PINS.items():
        file = root / name
        if any(part.is_symlink() for part in (file, *file.parents) if part != root.parent):
            raise AcceptanceBlocked("R42V_SYMLINK_SOURCE_DENIED")
        try:
            st = file.stat()
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > 100_000:
                raise AcceptanceBlocked("R42V_UNSAFE_SOURCE_FILE")
            raw = file.read_bytes()
        except OSError as exc:
            raise AcceptanceBlocked("R42V_SOURCE_UNAVAILABLE") from exc
        observed = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if observed != git_sha or hashlib.sha256(raw).hexdigest() != sha256:
            raise AcceptanceBlocked("R42V_PIN_MISMATCH")
        result[name] = {"git_blob_sha1": observed, "sha256": sha256, "bytes": len(raw)}
    return result


def _command(cmd: list[str], root: Path, env: dict, limit: int = 120) -> str:
    try:
        done = subprocess.run(cmd, cwd=root, env=env, check=False, capture_output=True,
                              text=True, timeout=limit)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceBlocked("R42V_TOOL_UNAVAILABLE_OR_TIMEOUT") from exc
    if done.returncode:
        raise AcceptanceBlocked("R42V_COMMAND_FAILED")
    return done.stdout


def evaluate(*, checkout: Path, ack: bool, source_check_only: bool = False) -> tuple[dict, int]:
    if not ack or os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise AcceptanceBlocked("R42V_NONPRODUCTION_ACK_REQUIRED")
    if not checkout.is_absolute() or checkout.is_symlink() or not checkout.is_dir():
        raise AcceptanceBlocked("R42V_EXPLICIT_NONLINKED_CHECKOUT_REQUIRED")
    if os.geteuid() == 0:
        raise AcceptanceBlocked("R42V_NONROOT_REQUIRED")
    pins = _checked_source(checkout)
    if source_check_only:
        return {"verdict": "R42V_SOURCE_ONLY_NOT_ACCEPTED", "file_pins": pins,
                "tests_executed": False, "python312_accepted": False,
                "live_authorized": False}, 3
    if sys.version_info[:2] != (3, 12):
        raise AcceptanceBlocked("R42V_REAL_PYTHON312_REQUIRED")
    if shutil.which("ruff") is None:
        raise AcceptanceBlocked("R42V_RUFF_REQUIRED")
    if shutil.which("git") is None:
        raise AcceptanceBlocked("R42V_GIT_REQUIRED")
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = str(checkout)
    head = _command(["git", "rev-parse", "HEAD"], checkout, env).strip()
    if not re.fullmatch("[a-f0-9]{40}", head):
        raise AcceptanceBlocked("R42V_UNPINNED_GIT_HEAD")
    _command(["git", "merge-base", "--is-ancestor", PARENT_COMMIT, head], checkout, env)
    if _command(["git", "status", "--porcelain"], checkout, env).strip():
        raise AcceptanceBlocked("R42V_DIRTY_CHECKOUT")
    files = list(PINS)
    ruff_version = _command(["ruff", "--version"], checkout, env).strip()
    _command(["ruff", "check", "--isolated", "--no-cache", "--select", "E4,E7,E9,F", *files,
              "scripts/mmt_r42v_pinned_runtime_acceptance_v1.py"],
             checkout, env)
    output = _command([sys.executable, "-X", "dev", "-W", "error", "-m", "pytest",
                       "-q", "-c", "/dev/null", "-p", "no:cacheprovider", "--noconftest",
                       *files[1:]], checkout, env)
    if not re.search(rf"(?m)^\s*{EXPECTED_TESTS} passed in ", output):
        raise AcceptanceBlocked("R42V_UNEXPECTED_TEST_COUNT")
    return {"verdict": "R42V_BOUNDED_PY312_TEST_LINT_PASS_NOT_RELEASE",
            "checkout_commit": head, "file_pins": pins, "python_version": sys.version.split()[0],
            "ruff_version": ruff_version, "pytest_cases_passed": EXPECTED_TESTS,
            "live_authorized": False, "public_signal_authorized": False,
            "real_provider_verified": False, "installed_paper_accepted": False}, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--ack-offline-only", action="store_true")
    parser.add_argument("--source-check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        outcome, status = evaluate(checkout=args.checkout, ack=args.ack_offline_only,
                                   source_check_only=args.source_check_only)
    except AcceptanceBlocked as exc:
        print(json.dumps({"verdict": "R42V_ACCEPTANCE_BLOCKED", "reason": str(exc),
                          "live_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
