"""Stage35 cross-stage evidence-chain safety. All inputs are synthetic.

No host, listener or network path is contacted. A synthetic Stage34 receipt
can be signed by an auditor and still DOES NOT verify a real host.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.designated_host_readonly_probe_stage34_v1 import (
    HostLocalProbeReceipt,
)
from naseri_markets.self_observation_evidence_chain_stage35_v1 import (
    SelfObservationEvidenceChain, Stage35Refused, _DOMAIN,
)
from test_disconnected_host_evidence_stage33_v1 import (
    HOST, prepared, claim,  # noqa: F401
)
from test_disposable_host_preflight_stage32_v1 import (
    fixture_and_policy, dossier, research_only,  # noqa: F401
)
from test_tls_boundary_stage31_v1 import tls_material  # noqa: F401

NODE = "pinned-disposable-node"


@pytest.fixture
def chain(prepared, fixture_and_policy):  # noqa: F811
    journal, auditor, preparation, now, _path, _stage32 = prepared
    (_cert, _key, digest, _now), _proposal, _fixture, _policy = fixture_and_policy
    assert digest == _fixture.certificate_sha256
    journal.record(claim(prepared), now=now, operator_ack=True)
    worker = SelfObservationEvidenceChain(journal, operator_ack=True)
    receipt = HostLocalProbeReceipt(
        host_alias=HOST, nodename=NODE, measured_at=now-20,
        listener_snapshot_sha256="b"*64, local_listener_count=1,
        local_tls_cert_sha256=digest,
        local_tls_cipher="TLS_AES_256_GCM_SHA384")
    return worker, prepared, auditor, preparation, now, receipt


def signed_binding(chain, *, receipt=None, report_sha=None,
                   host_alias=HOST, node=NODE, sequence=1, **changes):
    worker, _prepared, signer, prep, now, original = chain
    received = receipt or original
    latest = worker.db.execute(
        "SELECT signed_sha256 FROM stage33_signed_host_claims "
        "WHERE host_alias=? ORDER BY sequence DESC LIMIT 1",
        (HOST,)).fetchone()
    report_hash = report_sha or latest[0]
    body = {
        "version": 1, "kind": "stage34_self_observation_binding",
        "host_alias": host_alias, "nodename": node, "sequence": sequence,
        "stage32_preparation_sha256": prep.statement_sha256,
        "stage33_claim_sha256": report_hash,
        "stage34_probe_sha256": received.evidence_sha256(),
        "probe_measured_at": received.measured_at,
        "issued_at": now-5, "expires_at": now+200,
        "scope": "local_evidence_custody_not_host_attestation",
        "independent_host_attested": False,
        "public_deployment_authorized": False,
        "plugin_install_authorized": False,
        "broker_order_authorized": False,
        "telegram_send_authorized": False,
    }
    body.update(changes)
    signature = signer.sign(_DOMAIN + canonical(body))
    return canonical({
        "claim": body,
        "auditor_signature_b64": base64.b64encode(signature).decode("ascii"),
    })


def test_signed_chain_is_immutable_but_not_real_host_attestation(chain):
    worker, _prepared, _auditor, prep, now, receipt = chain
    signed = signed_binding(chain)
    outcome = worker.record(
        stage34_probe=receipt.evidence_json(),
        signed_binding=signed, expected_nodename=NODE,
        now=now, operator_ack=True)
    assert outcome.state == "STAGE34_SELF_OBSERVATION_CHAINED_NOT_HOST_ATTESTED"
    assert outcome.sequence == 1
    assert outcome.stage32_preparation_sha256 == prep.statement_sha256
    assert outcome.stage34_probe_sha256 == receipt.evidence_sha256()
    assert outcome.signed_binding_sha256 == hashlib.sha256(signed).hexdigest()
    for attr in (
        "actual_host_independently_attested", "real_public_tls_verified",
        "firewall_independently_verified", "gvisor_isolation_verified",
        "public_deployment_authorized", "public_installer_authorized",
        "untrusted_source_execution_authorized", "telegram_send_authorized",
        "broker_order_authorized",
    ):
        assert getattr(outcome, attr) is False
    assert worker.status(HOST)["linked_self_observations"] == 1
    assert not worker.status(HOST)["public_api_authorized"]
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_CHAIN"):
        worker.db.execute(
            "UPDATE stage35_self_observation_bindings "
            "SET stage34_probe_sha256=?", ("0"*64,))
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_CHAIN"):
        worker.db.execute("DELETE FROM stage35_self_observation_bindings")


def test_absent_stage33_claim_never_creates_a_record(prepared, fixture_and_policy):  # noqa: F811
    journal, *_ = prepared
    worker = SelfObservationEvidenceChain(journal, operator_ack=True)
    assert worker.status(HOST)["linked_self_observations"] == 0
    assert not worker.status(HOST)["real_host_independently_verified"]


@pytest.mark.parametrize("alter", [
    {"state": "REAL_HOST_SECURITY_VERIFIED"},
    {"host_designation_independently_verified": True},
    {"external_tls_or_dns_verified": True},
    {"firewall_policy_independently_verified": True},
    {"outbound_network_denial_verified": True},
    {"reverse_proxy_verified": True},
    {"gvisor_isolation_verified": True},
    {"hostile_source_executed": True},
    {"public_deployment_authorized": True},
    {"plugin_install_authorized": True},
    {"telegram_signal_authorized": True},
    {"broker_order_authorized": True},
    {"real_loopback_tls_handshake_observed": False},
    {"local_listener_count": True},
    {"local_listener_count": 0},
    {"local_tls_cipher": "TLS_RSA_WITH_RC4_128_SHA"},
    {"local_tls_cert_sha256": "0"*64},
    {"host_alias": "foreign_host"},
    {"nodename": "other-host"},
])
def test_stage34_self_report_tampering_or_false_privileges_fail_closed(
        chain, alter):
    worker, _prepared, _auditor, _prep, now, receipt = chain
    bad = {**json.loads(receipt.evidence_json()), **alter}
    raw = canonical(bad)
    # Sign the altered receipt digest with the *real* auditor to show
    # a valid signature cannot turn a false authorization into a pass.
    edited = HostLocalProbeReceipt(**{
        **json.loads(receipt.evidence_json()),
        **{k: v for k, v in alter.items()
           if k in json.loads(receipt.evidence_json())}})
    packet = signed_binding(chain, receipt=edited)
    with pytest.raises(Stage35Refused):
        worker.record(
            stage34_probe=raw, signed_binding=packet,
            expected_nodename=NODE, now=now, operator_ack=True)
    assert worker.status(HOST)["linked_self_observations"] == 0


@pytest.mark.parametrize("alter", [
    {"public_deployment_authorized": True},
    {"independent_host_attested": True},
    {"plugin_install_authorized": True},
    {"telegram_send_authorized": True},
    {"broker_order_authorized": True},
    {"scope": "certified_real_host"},
    {"kind": "production_host_admission"},
    {"nodename": "attacker"},
    {"host_alias": "external_host"},
    {"sequence": 0},
    {"sequence": True},
    {"expires_at": 2**63},
    {"stage32_preparation_sha256": "0"*64},
    {"stage33_claim_sha256": "0"*64},
    {"stage34_probe_sha256": "0"*64},
    {"probe_measured_at": True},
    {"extra": "undeclared_capability"},
])
def test_altered_even_validly_signed_auditor_claim_is_refused(chain, alter):
    worker, _prepared, _auditor, _prep, now, receipt = chain
    with pytest.raises(Stage35Refused):
        worker.record(
            stage34_probe=receipt.evidence_json(),
            signed_binding=signed_binding(chain, **alter),
            expected_nodename=NODE, now=now, operator_ack=True)
    assert worker.status(HOST)["linked_self_observations"] == 0


def test_stage34_evidence_json_must_be_exact_and_canonical(chain):
    worker, _prepared, _auditor, _prep, now, receipt = chain
    signed = signed_binding(chain)
    raw = receipt.evidence_json()
    for changed in (
        raw+b" ", json.dumps(json.loads(raw),indent=2).encode(),
        raw.replace(b'"host_alias":',b'"host_alias":"duplicate","host_alias":',1),
        raw.replace(b'"measured_at":',b'"unknown":123,"measured_at":',1),
        b"{}", b"[]", b"\xff"*8, b"x"*5000,
    ):
        with pytest.raises(Stage35Refused):
            worker.record(
                stage34_probe=changed, signed_binding=signed,
                expected_nodename=NODE, now=now, operator_ack=True)


def test_forged_auditor_wrong_digest_future_or_stale_reading(chain):
    worker, _prepared, _auditor, _prep, now, receipt = chain
    packet = json.loads(signed_binding(chain))
    foreign = Ed25519PrivateKey.generate()
    packet["auditor_signature_b64"] = base64.b64encode(
        foreign.sign(_DOMAIN + canonical(packet["claim"]))).decode()
    with pytest.raises(Stage35Refused, match="SIGNATURE"):
        worker.record(
            stage34_probe=receipt.evidence_json(),
            signed_binding=canonical(packet), expected_nodename=NODE,
            now=now, operator_ack=True)
    with pytest.raises(Stage35Refused, match="STALE|FRESHNESS|SCOPE"):
        old = HostLocalProbeReceipt(
            **{**json.loads(receipt.evidence_json()), "measured_at": now-1000})
        worker.record(
            stage34_probe=old.evidence_json(),
            signed_binding=signed_binding(chain, receipt=old),
            expected_nodename=NODE, now=now, operator_ack=True)


def test_tampered_stage33_packet_is_not_trusted_as_preexisting_proof(chain):
    worker, _prepared, _auditor, _prep, now, receipt = chain
    # Privileged DB-owner tampering outside Stage33 SQL API: Stage35 must
    # still refuse an altered signature. This does not bypass real custody.
    worker.db.execute("DROP TRIGGER stage33_no_edit")
    worker.db.execute(
        "UPDATE stage33_signed_host_claims SET signed_envelope=?",
        (b'{"spoof":"untrusted"}',))
    with pytest.raises((Stage35Refused, ValueError, KeyError)):
        worker.record(
            stage34_probe=receipt.evidence_json(),
            signed_binding=signed_binding(chain), expected_nodename=NODE,
            now=now, operator_ack=True)


def test_stage33_claim_supersession_and_stage35_sequence_replay_denied(chain):
    worker, prepared, _auditor, _prep, now, receipt = chain
    old_report = worker.db.execute(
        "SELECT signed_sha256 FROM stage33_signed_host_claims"
    ).fetchone()[0]
    prepared[0].record(claim(prepared, sequence=2),
                       now=now, operator_ack=True)
    with pytest.raises(Stage35Refused, match="SUPERSEDED"):
        worker.record(
            stage34_probe=receipt.evidence_json(),
            signed_binding=signed_binding(chain, report_sha=old_report),
            expected_nodename=NODE, now=now, operator_ack=True)
    current = signed_binding(chain, sequence=2)
    with pytest.raises(Stage35Refused, match="SEQUENCE"):
        worker.record(
            stage34_probe=receipt.evidence_json(), signed_binding=current,
            expected_nodename=NODE, now=now, operator_ack=True)


def test_replay_and_change_of_expected_nodename_denied(chain):
    worker, _prepared, _auditor, _prep, now, receipt = chain
    signed = signed_binding(chain)
    worker.record(stage34_probe=receipt.evidence_json(),
                  signed_binding=signed, expected_nodename=NODE,
                  now=now, operator_ack=True)
    with pytest.raises(Stage35Refused, match="SEQUENCE"):
        worker.record(stage34_probe=receipt.evidence_json(),
                      signed_binding=signed, expected_nodename=NODE,
                      now=now, operator_ack=True)
    with pytest.raises(Stage35Refused):
        worker.record(stage34_probe=receipt.evidence_json(),
                      signed_binding=signed, expected_nodename="wrong.node",
                      now=now, operator_ack=True)


def test_no_operator_ack_or_production_registration(chain, monkeypatch):
    worker, _prepared, _auditor, _prep, now, receipt = chain
    with pytest.raises(Stage35Refused, match="NONPRODUCTION"):
        worker.record(stage34_probe=receipt.evidence_json(),
                      signed_binding=signed_binding(chain),
                      expected_nodename=NODE, now=now, operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(Stage35Refused, match="NONPRODUCTION"):
        worker.record(stage34_probe=receipt.evidence_json(),
                      signed_binding=signed_binding(chain),
                      expected_nodename=NODE, now=now, operator_ack=True)
    assert worker.status(HOST)["linked_self_observations"] == 0
