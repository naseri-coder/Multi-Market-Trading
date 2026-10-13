"""RUNTIME-A1: optional polyglot Core API V1 host policy, NONPRODUCTION only.

This module does not supply/approve OCI runtime images or implement a strategy.
The worker protocol is framed bytes over stdin, never command-line executable
text. A pre-reviewed rootless+gVisor OCI worker image is mandatory per language.
The only permitted output is an inert, validated CoreResult.
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
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum

from .core_api_v1 import (
    ABI_MAJOR,
    ABI_MINOR,
    CoreContractError,
    CoreInput,
    CoreManifest,
    CoreResult,
    DataOrigin,
    _canonical,
)
from .secure_plugin_runtime_v1 import (
    SecurePluginPolicy,
    SecurePluginRefused,
    _assert_rootless_socket,
    _ensure_rootless_daemon,
    build_run_command,
    parse_core_result,
)
from .universal_artifact_intake_v1 import IntakeRefused, inspect_artifact

_MAX_PAYLOAD = 192 * 1024
_MAX_RESULT = 16 * 1024
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_KINDS = frozenset((".py", ".js", ".ts", ".wasm"))
_ENTRYPOINT = "/opt/mmt/bin/runtime-a1-worker"


class MultilangRefused(ValueError):
    """Non-disclosing, fail-closed polyglot runtime boundary."""


class RuntimeKind(StrEnum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    WASM = "wasm"


_KIND_BY_SUFFIX = {
    ".py": RuntimeKind.PYTHON,
    ".js": RuntimeKind.JAVASCRIPT,
    ".ts": RuntimeKind.TYPESCRIPT,
    ".wasm": RuntimeKind.WASM,
}


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    """Operator-selected image: SHA pin is identity, not publisher attestation.

    An enabled profile is usable only after a separate gVisor/rootless host
    audit and approval of the in-image \`runtime-a1-worker\` protocol binary.
    A user-uploaded artifact can never populate this object automatically.
    """

    kind: RuntimeKind
    policy: SecurePluginPolicy = SecurePluginPolicy()
    reviewed_image_sha256: str = ""
    protocol_version: str = "RUNTIME_A1_FRAMED_V1"
    worker_reviewed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RuntimeKind):
            raise MultilangRefused("UNKNOWN_RUNTIME_LANGUAGE")
        if (self.policy.enabled
                and (self.worker_reviewed is not True
                     or not _SHA.fullmatch(self.reviewed_image_sha256)
                     or self.policy.image.split("@sha256:")[-1] != self.reviewed_image_sha256
                     or self.protocol_version != "RUNTIME_A1_FRAMED_V1")):
            raise MultilangRefused("UNREVIEWED_WORKER_IMAGE_DENIED")


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Inert output only; there are intentionally no publication permissions."""

    language: RuntimeKind
    result: CoreResult
    artifact_sha256: str
    forward_enabled: bool = False
    orders_enabled: bool = False
    telegram_enabled: bool = False
    deployed: bool = False


def prepare_framed_request(
    kind: RuntimeKind, manifest: CoreManifest, event: CoreInput,
    *, artifact_name: str, artifact: bytes, approved_sha256: str,
) -> bytes:
    """Validate full input BEFORE starting any container or touching any OS."""

    if type(artifact_name) is not str or not isinstance(kind, RuntimeKind):
        raise MultilangRefused("INVALID_RUNTIME_ARTIFACT")
    suffix = "." + artifact_name.rsplit(".", 1)[-1].lower()
    if suffix not in _KINDS or _KIND_BY_SUFFIX[suffix] is not kind:
        raise MultilangRefused("LANGUAGE_EXTENSION_MISMATCH")
    if (not isinstance(manifest, CoreManifest) or not isinstance(event, CoreInput)
            or event.origin not in (DataOrigin.SYNTHETIC, DataOrigin.REPLAY)
            or event.core_id != manifest.core_id or
            event.core_version != manifest.core_version or
            event.binding.instrument.market not in manifest.supported_markets or
            event.event not in manifest.accepted_events or
            (event.candles and len(event.candles) < manifest.minimum_closed_candles)):
        raise MultilangRefused("NONPRODUCTION_CORE_EVENT_REQUIRED")
    if (type(artifact) is not bytes or type(approved_sha256) is not str
            or not _SHA.fullmatch(approved_sha256)
            or not hmac.compare_digest(hashlib.sha256(artifact).hexdigest(),
                                        approved_sha256)):
        raise MultilangRefused("APPROVED_SOURCE_DIGEST_REQUIRED")
    try:
        verdict = inspect_artifact(artifact_name, artifact)
    except IntakeRefused as exc:
        raise MultilangRefused("SOURCE_INTAKE_FAILED") from exc
    if verdict.sha256 != approved_sha256 or verdict.extension != suffix:
        raise MultilangRefused("SOURCE_INTAKE_MISMATCH")
    if verdict.findings:
        raise MultilangRefused("STATIC_SOURCE_REVIEW_REQUIRED")
    # Keep Stage-4 wire semantic compatibility: 4-byte source length,
    # exact artifact bytes, canonical request. The worker must verify both.
    request = json.dumps({
        "abi_major": ABI_MAJOR,
        "abi_minor": ABI_MINOR,
        "protocol": "RUNTIME_A1_FRAMED_V1",
        "runtime_kind": kind.value,
        "artifact_sha256": approved_sha256,
        "manifest_digest": hashlib.sha256(
            json.dumps(_canonical(manifest), sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
        "input_digest": event.input_digest,
        "event": _canonical(event),
    }, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
       allow_nan=False).encode()
    payload = len(artifact).to_bytes(4, "big") + artifact + request
    if len(payload) > _MAX_PAYLOAD:
        raise MultilangRefused("REQUEST_LIMIT_EXCEEDED")
    return payload


def build_polyglot_command(profile: RuntimeProfile, name: str) -> tuple[str, ...]:
    """Reuse the audited Stage-4 gVisor/rootless containment flags exactly."""

    if not isinstance(profile, RuntimeProfile) or not profile.policy.enabled:
        raise MultilangRefused("RUNTIME_DISABLED")
    base = build_run_command(profile.policy, name)
    # Only a reviewed worker can reinterpret the in-container framed protocol.
    # Replace the fixed Stage-4 Python bootstrap; never invoke user-provided
    # entrypoints, package managers, shell scripts or interpreter eval here.
    if "--entrypoint=python" not in base:
        raise MultilangRefused("ISOLATION_PROFILE_DRIFT")
    image_index = base.index(profile.policy.image)
    if not image_index or image_index + 5 != len(base):
        # Stage 4 terminates with: IMAGE -I -S -c FIXED_BOOTSTRAP
        raise MultilangRefused("ISOLATION_PROFILE_DRIFT")
    return (
        *tuple(x for x in base[:image_index] if x != "--entrypoint=python"),
        "--entrypoint=" + _ENTRYPOINT,
        "--env=MMT_RUNTIME_KIND=" + profile.kind.value,
        profile.policy.image,
    )


def _kill(process: subprocess.Popen[bytes]) -> None:
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=2)


def _run_oci(profile: RuntimeProfile, name: str, payload: bytes) -> bytes:
    """Host-only bounded I/O; process starts ONLY after rootless daemon check."""

    command = build_polyglot_command(profile, name)
    proc: subprocess.Popen[bytes] | None = None
    response = bytearray()
    cleanup_proved = False
    try:
        proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin",
                                            "HOME": "/nonexistent"},
            close_fds=True, start_new_session=True,
        )
        assert proc.stdin is not None and proc.stdout is not None
        os.set_blocking(proc.stdin.fileno(), False)
        os.set_blocking(proc.stdout.fileno(), False)
        offset, stdin_open, stdout_open = 0, True, True
        deadline = time.monotonic() + profile.policy.timeout_seconds
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdin, selectors.EVENT_WRITE)
            sel.register(proc.stdout, selectors.EVENT_READ)
            while stdin_open or stdout_open or proc.poll() is None:
                remain = deadline - time.monotonic()
                if remain <= 0:
                    raise MultilangRefused("RUNTIME_TIMEOUT")
                for key, _ in sel.select(timeout=min(remain, 0.1)):
                    if key.fileobj is proc.stdin:
                        try:
                            n = os.write(proc.stdin.fileno(), payload[offset:offset+8192])
                        except (BrokenPipeError, OSError) as exc:
                            raise MultilangRefused("RUNTIME_INPUT_CLOSED") from exc
                        if n <= 0:
                            raise MultilangRefused("RUNTIME_INPUT_CLOSED")
                        offset += n
                        if offset == len(payload):
                            sel.unregister(proc.stdin)
                            proc.stdin.close()
                            stdin_open = False
                    else:
                        block = os.read(proc.stdout.fileno(), 4096)
                        if not block:
                            sel.unregister(proc.stdout)
                            stdout_open = False
                        else:
                            response.extend(block)
                            if len(response) > _MAX_RESULT:
                                raise MultilangRefused("RUNTIME_OUTPUT_LIMIT")
                if proc.poll() is not None and not stdout_open:
                    break
        if proc.poll() != 0 or not response:
            raise MultilangRefused("RUNTIME_PROCESS_FAILED")
    except OSError as exc:
        raise MultilangRefused("RUNTIME_NOT_AVAILABLE") from exc
    except SecurePluginRefused as exc:
        raise MultilangRefused("RUNTIME_REFUSED") from exc
    finally:
        if proc is not None:
            if proc.poll() is None:
                _kill(proc)
            try:
                # Exact autogenerated child name only; never user input.
                rm = subprocess.run(
                    [profile.policy.docker_binary, "--host",
                     profile.policy.docker_socket, "rm", "-f", name],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, timeout=3, check=False,
                    env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
                )
                cleanup_proved = rm.returncode == 0 or b"No such container" in rm.stderr
            except (OSError, subprocess.TimeoutExpired):
                pass
    if not cleanup_proved:
        raise MultilangRefused("OCI_CLEANUP_NOT_PROVED")
    return bytes(response)


class MultiLanguageOfflineHost:
    """Admits reviewed OCI workers only; never imports/evaluates uploaded code."""

    def __init__(self, profiles: tuple[RuntimeProfile, ...] = ()) -> None:
        if (type(profiles) is not tuple
                or any(not isinstance(p, RuntimeProfile) for p in profiles)
                or len({p.kind for p in profiles}) != len(profiles)):
            raise MultilangRefused("RUNTIME_PROFILE_REGISTRY_INVALID")
        self._profiles = {profile.kind: profile for profile in profiles}
        self.quarantined: set[str] = set()

    def status(self) -> dict[str, str]:
        return {
            kind.value: ("REVIEWED_WORKER_POLICY" if
                         kind in self._profiles and self._profiles[kind].policy.enabled
                         else "WORKER_NOT_INSTALLED")
            for kind in RuntimeKind
        }

    def evaluate(
        self, kind: RuntimeKind, manifest: CoreManifest, event: CoreInput,
        *, artifact_name: str, artifact: bytes, approved_sha256: str,
    ) -> RuntimeResult:
        if not isinstance(kind, RuntimeKind):
            raise MultilangRefused("UNSUPPORTED_RUNTIME_KIND")
        profile = self._profiles.get(kind)
        if profile is None or not profile.policy.enabled:
            raise MultilangRefused("WORKER_NOT_INSTALLED")
        binding = event.binding.binding_id if isinstance(event, CoreInput) else None
        if binding in self.quarantined:
            raise MultilangRefused("BINDING_QUARANTINED")
        framed = prepare_framed_request(
            kind, manifest, event, artifact_name=artifact_name,
            artifact=artifact, approved_sha256=approved_sha256,
        )
        name = "mmt-core-" + secrets.token_hex(12)
        try:
            _assert_rootless_socket(profile.policy)
            _ensure_rootless_daemon(profile.policy)
            response = _run_oci(profile, name, framed)
            result = parse_core_result(response, manifest, event)
            return RuntimeResult(kind, result, approved_sha256)
        except (MultilangRefused, SecurePluginRefused,
                CoreContractError, OSError) as exc:
            if binding is not None:
                self.quarantined.add(binding)
            raise MultilangRefused("RUNTIME_CORE_QUARANTINED") from exc


__all__ = [
    "MultiLanguageOfflineHost", "MultilangRefused", "RuntimeKind",
    "RuntimeProfile", "RuntimeResult", "prepare_framed_request",
    "build_polyglot_command",
]
