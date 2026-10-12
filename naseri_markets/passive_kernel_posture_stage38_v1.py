"""Stage38: opt-in, read-only *self-process* Linux kernel posture observation.

This does NOT prove real firewall enforcement or gVisor confinement of a
different process/container, and it cannot authenticate an untrusted host.
It performs no command execution, no network connection, and no filesystem
writes. Never execute on a production machine or an undesignated host.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import asdict, dataclass

from .a24_publisher_admission import canonical
from .designated_host_readonly_probe_stage34_v1 import (
    Stage34Refused, _approved_host,
)

_PATHS = (
    "/proc/self/status",
    "/proc/self/mountinfo",
    "/proc/self/net/route",
    "/proc/self/net/ipv6_route",
)
_LIMITS = (32768, 131072, 32768, 32768)
_HEX = re.compile(r"[0-9A-Fa-f]+\Z")
_REQUIRED_STATUS = frozenset({
    "Uid", "Gid", "CapInh", "CapPrm", "CapEff",
    "CapBnd", "CapAmb", "NoNewPrivs", "Seccomp",
})


class Stage38Refused(ValueError):
    """Sanitized denial, never expose raw procfs or machine secrets."""


def _read_fixed_proc(path: str, *, limit: int) -> bytes:
    if path not in _PATHS or limit != _LIMITS[_PATHS.index(path)]:
        raise Stage38Refused("ONLY_FIXED_BOUNDED_LINUX_PROCFS_ALLOWED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as fp:
            raw = fp.read(limit + 1)
    except OSError as exc:
        raise Stage38Refused("FIXED_KERNEL_PROCFS_SNAPSHOT_UNAVAILABLE") from exc
    if not 1 <= len(raw) <= limit:
        raise Stage38Refused("MISSING_OR_EXCESSIVE_PROCFS_SNAPSHOT")
    return raw


def _lines(raw: bytes, *, limit: int) -> list[str]:
    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        raise Stage38Refused("BOUNDED_PROCFS_BYTES_REQUIRED")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise Stage38Refused("NONASCII_PROCFS_SNAPSHOT") from exc
    if not 1 <= len(lines) <= 2048:
        raise Stage38Refused("EXCESSIVE_PROCFS_RECORDS")
    return lines


def _identity_quad(value: str) -> int:
    chunks = value.split()
    if len(chunks) != 4 or any(not part.isascii()
                              or not part.isdecimal() for part in chunks):
        raise Stage38Refused("UNTRUSTED_PROCESS_IDENTITY")
    nums = tuple(int(x) for x in chunks)
    if not 0 < nums[0] == nums[1] == nums[2] == nums[3]:
        raise Stage38Refused("ROOT_OR_SPLIT_PROCESS_IDENTITY")
    return nums[0]


def _status(raw: bytes, *, expected_uid: int, expected_gid: int) -> None:
    records: dict[str, str] = {}
    for line in _lines(raw, limit=32768):
        if ":" not in line:
            raise Stage38Refused("MALFORMED_PROC_STATUS")
        name, value = line.split(":", 1)
        if name in _REQUIRED_STATUS or name == "Seccomp_filters":
            if name in records:
                raise Stage38Refused("DUPLICATE_PROC_SECURITY_PROPERTY")
            records[name] = value.strip()
    if not _REQUIRED_STATUS.issubset(records):
        raise Stage38Refused("INCOMPLETE_PROCESS_SECURITY_STATUS")
    if (_identity_quad(records["Uid"]) != expected_uid
            or _identity_quad(records["Gid"]) != expected_gid):
        raise Stage38Refused("PROCESS_IDENTITY_DOES_NOT_MATCH_HOST_CALLER")
    for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        value = records[name]
        if (not 1 <= len(value) <= 16
                or not _HEX.fullmatch(value) or int(value, 16) != 0):
            raise Stage38Refused("PROCESS_HAS_LINUX_CAPABILITY")
    if records["NoNewPrivs"] != "1" or records["Seccomp"] != "2":
        raise Stage38Refused("PROCESS_NO_NEW_PRIVS_OR_SECCOMP_NOT_ENFORCED")
    if "Seccomp_filters" in records:
        n = records["Seccomp_filters"]
        if not n.isascii() or not n.isdecimal() or not 1 <= int(n) <= 64:
            raise Stage38Refused("SECCOMP_FILTER_OBSERVATION_INVALID")


def _root_mount(raw: bytes) -> None:
    matches = 0
    for line in _lines(raw, limit=131072):
        left, sep, right = line.partition(" - ")
        cols = left.split()
        if not sep or len(cols) < 6 or len(right.split()) < 3:
            raise Stage38Refused("MALFORMED_MOUNTINFO_RECORD")
        if cols[4] == "/":
            matches += 1
            flags = cols[5].split(",")
            if "ro" not in flags or "rw" in flags:
                raise Stage38Refused("SELF_ROOT_FILESYSTEM_NOT_READ_ONLY")
    if matches != 1:
        raise Stage38Refused("UNAMBIGUOUS_SELF_ROOT_MOUNT_REQUIRED")


def _routes4(raw: bytes) -> int:
    lines = _lines(raw, limit=32768)
    columns = lines[0].split()
    if (len(columns) != 11 or columns[:4] !=
            ["Iface", "Destination", "Gateway", "Flags"]):
        raise Stage38Refused("MISSING_IPV4_ROUTE_HEADER")
    count = 0
    for line in lines[1:]:
        cols = line.split()
        if len(cols) != 11:
            raise Stage38Refused("MALFORMED_IPV4_KERNEL_ROUTE")
        if cols[0] != "lo":
            raise Stage38Refused("SELF_NAMESPACE_HAS_NONLOOPBACK_IPV4_ROUTE")
        if (any(len(cols[i]) != 8 or not _HEX.fullmatch(cols[i])
                for i in (1, 2, 7))
                or not _HEX.fullmatch(cols[3])):
            raise Stage38Refused("INVALID_IPV4_ROUTE_ENCODING")
        count += 1
    return count


def _routes6(raw: bytes) -> int:
    lines = _lines(raw, limit=32768)
    count = 0
    for line in lines:
        cols = line.split()
        if (len(cols) != 10
                or cols[-1] != "lo"
                or len(cols[0]) != 32
                or len(cols[2]) != 32
                or len(cols[4]) != 32
                or any(not _HEX.fullmatch(v) for v in cols[:-1])
                or any(len(cols[i]) != n for i, n in (
                    (1, 2), (3, 2), (5, 8), (6, 8), (7, 8), (8, 8)))):
            raise Stage38Refused("NONLOOPBACK_OR_INVALID_IPV6_ROUTE")
        count += 1
    return count


@dataclass(frozen=True, slots=True)
class PassiveKernelObservationReceipt:
    host_alias: str
    nodename: str
    measured_at: int
    process_uid: int
    process_gid: int
    proc_status_sha256: str
    proc_mountinfo_sha256: str
    proc_ipv4_routes_sha256: str
    proc_ipv6_routes_sha256: str
    loopback_routes_seen: int
    state: str = "LOCAL_PROCESS_KERNEL_POSTURE_ONLY_NO_RUNTIME_ATTESTATION"
    local_process_restrictive_snapshot: bool = True
    independent_host_identity_verified: bool = False
    nftables_active_ruleset_independently_verified: bool = False
    network_egress_independently_blocked: bool = False
    other_container_gvisor_verified: bool = False
    gvisor_escape_containment_certified: bool = False
    public_api_deployment_authorized: bool = False
    plugin_execution_authorized: bool = False
    telegram_publish_authorized: bool = False
    broker_order_authorized: bool = False

    def sanitized_json(self) -> bytes:
        return canonical(asdict(self))

    def digest_sha256(self) -> str:
        return hashlib.sha256(self.sanitized_json()).hexdigest()


def observe_authorized_process_kernel_posture(
    *, host_alias: str, expected_nodename: str,
    expected_gid: int, operator_ack: bool = False,
) -> PassiveKernelObservationReceipt:
    """Manual passive check on an EXISTING separately approved nonroot host.

    Actual Linux /proc files are opened read-only, with no shell, sudo,
    subprocess, listener, external connection, code execution or host
    mutation. Reads process and network namespace of this very sampler,
    NOT the installed runsc sandbox or another container's process state.
    """
    try:
        _approved_host(host_alias, expected_nodename, operator_ack=operator_ack)
    except Stage34Refused as exc:
        raise Stage38Refused("AUTHORIZED_DISPOSABLE_NONROOT_HOST_REQUIRED") from exc
    if type(expected_gid) is not int or not 0 < expected_gid < 2**31:
        raise Stage38Refused("EXACT_NONROOT_PROCESS_GID_REQUIRED")
    uid = os.geteuid()
    gid = os.getegid()
    if gid != expected_gid:
        raise Stage38Refused("OPERATOR_PINNED_PROCESS_GID_MISMATCH")
    raw = tuple(_read_fixed_proc(p, limit=limit)
                for p, limit in zip(_PATHS, _LIMITS))
    _status(raw[0], expected_uid=uid, expected_gid=gid)
    _root_mount(raw[1])
    routes = _routes4(raw[2]) + _routes6(raw[3])
    return PassiveKernelObservationReceipt(
        host_alias=host_alias, nodename=expected_nodename,
        measured_at=int(time.time()), process_uid=uid, process_gid=gid,
        proc_status_sha256=hashlib.sha256(raw[0]).hexdigest(),
        proc_mountinfo_sha256=hashlib.sha256(raw[1]).hexdigest(),
        proc_ipv4_routes_sha256=hashlib.sha256(raw[2]).hexdigest(),
        proc_ipv6_routes_sha256=hashlib.sha256(raw[3]).hexdigest(),
        loopback_routes_seen=routes,
    )


__all__ = [
    "Stage38Refused", "PassiveKernelObservationReceipt",
    "observe_authorized_process_kernel_posture",
]
