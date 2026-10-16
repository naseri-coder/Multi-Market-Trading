"""R34 manual local test runner for SHA-pinned OFFLINE checkout.

Runs ONLY explicitly requested read-only static parsing and selected test/lint
commands. It is not a broker, scheduler, CI workflow, production installer or
proof of authentic remote market / independent reviewer identity.

IMPORTANT: Python tests can execute arbitrary code and this script does not
create a network namespace, container or OS sandbox. Review the source on an
isolated, nonproduction device before invoking --run-tests/--run-ruff.
"""
from __future__ import annotations

import argparse
import ast
from importlib import metadata
import hashlib
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from naseri_markets.mmt_r34_offline_stack_acceptance_v1 import (
    R34AcceptanceRefused,
    R34OfflineEvidence,
    R34ToolFinding,
    _STATIC_SOURCES,
    _STAGE_UNIT_TARGETS,
    _wire,
    review_r34_local_stack_evidence,
)

TEST_TIMEOUT = 240
SUITE_TIMEOUT = 900
MAX_CAPTURE_BYTES = 4 * 1024 * 1024  # Never fill test-host storage with logs
_RUFF_TARGETS = (
    *_STATIC_SOURCES,
    *_STAGE_UNIT_TARGETS.values(),
    "tests/unit/test_mmt_r34_offline_stack_acceptance_v1.py",
)


