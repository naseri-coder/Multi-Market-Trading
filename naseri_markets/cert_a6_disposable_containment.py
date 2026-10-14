"""CERT-A6: fixed benign gVisor probe on a preapproved expendable host ONLY.

NEVER run on trading/TELMIVO/license or any machine carrying secrets.
RUNTIME-A6 dispatch denial is unaffected; no user core or Worker is executed.
This is an operator-triggered active OBSERVATION, not independent attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from . import runtime_a7_disposable_host_preflight as a7

_DOCKER = a7.DOCKER
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_OUT = 4096
_TIMEOUT = 12
_PROBE = """import json, os, socket
def test_file():
    try:
        with open("/cert_a6_rootfs_must_reject_write", "xb") as stream:
            stream.write(b"probe")
        return False
    except OSError:
        return True
def test_interfaces():
    # A refused TCP connection to TEST-NET alone is not isolation evidence:
    # any normal host may lack a route to that address. Examine the guest's
    # actual network-interface namespace as a separate, fail-closed signal.
    try:
        return {name for _, name in socket.if_nameindex()} == {"lo"}
    except (OSError, ValueError):
        return False
def test_network():
    connection = None
    try:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(0.5)
        return connection.connect_ex(("203.0.113.1", 443)) != 0
    except OSError:
        return True
    finally:
        if connection is not None:
            connection.close()
names = ("AWS_SECRET_ACCESS_KEY", "DATABASE_URL", "BINANCE_API_KEY",
         "TELEGRAM_BOT_TOKEN", "MMT_PRODUCTION")
print(json.dumps({"nonroot": os.geteuid() == 65534,
                  "rootfs_write_refused": test_file(),
                  "external_tcp_refused": test_network(),
                  "loopback_only_interfaces": test_interfaces(),
                  "no_named_secrets": not any(key in os.environ for key in names)},
                 sort_keys=True, separators=(",", ":")))
