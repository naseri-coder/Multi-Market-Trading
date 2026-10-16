"""R41 read-only Stage4 OCI argument and source-identity preflight.

Static parser only: DOES NOT run Docker, gVisor, malicious code, plugins,
pip, workers, network or external system commands. NEVER authorizes release.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

_MAX_SOURCE = 131_072
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED = frozenset({
    "run", "--rm", "--pull=never", "--runtime=runsc",
    "--network=none", "--ipc=none", "--read-only", "--cap-drop=ALL",
    "--security-opt=no-new-privileges", "--pids-limit=32",
    "--memory=128m", "--memory-swap=128m", "--cpus=0.5",
    "--ulimit=nofile=64:64", "--user=65534:65534",
    "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
    "--workdir=/tmp", "--entrypoint=python",
    "--env=PYTHONDONTWRITEBYTECODE=1", "-I", "-S", "-c",
})
_FORBIDDEN = (
    "--privileged", "--network=host", "--network=bridge",
    "--pid=host", "--ipc=host", "--user=0", "--user=root",
    "--cap-add", "--mount", "--volume", "-v", "-p", "--publish",
    "--device", "--security-opt=seccomp=unconfined",
)
_REQUIRED_FUNCTIONS = frozenset({
    "_assert_rootless_socket", "_ensure_rootless_daemon",
    "build_run_command", "_invoke",
})


class R41Refused(ValueError):
    """Constant refusal codes; an audit finding cannot grant privileges."""


def _read_source(path: Path) -> bytes:
    if not isinstance(path, Path) or not path.is_absolute():
        raise R41Refused("R41_ABSOLUTE_SOURCE_REQUIRED")
    if path.is_symlink() or path.parent.is_symlink():
        raise R41Refused("R41_SYMLINK_SOURCE_REFUSED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise R41Refused("R41_SOURCE_UNREADABLE") from exc
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or not 1 <= st.st_size <= _MAX_SOURCE):
            raise R41Refused("R41_BOUNDED_REGULAR_SOURCE_REQUIRED")
        raw = bytearray()
        while len(raw) < st.st_size:
            part = os.read(fd, min(65536, st.st_size - len(raw)))
            if not part:
                raise R41Refused("R41_SOURCE_TRUNCATED")
            raw.extend(part)
        st2 = os.fstat(fd)
        if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (
            st2.st_dev, st2.st_ino, st2.st_size, st2.st_mtime_ns
        ):
            raise R41Refused("R41_SOURCE_CHANGED_DURING_READ")
        return bytes(raw)
    finally:
        os.close(fd)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    found = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(found) != 1:
        raise R41Refused("R41_REQUIRED_FUNCTION_MISSING")
    return found[0]


def _command_literals(func: ast.FunctionDef) -> tuple[set[str], set[str]]:
    returned = [node.value for node in ast.walk(func)
                if isinstance(node, ast.Return)]
    if len(returned) != 1 or not isinstance(returned[0], ast.Tuple):
        raise R41Refused("R41_STATIC_COMMAND_TUPLE_REQUIRED")
    tokens: set[str] = set()
    references: set[str] = set()
    for item in returned[0].elts:
        if isinstance(item, ast.Constant) and type(item.value) is str:
            tokens.add(item.value)
        elif isinstance(item, ast.JoinedStr):
            # f"--name={name}" is the only permitted dynamically filled switch.
            rendered = "".join(
                chunk.value if isinstance(chunk, ast.Constant) else "{}"
                for chunk in item.values
            )
            tokens.add(rendered)
        elif isinstance(item, ast.Name):
            references.add(item.id)
        elif isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name):
            references.add(item.value.id + "." + item.attr)
        else:
            raise R41Refused("R41_UNREVIEWED_COMMAND_EXPRESSION")
    return tokens, references


def check_source(*, source: Path, expected_source_sha256: str,
                 operator_ack: bool = False) -> dict:
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or type(expected_source_sha256) is not str
            or not _SHA.fullmatch(expected_source_sha256)):
        raise R41Refused("R41_NONPRODUCTION_EXTERNAL_PIN_ACK_REQUIRED")
    if source.name != "secure_plugin_runtime_v1.py":
        raise R41Refused("R41_STAGE4_MODULE_NAME_REQUIRED")
    raw = _read_source(source)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_source_sha256:
        raise R41Refused("R41_STAGE4_SOURCE_PIN_MISMATCH")
    try:
        parsed = ast.parse(raw, filename="<pinned-stage4-module>")
    except (SyntaxError, ValueError, UnicodeError) as exc:
        raise R41Refused("R41_PINNED_SOURCE_SYNTAX_INVALID") from exc
    for function in _REQUIRED_FUNCTIONS:
        _function(parsed, function)
    command, references = _command_literals(_function(parsed, "build_run_command"))
    if not _REQUIRED <= command or "--name={}" not in command:
        raise R41Refused("R41_REQUIRED_GVISOR_ISOLATION_FLAGS_MISSING")
    if not {"policy.docker_binary", "policy.docker_socket",
            "policy.image", "_BOOTSTRAP"} <= references:
        raise R41Refused("R41_PINNED_COMMAND_HOST_OR_BOOTSTRAP_MISSING")
    if any(token == denied or token.startswith(denied + "=")
           for token in command for denied in _FORBIDDEN):
        raise R41Refused("R41_PRIVILEGED_OR_NETWORK_SWITCH_REFUSED")
    if "--host" not in command:
        raise R41Refused("R41_ROOTLESS_SOCKET_ROUTE_MISSING")
    # Static code presence does not prove that an external rootless
    # daemon and gVisor actually enforce these command-line switches.
    return {
        "verdict": "R41_STATIC_OCI_CONTRACT_PASS_HOST_TRIAL_PENDING",
        "stage4_sha256": digest,
        "required_hardening_flags_observed": len(_REQUIRED),
        "independent_rootless_host_tested": False,
        "gvisor_runtime_verified": False,
        "hostile_core_containment_proven": False,
        "cleanup_under_crash_proven": False,
        "broker_order_authorized": False,
        "telegram_authorized": False,
        "public_release_authorized": False,
        "live_authorized": False,
        "files_written": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage4-source", type=Path, required=True)
    parser.add_argument("--expected-stage4-sha256", required=True)
    parser.add_argument("--ack-readonly-static-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = check_source(
            source=args.stage4_source,
            expected_source_sha256=args.expected_stage4_sha256,
            operator_ack=args.ack_readonly_static_review,
        )
    except (R41Refused, OSError) as exc:
        print(json.dumps({
            "verdict": "R41_STATIC_CONTAINMENT_REVIEW_REFUSED",
            "reason": str(exc) if isinstance(exc, R41Refused)
                      else "R41_READONLY_IO_REFUSED",
            "hostile_core_containment_proven": False,
            "public_release_authorized": False,
            "live_authorized": False,
            "files_written": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