def _gate(ack: bool) -> None:
    if (ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise R34AcceptanceRefused("R34_ACK_LOCAL_NONPRODUCTION_ONLY")


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, text=True, timeout=12,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0",
                 "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise R34AcceptanceRefused("R34_GIT_CHECK_FAILED") from exc
    if proc.returncode != 0 or len(proc.stdout) > 200_000:
        raise R34AcceptanceRefused("R34_GIT_CHECK_FAILED")
    return proc.stdout.strip()


def _head(root: Path, sha: str) -> None:
    if (type(root) is not Path or not root.is_absolute()
            or not root.is_dir() or root.is_symlink()
            or root.resolve(strict=True) != root):
        raise R34AcceptanceRefused("R34_EXACT_NON_SYMLINKED_ROOT_REQUIRED")
    if (_git(root, "rev-parse", "--show-toplevel") != str(root)
            or _git(root, "rev-parse", "HEAD") != sha
            or _git(root, "status", "--porcelain=v1", "--untracked-files=all")):
        raise R34AcceptanceRefused("R34_CHECKOUT_NOT_PINNED_OR_DIRTY")


def _bytes(root: Path, rel: str, *, limit: int = 1_048_576) -> bytes:
    file = root / rel
    if (file.is_symlink() or not file.is_file()
            or any(item.is_symlink() for item in file.parents
                   if item != root and item.is_relative_to(root))
            or not file.resolve(strict=True).is_relative_to(root)):
        raise R34AcceptanceRefused("R34_SOURCE_PATH_INVALID")
    try:
        fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or not 1 <= st.st_size <= limit):
                raise R34AcceptanceRefused("R34_REGULAR_BOUNDED_SOURCE_REQUIRED")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                value = stream.read(limit + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise R34AcceptanceRefused("R34_SOURCE_READ_FAILED") from exc
    if len(value) != st.st_size:
        raise R34AcceptanceRefused("R34_CHANGED_SOURCE_DURING_READ")
    # Git status can conceal assume-unchanged or skip-worktree modifications:
    # verify the EXACT bytes parsed/executed against the HEAD blob identity.
    obj = b"blob " + str(len(value)).encode("ascii") + b"\x00" + value
    if hashlib.sha1(obj).hexdigest() != _git(root, "rev-parse", "HEAD:" + rel):
        raise R34AcceptanceRefused("R34_PINNED_SOURCE_BLOB_MISMATCH")
    return value


def _syntax(root: Path) -> R34ToolFinding:
    buffer = bytearray()
    try:
        for rel in (
            *_STATIC_SOURCES, *tuple(_STAGE_UNIT_TARGETS.values()),
            "tests/unit/test_mmt_r34_offline_stack_acceptance_v1.py",
        ):
            raw = _bytes(root, rel)
            ast.parse(raw, filename=rel)
            buffer += hashlib.sha256(raw).digest()
    except (ValueError, SyntaxError, UnicodeError, R34AcceptanceRefused):
        return R34ToolFinding(
            "STATIC_SYNTAX", "FAIL", 1,
            hashlib.sha256(bytes(buffer)).hexdigest(),
        )
    return R34ToolFinding(
        "STATIC_SYNTAX", "PASS", 0,
        hashlib.sha256(bytes(buffer)).hexdigest(),
    )


def _project_python_preflight(run_pytest: bool, version: tuple[int, int] | None = None) -> None:
    # pyproject.toml explicitly requires Python >=3.12,<3.13.
    current = version if version is not None else sys.version_info[:2]
    if run_pytest and current != (3, 12):
        raise R34AcceptanceRefused("R34_PROJECT_PYTHON_312_REQUIRED")


def _project_toolchain_preflight(
    *, pytest_needed: bool, ruff_needed: bool,
) -> None:
    """Check installed distributions WITHOUT importing test/plugin code."""
    required = {}
    if pytest_needed:
        required.update({"pytest": "9.1.1", "pytest-asyncio": "1.4.0"})
    if ruff_needed:
        required["ruff"] = "0.16.9"
    for package, expected_version in required.items():
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError as exc:
            raise R34AcceptanceRefused("R34_REQUIRED_TEST_TOOL_UNAVAILABLE") from exc
        if actual != expected_version:
            raise R34AcceptanceRefused("R34_PINNED_TEST_TOOL_VERSION_MISMATCH")


def _child_environment(root: Path | None = None) -> dict[str, str]:
    # Reduce ambient accidental credential exposure; NOT a system sandbox.
    sensitive = (
        "PASSWORD", "TOKEN", "SECRET", "API_KEY", "PRIVATE_KEY",
        "DATABASE_URL", "ACCESS_KEY", "AUTHORIZATION",
    )
    env = {
        k: v for k, v in os.environ.items()
        if not any(term in k.upper() for term in sensitive)
        and not k.upper().startswith(("TELEGRAM_", "BROKER_", "EXCHANGE_"))
    }
    # Never inherit arbitrary PYTHONPATH/PYTHONHOME entries from the operator.
    # The repository intentionally keeps the historical app in production_source.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    for key in (
        "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DEBUG",
        "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONINSPECT",
        "PYTHONWARNINGS", "PYTHONBREAKPOINT",
    ):
        env.pop(key, None)
    if root is not None:
        env["PYTHONPATH"] = os.pathsep.join(
            (str(root / "production_source"), str(root))
        )
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["MMT_NONPRODUCTION"] = "1"
    env.pop("MMT_PRODUCTION", None)
    env["PIP_NO_INDEX"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["HTTP_PROXY"] = "http://127.0.0.1:9"
    env["HTTPS_PROXY"] = "http://127.0.0.1:9"
    env["ALL_PROXY"] = "socks5://127.0.0.1:9"
    env["NO_PROXY"] = ""
    return env


def _run(root: Path, name: str, args: tuple[str, ...], timeout: int) -> R34ToolFinding:
    """No shell expansion; hash output rather than disclose tokens/logs."""
    if type(args) is not tuple or not args or timeout <= 0:
        raise R34AcceptanceRefused("R34_FIXED_TEST_COMMAND_REQUIRED")
    env = _child_environment(root)
    with tempfile.TemporaryFile(mode="w+b") as stream:
        try:
            # A bounded subprocess.run timeout kills only the immediate
            # Python process. Tests may have spawned subprocess descendants.
            # Isolate this invocation in its own POSIX session, then terminate
            # the process group on a deadline (Termux/Linux).
            p = subprocess.Popen(
                args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, close_fds=True,
                start_new_session=True,
            )
            deadline = time.monotonic() + timeout
            while True:
                # Check on disk while the subprocess is still alive. This
                # protects the disposable host from unlimited test output.
                if os.fstat(stream.fileno()).st_size > MAX_CAPTURE_BYTES:
                    reason = "OUTPUT_LIMIT"
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "TIMEOUT"
                    break
                try:
                    code = p.wait(timeout=min(0.2, remaining))
                    reason = ""
                    break
                except subprocess.TimeoutExpired:
                    continue
            if reason:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait()
                return R34ToolFinding(name, reason, None, None)
            # Also check the final buffered output before returning PASS.
            if os.fstat(stream.fileno()).st_size > MAX_CAPTURE_BYTES:
                return R34ToolFinding(name, "OUTPUT_LIMIT", None, None)
            stream.seek(0)
            digester = hashlib.sha256()
            while chunk := stream.read(65_536):
                digester.update(chunk)
            return R34ToolFinding(
                name, "PASS" if code == 0 else "FAIL", code,
                digester.hexdigest(),
            )
        except OSError:
            return R34ToolFinding(name, "UNAVAILABLE", None, None)


def _private_new_report(path: Path, data: bytes) -> None:
    if (type(path) is not Path or not path.is_absolute()
            or path.is_symlink() or not path.parent.is_dir()
            or path.parent.is_symlink()
            or path.parent.resolve(strict=True) != path.parent):
        raise R34AcceptanceRefused("R34_PRIVATE_NEW_REPORT_PATH_REQUIRED")
    parent = path.parent.stat()
    if (parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o077):
        raise R34AcceptanceRefused("R34_PRIVATE_0700_PARENT_REQUIRED")
    try:
        fd = os.open(
            path, os.O_CREAT | os.O_WRONLY | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:
        raise R34AcceptanceRefused("R34_EXCLUSIVE_REPORT_WRITE_REFUSED") from exc


def collect_r34_offline_evidence(
    *, root: Path, expected_head: str,
    run_stage_tests: bool = False, run_ruff: bool = False,
    run_full_suite: bool = False, operator_ack: bool = False,
) -> R34OfflineEvidence:
    """Optional tests execute untrusted repository Python: require explicit ack."""
    _gate(operator_ack)
    if any(type(v) is not bool for v in (
        run_stage_tests, run_ruff, run_full_suite,
    )):
        raise R34AcceptanceRefused("R34_BOOLEAN_TEST_SELECTION_REQUIRED")
    _head(root, expected_head)
    pre_syntax = _syntax(root)
    if pre_syntax.status != "PASS":
        raise R34AcceptanceRefused("R34_SOURCE_STATIC_PREFLIGHT_FAILED")
    _project_python_preflight(run_stage_tests or run_full_suite)
    _project_toolchain_preflight(
        pytest_needed=run_stage_tests or run_full_suite,
        ruff_needed=run_ruff,
    )
    results = []
    for stage, test_path in _STAGE_UNIT_TARGETS.items():
        results.append(
            _run(root, stage, (
                sys.executable, "-m", "pytest", "-q",
                "-p", "no:cacheprovider", "-p", "pytest_asyncio.plugin",
                test_path,
            ), TEST_TIMEOUT)
            if run_stage_tests else R34ToolFinding(stage, "NOT_RUN", None, None)
        )
    results.append(
        _run(root, "RUFF_R28_TO_R34", (
            sys.executable, "-m", "ruff", "check", *_RUFF_TARGETS,
        ), TEST_TIMEOUT)
        if run_ruff else R34ToolFinding("RUFF_R28_TO_R34", "NOT_RUN", None, None)
    )
    results.append(
        _run(root, "FULL_UNIT_SUITE", (
            sys.executable, "-m", "pytest", "-q",
            "-p", "no:cacheprovider", "-p", "pytest_asyncio.plugin",
            "tests/unit",
        ), SUITE_TIMEOUT)
        if run_full_suite else R34ToolFinding("FULL_UNIT_SUITE", "NOT_RUN", None, None)
    )
    post_syntax = _syntax(root)
    if (post_syntax.status != "PASS"
            or post_syntax.output_sha256 != pre_syntax.output_sha256):
        raise R34AcceptanceRefused("R34_SOURCE_CHANGED_DURING_TEST_SESSION")
    results.append(post_syntax)
    clean_after = not _git(
        root, "status", "--porcelain=v1", "--untracked-files=all",
    )
    return R34OfflineEvidence(
        pinned_checkout_head=expected_head,
        observed_checkout_head=_git(root, "rev-parse", "HEAD"),
        checkout_clean_pre_and_post=clean_after,
        local_test_runner_executed=(run_stage_tests or run_ruff or run_full_suite),
        results=tuple(results),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="R34 OFFLINE source/test evidence (NEVER authorizes release)"
    )
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--expected-head", required=True)
    p.add_argument("--output-private-json", type=Path)
    p.add_argument("--run-stage-tests", action="store_true")
    p.add_argument("--run-ruff", action="store_true")
    p.add_argument("--run-full-unit-suite", action="store_true")
    p.add_argument("--ack-execute-local-repository-tests", action="store_true")
    args = p.parse_args(argv)
    try:
        evidence = collect_r34_offline_evidence(
            root=args.source_root.absolute(),
            expected_head=args.expected_head,
            run_stage_tests=args.run_stage_tests,
            run_ruff=args.run_ruff,
            run_full_suite=args.run_full_unit_suite,
            operator_ack=args.ack_execute_local_repository_tests,
        )
        result = review_r34_local_stack_evidence(
            evidence, operator_ack=True,
        )
        if args.output_private_json is not None:
            report_path = args.output_private_json.absolute()
            if report_path.is_relative_to(args.source_root.absolute()):
                raise R34AcceptanceRefused("R34_REPORT_MUST_BE_OUTSIDE_CHECKOUT")
            _private_new_report(report_path, _wire(result) + b"\n")
    except (R34AcceptanceRefused, ValueError, OSError):
        print(_wire({
            "decision": "REVIEW_REFUSED_NO_RELEASE",
            "server_deployment_authorized": False,
            "live_orders_authorized": False,
        }).decode("ascii"))
        return 2
    print(_wire(result).decode("ascii"))
    return 0 if result["blocker_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
