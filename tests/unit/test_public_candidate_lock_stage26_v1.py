"""Stage26 durable public-untrusted lock; all fixtures are offline-only."""
from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("cryptography")

from naseri_markets.durable_isolated_core_gate_stage22_v1 import Stage22Refused
from naseri_markets.preinstall_evidence_stage25_v1 import review_preinstall_evidence
from naseri_markets.public_candidate_lock_stage26_v1 import (
    PublicCandidateLockRefused, inspect_public_candidate_lock,
    seal_public_candidate,
)
from test_preinstall_evidence_stage25_v1 import (
    HOST, NOW, TENANT, prepared,  # noqa: F401
)
from test_secure_plugin_runtime_v1 import CORE, SOURCE, event


def test_signed_cross_stage_chain_becomes_permanently_locked_without_execution(
        prepared, monkeypatch):  # noqa: F811
    args, g22, _g23, _g24 = prepared
    called = []
    monkeypatch.setattr(
        g22.host, "evaluate", lambda *_a, **_kw: called.append("BAD"))
    before = g22.state(TENANT, "binding_a")
    sealed = seal_public_candidate(**args)
    assert sealed.state == "SEALED_PUBLIC_UNTRUSTED_CANDIDATE_NO_EXECUTION"
    assert sealed.stage22_activation_authorized is False
    assert sealed.stage22_evaluation_authorized is False
    assert sealed.independently_verified_host is False
    assert sealed.public_install_authorized is False
    assert sealed.telegram_publish_authorized is False
    assert sealed.broker_order_authorized is False
    assert g22.state(TENANT, "binding_a")["public_untrusted_candidate_locked"]
    assert g22.state(TENANT, "binding_a")["revision"] == before["revision"]
    status = inspect_public_candidate_lock(
        g22, tenant_id=TENANT, binding_id="binding_a")
    assert status["sealed_state"] == "PENDING_INDEPENDENT_HOST_REVIEW"
    assert status["third_party_public_install_authorized"] is False
    with pytest.raises(Stage22Refused, match="STAGE26_PUBLIC_UNTRUSTED"):
        g22.set_enabled(TENANT, "binding_a", enabled=True,
                        expected_revision=1, operator_ack=True)
    with pytest.raises(Stage22Refused, match="STAGE26_PUBLIC_UNTRUSTED"):
        g22.evaluate(TENANT, CORE.manifest, event(),
                     source=SOURCE, operator_ack=True)
    assert called == []
    assert g22.audit(TENANT, "binding_a")["attempt_states"] == {}


def test_sqlite_denies_direct_enable_attempt_erase_or_mutate_fence(prepared):  # noqa: F811
    args, g22, *_ = prepared
    seal_public_candidate(**args)
    with pytest.raises(sqlite3.IntegrityError, match="STAGE26_PUBLIC_EXECUTION_BLOCKED"):
        g22.db.execute(
            "UPDATE secure22_bindings SET state='ENABLED' WHERE binding_id=?",
            ("binding_a",))
    with pytest.raises(sqlite3.IntegrityError, match="STAGE26_PUBLIC_ATTEMPT_BLOCKED"):
        g22.db.execute(
            "INSERT INTO secure22_attempts VALUES (?,?,?,?,?)",
            ("binding_a", "forged", 1, "IN_FLIGHT", None))
    with pytest.raises(sqlite3.IntegrityError, match="STAGE26_FENCE_IS_PERMANENT"):
        g22.db.execute(
            "DELETE FROM secure26_public_fence WHERE binding_id='binding_a'")
    with pytest.raises(sqlite3.IntegrityError, match="STAGE26_FENCE_IS_IMMUTABLE"):
        g22.db.execute(
            "UPDATE secure26_public_fence SET tenant_id='other' WHERE binding_id='binding_a'")
    assert inspect_public_candidate_lock(
        g22, tenant_id=TENANT, binding_id="binding_a")["sealed"]


def test_race_cas_state_revision_changes_are_rejected(prepared):  # noqa: F811
    args, g22, *_ = prepared
    g22.set_enabled(TENANT, "binding_a", enabled=False,
                    expected_revision=1, operator_ack=True)
    with pytest.raises(PublicCandidateLockRefused, match="INVALID_REVOKED"):
        # Any previous attempt blocks Stage25 and therefore Stage26.
        g22.db.execute(
            "INSERT INTO secure22_attempts VALUES (?,?,?,?,?)",
            ("binding_a", "old_attempt", 2, "FAILED", None))
        seal_public_candidate(**args)


