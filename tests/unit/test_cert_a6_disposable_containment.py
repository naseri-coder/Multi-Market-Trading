"""CERT-A6 mock-only probe/cleanup tests. No OCI or host commands in CI."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from naseri_markets import cert_a6_disposable_containment as a6

IMAGE = "registry.invalid/fixture@sha256:" + "a" * 64
RUNSC = Path("/usr/local/bin/runsc")
RUNSC_SHA = "b" * 64
PROBE_OK = {
    "nonroot": True,
    "rootfs_write_refused": True,
    "external_tcp_refused": True,
    "no_named_secrets": True,
}


def _result(code: int, out: bytes = b"", err: bytes = b""):
    return subprocess.CompletedProcess((), code, stdout=out, stderr=err)


def _test_host(monkeypatch, *, report=None, run_error=None,
               cleanup_success=True):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(a6.os, "geteuid", lambda: 1001)
    audits = []
    monkeypatch.setattr(a6.a7, "preflight", lambda **kwargs: audits.append(kwargs))
    monkeypatch.setattr(
        a6.a7, "safe_socket",
        lambda uid: "unix:///run/user/1001/docker.sock",
    )
    invoked = []

    def call(args, *, timeout):
        invoked.append((args, timeout))
        assert args[0] == "/usr/bin/docker"
        assert "--host" in args
        assert "unix:///run/user/1001/docker.sock" in args
        if "run" in args:
            if run_error is not None:
                raise a6.CertA6Refused(run_error)
            return _result(
                0, json.dumps(report or PROBE_OK, sort_keys=True).encode(),
            )
        if "rm" in args:
            return _result(0)
        if "info" in args:
            return _result(0, b'["name=rootless"]')
        if "inspect" in args:
            name = args[-1].encode("ascii")
            return (_result(1, err=b"Error: No such object: " + name)
                    if cleanup_success else _result(0))
        pytest.fail("UNEXPECTED_DOCKER_COMMAND")

    monkeypatch.setattr(a6, "_call", call)
    return audits, invoked


def _assess(**kwargs):
    return a6.assess(
        host_id="disposable.cert-a6.test", image=IMAGE,
        runsc=RUNSC, runsc_sha256=RUNSC_SHA,
        operator_ack=True, **kwargs,
    )


def test_fixed_probe_command_and_observation_have_no_authority(monkeypatch):
    audits, invoked = _test_host(monkeypatch)
    got = _assess()
    assert got.host_id == "disposable.cert-a6.test"
    assert got.worker_image_sha256 == "a" * 64
    assert got.runsc_sha256 == RUNSC_SHA
    assert got.probe_sha256
    assert got.network_probe_refused
    assert got.rootfs_probe_refused
    assert got.nonroot_probe_passed
    assert got.named_secret_probe_passed
    assert got.cleanup_checked
    assert got.status == "CERT_A6_FIXED_PROBE_OBSERVED_NOT_INDEPENDENTLY_CERTIFIED"
    assert not got.independent_host_isolation_certified
    assert not got.arbitrary_core_execution_authorized
    assert not got.runtime_a6_unlocked
    assert not got.broker_authorized
    assert not got.telegram_authorized
    assert not got.production_authorized
    assert len(audits) == 1
    assert audits[0]["operator_ack"] is True
    assert [x[0][3] for x in invoked] == ["run", "rm", "info", "container"]
    command = invoked[0][0]
    for required in (
        "--runtime=runsc", "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=32", "--memory=128m", "--memory-swap=128m",
        "--user=65534:65534", "--pull=never", "--ipc=none",
    ):
        assert required in command
    assert "--privileged" not in command
    assert not any(arg.startswith("--volume=") or arg == "-v" for arg in command)
    assert command[-5:] == (IMAGE, "-I", "-S", "-c", a6._PROBE)
    assert invoked[1][0][-1].startswith("mmt-cert-a6-")
    assert invoked[1][0][-1] == command[command.index("--name=" +
           invoked[1][0][-1])].removeprefix("--name=")


@pytest.mark.parametrize("bad_env", ["no_opt_in", "not_approved", "production"])
def test_scope_gate_precedes_even_passive_preflight(monkeypatch, bad_env):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    if bad_env == "no_opt_in":
        monkeypatch.delenv("MMT_NONPRODUCTION")
    elif bad_env == "not_approved":
        monkeypatch.delenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED")
    else:
        monkeypatch.setenv("MMT_PRODUCTION", "1")
    monkeypatch.setattr(
        a6.a7, "preflight", lambda **kwargs: pytest.fail("NO_HOST_QUERY")
    )
    with pytest.raises(a6.CertA6Refused, match="CERT_A6_EXPLICIT_DISPOSABLE_ONLY"):
        _assess()


def test_missing_ack_never_touches_host(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(
        a6.a7, "preflight", lambda **kwargs: pytest.fail("NO_HOST_QUERY")
    )
    with pytest.raises(a6.CertA6Refused, match="CERT_A6_OPERATOR_ACK_REQUIRED"):
        a6.assess(host_id="disposable.test", image=IMAGE, runsc=RUNSC,
                  runsc_sha256=RUNSC_SHA)


def test_failed_a7_refuses_before_docker_run(monkeypatch):
    _test_host(monkeypatch)
    def a7_denied(**kwargs):
        raise a6.a7.A7Refused("A7_PIN_MISMATCH")
    monkeypatch.setattr(a6.a7, "preflight", a7_denied)
    monkeypatch.setattr(a6, "_call", lambda *a, **kw: pytest.fail("NO_DOCKER"))
    with pytest.raises(a6.CertA6Refused, match="CERT_A6_A7_PREFLIGHT_REQUIRED"):
        _assess()


@pytest.mark.parametrize("key", list(PROBE_OK))
def test_any_failed_inside_probe_refuses_and_checks_cleanup(monkeypatch, key):
    broken = PROBE_OK | {key: False}
    _, invocations = _test_host(monkeypatch, report=broken)
    with pytest.raises(a6.CertA6Refused, match="CERT_A6_CONTAINMENT_PROBE_NOT_PASSED"):
        _assess()
    assert [x[0][3] for x in invocations] == ["run", "rm", "info", "container"]


def test_orphan_or_cleanup_not_proved_refused(monkeypatch):
    _test_host(monkeypatch, cleanup_success=False)
    with pytest.raises(a6.CertA6Refused, match="CERT_A6_CLEANUP_NOT_OBSERVED"):
        _assess()


def test_worker_timeout_is_denied_even_when_cleanup_observed(monkeypatch):
    _test_host(monkeypatch, run_error="CERT_A6_HOST_COMMAND_FAILED")
    with pytest.raises(a6.CertA6Refused, match="CERT_A6_HOST_COMMAND_FAILED"):
        _assess()


@pytest.mark.parametrize("wire", [
    b"", b"not-json", b'{"nonroot":true,"nonroot":true}',
    b'{"nonroot":true}', json.dumps(PROBE_OK | {"extra": True}).encode(),
    json.dumps(PROBE_OK | {"nonroot": 1}).encode(),
    b"x" * 4097,
])
def test_probe_refuses_noncanonical_or_forged_result(wire):
    with pytest.raises(a6.CertA6Refused):
        a6._strict_json(wire)


def test_shell_never_used_and_subprocess_environment_is_minimal(monkeypatch):
    captured = []
    def fake_run(args, **kwargs):
        captured.append((args, kwargs))
        return _result(0, b"OK")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert a6._call(("/usr/bin/docker", "info"), timeout=3).stdout == b"OK"
    kwargs = captured[0][1]
    assert kwargs["shell"] is False
    assert kwargs["close_fds"] is True
    assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
    assert kwargs["timeout"] == 3
    assert kwargs["stdin"] == subprocess.DEVNULL
