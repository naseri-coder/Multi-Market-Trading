"""Stage40: independently revalidated host-security readiness BLOCKER matrix.

A signed report, a TLS *self*-observation and a restrictive declared OCI
template are not independently authenticated live host measurements.
This module does not access hosts, read process files, run commands or
authorize installation, orders, public endpoints or plugin execution.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from .a24_publisher_admission import canonical
from .disconnected_host_evidence_stage33_v1 import host_assessment_checklist
from .disposable_host_preflight_stage32_v1 import _guard
from .offline_runtime_alignment_stage39_v1 import (
    Stage39Refused, verify_offline_runtime_alignment,
)
from .portable_evidence_verifier_stage36_v1 import _packed
from .self_observation_evidence_chain_stage35_v1 import _canonical_json

# Each check requires independent evidence from an approved isolated
# disposable host. Synthetic and signed declarations never close a check.
_HELP = {
    "designated_disposable_host_custody": "INDEPENDENT_DESIGNATION_AND_HOST_IDENTITY",
    "os_and_runtime_provenance": "TRUSTED_OS_BOOT_AND_RUNTIME_PROVENANCE",
    "tls13_real_endpoint_handshake": "INDEPENDENT_REAL_ENDPOINT_TLS13_TEST",
    "certificate_chain_hostname_expiry": "LIVE_CERTIFICATE_CHAIN_HOSTNAME_EXPIRY_TEST",
    "private_key_and_secret_permissions": "TRUSTED_HOST_KEY_AND_SECRET_CUSTODY_REVIEW",
    "firewall_loopback_only_ingress": "LIVE_FIREWALL_AND_NAMESPACE_INGRESS_TEST",
    "outbound_network_deny": "LIVE_EGRESS_DENIAL_MEASUREMENT",
    "proxy_client_identity_boundary": "LIVE_PROXY_CLIENT_IP_AND_HEADER_TRUST_TEST",
    "no_broker_or_telegram_credentials": "INDEPENDENT_HOST_CREDENTIALS_ABSENCE_REVIEW",
    "gvisor_runtime_and_cgroup_isolation": "ACTUAL_RUNSC_CGROUP_AND_NAMESPACE_ATTESTATION",
    "hostile_source_escape_negative_tests": "AUTHORIZED_DISPOSABLE_HOST_ADVERSARIAL_TEST",
    "log_redaction_and_evidence_integrity": "INDEPENDENT_LOG_REDACTION_EVIDENCE_CUSTODY",
}
assert set(_HELP) == set(host_assessment_checklist())


class Stage40Refused(ValueError):
    """Never disclose signed documents or untrusted host-snapshot bytes."""


@dataclass(frozen=True, slots=True)
class HostGateCheck:
    id: str
    declared_status: str
    signed_evidence_sha256: str | None
    provenance: str
    supporting_lab_artifact: str
    remaining_requirement: str
    independently_verified: bool = False
    release_gate_satisfied: bool = False


@dataclass(frozen=True, slots=True)
class OfflineHostReadiness:
    host_alias: str
    nodename: str
    stage35_checkpoint_sha256: str
    stage39_signed_alignment_sha256: str
    checks: tuple[HostGateCheck, ...]
    declared_pass_count: int
    declared_fail_count: int
    declared_not_run_count: int
    unresolved_independent_host_checks: int = 12
    state: str = "FULL_OFFLINE_CRYPTO_CHAIN_VALIDATED_HOST_NOT_ATTESTED"
    real_host_test_completed: bool = False
    full_network_security_verified: bool = False
    gvisor_hostile_code_containment_verified: bool = False
    public_api_deployment_authorized: bool = False
    public_core_install_authorized: bool = False
    third_party_source_execution_authorized: bool = False
    telegram_signals_authorized: bool = False
    broker_orders_authorized: bool = False

    def sanitized_json(self) -> bytes:
        """Canonical report with NO private keys, bundle, or personal data."""
        return canonical(asdict(self))

    def report_sha256(self) -> str:
        return hashlib.sha256(self.sanitized_json()).hexdigest()


# This mapping conveys a *limited self-reporting or reviewed-template scope*.
# It is explicitly NOT "independently verified", even when the claim passes.
_ARTIFACT_SCOPE = {
    "tls13_real_endpoint_handshake":
        "STAGE34_REPORTED_LOOPBACK_TEST_NOT_REMOTE_TLS",
    "certificate_chain_hostname_expiry":
        "STAGE32_TEST_CERT_AND_STAGE34_SELF_REPORT_ONLY",
    "firewall_loopback_only_ingress":
        "STAGE37_DECLARED_NFTABLES_TEMPLATE_NOT_ACTIVE_RULESET",
    "outbound_network_deny":
        "STAGE37_DECLARED_NO_NETWORK_NOT_MEASURED_EGRESS",
    "gvisor_runtime_and_cgroup_isolation":
        "STAGE37_DECLARED_RUNSC_AND_STAGE38_SELF_PROCESS_NOT_CONTAINER",
    "os_and_runtime_provenance":
        "STAGE38_SELF_PROCESS_HASHES_WITHOUT_PROVENANCE",
}


def assess_offline_host_readiness(
    bundle: bytes, *, stage39_options: dict,
    operator_ack: bool = False,
) -> OfflineHostReadiness:
    """Re-run *all* prior crypto, pins, signed checks and static posture gates.

    All Stage39 options (including independent key pins, challenge and time)
    must be supplied from a trusted operator context, never the evidence
    bundle. Stage33's declared PASS remains an unverified claim.
    """
    try:
        _guard(operator_ack)
    except ValueError as exc:
        raise Stage40Refused("EXPLICIT_NONPRODUCTION_SECURITY_REVIEW_REQUIRED") from exc
    if (type(stage39_options) is not dict
            or stage39_options.get("operator_ack") is not True):
        raise Stage40Refused("EXACT_OPERATOR_PINNED_STAGE39_OPTIONS_REQUIRED")
    try:
        valid = verify_offline_runtime_alignment(bundle, **stage39_options)
        archive = _canonical_json(bundle, limit=38000)
        raw33 = _packed(archive["stage33_signed_b64"], max_bytes=12000)
        stage33 = _canonical_json(raw33, limit=12000)
        entries = stage33["report"]["checks"]
        if (type(entries) is not dict
                or set(entries) != set(host_assessment_checklist())):
            raise Stage40Refused("EXACT_TWELVE_SIGNED_HOST_CHECKS_REQUIRED")
        checks = []
        for name in host_assessment_checklist():
            item = entries[name]
            # Stage36 signature+schema already rechecked by Stage39, never
            # reinterpret these as genuine host observations.
            declaration = item["status"]
            if declaration == "NOT_RUN":
                provenance = "NOT_RUN_NO_INDEPENDENT_MEASUREMENT"
            elif declaration == "DECLARED_FAIL":
                provenance = "SIGNED_REVIEWER_REPORTED_FAILURE_ONLY"
            elif declaration == "DECLARED_PASS":
                provenance = "SIGNED_REVIEWER_CLAIM_ONLY"
            else:
                raise Stage40Refused("UNRECOGNIZED_SIGNED_EVIDENCE_STATUS")
            checks.append(HostGateCheck(
                name, declaration, item["evidence_sha256"], provenance,
                _ARTIFACT_SCOPE.get(name, "NO_LIVE_HOST_EVIDENCE_PRESENT"),
                _HELP[name],
            ))
    except Stage40Refused:
        raise
    except (Stage39Refused, TypeError, ValueError, KeyError,
            AttributeError) as exc:
        raise Stage40Refused("INVALID_OFFLINE_CHAIN_OR_HOST_STATUS") from exc
    statuses = [check.declared_status for check in checks]
    return OfflineHostReadiness(
        valid.host_alias, valid.nodename, valid.stage35_binding_sha256,
        valid.signed_alignment_sha256, tuple(checks),
        statuses.count("DECLARED_PASS"),
        statuses.count("DECLARED_FAIL"),
        statuses.count("NOT_RUN"),
    )


__all__ = [
    "Stage40Refused", "HostGateCheck", "OfflineHostReadiness",
    "assess_offline_host_readiness",
]
