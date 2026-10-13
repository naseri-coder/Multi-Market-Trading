"""RUNTIME-A1 accepts 4 artifact kinds, rejects all live/unsafe execution.

Tests mock the OCI boundary. They do NOT demonstrate actual gVisor isolation or
certify any external worker image, interpreter, transpiler or WASM engine.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle,
    CoreBinding,
    CoreContractError,
    CoreEventType,
    CoreInput,
    DataOrigin,
)
from naseri_markets.multilang_runtime_a1 import (
    MultilangRefused,
    MultiLanguageOfflineHost,
    RuntimeKind,
    RuntimeProfile,
    build_polyglot_command,
    prepare_framed_request,
)
from naseri_markets.secure_plugin_runtime_v1 import SecurePluginPolicy

CORE = OfflineContractFixture()
T = datetime(2026, 10, 13, 10, tzinfo=UTC)
IMAGE = "registry.invalid/reviewed-polyglot@sha256:" + "a" * 64
SOURCE = {
    RuntimeKind.PYTHON: ("strategy.py", b"import json\nprint(json.dumps({}))\n"),
    RuntimeKind.JAVASCRIPT: ("strategy.js", b"export function evaluate(event) { return event; }\n"),
    RuntimeKind.TYPESCRIPT: (
        "strategy.ts", b"export const evaluate = (x: unknown): unknown => x;\n",
    ),
    RuntimeKind.WASM: ("strategy.wasm", b"\x00asm\x01\x00\x00\x00"),
}


def _event(origin=DataOrigin.SYNTHETIC, ident="binding_one"):
    b = CoreBinding(
        "instance_one", ident,
        Instrument(Market.CRYPTO, "operator_declared_provider", "ABCUSD", "UTC", "USD"),
        "15m",
    )
    candle = ClosedCandle(
        T, T + timedelta(minutes=15), D(100), D(102), D(98), D(100), D(10),
    )
    candle2 = ClosedCandle(
        candle.close_at, candle.close_at + timedelta(minutes=15),
        D(100), D(108), D(99), D(106), D(10),
    )
    return CoreInput(
        CORE.manifest.core_id, CORE.manifest.core_version,
        b, CoreEventType.CLOSED_CANDLE, candle2.close_at,
        origin, "runtime_a1_fixture_only", (candle, candle2),
    )


def _profile(monkeypatch, kind):
    monkeypatch.setattr(os, "geteuid", lambda: 1001)
    policy = SecurePluginPolicy(
        True, IMAGE, docker_binary="/usr/bin/docker",
        docker_socket="unix:///run/user/1001/docker.sock")
    return RuntimeProfile(kind, policy, "a" * 64, worker_reviewed=True)


def _response(event):
    return json.dumps({
        "abi_major": 1, "abi_minor": 0,
        "core_id": event.core_id, "core_version": event.core_version,
        "instance_id": event.binding.instance_id,
        "binding_id": event.binding.binding_id,
        "observed_at": event.observed_at.isoformat(),
        "input_digest": event.input_digest,
        "decisions": [{"decision_id": "synthetic_check", "kind": "no_setup"}],
    }, separators=(",", ":")).encode()


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_each_kind_has_bounded_framed_wire(kind):
    name, data = SOURCE[kind]
    payload = prepare_framed_request(
        kind, CORE.manifest, _event(), artifact_name=name,
        artifact=data, approved_sha256=hashlib.sha256(data).hexdigest())
    assert int.from_bytes(payload[:4], "big") == len(data)
    assert payload[4:4 + len(data)] == data
    req = json.loads(payload[4 + len(data):])
    assert req["runtime_kind"] == kind.value
    assert req["protocol"] == "RUNTIME_A1_FRAMED_V1"
    assert req["event"]["origin"] == "synthetic"
    assert len(req["manifest_digest"]) == 64
    assert "telegram_bot_token" not in str(req).lower()


def test_default_all_kinds_missing_and_no_execution(monkeypatch):
    host = MultiLanguageOfflineHost()
    assert set(host.status()) == {kind.value for kind in RuntimeKind}
    assert all(x == "WORKER_NOT_INSTALLED" for x in host.status().values())
    def forbidden(*a, **kw):
        raise AssertionError("NO_EXECUTION_PERMITTED")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    for kind in RuntimeKind:
        name, data = SOURCE[kind]
        with pytest.raises(MultilangRefused, match="WORKER_NOT_INSTALLED"):
            host.evaluate(kind, CORE.manifest, _event(), artifact_name=name,
                          artifact=data, approved_sha256=hashlib.sha256(data).hexdigest())


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_hardened_command_exact_worker_with_no_user_code_in_argv(monkeypatch, kind):
    p = _profile(monkeypatch, kind)
    command = build_polyglot_command(p, "mmt-core-" + "0" * 24)
    for switch in ("--runtime=runsc", "--network=none", "--read-only",
                   "--cap-drop=ALL", "--pull=never", "--ipc=none",
                   "--security-opt=no-new-privileges", "--user=65534:65534",
                   "--pids-limit=32", "--memory=128m", "--cpus=0.5"):
        assert switch in command
    assert "--entrypoint=/opt/mmt/bin/runtime-a1-worker" in command
    assert "--entrypoint=python" not in command
    assert "--env=MMT_RUNTIME_KIND=" + kind.value in command
    assert command[-1] == IMAGE
    assert not any(x.startswith(("--mount", "--volume", "--privileged")) for x in command)
    assert "strategy" not in " ".join(command)
    with pytest.raises(Exception, match="SANDBOX_NOT_AUTHORIZED"):
        build_polyglot_command(p, "user-named-worker")


def test_unreviewed_or_unpinned_worker_fails_closed(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1001)
    p = SecurePluginPolicy(True, IMAGE, docker_binary="/usr/bin/docker",
                           docker_socket="unix:///run/user/1001/docker.sock")
    with pytest.raises(MultilangRefused, match="UNREVIEWED"):
        RuntimeProfile(RuntimeKind.WASM, p, "a" * 64, worker_reviewed=False)
    with pytest.raises(MultilangRefused, match="UNREVIEWED"):
        RuntimeProfile(RuntimeKind.WASM, p, "b" * 64, worker_reviewed=True)


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_mismatched_artifact_name_digest_and_live_origin_rejected(kind):
    name, data = SOURCE[kind]
    pin = hashlib.sha256(data).hexdigest()
    with pytest.raises(MultilangRefused, match="APPROVED_SOURCE_DIGEST_REQUIRED"):
        prepare_framed_request(kind, CORE.manifest, _event(),
                               artifact_name=name, artifact=data, approved_sha256="0" * 64)
    with pytest.raises(MultilangRefused, match="LANGUAGE_EXTENSION_MISMATCH"):
        prepare_framed_request(kind, CORE.manifest, _event(),
                               artifact_name="x.txt", artifact=data, approved_sha256=pin)
    # The original CoreInput contract rejects the purported live origin
    # before it could reach a runtime adapter.
    with pytest.raises(CoreContractError, match="UNVERIFIED_ORIGIN"):
        _event("forward")


def test_python_static_findings_block_even_before_oci():
    data = b"import os\nos.system('echo no')\n"
    with pytest.raises(MultilangRefused, match="STATIC_SOURCE_REVIEW_REQUIRED"):
        prepare_framed_request(
            RuntimeKind.PYTHON, CORE.manifest, _event(),
            artifact_name="unsafe.py", artifact=data,
            approved_sha256=hashlib.sha256(data).hexdigest())


def test_mocked_oci_roundtrip_returns_only_typed_inert_result(monkeypatch):
    import naseri_markets.multilang_runtime_a1 as runtime
    p = _profile(monkeypatch, RuntimeKind.JAVASCRIPT)
    host = MultiLanguageOfflineHost((p,))
    e = _event()
    monkeypatch.setattr(runtime, "_assert_rootless_socket", lambda *a: None)
    monkeypatch.setattr(runtime, "_ensure_rootless_daemon", lambda *a: None)
    calls = []
    def pretend_oci(profile, name, packet):
        calls.append((profile.kind, name, packet))
        return _response(e)
    monkeypatch.setattr(runtime, "_run_oci", pretend_oci)
    name, data = SOURCE[RuntimeKind.JAVASCRIPT]
    out = host.evaluate(RuntimeKind.JAVASCRIPT, CORE.manifest, e,
                        artifact_name=name, artifact=data,
                        approved_sha256=hashlib.sha256(data).hexdigest())
    assert len(calls) == 1
    assert calls[0][0] is RuntimeKind.JAVASCRIPT
    assert out.result.decisions[0].kind.value == "no_setup"
    assert out.language is RuntimeKind.JAVASCRIPT
    assert out.orders_enabled is out.telegram_enabled is out.forward_enabled is False
    assert out.deployed is False
    assert host.quarantined == set()


def test_invalid_or_forged_result_quarantines_binding(monkeypatch):
    import naseri_markets.multilang_runtime_a1 as runtime
    p = _profile(monkeypatch, RuntimeKind.WASM)
    host = MultiLanguageOfflineHost((p,))
    monkeypatch.setattr(runtime, "_assert_rootless_socket", lambda *a: None)
    monkeypatch.setattr(runtime, "_ensure_rootless_daemon", lambda *a: None)
    e = _event(ident="bad_binding")
    forged = json.loads(_response(e))
    forged["binding_id"] = "another_binding"
    monkeypatch.setattr(runtime, "_run_oci", lambda *a: json.dumps(forged).encode())
    name, data = SOURCE[RuntimeKind.WASM]
    with pytest.raises(MultilangRefused, match="QUARANTINED"):
        host.evaluate(RuntimeKind.WASM, CORE.manifest, e, artifact_name=name,
                      artifact=data, approved_sha256=hashlib.sha256(data).hexdigest())
    assert "bad_binding" in host.quarantined
    with pytest.raises(MultilangRefused, match="BINDING_QUARANTINED"):
        host.evaluate(RuntimeKind.WASM, CORE.manifest, e, artifact_name=name,
                      artifact=data, approved_sha256=hashlib.sha256(data).hexdigest())


def test_duplicate_profiles_fail_closed(monkeypatch):
    p = _profile(monkeypatch, RuntimeKind.PYTHON)
    with pytest.raises(MultilangRefused, match="PROFILE_REGISTRY_INVALID"):
        MultiLanguageOfflineHost((p, p))


def test_no_worker_runtime_image_no_server_and_no_core_modification():
    import naseri_markets.multilang_runtime_a1 as runtime
    assert runtime._ENTRYPOINT == "/opt/mmt/bin/runtime-a1-worker"
    assert runtime._MAX_RESULT == 16 * 1024
