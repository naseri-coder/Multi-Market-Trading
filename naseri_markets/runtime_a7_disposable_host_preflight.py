"""RUNTIME-A7: passive disposable-host inspection; never launch a Worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{64}\Z")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,195}@sha256:[a-f0-9]{64}\Z")
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{3,95}\Z")
DOCKER = "/usr/bin/docker"


class A7Refused(ValueError):
    """Never include secrets or raw system output in refusal messages."""


@dataclass(frozen=True, slots=True)
class HostObservation:
    host_id: str
    image_ref: str
    image_id: str
    runsc_sha256: str
    status: str = "A7_PASSIVE_OBSERVATION_NOT_CERTIFIED"
    fixed_fixture_executed: bool = False
    kernel_isolation_proved: bool = False
    independently_attested: bool = False
    execution_authorized: bool = False
    broker_permitted: bool = False
    telegram_permitted: bool = False


def scope(host: str, image: str, runsc: Path, digest: str, ack: bool) -> int:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise A7Refused("A7_NONPRODUCTION_ONLY")
    uid = os.geteuid()
    if uid == 0 or ack is not True:
        raise A7Refused("A7_DISPOSABLE_OPERATOR_ACK_REQUIRED")
    if (type(host) is not str or not HOST.fullmatch(host)
            or type(image) is not str or not IMAGE.fullmatch(image)
            or type(digest) is not str or not SHA.fullmatch(digest)
            or not isinstance(runsc, Path) or not runsc.is_absolute()):
        raise A7Refused("A7_EXACT_HOST_AND_DIGEST_REQUIRED")
    return uid


def safe_socket(uid: int) -> str:
    path = Path(f"/run/user/{uid}/docker.sock")
    try:
        info = path.lstat()
        if (path.is_symlink() or path.parent.is_symlink()
                or not stat.S_ISSOCK(info.st_mode) or info.st_uid != uid
                or stat.S_IMODE(info.st_mode) & 0o007):
            raise A7Refused("A7_ROOTLESS_SOCKET_UNTRUSTED")
    except OSError as exc:
        raise A7Refused("A7_ROOTLESS_SOCKET_MISSING") from exc
    return f"unix://{path}"


def pinned_binary(path: Path, sha: str) -> None:
    try:
        data = path.lstat()
        if (path.is_symlink() or not stat.S_ISREG(data.st_mode)
                or stat.S_IMODE(data.st_mode) & 0o002
                or not os.access(path, os.X_OK)
                or not 0 < data.st_size <= 256 * 1024 * 1024):
            raise A7Refused("A7_RUNSC_BINARY_UNSAFE")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != sha:
            raise A7Refused("A7_RUNSC_PIN_MISMATCH")
    except OSError as exc:
        raise A7Refused("A7_RUNSC_UNAVAILABLE") from exc


def query(args: tuple[str, ...]) -> bytes:
    info = (len(args) == 6 and args[0] == DOCKER and args[1] == "--host"
            and args[3:5] == ("info", "--format")
            and args[5] in ("{{json .SecurityOptions}}", "{{json .Runtimes}}"))
    inspect = (len(args) == 8 and args[0] == DOCKER and args[1] == "--host"
               and args[3:5] == ("image", "inspect")
               and args[6] == "--format"
               and args[7] in ("{{json .RepoDigests}}", "{{.Id}}"))
    version = len(args) == 2 and args[1] == "--version" and args[0].startswith("/")
    if not (info or inspect or version):
        raise A7Refused("A7_COMMAND_NOT_READONLY")
    try:
        res = subprocess.run(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=5, check=False,
            close_fds=True, shell=False,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise A7Refused("A7_HOST_QUERY_UNAVAILABLE") from exc
    if res.returncode != 0 or not 0 < len(res.stdout) <= 8192:
        raise A7Refused("A7_HOST_QUERY_FAILED")
    return res.stdout


def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise A7Refused("A7_DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def parsed(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, A7Refused):
            raise
        raise A7Refused("A7_INVALID_HOST_JSON") from exc


def preflight(*, host: str, image: str, runsc: Path, sha: str,
              operator_ack: bool = False) -> HostObservation:
    """Read-only daemon and local file observations. Not sandbox validation."""
    uid = scope(host, image, runsc, sha, operator_ack)
    socket = safe_socket(uid)
    pinned_binary(runsc, sha)
    base = (DOCKER, "--host", socket)
    opts = parsed(query((*base, "info", "--format", "{{json .SecurityOptions}}")))
    if (type(opts) is not list or "name=rootless" not in opts
            or not any(isinstance(x, str) and x.startswith("name=seccomp")
                       for x in opts)):
        raise A7Refused("A7_ROOTLESS_OR_SECCOMP_NOT_OBSERVED")
    runtimes = parsed(query((*base, "info", "--format", "{{json .Runtimes}}")))
    if (type(runtimes) is not dict or not isinstance(runtimes.get("runsc"), dict)
            or runtimes["runsc"].get("path") != str(runsc)):
        raise A7Refused("A7_RUNSC_NOT_REGISTERED")
    digests = parsed(query((*base, "image", "inspect", image,
                            "--format", "{{json .RepoDigests}}")))
    if type(digests) is not list or image not in digests:
        raise A7Refused("A7_LOCAL_IMAGE_PIN_NOT_PRESENT")
    image_id = query((*base, "image", "inspect", image,
                      "--format", "{{.Id}}")).decode("ascii", "ignore").strip()
    if not image_id.startswith("sha256:") or not SHA.fullmatch(image_id[7:]):
        raise A7Refused("A7_IMAGE_ID_INVALID")
    if b"runsc" not in query((str(runsc), "--version")).lower():
        raise A7Refused("A7_RUNSC_VERSION_UNVERIFIED")
    return HostObservation(host, image, image_id, sha)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only preflight, NOT attestation.")
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runsc", type=Path, required=True)
    parser.add_argument("--runsc-sha256", required=True)
    parser.add_argument("--ack-disposable-host", action="store_true")
    args = parser.parse_args()
    try:
        result = preflight(
            host=args.host_id, image=args.image, runsc=args.runsc,
            sha=args.runsc_sha256, operator_ack=args.ack_disposable_host,
        )
    except A7Refused as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
