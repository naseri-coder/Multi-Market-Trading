"""Stage23 FIXED canary unit tests only; no real Docker/gVisor is launched."""
from __future__ import annotations

import json
import os

import pytest

from naseri_markets import disposable_gvisor_canary_stage23_v1 as probe
from naseri_markets.disposable_gvisor_canary_stage23_v1 import (
    HostCanaryRefused, _CANARY, _parse_probe, run_manual_disposable_host_canary,
)
from naseri_markets.secure_plugin_runtime_v1 import (
    SecurePluginPolicy, build_run_command,
)
from test_secure_plugin_runtime_v1 import IMAGE


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.delenv("MMT_DISPOSABLE_SANDBOX_HOST", raising=False)


def policy(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1001)
    return SecurePluginPolicy(
        enabled=True, image=IMAGE, docker_binary="/usr/bin/docker",
        docker_socket="unix:///run/user/1001/docker.sock")


def good(nonce):
    return json.dumps({
        "schema": 1, "nonce": nonce,
        "checks": {check: True for check in probe._REQUIRED},
    }, separators=(",", ":")).encode()


def test_reject_without_disposable_ack_or_env_before_any_launch(monkeypatch):
    p = policy(monkeypatch)
    calls = []
    monkeypatch.setattr(probe, "_invoke", lambda *_: calls.append(1))
    with pytest.raises(HostCanaryRefused, match="EXPLICIT_DISPOSABLE"):
        run_manual_disposable_host_canary(p, operator_ack=True)
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    with pytest.raises(HostCanaryRefused, match="EXPLICIT_DISPOSABLE"):
        run_manual_disposable_host_canary(p)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(HostCanaryRefused, match="EXPLICIT_DISPOSABLE"):
        run_manual_disposable_host_canary(p, operator_ack=True)
    assert calls == []


def test_simulated_one_canary_contract_not_real_isolation(monkeypatch):
    p = policy(monkeypatch)
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    asserted = []
    monkeypatch.setattr(probe, "_assert_rootless_socket",
                        lambda current: asserted.append("socket"))
    monkeypatch.setattr(probe, "_ensure_rootless_daemon",
                        lambda current: asserted.append("daemon"))
    monkeypatch.setattr(probe, "_prove_container_absent",
                        lambda policy, name: asserted.append("cleanup"))
    def synthetic_run(_p, name, framed):
        assert name.startswith("mmt-core-")
        assert len(name) == len("mmt-core-") + 24
        source_bytes = framed[4:4+int.from_bytes(framed[:4], "big")]
        assert source_bytes == _CANARY.encode()
        data = json.loads(framed[4+len(source_bytes):])
        asserted.append("invoke")
        return good(data["nonce"])
    monkeypatch.setattr(probe, "_invoke", synthetic_run)
    report = run_manual_disposable_host_canary(p, operator_ack=True)
    assert report.complete
    assert all(report.checks.values())
    assert asserted == ["socket", "daemon", "invoke", "cleanup"]
    assert report.status == "OBSERVED_SINGLE_DISPOSABLE_HOST_CANARY_NOT_SECURITY_CERTIFIED"
    assert not report.actual_host_isolation_independently_audited
    assert not report.publisher_trust_conferred
    assert not report.user_code_executed
    assert not report.public_plugin_install_authorized
    assert not report.live_trading_authorized
    assert not report.telegram_sent
    assert not report.broker_order_sent


@pytest.mark.parametrize("transform", [
    lambda d: {**d, "nonce": "wrong"},
    lambda d: {**d, "schema": True},
    lambda d: {**d, "unexpected": "extra"},
    lambda d: {**d, "checks": {**d["checks"], "uid_unprivileged": False}},
    lambda d: {**d, "checks": {**d["checks"], "rootfs_readonly": "true"}},
    lambda d: {**d, "checks": {"uid_unprivileged": True}},
])
def test_failclosed_probe_contract_for_all_negative_results(transform):
    datum = json.loads(good("nonce123"))
    with pytest.raises(HostCanaryRefused, match="FAILED_OR_FORGED"):
        _parse_probe(json.dumps(transform(datum)).encode(), "nonce123")


def test_reject_malformed_and_duplicate_source_probe():
    with pytest.raises(HostCanaryRefused, match="DUPLICATE"):
        _parse_probe(b'{"schema":1,"schema":1,"nonce":"x","checks":{}}', "x")
    with pytest.raises(HostCanaryRefused, match="BOUNDED"):
        _parse_probe(b"x" * 5000, "a")
    with pytest.raises(HostCanaryRefused, match="MALFORMED"):
        _parse_probe(b"{", "x")


def test_nonzero_exit_or_unproven_orphan_fails_closed(monkeypatch):
    p = policy(monkeypatch)
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    monkeypatch.setattr(probe, "_assert_rootless_socket", lambda _: None)
    monkeypatch.setattr(probe, "_ensure_rootless_daemon", lambda _: None)
    monkeypatch.setattr(probe, "_invoke", lambda *_args: b"bad")
    monkeypatch.setattr(probe, "_prove_container_absent",
                        lambda *_args: (_ for _ in ()).throw(
                            HostCanaryRefused("ORPHAN_CONTAINER_NOT_RULED_OUT")))
    with pytest.raises(HostCanaryRefused, match="ORPHAN_CONTAINER_NOT_RULED_OUT"):
        run_manual_disposable_host_canary(p, operator_ack=True)


def test_fixed_stage4_command_has_no_host_mount_network_or_privileged_exec(monkeypatch):
    p = policy(monkeypatch)
    cmd = build_run_command(p, "mmt-core-"+"0"*24)
    assert "--runtime=runsc" in cmd
    assert "--pull=never" in cmd
    assert "--network=none" in cmd
    assert "--read-only" in cmd
    assert "--user=65534:65534" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--security-opt=no-new-privileges" in cmd
    assert not any(x.startswith("--volume") or x.startswith("--mount")
                   or x == "--privileged" for x in cmd)
    assert "192.0.2.1" in _CANARY
    assert "api_key" not in _CANARY
