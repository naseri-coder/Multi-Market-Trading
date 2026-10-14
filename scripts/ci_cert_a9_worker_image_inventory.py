"""CERT-A9: actual installed-image inventory in the existing A2 CI fixture job.

Review-only CI evidence: it is NOT independently signed, a reproducible
dependency lock, rootless/gVisor certification or Worker launch permission.
Never execute on production/TELMIVO or allow caller-provided image/source.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from naseri_markets.runtime_a8_supply_chain import A8Refused, verify_source_lock

_ROOT = Path(__file__).resolve().parents[1]
_IMAGE = "mmt/runtime-a2-candidate:pr"
_DOCKER = ("/usr/bin/docker", "--host", "unix:///var/run/docker.sock")
_HEX = re.compile(r"sha256:[a-f0-9]{64}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[+._~-][A-Za-z0-9.+_-]+)?\Z")
_MAX_OUTPUT = 4096
_DOMAIN = b"MMT-CERT-A9-INSTALLED-IMAGE-CI-OBSERVATION-V1\x00"

# Fixed code, no uploaded sources, network connections, package installation
# or user-specified interpreter arguments. Read the *actual* installed image.
_PROBE = """import hashlib, importlib.metadata, json, subprocess, sys
def version(argv):
    proc = subprocess.run(argv, input=b"", stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=False, timeout=5)
    if proc.returncode != 0 or not 0 < len(proc.stdout) <= 96:
        raise RuntimeError("VERSION_QUERY_FAILED")
    return proc.stdout.decode("ascii").strip()
with open("/opt/mmt/bin/runtime-a1-worker", "rb") as worker:
    data = worker.read(262145)
if not 0 < len(data) <= 262144:
    raise RuntimeError("WORKER_SIZE_INVALID")
