"""CERT-A8: harmless GitHub-hosted rootful-Docker fixture smoke only.

Never run on an attached server. This is NOT rootless/gVisor certification,
not an arbitrary-plugin executor, and not a Worker launch authorization.
The sole permitted image is the A2 *local CI-built* candidate.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from dataclasses import asdict, dataclass

_DOCKER = ("/usr/bin/docker", "--host", "unix:///var/run/docker.sock")
_IMAGE = "mmt/runtime-a2-candidate:pr"
_MAX_OUTPUT = 4096

# Fixed, inert Python-only probe. Never accept source or image from callers.
_PROBE = """import json, os, resource, socket, tempfile
def readonly_root():
    try:
        with open("/mmt_cert_a8_root_must_reject_write", "xb") as file:
            file.write(b"fixed")
    except OSError:
        return True
    return False
def tempfs_writable():
    try:
        with tempfile.NamedTemporaryFile(dir="/tmp") as file:
            file.write(b"fixed")
            file.flush()
        return True
    except OSError:
        return False
def process_privileges():
    try:
        fields = {}
        with open("/proc/self/status", encoding="ascii") as file:
            for line in file:
                if line.startswith(("CapEff:", "NoNewPrivs:")):
                    name, value = line.split(":", 1)
                    fields[name] = value.strip()
        return (int(fields["CapEff"], 16) == 0
                and int(fields["NoNewPrivs"]) == 1)
    except (OSError, ValueError, KeyError):
        return False
def cgroup_limits():
    try:
        root = "/sys/fs/cgroup/"
        with open(root + "memory.max", encoding="ascii") as file:
            memory = int(file.read().strip())
        with open(root + "pids.max", encoding="ascii") as file:
            pids = int(file.read().strip())
        with open(root + "cpu.max", encoding="ascii") as file:
            quota, period = (int(value) for value in file.read().split())
        nofile = resource.getrlimit(resource.RLIMIT_NOFILE)
        return (0 < memory <= 128 * 1024 * 1024
                and 0 < pids <= 32
                and 0 < quota <= period // 2
                and nofile == (64, 64))
    except (OSError, ValueError, TypeError, ZeroDivisionError):
        return False
def only_loopback():
    try:
        return {name for _, name in socket.if_nameindex()} == {"lo"}
    except (OSError, ValueError):
        return False
sensitive = ("GITHUB_TOKEN", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY",
             "DATABASE_URL", "BINANCE_API_KEY", "TELEGRAM_BOT_TOKEN",
             "MMT_PRODUCTION")
result = {
    "nonroot": os.geteuid() == 65534,
    "root_readonly": readonly_root(),
    "tempfs_writable": tempfs_writable(),
    "loopback_only": only_loopback(),
    "no_effective_caps_and_nnp": process_privileges(),
    "bounded_resources": cgroup_limits(),
    "no_named_secret_env": not any(name in os.environ for name in sensitive),
}
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
"""
_KEYS = frozenset({
    "nonroot", "root_readonly", "tempfs_writable", "loopback_only",
    "no_effective_caps_and_nnp", "bounded_resources", "no_named_secret_env",
})


class CertA8Refused(ValueError):
    """Fail closed without emitting container output or environment secrets."""


@dataclass(frozen=True, slots=True)
class BenignDockerSmoke:
    checked_facts: int
    cleanup_observed: bool
    status: str = "CERT_A8_GITHUB_ROOTFUL_DOCKER_FIXTURE_NOT_GVISOR_CERTIFIED"
    host_isolation_certified: bool = False
    real_worker_execution_authorized: bool = False
    arbitrary_code_permitted: bool = False
    runtime_a6_unlocked: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    production_authorized: bool = False


def _guard() -> None:
    """Only intended for the GitHub-hosted A2 fixture job, never Telmivo."""
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1",
        "MMT_CERT_A8_BENIGN_DOCKER_ONLY": "1",
    }
    if (os.environ.get("MMT_PRODUCTION") == "1"
            or os.geteuid() == 0
            or any(os.environ.get(key) != value for key, value in required.items())):
        raise CertA8Refused("CERT_A8_GITHUB_HOSTED_FIXED_FIXTURE_ONLY")


def _call(args: tuple[str, ...], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    if args[:len(_DOCKER)] != _DOCKER:
        raise CertA8Refused("CERT_A8_UNEXPECTED_DOCKER_ENDPOINT")
    try:
        return subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True, check=False,
            timeout=timeout, close_fds=True, shell=False,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
                 "DOCKER_CONFIG": "/nonexistent"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CertA8Refused("CERT_A8_DOCKER_UNAVAILABLE_OR_TIMEOUT") from exc


def _strict_result(raw: bytes) -> None:
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_OUTPUT:
        raise CertA8Refused("CERT_A8_PROBE_OUTPUT_INVALID")

    def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, val in pairs:
            if key in result:
                raise CertA8Refused("CERT_A8_DUPLICATE_RESULT_FIELD")
            result[key] = val
        return result

    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, CertA8Refused):
            raise
        raise CertA8Refused("CERT_A8_MALFORMED_PROBE_RESULT") from exc
    if (type(obj) is not dict or set(obj) != _KEYS
            or any(value is not True for value in obj.values())):
        raise CertA8Refused("CERT_A8_CONFINEMENT_FIXTURE_REFUSED")


def _cleanup(name: str) -> bool:
    """Never overclaim process-orphan or independent-container proof."""
    try:
        _call((*_DOCKER, "rm", "--force", name), timeout=5)
        status = _call((*_DOCKER, "info", "--format", "{{.ServerVersion}}"),
                       timeout=5)
        observed = _call((*_DOCKER, "container", "inspect", name), timeout=5)
    except CertA8Refused:
        return False
    missing = (b"No such object: " + name.encode("ascii") in observed.stderr
               or b"No such container: " + name.encode("ascii") in observed.stderr)
    return status.returncode == 0 and observed.returncode != 0 and missing


def smoke() -> BenignDockerSmoke:
    """Run ONLY the pinned literal probe in the already-built local A2 image."""
    _guard()
    name = "mmt-ci-cert-a8-" + secrets.token_hex(12)
    argv = (
        *_DOCKER, "run", "--rm", "--pull=never", "--name=" + name,
        "--network=none", "--ipc=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=32",
        "--memory=128m", "--memory-swap=128m", "--cpus=0.5",
        "--ulimit=nofile=64:64", "--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
        "--workdir=/tmp", "--entrypoint=/usr/local/bin/python",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        _IMAGE, "-I", "-S", "-c", _PROBE,
    )
    error: CertA8Refused | None = None
    try:
        reply = _call(argv, timeout=20)
        if reply.returncode != 0 or len(reply.stderr) > _MAX_OUTPUT:
            raise CertA8Refused("CERT_A8_FIXED_DOCKER_PROBE_FAILED")
        _strict_result(reply.stdout)
    except CertA8Refused as exc:
        error = exc
    finally:
        clean = _cleanup(name)
    if not clean:
        raise CertA8Refused("CERT_A8_DOCKER_CLEANUP_UNPROVEN") from error
    if error is not None:
        raise error
    return BenignDockerSmoke(len(_KEYS), cleanup_observed=True)


def main() -> int:
    try:
        report = smoke()
    except CertA8Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(asdict(report), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
