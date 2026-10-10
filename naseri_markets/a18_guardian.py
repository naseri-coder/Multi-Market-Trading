"""A18 standalone Linux-only *synthetic* guardian executable.

This file is run by path with Python -I -S. It intentionally does not import
Multi Market Trading or private strategy code. All payloads are inert fixture
strings. It is NOT an untrusted binary sandbox or a production service.
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import hmac
import json
import os
import re
import secrets
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{64}\Z")

# These rules actually execute in the child. They are supplemental syscall
# denials, NOT a complete default-deny seccomp profile or privilege separation.
WORKER = r"""
import ctypes, errno, os, resource, socket, sys
token, digest = sys.argv[1:]
def must(condition):
    if not condition:
        os._exit(41)
resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
resource.setrlimit(resource.RLIMIT_NOFILE, (48, 48))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
libc = ctypes.CDLL(None, use_errno=True)
must(libc.prctl(38, 1, 0, 0, 0) == 0)  # PR_SET_NO_NEW_PRIVS
sc = ctypes.CDLL('libseccomp.so.2', use_errno=True)
sc.seccomp_init.argtypes = [ctypes.c_uint32]
sc.seccomp_init.restype = ctypes.c_void_p
sc.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
sc.seccomp_syscall_resolve_name.restype = ctypes.c_int
sc.seccomp_rule_add.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint,
]
sc.seccomp_load.argtypes = [ctypes.c_void_p]
sc.seccomp_release.argtypes = [ctypes.c_void_p]
ctx = sc.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW
must(bool(ctx))
for name in (
    b'socket', b'socketpair', b'connect', b'bind', b'listen', b'accept',
    b'accept4', b'sendto', b'recvfrom', b'sendmsg', b'recvmsg',
    b'execve', b'execveat', b'ptrace', b'mount', b'umount2',
    b'fork', b'vfork', b'clone', b'clone3', b'bpf', b'keyctl'
):
    number = sc.seccomp_syscall_resolve_name(name)
    if number >= 0:
        must(sc.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0) == 0)
must(sc.seccomp_load(ctx) == 0)
sc.seccomp_release(ctx)
try:
    socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    os._exit(43)
except OSError as exc:
    must(exc.errno == errno.EPERM)
with open('/proc/self/status', 'rt') as fd:
    status = fd.read()
must('NoNewPrivs:\t1' in status)
must('Seccomp:\t2' in status)
sys.stdout.write('READY|' + token + '|' + digest + '|NNP1|SECCOMP2|NET_DENIED\n')
sys.stdout.flush()
for raw in sys.stdin.buffer:
    if len(raw) > 160:
        break
    parts = raw.rstrip(b'\n').decode('ascii', 'replace').split('|')
    if len(parts) != 4 or parts[1] != token or parts[2] != digest:
        break
    action, _, _, nonce = parts
    if not nonce.isdecimal() or len(nonce) > 16:
        break
    if action == 'PING':
        sys.stdout.write('PONG|' + token + '|' + digest + '|' + nonce + '\n')
    elif action == 'STOP':
        sys.stdout.write('BYE|' + token + '|' + digest + '|' + nonce + '\n')
        sys.stdout.flush()
        break
    elif action == 'CRASH_TEST':
        os._exit(23)
    else:
        break
    sys.stdout.flush()
