"""Stage27 signed public intake never enables an executable third-party core."""
from __future__ import annotations

import hashlib
import os
import sqlite3

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.core_api_v1 import content_digest
from naseri_markets.durable_isolated_core_gate_stage22_v1 import (
    DurableIsolatedCoreGate, Stage22Refused,
)
from naseri_markets.host_observation_custody_stage24_v1 import HostObservationLedger
from naseri_markets.public_candidate_lock_stage26_v1 import seal_public_candidate
from naseri_markets.signed_public_intake_stage27_v1 import (
    PublicIntakeRefused, inspect_public_intake, register_signed_public_candidate,
)
from test_durable_isolated_core_gate_stage22_v1 import host  # noqa: F401
from test_signed_core_candidate_stage23_v1 import (
    TENANT, PUB, KEY_ID, NOW, key_bytes, signed, trusted,  # noqa: F401
)
from test_host_observation_custody_stage24_v1 import HOST, raw_receipt
from test_secure_plugin_runtime_v1 import CORE, IMAGE, SHA, SOURCE, event


@pytest.fixture(autouse=True)
def safe(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


@pytest.fixture
def public_case(tmp_path, host, trusted):  # noqa: F811
    witness, _publisher, _operator, _path = trusted
    payload = signed(trusted)
    witness.admit(
        payload, source=SOURCE, manifest=CORE.manifest, binding=event().binding,
        tenant_id=TENANT, publisher=PUB, publisher_key_id=KEY_ID,
        image=IMAGE, now=NOW, operator_ack=True)
    with DurableIsolatedCoreGate(
            tmp_path / "stage27.sqlite", host=host) as gate:
        options = dict(
            stage22=gate, stage23=witness, tenant_id=TENANT,
            publisher=PUB, publisher_key_id=KEY_ID,
            manifest=CORE.manifest, binding=event().binding,
            source=SOURCE, signed_candidate=payload,
            expected_image=IMAGE, now=NOW, operator_ack=True)
        yield options, gate, witness


def test_public_registration_is_atomic_default_denied_and_signed(public_case, monkeypatch):
    args, stage22, _witness = public_case
    called = []
    monkeypatch.setattr(stage22.host, "evaluate",
                        lambda *_a, **_kw: called.append("BAD"))
    registration = register_signed_public_candidate(**args)
    assert registration.status == "SIGNED_PUBLIC_UNTRUSTED_INTAKE_BLOCKED"
    assert registration.classified_public
    assert registration.stage22_revision == 1
    assert registration.signed_publisher_claim_current
    assert not registration.runtime_execution_authorized
    assert not registration.public_installer_authorized
    assert not registration.telegram_signal_authorized
    assert not registration.broker_order_authorized
    assert not registration.live_trading_authorized
    assert not registration.independent_host_isolation_verified
    row = stage22.state(TENANT, "binding_a")
    assert row["state"] == "DISABLED"
    assert row["public_untrusted_intake_pending"]
    result = inspect_public_intake(
        stage22, tenant_id=TENANT, binding_id="binding_a")
    assert result["public_classified"]
    assert result["public_intake_status"] == "PUBLIC_UNTRUSTED_PENDING_INDEPENDENT_HOST"
    with pytest.raises(Stage22Refused, match="STAGE27_PUBLIC_UNTRUSTED"):
        stage22.set_enabled(TENANT, "binding_a", enabled=True,
                            expected_revision=1, operator_ack=True)
    with pytest.raises(Stage22Refused, match="STAGE27_PUBLIC_UNTRUSTED"):
        stage22.evaluate(TENANT, CORE.manifest, event(),
                         source=SOURCE, operator_ack=True)
    assert called == []


def test_raw_sql_cannot_activate_or_add_new_attempt_or_unclassify(public_case):
    args, stage22, _ = public_case
    register_signed_public_candidate(**args)
    with pytest.raises(sqlite3.IntegrityError, match="STAGE27_PUBLIC_ACTIVATION"):
        stage22.db.execute(
            "UPDATE secure22_bindings SET state='ENABLED' WHERE binding_id='binding_a'")
    with pytest.raises(sqlite3.IntegrityError, match="STAGE27_PUBLIC_ATTEMPT"):
        stage22.db.execute(
            "INSERT INTO secure22_attempts VALUES(?,?,?,?,?)",
            ("binding_a", "rogueinput", 2, "IN_FLIGHT", None))
    with pytest.raises(sqlite3.IntegrityError, match="STAGE27_CLASSIFICATION_IS_IMMUTABLE"):
        stage22.db.execute(
            "UPDATE secure27_public_intake SET tenant_id='tenant_beta' "
            "WHERE binding_id='binding_a'")
    with pytest.raises(sqlite3.IntegrityError, match="STAGE27_CLASSIFICATION_IS_PERMANENT"):
        stage22.db.execute(
            "DELETE FROM secure27_public_intake WHERE binding_id='binding_a'")
    with sqlite3.connect(stage22.path) as second:
        with pytest.raises(sqlite3.IntegrityError, match="STAGE27_PUBLIC_ACTIVATION"):
            second.execute(
                "UPDATE secure22_bindings SET state='ENABLED' "
                "WHERE binding_id='binding_a'")


def test_owner_id_and_duplicate_registration_do_not_mutate_other_tenant(public_case):
    args, stage22, _ = public_case
    with pytest.raises(PublicIntakeRefused):
        register_signed_public_candidate(**{**args, "tenant_id": "tenant_beta"})
    assert not stage22.db.execute(
        "SELECT 1 FROM secure22_bindings WHERE binding_id='binding_a'").fetchone()
    register_signed_public_candidate(**args)
    with pytest.raises(PublicIntakeRefused):
        register_signed_public_candidate(**args)
    with pytest.raises(Stage22Refused, match="TENANT_BINDING_NOT_AUTHORIZED"):
        stage22.state("tenant_beta", "binding_a")


@pytest.mark.parametrize("corruption", [
    {"publisher": "counterfeit.vendor"},
    {"publisher_key_id": "stolen_key"},
    {"tenant_id": "tenant_beta"},
    {"source": b"modified source"},
    {"signed_candidate": b"{}"},
    {"expected_image": "registry.invalid/fake@sha256:"+"b"*64},
    {"now": NOW+2000},
    {"operator_ack": False},
])
def test_missing_or_invalid_signed_auth_never_registers(public_case, corruption):
    args, stage22, _ = public_case
    with pytest.raises(PublicIntakeRefused):
        register_signed_public_candidate(**{**args, **corruption})
    assert stage22.db.execute(
        "SELECT COUNT(*) FROM secure22_bindings").fetchone()[0] == 0
    assert stage22.db.execute(
        "SELECT COUNT(*) FROM secure27_public_intake").fetchone()[0] == 0


def test_revoked_publisher_candidate_never_creates_binding(public_case):
    args, stage22, witness = public_case
    witness.revoke(TENANT, "binding_a", operator_ack=True)
    with pytest.raises(PublicIntakeRefused):
        register_signed_public_candidate(**args)
    assert not stage22.db.execute(
        "SELECT 1 FROM secure27_public_intake").fetchone()


def test_atomic_registry_second_insert_failure_rolls_back_binding(
        public_case):
    args, stage22, _ = public_case
    # A separately opened connection may not tamper protected real records.
    # Simulate a fault in Stage27's SECOND INSERT with a persistent trigger.
    stage22.db.execute("""
       CREATE TRIGGER fail_stage27_insert BEFORE INSERT ON secure27_public_intake
       BEGIN SELECT RAISE(ABORT,'INJECTED_DISK_REJECTION'); END
    """)
    with pytest.raises(PublicIntakeRefused, match="ATOMIC_INTAKE_FAILED"):
        register_signed_public_candidate(**args)
    assert stage22.db.execute(
        "SELECT COUNT(*) FROM secure22_bindings").fetchone()[0] == 0
    assert stage22.db.execute(
        "SELECT COUNT(*) FROM secure27_public_intake").fetchone()[0] == 0


def test_stage26_sealing_keeps_both_persistent_denial_layers(public_case, tmp_path):
    args, stage22, stage23 = public_case
    receipt = register_signed_public_candidate(**args)
    reviewer = Ed25519PrivateKey.generate()
    reviewer_public = key_bytes(reviewer)
    with HostObservationLedger(
            tmp_path / "stage24.sqlite",
            reviewer_public_key=reviewer_public,
            approved_reviewer_key_sha256=hashlib.sha256(reviewer_public).hexdigest(),
            operator_ack=True) as stage24:
        from test_host_observation_custody_stage24_v1 import signed as sign_host
        canary = raw_receipt()
        observation = sign_host(reviewer, canary)
        stage24.record(observation, canary, expected_host_id=HOST,
                       expected_image=IMAGE, now=NOW, operator_ack=True)
        seal = seal_public_candidate(
            stage22=stage22, stage23=stage23, stage24=stage24,
            candidate=args["signed_candidate"], source=SOURCE,
            manifest=CORE.manifest, binding=event().binding,
            observation=observation, canary_receipt=canary,
            tenant_id=TENANT, publisher=PUB, publisher_key_id=KEY_ID,
            host_id=HOST, expected_image=IMAGE, now=NOW, operator_ack=True)
        assert seal.candidate_sha256 == receipt.candidate_sha256
        assert stage22.state(TENANT, "binding_a")["public_untrusted_candidate_locked"]
        assert stage22.state(TENANT, "binding_a")["public_untrusted_intake_pending"]
        with pytest.raises(Stage22Refused):
            stage22.set_enabled(TENANT, "binding_a", enabled=True,
                                expected_revision=1, operator_ack=True)


def test_stage22_trusted_research_regression_still_explicitly_separate(
        tmp_path, host):  # noqa: F811
    with DurableIsolatedCoreGate(tmp_path / "research.sqlite", host=host) as gate:
        response = gate.register(
            TENANT, CORE.manifest, event().binding,
            approved_manifest_digest=content_digest(CORE.manifest),
            approved_source_sha256=SHA, operator_ack=True)
        assert response["state"] == "DISABLED"
        assert not response["public_untrusted_intake_pending"]
        enabled = gate.set_enabled(TENANT, "binding_a",
                                   enabled=True, expected_revision=1,
                                   operator_ack=True)
        assert enabled["state"] == "ENABLED"


def test_production_flag_blocks_public_registration(public_case, monkeypatch):
    args, stage22, _ = public_case
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(PublicIntakeRefused, match="EXPLICIT_NONPRODUCTION"):
        register_signed_public_candidate(**args)
    assert not stage22.db.execute(
        "SELECT 1 FROM secure22_bindings").fetchone()
