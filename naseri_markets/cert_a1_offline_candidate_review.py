"""CERT-A1: consolidated NONPRODUCTION artifact evidence review, never admission.

This is an audit of pinned bytes, existing structural contracts and
operator-supplied *claims*. None of these claims attest an external host,
publisher identity, broker data source, TradingView or a MetaTrader terminal.
No user code or binary is imported, compiled, loaded, installed or executed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .core_certification_v1 import CertificationReport
from .data_a1_file_intake import HistoricalIntakeReport
from .data_runtime_paper_wire_a1 import PaperWireReview
from .mt_a1_offline_artifact_preflight import MetaTraderArtifactReview
from .native_a1_inert_binary_preflight import (
    NativeA1Refused,
    inspect_native_bytes,
)
from .pine_a1_sma_cross_parity import (
    PineA1Refused,
    PineTraceReview,
    parse_pine_sma_cross,
)
from .runtime_a13_security_contract_audit import (
    A13AuditRefused,
    audit_repository,
)
from .universal_artifact_intake_v1 import IntakeRefused, inspect_artifact

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DOMAIN = b"MMT-CERT-A1-INERT-REVIEW-V1\x00"
_KIND = {
    ".py": PaperWireReview,
    ".js": PaperWireReview,
    ".ts": PaperWireReview,
    ".wasm": PaperWireReview,
    ".csv": HistoricalIntakeReport,
    ".parquet": HistoricalIntakeReport,
    ".mq4": MetaTraderArtifactReview,
    ".mq5": MetaTraderArtifactReview,
    ".ex5": MetaTraderArtifactReview,
    ".pine": PineTraceReview,
    ".dll": None,  # Independently parsed again by native A1 below.
    ".exe": None,
    ".so": None,
    ".zip": CertificationReport,
    ".json": None,
}
_LANGUAGE = {".py": "python", ".js": "javascript",
             ".ts": "typescript", ".wasm": "wasm"}
_MT = {".mq4": ("MT4", "MQL4_SOURCE"),
       ".mq5": ("MT5", "MQL5_SOURCE"),
       ".ex5": ("MT5", "EX5_OPAQUE_BINARY")}
_EXTERNAL = (
    "CUSTODIED_INDEPENDENT_SOURCE_PROVENANCE_REQUIRED",
    "INDEPENDENT_OPERATOR_AND_SIGNER_IDENTITY_REQUIRED",
    "ACTUAL_SANDBOX_AND_NATIVE_HOST_ATTESTATION_REQUIRED",
    "REPRODUCIBLE_DEPENDENCY_AND_IMAGE_PROVENANCE_REQUIRED",
    "LATEST_CHECKPOINT_AND_TRUSTED_MONOTONIC_TIME_REQUIRED",
    "A6_UNCONDITIONAL_WORKER_EXECUTION_DENIAL_REMAINS",
)


class CertA1Refused(ValueError):
    """Review cannot proceed; errors must not include user artifact content."""


@dataclass(frozen=True, slots=True)
class CertA1Report:
    artifact_name: str
    artifact_sha256: str
    artifact_type: str
    byte_length: int
    inspection_level: str
    claim_class: str
    claim_reconciled: bool
    source_contract_files_audited: int
    review_fingerprint_sha256: str
    blockers: tuple[str, ...] = _EXTERNAL
    status: str = "CERT_A1_OFFLINE_REVIEW_ONLY_EXECUTION_BLOCKED"
    source_provenance_independently_authenticated: bool = False
    review_claim_independently_authenticated: bool = False
    hosted_runtime_isolation_certified: bool = False
    actual_tradingview_equivalence_proven: bool = False
    binary_safe_from_malware: bool = False
    native_execution_authorized: bool = False
    worker_execution_authorized: bool = False
    paper_strategy_executed: bool = False
    paper_order_sent: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    distribution_authorized: bool = False
    quarantine_release_authorized: bool = False
    production_recovery_authorized: bool = False


def _scope(ack: bool) -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or ack is not True):
        raise CertA1Refused("CERT_A1_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")


def _false_fields(evidence: object, names: tuple[str, ...]) -> None:
    if any(getattr(evidence, name, None) is not False for name in names):
        raise CertA1Refused("CERT_A1_UNTRUSTED_CLAIM_GRANTS_AUTHORITY")


def _claim(
    extension: str, evidence: object | None, sha: str,
) -> tuple[str, bool]:
    """Match a provided review to bytes; this is never independent trust."""
    if evidence is None:
        return "NO_STAGE_REVIEW_PROVIDED", False
    if extension not in _KIND or _KIND[extension] is None:
        raise CertA1Refused("CERT_A1_UNEXPECTED_STAGE_CLAIM")
    if type(evidence) is not _KIND[extension]:
        raise CertA1Refused("CERT_A1_STAGE_CLAIM_TYPE_MISMATCH")
    if extension in _LANGUAGE:
        x = evidence
        if (x.artifact_sha256 != sha
                or x.language != _LANGUAGE[extension]
                or x.status != "DATA_RUNTIME_PAPER_WIRE_VALIDATED_NO_WORKER_EXECUTION"
                or type(x.frames_prepared) is not int or x.frames_prepared < 1
                or type(x.transcript_sha256) is not str
                or _SHA.fullmatch(x.transcript_sha256) is None):
            raise CertA1Refused("CERT_A1_WIRE_EVIDENCE_NOT_CONSISTENT")
        _false_fields(x, (
            "market_source_authenticated", "actual_point_in_time_proven",
            "independent_host_certified", "worker_executed",
            "paper_order_sent", "broker_order_sent", "telegram_sent",
            "worker_execution_authorized", "quarantine_release_authorized",
        ))
        return "DATA_RUNTIME_PAPER_WIRE_OPERATOR_CLAIM", True
    if extension in {".csv", ".parquet"}:
        x = evidence
        if (x.sha256 != sha or x.format != extension[1:]
                or x.status != "DATA_A1_FILE_VALIDATED_OFFLINE_PAPER_INPUT_ONLY"
                or type(x.rows_validated) is not int or x.rows_validated < 1
                or type(x.paper_core_inputs_validated) is not int
                or x.rows_validated != x.paper_core_inputs_validated):
            raise CertA1Refused("CERT_A1_HISTORICAL_CLAIM_INCONSISTENT")
        _false_fields(x, (
            "source_authenticated", "point_in_time_feed_certified",
            "exchange_calendar_verified", "paper_strategy_executed",
            "broker_order_sent", "telegram_sent", "worker_execution_authorized",
        ))
        return "DATA_A1_STRUCTURAL_PAPER_INPUT_OPERATOR_CLAIM", True
    if extension in _MT:
        x = evidence
        platform, artifact_type = _MT[extension]
        if (x.sha256 != sha or x.platform != platform
                or x.artifact_kind != artifact_type
                or x.status != "MT_A1_LOCAL_ARTIFACT_BYTES_REVIEWED_NO_TERMINAL_EXECUTION"):
            raise CertA1Refused("CERT_A1_MT_CLAIM_INCONSISTENT")
        _false_fields(x, (
            "mt_source_compiled", "ex5_format_verified",
            "broker_source_authenticated", "platform_account_verified",
            "real_terminal_connected", "market_data_observed",
            "point_in_time_verified", "paper_strategy_executed",
            "broker_order_sent", "telegram_sent",
            "worker_execution_authorized", "quarantine_release_authorized",
        ))
        return "MT_A1_OPERATOR_FILE_REVIEW_UNATTESTED", True
    if extension == ".pine":
        x = evidence
        if (x.source_sha256 != sha
                or x.status != "PINE_A1_OFFLINE_TRACE_MATCH_NOT_TV_ATTESTED"
                or x.offline_fixture_trace_matched is not True
                or type(x.bars_compared) is not int or x.bars_compared < 1
                or type(x.mismatch_bars) is not int or x.mismatch_bars != 0
                or x.first_mismatch_at is not None):
            raise CertA1Refused("CERT_A1_PINE_PARITY_CLAIM_INCONSISTENT")
        _false_fields(x, (
            "actual_tradingview_source_authenticated",
            "actual_tradingview_trace_authenticated",
            "true_pine_runtime_equivalence_proven", "market_source_authenticated",
            "point_in_time_proven", "paper_strategy_executed",
            "paper_order_sent", "broker_order_sent", "telegram_sent",
            "worker_execution_authorized", "quarantine_release_authorized",
        ))
        return "PINE_A1_OFFLINE_TRACE_OPERATOR_CLAIM", True
    if extension == ".zip":
        x = evidence
        if (x.artifact_sha256 != sha
                or x.status != "REVIEW_REQUIRED_NONPRODUCTION"):
            raise CertA1Refused("CERT_A1_SDK_CLAIM_INCONSISTENT")
        _false_fields(x, (
            "approved_for_public_distribution", "approved_for_execution",
            "approved_for_trading", "approved_for_telegram",
        ))
        return "STAGE14_SDK_CERTIFICATION_REVIEW_CLAIM", True
    raise CertA1Refused("CERT_A1_UNSUPPORTED_STAGE_REVIEW")


def review_candidate(
    root: Path, filename: str, artifact: bytes, *,
    expected_sha256: str, stage_evidence: object | None = None,
    operator_ack: bool = False,
) -> CertA1Report:
    """Cross-stage *review* of exact bytes. Never grants certification.

    A user can fabricate a dataclass that matches these fields, including
    a matching hash. No out-of-band custody, signature or real host is
    authenticated by this function, and its result MUST remain quarantined.
    """
    _scope(operator_ack)
    if (type(expected_sha256) is not str or
            _SHA.fullmatch(expected_sha256) is None
            or type(artifact) is not bytes):
        raise CertA1Refused("CERT_A1_EXACT_SOURCE_SHA256_REQUIRED")
    if hashlib.sha256(artifact).hexdigest() != expected_sha256:
        raise CertA1Refused("CERT_A1_SOURCE_SHA256_MISMATCH")
    try:
        audit = audit_repository(root)
    except A13AuditRefused as exc:
        raise CertA1Refused("CERT_A1_A6_SOURCE_CONTRACT_NOT_VERIFIED") from exc
    if (audit.worker_execution_authorized is not False
            or audit.quarantine_release_authorized is not False
            or audit.hard_stop_checks != 3):
        raise CertA1Refused("CERT_A1_A6_EXECUTION_DENIAL_REQUIRED")
    try:
        inspected = inspect_artifact(filename, artifact)
    except IntakeRefused as exc:
        raise CertA1Refused("CERT_A1_FORMAT_INTAKE_REFUSED") from exc
    ext = inspected.extension
    if ext not in _KIND:
        raise CertA1Refused("CERT_A1_EXTENSION_NOT_IN_CONTRACT")
    if (inspected.sha256 != expected_sha256
            or inspected.executable is not False
            or inspected.adapter_installed is not False
            or inspected.live_enabled is not False
            or inspected.paper_enabled is not False
            or inspected.telegram_enabled is not False):
        raise CertA1Refused("CERT_A1_INTAKE_AUTHORIZATION_DRIFT")
    if ext in {".dll", ".exe", ".so"}:
        try:
            native = inspect_native_bytes(
                filename, artifact, expected_sha256=expected_sha256,
                operator_ack=operator_ack,
            )
        except NativeA1Refused as exc:
            raise CertA1Refused("CERT_A1_NATIVE_STRUCTURE_REFUSED") from exc
        if (native.sha256 != expected_sha256
                or native.worker_execution_authorized is not False
                or native.quarantine_release_authorized is not False):
            raise CertA1Refused("CERT_A1_NATIVE_CLAIM_DRIFT")
        if stage_evidence is not None:
            raise CertA1Refused("CERT_A1_NATIVE_EXTERNAL_CLAIM_UNSUPPORTED")
        claim_class, reconciled = "NATIVE_A1_REPARSED_HEADER_BYTES_ONLY", True
    else:
        if ext == ".pine":
            # Reject arbitrary Pine even when V1 generic intake accepts
            # its UTF-8 bytes. The strict subset can be reviewed only.
            try:
                parse_pine_sma_cross(artifact, expected_sha256=expected_sha256)
            except PineA1Refused as exc:
                raise CertA1Refused("CERT_A1_PINE_STRICT_SUBSET_REQUIRED") from exc
        claim_class, reconciled = _claim(ext, stage_evidence, expected_sha256)
    label = "STAGE_EVIDENCE_MATCHED_BUT_UNATTESTED" if reconciled else "STAGE_EVIDENCE_MISSING"
    fingerprint = hashlib.sha256(
        _DOMAIN + json.dumps({
            "name": filename, "sha256": expected_sha256,
            "type": ext, "stage": claim_class,
            "status": label, "a13_files": audit.audited_files,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"),
    ).hexdigest()
    return CertA1Report(
        artifact_name=filename,
        artifact_sha256=expected_sha256,
        artifact_type=ext, byte_length=len(artifact),
        inspection_level=inspected.inspection_level.value,
        claim_class=claim_class, claim_reconciled=reconciled,
        source_contract_files_audited=audit.audited_files,
        review_fingerprint_sha256=fingerprint,
        blockers=_EXTERNAL + (label,),
    )


__all__ = ["CertA1Refused", "CertA1Report", "review_candidate"]
