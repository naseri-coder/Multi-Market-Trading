"""A23 ephemeral fixed sandbox relay and lifecycle for PUBLIC Custom PAPER data.

The only executable is this audited, deterministic Python relay string.
No third-party code, arbitrary imports, private engines, packaged binaries,
production services, host changes, live orders or remote connections.
The Linux profile is intentionally runnable only on disposable GitHub CI.
"""
from __future__ import annotations

import asyncio
import fcntl
import hmac
import os
import pwd
import re
import secrets
import select
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .a18_guardian import atomic_status
from .a20_hardening import CPU_PERCENT, MEM_HIGH, MEM_MAX, TASKS_MAX, verify_scoped_pid
from .a21_custom_contract import CustomContractCatalog, CustomEngineContract, inspect_custom_paper_fixture
from .a22_custom_bridge import CustomPaperRuntimeBridge, CustomRuntimeRefused
from .quotes import QuoteOrigin, QuoteTick

# A20 limits and pinned scope regex are reused verbatim; no new host controls.
_MAX_LINE = 16550
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{16}\Z")

# Static public Python fixture: BEFORE installing default-DENY seccomp it
# resolves libseccomp and opens /proc. It then proves real EPERM for network,
# filesystem opening and fork. Only stdin/stdout fixed byte relay is permitted.
# lease requires explicit heartbeat/relay; after owner crash, pipe EOF terminates.
FIXED_RELAY = r"""
import ctypes, errno, os, resource, select, socket, sys, time
def require(v):
    if not v:
        os._exit(63)
require(len(sys.argv) == 2 and sys.argv[1] == 'a23_fixed_paper_relay')
uid = os.geteuid()
require(uid > 0)
resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
resource.setrlimit(resource.RLIMIT_NOFILE, (48, 48))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
statusfd = os.open('/proc/self/status', os.O_RDONLY)
libc = ctypes.CDLL(None, use_errno=True)
require(libc.prctl(38, 1, 0, 0, 0) == 0)
sc = ctypes.CDLL('libseccomp.so.2')
sc.seccomp_init.argtypes = [ctypes.c_uint32]
sc.seccomp_init.restype = ctypes.c_void_p
sc.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
sc.seccomp_syscall_resolve_name.restype = ctypes.c_int
sc.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
sc.seccomp_load.argtypes = [ctypes.c_void_p]
sc.seccomp_release.argtypes = [ctypes.c_void_p]
ctx = sc.seccomp_init(0x00050000 | errno.EPERM)
require(bool(ctx))
for name in (
    b'read', b'write', b'close', b'exit', b'exit_group',
    b'rt_sigreturn', b'rt_sigaction', b'rt_sigprocmask', b'brk',
    b'mmap', b'mprotect', b'munmap', b'mremap', b'clock_gettime',
    b'futex', b'lseek', b'fstat', b'newfstatat', b'getpid', b'gettid',
    b'getuid', b'geteuid', b'getrandom', b'ioctl', b'prlimit64',
    b'sched_yield', b'pselect6', b'poll',
):
    num = sc.seccomp_syscall_resolve_name(name)
    require(num >= 0 and sc.seccomp_rule_add(ctx, 0x7fff0000, num, 0) == 0)
require(sc.seccomp_load(ctx) == 0)
sc.seccomp_release(ctx)
os.lseek(statusfd, 0, 0)
kernel = os.read(statusfd, 4096).decode('ascii')
os.close(statusfd)
require('NoNewPrivs:\t1' in kernel and 'Seccomp:\t2' in kernel)
try:
    socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    os._exit(64)
except OSError as exc:
    require(exc.errno == errno.EPERM)
try:
    os.open('/etc/passwd', os.O_RDONLY)
    os._exit(65)
except OSError as exc:
    require(exc.errno == errno.EPERM)
try:
    os.fork()
    os._exit(66)
except OSError as exc:
    require(exc.errno == errno.EPERM)
os.write(1, ('READY|' + str(os.getpid()) + '|' + str(uid)
             + '|NNP1|STRICT2|NETWORK_OPEN_FORK_DENIED\n').encode())
pending = b''
deadline = time.monotonic() + 3.0
while True:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        break
    if not select.select([0], [], [], remaining)[0]:
        break
    data = os.read(0, 4096)
    if not data:
        break
    pending += data
    if len(pending) > 16550:
        break
    while b'\n' in pending:
        line, pending = pending.split(b'\n', 1)
        if line == b'STOP':
            os.write(1, b'BYE\n')
            os._exit(0)
        if line == b'CRASH_TEST':
            os._exit(23)
        if line.startswith(b'PING|'):
            nonce = line[5:]
            if len(nonce) != 16 or any(x not in b'0123456789abcdef' for x in nonce):
                os._exit(67)
            os.write(1, b'PONG|' + nonce + b'\n')
        elif line.startswith(b'ECHO|'):
            parts = line.split(b'|')
            if len(parts) != 3:
                os._exit(68)
            nonce, encoded = parts[1:]
            if (len(nonce) != 16
                    or any(x not in b'0123456789abcdef' for x in nonce)
                    or not 0 < len(encoded) <= 16384
                    or len(encoded) % 2
                    or any(x not in b'0123456789abcdef' for x in encoded)):
                os._exit(69)
            os.write(1, b'OK|' + nonce + b'|' + encoded + b'\n')
        else:
            os._exit(70)
        deadline = time.monotonic() + 3.0
"""

