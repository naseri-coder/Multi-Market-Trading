"""RUNTIME-A6 denies Worker execution through A1, A3, or direct OCI.

All checks are nonproduction offline fixture/mocked checks. No worker runs.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import naseri_markets.multilang_runtime_a1 as a1
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle,
    CoreBinding,
    CoreEventType,
    CoreInput,
    DataOrigin,
)
from naseri_markets.durable_runtime_a3 import (
    DurableOfflineRuntime,
    DurableRuntimeLedger,
    DurableRuntimeRefused,
)
from naseri_markets.multilang_runtime_a1 import (
    MultilangRefused,
    MultiLanguageOfflineHost,
    RuntimeKind,
    RuntimeProfile,
    prepare_framed_request,
)
from naseri_markets.runtime_a5_nonce_custody import ConsumedReview
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
    review_worker_launch,
)
from naseri_markets.secure_plugin_runtime_v1 import SecurePluginPolicy

IMAGE = "registry.invalid/a6-untrusted@sha256:" + "a" * 64
SOURCE = {
    RuntimeKind.PYTHON: ("fixture.py", b"def evaluate(event):\n    return []\n"),
    RuntimeKind.JAVASCRIPT: ("fixture.js", b"export function evaluate(event) { return event; }\n"),
    RuntimeKind.TYPESCRIPT: (
        "fixture.ts", b"export const evaluate = (x: unknown): unknown => x;\n",
    ),
    RuntimeKind.WASM: ("fixture.wasm", b"\x00asm\x01\x00\x00\x00"),
}


def _fixture(monkeypatch, kind):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(os, "geteuid", lambda: 1001)
    policy = SecurePluginPolicy(
        True, IMAGE, docker_binary="/usr/bin/docker",
        docker_socket="unix:///run/user/1001/docker.sock",
    )
    profile = RuntimeProfile(kind, policy, "a" * 64, worker_reviewed=True)
    at = datetime(2026, 10, 13, 10, tzinfo=UTC)
    inst = Instrument(Market.CRYPTO, "a6_fixture", "ABCUSD", "UTC", "USD")
    binding = CoreBinding("a6_instance", "a6_binding", inst, "15m")
    candles = (
        ClosedCandle(at, at + timedelta(minutes=15), Decimal("100"),
                     Decimal("102"), Decimal("98"), Decimal("100"), Decimal("10")),
        ClosedCandle(at + timedelta(minutes=15), at + timedelta(minutes=30),
                     Decimal("100"), Decimal("102"), Decimal("98"),
                     Decimal("101"), Decimal("10")),
    )
    manifest = OfflineContractFixture().manifest
    event = CoreInput(
        manifest.core_id, manifest.core_version, binding,
        CoreEventType.CLOSED_CANDLE, candles[-1].close_at,
        DataOrigin.SYNTHETIC, "a6_fixture_only", candles,
    )
    name, source = SOURCE[kind]
    digest = hashlib.sha256(source).hexdigest()
    framed = prepare_framed_request(
        kind, manifest, event, artifact_name=name,
        artifact=source, approved_sha256=digest,
    )
    return profile, manifest, event, name, source, digest, framed


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_all_languages_review_only_and_launch_denied(monkeypatch, kind):
    profile, _, _, _, _, _, frame = _fixture(monkeypatch, kind)
    review = review_worker_launch(profile, frame)
    assert review.language == kind.value
    assert len(review.policy_sha256) == 64
    assert review.worker_launch_permitted is False
    assert review.independent_host_certified is False
    assert review.broker_permitted is False
    assert review.telegram_permitted is False
    with pytest.raises(RuntimeA6Denied, match="A6_INDEPENDENT_HOST_CERTIFICATION"):
        require_worker_launch(profile, frame)


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_direct_oci_and_a1_host_refuse_before_any_process(monkeypatch, kind):
    profile, manifest, event, name, source, digest, frame = _fixture(monkeypatch, kind)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("A6 must prevent every prelaunch side effect")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(a1, "_assert_rootless_socket", forbidden)
    monkeypatch.setattr(a1, "_ensure_rootless_daemon", forbidden)
    with pytest.raises(RuntimeA6Denied, match="A6_INDEPENDENT_HOST_CERTIFICATION"):
        a1._run_oci(profile, "mmt-core-" + "0" * 24, frame)
    host = MultiLanguageOfflineHost((profile,))
    with pytest.raises(MultilangRefused, match="RUNTIME_A6_EXECUTION_DENIED"):
        host.evaluate(
            kind, manifest, event, artifact_name=name,
            artifact=source, approved_sha256=digest,
        )
    assert calls == []
    assert host.quarantined == set()


def test_a3_wrapper_cannot_run_worker_by_delegation(tmp_path, monkeypatch):
    profile, manifest, event, name, source, digest, _ = _fixture(
        monkeypatch, RuntimeKind.JAVASCRIPT,
    )
    invocations = []

    def forbidden(*args, **kwargs):
        invocations.append(args)
        raise AssertionError("A6 missed a Worker path")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(a1, "_run_oci", forbidden)
    monkeypatch.setattr(a1, "_assert_rootless_socket", forbidden)
    # The synthetic Docker profile pretends to use UID 1001. The actual
    # owner of this isolated SQLite fixture must match the real test UID.
    monkeypatch.setattr(os, "geteuid", lambda: tmp_path.stat().st_uid)
    ledger = DurableRuntimeLedger(tmp_path / "a6_a3.sqlite")
    try:
        runtime = DurableOfflineRuntime(MultiLanguageOfflineHost((profile,)), ledger)
        with pytest.raises(DurableRuntimeRefused, match="DURABLE_BINDING_QUARANTINED"):
            runtime.evaluate(
                RuntimeKind.JAVASCRIPT, manifest, event,
                artifact_name=name, artifact=source,
                approved_sha256=digest, operator_ack=True,
            )
        assert not invocations
    finally:
        ledger.close()


def test_a5_consumed_review_cannot_be_transmuted_into_execution(monkeypatch):
    profile, _, _, _, _, _, frame = _fixture(monkeypatch, RuntimeKind.PYTHON)
    review = ConsumedReview("a" * 64, "b" * 64, "c" * 64)
    preflight = review_worker_launch(profile, frame, a5_review=review)
    assert preflight.a5_review_is_execution_grant is False
    assert not preflight.worker_launch_permitted
    with pytest.raises(RuntimeA6Denied, match="A6_INDEPENDENT_HOST_CERTIFICATION"):
        require_worker_launch(profile, frame)
    with pytest.raises(RuntimeA6Denied, match="A6_INVALID_REVIEW_ONLY_CLAIM"):
        review_worker_launch(
            profile, frame, a5_review=replace(review, execution_authorized=True),
        )


def test_production_env_disabled_profile_and_bad_frame_denied(monkeypatch):
    profile, _, _, _, _, _, frame = _fixture(monkeypatch, RuntimeKind.WASM)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(RuntimeA6Denied, match="A6_NONPRODUCTION_ONLY"):
        require_worker_launch(profile, frame)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(RuntimeA6Denied, match="A6_NONPRODUCTION_ONLY"):
        require_worker_launch(profile, frame)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(RuntimeA6Denied, match="A6_BOUNDED_FRAME_REQUIRED"):
        require_worker_launch(profile, b"")
    with pytest.raises(RuntimeA6Denied, match="A6_FRAME_LENGTH_INVALID"):
        require_worker_launch(profile, b"\\xff\\xff\\xff\\xff{}")
    with pytest.raises(RuntimeA6Denied, match="A6_REVIEWED_PROFILE_REQUIRED"):
        require_worker_launch(None, frame)


def test_static_process_choke_point_gated_before_popen():
    source = inspect.getsource(a1._run_oci)
    tree = ast.parse(source)
    fn = tree.body[0]
    calls = {
        node.func.id: node.lineno for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls["require_worker_launch"] < calls["build_polyglot_command"]
    assert "require_worker_launch(profile, payload)" in source
    assert "subprocess.Popen(" in source
    host_source = inspect.getsource(a1.MultiLanguageOfflineHost.evaluate)
    assert host_source.index("require_worker_launch(profile, framed)") < (
        host_source.index("_assert_rootless_socket")
    )
