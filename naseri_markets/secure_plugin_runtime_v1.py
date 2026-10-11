"""Stage 4: disabled-by-default OFFLINE OCI execution of public Core API v1 code.

An untrusted Python core is *never* imported or executed by this host process.
This is a candidate for an independently hardened, dedicated rootless Docker +
gVisor worker host; not a generic Python sandbox, not approved for production.
No broker/Telegram/secret/database access or automatic plugin registration.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import selectors
import signal
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .contracts import Direction
from .core_api_v1 import (
    ABI_MAJOR, ABI_MINOR, CoreContractError, CoreDecision,
    CoreInput, CoreManifest, CoreResult, DecisionKind, ExitAction,
    ManagementAction, _canonical, validate_core_result,
)

_MAX_SOURCE = 65536
_MAX_INPUT = 196608
_MAX_OUTPUT = 16384
_PIN = re.compile(r"^[0-9a-f]{64}$")
_IMAGE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,195}@sha256:[0-9a-f]{64}$")

# Only static bootstrap source appears in argv; the plugin and request are on stdin.
# This code is run INSIDE the pinned, gVisor-protected OCI container.
_BOOTSTRAP = '''import io,struct,sys
header=sys.stdin.buffer.read(4)
if len(header)!=4: sys.exit(71)
size=struct.unpack("!I",header)[0]
if not 0<size<=65536: sys.exit(72)
source=sys.stdin.buffer.read(size)
if len(source)!=size: sys.exit(73)
request=sys.stdin.buffer.read(196609)
if len(request)>196608: sys.exit(74)
sys.stdin=io.TextIOWrapper(io.BytesIO(request),encoding="utf-8")
exec(compile(source.decode("utf-8"),"<external-core>","exec"),{"__name__":"__main__"})
'''


class SecurePluginRefused(ValueError):
    """No direct exception detail or plugin output is disclosed to end users."""


@dataclass(frozen=True, slots=True)
class SecurePluginPolicy:
    """A request is denied unless an isolated operator explicitly enables it."""

    enabled: bool = False
    image: str = ""
    docker_binary: str = "/usr/bin/docker"
    docker_socket: str = ""
    timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        if self.enabled is not True:
            return
        if (os.geteuid() == 0 or not _IMAGE.fullmatch(self.image)
                or type(self.timeout_seconds) not in (int, float)
                or not 0.5 <= self.timeout_seconds <= 10):
            raise SecurePluginRefused("UNSAFE_ISOLATION_POLICY")
        if type(self.docker_binary) is not str or not self.docker_binary.startswith("/"):
            raise SecurePluginRefused("ABSOLUTE_DOCKER_BINARY_REQUIRED")
        # A root-owned Docker socket is equivalent to privileged host control.
        # Refuse it; require the current non-root user's rootless Docker socket.
        expected = f"unix:///run/user/{os.geteuid()}/docker.sock"
        if self.docker_socket != expected:
            raise SecurePluginRefused("ROOTLESS_DOCKER_SOCKET_REQUIRED")


def _pair_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecurePluginRefused("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _price(raw: object) -> Decimal | None:
    if raw is None:
        return None
    if type(raw) is not str or not 0 < len(raw) <= 64:
        raise SecurePluginRefused("DECIMAL_STRING_REQUIRED")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise SecurePluginRefused("INVALID_DECIMAL") from exc
    if not value.is_finite():
        raise SecurePluginRefused("INVALID_DECIMAL")
    return value


def _optional_enum(enum_cls: type, raw: object) -> object:
    if raw is None:
        return None
    if type(raw) is not str:
        raise SecurePluginRefused("INVALID_ENUM")
    try:
        return enum_cls(raw)
    except ValueError as exc:
        raise SecurePluginRefused("INVALID_ENUM") from exc


def _when(raw: object) -> datetime:
    if type(raw) is not str or len(raw) > 48:
        raise SecurePluginRefused("INVALID_TIMESTAMP")
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SecurePluginRefused("INVALID_TIMESTAMP") from exc


def parse_core_result(blob: bytes, manifest: CoreManifest, event: CoreInput) -> CoreResult:
    """Strict wire boundary: only a typed, causally valid v1 result escapes."""
    if type(blob) is not bytes or not 0 < len(blob) <= _MAX_OUTPUT:
        raise SecurePluginRefused("OUTPUT_SIZE_REJECTED")
    try:
        data = json.loads(blob.decode("utf-8"), object_pairs_hook=_pair_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              SecurePluginRefused("NONFINITE_JSON_NUMBER")))
    except SecurePluginRefused:
        raise
    except (ValueError, UnicodeError) as exc:
        raise SecurePluginRefused("OUTPUT_NOT_STRICT_JSON") from exc
    fields = {"abi_major", "abi_minor", "core_id", "core_version", "instance_id",
              "binding_id", "observed_at", "input_digest", "decisions"}
    if type(data) is not dict or set(data) != fields:
        raise SecurePluginRefused("OUTPUT_SCHEMA_REJECTED")
    if type(data["abi_major"]) is not int or data["abi_major"] != ABI_MAJOR or (
            type(data["abi_minor"]) is not int or data["abi_minor"] != ABI_MINOR):
        raise SecurePluginRefused("OUTPUT_ABI_REJECTED")
    decisions = data["decisions"]
    if type(decisions) is not list or not 1 <= len(decisions) <= 12:
        raise SecurePluginRefused("OUTPUT_DECISIONS_REJECTED")
    allowed = {"decision_id", "kind", "setup_id", "reason_codes", "direction",
               "entry", "stop", "targets", "expires_at", "action", "position_id",
               "expected_position_revision", "new_stop", "pending_entry_id"}
    typed: list[CoreDecision] = []
    for raw in decisions:
        if type(raw) is not dict or not {"decision_id", "kind"} <= set(raw) or set(raw) - allowed:
            raise SecurePluginRefused("OUTPUT_DECISION_SCHEMA_REJECTED")
        ts = raw.get("targets", [])
        reasons = raw.get("reason_codes", [])
        if type(ts) is not list or type(reasons) is not list:
            raise SecurePluginRefused("OUTPUT_ARRAY_REJECTED")
        action = raw.get("action")
        if action is not None:
            # Do not silently conflate stop-management and position-exit actions.
            action = (_optional_enum(ManagementAction, action)
                      if raw["kind"] == DecisionKind.MANAGEMENT_INTENT.value
                      else _optional_enum(ExitAction, action))
        try:
            typed.append(CoreDecision(
                decision_id=raw["decision_id"], kind=DecisionKind(raw["kind"]),
                setup_id=raw.get("setup_id"), reason_codes=tuple(reasons),
                direction=_optional_enum(Direction, raw.get("direction")),
                entry=_price(raw.get("entry")), stop=_price(raw.get("stop")),
                targets=tuple(_price(v) for v in ts),
                expires_at=(\n                    _when(raw["expires_at"]) if raw.get("expires_at") is not None else None\n                ),
                action=action, position_id=raw.get("position_id"),
                expected_position_revision=raw.get("expected_position_revision"),
                new_stop=_price(raw.get("new_stop")),
                pending_entry_id=raw.get("pending_entry_id"),
            ))
        except (KeyError, TypeError, ValueError, CoreContractError) as exc:
            raise SecurePluginRefused("OUTPUT_DECISION_INVALID") from exc
    try:
        result = CoreResult(
            core_id=data["core_id"], core_version=data["core_version"],
            instance_id=data["instance_id"], binding_id=data["binding_id"],
            observed_at=_when(data["observed_at"]),
            input_digest=data["input_digest"], decisions=tuple(typed),
        )
        validate_core_result(manifest, event, result)
    except (TypeError, ValueError, CoreContractError) as exc:
        raise SecurePluginRefused("OUTPUT_CONTRACT_REJECTED") from exc
    return result


def build_run_command(policy: SecurePluginPolicy, name: str) -> tuple[str, ...]:
    """No shell, bind mounts, host networking, forwarded env, or plugin in argv."""
    if not policy.enabled or not re.fullmatch(r"mmt-core-[0-9a-f]{24}", name):
        raise SecurePluginRefused("SANDBOX_NOT_AUTHORIZED")
    return (
        policy.docker_binary, "--host", policy.docker_socket, "run", "--rm",
        "--pull=never", f"--name={name}", "--runtime=runsc",
        "--network=none", "--ipc=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=32",
        "--memory=128m", "--memory-swap=128m", "--cpus=0.5",
        "--ulimit=nofile=64:64", "--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
        "--workdir=/tmp", "--entrypoint=python", "--env=PYTHONDONTWRITEBYTECODE=1",
        policy.image, "-I", "-S", "-c", _BOOTSTRAP,
    )


def _assert_rootless_socket(policy: SecurePluginPolicy) -> None:
    path = Path(policy.docker_socket.removeprefix("unix://"))
    try:
        st = path.lstat()
    except OSError as exc:
        raise SecurePluginRefused("ROOTLESS_DOCKER_NOT_AVAILABLE") from exc
    if (not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.geteuid()
            or path.is_symlink()):
        raise SecurePluginRefused("ROOTLESS_DOCKER_SOCKET_UNTRUSTED")


def _ensure_rootless_daemon(policy: SecurePluginPolicy) -> None:
    """Refuse daemons not advertising rootless mode; no insecure fallback."""
    try:
        result = subprocess.run(
            [policy.docker_binary, "--host", policy.docker_socket,
             "info", "--format", "{{json .SecurityOptions}}"],
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=3, check=False,
        )
        if result.returncode or len(result.stdout) > 4096:
            raise SecurePluginRefused("ROOTLESS_DOCKER_NOT_VERIFIED")
        parsed = json.loads(result.stdout)
        if type(parsed) is not list or "name=rootless" not in parsed:
            raise SecurePluginRefused("ROOTLESS_DOCKER_NOT_VERIFIED")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise SecurePluginRefused("ROOTLESS_DOCKER_NOT_VERIFIED") from exc


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _invoke(policy: SecurePluginPolicy, name: str, payload: bytes) -> bytes:
    """Bounded duplex I/O; prevent unlimited stdout and stuck stdin writes."""
    command = build_run_command(policy, name)
    process: subprocess.Popen[bytes] | None = None
    failure: str | None = None
    buffer = bytearray()
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        )
        assert process.stdin is not None and process.stdout is not None
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        deadline = time.monotonic() + policy.timeout_seconds
        offset = 0
        input_open = True
        output_open = True
        with selectors.DefaultSelector() as watch:
            watch.register(process.stdin, selectors.EVENT_WRITE)
            watch.register(process.stdout, selectors.EVENT_READ)
            while input_open or output_open or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failure = "SANDBOX_TIMEOUT"
                    break
                for key, _ in watch.select(timeout=min(remaining, 0.1)):
                    if key.fileobj is process.stdin:
                        try:
                            n = os.write(process.stdin.fileno(), payload[offset:offset + 8192])
                        except (BrokenPipeError, OSError):
                            n = 0
                            offset = len(payload)
                        offset += n
                        if offset == len(payload):
                            watch.unregister(process.stdin)
                            process.stdin.close()
                            input_open = False
                    else:
                        block = os.read(process.stdout.fileno(), 4096)
                        if not block:
                            watch.unregister(process.stdout)
                            output_open = False
                        else:
                            buffer.extend(block)
                            if len(buffer) > _MAX_OUTPUT:
                                failure = "SANDBOX_OUTPUT_LIMIT"
                                break
                if failure:
                    break
                if process.poll() is not None and not output_open:
                    break
        if not failure and (process.poll() is None or process.returncode != 0 or not buffer):
            failure = "SANDBOX_PROCESS_FAILED"
        if failure:
            raise SecurePluginRefused(failure)
        return bytes(buffer)
    except OSError as exc:
        raise SecurePluginRefused("SANDBOX_RUNTIME_NOT_AVAILABLE") from exc
    finally:
        if process is not None:
            if process.poll() is None:
                _kill_group(process)
            # A detached daemon-side container can survive a killed Docker CLI.
            # The unique random name is never selected by user/plugin input.
            try:
                subprocess.run(
                    [policy.docker_binary, "--host", policy.docker_socket,
                     "rm", "-f", name],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=3, check=False,
                    env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
                )
            except (OSError, subprocess.TimeoutExpired):
                # Cannot prove cleanup. Treat isolated host as needing inspection.
                pass


class SecureOfflineCoreHost:
    """Bounded invocation; output is an inert contract decision only."""

    def __init__(self, policy: SecurePluginPolicy) -> None:
        self.policy = policy
        self.quarantined: set[str] = set()

    def evaluate(self, manifest: CoreManifest, event: CoreInput, *,
                 source: bytes, approved_source_sha256: str) -> CoreResult:
        if not self.policy.enabled:
            raise SecurePluginRefused("SECURE_EXECUTION_DISABLED")
        if event.binding.binding_id in self.quarantined:
            raise SecurePluginRefused("BINDING_QUARANTINED")
        if (not isinstance(manifest, CoreManifest) or not isinstance(event, CoreInput)
                or event.core_id != manifest.core_id or
                event.core_version != manifest.core_version or
                event.binding.instrument.market not in manifest.supported_markets or
                event.event not in manifest.accepted_events or
                (event.candles and len(event.candles) < manifest.minimum_closed_candles)):
            raise SecurePluginRefused("INCOMPATIBLE_CORE_EVENT")
        if (type(source) is not bytes or not 0 < len(source) <= _MAX_SOURCE
                or type(approved_source_sha256) is not str or
                not _PIN.fullmatch(approved_source_sha256) or
                not hmac.compare_digest(hashlib.sha256(source).hexdigest(),
                                        approved_source_sha256)):
            raise SecurePluginRefused("SOURCE_PIN_REQUIRED")
        request = json.dumps({
            "abi_major": ABI_MAJOR, "abi_minor": ABI_MINOR,
            "manifest_digest": hashlib.sha256(
                json.dumps(_canonical(manifest), sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "event": _canonical(event),
            "input_digest": event.input_digest,
        }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(request) > _MAX_INPUT:
            raise SecurePluginRefused("INPUT_TOO_LARGE")
        framed = len(source).to_bytes(4, "big") + source + request
        name = "mmt-core-" + secrets.token_hex(12)
        try:
            _assert_rootless_socket(self.policy)
            _ensure_rootless_daemon(self.policy)
            blob = _invoke(self.policy, name, framed)
            return parse_core_result(blob, manifest, event)
        except (SecurePluginRefused, CoreContractError, OSError) as exc:
            self.quarantined.add(event.binding.binding_id)
            raise SecurePluginRefused("SECURE_CORE_QUARANTINED") from exc
