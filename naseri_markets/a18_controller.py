"""A18 signed-gated controller for a separate *inert* Linux Guardian process.

The Guardian is a process, not an A17 daemon thread. All code it executes is a
fixed public fixture and is independent of the mock ZIP payload. This is not a
production private-engine loader or an adversarial OS security boundary.
"""
from __future__ import annotations

import fcntl
import json
import os
import pwd
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .a15_releases import SignedMockDeploymentManager
from .a16_supervisor import ServiceRefused
from .a18_guardian import atomic_status

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")


class GuardianRefused(ServiceRefused):
    """An unsigned, stale or unowned fixture guardian action was rejected."""


@dataclass(frozen=True, slots=True)
class GuardianStatus:
    state: str
    revision: int
    worker_alive: bool
    guardian_alive: bool
    sandbox_verified: bool
    current_proof_checked: bool = False
    mock_fixture_only: bool = True
    real_private_engine_running: bool = False
    live_trading_permitted: bool = False


class SignedGuardianController:
    """Control a Guardian *spawned by this controller*, never adopt random PIDs.

    The caller must provide live A12/A13 signed offline admission and A15
    independently pinned publisher release evidence for every start/renew.
    A Guardian does not know these keys; loss of renewals kills its worker
    after the short lease. Renewal is explicit in A18, not an auto loop.
    """

    def __init__(self, root: str | Path, *, signed: SignedMockDeploymentManager,
                 engine_id: str, installation_id: str,
                 lease_seconds: float = 0.8, heartbeat_seconds: float = 0.1,
                 a20_ci_scoped: bool = False):
        if not isinstance(signed, SignedMockDeploymentManager):
            raise GuardianRefused("A18_A15_SIGNED_FACADE_REQUIRED")
        if (type(engine_id) is not str or not _ID.fullmatch(engine_id)
                or type(installation_id) is not str
                or not _ID.fullmatch(installation_id)
                or signed._mock._engine_id != engine_id
                or signed._mock._installation_id != installation_id
                or signed._authority.engine_id != engine_id
                or signed._authority.installation_id != installation_id):
            raise GuardianRefused("A18_SIGNED_IDENTITY_MISMATCH")
        if (type(lease_seconds) not in (int, float)
                or type(heartbeat_seconds) not in (int, float)
                or not 0.35 <= lease_seconds <= 5.0
                or not 0.05 <= heartbeat_seconds <= lease_seconds / 2):
            raise GuardianRefused("A18_INVALID_BOUNDED_LEASE")
        base = Path(root)
        temp = Path(tempfile.gettempdir()).resolve()
        mock_root = signed._mock._root.resolve()
        if (not base.is_absolute() or base.is_symlink()
                or base.parent.is_symlink() or base.resolve() == temp
                or not base.resolve().is_relative_to(temp)
                or base.resolve() == mock_root
                or base.resolve().is_relative_to(mock_root)
                or mock_root.is_relative_to(base.resolve())):
            raise GuardianRefused("A18_TEMP_ISOLATED_ROOT_ONLY")
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not base.is_dir() or base.stat().st_mode & 0o077:
            raise GuardianRefused("A18_ROOT_PERMISSIONS")
        if type(a20_ci_scoped) is not bool:
            raise GuardianRefused("A20_PROFILE_MUST_BE_BOOL")
        if a20_ci_scoped:
            if (os.environ.get("GITHUB_ACTIONS") != "true"
                    or not os.environ.get("RUNNER_TEMP")
                    or os.geteuid() == 0
                    or not Path("/usr/bin/systemd-run").is_file()
                    or not Path("/usr/bin/sudo").is_file()):
                raise GuardianRefused("A20_EPHEMERAL_NONROOT_CI_ONLY")
        self._a20_ci_scoped = a20_ci_scoped
        self._root = base
        self._signed = signed
        self._lease = float(lease_seconds)
        self._heartbeat = float(heartbeat_seconds)
        self._child: subprocess.Popen | None = None
        self._token: str | None = None
        self._digest: str | None = None

    def _verify(self, *, admission, now: int) -> str:
        if type(now) is not int or now < 1:
            raise GuardianRefused("A18_TRUSTED_INTEGER_CLOCK_REQUIRED")
        base = self._signed._mock.status()
        if (base.state != "STOPPED" or base.owned_mock_worker_running
                or base.active is None or not _SHA.fullmatch(base.active)):
            raise GuardianRefused("A18_A14_MUST_BE_SIGNED_AND_STOPPED")
        record = self._signed._mock._admit(admission, now)
        manifest = self._signed._mock._verified_release(base.active, record)
        self._signed._authority.require_current(
            base.active, now=now, record=record, manifest=manifest)
        if manifest["mock_behavior"] != "healthy":
            raise GuardianRefused("A18_UNHEALTHY_FIXTURE_DENIED")
        return base.active

    def _control(self, cmd: str) -> GuardianStatus:
        if self._token is None or self._digest is None:
            raise GuardianRefused("A18_NO_OWNED_GUARDIAN_TOKEN")
        raw = json.dumps({"token": self._token, "cmd": cmd},
                         separators=(",", ":")).encode() + b"\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(1.8)
            try:
                channel.connect(str(self._root / "guardian.sock"))
                channel.sendall(raw)
                reply = b""
                while b"\n" not in reply and len(reply) <= 512:
                    chunk = channel.recv(513)
                    if not chunk:
                        break
                    reply += chunk
            except (OSError, TimeoutError) as exc:
                raise GuardianRefused("A18_GUARDIAN_CHANNEL_NOT_AVAILABLE") from exc
        if len(reply) > 512 or not reply.endswith(b"\n"):
            raise GuardianRefused("A18_UNBOUNDED_OR_TRUNCATED_RESPONSE")
        try:
            value = json.loads(reply)
        except (ValueError, UnicodeError) as exc:
            raise GuardianRefused("A18_GUARDIAN_RESPONSE_INVALID") from exc
        if not isinstance(value, dict) or "error" in value:
            raise GuardianRefused(
                "A18_GUARDIAN_REJECTED_" + str(value.get("error", "UNKNOWN"))[:80])
        if (set(value) != {"state", "revision", "worker_alive", "sandbox_verified",
                           "real_private_engine_running", "live_trading_permitted"}
                or value["state"] not in ("WAITING", "RUNNING", "STOPPED", "QUARANTINED")
                or type(value["revision"]) is not int
                or type(value["worker_alive"]) is not bool
                or type(value["sandbox_verified"]) is not bool
                or value["real_private_engine_running"] is not False
                or value["live_trading_permitted"] is not False):
            raise GuardianRefused("A18_GUARDIAN_STATUS_INVALID")
        guardian_live = self._child is not None and self._child.poll() is None
        return GuardianStatus(value["state"], value["revision"],
                              value["worker_alive"], guardian_live,
                              value["sandbox_verified"])

    def _persisted(self) -> dict | None:
        path = self._root / "guardian.json"
        if path.is_symlink():
            raise GuardianRefused("A18_STATE_SYMLINK")
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
            if len(raw) > 2048:
                raise ValueError("large")
            state = json.loads(raw)
        except (OSError, UnicodeError, ValueError) as exc:
            raise GuardianRefused("A18_CORRUPT_GUARDIAN_STATE") from exc
        if (type(state) is not dict
                or set(state) != {
                    "schema", "state", "revision", "digest", "worker_pid",
                    "guardian_pid", "sandbox_verified",
                    "real_private_engine_running", "live_trading_permitted"}
                or state["schema"] != 1
                or state["state"] not in (
                    "WAITING", "RUNNING", "STOPPED", "QUARANTINED",
                    "RECOVERED_STOPPED")
                or type(state["revision"]) is not int or state["revision"] < 0
                or type(state["digest"]) is not str
                or not _SHA.fullmatch(state["digest"])
                or state["real_private_engine_running"] is not False
                or state["live_trading_permitted"] is not False):
            raise GuardianRefused("A18_PERSISTED_STATE_INVALID")
        return state

    def launch(self, *, admission, now: int) -> GuardianStatus:
        if self._child is not None:
            raise GuardianRefused("A18_GUARDIAN_ALREADY_OWNED")
        digest = self._verify(admission=admission, now=now)
        previous = self._persisted()
        if previous is not None and previous["state"] != "RECOVERED_STOPPED":
            raise GuardianRefused("A18_EXPLICIT_RECONCILIATION_REQUIRED")
        token = secrets.token_hex(32)
        path = Path(__file__).with_name("a18_guardian.py").resolve()
        if self._a20_ci_scoped:
            # The systemd transient scope contains Guardian AND worker.
            # All cgroup controls are real and bounded on disposable CI.
            from .a20_hardening import MEM_MAX, MEM_HIGH, CPU_PERCENT, TASKS_MAX
            scope = "mmt-a20-" + secrets.token_hex(6)
            runner = pwd.getpwuid(os.geteuid()).pw_name
            if not runner or runner == "root":
                raise GuardianRefused("A20_SEPARATE_CI_OPERATOR_REQUIRED")
            command = [
                "/usr/bin/sudo", "-n", "/usr/bin/systemd-run", "--scope",
                "--unit=" + scope,
                "--property=MemoryMax=" + str(MEM_MAX),
                "--property=MemoryHigh=" + str(MEM_HIGH),
                "--property=CPUQuota=" + str(CPU_PERCENT) + "%",
                "--property=TasksMax=" + str(TASKS_MAX),
                "--", "/usr/bin/sudo", "-n", "-u", runner, "--",
                "/usr/bin/python3", "-I", "-S", "-u", str(path),
                str(self._root), digest, "0", str(self._lease),
                str(self._heartbeat), "offline_paper_a20_ci",
            ]
            child = subprocess.Popen(
                command, cwd=self._root,
                env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True,
                start_new_session=True,
            )
            try:
                if child.stdin is None:
                    raise GuardianRefused("A20_NO_PRIVATE_TOKEN_PIPE")
                child.stdin.write(token.encode("ascii"))
                child.stdin.flush()
            finally:
                if child.stdin is not None:
                    child.stdin.close()
        else:
            readfd, writefd = os.pipe()
            try:
                child = subprocess.Popen(
                    [sys.executable, "-I", "-S", "-u", str(path),
                     str(self._root), digest, str(readfd),
                     str(self._lease), str(self._heartbeat), "offline_paper_only"],
                    cwd=self._root, env={"PYTHONNOUSERSITE": "1"},
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True,
                    pass_fds=(readfd,), start_new_session=True,
                )
            finally:
                os.close(readfd)
            try:
                os.write(writefd, token.encode("ascii"))
            finally:
                os.close(writefd)
        self._child = child
        self._token = token
        self._digest = digest
        try:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise GuardianRefused("A18_INDEPENDENT_GUARDIAN_FAILED_STARTUP")
                if (self._root / "guardian.sock").is_socket():
                    try:
                        self._control("HELLO")
                        break
                    except GuardianRefused:
                        pass
                time.sleep(0.025)
            else:
                raise GuardianRefused("A18_GUARDIAN_STARTUP_TIMEOUT")
            started = self._control("START")
            if (started.state != "RUNNING" or not started.worker_alive
                    or not started.sandbox_verified):
                raise GuardianRefused("A18_UNVERIFIED_SANDBOX_START")
            if self._a20_ci_scoped:
                from .a20_hardening import verify_worker_report
                observed = self._persisted()
                if observed is None:
                    raise GuardianRefused("A20_MISSING_GUARDIAN_RECORD")
                verify_worker_report(self._root, observed["guardian_pid"])
            return GuardianStatus(started.state, started.revision,
                                  started.worker_alive, started.guardian_alive,
                                  started.sandbox_verified, True)
        except BaseException:
            self.close()
            raise

    def renew(self, *, admission, now: int) -> GuardianStatus:
        try:
            digest = self._verify(admission=admission, now=now)
            if digest != self._digest:
                raise GuardianRefused("A18_RELEASE_CHANGED_WITHIN_LEASE")
        except (ValueError, OSError):
            # Explicit fail-closed local revocation; independent Guardian
            # stops on monotonic lease expiry even when this caller dies.
            try:
                self._control("STOP")
            except GuardianRefused:
                pass
            raise
        if self._a20_ci_scoped:
            # Terminal leases must fail as NOT_RUNNING, not as alleged
            # attestation tampering because the terminated PID is gone.
            observed_status = self._control("HELLO")
            if observed_status.state != "RUNNING" or not observed_status.worker_alive:
                raise GuardianRefused("A18_GUARDIAN_REJECTED_A18_NOT_RUNNING")
            try:
                from .a20_hardening import verify_worker_report
                observed = self._persisted()
                if observed is None:
                    raise GuardianRefused("A20_MISSING_RENEW_GUARDIAN_RECORD")
                verify_worker_report(self._root, observed["guardian_pid"])
            except (ValueError, OSError):
                try:
                    self._control("STOP")
                except GuardianRefused:
                    pass
                raise
        state = self._control("RENEW")
        if (state.state != "RUNNING" or not state.worker_alive
                or not state.sandbox_verified):
            raise GuardianRefused("A18_RENEW_REQUIRES_LIVE_PROOF")
        return GuardianStatus(state.state, state.revision, state.worker_alive,
                              state.guardian_alive, state.sandbox_verified, True)

    def status(self) -> GuardianStatus:
        """Raw independent Guardian observation; NOT a fresh signed grant."""
        return self._control("HELLO")

    def stop(self) -> GuardianStatus:
        """Always available after A12/A15 revocation if Guardian still owns child."""
        return self._control("STOP")

    def crash_worker_for_test(self) -> GuardianStatus:
        return self._control("CRASH_TEST")

    def close(self) -> None:
        child = self._child
        if child is None:
            return
        try:
            try:
                self._control("SHUTDOWN")
            except GuardianRefused:
                pass
            try:
                child.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                # Only ever signal the Guardian process launched by this Popen.
                # Guardian owns its worker, so short TTL is the fallback.
                child.terminate()
                try:
                    child.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=1.0)
        finally:
            self._child = None
            self._token = None
            self._digest = None

    def reconcile_after_owner_exit(self, *, admission, now: int) -> str:
        """Explicit recovery after guardian lock is free; NEVER adopt a pid.

        Caller must still prove fresh signed A12-A15 admission. The guardian
        itself owns/kills worker before exit. This API only acknowledges the
        persisted terminal state; no subprocess is auto-restarted.
        """
        if self._child is not None:
            raise GuardianRefused("A18_OWNED_GUARDIAN_MUST_BE_CLOSED")
        self._verify(admission=admission, now=now)
        lock = self._root / "guardian.lock"
        if lock.is_symlink() or not lock.exists():
            raise GuardianRefused("A18_NO_PREVIOUS_GUARDIAN")
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise GuardianRefused("A18_GUARDIAN_STILL_OWNS_WORKER") from exc
            persisted = self._persisted()
            if persisted is None or persisted["state"] not in (
                "QUARANTINED", "STOPPED"):
                raise GuardianRefused("A18_TERMINAL_GUARDIAN_STATE_REQUIRED")
            if persisted["digest"] != self._signed._mock.status().active:
                raise GuardianRefused("A18_STALE_RELEASE_AFTER_GUARDIAN")
            persisted["state"] = "RECOVERED_STOPPED"
            persisted["revision"] += 1
            persisted["worker_pid"] = None
            persisted["guardian_pid"] = None
            persisted["sandbox_verified"] = False
            atomic_status(self._root / "guardian.json", persisted)
            return "RECOVERED_STOPPED"
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
