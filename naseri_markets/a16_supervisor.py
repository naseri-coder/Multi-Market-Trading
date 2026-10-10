"""A16 Linux-only, temporary, signed-gated *fixture* process supervisor.

Runs ONLY a fixed, inert Python stdin/stdout worker. Never imports or executes
a private-engine package or performs external IO, trades, Telegram, Docker or
production process control. Does not provide OS sandboxing or remote attestation.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import re
import secrets
import selectors
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .a14_packages import _atomic_json, _pairs
from .a15_releases import SignedMockDeploymentManager

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
# No subprocess supplied by a package, no network calls, no dynamic imports.
# Worker exits on parent stdin EOF, including when the parent crashes.
_FIXED_WORKER = """
import os, sys
token, digest = sys.argv[1:]
sys.stdout.write('READY|' + token + '|' + digest + '\\n')
sys.stdout.flush()
for data in sys.stdin.buffer:
    if len(data) > 192:
        break
    parts = data.rstrip(b'\\n').decode('ascii', 'replace').split('|')
    if len(parts) != 4 or parts[1] != token or parts[2] != digest:
        break
    action, _, _, nonce = parts
    if not nonce.isdigit() or len(nonce) > 16:
        break
    if action == 'PING':
        sys.stdout.write('PONG|' + token + '|' + digest + '|' + nonce + '\\n')
        sys.stdout.flush()
    elif action == 'STOP':
        sys.stdout.write('BYE|' + token + '|' + digest + '|' + nonce + '\\n')
        sys.stdout.flush()
        break
    elif action == 'CRASH':  # deterministic negative-test fault only
        os._exit(23)
    else:
        break
