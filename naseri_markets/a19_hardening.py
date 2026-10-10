"""A19 offline Linux hardening rehearsal: real UID/seccomp probe + unit preview.

NEVER executes a private engine, deploys a service, changes host users, writes
cgroup controllers or installs systemd units. All subprocesses are fixed,
inert, CI-only fixtures. cgroup policy is PREPARED, not activated.
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

C_GROUPS = frozenset({"cpu", "memory", "pids"})
PROBE_UID_NAME = "nobody"
UNIT_BASENAME = "multi-market-trading-a19-fixture.service"

# Static Python snippet executed by /usr/bin/python3 as the *independent*
# low-privilege user on an ephemeral CI runner. It does not execute packages.
# For this inert probe only, a libseccomp DEFAULT-ERRNO filter is installed.
STRICT_PROBE = r"""
import ctypes, errno, json, os, resource, socket, sys
uid = os.geteuid()
if uid == 0:
    os._exit(60)
resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
resource.setrlimit(resource.RLIMIT_NOFILE, (48, 48))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
statusfd = os.open('/proc/self/status', os.O_RDONLY)
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(38, 1, 0, 0, 0) != 0:
    os._exit(61)
sc = ctypes.CDLL('libseccomp.so.2')
sc.seccomp_init.argtypes = [ctypes.c_uint32]
sc.seccomp_init.restype = ctypes.c_void_p
sc.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
sc.seccomp_syscall_resolve_name.restype = ctypes.c_int
sc.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
sc.seccomp_load.argtypes = [ctypes.c_void_p]
sc.seccomp_release.argtypes = [ctypes.c_void_p]
# SCMP_ACT_ERRNO(EPERM): every syscall is forbidden unless explicitly ALLOW.
ctx = sc.seccomp_init(0x00050000 | errno.EPERM)
if not ctx:
    os._exit(62)
for name in (
    b'read', b'write', b'close', b'exit', b'exit_group',
    b'rt_sigreturn', b'rt_sigaction', b'rt_sigprocmask',
    b'brk', b'mmap', b'mprotect', b'munmap', b'mremap',
    b'clock_gettime', b'futex', b'lseek', b'fstat', b'newfstatat',
    b'getpid', b'gettid', b'getuid', b'geteuid', b'getrandom',
    b'ioctl', b'prlimit64', b'sched_yield',
):
    number = sc.seccomp_syscall_resolve_name(name)
    if number < 0 or sc.seccomp_rule_add(ctx, 0x7fff0000, number, 0) != 0:
        os._exit(63)
if sc.seccomp_load(ctx) != 0:
    os._exit(64)
sc.seccomp_release(ctx)
os.lseek(statusfd, 0, 0)
kernel = os.read(statusfd, 4096).decode('ascii')
os.close(statusfd)
checks = {}
try:
    socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    checks['socket_denied'] = False
except OSError as exc:
    checks['socket_denied'] = exc.errno == errno.EPERM
try:
    os.open('/etc/passwd', os.O_RDONLY)
    checks['open_denied'] = False
except OSError as exc:
    checks['open_denied'] = exc.errno == errno.EPERM
try:
    os.fork()
    checks['fork_denied'] = False
except OSError as exc:
    checks['fork_denied'] = exc.errno == errno.EPERM
checks['no_new_privs'] = 'NoNewPrivs:\t1' in kernel
checks['seccomp_filter'] = 'Seccomp:\t2' in kernel
checks['uid_nonroot'] = uid > 0
if not all(checks.values()):
    os._exit(65)
sys.stdout.write(json.dumps({'uid': uid, 'checks': checks}, sort_keys=True) + '\n')
sys.stdout.flush()
"""


class HardeningRefused(ValueError):
    """A19 hardening policy cannot be proven or is outside ephemeral CI."""


@dataclass(frozen=True, slots=True)
class StrictFixtureProof:
    uid: int
    required_uid: int
    no_new_privs: bool
    seccomp_default_deny: bool
    socket_denied: bool
    file_open_denied: bool
    fork_denied: bool
    real_private_engine_running: bool = False
    live_trading_permitted: bool = False


@dataclass(frozen=True, slots=True)
class CgroupReadiness:
    cgroup_v2_seen: bool
    available_controllers: frozenset[str]
    required_controllers_present: bool
    limits_enforced: bool = False


def cgroup_readiness(root: str | Path = "/sys/fs/cgroup") -> CgroupReadiness:
    """Read-only capability observation. No cgroup tree is created or changed."""
    root = Path(root)
    path = root / "cgroup.controllers"
    if not path.is_file() or path.is_symlink():
        return CgroupReadiness(False, frozenset(), False)
    try:
        raw = path.read_bytes()
        if len(raw) > 4096:
            raise HardeningRefused("A19_CGROUP_STATUS_OVERSIZE")
        names = frozenset(raw.decode("ascii").split())
        if any(not re.fullmatch(r"[a-z_]+", name) for name in names):
            raise HardeningRefused("A19_CGROUP_STATUS_INVALID")
    except (OSError, UnicodeError) as exc:
        raise HardeningRefused("A19_CGROUP_READ_FAILED") from exc
    return CgroupReadiness(True, names, C_GROUPS.issubset(names), False)


def systemd_fixture_unit() -> str:
    """Nonactivatable preview of future separate-UID/cgroup service policy."""
    return """# Multi Market Trading / A19 — disposable NON-PRODUCTION fixture policy
