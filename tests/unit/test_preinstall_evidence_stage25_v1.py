"""Stage25 strictly read-only reconciliation; no malicious code ever executed."""
from __future__ import annotations

import hashlib
import os

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.core_api_v1 import content_digest
from naseri_markets.durable_isolated_core_gate_stage22_v1 import (
    DurableIsolatedCoreGate,
)
from naseri_markets.host_observation_custody_stage24_v1 import (
    HostObservationLedger,
)
from naseri_markets.preinstall_evidence_stage25_v1 import (
    PreinstallReviewRefused, review_preinstall_evidence,
)
from naseri_markets.signed_core_candidate_stage23_v1 import SignedCandidateWitness
from test_secure_plugin_runtime_v1 import CORE, IMAGE, SHA, SOURCE, event
from test_signed_core_candidate_stage23_v1 import (
    key_bytes, signed as sign_candidate,
)
from test_host_observation_custody_stage24_v1 import (
    raw_receipt, signed as sign_host_observation,
)

TENANT = "tenant_alpha"
HOST = "disposable_host_one"
PUB = "community.vendor"
KEY_ID = "pub_key_one"
NOW = 1000


@pytest.fixture(autouse=True)
def safe_env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    # Strict mocks of previously reviewed signing contracts and Stage4 host:
    # no actual sandbox, Docker, broker order or Telegram publication.
    from naseri_markets.secure_plugin_runtime_v1 import (
        SecureOfflineCoreHost, SecurePluginPolicy,
    )
    with monkeypatch.context() as local:
        local.setattr(os, "geteuid", lambda: 1001)
        policy = SecurePluginPolicy(
            enabled=True, image=IMAGE, docker_binary="/usr/bin/docker",
            docker_socket="unix:///run/user/1001/docker.sock")
    host = SecureOfflineCoreHost(policy)
    folder = tmp_path / "stage25-private"
    folder.mkdir(mode=0o700)
    publisher = Ed25519PrivateKey.generate()
    operator = Ed25519PrivateKey.generate()
    reviewer = Ed25519PrivateKey.generate()
    ph, oh, rh = (key_bytes(k) for k in (publisher, operator, reviewer))
    hashkey = lambda key: hashlib.sha256(key).hexdigest()
    with (DurableIsolatedCoreGate(folder / "stage22.sqlite", host=host) as g22,
          SignedCandidateWitness(
              folder / "stage23.sqlite",
              publisher_public_key=ph, publisher_key_sha256=hashkey(ph),
              operator_public_key=oh, operator_key_sha256=hashkey(oh),
              operator_ack=True) as g23,
          HostObservationLedger(
              folder / "stage24.sqlite", reviewer_public_key=rh,
              approved_reviewer_key_sha256=hashkey(rh),
              operator_ack=True) as g24):
        binding = event().binding
        g22.register(
            TENANT, CORE.manifest, binding,
            approved_manifest_digest=content_digest(CORE.manifest),
            approved_source_sha256=SHA, operator_ack=True)
        claim = sign_candidate((g23, publisher, operator, folder / "stage23.sqlite"))
        assert g23.admit(
            claim, source=SOURCE, manifest=CORE.manifest, binding=binding,
            tenant_id=TENANT, publisher=PUB, publisher_key_id=KEY_ID,
            image=IMAGE, now=NOW, operator_ack=True).sequence == 1
        receipt = raw_receipt()
        witness = sign_host_observation(reviewer, receipt)
        assert g24.record(
            witness, receipt, expected_host_id=HOST, expected_image=IMAGE,
            now=NOW, operator_ack=True).sequence == 1
        opts = dict(
            stage22=g22, stage23=g23, stage24=g24,
            candidate=claim, source=SOURCE,
            manifest=CORE.manifest, binding=binding,
            observation=witness, canary_receipt=receipt,
            tenant_id=TENANT, publisher=PUB, publisher_key_id=KEY_ID,
            host_id=HOST, expected_image=IMAGE, now=NOW, operator_ack=True)
        yield opts, g22, g23, g24