def test_previous_lease_and_enabled_state_cannot_be_sealed(prepared):  # noqa: F811
    args, g22, *_ = prepared
    g22.set_enabled(TENANT, "binding_a", enabled=True,
                    expected_revision=1, operator_ack=True)
    with pytest.raises(PublicCandidateLockRefused, match="INVALID_REVOKED"):
        seal_public_candidate(**args)
    assert not inspect_public_candidate_lock(
        g22, tenant_id=TENANT, binding_id="binding_a")["sealed"]


@pytest.mark.parametrize("corruption", [
    {"tenant_id": "tenant_beta"},
    {"publisher": "impostor"},
    {"host_id": "unknown_host"},
    {"source": b"modified binary source"},
    {"candidate": b"{}"},
    {"observation": b"{}"},
    {"canary_receipt": b"{}"},
    {"now": NOW + 900},
    {"operator_ack": False},
])
def test_missing_invalid_expired_or_wrong_identity_never_seals(prepared, corruption):  # noqa: F811
    args, g22, *_ = prepared
    with pytest.raises(PublicCandidateLockRefused):
        seal_public_candidate(**{**args, **corruption})
    assert not inspect_public_candidate_lock(
        g22, tenant_id=TENANT, binding_id="binding_a")["sealed"]


def test_revoked_signer_or_host_statement_blocks_seal(prepared):  # noqa: F811
    args, g22, _g23, g24 = prepared
    g24.revoke(HOST, operator_ack=True)
    with pytest.raises(PublicCandidateLockRefused, match="INVALID_REVOKED"):
        seal_public_candidate(**args)
    assert not inspect_public_candidate_lock(
        g22, tenant_id=TENANT, binding_id="binding_a")["sealed"]


def test_postseal_revocation_cannot_reactivate_a_candidate(prepared):  # noqa: F811
    args, g22, g23, g24 = prepared
    seal_public_candidate(**args)
    g23.revoke(TENANT, "binding_a", operator_ack=True)
    g24.revoke(HOST, operator_ack=True)
    with pytest.raises(PublicCandidateLockRefused):
        seal_public_candidate(**args)
    with pytest.raises(Stage22Refused, match="STAGE26_PUBLIC"):
        g22.set_enabled(TENANT, "binding_a", enabled=True,
                        expected_revision=1, operator_ack=True)


def test_repeat_seal_and_old_research_do_not_gain_public_permission(prepared):  # noqa: F811
    args, g22, *_ = prepared
    assert review_preinstall_evidence(**args).installation_authorized is False
    seal_public_candidate(**args)
    with pytest.raises(PublicCandidateLockRefused, match="CAS_OR_EXECUTION_HISTORY"):
        seal_public_candidate(**args)
    assert g22.state(TENANT, "binding_a")["broker_order_authorized"] is False


def test_stage25_unsupported_legacy_activation_cannot_promote(prepared):  # noqa: F811
    args, g22, *_ = prepared
    g22.set_enabled(TENANT, "binding_a", enabled=True,
                    expected_revision=1, operator_ack=True)
    assert g22.state(TENANT, "binding_a")["state"] == "ENABLED"
    with pytest.raises(PublicCandidateLockRefused, match="INVALID_REVOKED"):
        seal_public_candidate(**args)


def test_physical_db_shutdown_keeps_permanent_public_fence(
        prepared):  # noqa: F811
    args, g22, *_ = prepared
    seal_public_candidate(**args)
    # A second SQLite connection has exactly the same trigger defense.
    with sqlite3.connect(g22.path) as other:
        with pytest.raises(sqlite3.IntegrityError, match="STAGE26_PUBLIC_EXECUTION"):
            other.execute(
                "UPDATE secure22_bindings SET state='ENABLED' WHERE binding_id='binding_a'")


def test_explicit_nonproduction_fence_works_after_correct_signatures(
        prepared, monkeypatch):  # noqa: F811
    args, g22, *_ = prepared
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(PublicCandidateLockRefused, match="EXPLICIT_NONPRODUCTION"):
        seal_public_candidate(**args)
    assert not inspect_public_candidate_lock(
        g22, tenant_id=TENANT, binding_id="binding_a")["sealed"]