print(json.dumps({
    "python_version": ".".join(map(str, sys.version_info[:3])),
    "node_version": version(["node", "--version"]).removeprefix("v"),
    "npm_version": version(["npm", "--version"]),
    "typescript_version": version(["tsc", "--version"]).removeprefix("Version "),
    "wasmtime_version": importlib.metadata.version("wasmtime"),
    "worker_sha256": hashlib.sha256(data).hexdigest(),
}, sort_keys=True, separators=(",", ":")))
"""
_KEYS = frozenset({
    "python_version", "node_version", "npm_version",
    "typescript_version", "wasmtime_version", "worker_sha256",
})


class CertA9Refused(ValueError):
    """Fail closed without disclosing raw Docker output or private data."""


@dataclass(frozen=True, slots=True)
class InstalledImageReview:
    image_id: str
    worker_sha256: str
    python_version: str
    node_version: str
    npm_version: str
    typescript_version: str
    wasmtime_version: str
    inventory_fingerprint_sha256: str
    status: str = "CERT_A9_IMAGE_CONTENT_OBSERVED_NOT_SUPPLY_CHAIN_ATTESTED"
    source_lock_checked: bool = True
    image_unchanged_during_probe: bool = True
    independent_publisher_verified: bool = False
    base_image_digest_pinned: bool = False
    apt_packages_immutable: bool = False
    npm_tarball_integrity_verified: bool = False
    wheel_integrity_verified: bool = False
    independently_reproducible: bool = False
    host_isolation_certified: bool = False
    worker_execution_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    production_authorized: bool = False


def _guard() -> None:
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1",
        "MMT_CERT_A9_INSTALLED_IMAGE_ONLY": "1",
    }
    if (os.geteuid() == 0 or os.environ.get("MMT_PRODUCTION") == "1"
            or any(os.environ.get(k) != val for k, val in required.items())):
        raise CertA9Refused("CERT_A9_EXPLICIT_HOSTED_CI_SCOPE_REQUIRED")


def _call(argv: tuple[str, ...], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    if argv[:len(_DOCKER)] != _DOCKER:
        raise CertA9Refused("CERT_A9_UNEXPECTED_DOCKER_ENDPOINT")
    try:
        return subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=timeout, check=False, close_fds=True, shell=False,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
                 "DOCKER_CONFIG": "/nonexistent"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CertA9Refused("CERT_A9_DOCKER_UNAVAILABLE_OR_TIMEOUT") from exc


def _image_id() -> str:
    reply = _call((*_DOCKER, "image", "inspect", _IMAGE,
                   "--format", "{{.Id}}"), timeout=5)
    if reply.returncode != 0 or not 0 < len(reply.stdout) <= 96:
        raise CertA9Refused("CERT_A9_IMAGE_NOT_LOCALLY_PRESENT")
    try:
        image_id = reply.stdout.decode("ascii").strip()
    except UnicodeError as exc:
        raise CertA9Refused("CERT_A9_IMAGE_ID_ENCODING_INVALID") from exc
    if _HEX.fullmatch(image_id) is None:
        raise CertA9Refused("CERT_A9_IMAGE_ID_INVALID")
    return image_id


def _strict_versions(raw: bytes, expected_sha: str) -> dict[str, str]:
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_OUTPUT:
        raise CertA9Refused("CERT_A9_INVENTORY_OUTPUT_INVALID")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise CertA9Refused("CERT_A9_DUPLICATE_INVENTORY_FIELD")
            obj[key] = value
        return obj

    try:
        data = json.loads(raw.decode("ascii"), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, CertA9Refused):
            raise
        raise CertA9Refused("CERT_A9_MALFORMED_INVENTORY") from exc
    if (type(data) is not dict or set(data) != _KEYS
            or any(type(val) is not str or len(val) > 96
                   for val in data.values())
            or any(_VERSION.fullmatch(data[key]) is None
                   for key in _KEYS - {"worker_sha256"})
            or not re.fullmatch(r"[a-f0-9]{64}", data["worker_sha256"])):
        raise CertA9Refused("CERT_A9_INVENTORY_SCHEMA_INVALID")
    if (data["worker_sha256"] != expected_sha
            or not data["python_version"].startswith("3.12.")
            or data["typescript_version"] != "5.9.3"
            or data["wasmtime_version"] != "49.0.0"):
        raise CertA9Refused("CERT_A9_INSTALLED_WORKER_OR_VERSION_DRIFT")
    # Node and npm are installed by the mutable APT repository. Record their
    # exact versions, but do not pretend this phase pinned package hashes.
    if not int(data["node_version"].split(".", 1)[0]) >= 18:
        raise CertA9Refused("CERT_A9_UNSUPPORTED_NODE_VERSION")
    return data


def _cleanup(name: str) -> bool:
    try:
        _call((*_DOCKER, "rm", "-f", name), timeout=5)
        reply = _call((*_DOCKER, "container", "inspect", name), timeout=5)
        check = _call((*_DOCKER, "info", "--format", "{{.ServerVersion}}"),
                      timeout=5)
    except CertA9Refused:
        return False
    missing = (b"No such object: " + name.encode("ascii") in reply.stderr
               or b"No such container: " + name.encode("ascii") in reply.stderr)
    return reply.returncode != 0 and missing and check.returncode == 0


def review() -> InstalledImageReview:
    _guard()
    try:
        lock = verify_source_lock(
            _ROOT, _ROOT / "deploy/runtime_a2/a8_source_lock.json",
        )
    except A8Refused as exc:
        raise CertA9Refused("CERT_A9_SOURCE_LOCK_NOT_MATCHED") from exc
    if lock.checked_files != 3:
        raise CertA9Refused("CERT_A9_SOURCE_SET_INCOMPLETE")
    expected_sha = hashlib.sha256(
        (_ROOT / "scripts/runtime_a2_worker.py").read_bytes(),
    ).hexdigest()
    before = _image_id()
    name = "mmt-ci-cert-a9-" + secrets.token_hex(12)
    command = (
        *_DOCKER, "run", "--rm", "--pull=never", "--name=" + name,
        "--network=none", "--ipc=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=32",
        "--memory=128m", "--memory-swap=128m", "--cpus=0.5",
        "--ulimit=nofile=64:64", "--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
        "--workdir=/tmp", "--entrypoint=/usr/local/bin/python",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        _IMAGE, "-I", "-c", _PROBE,
    )
    versions = None
    failure = None
    try:
        result = _call(command, timeout=25)
        if result.returncode != 0 or len(result.stderr) > _MAX_OUTPUT:
            raise CertA9Refused("CERT_A9_INSTALLED_IMAGE_PROBE_FAILED")
        versions = _strict_versions(result.stdout, expected_sha)
    except CertA9Refused as exc:
        failure = exc
    finally:
        clean = _cleanup(name)
    if not clean:
        raise CertA9Refused("CERT_A9_CLEANUP_NOT_OBSERVED") from failure
    if failure is not None:
        raise failure
    after = _image_id()
    if before != after:
        raise CertA9Refused("CERT_A9_LOCAL_IMAGE_ID_CHANGED_DURING_REVIEW")
    if versions is None:
        raise CertA9Refused("CERT_A9_RESULT_NOT_AVAILABLE")
    fingerprint = hashlib.sha256(
        _DOMAIN + json.dumps(
            {"image_id": before, "inventory": versions},
            sort_keys=True, separators=(",", ":"),
        ).encode("ascii"),
    ).hexdigest()
    return InstalledImageReview(
        image_id=before, worker_sha256=versions["worker_sha256"],
        python_version=versions["python_version"],
        node_version=versions["node_version"], npm_version=versions["npm_version"],
        typescript_version=versions["typescript_version"],
        wasmtime_version=versions["wasmtime_version"],
        inventory_fingerprint_sha256=fingerprint,
    )


def main() -> int:
    try:
        evidence = review()
    except CertA9Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(asdict(evidence), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