class SandboxRefused(CustomRuntimeRefused):
    """Fixed child, kernel boundary, contract or lifecycle refused."""


@dataclass(frozen=True, slots=True)
class SandboxStatus:
    state: str
    revision: int
    engine_id: str
    scope_verified: bool
    worker_uid: int | None
    fixed_fixture_only: bool = True
    custom_code_executed: bool = False
    private_engine_loaded: bool = False
    live_trading_permitted: bool = False


def _receive(fd: int, *, timeout: float = 2.0) -> bytes:
    deadline = time.monotonic() + timeout
    pending = b""
    while b"\n" not in pending:
        if len(pending) > _MAX_LINE:
            raise SandboxRefused("A23_OVERSIZED_RESPONSE")
        left = deadline - time.monotonic()
        if left <= 0 or not select.select([fd], [], [], left)[0]:
            raise SandboxRefused("A23_SANDBOX_RESPONSE_TIMEOUT")
        part = os.read(fd, 4096)
        if not part:
            raise SandboxRefused("A23_SANDBOX_PIPE_CLOSED")
        pending += part
    line, rest = pending.split(b"\n", 1)
    if rest or len(line) > _MAX_LINE:
        raise SandboxRefused("A23_MULTIPLE_OR_OVERSIZED_REPLY")
    return line