def test_all_three_exact_local_ledgers_coherent_never_an_execution_grant(prepared):
    opts, g22, _, _ = prepared
    pre = g22.state(TENANT, "binding_a")
    before = g22.db.execute("SELECT COUNT(*) FROM secure22_attempts").fetchone()[0]
    report = review_preinstall_evidence(**opts)
    assert report.review_state == "LOCAL_CROSS_STAGE_EVIDENCE_MATCHED_NOT_AUTHORIZED"
    assert report.tenant_id == TENANT
    assert report.stage22_state == "DISABLED"
    assert report.stage22_revision == 1
    assert len(report.chain_checks) == 5
    assert not report.host_isolation_independently_verified
    assert not report.supply_chain_outside_local_state_verified
    assert not report.runtime_wiring_authorized
    assert not report.installation_authorized
    assert not report.activation_authorized
    assert not report.telegram_signal_authorized
    assert not report.broker_order_authorized
    assert not report.live_trading_authorized
    assert g22.state(TENANT, "binding_a") == pre
    assert g22.db.execute("SELECT COUNT(*) FROM secure22_attempts").fetchone()[0] == before


@pytest.mark.parametrize("different", [
    {"tenant_id": "tenant_beta"},
    {"publisher": "impostor.vendor"},
    {"publisher_key_id": "impostor_key"},
    {"host_id": "other_host"},
    {"now": NOW + 700},
    {"source": b"altered source"},
    {"candidate": b"{}"},
    {"observation": b"{}"},
    {"canary_receipt": b"{}"},
    {"operator_ack": False},
])
def test_invalid_identity_expiry_or_tamper_fails_closed(prepared, different):
    opts, *_ = prepared
    with pytest.raises(PreinstallReviewRefused):
        review_preinstall_evidence(**{**opts, **different})


def test_stage23_publisher_revocation_is_irrevocable(prepared):
    opts, _, witness, _ = prepared
    witness.revoke(TENANT, "binding_a", operator_ack=True)
    with pytest.raises(PreinstallReviewRefused, match="INCOMPLETE_REVOKED"):
        review_preinstall_evidence(**opts)


def test_stage24_host_statement_revoked_even_if_candidate_current(prepared):
    opts, _, _, observations = prepared
    observations.revoke(HOST, operator_ack=True)
    with pytest.raises(PreinstallReviewRefused, match="INCOMPLETE_REVOKED"):
        review_preinstall_evidence(**opts)


def test_stage22_preexisting_activation_refuses_even_pinned_signed_candidate(prepared):
    opts, g22, *_ = prepared
    g22.set_enabled(TENANT, "binding_a", enabled=True, expected_revision=1,
                    operator_ack=True)
    with pytest.raises(PreinstallReviewRefused, match="STAGE22_MUST_BE_DISABLED"):
        review_preinstall_evidence(**opts)
    assert g22.state(TENANT, "binding_a")["state"] == "ENABLED"


def test_a_prior_lease_is_never_mistaken_for_safe_preinstall(prepared):
    opts, g22, *_ = prepared
    g22.db.execute(
        "INSERT INTO secure22_attempts VALUES(?,?,?,'FAILED',NULL)",
        ("binding_a", "sha_prior", 1))
    with pytest.raises(PreinstallReviewRefused, match="PRIOR_EXECUTION_ATTEMPT"):
        review_preinstall_evidence(**opts)


def test_cross_ledger_source_or_manifest_mismatch_fails_closed(prepared):
    opts, g22, *_ = prepared
    g22.db.execute(
        "UPDATE secure22_bindings SET source_sha256=? WHERE binding_id=?",
        ("0" * 64, "binding_a"))
    with pytest.raises(PreinstallReviewRefused, match="STAGE22_ADMISSION_PIN_DRIFT"):
        review_preinstall_evidence(**opts)


def test_alternate_image_even_if_present_in_local_stage4_policy_rejected(prepared):
    opts, _gate, *_ = prepared
    altered = "registry.example.invalid/new@sha256:"+"b"*64
    with pytest.raises(PreinstallReviewRefused):
        review_preinstall_evidence(**{**opts, "expected_image": altered})


def test_fence_disallows_production_even_with_three_consistent_ledgers(
        prepared, monkeypatch):
    opts, *_ = prepared
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(PreinstallReviewRefused, match="EXPLICIT_NONPRODUCTION"):
        review_preinstall_evidence(**opts)
