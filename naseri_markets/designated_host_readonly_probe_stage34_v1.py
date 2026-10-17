"""Stage34 opt-in, local-only security observations on an approved disposable host.

NEVER auto-run or deploy. No source execution, Docker, firewall changes, CA/key
generation, file writes, public listeners, SSH, or remote probes. Linux /proc
listener inspection and a TLS1.3 client handshake to *127.0.0.1 only* are read-
only observations, NOT independent attestation, firewall proof, or public
installation authorization. The host must be designated out of band.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import socket
import ssl
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .a24_publisher_admission import canonical
from .disposable_host_preflight_stage32_v1 import _private_file
from .tls_boundary_stage31_v1 import _HOSTNAME, _TLS13_CIPHERS

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOST = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")
_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_LOCAL = frozenset({"127.0.0.1", "::1"})
_MAX_PROC = 262144


class Stage34Refused(ValueError):
    """No CA file contents, host secrets or network error details leak."""


def _approved_host(host_alias: str, expected_nodename: str, *,
                   operator_ack: bool) -> None:
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or os.environ.get("MMT_DISPOSABLE_SANDBOX_HOST") != "1"
            or type(host_alias) is not str or not _HOST.fullmatch(host_alias)
            or type(expected_nodename) is not str
            or not _NODE.fullmatch(expected_nodename)
            or os.geteuid() == 0
            or os.uname().nodename != expected_nodename):
        raise Stage34Refused("EXPLICIT_NONROOT_DESIGNATED_DISPOSABLE_HOST_REQUIRED")


def _read_proc(path: str) -> bytes:
    # Do not accept attacker-provided path. The reader never opens /proc/pid
    # secrets or shell-interpreted paths, and limits output from procfs.
    if path not in ("/proc/net/tcp", "/proc/net/tcp6"):
        raise Stage34Refused("ONLY_FIXED_KERNEL_SOCKET_SNAPSHOT_ALLOWED")
    try:
        with open(path, "rb") as stream:
            raw = stream.read(_MAX_PROC+1)
    except OSError as exc:
        raise Stage34Refused("KERNEL_LISTEN_SNAPSHOT_UNAVAILABLE") from exc
    if len(raw) > _MAX_PROC:
        raise Stage34Refused("KERNEL_LISTEN_SNAPSHOT_OVERSIZE")
    return raw


def _socket_listeners(proc4: bytes, proc6: bytes) -> tuple[tuple[str, int], ...]:
    """Bound and parse Linux /proc/net/tcp{,6} LISTEN state 0A.

    An empty/garbled proc file or unsupported address is a hard refusal.
    A passing LISTEN snapshot does not assert firewall rules or external
    reachability; sockets can change immediately afterwards.
    """
    result = []
    for family, blob in ((4, proc4), (6, proc6)):
        if (type(blob) is not bytes or not 1 <= len(blob) <= _MAX_PROC):
            raise Stage34Refused("BOUNDED_KERNEL_SNAPSHOT_REQUIRED")
        try:
            lines = blob.decode("ascii").splitlines()
        except UnicodeError as exc:
            raise Stage34Refused("NONASCII_KERNEL_SOCKET_TABLE") from exc
        if (not 1 <= len(lines) <= 1025 or
                "local_address" not in lines[0] or "st" not in lines[0]):
            raise Stage34Refused("MISSING_KERNEL_SOCKET_TABLE_HEADER")
        for line in lines[1:]:
            cols = line.split()
            if len(cols) < 4 or cols[3] not in (
                    "0A", "01", "02", "03", "04", "05", "06",
                    "07", "08", "09", "0B", "0C"):
                raise Stage34Refused("INVALID_KERNEL_SOCKET_RECORD")
            if cols[3] != "0A":
                continue
            try:
                a, p = cols[1].split(":")
                if len(a) != (8 if family == 4 else 32):
                    raise ValueError
                addr_bytes = bytes.fromhex(a)
                if family == 4:
                    addr = str(ipaddress.IPv4Address(addr_bytes[::-1]))
                else:
                    # /proc/net/tcp6 dumps each 32-bit word in host order.
                    net = b"".join(addr_bytes[i:i+4][::-1]
                                   for i in range(0, 16, 4))
                    addr = str(ipaddress.IPv6Address(net))
                port = int(p, 16)
                if not 1 <= port <= 65535:
                    raise ValueError
            except (ValueError, TypeError, IndexError) as exc:
                raise Stage34Refused("INVALID_KERNEL_LISTENER_ADDRESS") from exc
            if addr not in _LOCAL:
                raise Stage34Refused("WILDCARD_OR_NONLOOPBACK_LISTENER_FOUND")
            result.append((addr, port))
            if len(result) > 128:
                raise Stage34Refused("UNBOUNDED_HOST_LISTENERS")
    return tuple(sorted(result))


def _trusted_ca(path: Path) -> bytes:
    if not isinstance(path, Path) or not path.is_absolute():
        raise Stage34Refused("EXPLICIT_OWNER_PRIVATE_CA_PATH_REQUIRED")
    try:
        return _private_file(path, max_bytes=16384)
    except (OSError, ValueError) as exc:
        raise Stage34Refused("OWNER_PRIVATE_CA_FILE_REQUIRED") from exc


def _real_local_tls(*, hostname: str, port: int, trusted_ca_pem: bytes,
                    cert_sha256: str) -> tuple[str, str]:
    """Real TLS over a connected socket; the only destination is loopback."""
    if (type(hostname) is not str or not _HOSTNAME.fullmatch(hostname)
            or not hostname.endswith((".test", ".invalid"))
            or type(port) is not int or not 1 <= port <= 65535
            or type(trusted_ca_pem) is not bytes
            or not 1 <= len(trusted_ca_pem) <= 16384
            or type(cert_sha256) is not str or not _SHA.fullmatch(cert_sha256)):
        raise Stage34Refused("PINNED_LOCAL_TEST_TLS_TARGET_REQUIRED")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    try:
        ctx.load_verify_locations(cadata=trusted_ca_pem.decode("ascii"))
        with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
            sock.settimeout(3)
            with ctx.wrap_socket(sock, server_hostname=hostname) as tls:
                peer = tls.getpeercert(binary_form=True)
                negotiated = tls.version()
                cipher = tls.cipher()
                if (negotiated != "TLSv1.3" or not cipher
                        or cipher[0] not in _TLS13_CIPHERS
                        or type(peer) is not bytes or not peer
                        or not hmac.compare_digest(
                            hashlib.sha256(peer).hexdigest(), cert_sha256)):
                    raise Stage34Refused("TLS_PEER_PIN_OR_VERSION_REJECTED")
                return cipher[0], hashlib.sha256(peer).hexdigest()
    except Stage34Refused:
        raise
    except (OSError, ssl.SSLError, UnicodeError, ValueError) as exc:
        raise Stage34Refused("LOOPBACK_TLS_HANDSHAKE_NOT_VERIFIED") from exc


@dataclass(frozen=True, slots=True)
class HostLocalProbeReceipt:
    host_alias: str
    nodename: str
    measured_at: int
    listener_snapshot_sha256: str
    local_listener_count: int
    local_tls_cert_sha256: str
    local_tls_cipher: str
    state: str = "ON_HOST_SELF_OBSERVATION_NOT_INDEPENDENT_ATTESTATION"
    host_designation_independently_verified: bool = False
    real_loopback_tls_handshake_observed: bool = True
    external_tls_or_dns_verified: bool = False
    firewall_policy_independently_verified: bool = False
    outbound_network_denial_verified: bool = False
    reverse_proxy_verified: bool = False
    gvisor_isolation_verified: bool = False
    hostile_source_executed: bool = False
    public_deployment_authorized: bool = False
    plugin_install_authorized: bool = False
    telegram_signal_authorized: bool = False
    broker_order_authorized: bool = False

    def evidence_json(self) -> bytes:
        """Canonical safe metadata for independent custody; no keys or paths."""
        return canonical(asdict(self))

    def evidence_sha256(self) -> str:
        return hashlib.sha256(self.evidence_json()).hexdigest()


def probe_designated_local_host(
    *, host_alias: str, expected_nodename: str, tls_hostname: str,
    tls_port: int, ca_file: Path, expected_certificate_sha256: str,
    operator_ack: bool = False,
) -> HostLocalProbeReceipt:
    """Explicitly opt-in, nonroot, host-local evidence; no daemon start.

    This is NOT automatically called by GitHub CI, imports or Telegram.
    An approved disposable host must already have a TLS test service
    bound to loopback; the probe never configures it or opens a listener.
    A local compromised OS can falsify /proc and the remote socket endpoint.
    """
    _approved_host(host_alias, expected_nodename, operator_ack=operator_ack)
    if tls_port != 443:
        raise Stage34Refused("REVIEWED_LOOPBACK_TLS_PORT_443_REQUIRED")
    raw4 = _read_proc("/proc/net/tcp")
    raw6 = _read_proc("/proc/net/tcp6")
    listeners = _socket_listeners(raw4, raw6)
    if ("127.0.0.1", tls_port) not in listeners:
        raise Stage34Refused("REVIEWED_LOOPBACK_TLS_LISTENER_MISSING")
    ca = _trusted_ca(ca_file)
    cipher, peer_sha = _real_local_tls(
        hostname=tls_hostname, port=tls_port,
        trusted_ca_pem=ca, cert_sha256=expected_certificate_sha256)
    stamp = int(time.time())
    # Self-reported hostname and proc records are NOT remote attestation.
    return HostLocalProbeReceipt(
        host_alias=host_alias, nodename=expected_nodename,
        measured_at=stamp,
        listener_snapshot_sha256=hashlib.sha256(raw4 + b"\x00" + raw6).hexdigest(),
        local_listener_count=len(listeners),
        local_tls_cert_sha256=peer_sha, local_tls_cipher=cipher)


__all__ = [
    "Stage34Refused", "HostLocalProbeReceipt",
    "probe_designated_local_host",
]
