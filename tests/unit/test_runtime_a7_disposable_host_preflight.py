"""A7 mock-only denial tests, never run Docker."""
from __future__ import annotations

import hashlib
import socket
import subprocess

import pytest

import naseri_markets.runtime_a7_disposable_host_preflight as a7

IMAGE = "registry.invalid/fixture@sha256:" + "a" * 64


def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(a7.os, "geteuid", lambda: 1001)
    runsc = tmp_path / "runsc"
    runsc.write_bytes(b"offline-only-binary-fixture")
    runsc.chmod(0o700)
    pin = hashlib.sha256(runsc.read_bytes()).hexdigest()
    monkeypatch.setattr(a7, "safe_socket", lambda uid: "unix:///fake/docker.sock")
    return runsc, pin


def observe(runsc, pin):
    return a7.preflight(
        host="disposable.a7.test", image=IMAGE,
        runsc=runsc, sha=pin, operator_ack=True,
    )


def mock_queries(monkeypatch, runsc, broken=""):
    calls = []

    def respond(args):
        calls.append(args)
        if args[0] == str(runsc):
            return b"runsc version CI-fixture"
        if ".SecurityOptions" in args[-1]:
            return (b'["name=seccomp,profile=builtin"]'
                    if broken == "rootless"
                    else b'["name=rootless","name=seccomp,profile=builtin"]')
        if ".Runtimes" in args[-1]:
            data = {} if broken == "runsc" else {"runsc": {"path": str(runsc)}}
            return a7.json.dumps(data).encode()
        if ".RepoDigests" in args[-1]:
            return a7.json.dumps([] if broken == "image" else [IMAGE]).encode()
        if ".Id" in args[-1]:
            return b"sha256:" + b"c" * 64
        raise AssertionError("unexpected read-only query")

    monkeypatch.setattr(a7, "query", respond)
    return calls


def test_passive_not_certification(tmp_path, monkeypatch):
    runsc, pin = fixture(tmp_path, monkeypatch)
    calls = mock_queries(monkeypatch, runsc)
    result = observe(runsc, pin)
    assert result.status == "A7_PASSIVE_OBSERVATION_NOT_CERTIFIED"
    assert not result.execution_authorized
    assert not result.fixed_fixture_executed
    assert not result.kernel_isolation_proved
    assert not result.independently_attested
    assert not result.broker_permitted
    assert not result.telegram_permitted
    assert len(calls) == 5


@pytest.mark.parametrize("missing", ["rootless", "runsc", "image"])
def test_missing_runtime_or_pins_denied(tmp_path, monkeypatch, missing):
    runsc, pin = fixture(tmp_path, monkeypatch)
    mock_queries(monkeypatch, runsc, missing)
    with pytest.raises(a7.A7Refused):
        observe(runsc, pin)


def test_no_ack_production_root_and_corrupt_pin(tmp_path, monkeypatch):
    runsc, pin = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        a7, "query", lambda _: pytest.fail("should not query any host")
    )
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(a7.A7Refused, match="A7_NONPRODUCTION_ONLY"):
        observe(runsc, pin)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(a7.A7Refused, match="A7_DISPOSABLE_OPERATOR_ACK_REQUIRED"):
        a7.preflight(host="disposable.a7.test", image=IMAGE, runsc=runsc, sha=pin)
    with pytest.raises(a7.A7Refused, match="A7_RUNSC_PIN_MISMATCH"):
        observe(runsc, "0" * 64)
    monkeypatch.setattr(a7.os, "geteuid", lambda: 0)
    with pytest.raises(a7.A7Refused, match="A7_DISPOSABLE_OPERATOR_ACK_REQUIRED"):
        observe(runsc, pin)
    monkeypatch.setattr(a7.os, "geteuid", lambda: 1001)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(a7.A7Refused, match="A7_NONPRODUCTION_ONLY"):
        observe(runsc, pin)


def test_private_socket_mode(tmp_path, monkeypatch):
    path = tmp_path / "docker.sock"
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        path.chmod(0o600)
        real_lstat = a7.Path.lstat

        def fake_lstat(self):
            if str(self).startswith("/run/user/"):
                return path.stat()
            return real_lstat(self)

        monkeypatch.setattr(a7.Path, "lstat", fake_lstat)
        assert a7.safe_socket(path.stat().st_uid).startswith("unix:///run/user/")
        path.chmod(0o666)
        with pytest.raises(a7.A7Refused, match="A7_ROOTLESS_SOCKET_UNTRUSTED"):
            a7.safe_socket(path.stat().st_uid)


def test_host_command_allowlist_and_secret_redaction(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        class Outcome:
            returncode = 1
            stdout = b"PRIVATE_DATA"
        return Outcome()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(a7.A7Refused, match="A7_COMMAND_NOT_READONLY"):
        a7.query(("/usr/bin/docker", "--host", "unix:///fake", "run", "x"))
    assert not calls
    with pytest.raises(a7.A7Refused, match="A7_HOST_QUERY_FAILED") as exc:
        a7.query(("/usr/bin/docker", "--host", "unix:///fake",
                  "info", "--format", "{{json .SecurityOptions}}"))
    assert "PRIVATE_DATA" not in str(exc.value)
    assert calls[0][1]["shell"] is False


def test_duplicate_json_refused():
    with pytest.raises(a7.A7Refused, match="A7_DUPLICATE_JSON_FIELD"):
        a7.parsed(b'{"a":1,"a":2}')