class FixedCustomSandbox:
    """Exclusive ownership, explicit lifecycle and real scoped Linux worker.

    A23 does NOT accept executable paths or callbacks from Custom contracts.
    An A21 descriptor is *not* publisher authenticity or a license grant.
    """

    def __init__(self, root: str | Path, *,
                 catalog: CustomContractCatalog, contract: CustomEngineContract):
        if (type(catalog) is not CustomContractCatalog
                or type(contract) is not CustomEngineContract
                or contract.access_policy != "public_custom"
                or contract.protected_owner_core
                or contract.strategy_family != "generic_custom"
                or not _SHA.fullmatch(contract.approved_descriptor_sha256)
                or catalog.public_lookup(contract.engine_id) is None
                or contract not in catalog.owner_inventory()):
            raise SandboxRefused("A23_PUBLIC_GENERIC_PINNED_CONTRACT_REQUIRED")
        base = Path(root)
        temp = Path(tempfile.gettempdir()).resolve()
        if (not base.is_absolute() or base.is_symlink()
                or base.parent.is_symlink() or base.resolve() == temp
                or not base.resolve().is_relative_to(temp)):
            raise SandboxRefused("A23_TEMP_EXCLUSIVE_ROOT_ONLY")
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not base.is_dir() or base.stat().st_mode & 0o077:
            raise SandboxRefused("A23_UNSAFE_ROOT_PERMISSIONS")
        lockpath = base / "a23.lock"
        if lockpath.is_symlink():
            raise SandboxRefused("A23_UNSAFE_LOCK")
        fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise SandboxRefused("A23_EXISTING_SANDBOX_OWNER") from exc
        self._fd = fd
        self._root = base
        self._catalog = catalog
        self._contract = contract
        self._proc: subprocess.Popen | None = None
        self._pid: int | None = None
        self._uid: int | None = None
        self._revision = 0
        self._state = "NEW"
        self._io_lock = threading.Lock()
        self._blocked_previous = False
        previous = base / "a23.json"
        if previous.exists() or previous.is_symlink():
            if previous.is_symlink() or previous.stat().st_size > 1200:
                self._blocked_previous = True
            else:
                # Never adopt a PID from stale or untrusted persistent state.
                self._blocked_previous = True
        else:
            self._persist()

    def _persist(self) -> None:
        atomic_status(self._root / "a23.json", {
            "schema": 1, "engine_id": self._contract.engine_id,
            "descriptor_sha256": self._contract.approved_descriptor_sha256,
            "state": self._state, "revision": self._revision,
            "pid_observed_only": self._pid,
            "fixed_fixture_only": True,
            "custom_code_executed": False, "live_trading_permitted": False,
        })

    def status(self) -> SandboxStatus:
        if self._proc is not None and self._proc.poll() is not None and self._state == "RUNNING":
            self._state = "QUARANTINED"
            self._revision += 1
            self._persist()
        return SandboxStatus(self._state, self._revision,
                             self._contract.engine_id, self._state == "RUNNING",
                             self._uid)

    def _assure_live(self) -> None:
        if (self._state != "RUNNING" or self._proc is None
                or self._proc.poll() is not None or self._pid is None):
            raise SandboxRefused("A23_SANDBOX_NOT_RUNNING")
        try:
            proof = verify_scoped_pid(self._pid)
            status = Path(f"/proc/{self._pid}/status").read_text()
            if (not proof.limits_enforced
                    or "NoNewPrivs:\t1" not in status
                    or "Seccomp:\t2" not in status
                    or self._uid is None or self._uid <= 0
                    or self._uid == os.geteuid()):
                raise SandboxRefused("A23_KERNEL_PROFILE_CHANGED")
        except (OSError, ValueError) as exc:
            raise SandboxRefused("A23_KERNEL_ATTESTATION_FAILED") from exc

    def _exchange(self, command: bytes, *, expected: bytes | None = None) -> bytes:
        if len(command) > _MAX_LINE or b"\n" in command:
            raise SandboxRefused("A23_UNSAFE_COMMAND_LENGTH")
        with self._io_lock:
            self._assure_live()
            try:
                os.write(self._proc.stdin.fileno(), command + b"\n")
                response = _receive(self._proc.stdout.fileno())
                self._assure_live()
            except (OSError, ValueError) as exc:
                self._state = "QUARANTINED"
                self._revision += 1
                self._persist()
                raise SandboxRefused("A23_IPC_OR_KERNEL_FAILURE") from exc
            if expected is not None and not hmac.compare_digest(response, expected):
                self._state = "QUARANTINED"
                self._revision += 1
                self._persist()
                raise SandboxRefused("A23_RELAY_RESPONSE_MISMATCH")
            return response

    def launch(self, *, approved_sha256: str) -> SandboxStatus:
        if (self._state != "NEW" or self._blocked_previous or self._proc is not None):
            raise SandboxRefused("A23_EXPLICIT_RECOVERY_BEFORE_RELAUNCH")
        if (type(approved_sha256) is not str
                or not hmac.compare_digest(approved_sha256,
                                          self._contract.approved_descriptor_sha256)
                or self._catalog.public_lookup(self._contract.engine_id) is None):
            raise SandboxRefused("A23_FRESH_PUBLIC_PIN_REQUIRED")
        if (sys.platform != "linux" or os.geteuid() == 0
                or os.environ.get("GITHUB_ACTIONS") != "true"
                or not os.environ.get("RUNNER_TEMP")
                or not Path("/usr/bin/sudo").is_file()
                or not Path("/usr/bin/systemd-run").is_file()
                or not Path("/usr/bin/python3").is_file()):
            raise SandboxRefused("A23_DISPOSABLE_NONROOT_GITHUB_LINUX_ONLY")
        runner = pwd.getpwuid(os.geteuid()).pw_name
        if runner == "nobody":
            raise SandboxRefused("A23_DISTINCT_WORKER_UID_REQUIRED")
        scope = "mmt-a20-" + secrets.token_hex(6)
        command = [
            "/usr/bin/sudo", "-n", "/usr/bin/systemd-run", "--scope",
            "--unit=" + scope,
            "--property=MemoryMax=" + str(MEM_MAX),
            "--property=MemoryHigh=" + str(MEM_HIGH),
            "--property=CPUQuota=" + str(CPU_PERCENT) + "%",
            "--property=TasksMax=" + str(TASKS_MAX),
            "--", "/usr/bin/sudo", "-n", "-u", "nobody", "--",
            "/usr/bin/python3", "-I", "-S", "-u", "-c",
            FIXED_RELAY, "a23_fixed_paper_relay",
        ]
        self._proc = subprocess.Popen(
            command, cwd=self._root,
            env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        try:
            ready = _receive(self._proc.stdout.fileno(), timeout=3.0)
            fields = ready.decode("ascii").split("|")
            if (len(fields) != 6 or fields[0] != "READY"
                    or fields[3:] != ["NNP1", "STRICT2", "NETWORK_OPEN_FORK_DENIED"]):
                raise SandboxRefused("A23_NO_STRICT_KERNEL_READY")
            self._pid, self._uid = int(fields[1]), int(fields[2])
            self._state = "RUNNING"
            self._assure_live()
            self._revision += 1
            self._persist()
            self.heartbeat()
            return self.status()
        except BaseException:
            self._state = "QUARANTINED"
            self._revision += 1
            self._persist()
            self._stop_process()
            raise

    def heartbeat(self) -> SandboxStatus:
        nonce = secrets.token_hex(8).encode("ascii")
        self._exchange(b"PING|" + nonce, expected=b"PONG|" + nonce)
        return self.status()

    def relay(self, packet: bytes, *, tick: QuoteTick) -> bytes:
        if (type(packet) is not bytes or not 0 < len(packet) <= 8192
                or type(tick) is not QuoteTick
                or tick.origin not in (QuoteOrigin.REPLAY, QuoteOrigin.SYNTHETIC)):
            raise SandboxRefused("A23_PRECOMPUTED_PAPER_BYTES_REQUIRED")
        inspect_custom_paper_fixture(self._contract, packet, tick)
        nonce = secrets.token_hex(8).encode("ascii")
        encoded = packet.hex().encode("ascii")
        self._exchange(b"ECHO|" + nonce + b"|" + encoded,
                       expected=b"OK|" + nonce + b"|" + encoded)
        return packet

    async def dispatch(self, bridge: CustomPaperRuntimeBridge, packet: bytes,
                       *, tick: QuoteTick, expected_revision: int,
                       now) -> object:
        if type(bridge) is not CustomPaperRuntimeBridge:
            raise SandboxRefused("A23_A22_BRIDGE_REQUIRED")
        state = bridge.status(self._contract.engine_id)
        if (not state.enabled or not bridge._paper_enabled
                or type(expected_revision) is not int
                or state.revision != expected_revision
                or state.descriptor_sha256 != self._contract.approved_descriptor_sha256):
            raise SandboxRefused("A23_A22_PERMISSION_OR_PIN_DENIED")
        relay = await asyncio.to_thread(self.relay, packet, tick=tick)
        current = bridge.status(self._contract.engine_id)
        if (not current.enabled or not bridge._paper_enabled
                or current.revision != expected_revision):
            raise SandboxRefused("A23_PERMISSION_CHANGED_DURING_SANDBOX")
        return await bridge.dispatch(
            tick, packets={self._contract.engine_id: relay},
            expected_revisions={self._contract.engine_id: expected_revision}, now=now)

    def crash_for_test(self) -> SandboxStatus:
        try:
            self._exchange(b"CRASH_TEST")
        except SandboxRefused:
            pass
        self._state = "QUARANTINED"
        self._revision += 1
        self._persist()
        return self.status()

    def _stop_process(self):
        child = self._proc
        if child is None:
            return
        try:
            if child.stdin is not None and not child.stdin.closed:
                child.stdin.close()  # Worker MUST exit on EOF.
            try:
                child.wait(timeout=2.5)
            except subprocess.TimeoutExpired:
                # Only terminate the EXACT Popen that this owner spawned.
                child.terminate()
                try:
                    child.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=1.0)
        finally:
            if child.stdout is not None:
                child.stdout.close()
            self._proc = None
            self._pid = None
            self._uid = None

    def stop(self) -> SandboxStatus:
        if self._state == "RUNNING" and self._proc is not None:
            try:
                self._exchange(b"STOP", expected=b"BYE")
            except SandboxRefused:
                pass
        self._stop_process()
        self._state = "STOPPED"
        self._revision += 1
        self._persist()
        return self.status()

    def reconcile(self, *, approved_sha256: str) -> SandboxStatus:
        """Manual local reset only after owned child is fully stopped.

        Stale persisted state from a previous owner is NOT silently adopted
        or reset. Separate operator remediation is needed after owner loss.
        """
        if (self._proc is not None or self._blocked_previous
                or self._state not in ("STOPPED", "QUARANTINED")
                or type(approved_sha256) is not str
                or not hmac.compare_digest(approved_sha256,
                                          self._contract.approved_descriptor_sha256)):
            raise SandboxRefused("A23_RECONCILIATION_DENIED")
        self._state = "NEW"
        self._revision += 1
        self._persist()
        return self.status()

    def close(self) -> None:
        try:
            if self._proc is not None:
                self.stop()
        finally:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                self._fd = None