# Offline preview only; NEVER install or enable without separate authorization.
[Unit]
Description=Multi Market Trading A19 inert hardening fixture (offline)
ConditionPathExists=/run/mmt-a19-explicit-test-authorization-never-created
RefuseManualStart=yes
StartLimitBurst=1

[Service]
Type=exec
DynamicUser=yes
User=mmt-a19-fixture
Group=mmt-a19-fixture
RuntimeDirectory=mmt-a19-fixture
RuntimeDirectoryMode=0700
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
PrivateNetwork=yes
RestrictAddressFamilies=AF_UNIX
IPAddressDeny=any
PrivateDevices=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectHostname=yes
ProtectClock=yes
ProtectProc=invisible
ProtectKernelLogs=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
RemoveIPC=yes
DevicePolicy=closed
SystemCallArchitectures=native
SystemCallFilter=@system-service ~@network-io ~@privileged
SystemCallErrorNumber=EPERM
MemoryMax=256M
MemoryHigh=192M
CPUQuota=50%
TasksMax=8
LimitNOFILE=48
LimitCORE=0
Restart=no
ExecStart=/usr/bin/python3 -I -S -u -c 'print("A19_INERT_FIXTURE_ONLY")'
StandardInput=null
StandardOutput=null
StandardError=null

[Install]
# Intentionally no WantedBy; this unit is never automatically enabled.
"""


def export_offline_unit(destination: str | Path) -> tuple[Path, str]:
    """Write 0600 preview exclusively under /tmp; never install to /etc."""
    root = Path(destination)
    temp = Path(tempfile.gettempdir()).resolve()
    if (not root.is_absolute() or root.is_symlink()
            or root.parent.is_symlink() or root.resolve() == temp
            or not root.resolve().is_relative_to(temp)
            or root.resolve().is_relative_to(Path("/etc"))
            or root.resolve().is_relative_to(Path("/run/systemd"))):
        raise HardeningRefused("A19_DISPOSABLE_PREVIEW_ONLY")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir() or root.stat().st_mode & 0o077:
        raise HardeningRefused("A19_UNSAFE_PREVIEW_DIRECTORY")
    unit = root / UNIT_BASENAME
    if unit.exists() or unit.is_symlink():
        raise HardeningRefused("A19_PREVIEW_MUST_BE_NEW")
    content = systemd_fixture_unit().encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    fd = os.open(unit, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        unit.unlink(missing_ok=True)
        raise
    return unit, digest


def validate_offline_unit(unit: str | Path) -> str:
    path = Path(unit)
    if (not path.is_absolute() or not path.is_file() or path.is_symlink()
            or path.name != UNIT_BASENAME
            or not path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
            or path.read_bytes() != systemd_fixture_unit().encode()):
        raise HardeningRefused("A19_UNIT_MUST_MATCH_FROZEN_PREVIEW")
    result = subprocess.run(
        ["/usr/bin/systemd-analyze", "verify", str(path)],
        capture_output=True, text=True, timeout=8.0, check=False,
    )
    if result.returncode != 0:
        raise HardeningRefused("A19_SYSTEMD_VERIFY_FAILED: " + result.stderr[-280:])
    return "A19_SYSTEMD_SYNTAX_VERIFIED_NOT_ACTIVATED"


def run_separate_uid_kernel_probe() -> StrictFixtureProof:
    """Ephemeral GitHub Actions runner ONLY; sudo -n as pre-existing nobody.

    No system users/groups, files, cgroups, services or host policies changed.
    Fail closed rather than silently substituting an unprivileged same-uid
    process. The static child is NOT a private core or signed release.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise HardeningRefused("A19_GITHUB_EPHEMERAL_RUNNER_REQUIRED")
    if sys.platform != "linux":
        raise HardeningRefused("A19_LINUX_REQUIRED")
    uid = pwd.getpwnam(PROBE_UID_NAME).pw_uid
    if uid == 0 or uid == os.geteuid():
        raise HardeningRefused("A19_DISTINCT_NONROOT_UID_REQUIRED")
    if not Path("/usr/bin/sudo").is_file() or not Path("/usr/bin/python3").is_file():
        raise HardeningRefused("A19_REQUIRED_CI_TOOLS_MISSING")
    command = ["/usr/bin/sudo", "-n", "-u", PROBE_UID_NAME, "--",
               "/usr/bin/python3", "-I", "-S", "-u", "-c", STRICT_PROBE]
    try:
        run = subprocess.run(
            command, capture_output=True, timeout=7.0, check=False,
            env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HardeningRefused("A19_UNPRIVILEGED_KERNEL_PROBE_UNAVAILABLE") from exc
    if run.returncode != 0 or len(run.stdout) > 1024:
        raise HardeningRefused("A19_KERNEL_ISOLATION_PROBE_FAILED: "
                              + run.stderr[:240].decode("utf8", "replace"))
    try:
        report = json.loads(run.stdout)
        checks = report["checks"]
        expected_checks = {"socket_denied", "open_denied", "fork_denied",
                           "no_new_privs", "seccomp_filter", "uid_nonroot"}
        if (type(report) is not dict or set(report) != {"uid", "checks"}
                or report["uid"] != uid or type(checks) is not dict
                or set(checks) != expected_checks
                or any(value is not True for value in checks.values())):
            raise ValueError("false kernel proof")
    except (ValueError, KeyError, TypeError) as exc:
        raise HardeningRefused("A19_INVALID_KERNEL_PROOF") from exc
    return StrictFixtureProof(uid, uid, True, True, True, True, True)