"""


@dataclass(frozen=True, slots=True)
class FixtureProcessLimits:
    """Bounded Linux child resource ceilings; never a sandbox."""
    memory_bytes: int = 256 * 1024 * 1024
    cpu_seconds: int = 5
    open_files: int = 48

    def __post_init__(self):
        if (type(self.memory_bytes) is not int
                or not 128 * 1024 * 1024 <= self.memory_bytes <= 512 * 1024 * 1024
                or type(self.cpu_seconds) is not int
                or not 2 <= self.cpu_seconds <= 20
                or type(self.open_files) is not int
                or not 24 <= self.open_files <= 128):
            raise ValueError("A17_FIXTURE_LIMITS_OUT_OF_BOUNDS")


class ServiceRefused(ValueError):
    """A16 fails closed rather than claiming fixture service health."""


@dataclass(frozen=True, slots=True)
class FixtureServiceStatus:
    state: str
    revision: int
    artifact_sha256: str | None
    owned_process_alive: bool
    signed_and_admitted_now: bool
    real_private_engine_running: bool = False
    live_trading_permitted: bool = False


class OfflineFixtureSupervisor:
    """Explicitly signed A15 / A12-A13-gated process fixture.

    This is a *separate* process from the A14 no-op mock worker. A16
    requires that A14's own worker is STOPPED. Only the A16 supervisor
    spawns this static fixture; no package entry point can be executed.
    """

    def __init__(self, root: str | Path, *, signed: SignedMockDeploymentManager,
                 engine_id: str, installation_id: str,
                 process_limits: FixtureProcessLimits | None = None) -> None:
        if not isinstance(signed, SignedMockDeploymentManager):
            raise ServiceRefused("A16_SIGNED_A15_REQUIRED")
        if (type(engine_id) is not str or not _ID.fullmatch(engine_id)
                or type(installation_id) is not str
                or not _ID.fullmatch(installation_id)
                or signed._mock._engine_id != engine_id
                or signed._mock._installation_id != installation_id
                or signed._authority.engine_id != engine_id
                or signed._authority.installation_id != installation_id):
            raise ServiceRefused("A16_IDENTITY_MISMATCH")
        root = Path(root)
        tmp = Path(tempfile.gettempdir()).resolve()
        if (not root.is_absolute() or root.is_symlink()
                or root.parent.is_symlink() or root.resolve() == tmp
                or not root.resolve().is_relative_to(tmp)
                or root.resolve() == signed._mock._root.resolve()
                or root.resolve().is_relative_to(signed._mock._root.resolve())
                or signed._mock._root.resolve().is_relative_to(root.resolve())):
            raise ServiceRefused("A16_DISPOSABLE_ISOLATED_ROOT_REQUIRED")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not root.is_dir() or root.stat().st_mode & 0o077:
            raise ServiceRefused("A16_UNSAFE_ROOT_PERMISSIONS")
        self._root = root
        self._signed = signed
        self._engine = engine_id
        self._installation = installation_id
        if process_limits is not None and not isinstance(process_limits, FixtureProcessLimits):
            raise ServiceRefused("A17_TYPED_LIMITS_REQUIRED")
        self._process_limits = process_limits
        self._state_path = root / "service-state.json"
        self._state_lock = root / "service-state.lock"
        self._worker_lock = root / "service-worker.lock"
        self._child: subprocess.Popen | None = None
        self._worker_fd: int | None = None
        self._token: str | None = None
        self._pending = b""
        self._request_sequence = 0
        with self._locked():
            if not self._state_path.exists():
                _atomic_json(self._state_path, {
                    "schema": 1, "engine_id": engine_id,
                    "installation_id": installation_id, "revision": 0,
                    "state": "STOPPED", "artifact_sha256": None,
                    "a14_revision": None, "events": [],
                })
            self._load()

    @contextlib.contextmanager
    def _locked(self):
        fd = os.open(self._state_lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _load(self) -> dict:
        if self._state_path.is_symlink():
            raise ServiceRefused("A16_SYMLINK_STATE_REFUSED")
        try:
            raw = self._state_path.read_bytes()
            if len(raw) > 8192:
                raise ServiceRefused("A16_OVERSIZED_STATE")
            import json
            state = json.loads(raw, object_pairs_hook=_pairs)
        except (OSError, ValueError, UnicodeError) as exc:
            raise ServiceRefused("A16_CORRUPT_STATE") from exc
        if (type(state) is not dict or set(state) != {
                "schema", "engine_id", "installation_id", "revision",
                "state", "artifact_sha256", "a14_revision", "events"}
                or type(state["schema"]) is not int or state["schema"] != 1
                or state["engine_id"] != self._engine
                or state["installation_id"] != self._installation
                or type(state["revision"]) is not int or state["revision"] < 0
                or state["state"] not in ("STOPPED", "RUNNING", "QUARANTINED",
                                         "RECOVERY_REQUIRED")
                or (state["artifact_sha256"] is not None
                    and (type(state["artifact_sha256"]) is not str
                         or not _HASH.fullmatch(state["artifact_sha256"])))
                or (state["a14_revision"] is not None
                    and (type(state["a14_revision"]) is not int
                         or state["a14_revision"] < 1))
                or type(state["events"]) is not list
                or len(state["events"]) > 24
                or any(type(e) is not str or len(e) > 64
                       for e in state["events"])):
            raise ServiceRefused("A16_INVALID_STATE")
        return state

    @staticmethod
    def _cas(state: dict, expected_revision: int):
        if (type(expected_revision) is not int
                or expected_revision != state["revision"]):
            raise ServiceRefused("A16_STALE_REVISION")

    def _commit(self, state: dict, new_state: str, event: str):
        state["revision"] += 1
        state["state"] = new_state
        state["events"] = (state["events"] + [event])[-24:]
        _atomic_json(self._state_path, state)

    def _reserve(self):
        fd = os.open(self._worker_lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise ServiceRefused("A16_WORKER_OWNED_BY_ANOTHER_PROCESS") from exc
        self._worker_fd = fd

    def _release(self):
        if self._worker_fd is not None:
            fcntl.flock(self._worker_fd, fcntl.LOCK_UN)
            os.close(self._worker_fd)
            self._worker_fd = None

    def _owned_alive(self) -> bool:
        return self._child is not None and self._child.poll() is None

    def _status(self, state: dict, admitted: bool = False) -> FixtureServiceStatus:
        shown = state["state"]
        alive = self._owned_alive()
        if shown == "RUNNING" and not alive:
            shown = "RECOVERY_REQUIRED"
        return FixtureServiceStatus(shown, state["revision"],
                                    state["artifact_sha256"], alive,
                                    admitted and shown == "RUNNING")

    def status(self) -> FixtureServiceStatus:
        # No persisted RUNNING flag alone can claim a live or trusted service.
        with self._locked():
            return self._status(self._load())

    def history(self) -> tuple[str, ...]:
        with self._locked():
            return tuple(self._load()["events"])

    def _admit_active(self, *, admission, now: int) -> tuple[str, int, dict]:
        # Verify from the *current* A14 immutable archive and A15 witness.
        # A14 is a fixture-only manager, never a deployment security boundary.
        base = self._signed._mock.status()
        if (base.state != "STOPPED" or base.owned_mock_worker_running
                or base.active is None):
            raise ServiceRefused("A16_A14_MUST_REMAIN_STOPPED")
        record = self._signed._mock._admit(admission, now)
        manifest = self._signed._mock._verified_release(base.active, record)
        self._signed._authority.require_current(
            base.active, now=now, record=record, manifest=manifest)
        if manifest["mock_behavior"] != "healthy":
            raise ServiceRefused("A16_INJECTED_UNHEALTHY_RELEASE")
        return base.active, base.revision, manifest

    def _receive(self, timeout: float = 1.0) -> str:
        if self._child is None or self._child.stdout is None:
            raise ServiceRefused("A16_NO_OWNED_CHILD")
        fd = self._child.stdout.fileno()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            while True:
                if b"\n" in self._pending:
                    one, self._pending = self._pending.split(b"\n", 1)
                    if len(one) > 192:
                        raise ServiceRefused("A16_INVALID_WORKER_FRAME")
                    try:
                        return one.decode("ascii")
                    except UnicodeError as exc:
                        raise ServiceRefused("A16_NONASCII_WORKER_FRAME") from exc
                if len(self._pending) > 192:
                    raise ServiceRefused("A16_OVERSIZED_WORKER_FRAME")
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise ServiceRefused("A16_HEALTH_TIMEOUT")
                chunk = os.read(fd, 256)
                if not chunk:
                    raise ServiceRefused("A16_WORKER_PIPE_CLOSED")
                self._pending += chunk

    def _request(self, cmd: str, digest: str):
        if not self._owned_alive() or self._child is None or self._child.stdin is None:
            raise ServiceRefused("A16_WORKER_NOT_RUNNING")
        self._request_sequence += 1
        nonce = str(self._request_sequence)
        expected = {
            "PING": "PONG", "STOP": "BYE",
        }[cmd] + "|" + self._token + "|" + digest + "|" + nonce
        frame = (cmd + "|" + self._token + "|" + digest + "|" + nonce + "\n").encode("ascii")
        try:
            self._child.stdin.write(frame)
            self._child.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ServiceRefused("A16_WORKER_PIPE_WRITE_FAILED") from exc
        if self._receive() != expected:
            raise ServiceRefused("A16_BAD_WORKER_RESPONSE")

    def _halt_owned(self, digest: str | None = None):
        child = self._child
        try:
            if child is not None:
                if child.poll() is None and digest is not None:
                    try:
                        self._request("STOP", digest)
                    except ServiceRefused:
                        pass
                if child.stdin is not None:
                    child.stdin.close()
                try:
                    child.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2.0)
                if child.stdout is not None:
                    child.stdout.close()
        finally:
            self._child = None
            self._token = None
            self._pending = b""
            self._release()

    def start(self, *, expected_revision: int, admission, now: int):
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "STOPPED" or self._child is not None:
                raise ServiceRefused("A16_EXPLICIT_RECOVERY_OR_STOP_REQUIRED")
            digest, base_revision, _ = self._admit_active(admission=admission, now=now)
            self._reserve()
            try:
                self._token = secrets.token_hex(16)
                source = _FIXED_WORKER
                if self._process_limits is not None:
                    ceiling = self._process_limits
                    # Fixed stdlib preamble runs INSIDE the child; preexec_fn
                    # is not safe when the parent has active threads.
                    source = (
                        "import resource\n"
                        f"resource.setrlimit(resource.RLIMIT_AS, ({ceiling.memory_bytes}, {ceiling.memory_bytes}))\n"
                        f"resource.setrlimit(resource.RLIMIT_CPU, ({ceiling.cpu_seconds}, {ceiling.cpu_seconds}))\n"
                        f"resource.setrlimit(resource.RLIMIT_NOFILE, ({ceiling.open_files}, {ceiling.open_files}))\n"
                        "resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n"
                        + _FIXED_WORKER
                    )
                self._child = subprocess.Popen(
                    [sys.executable, "-I", "-S", "-u", "-c", source,
                     self._token, digest],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, cwd=self._root,
                    env={"PYTHONNOUSERSITE": "1"}, close_fds=True,
                )
                if self._receive() != "READY|" + self._token + "|" + digest:
                    raise ServiceRefused("A16_BAD_STARTUP_IDENTITY")
                self._request("PING", digest)
                # A15 signature and A12 admission are checked again *after*
                # launch, before persisting an affirmative running status.
                fresh, revision, _ = self._admit_active(admission=admission, now=now)
                if (fresh, revision) != (digest, base_revision):
                    raise ServiceRefused("A16_RELEASE_CHANGED_DURING_START")
                state["artifact_sha256"] = digest
                state["a14_revision"] = base_revision
                self._commit(state, "RUNNING", "START_FIXTURE")
            except BaseException:
                self._halt_owned()
                raise
            return self._status(state, admitted=True)

    def health(self, *, admission, now: int) -> FixtureServiceStatus:
        """One fresh signed/licensed probe; invalid evidence halts *owned* fixture."""
        with self._locked():
            state = self._load()
            if state["state"] != "RUNNING" or self._child is None:
                return self._status(state)
            try:
                digest, base_revision, _ = self._admit_active(
                    admission=admission, now=now)
                if (digest, base_revision) != (
                    state["artifact_sha256"], state["a14_revision"]
                ):
                    raise ServiceRefused("A16_RELEASE_CHANGED_DURING_RUN")
                self._request("PING", digest)
            except (ValueError, OSError, TimeoutError, BrokenPipeError):
                # Local safety action; does not kill any PID not owned by this
                # process. No restart and no automatic permission escalation.
                self._halt_owned()
                self._commit(state, "QUARANTINED", "FAIL_CLOSED_HEALTH")
                return self._status(state)
            return self._status(state, admitted=True)

    def quarantine_owned_for_a17(self):
        """Fail-closed kill of only the child this A16 instance owns.

        The A17 watchdog invokes this on unexpected monitor faults.
        It cannot adopt an arbitrary PID or reset signed release floors.
        """
        with self._locked():
            state = self._load()
            if state["state"] == "RUNNING" and self._child is not None:
                self._halt_owned()
                self._commit(state, "QUARANTINED", "A17_WATCHDOG_EXCEPTION")
            return self._status(state)

    def stop(self, *, expected_revision: int):
        """STOP remains available even when A12/A15 grants have been revoked."""
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "RUNNING" or self._child is None:
                raise ServiceRefused("A16_NO_OWNED_RUNNING_WORKER")
            self._halt_owned(state["artifact_sha256"])
            self._commit(state, "STOPPED", "STOP_FIXTURE")
            return self._status(state)

    def crash_fixture_for_test(self, *, expected_revision: int):
        """Deliberate crash injection; available ONLY in this inert fixture."""
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "RUNNING" or not self._owned_alive():
                raise ServiceRefused("A16_CRASH_ONLY_OWNED_RUNNING_FIXTURE")
            frame = ("CRASH|" + self._token + "|" + state["artifact_sha256"]
                     + "|1\n").encode("ascii")
            self._child.stdin.write(frame)
            self._child.stdin.flush()
            self._child.wait(timeout=2.0)
            return self._status(state)

    def reconcile(self, *, expected_revision: int):
        """Explicit manual crash/restart acknowledgement, never auto-restart."""
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if (state["state"] not in ("RUNNING", "QUARANTINED", "RECOVERY_REQUIRED")
                    or self._owned_alive()):
                raise ServiceRefused("A16_RECONCILE_REQUIRES_QUIESCENCE")
            # Refuse if another supervisor still owns the fixture.
            if self._worker_fd is None:
                self._reserve()
            try:
                if self._child is not None:
                    self._halt_owned()
                state["artifact_sha256"] = None
                state["a14_revision"] = None
                self._commit(state, "STOPPED", "MANUAL_RECONCILE")
            finally:
                self._release()
            return self._status(state)

    def close(self):
        if self._child is not None:
            with self._locked():
                state = self._load()
                self._halt_owned(state["artifact_sha256"])
                if state["state"] == "RUNNING":
                    self._commit(state, "STOPPED", "OWNER_CLOSE_STOP")
