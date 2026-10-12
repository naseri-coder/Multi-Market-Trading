"""Stage40 signed-claims-versus-independent-host-evidence blocker assessment.

Tests reuse a FULL REAL-signature Stage32–39 synthetic chain. No real host
is probed; passing static policy proofs are not public installation grants.
"""
from __future__ import annotations

import hashlib
import json

import pytest

pytest.importorskip("cryptography")

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.disconnected_host_evidence_stage33_v1 import (
    host_assessment_checklist,
)
from naseri_markets.offline_host_readiness_stage40_v1 import (
    OfflineHostReadiness, Stage40Refused, assess_offline_host_readiness,
)
from test_offline_runtime_alignment_stage39_v1 import (
    aligned_case,  # noqa: F401
)
from test_offline_host_controls_stage37_v1 import (  # noqa: F401
    prepared_controls,
)
from test_portable_evidence_verifier_stage36_v1 import exported  # noqa: F401
from test_self_observation_evidence_chain_stage35_v1 import (  # noqa: F401
    chain, signed_binding,
)
from test_disconnected_host_evidence_stage33_v1 import (  # noqa: F401
    prepared, research_only,
)
from test_disposable_host_preflight_stage32_v1 import (  # noqa: F401
    dossier, fixture_and_policy,
)
from test_tls_boundary_stage31_v1 import tls_material  # noqa: F401


def test_complete_crypto_chain_still_reports_twelve_real_host_blockers(
        aligned_case):  # noqa: F811
    bundle, args, _signer, _claim, _observation = aligned_case
    report = assess_offline_host_readiness(
        bundle, stage39_options=args, operator_ack=True)
    assert isinstance(report, OfflineHostReadiness)
    assert report.host_alias == "disposable_staging_one"
    assert report.nodename == "pinned-disposable-node"
    assert report.stage35_checkpoint_sha256 == args[
        "stage37_options"]["stage36_verification"]["pinned_stage35_sha256"]
    assert report.stage39_signed_alignment_sha256 == hashlib.sha256(
        args["signed_alignment"]).hexdigest()
    assert len(report.checks) == 12
    assert tuple(c.id for c in report.checks) == host_assessment_checklist()
    assert report.declared_pass_count == 0
    assert report.declared_fail_count == 0
    assert report.declared_not_run_count == 12
    assert report.unresolved_independent_host_checks == 12
    assert all(c.provenance == "NOT_RUN_NO_INDEPENDENT_MEASUREMENT"
               for c in report.checks)
    assert all(c.signed_evidence_sha256 is None for c in report.checks)
    assert all(c.remaining_requirement and not c.independently_verified
               and not c.release_gate_satisfied for c in report.checks)
    for field in (
        "real_host_test_completed",
        "full_network_security_verified",
        "gvisor_hostile_code_containment_verified",
        "public_api_deployment_authorized", "public_core_install_authorized",
        "third_party_source_execution_authorized",
        "telegram_signals_authorized", "broker_orders_authorized",
    ):
        assert getattr(report, field) is False
    output = report.sanitized_json()
    assert report.report_sha256() == hashlib.sha256(output).hexdigest()
    assert b"PRIVATE KEY" not in output
    assert b"stage32_signed_b64" not in output
    assert b"signature_b64" not in output
    assert json.loads(output)["state"] == (
        "FULL_OFFLINE_CRYPTO_CHAIN_VALIDATED_HOST_NOT_ATTESTED")


@pytest.mark.parametrize("security_area,expected_scope", [
    ("tls13_real_endpoint_handshake", "STAGE34_REPORTED_LOOPBACK_TEST"),
    ("firewall_loopback_only_ingress", "STAGE37_DECLARED_NFTABLES"),
    ("outbound_network_deny", "STAGE37_DECLARED_NO_NETWORK"),
    ("gvisor_runtime_and_cgroup_isolation", "STAGE37_DECLARED_RUNSC"),
    ("os_and_runtime_provenance", "STAGE38_SELF_PROCESS"),
])
def test_static_self_observations_never_promoted_to_host_verification(
        aligned_case, security_area, expected_scope):  # noqa: F811
    bundle, options, *_ = aligned_case
    report = assess_offline_host_readiness(
        bundle, stage39_options=options, operator_ack=True)
    check = next(c for c in report.checks if c.id == security_area)
    assert check.supporting_lab_artifact.startswith(expected_scope)
    assert not check.independently_verified


@pytest.mark.parametrize("alter", [
    {"expected_challenge": "1"*32},
    {"expected_nodename": "rogue-host"},
    {"witness_public_key_sha256": "0"*64},
    {"now": True},
    {"now": 1},
    {"operator_ack": False},
    {"stage38_self_report": b"{}"},
    {"signed_alignment": b"{}"},
])
def test_stage39_cryptographic_provenance_required_before_status(
        aligned_case, alter):  # noqa: F811
    bundle, options, *_ = aligned_case
    with pytest.raises(Stage40Refused):
        assess_offline_host_readiness(
            bundle, stage39_options={**options, **alter},
            operator_ack=True)


def test_stage36_independent_latest_checkpoint_must_match(aligned_case):  # noqa: F811
    bundle, opts, *_ = aligned_case
    broken = {**opts, "stage37_options": {
        **opts["stage37_options"],
        "stage36_verification": {
            **opts["stage37_options"]["stage36_verification"],
            "pinned_stage35_sha256": "f"*64}}}
    with pytest.raises(Stage40Refused):
        assess_offline_host_readiness(
            bundle, stage39_options=broken, operator_ack=True)


def test_forged_stage33_declared_pass_flags_cannot_bypass_signatures(
        aligned_case):  # noqa: F811
    bundle, opts, *_ = aligned_case
    doc = json.loads(bundle)
    import base64
    field = "stage33_signed_b64"
    raw = json.loads(base64.b64decode(doc[field]))
    for check in raw["report"]["checks"].values():
        check["status"] = "DECLARED_PASS"
        check["evidence_sha256"] = "a"*64
    doc[field] = base64.b64encode(canonical(raw)).decode("ascii")
    with pytest.raises(Stage40Refused):
        assess_offline_host_readiness(
            canonical(doc), stage39_options=opts, operator_ack=True)


def test_public_production_env_and_missing_operator_ack_denied(
        aligned_case, monkeypatch):  # noqa: F811
    bundle, args, *_ = aligned_case
    with pytest.raises(Stage40Refused, match="NONPRODUCTION"):
        assess_offline_host_readiness(
            bundle, stage39_options=args, operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage40Refused, match="NONPRODUCTION"):
        assess_offline_host_readiness(
            bundle, stage39_options=args, operator_ack=True)
