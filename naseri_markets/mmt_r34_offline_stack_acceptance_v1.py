"""R34 deterministic OFFLINE acceptance evidence for R27..R33 stacked drafts.

A local test PASS is only a reproducible claim bound to a Git checkout; it
does not attest provenance, merge approval, live account safety, genuine
prospective market observations or release readiness. NEVER authorizes LIVE.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime

_STAGE_PR = {
    "R27": (320, "9864a5165114654e25e8aa0ce83b27b7a268c6cc"),
    "R28": (321, "03a878b7c7f0d5955427efb2f32e3f5611afc919"),
    "R29": (322, "6031385a463adb9f544dc9250c158b23fdd2a087"),
    "R30": (323, "19f93e500ef4bc6e1854bb1efd02adebfebb4c22"),
    "R31": (324, "9658949fa2bb8d22c6ca6012e9af1bc45e6b460c"),
    "R32": (325, "f857dc66d91bffee022715fa1a00f0f5ba662f3e"),
    "R33": (326, "4a22bf0be13d64f81aa7a636bf90ca5cc6ec2e0c"),
}
_EXPECTED_STAGE_KEYS = tuple(_STAGE_PR)
_STAGE_UNIT_TARGETS = {
    "R27": "tests/unit/test_mmt_r27_independent_brooks_lifecycle_economics_v1.py",
    "R28": "tests/unit/test_offline_runtime_supervisor_v1.py",
    "R29": "tests/unit/test_mmt_r29_real_source_shadow_paper_v1.py",
    "R30": "tests/unit/test_mmt_r30_offline_risk_order_preflight_v1.py",
    "R31": "tests/unit/test_mmt_r31_private_admin_console_v1.py",
    "R32": "tests/unit/test_mmt_r32_offline_review_kit_and_recovery_v1.py",
    "R33": "tests/unit/test_mmt_r33_live_hard_deny_readiness_v1.py",
}
_STATIC_SOURCES = (
    "naseri_markets/mmt_r28_unified_offline_runtime_v1.py",
    "naseri_markets/brooks_future_shadow_paper_mmt_r29_v1.py",
    "naseri_markets/mmt_r29_shadow_session_audit_v1.py",
    "naseri_markets/mmt_r30_offline_risk_order_preflight_v1.py",
    "naseri_markets/mmt_r31_private_admin_console_v1.py",
    "naseri_markets/mmt_r32_stopped_recovery_review_v1.py",
    "naseri_markets/mmt_r33_live_hard_deny_readiness_v1.py",
)
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_TERMINAL = frozenset({"PASS", "FAIL", "TIMEOUT", "UNAVAILABLE", "NOT_RUN"})


class R34AcceptanceRefused(ValueError):
    """Constant refusal; never expose private input or test stdout."""


def _wire(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, slots=True)
class R34ToolFinding:
    """Local process outcome, not an externally signed execution proof."""
    name: str
    status: str
    returncode: int | None
    output_sha256: str | None

    def __post_init__(self) -> None:
        valid_names = (
            "R27", "R28", "R29", "R30", "R31", "R32", "R33",
            "RUFF_R28_TO_R34", "FULL_UNIT_SUITE", "STATIC_SYNTAX",
        )
        if (type(self.name) is not str or self.name not in valid_names
                or type(self.status) is not str or self.status not in _TERMINAL
                or (self.returncode is not None
                    and (type(self.returncode) is not int
                         or not -128 <= self.returncode <= 255))
                or (self.output_sha256 is not None
                    and (type(self.output_sha256) is not str
                         or not _SHA64.fullmatch(self.output_sha256)))):
            raise R34AcceptanceRefused("R34_UNTRUSTED_TEST_RESULT")
        if (self.status == "PASS" and (
                self.returncode != 0 or self.output_sha256 is None)):
            raise R34AcceptanceRefused("R34_PASS_WITHOUT_SUCCESS_EXIT_AND_DIGEST")
        if self.status == "NOT_RUN" and (
                self.returncode is not None or self.output_sha256 is not None):
            raise R34AcceptanceRefused("R34_NOT_RUN_MUST_HAVE_NO_RESULTS")


@dataclass(frozen=True, slots=True)
class R34OfflineEvidence:
    pinned_checkout_head: str
    observed_checkout_head: str
    checkout_clean_pre_and_post: bool
    local_test_runner_executed: bool
    results: tuple[R34ToolFinding, ...]
    # The operator can enter claims but no code here authenticates them.
    independent_test_witness_attested: bool = False
    upstream_prs_reviewed_and_merged: bool = False
    r29_true_prospective_oos_accepted: bool = False
    venue_permission_verified: bool = False
    real_account_position_state_verified: bool = False
    real_production_rollback_rehearsed: bool = False

    def __post_init__(self) -> None:
        if (type(self.pinned_checkout_head) is not str
                or _SHA40.fullmatch(self.pinned_checkout_head) is None
                or type(self.observed_checkout_head) is not str
                or _SHA40.fullmatch(self.observed_checkout_head) is None
                or type(self.checkout_clean_pre_and_post) is not bool
                or type(self.local_test_runner_executed) is not bool
                or type(self.results) is not tuple
                or any(type(r) is not R34ToolFinding for r in self.results)
                or tuple(r.name for r in self.results) != (
                    *_EXPECTED_STAGE_KEYS, "RUFF_R28_TO_R34",
                    "FULL_UNIT_SUITE", "STATIC_SYNTAX",
                )):
            raise R34AcceptanceRefused("R34_EXACT_EVIDENCE_CONTRACT_REQUIRED")
        for name in (
            "independent_test_witness_attested",
            "upstream_prs_reviewed_and_merged",
            "r29_true_prospective_oos_accepted",
            "venue_permission_verified",
            "real_account_position_state_verified",
            "real_production_rollback_rehearsed",
        ):
            if type(getattr(self, name)) is not bool:
                raise R34AcceptanceRefused("R34_TYPED_ATTESTATIONS_REQUIRED")


def review_r34_local_stack_evidence(
    evidence: R34OfflineEvidence, *, operator_ack: bool = False,
) -> dict:
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or type(evidence) is not R34OfflineEvidence):
        raise R34AcceptanceRefused("R34_EXPLICIT_NONPRODUCTION_LOCAL_REVIEW")
    blocks = []
    if evidence.observed_checkout_head != evidence.pinned_checkout_head:
        blocks.append("R34_CHECKOUT_HEAD_NOT_PINNED")
    if not evidence.checkout_clean_pre_and_post:
        blocks.append("R34_CHECKOUT_NOT_CLEAN")
    if not evidence.local_test_runner_executed:
        blocks.append("R34_TEST_RUN_NOT_EXECUTED")
    statuses = {}
    for finding in evidence.results:
        statuses[finding.name] = finding.status
        if finding.status != "PASS":
            blocks.append("R34_" + finding.name + "_" + finding.status)
    for flag in (
        "independent_test_witness_attested",
        "upstream_prs_reviewed_and_merged",
        "r29_true_prospective_oos_accepted",
        "venue_permission_verified",
        "real_account_position_state_verified",
        "real_production_rollback_rehearsed",
    ):
        if not getattr(evidence, flag):
            blocks.append("R34_" + flag.upper() + "_UNVERIFIED")
    # A local runner can never supply an independently trusted proof of
    # account/broker reality. Do not create any promotion or LIVE grant here.
    blocks.append("R34_LOCAL_EVIDENCE_NOT_INDEPENDENT_RELEASE_AUTHORITY")
    result = {
        "protocol": "MMT_R34_OFFLINE_STACK_ACCEPTANCE_REVIEW_V1",
        "decision": "REVIEW_ONLY_RELEASE_BLOCKED",
        "pinned_checkout_head": evidence.pinned_checkout_head,
        "observed_checkout_head": evidence.observed_checkout_head,
        "local_tests_claimed_executed": evidence.local_test_runner_executed,
        "stage_test_statuses": statuses,
        "blockers": blocks,
        "blocker_count": len(blocks),
        "original_prospective_r29_sample_verified": False,
        "independent_test_witness_authenticated_by_this_module": False,
        "github_review_or_merge_performed": False,
        "live_orders_authorized": False,
        "connected_paper_authorized": False,
        "telegram_send_authorized": False,
        "order_unknown_auto_retry_authorized": False,
        "server_deployment_authorized": False,
        "production_modified": False,
    }
    result["review_sha256"] = _sha(_wire(result))
    return result


def pending_r34_stage_tests() -> tuple[R34ToolFinding, ...]:
    return tuple(
        R34ToolFinding(stage, "NOT_RUN", None, None)
        for stage in _EXPECTED_STAGE_KEYS
    ) + tuple(
        R34ToolFinding(key, "NOT_RUN", None, None)
        for key in ("RUFF_R28_TO_R34", "FULL_UNIT_SUITE", "STATIC_SYNTAX")
    )


def known_upstream_pr_snapshots() -> dict[str, dict[str, object]]:
    """Dated initial observations, NOT a live GitHub provider lookup."""
    return {
        stage: {
            "pr": number, "pinned_observed_2026_10_16_sha": sha,
            "status_as_of_2026_10_16": "OPEN_DRAFT_UNMERGED",
        } for stage, (number, sha) in _STAGE_PR.items()
    }


__all__ = [
    "R34AcceptanceRefused", "R34ToolFinding", "R34OfflineEvidence",
    "review_r34_local_stack_evidence", "pending_r34_stage_tests",
    "known_upstream_pr_snapshots",
]
