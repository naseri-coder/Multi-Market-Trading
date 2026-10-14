"""CERT-A3: directly recreate four offline Core API wire traces, NEVER run them.

This verifies identical historical scope, causal frame counts and digest
integrity for Python, JavaScript, TypeScript and WASM. It is NOT execution
parity or source/host attestation. Every authority field remains FALSE.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .cert_a2_direct_paper_replay import (
    CertA2DirectReplayReview,
    CertA2Refused,
    reverify_paper_evidence,
)
from .core_api_v1 import CoreBinding, CoreManifest
from .data_a1_file_intake import HistoricalIntakeReport
from .data_runtime_paper_wire_a1 import (
    PaperWireRefused,
    PaperWireReview,
    review_file_to_runtime_wire,
)
from .historical_data_loader_a1 import HistoricalFileSpec
from .multilang_runtime_a1 import RuntimeKind

_DOMAIN = b"MMT-CERT-A3-FOUR-LANGUAGE-REPLAY-V1\x00"
_EXTENSIONS = {
    RuntimeKind.PYTHON: ".py",
    RuntimeKind.JAVASCRIPT: ".js",
    RuntimeKind.TYPESCRIPT: ".ts",
    RuntimeKind.WASM: ".wasm",
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_MAX_ROWS = 2048
_MAX_SOURCE_BYTES = 128 * 1024


class CertA3Refused(ValueError):
    """Stable refusal codes never include source bytes or trading data."""


@dataclass(frozen=True, slots=True)
class RuntimeSourceSubmission:
    kind: RuntimeKind
    artifact_name: str
    artifact: bytes
    approved_sha256: str
    prior_wire_claim: PaperWireReview | None = None


@dataclass(frozen=True, slots=True)
class RuntimeWireReproduction:
    language: str
    artifact_sha256: str
    transcript_sha256: str
    validated_rows: int
    warmup_rows: int
    frames_prepared: int
    peak_frame_bytes: int
    prior_claim_matched: bool
    actual_worker_executed: bool = False
    actual_core_result_verified: bool = False
    broker_or_telegram_authorized: bool = False


@dataclass(frozen=True, slots=True)
class CertA3Review:
    dataset_sha256: str
    dataset_format: str
    symbol: str
    timeframe: str
    rows_replayed: int
    paper_core_inputs_prepared: int
    manifest_core_id: str
    binding_id: str
    language_traces: tuple[RuntimeWireReproduction, ...]
    fingerprint_sha256: str
    status: str = "CERT_A3_FOUR_LANGUAGE_PAPER_WIRES_REPRODUCED_EXECUTION_DENIED"
    independently_authenticated_market_source: bool = False
    independently_verified_runtime_host: bool = False
    actual_worker_executed: bool = False
    actual_strategy_behavior_equivalent: bool = False
    paper_strategy_executed: bool = False
    paper_order_sent: bool = False
    broker_order_sent: bool = False
    telegram_sent: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    production_release_authorized: bool = False


def _operator_gate(operator_ack: bool) -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or operator_ack is not True):
        raise CertA3Refused("CERT_A3_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")


def _validate_submissions(
    sources: tuple[RuntimeSourceSubmission, ...],
) -> tuple[RuntimeSourceSubmission, ...]:
    if type(sources) is not tuple or len(sources) != len(_EXTENSIONS):
        raise CertA3Refused("CERT_A3_EXACT_FOUR_LANGUAGE_BUNDLE_REQUIRED")
    indexed: dict[RuntimeKind, RuntimeSourceSubmission] = {}
    seen_names: set[str] = set()
    for submission in sources:
        if (type(submission) is not RuntimeSourceSubmission
                or type(submission.kind) is not RuntimeKind
                or submission.kind in indexed
                or type(submission.artifact_name) is not str
                or _NAME.fullmatch(submission.artifact_name) is None
                or Path(submission.artifact_name).suffix.lower()
                != _EXTENSIONS[submission.kind]
                or type(submission.artifact) is not bytes
                or not 0 < len(submission.artifact) <= _MAX_SOURCE_BYTES
                or type(submission.approved_sha256) is not str
                or _SHA.fullmatch(submission.approved_sha256) is None
                or hashlib.sha256(submission.artifact).hexdigest()
                != submission.approved_sha256
                or submission.artifact_name.casefold() in seen_names
                or (submission.prior_wire_claim is not None
                    and type(submission.prior_wire_claim) is not PaperWireReview)):
            raise CertA3Refused("CERT_A3_UNPINNED_DUPLICATE_OR_UNSAFE_SOURCE")
        indexed[submission.kind] = submission
        seen_names.add(submission.artifact_name.casefold())
    if set(indexed) != set(_EXTENSIONS):
        raise CertA3Refused("CERT_A3_MISSING_RUNTIME_KIND")
    return tuple(indexed[k] for k in _EXTENSIONS)


def reproduce_four_runtime_wires(
    repository_root: Path, data_file: Path, *,
    spec: HistoricalFileSpec,
    manifest: CoreManifest,
    binding: CoreBinding,
    sources: tuple[RuntimeSourceSubmission, ...],
    operator_ack: bool = False,
    prior_data_claim: HistoricalIntakeReport | None = None,
) -> CertA3Review:
    """Re-read pinned DATA-A1 bytes and construct four canonical A1 wires.

    Each language uses the same manifest, binding and historical source;
    frame payload hashes are expected to DIFFER due to different source
    identity/language. Their causal timestamps and counts must agree.
    No child process, language engine, runtime container or code evaluation.
    """
    _operator_gate(operator_ack)
    if (type(spec) is not HistoricalFileSpec
            or type(spec.max_rows) is not int
            or not 1 <= spec.max_rows <= _MAX_ROWS
            or not isinstance(data_file, Path) or not data_file.is_absolute()
            or type(manifest) is not CoreManifest
            or type(binding) is not CoreBinding):
        raise CertA3Refused("CERT_A3_BOUNDED_EXACT_TYPED_REPLAY_REQUIRED")
    chosen = _validate_submissions(sources)
    try:
        data: CertA2DirectReplayReview = reverify_paper_evidence(
            repository_root, data_file, spec=spec, operator_ack=True,
            prior_data_claim=prior_data_claim,
        )
    except CertA2Refused as exc:
        raise CertA3Refused("CERT_A3_DIRECT_DATA_REPLAY_REFUSED") from exc
    if (data.data_rows_replayed != data.data_core_inputs_prepared
            or data.data_rows_replayed > _MAX_ROWS
            or data.dataset_sha256 != spec.expected_sha256
            or data.symbol != binding.instrument.symbol
            or data.timeframe != binding.timeframe
            or binding.instrument != spec.feed.instrument):
        raise CertA3Refused("CERT_A3_DATA_IDENTITY_DRIFT")
    results: list[RuntimeWireReproduction] = []
    baseline: tuple[int, int, int, object, object] | None = None
    for src in chosen:
        try:
            wire = review_file_to_runtime_wire(
                data_file, spec=spec, manifest=manifest, binding=binding,
                kind=src.kind, artifact_name=src.artifact_name,
                artifact=src.artifact, artifact_sha256=src.approved_sha256,
                max_frames=_MAX_ROWS, operator_ack=True,
            )
        except PaperWireRefused as exc:
            raise CertA3Refused("CERT_A3_RUNTIME_WIRE_REPLAY_REFUSED") from exc
        if (wire.source_sha256 != spec.expected_sha256
                or wire.language != src.kind.value
                or wire.artifact_sha256 != src.approved_sha256
                or wire.source_ref != spec.feed.source_ref
                or wire.symbol != binding.instrument.symbol
                or wire.timeframe != binding.timeframe
                or wire.core_id != manifest.core_id
                or wire.binding_id != binding.binding_id
                or wire.worker_executed is not False
                or wire.worker_execution_authorized is not False
                or wire.paper_order_sent is not False
                or wire.broker_order_sent is not False
                or wire.telegram_sent is not False
                or wire.quarantine_release_authorized is not False):
            raise CertA3Refused("CERT_A3_WIRE_SCOPE_OR_AUTHORITY_DRIFT")
        geometry = (
            wire.validated_rows, wire.warmup_rows, wire.frames_prepared,
            wire.first_ready_observed_at, wire.last_ready_observed_at,
        )
        if (wire.validated_rows != data.data_rows_replayed
                or wire.frames_prepared < 1
                or wire.frames_prepared + wire.warmup_rows
                != data.data_rows_replayed
                or baseline is not None and geometry != baseline):
            raise CertA3Refused("CERT_A3_INCONSISTENT_LANGUAGE_REPLAY_GEOMETRY")
        baseline = geometry
        if src.prior_wire_claim is not None and wire != src.prior_wire_claim:
            raise CertA3Refused("CERT_A3_PRIOR_WIRE_CLAIM_NOT_REPRODUCED")
        results.append(RuntimeWireReproduction(
            language=src.kind.value,
            artifact_sha256=wire.artifact_sha256,
            transcript_sha256=wire.transcript_sha256,
            validated_rows=wire.validated_rows,
            warmup_rows=wire.warmup_rows,
            frames_prepared=wire.frames_prepared,
            peak_frame_bytes=wire.peak_frame_bytes,
            prior_claim_matched=src.prior_wire_claim is not None,
        ))
    fingerprint = hashlib.sha256(
        _DOMAIN + json.dumps({
            "dataset": data.dataset_sha256,
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "core": manifest.core_id,
            "binding": binding.binding_id,
            "traces": [(v.language, v.artifact_sha256, v.transcript_sha256,
                        v.warmup_rows, v.frames_prepared) for v in results],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"),
    ).hexdigest()
    return CertA3Review(
        dataset_sha256=data.dataset_sha256,
        dataset_format=data.dataset_format,
        symbol=data.symbol, timeframe=data.timeframe,
        rows_replayed=data.data_rows_replayed,
        paper_core_inputs_prepared=data.data_core_inputs_prepared,
        manifest_core_id=manifest.core_id, binding_id=binding.binding_id,
        language_traces=tuple(results), fingerprint_sha256=fingerprint,
    )


__all__ = [
    "CertA3Refused", "RuntimeSourceSubmission",
    "RuntimeWireReproduction", "CertA3Review",
    "reproduce_four_runtime_wires",
]