"""


def atomic_status(path: Path, value: dict):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > 2048:
        raise ValueError("A18_OVERSIZED_GUARDIAN_STATE")
    temp = path.with_name(".a18-" + secrets.token_hex(8))
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if temp.exists():
            temp.unlink()


def receive(fd: int, *, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    pending = b""
    while b"\n" not in pending:
        if len(pending) > 200:
            raise ValueError("A18_BAD_FRAME")
        remain = deadline - time.monotonic()
        if remain <= 0 or not select.select([fd], [], [], remain)[0]:
            raise ValueError("A18_WORKER_TIMEOUT")
        chunk = os.read(fd, 220)
        if not chunk:
            raise ValueError("A18_WORKER_EOF")
        pending += chunk
    if len(pending) > 200 or pending.count(b"\n") != 1:
        raise ValueError("A18_BAD_WORKER_FRAME")
    return pending[:-1].decode("ascii")


class Guardian:
    def __init__(self, root: Path, digest: str, secret: str, ttl: float,
                 heartbeat: float):
        temp = Path(tempfile.gettempdir()).resolve()
        if (not root.is_absolute() or root.is_symlink()
                or root.resolve() == temp
                or not root.resolve().is_relative_to(temp)
                or not root.is_dir() or root.stat().st_mode & 0o077
                or not SHA.fullmatch(digest)
                or len(secret) != 64 or not SHA.fullmatch(secret)
                or not 0.35 <= ttl <= 5.0
                or not 0.05 <= heartbeat <= ttl / 2):
            raise ValueError("A18_INVALID_GUARDIAN_START")
        self.root = root
        self.digest = digest
        self.secret = secret
        self.ttl = ttl
        self.heartbeat = heartbeat
        self.socket_path = root / "guardian.sock"
        self.state_path = root / "guardian.json"
        lock_path = root / "guardian.lock"
        self.lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if self.socket_path.is_symlink():
            raise ValueError("A18_UNSAFE_SOCKET")
        if self.socket_path.exists():
            self.socket_path.unlink()  # lock guarantees no other guardian owner
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        self.server.listen(4)
        self.server.setblocking(False)
        self.child: subprocess.Popen | None = None
        self.child_token = secrets.token_hex(16)
        self.nonce = 0
        self.state = "WAITING"
        self.revision = 0
        self.lease_until: float | None = None
        self.started = time.monotonic()
        self.last_pulse = self.started
        self.quit = False
        self.persist()

    def persist(self):
        atomic_status(self.state_path, {
            "schema": 1, "state": self.state, "revision": self.revision,
            "digest": self.digest,
            "worker_pid": self.child.pid if self.child is not None else None,
            "guardian_pid": os.getpid(),
            "sandbox_verified": self.state == "RUNNING",
            "real_private_engine_running": False, "live_trading_permitted": False,
        })

    def transition(self, state):
        self.state = state
        self.revision += 1
        self.persist()

    def ask_worker(self, action):
        child = self.child
        if child is None or child.poll() is not None or child.stdin is None:
            raise ValueError("A18_CHILD_EXITED")
        self.nonce += 1
        seq = str(self.nonce)
        child.stdin.write((action + "|" + self.child_token + "|"
                          + self.digest + "|" + seq + "\n").encode())
        child.stdin.flush()
        kind = "PONG" if action == "PING" else "BYE"
        expected = kind + "|" + self.child_token + "|" + self.digest + "|" + seq
        if receive(child.stdout.fileno(), timeout=0.7) != expected:
            raise ValueError("A18_BAD_HEARTBEAT")

    def halt(self):
        child, self.child = self.child, None
        if child is not None:
            try:
                if child.poll() is None:
                    try:
                        # The guardian only signals the Popen child it spawned.
                        self.child = child
                        self.ask_worker("STOP")
                    except (OSError, ValueError, BrokenPipeError):
                        pass
                    finally:
                        self.child = None
                if child.stdin:
                    child.stdin.close()
                try:
                    child.wait(timeout=0.8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=1.0)
                if child.stdout:
                    child.stdout.close()
            finally:
                self.child = None

    def start_worker(self):
        if self.state != "WAITING":
            raise ValueError("A18_NOT_WAITING")
        self.child = subprocess.Popen(
            [sys.executable, "-I", "-S", "-u", "-c", WORKER,
             self.child_token, self.digest],
            cwd=self.root, env={"PYTHONNOUSERSITE": "1"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True,
        )
        try:
            expected = ("READY|" + self.child_token + "|" + self.digest
                        + "|NNP1|SECCOMP2|NET_DENIED")
            if receive(self.child.stdout.fileno(), timeout=1.2) != expected:
                raise ValueError("A18_SANDBOX_ATTESTATION_FAILED")
            self.ask_worker("PING")
        except BaseException:
            self.halt()
            self.transition("QUARANTINED")
            raise
        self.lease_until = time.monotonic() + self.ttl
        self.last_pulse = time.monotonic()
        self.transition("RUNNING")

    def _commands(self, conn):
        try:
            peer = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            import struct
            _, uid, _ = struct.unpack("3i", peer)
            if uid != os.getuid():
                return {"error": "A18_PEER_UID_REJECTED"}
            conn.settimeout(0.5)
            raw = b""
            while b"\n" not in raw and len(raw) <= 400:
                block = conn.recv(401)
                if not block:
                    break
                raw += block
            if len(raw) > 400 or not raw.endswith(b"\n"):
                return {"error": "A18_BAD_CONTROL_FRAME"}
            request = json.loads(raw[:-1])
            if (type(request) is not dict or set(request) != {"token", "cmd"}
                    or type(request["token"]) is not str
                    or not hmac.compare_digest(request["token"], self.secret)
                    or request["cmd"] not in (
                        "HELLO", "START", "RENEW", "STOP", "SHUTDOWN", "CRASH_TEST",
                    )):
                return {"error": "A18_CONTROL_AUTH_FAILED"}
            cmd = request["cmd"]
            if cmd == "START":
                self.start_worker()
            elif cmd == "RENEW":
                if self.state != "RUNNING":
                    raise ValueError("A18_NOT_RUNNING")
                # Important: independent guardian does not trust persisted PID;
                # it probes the actual owned child before extending the lease.
                self.ask_worker("PING")
                self.lease_until = time.monotonic() + self.ttl
            elif cmd == "CRASH_TEST":
                if self.state != "RUNNING":
                    raise ValueError("A18_NOT_RUNNING")
                self.child.kill()
                self.child.wait(timeout=0.5)
            elif cmd in ("STOP", "SHUTDOWN"):
                self.halt()
                if self.state not in ("STOPPED", "QUARANTINED"):
                    self.transition("STOPPED")
                if cmd == "SHUTDOWN":
                    self.quit = True
            return {
                "state": self.state, "revision": self.revision,
                "worker_alive": self.child is not None and self.child.poll() is None,
                "sandbox_verified": self.state == "RUNNING",
                "real_private_engine_running": False,
                "live_trading_permitted": False,
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"error": str(exc)[:96]}

    def run(self):
        try:
            # Parent may terminate abruptly; lease countdown is monotonic and
            # owned by this separate process, never by a parent-side thread.
            while not self.quit:
                now = time.monotonic()
                if self.state == "RUNNING":
                    if self.lease_until is None or now >= self.lease_until:
                        self.halt()
                        self.transition("QUARANTINED")
                    elif now - self.last_pulse >= self.heartbeat:
                        try:
                            self.ask_worker("PING")
                            self.last_pulse = time.monotonic()
                        except (OSError, ValueError, BrokenPipeError):
                            self.halt()
                            self.transition("QUARANTINED")
                # On loss of manager, exit safely after quarantine grace.
                if (self.state in ("WAITING", "QUARANTINED", "STOPPED")
                        and time.monotonic() - self.started > 6.0):
                    break
                ready = select.select([self.server], [], [], 0.025)[0]
                if ready:
                    conn, _ = self.server.accept()
                    with conn:
                        response = self._commands(conn)
                        try:
                            conn.sendall((json.dumps(response, sort_keys=True) + "\n").encode())
                        except OSError:
                            pass
        finally:
            self.halt()
            self.server.close()
            if self.socket_path.exists() and not self.socket_path.is_symlink():
                self.socket_path.unlink()
            os.close(self.lock_fd)


def main():
    if len(sys.argv) != 7:
        raise SystemExit("A18_FIXTURE_ARGS_REQUIRED")
    _, base, digest, secret_fd, ttl, interval, _marker = sys.argv
    if _marker != "offline_paper_only":
        raise SystemExit("A18_FIXTURE_ONLY")
    try:
        fd = int(secret_fd)
        secret = os.read(fd, 64).decode("ascii")
        os.close(fd)
        owner = Guardian(Path(base), digest, secret, float(ttl), float(interval))
        owner.run()
    except (OSError, ValueError, BlockingIOError):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
