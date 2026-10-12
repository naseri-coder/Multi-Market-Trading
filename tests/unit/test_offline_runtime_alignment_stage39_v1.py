"""Stage39: signed offline Stage37 runsc policy / Stage38 process observation.

All input receipts are synthetic. Never samples the CI host or runs Docker.
A consistent signed self-report still cannot prove gVisor is truly enforced.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.offline_runtime_alignment_stage39_v1 import (
    Stage39Refused, _DOMAIN, verify_offline_runtime_alignment,
)
from naseri_markets.passive_kernel_posture_stage38_v1 import (
    PassiveKernelObservationReceipt,
)
from test_offline_host_controls_stage37_v1 import (  # noqa: F401
    prepared_controls,
)
from test_portable_evidence_verifier_stage36_v1 import exported  # noqa: F401
from test_self_observation_evidence_chain_stage35_v1 import (  # noqa: F401
    chain, signed_binding,
)
from test_disconnected_host_evidence_stage33_v1 import (  # noqa: F401
    prepared, claim, research_only,
)
from test_disposable_host_preflight_stage32_v1 import (  # noqa: F401
    fixture_and_policy, dossier,
)
from test_tls_boundary_stage31_v1 import tls_material  # noqa: F401

HOST = "disposable_staging_one"
NODE = "pinned-disposable-node"
NONCE = "7"*32


@pytest.fixture
def aligned_case(prepared_controls):
    archive, prior, _third = prepared_controls
    signer = Ed25519PrivateKey.generate()
    public = signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    now = prior["now"]
    observation = PassiveKernelObservationReceipt(
        host_alias=HOST, nodename=NODE, measured_at=now-10,
        process_uid=65534, process_gid=65534,
        proc_status_sha256="a"*64,
        proc_mountinfo_sha256="b"*64,
        proc_ipv4_routes_sha256="c"*64,
        proc_ipv6_routes_sha256="d"*64,
        loopback_routes_seen=2,
    )
    self_report = observation.sanitized_json()
    statement = {
        "schema": 1,
        "kind": "static_runsc_to_self_process_alignment",
        "scope": "signed_self_report_not_runtime_attestation",
        "host_alias": HOST, "nodename": NODE,
        "stage35_binding_sha256":
            prior["stage36_verification"]["pinned_stage35_sha256"],
        "stage37_review_sha256": hashlib.sha256(
            prior["signed_review"]).hexdigest(),
        "stage38_self_report_sha256": hashlib.sha256(
            self_report).hexdigest(),
        "challenge": NONCE, "self_observed_at": now-10,
        "issued_at": now-3, "expires_at": now+120,
        "independent_host_attested": False,
        "runtime_isolation_independently_verified": False,
        "actual_firewall_verified": False,
        "public_deployment_authorized": False,
        "plugin_execution_authorized": False,
        "telegram_send_authorized": False,
        "broker_order_authorized": False,
    }
    args = {
        "stage37_options": prior, "stage38_self_report": self_report,
        "signed_alignment": make_signature(signer, statement),
        "witness_public_key": public,
        "witness_public_key_sha256": hashlib.sha256(public).hexdigest(),
        "expected_host_alias": HOST,
        "expected_nodename": NODE,
        "expected_challenge": NONCE,
        "now": now, "operator_ack": True,
    }
    return archive, args, signer, statement, observation


def make_signature(signer, claim):
    return canonical({
        "review": claim,
        "signature_b64": base64.b64encode(
            signer.sign(_DOMAIN+canonical(claim))).decode("ascii"),
    })


def test_offline_fourth_witness_is_not_real_host_or_gvisor_proof(aligned_case):
    archive, args, _key, _claim, receipt = aligned_case
    result = verify_offline_runtime_alignment(archive, **args)
    assert result.state == "SIGNED_OFFLINE_POLICY_ALIGNMENT_NOT_HOST_ATTESTED"
    assert result.nodename == NODE
    assert result.stage38_self_report_sha256 == receipt.digest_sha256()
    assert result.stage37_review_sha256 == hashlib.sha256(
        args["stage37_options"]["signed_review"]).hexdigest()
    for field in (
        "actual_gvisor_sandbox_observed",
        "self_report_origin_authenticated",
        "actual_host_independently_verified",
        "firewall_rules_actually_enforced",
        "outbound_network_deny_verified", "code_containment_certified",
        "public_deployment_authorized", "public_plugin_execution_authorized",
        "telegram_publish_authorized", "broker_order_authorized",
    ):
        assert getattr(result, field) is False


@pytest.mark.parametrize("change", [
    {"process_uid": 0}, {"process_gid": 0},
    {"process_uid": 1001}, {"process_gid": 1001},
    {"process_uid": True}, {"process_gid": True},
    {"local_process_restrictive_snapshot": False},
    {"independent_host_identity_verified": True},
    {"nftables_active_ruleset_independently_verified": True},
    {"network_egress_independently_blocked": True},
    {"other_container_gvisor_verified": True},
    {"gvisor_escape_containment_certified": True},
    {"public_api_deployment_authorized": True},
    {"plugin_execution_authorized": True},
    {"telegram_publish_authorized": True},
    {"broker_order_authorized": True},
    {"state": "HOST_ATTESTED"},
    {"host_alias": "other_host"}, {"nodename": "some_other_node"},
    {"loopback_routes_seen": -1},
    {"loopback_routes_seen": True},
    {"proc_mountinfo_sha256": "invalid"},
])
def test_even_signed_bad_self_process_claims_fail_closed(aligned_case, change):
    archive, args, signer, statement, receipt = aligned_case
    # Re-sign the hash with the true review key: signature must not bypass
    # type, privilege, identity, capability or digest restrictions.
    revised = {**json.loads(receipt.sanitized_json()), **change}
    raw = canonical(revised)
    claim = {**statement, "stage38_self_report_sha256":
             hashlib.sha256(raw).hexdigest()}
    new = {**args, "stage38_self_report": raw,
           "signed_alignment": make_signature(signer, claim)}
    with pytest.raises(Stage39Refused):
        verify_offline_runtime_alignment(archive, **new)


@pytest.mark.parametrize("shift", [-1000, 1000])
def test_old_or_future_self_report_is_refused(aligned_case, shift):
    archive, args, signer, statement, receipt = aligned_case
    old = replace(receipt, measured_at=args["now"]+shift)
    raw = old.sanitized_json()
    review = {**statement, "stage38_self_report_sha256":old.digest_sha256(),
              "self_observed_at": old.measured_at}
    with pytest.raises(Stage39Refused):
        verify_offline_runtime_alignment(archive, **{
            **args, "stage38_self_report": raw,
            "signed_alignment": make_signature(signer, review)})


@pytest.mark.parametrize("change", [
    {"independent_host_attested": True},
    {"runtime_isolation_independently_verified": True},
    {"actual_firewall_verified": True},
    {"public_deployment_authorized": True},
    {"plugin_execution_authorized": True},
    {"telegram_send_authorized": True},
    {"broker_order_authorized": True},
    {"stage35_binding_sha256": "0"*64},
    {"stage37_review_sha256": "0"*64},
    {"stage38_self_report_sha256": "0"*64},
    {"host_alias": "foreign_host"},
    {"nodename": "foreign_node"},
    {"challenge": "0"*32},
    {"issued_at": True},
    {"expires_at": 2**63},
    {"self_observed_at": True},
    {"schema": True},
    {"kind": "production_host_verified"},
    {"scope": "can_execute_untrusted_code"},
    {"secret": "unexpected"},
])
def test_even_validly_signed_privileged_alignment_is_rejected(
        aligned_case, change):
    archive, args, signer, statement, _ = aligned_case
    with pytest.raises(Stage39Refused):
        verify_offline_runtime_alignment(archive, **{
            **args, "signed_alignment":
                make_signature(signer, {**statement, **change})})


def test_wrong_fourth_signer_or_same_as_earlier_role_rejected(aligned_case):
    archive, args, _signer, statement, _ = aligned_case
    stranger = Ed25519PrivateKey.generate()
    with pytest.raises(Stage39Refused, match="SIGNATURE"):
        verify_offline_runtime_alignment(archive, **{
            **args, "signed_alignment":make_signature(stranger, statement)})
    for role in ("reviewer_public_key", "auditor_public_key"):
        prior = args["stage37_options"]["stage36_verification"][role]
        with pytest.raises(Stage39Refused, match="SIGNER_ROLES"):
            verify_offline_runtime_alignment(archive, **{
                **args, "witness_public_key": prior,
                "witness_public_key_sha256": hashlib.sha256(prior).hexdigest(),
            })
    prior = args["stage37_options"]["reviewer_public_key"]
    with pytest.raises(Stage39Refused, match="SIGNER_ROLES"):
        verify_offline_runtime_alignment(archive, **{
            **args, "witness_public_key": prior,
            "witness_public_key_sha256": hashlib.sha256(prior).hexdigest(),
        })


def test_duplicate_key_malformed_json_and_forged_challenge(aligned_case):
    archive, args, _, _, _ = aligned_case
    for raw in (
        args["stage38_self_report"]+b" ",
        b'{"host_alias":"x","host_alias":"y"}',
        b"[]", b"\xff",
    ):
        with pytest.raises(Stage39Refused):
            verify_offline_runtime_alignment(archive, **{
                **args, "stage38_self_report": raw})
    for raw in (
        args["signed_alignment"]+b" ",
        b'{"review":{}, "review":{}, "signature_b64":"x"}',
        b"\xff", b"[]" , b"x"*4097,
    ):
        with pytest.raises(Stage39Refused):
            verify_offline_runtime_alignment(archive, **{
                **args, "signed_alignment": raw})
    with pytest.raises(Stage39Refused):
        verify_offline_runtime_alignment(archive, **{
            **args,"expected_challenge":"f"*32})


def test_strong_stage35_anchor_and_rejected_stage37_snapshot(aligned_case):
    archive, args, _signer, _statement, _ = aligned_case
    prior = args["stage37_options"]
    for edits in (
        {"stage36_verification": {
            **prior["stage36_verification"],
            "pinned_stage35_sha256": "0"*64}},
        {"runtime_snapshot": canonical({"runtime": "host"})},
        {"firewall_snapshot": canonical({"nftables":[]})},
    ):
        with pytest.raises(Stage39Refused,match="REJECTED_STAGE37"):
            verify_offline_runtime_alignment(archive, **{
                **args, "stage37_options": {**prior, **edits}})


def test_never_runs_stage38_sampler_or_changes_host(aligned_case, monkeypatch):
    import naseri_markets.passive_kernel_posture_stage38_v1 as host
    monkeypatch.setattr(
        host, "observe_authorized_process_kernel_posture",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("host probe must not run from stage39")))
    archive, args, *_ = aligned_case
    assert not verify_offline_runtime_alignment(
        archive, **args).public_deployment_authorized


def test_missing_operator_ack_and_production_flag_rejected(aligned_case, monkeypatch):
    archive, args, *_ = aligned_case
    with pytest.raises(Stage39Refused,match="NONPRODUCTION"):
        verify_offline_runtime_alignment(archive, **{
            **args,"operator_ack":False})
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(Stage39Refused,match="NONPRODUCTION"):
        verify_offline_runtime_alignment(archive, **args)
