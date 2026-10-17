"""Stage 23 manual disposable-host Stage4 OCI/gVisor canary.

Never launched by CI, package import or bot. Real execution requires four
operator/OS gates, exact Stage4 rootless Docker/runsc policy, a pinned image
and explicit nonproduction disposable-host acknowledgement. Runs ONLY this
FIXED harmless built-in probe, not a submitted plugin or marketplace code.

Mocked unit tests validate contracts but DO NOT prove real containment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
from dataclasses import dataclass

from .secure_plugin_runtime_v1 import (
    SecurePluginPolicy, SecurePluginRefused,
    _assert_rootless_socket, _ensure_rootless_daemon, _invoke,
)

# Intentionally static text passed via Stage4 stdin-framed bootstrap. Does
# not execute received plugin/source bytes, or read actual secrets.
_CANARY = r'''import json,os,re,socket,sys
request=json.load(sys.stdin)
ok={}
ok["uid_unprivileged"]=(os.getuid()==65534 and os.geteuid()==65534)
try:
 s=open("/proc/self/status",encoding="ascii").read()
 cap=re.search(r"(?m)^CapEff:\s*([0-9A-Fa-f]+)",s)
 nnp=re.search(r"(?m)^NoNewPrivs:\s*(\d+)",s)
 ok["no_capabilities"]=bool(cap and int(cap.group(1),16)==0)
 ok["no_new_privileges"]=bool(nnp and nnp.group(1)=="1")
except (OSError,ValueError):
 ok["no_capabilities"]=False
 ok["no_new_privileges"]=False
ok["docker_socket_absent"]=not os.path.exists("/var/run/docker.sock")
ok["docker_user_socket_absent"]=not os.path.exists("/run/user")
try:
 interfaces=socket.if_nameindex()
 ok["only_loopback_interfaces"]=(bool(interfaces) and
                                 all(name=="lo" for _idx,name in interfaces))
except OSError:
 ok["only_loopback_interfaces"]=False
try:
 fd=os.open("/mmt-stage23-root-write-attempt",os.O_CREAT|os.O_WRONLY,0o600)
 os.close(fd)
 ok["rootfs_readonly"]=False
except OSError:
 ok["rootfs_readonly"]=True
try:
 sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
 sock.settimeout(0.15)
 try:
  ok["external_network_denied"]=(sock.connect_ex(("192.0.2.1",9))!=0)
 finally:
  sock.close()
except OSError:
 ok["external_network_denied"]=True
try:
 with open("/root/.ssh/id_rsa","rb") as secret:
  secret.read(1)
 ok["root_secret_unreadable"]=False
except OSError:
 ok["root_secret_unreadable"]=True
print(json.dumps({"schema":1,"nonce":request["nonce"],"checks":ok},
                 sort_keys=True,separators=(",",":")))
'''


class HostCanaryRefused(ValueError):
    """Sanitized runtime-evidence failure, never a deployment permission."""


_REQUIRED = frozenset({
    "uid_unprivileged", "no_capabilities", "no_new_privileges",
    "docker_socket_absent", "docker_user_socket_absent",
    "only_loopback_interfaces", "rootfs_readonly", "external_network_denied",
    "root_secret_unreadable",
})


@dataclass(frozen=True, slots=True)
class CanaryReceipt:
    status: str
    image_digest: str
    probe_sha256: str
    checks: dict[str, bool]
    complete: bool
    actual_host_isolation_independently_audited: bool = False
    publisher_trust_conferred: bool = False
    user_code_executed: bool = False
    public_plugin_install_authorized: bool = False
    live_trading_authorized: bool = False
    telegram_sent: bool = False
    broker_order_sent: bool = False


def _parse_probe(blob: bytes, nonce: str) -> dict[str, bool]:
    if type(blob) is not bytes or not 1 <= len(blob) <= 4096:
        raise HostCanaryRefused("BOUNDED_CANARY_OUTPUT_REQUIRED")
    try:
        data = json.loads(blob.decode("ascii"), parse_constant=lambda _:
                          (_ for _ in ()).throw(HostCanaryRefused(
                              "NONFINITE_CANARY")), object_pairs_hook=_unique)
    except HostCanaryRefused:
        raise
    except (ValueError, UnicodeError) as exc:
        raise HostCanaryRefused("MALFORMED_CANARY_OUTPUT") from exc
    if (type(data) is not dict or set(data) != {"schema", "nonce", "checks"}
            or type(data["schema"]) is not int or data["schema"] != 1
            or type(data["nonce"]) is not str
            or not hmac.compare_digest(data["nonce"], nonce)
            or type(data["checks"]) is not dict
            or set(data["checks"]) != _REQUIRED
            or any(type(v) is not bool for v in data["checks"].values())
            or any(v is not True for v in data["checks"].values())):
        raise HostCanaryRefused("FAILED_OR_FORGED_RUNTIME_CANARY")
    return data["checks"]


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise HostCanaryRefused("DUPLICATE_CANARY_JSON_KEY")
        out[k] = v
    return out


def _prove_container_absent(policy: SecurePluginPolicy, name: str) -> None:
    try:
        result = subprocess.run(
            [policy.docker_binary, "--host", policy.docker_socket,
             "ps", "-a", "--filter", f"name=^/{name}$",
             "--format", "{{.Names}}"],
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostCanaryRefused("CANNOT_VERIFY_CONTAINER_CLEANUP") from exc
    if result.returncode != 0 or result.stdout.strip():
        raise HostCanaryRefused("ORPHAN_CONTAINER_NOT_RULED_OUT")


def run_manual_disposable_host_canary(
        policy: SecurePluginPolicy, *, operator_ack: bool = False) -> CanaryReceipt:
    """Runs EXACT built-in source once in a real Stage4 OCI worker only.

    A source-checking unit test can mock this function's internals; those
    mocks do not represent real gVisor security acceptance. No automatic CI.
    """
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or os.environ.get("MMT_DISPOSABLE_SANDBOX_HOST") != "1"):
        raise HostCanaryRefused("EXPLICIT_DISPOSABLE_NONPRODUCTION_HOST_REQUIRED")
    if type(policy) is not SecurePluginPolicy or not policy.enabled:
        raise HostCanaryRefused("EXACT_ENABLED_STAGE4_POLICY_REQUIRED")
    if os.geteuid() == 0:
        raise HostCanaryRefused("ROOT_HOST_FORBIDDEN")
    try:
        _assert_rootless_socket(policy)
        _ensure_rootless_daemon(policy)
    except SecurePluginRefused as exc:
        raise HostCanaryRefused("ROOTLESS_RUNTIME_NOT_VERIFIED") from exc
    nonce = secrets.token_hex(24)
    probe = _CANARY.encode("utf-8")
    payload = json.dumps({"nonce": nonce}, sort_keys=True,
                         separators=(",", ":")).encode("ascii")
    framed = len(probe).to_bytes(4, "big") + probe + payload
    name = "mmt-core-" + secrets.token_hex(12)
    error = None
    checks = None
    try:
        output = _invoke(policy, name, framed)
        checks = _parse_probe(output, nonce)
    except (OSError, ValueError, SecurePluginRefused) as exc:
        error = exc
    # Best-effort Stage4 removal is not enough. Require independent
    # Docker query proving the exact daemon-side name was removed.
    _prove_container_absent(policy, name)
    if error is not None or checks is None:
        raise HostCanaryRefused("DISPOSABLE_CANARY_DENIED") from error
    return CanaryReceipt(
        status="OBSERVED_SINGLE_DISPOSABLE_HOST_CANARY_NOT_SECURITY_CERTIFIED",
        image_digest=policy.image.rsplit("@sha256:", 1)[-1],
        probe_sha256=hashlib.sha256(probe).hexdigest(),
        checks=checks, complete=True)


__all__ = ["HostCanaryRefused", "CanaryReceipt",
           "run_manual_disposable_host_canary"]
