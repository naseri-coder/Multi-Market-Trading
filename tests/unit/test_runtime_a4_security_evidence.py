"""RUNTIME-A4 evidence-policy tests: fabricated receipts, ZERO host calls."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
from datetime import UTC, datetime

import pytest

from naseri_markets.multilang_runtime_a1 import RuntimeKind, RuntimeProfile
from naseri_markets.runtime_a4_security_evidence import (
    RuntimeEvidenceRefused,
    policy_digest,
    verify_security_evidence,
)
from naseri_markets.secure_plugin_runtime_v1 import SecurePluginPolicy

ISSUER = "auditor.test-v1"
HOST = "isolated.test-host"
NONCE = "ab" * 16
SECRET = b"deliberately-fake-key-for-ci-only-never-production-012345"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
CHECKS = (
    "rootless_daemon_verified", "runsc_runtime_verified",
    "network_denied_verified", "readonly_root_verified",
    "no_mounts_verified", "no_privileges_verified",
    "nonroot_uid_verified", "cpu_memory_pid_limits_verified",
    "no_credentials_verified", "oci_cleanup_verified",
    "fixed_fixture_abi_verified",
)


def _profile(monkeypatch, kind=RuntimeKind.PYTHON):
    monkeypatch.setattr(os, "geteuid", lambda: 1001)
    image = "registry.invalid/reviewed-worker@sha256:" + "a" * 64
    policy = SecurePluginPolicy(
        enabled=True, image=image, docker_binary="/usr/bin/docker",
        docker_socket="unix:///run/user/1001/docker.sock",
        timeout_seconds=3.0,
    )
    return RuntimeProfile(
        kind, policy, reviewed_image_sha256="a" * 64,
        worker_reviewed=True,
    )


def _payload(profile):
    return {
        "schema_version": 1,
        "audience": "MMT-RUNTIME-A4-RESEARCH-ONLY",
        "issuer_id": ISSUER,
        "host_id": HOST,
        "runtime_kind": profile.kind.value,
        "image_digest": "a" * 64,
        "policy_digest": policy_digest(profile),
        "worker_digest": "b" * 64,
        "issued_at": "2026-10-14T11:59:00Z",
        "expires_at": "2026-10-14T12:04:00Z",
        "nonce": NONCE,
        "checks": {k: True for k in CHECKS},
    }


def _encode(payload, key=SECRET):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()
    mac = hmac.new(key, body, hashlib.sha256).hexdigest()
    return json.dumps(
        {"payload": payload, "mac_sha256": mac},
        sort_keys=True, separators=(",", ":"),
    ).encode()


def _verify(monkeypatch, payload=None, *, kind=RuntimeKind.PYTHON,
            key=SECRET, nonce=NONCE, host=HOST, issuer=ISSUER, now=NOW):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    profile = _profile(monkeypatch, kind)
    receipt = _encode(_payload(profile) if payload is None else payload)
    return verify_security_evidence(
        receipt, profile=profile, review_key=key,
        trusted_issuer_id=issuer, expected_host_id=host,
        expected_nonce=nonce, at=now,
    )


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_all_four_language_receipts_are_review_only(monkeypatch, kind):
    decision = _verify(monkeypatch, kind=kind)
    assert decision.status == "SIGNED_CLAIMS_MATCH_REVIEW_ONLY"
    assert decision.evidence_claims_authenticated is True
    assert decision.host_isolation_certified is False
    assert decision.untrusted_code_execution_permitted is False
    assert decision.worker_installed is False
    assert decision.live_enabled is False
    assert decision.broker_enabled is False
    assert decision.telegram_enabled is False
    assert decision.runtime_kind is kind


def test_fabricated_test_claims_do_not_prove_actual_host(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("NO PROCESS"))
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **kw: pytest.fail("NO HOST PROBE"))
    x = _verify(monkeypatch)
    assert x.host_isolation_certified is False
    assert not x.untrusted_code_execution_permitted


def test_hmac_wrong_key_denied(monkeypatch):
    with pytest.raises(RuntimeEvidenceRefused, match="MAC_INVALID"):
        _verify(monkeypatch, key=b"wrong-verifier-key-wrong-verifier-key-0000")


@pytest.mark.parametrize(("field", "value"), [
    ("issuer_id", "wrong-auditor"),
    ("host_id", "unexpected-host"),
    ("nonce", "cd" * 16),
    ("runtime_kind", "javascript"),
    ("image_digest", "c" * 64),
    ("worker_digest", "bad"),
    ("policy_digest", "0" * 64),
    ("audience", "MMT-RUNTIME-A4-PRODUCTION"),
    ("schema_version", True),
])
def test_correctly_macd_but_wrong_scope_refused(monkeypatch, field, value):
    profile = _profile(monkeypatch)
    body = _payload(profile)
    body[field] = value
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(RuntimeEvidenceRefused, match="PIN_OR_SCOPE"):
        verify_security_evidence(
            _encode(body), profile=profile, review_key=SECRET,
            trusted_issuer_id=ISSUER, expected_host_id=HOST,
            expected_nonce=NONCE, at=NOW,
        )


def test_missing_or_false_probe_denied_even_if_mac_matches(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    for case in ("false", "missing", "extra"):
        body = _payload(profile)
        if case == "false":
            body["checks"]["runsc_runtime_verified"] = False
        elif case == "missing":
            del body["checks"]["network_denied_verified"]
        else:
            body["checks"]["unreviewed_new_claim"] = True
        with pytest.raises(RuntimeEvidenceRefused, match="MANDATORY_PROBE"):
            verify_security_evidence(
                _encode(body), profile=profile, review_key=SECRET,
                trusted_issuer_id=ISSUER, expected_host_id=HOST,
                expected_nonce=NONCE, at=NOW,
            )


@pytest.mark.parametrize(("issued", "expires", "now"), [
    ("2026-10-14T12:01:00Z", "2026-10-14T12:04:00Z", NOW),
    ("2026-10-14T11:40:00Z", "2026-10-14T11:59:59Z", NOW),
    ("2026-10-14T11:40:00Z", "2026-10-14T12:00:00Z", NOW),
    ("2026-10-14T12:00:00Z", "2026-10-14T12:00:00Z", NOW),
])
def test_expired_future_or_oversized_window_refused(monkeypatch,
                                                      issued, expires, now):
    profile = _profile(monkeypatch)
    body = _payload(profile)
    body["issued_at"], body["expires_at"] = issued, expires
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(RuntimeEvidenceRefused, match="VALIDITY_WINDOW"):
        verify_security_evidence(
            _encode(body), profile=profile, review_key=SECRET,
            trusted_issuer_id=ISSUER, expected_host_id=HOST,
            expected_nonce=NONCE, at=now,
        )


@pytest.mark.parametrize("bad_receipt", [
    b"",
    b"not JSON",
    b'{"payload":{},"payload":{},"mac_sha256":"' + b"0" * 64 + b'"}',
    b'{"payload":NaN,"mac_sha256":"' + b"0" * 64 + b'"}',
    b'{"payload":{},"mac_sha256":"' + b"0" * 64 + b'","extra":true}',
    b"x" * 16385,
])
def test_corrupt_malformed_duplicate_or_large_receipt_refused(
    monkeypatch, bad_receipt,
):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    with pytest.raises(RuntimeEvidenceRefused):
        verify_security_evidence(
            bad_receipt, profile=profile, review_key=SECRET,
            trusted_issuer_id=ISSUER, expected_host_id=HOST,
            expected_nonce=NONCE, at=NOW,
        )


def test_no_environment_flag_no_receipt_acceptance(monkeypatch):
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    profile = _profile(monkeypatch)
    receipt = _encode(_payload(profile))
    kwargs = dict(
        profile=profile, review_key=SECRET,
        trusted_issuer_id=ISSUER, expected_host_id=HOST,
        expected_nonce=NONCE, at=NOW,
    )
    with pytest.raises(RuntimeEvidenceRefused, match="NONPRODUCTION_ONLY"):
        verify_security_evidence(receipt, **kwargs)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(RuntimeEvidenceRefused, match="NONPRODUCTION_ONLY"):
        verify_security_evidence(receipt, **kwargs)


def test_trust_key_and_expected_nonce_are_mandatory(monkeypatch):
    profile = _profile(monkeypatch)
    receipt = _encode(_payload(profile))
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    kwargs = dict(
        profile=profile, trusted_issuer_id=ISSUER,
        expected_host_id=HOST, expected_nonce=NONCE, at=NOW,
    )
    for key in (b"", b"short", None):
        with pytest.raises(RuntimeEvidenceRefused, match="OUT_OF_BAND"):
            verify_security_evidence(receipt, review_key=key, **kwargs)
    with pytest.raises(RuntimeEvidenceRefused, match="OUT_OF_BAND"):
        verify_security_evidence(
            receipt, review_key=SECRET,
            **{**kwargs, "expected_nonce": "not-pinned"},
        )


def test_mutating_oci_policy_invalidates_original_receipt(monkeypatch):
    profile = _profile(monkeypatch)
    receipt = _encode(_payload(profile))
    # A different timeout, even with an unchanged worker image, invalidates.
    changed = RuntimeProfile(
        profile.kind,
        SecurePluginPolicy(
            enabled=True, image=profile.policy.image,
            docker_binary=profile.policy.docker_binary,
            docker_socket=profile.policy.docker_socket,
            timeout_seconds=8.0,
        ),
        profile.reviewed_image_sha256,
        worker_reviewed=True,
    )
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(RuntimeEvidenceRefused, match="PIN_OR_SCOPE"):
        verify_security_evidence(
            receipt, profile=changed, review_key=SECRET,
            trusted_issuer_id=ISSUER, expected_host_id=HOST,
            expected_nonce=NONCE, at=NOW,
        )
