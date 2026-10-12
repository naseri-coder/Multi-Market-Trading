"""Stage22 durable tenant admission for existing strictly isolated Core API.

These are MOCKED OCI-policy tests, not a kernel/gVisor hostile-code proof.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from naseri_markets.core_api_v1 import (
    CoreBinding, content_digest,
)
from naseri_markets.durable_isolated_core_gate_stage22_v1 import (
    DurableIsolatedCoreGate, Stage22Refused,
)
from naseri_markets.secure_plugin_runtime_v1 import (
    SecureOfflineCoreHost, SecurePluginPolicy,
)
from test_secure_plugin_runtime_v1 import (
    CORE, IMAGE, SHA, SOURCE, event,
)


@pytest.fixture(autouse=True)
def research_only(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


@pytest.fixture
def host(monkeypatch):
    # The real host still owns its disabled-by-default, independently configured
    # rootless+gVisor policy. No container is started in any Stage22 test.
    with monkeypatch.context() as local:
        local.setattr(os, "geteuid", lambda: 1001)
        policy = SecurePluginPolicy(
            enabled=True, image=IMAGE, docker_binary="/usr/bin/docker",
            docker_socket="unix:///run/user/1001/docker.sock")
    return SecureOfflineCoreHost(policy)


def register(gate, *, tenant="tenant_alpha", binding=None):
    binding = binding if binding is not None else event().binding
    return gate.register(
        tenant, CORE.manifest, binding,
        approved_manifest_digest=content_digest(CORE.manifest),
        approved_source_sha256=SHA, operator_ack=True)


def open_gate(tmp_path, host):
    return DurableIsolatedCoreGate(tmp_path / "stage22.sqlite", host=host)


def test_source_pins_and_parent_are_private_before_registration(tmp_path, host):
    with open_gate(tmp_path, host) as gate:
        saved = register(gate)
        assert saved["state"] == "DISABLED"
        assert saved["revision"] == 1
        assert saved["telegram_send_authorized"] is False
        assert saved["broker_order_authorized"] is False
        assert (tmp_path / "stage22.sqlite").stat().st_mode & 0o077 == 0
        with pytest.raises(Stage22Refused, match="BINDING_ID_RESERVED_GLOBAL"):
            register(gate, tenant="tenant_beta")
        with pytest.raises(Stage22Refused, match="TENANT_BINDING_NOT_AUTHORIZED"):
            gate.state("tenant_beta", event().binding.binding_id)
        with pytest.raises(Stage22Refused, match="MANIFEST_PIN_MISMATCH"):
            gate.register(
                "tenant_alpha", CORE.manifest, event(ident="other_binding").binding,
                approved_manifest_digest="0" * 64, approved_source_sha256=SHA,
                operator_ack=True)
        with pytest.raises(Stage22Refused, match="BINDING_DISABLED"):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)


def test_exact_isolated_result_and_idempotent_durable_replay_denial(tmp_path, host, monkeypatch):
    observed = []
    def safe_stub(manifest, e, *, source, approved_source_sha256):
        assert manifest == CORE.manifest
        assert hashlib.sha256(source).hexdigest() == approved_source_sha256
        observed.append(e.binding.binding_id)
        return CORE.evaluate(e)
    monkeypatch.setattr(host, "evaluate", safe_stub)
    with open_gate(tmp_path, host) as gate:
        register(gate)
        gate.set_enabled("tenant_alpha", event().binding.binding_id,
                         enabled=True, expected_revision=1, operator_ack=True)
        output = gate.evaluate("tenant_alpha", CORE.manifest, event(),
                               source=SOURCE, operator_ack=True)
        assert output.input_digest == event().input_digest
        assert gate.audit("tenant_alpha", event().binding.binding_id)[
            "attempt_states"] == {"VERIFIED": 1}
        assert gate.state("tenant_alpha", event().binding.binding_id)[
            "verified_evaluations"] == 1
        with pytest.raises(Stage22Refused, match="DURABLE_INPUT_REPLAY_DENIED"):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)
        assert len(observed) == 1
    with open_gate(tmp_path, host) as reopened:
        assert reopened.audit("tenant_alpha", event().binding.binding_id)[
            "attempt_states"] == {"VERIFIED": 1}
        with pytest.raises(Stage22Refused, match="DURABLE_INPUT_REPLAY_DENIED"):
            reopened.evaluate("tenant_alpha", CORE.manifest, event(),
                              source=SOURCE, operator_ack=True)


def test_forged_tenant_binding_symbol_or_source_never_calls_worker(
        tmp_path, host, monkeypatch):
    called = []
    monkeypatch.setattr(host, "evaluate", lambda *_a, **_k: called.append(1))
    with open_gate(tmp_path, host) as gate:
        register(gate)
        gate.set_enabled("tenant_alpha", "binding_a", enabled=True,
                         expected_revision=1, operator_ack=True)
        with pytest.raises(Stage22Refused, match="TENANT_BINDING_NOT_AUTHORIZED"):
            gate.evaluate("tenant_beta", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)
        with pytest.raises(Stage22Refused, match="SOURCE_OR_MARKET_BINDING_PIN_MISMATCH"):
            gate.evaluate("tenant_alpha", CORE.manifest,
                          event(provider="other_venue", symbol="OTHERUSD"),
                          source=SOURCE, operator_ack=True)
        with pytest.raises(Stage22Refused, match="SOURCE_OR_MARKET_BINDING_PIN_MISMATCH"):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=b"malicious source", operator_ack=True)
        assert not called
        assert gate.audit("tenant_alpha", "binding_a")["attempt_states"] == {}


def test_sandbox_rejection_quarantines_permanently_after_restart(
        tmp_path, host, monkeypatch):
    called = []
    def broken(*_args, **_kwargs):
        called.append(True)
        raise RuntimeError("private exception including imagined credential")
    monkeypatch.setattr(host, "evaluate", broken)
    with open_gate(tmp_path, host) as gate:
        register(gate)
        gate.set_enabled("tenant_alpha", "binding_a", enabled=True,
                         expected_revision=1, operator_ack=True)
        with pytest.raises(Stage22Refused, match="PERSISTENT_CORE_QUARANTINE"):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)
        assert gate.state("tenant_alpha", "binding_a")["state"] == "QUARANTINED"
        assert gate.audit("tenant_alpha", "binding_a")["attempt_states"] == {"FAILED": 1}
    with open_gate(tmp_path, host) as gate:
        with pytest.raises(Stage22Refused, match="FRESH_REVIEW_REQUIRED"):
            gate.set_enabled("tenant_alpha", "binding_a", enabled=True,
                             expected_revision=4, operator_ack=True)
        with pytest.raises(Stage22Refused, match="BINDING_DISABLED"):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)
    assert called == [True]


def test_revocation_mid_sandbox_discards_late_result(tmp_path, host, monkeypatch):
    with open_gate(tmp_path, host) as gate:
        register(gate)
        gate.set_enabled("tenant_alpha", "binding_a", enabled=True,
                         expected_revision=1, operator_ack=True)
        with open_gate(tmp_path, host) as controller:
            def in_flight(manifest, current, *, source, approved_source_sha256):
                current_state = controller.state("tenant_alpha", "binding_a")
                assert current_state["state"] == "EVALUATING"
                controller.set_enabled("tenant_alpha", "binding_a",
                                       enabled=False, expected_revision=3,
                                       operator_ack=True)
                return CORE.evaluate(current)
            monkeypatch.setattr(host, "evaluate", in_flight)
            with pytest.raises(Stage22Refused, match="DISABLED_DURING_UNTRUSTED"):
                gate.evaluate("tenant_alpha", CORE.manifest, event(),
                              source=SOURCE, operator_ack=True)
            assert gate.state("tenant_alpha", "binding_a")["state"] == "REVOKED"
            assert gate.audit("tenant_alpha", "binding_a")["attempt_states"] == {
                "DISCARDED": 1}
            with pytest.raises(Stage22Refused, match="FRESH_REVIEW_REQUIRED"):
                gate.set_enabled("tenant_alpha", "binding_a", enabled=True,
                                 expected_revision=4, operator_ack=True)


def test_crash_leaves_visible_unrecoverable_lease(tmp_path, host, monkeypatch):
    def crash(*_a, **_k):
        raise SystemExit(71)
    monkeypatch.setattr(host, "evaluate", crash)
    with open_gate(tmp_path, host) as gate:
        register(gate)
        gate.set_enabled("tenant_alpha", "binding_a", enabled=True,
                         expected_revision=1, operator_ack=True)
        with pytest.raises(SystemExit):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)
    with open_gate(tmp_path, host) as gate:
        assert gate.state("tenant_alpha", "binding_a")["state"] == "EVALUATING"
        assert gate.audit("tenant_alpha", "binding_a")["quarantined_or_revoked"]
        with pytest.raises(Stage22Refused, match="BINDING_DISABLED"):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)
        gate.set_enabled("tenant_alpha", "binding_a", enabled=False,
                         expected_revision=3, operator_ack=True)
        assert gate.state("tenant_alpha", "binding_a")["state"] == "REVOKED"


def test_tenant_quota_and_source_not_stored(tmp_path, host):
    with open_gate(tmp_path, host) as gate:
        for i in range(8):
            binding = event(ident="binding_" + str(i)).binding
            register(gate, binding=binding)
        with pytest.raises(Stage22Refused, match="TENANT_BINDING_QUOTA"):
            register(gate, binding=event(ident="binding_9").binding)
        assert not any(
            SOURCE in row for row in (
                (tmp_path / "stage22.sqlite").read_bytes(),))


def test_nonproduction_only_and_disabled_runtime(tmp_path, monkeypatch, host):
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage22Refused, match="EXPLICIT_NONPRODUCTION"):
        open_gate(tmp_path, host)
    monkeypatch.delenv("MMT_PRODUCTION")
    with pytest.raises(Stage22Refused, match="REAL_ISOLATED"):
        DurableIsolatedCoreGate(
            tmp_path / "blocked.sqlite", host=SecureOfflineCoreHost(
                SecurePluginPolicy()))
    assert not (tmp_path / "blocked.sqlite").exists()


def test_untrusted_result_type_quarantines_without_any_order_send(
        tmp_path, monkeypatch, host):
    monkeypatch.setattr(host, "evaluate", lambda *_a, **_k: {"broker_ok": True})
    with open_gate(tmp_path, host) as gate:
        register(gate)
        gate.set_enabled("tenant_alpha", "binding_a", enabled=True,
                         expected_revision=1, operator_ack=True)
        with pytest.raises(Stage22Refused, match="PERSISTENT_CORE_QUARANTINE"):
            gate.evaluate("tenant_alpha", CORE.manifest, event(),
                          source=SOURCE, operator_ack=True)
        assert gate.audit("tenant_alpha", "binding_a")["attempt_states"] == {
            "FAILED": 1}
