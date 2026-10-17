"""CERT-A1 cross-format PAPER *capability inventory*, NO execution certification.

Review the submitted bytes again through existing CERT-A1 and preserve the
distinction between data input, wire preparation, static format review and
actual PAPER strategy execution (which remains forbidden for all formats).

This file neither trusts caller-created dataclasses nor opens a Worker,
broker, database, TradingView, native loader or MetaTrader terminal.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .cert_a1_offline_candidate_review import (
    CertA1Refused,
    CertA1Report,
    review_candidate,
)
from .universal_artifact_intake_v1 import supported_extensions

_DOMAIN = b"MMT-CERT-A1-PAPER-CAPABILITY-INVENTORY-V1\x00"
_CAPABILITIES = {
    ".csv": "PAPER_DATA_CORE_INPUT_CLAIM_ONLY",
    ".parquet": "PAPER_DATA_CORE_INPUT_CLAIM_ONLY",
    ".py": "PAPER_WIRE_FRAMES_CLAIM_ONLY",
    ".js": "PAPER_WIRE_FRAMES_CLAIM_ONLY",
    ".ts": "PAPER_WIRE_FRAMES_CLAIM_ONLY",
    ".wasm": "PAPER_WIRE_FRAMES_CLAIM_ONLY",
    ".pine": "STATIC_RULE_AND_ORACLE_CLAIM_ONLY",
    ".mq4": "METATRADER_ARTIFACT_IDENTITY_CLAIM_ONLY",
    ".mq5": "METATRADER_ARTIFACT_IDENTITY_CLAIM_ONLY",
    ".ex5": "METATRADER_OPAQUE_ARTIFACT_CLAIM_ONLY",
    ".dll": "NATIVE_HEADER_REPARSED_NO_NATIVE_LOAD",
    ".exe": "NATIVE_HEADER_REPARSED_NO_NATIVE_LOAD",
    ".so": "NATIVE_HEADER_REPARSED_NO_NATIVE_LOAD",
    ".zip": "SDK_PACKAGE_STRUCTURE_CLAIM_ONLY",
    ".json": "DECLARATION_STRUCTURE_ONLY",
}
_REQUIRED_FALSE = (
    "source_provenance_independently_authenticated",
    "review_claim_independently_authenticated",
    "hosted_runtime_isolation_certified",
    "actual_tradingview_equivalence_proven",
    "binary_safe_from_malware",
    "native_execution_authorized",
    "worker_execution_authorized",
    "paper_strategy_executed",
    "paper_order_sent",
    "broker_authorized",
    "telegram_authorized",
    "distribution_authorized",
    "quarantine_release_authorized",
    "production_recovery_authorized",
)


class CertA1InventoryRefused(ValueError):
    """Fail-closed stable response, never raw content in messages."""


@dataclass(frozen=True, slots=True)
class CandidateSubmission:
    filename: str
    artifact: bytes
    sha256: str
    stage_evidence: object | None = None


@dataclass(frozen=True, slots=True)
class FormatCoverage:
    extension: str
    artifact_sha256: str
    inspection_level: str
    paper_capability: str
    stage_claim_present: bool
    stage_claim_reconciled: bool
    stage_claim_authenticated: bool = False
    market_provenance_authenticated: bool = False
    paper_strategy_executed: bool = False
    native_or_worker_executed: bool = False
    broker_order_sent: bool = False
    telegram_sent: bool = False
    quarantine_release_authorized: bool = False


@dataclass(frozen=True, slots=True)
class CertA1InventoryReport:
    present: tuple[FormatCoverage, ...]
    missing_extensions: tuple[str, ...]
    submitted_format_count: int
    expected_format_count: int
    matching_unattested_stage_claims: int
    missing_stage_claims: int
    fingerprint_sha256: str
    status: str = "CERT_A1_PAPER_COVERAGE_INVENTORY_ONLY_ALL_EXECUTION_DENIED"
    independent_market_history_authenticated: bool = False
    independent_runtime_host_attested: bool = False
    independent_stage_receipts_authenticated: bool = False
    all_formats_paper_executable: bool = False
    paper_strategy_executed: bool = False
    paper_order_sent: bool = False
    native_execution_authorized: bool = False
    worker_execution_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    quarantine_release_authorized: bool = False
    production_release_authorized: bool = False


def _check_review(report: CertA1Report, suffix: str, digest: str) -> None:
    if (type(report) is not CertA1Report
            or report.artifact_type != suffix or report.artifact_sha256 != digest
            or report.status != "CERT_A1_OFFLINE_REVIEW_ONLY_EXECUTION_BLOCKED"
            or any(getattr(report, field) is not False for field in _REQUIRED_FALSE)
            or "A6_UNCONDITIONAL_WORKER_EXECUTION_DENIAL_REMAINS"
            not in report.blockers):
        raise CertA1InventoryRefused("CERT_A1_INVENTORY_REVIEW_AUTHORITY_DRIFT")


def review_paper_format_inventory(
    root: Path,
    candidates: tuple[CandidateSubmission, ...],
    *, operator_ack: bool = False, require_all_formats: bool = False,
) -> CertA1InventoryReport:
    """Re-examine each candidate under CERT-A1, never promote review to a grant.

    A complete *inventory* still cannot certify that any code runs safely;
    even an exact match is only a claim of PAPER inputs/wire frames.
    """
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or operator_ack is not True):
        raise CertA1InventoryRefused("CERT_A1_INVENTORY_NONPRODUCTION_ACK_REQUIRED")
    recognized = supported_extensions()
    if set(recognized) != set(_CAPABILITIES):
        raise CertA1InventoryRefused("CERT_A1_FORMAT_REGISTRY_DRIFT")
    if (type(candidates) is not tuple
            or not 1 <= len(candidates) <= len(recognized)
            or type(require_all_formats) is not bool):
        raise CertA1InventoryRefused("CERT_A1_BOUNDED_CANDIDATE_TUPLE_REQUIRED")

    names: set[str] = set()
    extensions: set[str] = set()
    digests: set[str] = set()
    rows: list[FormatCoverage] = []
    fingerprints: list[tuple[str, str]] = []

    for candidate in candidates:
        if (type(candidate) is not CandidateSubmission
                or type(candidate.filename) is not str
                or type(candidate.artifact) is not bytes
                or type(candidate.sha256) is not str):
            raise CertA1InventoryRefused("CERT_A1_EXACT_CANDIDATE_REQUIRED")
        basename = candidate.filename.casefold()
        suffix = Path(candidate.filename).suffix.lower()
        if (suffix not in _CAPABILITIES or basename in names
                or suffix in extensions or candidate.sha256 in digests):
            raise CertA1InventoryRefused("CERT_A1_AMBIGUOUS_OR_DUPLICATE_CANDIDATE")
        names.add(basename)
        extensions.add(suffix)
        digests.add(candidate.sha256)

        try:
            report = review_candidate(
                root, candidate.filename, candidate.artifact,
                expected_sha256=candidate.sha256,
                stage_evidence=candidate.stage_evidence,
                operator_ack=True,
            )
        except CertA1Refused as exc:
            raise CertA1InventoryRefused("CERT_A1_CANDIDATE_REVIEW_REFUSED") from exc

        _check_review(report, suffix, candidate.sha256)
        row = FormatCoverage(
            extension=suffix, artifact_sha256=candidate.sha256,
            inspection_level=report.inspection_level,
            paper_capability=_CAPABILITIES[suffix],
            stage_claim_present=candidate.stage_evidence is not None,
            stage_claim_reconciled=(
                candidate.stage_evidence is not None and report.claim_reconciled
            ),
        )
        rows.append(row)
        fingerprints.append((suffix, report.review_fingerprint_sha256))

    missing = tuple(sorted(set(recognized) - extensions))
    if require_all_formats and missing:
        raise CertA1InventoryRefused("CERT_A1_FULL_FORMAT_INVENTORY_INCOMPLETE")

    rows.sort(key=lambda x: x.extension)
    payload = {
        "schema": 1,
        "reviews": sorted(fingerprints),
        "missing_extensions": missing,
        "status": "INERT_NONPRODUCTION_ONLY",
    }
    fingerprint = hashlib.sha256(
        _DOMAIN + json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii"),
    ).hexdigest()
    return CertA1InventoryReport(
        present=tuple(rows),
        missing_extensions=missing,
        submitted_format_count=len(rows),
        expected_format_count=len(recognized),
        matching_unattested_stage_claims=sum(x.stage_claim_reconciled for x in rows),
        missing_stage_claims=sum(not x.stage_claim_present for x in rows),
        fingerprint_sha256=fingerprint,
    )


__all__ = [
    "CandidateSubmission", "FormatCoverage", "CertA1InventoryRefused",
    "CertA1InventoryReport", "review_paper_format_inventory",
]
