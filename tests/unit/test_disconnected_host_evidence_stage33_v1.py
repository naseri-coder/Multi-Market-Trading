"""Stage33 signing and replay safety. Synthetic claims are never host proof."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.disconnected_host_evidence_stage33_v1 import (
    DisconnectedHostEvidenceLedger, Stage33Refused,
    _DOMAIN, host_assessment_checklist,
)
from test_disposable_host_preflight_stage32_v1 import (
    dossier, fixture_and_policy, signed_review, research_only,  # noqa: F401
)
from test_tls_boundary_stage31_v1 import tls_material  # noqa: F401

HOST = "disposable_staging_one"


@pytest.fixture
def prepared(fixture_and_policy, dossier):  # noqa: F811
    (_, _, _, now), _, fixture, policy = fixture_and_policy
    stage32, preparer, path = dossier
    signed = signed_review(preparer, fixture, policy, now)
    prepared_receipt = stage32.record(
        signed, fixture=fixture, proposed_policy=policy,
        now=now, operator_ack=True)
    auditor = Ed25519PrivateKey.generate()
    auditor_public = auditor.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    journal = DisconnectedHostEvidenceLedger(
        stage32, auditor_public_key=auditor_public,
        pinned_auditor_sha256=hashlib.sha256(auditor_public).hexdigest(),
        operator_ack=True)
    yield journal, auditor, prepared_receipt, now, path, stage32


def claim(prepared, *, statuses=None, sequence=1, **overrides):
    _journal, auditor, stage32, now, _path, _source = prepared
    statuses = statuses or {}
    checks = {
        item: {
            "status": statuses.get(item, "NOT_RUN"),
            "evidence_sha256": (
                "a"*64 if statuses.get(item) in
                ("DECLARED_PASS", "DECLARED_FAIL") else None),
        }
        for item in host_assessment_checklist()
    }
    body = {
        "version": 1, "kind": "disconnected_host_assessment_claims",
        "host_alias": HOST, "sequence": sequence, "issued_at": now-15,
        "expires_at": now+240,
        "stage32_preparation_sha256": stage32.statement_sha256,
        "checks": checks, "scope": "signed_claims_only_no_remote_attestation",
        "public_deployment_authorized": False,
        "plugin_install_authorized": False,
        "strategy_source_executed": False,
        "telegram_signal_authorized": False,
        "broker_order_authorized": False,
    }
    body.update(overrides)
    return canonical({
        "report": body, "auditor_signature_b64": base64.b64encode(
            auditor.sign(_DOMAIN + canonical(body))).decode("ascii"),
    })


def test_no_claims_no_assigned_host_is_hard_block(prepared):
    journal, *_ = prepared
    s = journal.status(HOST)
    assert s["recorded_claims"] == 0
    assert s["last_sequence"] is None
    assert not s["host_designated_and_independently_attested"]
    assert not s["live_tls_verified"]
    assert not s["firewall_tested"]
    assert not s["gvisor_validated"]
    assert not s["public_api_deployment_authorized"]


def test_complete_signed_claims_are_not_verified_real_host(prepared):
    journal, *_ = prepared
    statuses = {name: "DECLARED_PASS" for name in host_assessment_checklist()}
    packet = claim(prepared, statuses=statuses)
    receipt = journal.record(packet, now=prepared[3], operator_ack=True)
    assert receipt.sequence == 1
    assert receipt.signed_report_sha256 == hashlib.sha256(packet).hexdigest()
    assert receipt.declared_pass_checks == len(host_assessment_checklist())
    assert receipt.remaining_unrun_checks == 0
    assert receipt.state == "SIGNED_CLAIMS_NOT_INDEPENDENTLY_VERIFIED"
    assert not receipt.actual_host_independently_verified
    assert not receipt.actual_tls_endpoint_verified
    assert not receipt.network_policy_enforced
    assert not receipt.gvisor_isolation_certified
    assert not receipt.public_ingress_authorized
    assert not receipt.public_installer_authorized
    assert not receipt.telegram_send_authorized
    assert not receipt.broker_order_authorized
    s = journal.status(HOST)
    assert s["recorded_claims"] == 1
    assert not s["host_designated_and_independently_attested"]


def test_missing_and_failed_declared_checks_never_unlock(prepared):
    journal, *_ = prepared
    items = host_assessment_checklist()
    packet = claim(prepared, statuses={
        items[0]: "DECLARED_FAIL", items[1]: "DECLARED_PASS"})
    r = journal.record(packet, now=prepared[3], operator_ack=True)
    assert r.declared_failed_checks == 1
    assert r.declared_pass_checks == 1
    assert r.remaining_unrun_checks == len(items)-2
    assert not r.public_installer_authorized
    assert not r.actual_host_independently_verified


@pytest.mark.parametrize("changes", [
    {"public_deployment_authorized": True},
    {"plugin_install_authorized": True},
    {"strategy_source_executed": True},
    {"telegram_signal_authorized": True},
    {"broker_order_authorized": True},
    {"kind": "live_host_attested"},
    {"scope": "independently_verified"},
    {"host_alias": "other_alias"},
    {"version": True},
    {"sequence": True},
    {"sequence": 0},
    {"stage32_preparation_sha256": "0"*64},
    {"expires_at": 2**63},
    {"extra": "escape"},
])
def test_false_privilege_and_invalid_signed_attestations_fail_closed(
        prepared, changes):
    journal, *_ = prepared
    with pytest.raises(Stage33Refused):
        journal.record(claim(prepared, **changes), now=prepared[3],
                       operator_ack=True)
    assert journal.status(HOST)["recorded_claims"] == 0


def test_forged_second_auditor_tampered_envelope_and_duplicate_keys(prepared):
    journal, *_ = prepared
    signed = json.loads(claim(prepared))
    attacker = Ed25519PrivateKey.generate()
    signed["auditor_signature_b64"] = base64.b64encode(
        attacker.sign(_DOMAIN+canonical(signed["report"]))).decode()
    with pytest.raises(Stage33Refused, match="AUDITOR_SIGNATURE"):
        journal.record(canonical(signed), now=prepared[3], operator_ack=True)
    good = claim(prepared)
    with pytest.raises(Stage33Refused, match="EXACT_SIGNED"):
        journal.record(json.dumps(json.loads(good), indent=2).encode("ascii"),
                       now=prepared[3], operator_ack=True)
    duplicate = good.replace(b'{"auditor_signature_b64":',
                             b'{"auditor_signature_b64":"x","auditor_signature_b64":',
                             1)
    with pytest.raises(Stage33Refused, match="DUPLICATE"):
        journal.record(duplicate, now=prepared[3], operator_ack=True)


def test_nonfinite_or_missing_check_and_digest_confusion_denied(prepared):
    journal, *_ = prepared
    data = json.loads(claim(prepared))["report"]
    name = host_assessment_checklist()[0]
    data["checks"].pop(name)
    with pytest.raises(Stage33Refused, match="ALL_REQUIRED_HOST_CHECKS"):
        journal.record(claim(prepared, checks=data["checks"]),
                       now=prepared[3], operator_ack=True)
    data = json.loads(claim(prepared))["report"]
    data["checks"][name] = {"status":"DECLARED_PASS","evidence_sha256":None}
    with pytest.raises(Stage33Refused, match="DECLARED_CHECK_NEEDS"):
        journal.record(claim(prepared, checks=data["checks"]),
                       now=prepared[3], operator_ack=True)
    data["checks"][name] = {"status":"NOT_RUN","evidence_sha256":"a"*64}
    with pytest.raises(Stage33Refused, match="NO_EVIDENCE"):
        journal.record(claim(prepared, checks=data["checks"]),
                       now=prepared[3], operator_ack=True)


def test_sequence_replay_gap_and_sqlite_row_immutability(prepared):
    journal, *_ = prepared
    now = prepared[3]
    first = claim(prepared)
    journal.record(first, now=now, operator_ack=True)
    with pytest.raises(Stage33Refused, match="REPLAY"):
        journal.record(first, now=now, operator_ack=True)
    with pytest.raises(Stage33Refused, match="REPLAY"):
        journal.record(claim(prepared, sequence=3), now=now, operator_ack=True)
    journal.record(claim(prepared, sequence=2), now=now, operator_ack=True)
    with pytest.raises(sqlite3.IntegrityError, match="STAGE33_APPEND_ONLY"):
        journal.db.execute("DELETE FROM stage33_signed_host_claims")
    with pytest.raises(sqlite3.IntegrityError, match="STAGE33_APPEND_ONLY"):
        journal.db.execute(
            "UPDATE stage33_signed_host_claims SET declared_pass=12")
    assert journal.status(HOST)["last_sequence"] == 2


def test_distinct_signing_roles_and_persistent_pin(prepared):
    journal, auditor, _, now, _, stage32 = prepared
    same = stage32.reviewer_public_key
    with pytest.raises(Stage33Refused, match="SEPARATE_OUT_OF_BAND"):
        DisconnectedHostEvidenceLedger(
            stage32, auditor_public_key=same,
            pinned_auditor_sha256=hashlib.sha256(same).hexdigest(),
            operator_ack=True)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    with pytest.raises(Stage33Refused, match="AUDITOR_PIN_CHANGED"):
        DisconnectedHostEvidenceLedger(
            stage32, auditor_public_key=other,
            pinned_auditor_sha256=hashlib.sha256(other).hexdigest(),
            operator_ack=True)
    assert journal.record(
        claim(prepared), now=now, operator_ack=True).sequence == 1


def test_expired_preparation_and_report_denied(prepared):
    journal, *_ = prepared
    now = prepared[3]
    with pytest.raises(Stage33Refused, match="UNSUPPORTED_OR_FALSE"):
        journal.record(
            claim(prepared, issued_at=now-1000, expires_at=now-1),
            now=now, operator_ack=True)
    with pytest.raises(Stage33Refused, match="STAGE32_PREPARATION_NOT_CURRENT"):
        journal.record(
            claim(prepared, issued_at=now+1000, expires_at=now+1900),
            now=now+1200, operator_ack=True)


def test_nonproduction_and_explicit_ack_required(prepared, monkeypatch):
    journal, *_ = prepared
    with pytest.raises(Stage33Refused, match="EXPLICIT_NONPRODUCTION"):
        journal.record(claim(prepared), now=prepared[3], operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage33Refused, match="EXPLICIT_NONPRODUCTION"):
        journal.record(claim(prepared), now=prepared[3], operator_ack=True)
    assert journal.status(HOST)["recorded_claims"] == 0
