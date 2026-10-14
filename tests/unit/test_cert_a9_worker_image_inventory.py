"""CERT-A9: MOCK-ONLY installed-image review tests. No real Docker here."""
from __future__ import annotations

import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from naseri_markets.runtime_a8_supply_chain import verify_source_lock
from scripts import ci_cert_a9_worker_image_inventory as a9

IMAGE_ID = "sha256:" + "b" * 64
VERSIONS = {
    "python_version": "3.12.12",
    "node_version": "18.20.4",
    "npm_version": "9.2.0",
    "typescript_version": "5.9.3",
    "wasmtime_version": "49.0.0",
    "worker_sha256": "a" * 64,
}


@pytest.fixture(autouse=True)
def _ci_context(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_CERT_A9_INSTALLED_IMAGE_ONLY", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(a9.os, "geteuid", lambda: 1001)


def _reply(code=0, *, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess((), code, stdout=stdout, stderr=stderr)


def _fake_host(monkeypatch, *, versions=None, orphan=False, run_error=None,
               changed_image=False):
    monkeypatch.setattr(
        a9, "verify_source_lock",
        lambda *args: SimpleNamespace(checked_files=3),
    )
    monkeypatch.setattr(
        a9.hashlib, "sha256",
        a9.hashlib.sha256,
    )
    calls = []
    image_checks = 0

    def call(argv, *, timeout):
        nonlocal image_checks
        assert argv[:len(a9._DOCKER)] == a9._DOCKER
        calls.append((argv, timeout))
        command = argv[len(a9._DOCKER)]
        if command == "image":
            image_checks += 1
            image_id = (
                "sha256:" + "c" * 64
                if changed_image and image_checks == 2 else IMAGE_ID
            )
            return _reply(stdout=(image_id + "\n").encode("ascii"))
        if command == "run":
            if run_error is not None:
                raise a9.CertA9Refused(run_error)
            source_sha = hashlib.sha256(
                (a9._ROOT / "scripts/runtime_a2_worker.py").read_bytes(),
            ).hexdigest()
            inventory = VERSIONS | {"worker_sha256": source_sha}
            if versions is not None:
                inventory.update(versions)
            return _reply(stdout=json.dumps(inventory, sort_keys=True).encode())
        if command == "rm":
            return _reply()
        if command == "container":
            name = argv[-1].encode("ascii")
            return (_reply(0) if orphan
                    else _reply(1, stderr=b"Error: No such object: " + name))
        if command == "info":
            return _reply(stdout=b"29.8.2")
        pytest.fail("UNEXPECTED_CI_DOCKER_COMMAND")

    monkeypatch.setattr(a9, "_call", call)
    return calls


def test_real_source_lock_is_still_exactly_pinned():
    root = a9._ROOT
    result = verify_source_lock(
        root, root / "deploy/runtime_a2/a8_source_lock.json",
    )
    assert result.checked_files == 3
    assert not result.worker_execution_authorized


def test_local_image_and_installed_version_inventory_mock(monkeypatch):
    calls = _fake_host(monkeypatch)
    result = a9.review()
    assert result.image_id == IMAGE_ID
    assert result.worker_sha256 == hashlib.sha256(
        (a9._ROOT / "scripts/runtime_a2_worker.py").read_bytes(),
    ).hexdigest()
    assert result.python_version == "3.12.12"
    assert result.node_version == "18.20.4"
    assert result.npm_version == "9.2.0"
    assert result.typescript_version == "5.9.3"
    assert result.wasmtime_version == "49.0.0"
    assert len(result.inventory_fingerprint_sha256) == 64
    assert result.source_lock_checked and result.image_unchanged_during_probe
    assert not result.independent_publisher_verified
    assert not result.base_image_digest_pinned
    assert not result.apt_packages_immutable
    assert not result.npm_tarball_integrity_verified
    assert not result.wheel_integrity_verified
    assert not result.independently_reproducible
    assert not result.host_isolation_certified
    assert not result.worker_execution_authorized
    assert not result.broker_authorized
    assert not result.telegram_authorized
    assert not result.production_authorized
    assert [a[len(a9._DOCKER)] for a, _ in calls] == [
        "image", "run", "rm", "container", "info", "image",
    ]
    run = calls[1][0]
    assert "--pull=never" in run and "--network=none" in run
    assert "--read-only" in run and "--cap-drop=ALL" in run
    assert "--user=65534:65534" in run
    assert not any(
        flag.startswith(("--privileged", "--mount", "--volume",
                         "--network=host", "--env-file"))
        for flag in run
    )
    assert run[-4:] == ("-I", "-c", a9._PROBE, ) or run[-5:] == (
        a9._IMAGE, "-I", "-c", a9._PROBE,
    )


@pytest.mark.parametrize("env", [
    "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "MMT_NONPRODUCTION",
    "MMT_CERT_A9_INSTALLED_IMAGE_ONLY",
])
def test_missing_scope_refused_without_host_interaction(monkeypatch, env):
    monkeypatch.delenv(env)
    monkeypatch.setattr(
        a9, "_call", lambda *args, **kwargs: pytest.fail("HOST_NOT_ALLOWED"),
    )
    with pytest.raises(a9.CertA9Refused, match="CERT_A9_EXPLICIT_HOSTED_CI_SCOPE_REQUIRED"):
        a9.review()


@pytest.mark.parametrize("state", ["production", "root", "self_hosted"])
def test_unsafe_scope_refused(monkeypatch, state):
    if state == "production":
        monkeypatch.setenv("MMT_PRODUCTION", "1")
    elif state == "root":
        monkeypatch.setattr(a9.os, "geteuid", lambda: 0)
    else:
        monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")
    monkeypatch.setattr(
        a9, "_call", lambda *args, **kwargs: pytest.fail("HOST_NOT_ALLOWED"),
    )
    with pytest.raises(a9.CertA9Refused, match="CERT_A9_EXPLICIT_HOSTED_CI_SCOPE_REQUIRED"):
        a9.review()


@pytest.mark.parametrize("override", [
    {"worker_sha256": "c" * 64},
    {"python_version": "3.13.0"},
    {"typescript_version": "5.9.2"},
    {"wasmtime_version": "50.0.0"},
    {"node_version": "16.20.0"},
    {"npm_version": "invalid"},
    {"node_version": True},
    {"unexpected": "9.0.0"},
])
def test_dependency_or_worker_drift_always_denied(monkeypatch, override):
    _fake_host(monkeypatch, versions=override)
    with pytest.raises(a9.CertA9Refused):
        a9.review()


def test_local_image_replacement_detected(monkeypatch):
    _fake_host(monkeypatch, changed_image=True)
    with pytest.raises(a9.CertA9Refused, match="CERT_A9_LOCAL_IMAGE_ID_CHANGED_DURING_REVIEW"):
        a9.review()


def test_cleanup_orphan_is_not_silently_successful(monkeypatch):
    calls = _fake_host(monkeypatch, orphan=True)
    with pytest.raises(a9.CertA9Refused, match="CERT_A9_CLEANUP_NOT_OBSERVED"):
        a9.review()
    assert any(a[len(a9._DOCKER)] == "container" for a, _ in calls)


def test_timeout_still_checks_cleanup(monkeypatch):
    calls = _fake_host(monkeypatch, run_error="CERT_A9_DOCKER_UNAVAILABLE_OR_TIMEOUT")
    with pytest.raises(a9.CertA9Refused, match="CERT_A9_DOCKER_UNAVAILABLE_OR_TIMEOUT"):
        a9.review()
    assert [a[len(a9._DOCKER)] for a, _ in calls] == [
        "image", "run", "rm", "container", "info",
    ]


@pytest.mark.parametrize("bad", [
    b"", b"invalid", b'{"node_version":"18.20.4","node_version":"18.20.4"}',
    b"[]", json.dumps(VERSIONS | {"extra": "bad"}).encode(),
    json.dumps(VERSIONS | {"wasmtime_version": 49}).encode(),
    json.dumps(VERSIONS | {"typescript_version": "6.0.0"}).encode(),
])
def test_malformed_or_untrusted_inventory_never_grants_authority(bad):
    with pytest.raises(a9.CertA9Refused):
        a9._strict_versions(bad, "a" * 64)


def test_subprocess_removes_inherited_environment_and_shell(monkeypatch):
    observed = []

    def fake_run(args, **kwargs):
        observed.append(kwargs)
        return _reply(stdout=b"ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = a9._call((*a9._DOCKER, "image", "ls"), timeout=4)
    assert result.stdout == b"ok"
    assert observed[0]["shell"] is False
    assert observed[0]["close_fds"] is True
    assert observed[0]["env"] == {
        "PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
        "DOCKER_CONFIG": "/nonexistent",
    }
    assert observed[0]["stdin"] == subprocess.DEVNULL
    assert observed[0]["timeout"] == 4
    with pytest.raises(a9.CertA9Refused, match="CERT_A9_UNEXPECTED_DOCKER_ENDPOINT"):
        a9._call(("docker", "run", "unexpected"), timeout=4)
