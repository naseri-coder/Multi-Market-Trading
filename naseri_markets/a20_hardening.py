"""A20 STRICT offline mock worker and verifiable disposable cgroup bounds.

This is public fixed Python only, not a private plugin launcher. Used exclusively
by the opt-in A18 guardian on an ephemeral GitHub Linux runner. No host
users, on-disk systemd service, production, database or live trades.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

MEM_MAX = 256 * 1024 * 1024
MEM_HIGH = 192 * 1024 * 1024
CPU_PERCENT = 50
TASKS_MAX = 16
SCOPE_PREFIX = "mmt-a20-"
_SCOPE = re.compile(r"mmt-a20-[0-9a-f]{12}\.scope\Z")
NONPRODUCTION_MARKER = "offline_paper_a20_ci"


class A20Refused(ValueError):
    """Hardened mock cannot run without verified cgroup/kernel evidence."""


@dataclass(frozen=True, slots=True)
class A20ScopeProof:
    relative_path: str
    memory_max: int
    memory_high: int
    cpu_quota_us: int
    cpu_period_us: int
    pids_max: int
    limits_enforced: bool
    private_strategy_executed: bool = False
    production_enabled: bool = False


def verify_scoped_pid(pid: int, *, sysroot: Path = Path("/sys/fs/cgroup")) -> A20ScopeProof:
    if type(pid) is not int or pid < 2:
        raise A20Refused("A20_INVALID_KERNEL_PID")
    try:
        mapping = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
        if len(mapping) != 1 or not mapping[0].startswith("0::"):
            raise A20Refused("A20_UNVERIFIED_CGROUP_V2")
        path = mapping[0][3:].strip()
        scope = path.rsplit("/", 1)[-1]
        if not _SCOPE.fullmatch(scope) or ".." in path or not path.startswith("/"):
            raise A20Refused("A20_WRONG_SYSTEMD_SCOPE")
        base = (sysroot / path.lstrip("/")).resolve()
        if not base.is_relative_to(sysroot.resolve()):
            raise A20Refused("A20_CGROUP_ESCAPE")
        def read(name: str) -> str:
            p = base / name
            if not p.is_file() or p.is_symlink():
                raise A20Refused("A20_UNAVAILABLE_CGROUP_CONTROL")
            raw = p.read_bytes()
            if len(raw) > 96:
                raise A20Refused("A20_OVERSIZED_CGROUP_VALUE")
            return raw.decode("ascii").strip()
        memory_max = int(read("memory.max"))
        memory_high = int(read("memory.high"))
        pids_max = int(read("pids.max"))
        cpu_quota, cpu_period = map(int, read("cpu.max").split())
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, A20Refused):
            raise
        raise A20Refused("A20_KERNEL_CGROUP_PROOF_UNAVAILABLE") from exc
    if (memory_max != MEM_MAX or memory_high != MEM_HIGH
            or pids_max != TASKS_MAX or cpu_period <= 0
            or cpu_quota <= 0 or cpu_quota * 100 != cpu_period * CPU_PERCENT):
        raise A20Refused("A20_CGROUP_ENFORCEMENT_MISMATCH")
    return A20ScopeProof(path, memory_max, memory_high, cpu_quota,
                         cpu_period, pids_max, True)


def verify_worker_report(root: Path, guardian_pid: int) -> dict:
    """Read-only proof; attestation file is not signed or a trust anchor."""
    file = root / "a20-kernel-report.json"
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 1500:
        raise A20Refused("A20_WORKER_PROOF_MISSING")
    try:
        report = json.loads(file.read_bytes())
        if (type(report) is not dict
                or set(report) != {"schema", "worker_pid", "worker_uid",
                                   "guardian_pid", "denied_socket",
                                   "denied_open", "denied_fork",
                                   "no_new_privs", "strict_seccomp",
                                   "cgroup_verified"}
                or report["schema"] != 1
                or report["guardian_pid"] != guardian_pid
                or type(report["worker_pid"]) is not int
                or type(report["worker_uid"]) is not int
                or report["worker_uid"] in (0, os.geteuid())
                or any(report[x] is not True for x in (
                    "denied_socket", "denied_open", "denied_fork",
                    "no_new_privs", "strict_seccomp", "cgroup_verified"))):
            raise A20Refused("A20_INVALID_WORKER_ATTESTATION")
        verify_scoped_pid(report["worker_pid"])
        return report
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, A20Refused):
            raise
        raise A20Refused("A20_MALFORMED_WORKER_ATTESTATION") from exc


# The fixed worker loads libseccomp and other Python modules BEFORE applying
# default-deny. Once installed, only a small allowlist supports stdin/out.
# It really tests socket(), os.open() and fork() returning EPERM.
STRICT_WORKER = r"""
import ctypes, errno, os, resource, socket, sys
token, digest = sys.argv[1:]
def must(condition):
    if not condition:
        os._exit(41)