"""
_KEYS = frozenset({
    "nonroot", "rootfs_write_refused", "external_tcp_refused",
    "loopback_only_interfaces", "no_named_secrets",
})


class CertA6Refused(ValueError):
    """Do not leak worker image details, host output or environment."""


@dataclass(frozen=True, slots=True)
class ContainmentObservation:
    host_id: str
    worker_image_sha256: str
    runsc_sha256: str
    probe_sha256: str
    network_probe_refused: bool
    loopback_interfaces_only: bool
    rootfs_probe_refused: bool
    nonroot_probe_passed: bool
    named_secret_probe_passed: bool
    cleanup_checked: bool
    status: str = "CERT_A6_FIXED_PROBE_OBSERVED_NOT_INDEPENDENTLY_CERTIFIED"
    independent_host_isolation_certified: bool = False
    arbitrary_core_execution_authorized: bool = False
    runtime_a6_unlocked: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    production_authorized: bool = False


def _scope() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or os.environ.get("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED") != "1"):
        raise CertA6Refused("CERT_A6_EXPLICIT_DISPOSABLE_ONLY")


def _call(argv: tuple[str, ...], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    """Do not execute through a shell or inherit operator credentials."""
    try:
        return subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=timeout, check=False, shell=False, close_fds=True,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CertA6Refused("CERT_A6_HOST_COMMAND_FAILED") from exc


def _strict_json(raw: bytes) -> dict[str, bool]:
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_OUT:
        raise CertA6Refused("CERT_A6_PROBE_OUTPUT_LIMIT")
    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise CertA6Refused("CERT_A6_DUPLICATE_RESULT_FIELD")
            data[key] = value
        return data
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=unique)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, CertA6Refused):
            raise
        raise CertA6Refused("CERT_A6_INVALID_PROBE_JSON") from exc
    if (type(obj) is not dict or set(obj) != _KEYS
            or any(value is not True for value in obj.values())):
        raise CertA6Refused("CERT_A6_CONTAINMENT_PROBE_NOT_PASSED")
    return obj


def _cleanup(docker: tuple[str, ...], name: str) -> bool:
    """Verify Docker daemon is alive AFTER best-effort bounded removal.

    Name-absence plus daemon liveness is not kernel-level orphan attestation.
    """
    try:
        _call((*docker, "rm", "-f", name), timeout=5)
        info = _call(
            (*docker, "info", "--format", "{{json .SecurityOptions}}"),
            timeout=5,
        )
        inspect = _call((*docker, "container", "inspect", name), timeout=5)
        missing = (b"No such container: " + name.encode("ascii") in inspect.stderr
                   or b"No such object: " + name.encode("ascii") in inspect.stderr)
        return info.returncode == 0 and inspect.returncode != 0 and missing
    except CertA6Refused:
        return False


def assess(*, host_id: str, image: str, runsc: Path, runsc_sha256: str,
           operator_ack: bool = False) -> ContainmentObservation:
    """On a *designated disposable host only*: one immutable-image benign probe.

    A7 validates rootless socket, runsc SHA, registered runtime and local
    content-addressed image. The launched fixed script contains no user code.
    """
    _scope()
    if operator_ack is not True:
        raise CertA6Refused("CERT_A6_OPERATOR_ACK_REQUIRED")
    try:
        a7.preflight(
            host=host_id, image=image, runsc=runsc, sha=runsc_sha256,
            operator_ack=True,
        )
        socket = a7.safe_socket(os.geteuid())
    except a7.A7Refused as exc:
        raise CertA6Refused("CERT_A6_A7_PREFLIGHT_REQUIRED") from exc
    docker = (_DOCKER, "--host", socket)
    name = "mmt-cert-a6-" + secrets.token_hex(12)
    argv = (
        *docker, "run", "--rm", "--pull=never",
        "--name=" + name, "--runtime=runsc",
        "--network=none", "--ipc=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=32", "--memory=128m", "--memory-swap=128m",
        "--cpus=0.5", "--ulimit=nofile=64:64",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
        "--workdir=/tmp", "--entrypoint=/usr/local/bin/python",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        image, "-I", "-S", "-c", _PROBE,
    )
    raw = None
    failure = None
    try:
        result = _call(argv, timeout=_TIMEOUT)
        if (result.returncode != 0
                or len(result.stdout) > _MAX_OUT
                or len(result.stderr) > _MAX_OUT):
            raise CertA6Refused("CERT_A6_FIXED_PROBE_FAILED")
        raw = _strict_json(result.stdout)
    except CertA6Refused as exc:
        failure = exc
    finally:
        clean = _cleanup(docker, name)
    if not clean:
        raise CertA6Refused("CERT_A6_CLEANUP_NOT_OBSERVED") from failure
    if failure is not None:
        raise failure
    if raw is None:
        raise CertA6Refused("CERT_A6_RESULT_NOT_AVAILABLE")
    image_sha = image.rsplit("@sha256:", 1)[-1]
    if _SHA.fullmatch(image_sha) is None:
        raise CertA6Refused("CERT_A6_IMAGE_DIGEST_INVALID")
    return ContainmentObservation(
        host_id=host_id, worker_image_sha256=image_sha,
        runsc_sha256=runsc_sha256,
        probe_sha256=hashlib.sha256(_PROBE.encode("utf-8")).hexdigest(),
        network_probe_refused=raw["external_tcp_refused"],
        loopback_interfaces_only=raw["loopback_only_interfaces"],
        rootfs_probe_refused=raw["rootfs_write_refused"],
        nonroot_probe_passed=raw["nonroot"],
        named_secret_probe_passed=raw["no_named_secrets"],
        cleanup_checked=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CERT-A6 fixed benign disposable-host probe; NOT attestation"
    )
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runsc", type=Path, required=True)
    parser.add_argument("--runsc-sha256", required=True)
    parser.add_argument("--ack-disposable-host", action="store_true")
    args = parser.parse_args()
    try:
        report = assess(
            host_id=args.host_id, image=args.image, runsc=args.runsc,
            runsc_sha256=args.runsc_sha256,
            operator_ack=args.ack_disposable_host,
        )
    except CertA6Refused as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(asdict(report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
