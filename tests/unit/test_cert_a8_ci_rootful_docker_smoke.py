"""CERT-A8 mock-only regressions; never invoke a real Docker daemon here."""
from __future__ import annotations

import json
import subprocess

import pytest

from scripts import ci_cert_a8_rootful_docker_smoke as a8

_FACTS = {
    "nonroot": True,
    "root_readonly": True,
    "tempfs_writable": True,
    "loopback_only": True,
    "no_effective_caps_and_nnp": True,
    "bounded_resources": True,
    "no_named_secret_env": True,
}


@pytest.fixture(autouse=True)
def _ci_fixture(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_CERT_A8_BENIGN_DOCKER_ONLY", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(a8.os, "geteuid", lambda: 1001)


def _result(code=0, *, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess((), code, stdout=stdout, stderr=stderr)


def _fake_docker(monkeypatch, *, facts=None, orphan=False, code=0, error=None):
    commands = []

    def call(args, *, timeout):
        assert isinstance(args, tuple)
        assert args[:3] == (
            "/usr/bin/docker", "--host", "unix:///var/run/docker.sock",
        )
        commands.append((args, timeout))
        verb = args[3]
        if verb == "run":
            if error is not None:
                raise a8.CertA8Refused(error)
            payload = _FACTS if facts is None else facts
            return _result(code, stdout=json.dumps(payload).encode("ascii"))
        if verb == "rm":
            return _result(1, stderr=b"already removed")
        if verb == "info":
            return _result(0, stdout=b"29.8.2")
        if verb == "container":
            name = args[-1].encode("ascii")
            return (_result(0) if orphan
                    else _result(1, stderr=b"Error: No such object: " + name))
        pytest.fail("UNEXPECTED_DOCKER_OPERATION")

    monkeypatch.setattr(a8, "_call", call)
    return commands


def test_real_benign_probe_command_is_hardcoded_and_authority_denied(monkeypatch):
    calls = _fake_docker(monkeypatch)
    got = a8.smoke()
    assert got.checked_facts == len(_FACTS)
    assert got.cleanup_observed
    assert got.status == "CERT_A8_GITHUB_ROOTFUL_DOCKER_FIXTURE_NOT_GVISOR_CERTIFIED"
    assert not got.host_isolation_certified
    assert not got.real_worker_execution_authorized
    assert not got.arbitrary_code_permitted
    assert not got.runtime_a6_unlocked
    assert not got.broker_authorized
    assert not got.telegram_authorized
    assert not got.production_authorized
    assert [c[0][3] for c in calls] == ["run", "rm", "info", "container"]
    run = calls[0][0]
    for flag in (
        "--rm", "--pull=never", "--network=none", "--ipc=none",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=32",
        "--memory=128m", "--memory-swap=128m", "--cpus=0.5",
        "--ulimit=nofile=64:64", "--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
        "--entrypoint=/usr/local/bin/python",
    ):
        assert flag in run
    assert "--runtime=runsc" not in run
    assert not any(
        x.startswith(("--volume", "--mount", "-v", "--privileged",
                      "--network=host", "--device", "--env-file")) for x in run
    )
    assert run[-5:] == (
        "mmt/runtime-a2-candidate:pr", "-I", "-S", "-c", a8._PROBE,
    )
    assert calls[0][1] == 20
    assert calls[1][0][-1] == run[run.index(
        "--name=" + calls[1][0][-1],
    )].removeprefix("--name=")


@pytest.mark.parametrize("missing", [
    "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "MMT_NONPRODUCTION",
    "MMT_CERT_A8_BENIGN_DOCKER_ONLY",
])
def test_missing_explicit_ci_context_refuses_before_any_docker(
    monkeypatch, missing,
):
    monkeypatch.delenv(missing)
    monkeypatch.setattr(
        a8, "_call", lambda *args, **kw: pytest.fail("DOCKER_NOT_ALLOWED"),
    )
    with pytest.raises(a8.CertA8Refused, match="CERT_A8_GITHUB_HOSTED_FIXED_FIXTURE_ONLY"):
        a8.smoke()


@pytest.mark.parametrize("bad", ["prod", "root", "self_hosted"])
def test_production_root_or_self_hosted_refused(monkeypatch, bad):
    if bad == "prod":
        monkeypatch.setenv("MMT_PRODUCTION", "1")
    elif bad == "root":
        monkeypatch.setattr(a8.os, "geteuid", lambda: 0)
    else:
        monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")
    monkeypatch.setattr(
        a8, "_call", lambda *args, **kw: pytest.fail("DOCKER_NOT_ALLOWED"),
    )
    with pytest.raises(a8.CertA8Refused, match="CERT_A8_GITHUB_HOSTED_FIXED_FIXTURE_ONLY"):
        a8.smoke()


@pytest.mark.parametrize("broken", tuple(_FACTS))
def test_each_failed_guest_observation_refused_with_cleanup(monkeypatch, broken):
    calls = _fake_docker(monkeypatch, facts=_FACTS | {broken: False})
    with pytest.raises(a8.CertA8Refused, match="CERT_A8_CONFINEMENT_FIXTURE_REFUSED"):
        a8.smoke()
    assert [c[0][3] for c in calls] == ["run", "rm", "info", "container"]


def test_timeout_fails_closed_and_still_checks_cleanup(monkeypatch):
    calls = _fake_docker(monkeypatch, error="CERT_A8_DOCKER_UNAVAILABLE_OR_TIMEOUT")
    with pytest.raises(a8.CertA8Refused, match="CERT_A8_DOCKER_UNAVAILABLE_OR_TIMEOUT"):
        a8.smoke()
    assert [c[0][3] for c in calls] == ["run", "rm", "info", "container"]


def test_orphan_check_is_mandatory_even_after_positive_probe(monkeypatch):
    calls = _fake_docker(monkeypatch, orphan=True)
    with pytest.raises(a8.CertA8Refused, match="CERT_A8_DOCKER_CLEANUP_UNPROVEN"):
        a8.smoke()
    assert calls[-1][0][3:5] == ("container", "inspect")


def test_failed_docker_run_is_not_silently_accepted(monkeypatch):
    calls = _fake_docker(monkeypatch, code=125)
    with pytest.raises(a8.CertA8Refused, match="CERT_A8_FIXED_DOCKER_PROBE_FAILED"):
        a8.smoke()
    assert len(calls) == 4


@pytest.mark.parametrize("raw", [
    b"", b"not-json", b'{"nonroot":true,"nonroot":true}',
    b'{"nonroot":true}', b'[]', b"[]" * 4000,
    json.dumps(_FACTS | {"extra": True}).encode(),
    json.dumps(_FACTS | {"bounded_resources": 1}).encode(),
])
def test_strict_guest_parser_does_not_trust_forged_result(raw):
    with pytest.raises(a8.CertA8Refused):
        a8._strict_result(raw)


def test_subprocess_has_no_shell_no_credentials_and_bounded_wait(monkeypatch):
    observed = []

    def fake_run(args, **kwargs):
        observed.append((args, kwargs))
        return _result(stdout=b"OK")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert a8._call((*a8._DOCKER, "info"), timeout=3).stdout == b"OK"
    assert observed[0][1]["shell"] is False
    assert observed[0][1]["close_fds"] is True
    assert observed[0][1]["env"] == {
        "PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
        "DOCKER_CONFIG": "/nonexistent",
    }
    assert observed[0][1]["stdin"] == subprocess.DEVNULL
    assert observed[0][1]["timeout"] == 3
    with pytest.raises(a8.CertA8Refused, match="CERT_A8_UNEXPECTED_DOCKER_ENDPOINT"):
        a8._call(("docker", "run", "something"), timeout=3)
