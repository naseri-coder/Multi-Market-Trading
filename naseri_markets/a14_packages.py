"""A14 disposable, offline PRIVATE package and mock-service deployment rehearsal.

NEVER runs package payloads. All paths are restricted to an operator-supplied
OS temporary directory; the only subprocess is a fixed inert fixture worker.
Not a production service supervisor, signature verifier or live trading manager.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_RELEASE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_KEYS = {"schema_version", "kind", "engine_id", "engine_version", "installation_id",
         "manifest_sha256", "trust_generation", "release", "mode", "payload_sha256",
         "mock_behavior"}
_WORKER = "import sys; sys.stdin.buffer.read(1)"  # no shell, socket or package import


class PackageRefused(ValueError):
    """Fail-closed rejection of an A14 mock package or lifecycle transition."""


def _pairs(items):
    result = {}
    for k, v in items:
        if k in result:
            raise PackageRefused("A14_DUPLICATE_JSON_FIELD")
        result[k] = v
    return result


def _atomic_json(path: Path, obj: dict) -> None:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    fd, temp = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _sync_dir(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _sync_dir(folder: Path) -> None:
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def inspect_bundle(raw: bytes, *, approved_sha256: str) -> tuple[dict, bytes]:
    """Require a *separately trusted* byte pin; never self-approve package content."""
    if type(raw) is not bytes or not 0 < len(raw) <= 98304:
        raise PackageRefused("A14_PACKAGE_SIZE")
    if type(approved_sha256) is not str or not _SHA.fullmatch(approved_sha256):
        raise PackageRefused("A14_EXTERNAL_PIN_REQUIRED")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), approved_sha256):
        raise PackageRefused("A14_PIN_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            entries = archive.infolist()
            if len(entries) != 2 or {x.filename for x in entries} != {
                "manifest.json", "payload.bin"
            }:
                raise PackageRefused("A14_EXACT_ARCHIVE_MEMBERS_REQUIRED")
            for item in entries:
                kind = (item.external_attr >> 16) & 0o170000
                if (item.flag_bits & 1 or item.is_dir() or kind not in (0, 0o100000)
                        or item.file_size > 65536 or item.compress_size > 65536):
                    raise PackageRefused("A14_UNSAFE_ARCHIVE_ENTRY")
            manifest_bytes = archive.read("manifest.json")
            payload = archive.read("payload.bin")
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError) as exc:
        raise PackageRefused("A14_BAD_ZIP") from exc
    if not (0 < len(manifest_bytes) <= 4096 and 0 < len(payload) <= 32768):
        raise PackageRefused("A14_BOUNDED_CONTENT_REQUIRED")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(
                                  PackageRefused("A14_NONFINITE")))
    except (UnicodeError, ValueError) as exc:
        raise PackageRefused("A14_INVALID_MANIFEST") from exc
    if not isinstance(manifest, dict) or set(manifest) != _KEYS:
        raise PackageRefused("A14_MANIFEST_SCHEMA")
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["kind"] != "synthetic_private_data"
            or manifest["mode"] != "offline_paper_only"
            or manifest["mock_behavior"] not in ("healthy", "fail_start")
            or type(manifest["trust_generation"]) is not int
            or manifest["trust_generation"] < 1
            or type(manifest["release"]) is not str
            or not _RELEASE.fullmatch(manifest["release"])):
        raise PackageRefused("A14_FORBIDDEN_PACKAGE_CONTRACT")
    for key in ("engine_id", "engine_version", "installation_id"):
        if type(manifest[key]) is not str or not 1 <= len(manifest[key]) <= 100:
            raise PackageRefused("A14_INVALID_IDENTITY")
    for key in ("manifest_sha256", "payload_sha256"):
        if type(manifest[key]) is not str or not _SHA.fullmatch(manifest[key]):
            raise PackageRefused("A14_INVALID_DIGEST")
    if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(),
                               manifest["payload_sha256"]):
        raise PackageRefused("A14_PAYLOAD_TAMPERED")
    return manifest, payload


@dataclass(frozen=True, slots=True)
class PackageStatus:
    revision: int
    active: str | None
    previous: str | None
    state: str
    owned_mock_worker_running: bool
    live_trading_permitted: bool = False
    actual_private_engine_connected: bool = False


class MockPackageDeploymentManager:
    """Single private fixture, temp-only, immutable releases and atomic active pointer.

    A13 verification is mandatory for install/start/rollback. Stop remains
    possible during license revocation. A saved RUNNING state after a crash
    requires explicit reconciliation, never automatic restart.
    """

    def __init__(self, root: str | Path, *, provisioner, engine_id: str,
                 installation_id: str) -> None:
        root = Path(root)
        sandbox = Path(tempfile.gettempdir()).resolve()
        if (root.is_symlink() or not root.is_absolute() or
                not root.resolve().is_relative_to(sandbox) or
                root.resolve() == sandbox):
            raise PackageRefused("A14_TEMP_ROOT_ONLY")
        if root.exists() and (not root.is_dir() or root.is_symlink()):
            raise PackageRefused("A14_UNSAFE_ROOT")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.stat().st_mode & 0o077:
            raise PackageRefused("A14_ROOT_PERMISSIONS")
        self._root = root
        self._releases = root / "releases"
        if self._releases.is_symlink():
            raise PackageRefused("A14_UNSAFE_RELEASES")
        self._releases.mkdir(mode=0o700, exist_ok=True)
        self._state_path = root / "state.json"
        self._lock_path = root / "state.lock"
        self._runtime_path = root / "runtime.lock"
        self._provisioner = provisioner
        self._engine_id = engine_id
        self._installation_id = installation_id
        self._child: subprocess.Popen | None = None
        self._runtime_fd: int | None = None
        with self._locked():
            if not self._state_path.exists():
                _atomic_json(self._state_path, {
                    "schema": 1, "engine_id": engine_id,
                    "installation_id": installation_id, "revision": 0,
                    "active": None, "previous": None, "state": "STOPPED",
                })
            self._load()

    @contextlib.contextmanager
    def _locked(self):
        fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _load(self) -> dict:
        if self._state_path.is_symlink():
            raise PackageRefused("A14_UNSAFE_STATE")
        try:
            raw = self._state_path.read_bytes()
            if len(raw) > 4096:
                raise PackageRefused("A14_STATE_OVERSIZE")
            state = json.loads(raw, object_pairs_hook=_pairs)
        except (OSError, UnicodeError, ValueError) as exc:
            raise PackageRefused("A14_STATE_CORRUPT") from exc
        if (type(state) is not dict or set(state) != {
                "schema", "engine_id", "installation_id", "revision", "active", "previous", "state"
            } or state["schema"] != 1
            or state["engine_id"] != self._engine_id
            or state["installation_id"] != self._installation_id
            or type(state["revision"]) is not int or state["revision"] < 0
            or state["state"] not in ("STOPPED", "MOCK_RUNNING")
            or any(x is not None and
                   (type(x) is not str or not _SHA.fullmatch(x))
                   for x in (state["active"], state["previous"]))):
            raise PackageRefused("A14_STATE_INVALID")
        return state

    def _cas(self, state: dict, expected_revision: int) -> None:
        if type(expected_revision) is not int or state["revision"] != expected_revision:
            raise PackageRefused("A14_STALE_REVISION")

    def _admit(self, admission, now: int):
        if type(now) is not int:
            raise PackageRefused("A14_CLOCK_REQUIRED")
        record = self._provisioner.get(self._engine_id)
        health = self._provisioner.health(self._engine_id, admission=admission, now=now)
        if (record is None or record.status != "OFFLINE_VERIFIED"
                or record.installation_id != self._installation_id
                or not health.verified_offline):
            raise PackageRefused("A14_A13_FRESH_ADMISSION_REQUIRED")
        return record

    def _matches(self, manifest: dict, record) -> None:
        if (manifest["engine_id"] != self._engine_id
                or manifest["installation_id"] != self._installation_id
                or manifest["engine_version"] != self._provisioner._plugins.get(
                    self._engine_id).engine_version
                or manifest["manifest_sha256"] != record.manifest_sha256
                or manifest["trust_generation"] != record.generation):
            raise PackageRefused("A14_GRANT_OR_INSTALLATION_MISMATCH")

    def _verified_release(self, digest: str, record) -> dict:
        folder = self._releases / digest
        archive = folder / "package.zip"
        if folder.is_symlink() or archive.is_symlink() or not archive.is_file():
            raise PackageRefused("A14_RELEASE_MISSING_OR_UNSAFE")
        raw = archive.read_bytes()
        manifest, _ = inspect_bundle(raw, approved_sha256=digest)
        self._matches(manifest, record)
        return manifest

    def status(self) -> PackageStatus:
        with self._locked():
            state = self._load()
            running = self._child is not None and self._child.poll() is None
            persisted = state["state"]
            if persisted == "MOCK_RUNNING" and not running:
                persisted = "INTERRUPTED_RECONCILIATION_REQUIRED"
            return PackageStatus(state["revision"], state["active"],
                                 state["previous"], persisted, running)

    def install(self, raw: bytes, *, approved_sha256: str, expected_revision: int,
                admission, now: int) -> PackageStatus:
        manifest, _ = inspect_bundle(raw, approved_sha256=approved_sha256)
        record = self._admit(admission, now)
        self._matches(manifest, record)
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "STOPPED":
                raise PackageRefused("A14_STOP_BEFORE_INSTALL")
            if state["active"] == approved_sha256:
                raise PackageRefused("A14_ALREADY_ACTIVE")
            target = self._releases / approved_sha256
            if target.exists() or target.is_symlink():
                self._verified_release(approved_sha256, record)
            else:
                staging = Path(tempfile.mkdtemp(prefix=".stage-", dir=self._releases))
                try:
                    with (staging / "package.zip").open("xb") as handle:
                        os.fchmod(handle.fileno(), 0o600)
                        handle.write(raw)
                        handle.flush()
                        os.fsync(handle.fileno())
                    _sync_dir(staging)
                    os.rename(staging, target)
                    _sync_dir(self._releases)
                finally:
                    if staging.exists():
                        shutil.rmtree(staging)
            state["previous"], state["active"] = state["active"], approved_sha256
            state["revision"] += 1
            _atomic_json(self._state_path, state)
        return self.status()

    def _reserve_worker(self) -> None:
        fd = os.open(self._runtime_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise PackageRefused("A14_MOCK_WORKER_OWNED_ELSEWHERE") from exc
        self._runtime_fd = fd

    def _release_worker(self) -> None:
        if self._runtime_fd is not None:
            fcntl.flock(self._runtime_fd, fcntl.LOCK_UN)
            os.close(self._runtime_fd)
            self._runtime_fd = None

    def start(self, *, expected_revision: int, admission, now: int) -> PackageStatus:
        record = self._admit(admission, now)
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "STOPPED" or state["active"] is None:
                raise PackageRefused("A14_NOT_STOPPED_OR_INSTALLED")
            manifest = self._verified_release(state["active"], record)
            self._reserve_worker()
            try:
                if manifest["mock_behavior"] == "fail_start":
                    raise PackageRefused("A14_INJECTED_MOCK_START_FAILURE")
                self._child = subprocess.Popen(
                    [sys.executable, "-I", "-S", "-c", _WORKER],
                    cwd=self._root, env={"PYTHONNOUSERSITE": "1"},
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True,
                )
                time.sleep(0.05)
                if self._child.poll() is not None:
                    raise PackageRefused("A14_FIXTURE_WORKER_EXITED")
                state["state"] = "MOCK_RUNNING"
                state["revision"] += 1
                _atomic_json(self._state_path, state)
            except BaseException:
                self._halt()
                if state["previous"] is not None:
                    self._verified_release(state["previous"], record)
                    state["active"], state["previous"] = (
                        state["previous"], state["active"]
                    )
                    state["state"] = "STOPPED"
                    state["revision"] += 1
                    _atomic_json(self._state_path, state)
                raise
        return self.status()

    def _halt(self) -> None:
        child, self._child = self._child, None
        try:
            if child is not None:
                if child.stdin is not None:
                    try:
                        child.stdin.write(b"q")
                        child.stdin.close()
                    except (OSError, BrokenPipeError):
                        pass
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
        finally:
            self._release_worker()

    def stop(self, *, expected_revision: int) -> PackageStatus:
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "MOCK_RUNNING" or self._child is None:
                raise PackageRefused("A14_NO_OWNED_RUNNING_WORKER")
            self._halt()
            state["state"] = "STOPPED"
            state["revision"] += 1
            _atomic_json(self._state_path, state)
        return self.status()

    def reconcile_interrupted(self, *, expected_revision: int) -> PackageStatus:
        """Requires exclusive worker lock; never adopt/kill foreign PIDs."""
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "MOCK_RUNNING" or self._child is not None:
                raise PackageRefused("A14_NOT_INTERRUPTED")
            self._reserve_worker()
            try:
                state["state"] = "STOPPED"
                state["revision"] += 1
                _atomic_json(self._state_path, state)
            finally:
                self._release_worker()
        return self.status()

    def rollback(self, *, expected_revision: int, admission, now: int) -> PackageStatus:
        record = self._admit(admission, now)
        with self._locked():
            state = self._load()
            self._cas(state, expected_revision)
            if state["state"] != "STOPPED" or state["previous"] is None:
                raise PackageRefused("A14_ROLLBACK_REQUIRES_STOPPED_PREVIOUS")
            self._verified_release(state["previous"], record)
            state["active"], state["previous"] = state["previous"], state["active"]
            state["revision"] += 1
            _atomic_json(self._state_path, state)
        return self.status()

    def close(self) -> None:
        if self._child is not None:
            self.stop(expected_revision=self.status().revision)
