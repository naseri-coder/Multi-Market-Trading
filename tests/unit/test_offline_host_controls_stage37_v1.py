"""Stage37 offline static security-config review and cryptographic pins.

All nftables and OCI review snapshots in these tests are SYNTHETIC.
Not a live firewall probe, gVisor escape test or public host acceptance.
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.offline_host_controls_stage37_v1 import (
    Stage37Refused, _DOMAIN, review_nftables_static_snapshot,
    review_gvisor_static_snapshot, verify_offline_host_controls,
)
from test_portable_evidence_verifier_stage36_v1 import exported  # noqa: F401
from test_self_observation_evidence_chain_stage35_v1 import (  # noqa: F401
    chain, signed_binding,
)
from test_disconnected_host_evidence_stage33_v1 import (  # noqa: F401
    prepared, research_only,
)
from test_disposable_host_preflight_stage32_v1 import (  # noqa: F401
    fixture_and_policy, dossier,
)
from test_tls_boundary_stage31_v1 import tls_material  # noqa: F401

HOST = "disposable_staging_one"


def chain_entry(name: str) -> dict:
    return {
        "chain": {
            "family": "inet", "table": "mmt_disposable",
            "name": name, "type": "filter", "hook": name,
            "prio": 0, "policy": "drop",
        },
    }


def accept_loopback(name: str) -> dict:
    return {"rule": {
        "family": "inet", "table": "mmt_disposable", "chain": name,
        "expr": [
            {"match": {
                "left": {"meta": {
                    "key": "iifname" if name == "input" else "oifname",
                }}, "op": "==", "right": "lo",
            }},
            {"accept": None},
        ],
    }}


def nft_config() -> dict:
    return {"nftables": [
        {"metainfo": {"version": "1.0.9"}},
        {"table": {"family": "inet", "name": "mmt_disposable"}},
        chain_entry("input"), chain_entry("output"), chain_entry("forward"),
        accept_loopback("input"), accept_loopback("output"),
    ]}


def runtime_config() -> dict:
    return {
        "runtime": "runsc", "network_mode": "none",
        "rootfs_readonly": True, "privileged": False,
        "user": "65534:65534", "cap_add": [], "cap_drop": ["ALL"],
        "bind_mounts": [], "devices": [], "published_ports": {},
        "security_opt": ["no-new-privileges"], "pids_limit": 16,
        "memory_limit_bytes": 256 * 1024**2, "nano_cpus": 500_000_000,
        "ipc_mode": "private", "pid_mode": "",
        "cgroupns_mode": "private",
        "init_process_kind": "fixed_harmless_canary_no_user_code",
    }


@pytest.fixture
def prepared_controls(exported):  # noqa: F811
    worker, archive, stage36 = exported
    third_key = Ed25519PrivateKey.generate()
    third_pub = third_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    firewall = canonical(nft_config())
    runtime = canonical(runtime_config())
    now = stage36["now"]
    claim = {
        "schema": 1, "scope": "static_snapshot_review_only",
        "host_alias": HOST,
        "stage35_binding_sha256": stage36["pinned_stage35_sha256"],
        "firewall_snapshot_sha256": hashlib.sha256(firewall).hexdigest(),
        "runtime_snapshot_sha256": hashlib.sha256(runtime).hexdigest(),
        "challenge": "e"*32,
        "issued_at": now-30, "expires_at": now+120,
        "real_host_attested": False,
        "public_deployment_authorized": False,
        "plugin_execution_authorized": False,
        "telegram_send_authorized": False,
        "broker_order_authorized": False,
    }
    review = canonical({
        "review": claim,
        "signature_b64": base64.b64encode(
            third_key.sign(_DOMAIN+canonical(claim))).decode("ascii"),
    })
    kwargs = {
        "stage36_verification": stage36,
        "firewall_snapshot": firewall,
        "runtime_snapshot": runtime,
        "signed_review": review,
        "reviewer_public_key": third_pub,
        "reviewer_public_key_sha256": hashlib.sha256(third_pub).hexdigest(),
        "expected_host_alias": HOST, "expected_challenge": "e"*32,
        "now": now, "operator_ack": True,
    }
    return archive, kwargs, third_key


def signed_review(key, data):
    return canonical({
        "review": data,
        "signature_b64": base64.b64encode(
            key.sign(_DOMAIN+canonical(data))).decode("ascii"),
    })


def test_three_offline_control_review_is_never_real_host_acceptance(prepared_controls):
    archive, kwargs, _ = prepared_controls
    receipt = verify_offline_host_controls(archive, **kwargs)
    assert receipt.state == "STATIC_CONTROL_TEMPLATES_REVIEWED_NOT_HOST_ACCEPTED"
    assert receipt.accepted_drop_chains == 3
    assert receipt.stage35_binding_sha256 == kwargs[
        "stage36_verification"]["pinned_stage35_sha256"]
    for field in (
        "actual_host_independently_attested",
        "tls_endpoint_independently_verified",
        "firewall_actually_enforced", "runtime_gvisor_actually_verified",
        "hostile_code_containment_certified",
        "public_deployment_authorized",
        "third_party_core_execution_authorized",
        "telegram_signal_authorized", "broker_order_authorized",
    ):
        assert getattr(receipt, field) is False


@pytest.mark.parametrize("kind,alter", [
    ("chain", {"policy": "accept"}),
    ("chain", {"hook": "prerouting"}),
    ("chain", {"prio": True}),
    ("chain", {"name": "outside"}),
    ("rule", {"chain": "forward"}),
    ("rule", {"family": "ip"}),
    ("table", {"name": "unreviewed"}),
    ("table", {"family": "ip6"}),
])
def test_insecure_nft_chain_rule_or_table_refused(kind, alter):
    config = nft_config()
    for entry in config["nftables"]:
        if kind in entry:
            entry[kind].update(alter)
            break
    with pytest.raises(Stage37Refused):
        review_nftables_static_snapshot(canonical(config))


def test_missing_lo_accept_additional_nat_or_wildcard_rules_refused():
    for change in (
        lambda c: c["nftables"].pop(),
        lambda c: c["nftables"].append({
            "table": {"family": "ip", "name": "nat"}}),
        lambda c: c["nftables"].append(
            {"rule": {"family": "inet", "table": "mmt_disposable",
                      "chain": "input", "expr": [{"accept": None}]}}),
        lambda c: c["nftables"].append(chain_entry("output")),
        lambda c: c["nftables"].append({
            "chain": {"family": "inet", "table": "mmt_disposable",
                      "name": "new", "type": "filter", "hook": "input",
                      "prio": 0, "policy": "accept"}}),
    ):
        c = nft_config()
        change(c)
        with pytest.raises(Stage37Refused):
            review_nftables_static_snapshot(canonical(c))


@pytest.mark.parametrize("mutation", [
    {"runtime": "runc"}, {"network_mode": "host"},
    {"rootfs_readonly": False}, {"privileged": True},
    {"user": "0:0"}, {"cap_add": ["SYS_ADMIN"]},
    {"cap_drop": []}, {"bind_mounts": ["/var/run/docker.sock:/sock"]},
    {"devices": ["dev/null"]}, {"published_ports": {"80":"80"}},
    {"security_opt": []}, {"pids_limit": 512},
    {"pids_limit": True}, {"memory_limit_bytes": 1024**3},
    {"nano_cpus": True}, {"ipc_mode": "host"},
    {"pid_mode": "host"}, {"cgroupns_mode": "host"},
    {"init_process_kind": "arbitrary_uploaded_user_python"},
    {"extra": "backdoor"},
])
def test_gvisor_normalized_snapshot_rejects_risky_parameters(mutation):
    config = {**runtime_config(), **mutation}
    with pytest.raises(Stage37Refused, match="NONCONFORMING"):
        review_gvisor_static_snapshot(canonical(config))


def test_reviewer_identity_digest_nonce_time_and_host_are_independent(prepared_controls):
    archive, kwargs, _ = prepared_controls
    wrong = Ed25519PrivateKey.generate()
    outsider_pub = wrong.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    for change in (
        {"reviewer_public_key": outsider_pub,
         "reviewer_public_key_sha256": hashlib.sha256(outsider_pub).hexdigest()},
        {"reviewer_public_key_sha256": "0"*64},
        {"expected_challenge": "a"*32},
        {"expected_host_alias": "different_host"},
        {"now": kwargs["now"]+10},
        {"operator_ack": False},
    ):
        with pytest.raises(Stage37Refused):
            verify_offline_host_controls(archive, **{**kwargs, **change})


@pytest.mark.parametrize("field,value", [
    ("scope", "host_attested"),
    ("real_host_attested", True),
    ("public_deployment_authorized", True),
    ("plugin_execution_authorized", True),
    ("telegram_send_authorized", True),
    ("broker_order_authorized", True),
    ("host_alias", "foreign"),
    ("stage35_binding_sha256", "0"*64),
    ("firewall_snapshot_sha256", "0"*64),
    ("runtime_snapshot_sha256", "0"*64),
    ("issued_at", True),
    ("expires_at", 2**63),
    ("schema", True),
    ("extra", True),
])
def test_even_validly_signed_privilege_escalation_is_rejected(
        prepared_controls, field, value):
    archive, kwargs, third_key = prepared_controls
    data = json.loads(kwargs["signed_review"])["review"]
    data[field] = value
    with pytest.raises(Stage37Refused):
        verify_offline_host_controls(
            archive, **{**kwargs,"signed_review":signed_review(third_key,data)})


def test_mismatched_snapshot_digest_and_ambiguous_json_denied(prepared_controls):
    archive, kwargs, _ = prepared_controls
    for field, new in (
        ("firewall_snapshot", canonical({**nft_config(), "extra": 1})),
        ("runtime_snapshot", canonical({**runtime_config(), "extra": 1})),
        ("signed_review", kwargs["signed_review"]+b"\n"),
        ("signed_review", b'{"review":{}, "review":{}}'),
    ):
        with pytest.raises(Stage37Refused):
            verify_offline_host_controls(archive, **{**kwargs, field:new})


def test_prior_staged_signature_anchor_forgery_blocks_even_static_review(prepared_controls):
    archive, kwargs, _ = prepared_controls
    for patch in (
        {"pinned_stage35_sha256": "a"*64},
        {"pinned_stage35_sequence": 999},
        {"reviewer_key_sha256": "0"*64},
    ):
        with pytest.raises(Stage37Refused, match="INVALID_PRIOR"):
            verify_offline_host_controls(archive, **{
                **kwargs, "stage36_verification": {
                    **kwargs["stage36_verification"], **patch}})