uid = os.geteuid()
must(uid > 0)
resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
resource.setrlimit(resource.RLIMIT_NOFILE, (48, 48))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
fd = os.open('/proc/self/status', os.O_RDONLY)
libc = ctypes.CDLL(None, use_errno=True)
must(libc.prctl(38, 1, 0, 0, 0) == 0)
sc = ctypes.CDLL('libseccomp.so.2')
sc.seccomp_init.argtypes = [ctypes.c_uint32]
sc.seccomp_init.restype = ctypes.c_void_p
sc.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
sc.seccomp_syscall_resolve_name.restype = ctypes.c_int
sc.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
sc.seccomp_load.argtypes = [ctypes.c_void_p]
sc.seccomp_release.argtypes = [ctypes.c_void_p]
ctx = sc.seccomp_init(0x00050000 | errno.EPERM)
must(bool(ctx))
for name in (
    b'read', b'write', b'close', b'exit', b'exit_group', b'rt_sigreturn',
    b'rt_sigaction', b'rt_sigprocmask', b'brk', b'mmap', b'mprotect',
    b'munmap', b'mremap', b'clock_gettime', b'futex', b'lseek',
    b'fstat', b'newfstatat', b'getpid', b'gettid', b'getuid', b'geteuid',
    b'getrandom', b'ioctl', b'prlimit64', b'sched_yield'
):
    number = sc.seccomp_syscall_resolve_name(name)
    must(number >= 0)
    must(sc.seccomp_rule_add(ctx, 0x7fff0000, number, 0) == 0)
must(sc.seccomp_load(ctx) == 0)
sc.seccomp_release(ctx)
os.lseek(fd, 0, 0)
kernel = os.read(fd, 4096).decode('ascii')
os.close(fd)
must('NoNewPrivs:\t1' in kernel and 'Seccomp:\t2' in kernel)
try:
    socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    os._exit(43)
except OSError as exc:
    must(exc.errno == errno.EPERM)
try:
    os.open('/etc/passwd', os.O_RDONLY)
    os._exit(44)
except OSError as exc:
    must(exc.errno == errno.EPERM)
try:
    os.fork()
    os._exit(45)
except OSError as exc:
    must(exc.errno == errno.EPERM)
os.write(1, ('READY|' + token + '|' + digest
             + '|UID|' + str(uid) + '|PID|' + str(os.getpid())
             + '|NNP1|STRICT2|NET_OPEN_FORK_DENIED\n').encode())
for data in iter(lambda: os.read(0, 160), b''):
    if len(data) > 159 or b'\n' not in data or data.count(b'\n') != 1:
        break
    parts = data.rstrip(b'\n').decode('ascii', 'replace').split('|')
    if len(parts) != 4 or parts[1] != token or parts[2] != digest:
        break
    action, _, _, nonce = parts
    if not nonce.isdecimal() or len(nonce) > 16:
        break
    if action == 'PING':
        os.write(1, ('PONG|' + token + '|' + digest + '|' + nonce + '\n').encode())
    elif action == 'STOP':
        os.write(1, ('BYE|' + token + '|' + digest + '|' + nonce + '\n').encode())
        break
    elif action == 'CRASH_TEST':
        os._exit(23)
    else:
        break
"""
