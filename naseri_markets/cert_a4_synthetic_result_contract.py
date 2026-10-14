"""CERT-A4: replay and compare SYNTHETIC CoreResult claims; NEVER run Workers.

An externally submitted Python/JS/TS/WASM "result" is only a claim.
Even valid results cannot certify that any strategy or language ran.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from .cert_a3_four_language_wire_replay import (
    CertA3Refused,
    CertA3Review,
    RuntimeSourceSubmission,
    reproduce_four_runtime_wires,
)
from .core_api_v1 import (
    CoreBinding,
    CoreContractError,
    CoreDecision,
    CoreManifest,
    CoreResult,
    DataOrigin,
    DecisionKind,
    content_digest,
    validate_core_result,
)
from .historical_data_loader_a1 import (
    HistoricalDataRefused,
    HistoricalFileSpec,
    validate_historical_file,
)
from .market_data_engine_v1 import (
    MarketDataRefused,
    OfflineMarketDataEngine,
    PacketStatus,
)
from .multilang_runtime_a1 import RuntimeKind

_MAX_BARS = 512
_MAX_DECISIONS = 12
_DOMAIN = b"MMT-CERT-A4-SYNTHETIC-RESULT-CONTRACT-V1\x00"
_KINDS = tuple(RuntimeKind)
_GENESIS = b"\x00" * 32


class CertA4Refused(ValueError):
    """Stable refusal messages omit candidate code, market prices and keys."""


@dataclass(frozen=True, slots=True)
class SyntheticResultTrace:
    """Caller-built CoreResult objects. NOT signed, executed or trusted."""

    kind: RuntimeKind
    results: tuple[CoreResult, ...]
    claim_origin: str = "SYNTHETIC_TEST_FIXTURE_NOT_WORKER_OUTPUT"


@dataclass(frozen=True, slots=True)
class CertA4ResultReview:
    dataset_sha256: str
    four_language_wire_fingerprint_sha256: str
    core_id: str
    binding_id: str
    ready_bars_reviewed: int
    result_claims_checked: int
    decision_shapes_checked: int
    entry_intent_shapes_checked: int
    decision_trace_sha256: str
    report_fingerprint_sha256: str
    prior_a3_claim_reproduced: bool
    synthetic_claims_matched: bool
    status: str = "CERT_A4_SYNTHETIC_RESULT_CONTRACT_REPLAY_ONLY_ALL_EXECUTION_DENIED"
    independent_claim_origins_authenticated: bool = False
    actual_runtime_results_authenticated: bool = False
    strategy_equivalence_proven: bool = False
    paper_strategy_executed: bool = False
    paper_order_sent: bool = False
    broker_order_sent: bool = False
    telegram_sent: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    production_release_authorized: bool = False


def _gate(operator_ack: bool) -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or operator_ack is not True):
        raise CertA4Refused("CERT_A4_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")


def _traces(
    claims: tuple[SyntheticResultTrace, ...],
) -> dict[RuntimeKind, tuple[CoreResult, ...]]:
    if type(claims) is not tuple or len(claims) != len(_KINDS):
        raise CertA4Refused("CERT_A4_EXACT_FOUR_SYNTHETIC_TRACES_REQUIRED")
    records: dict[RuntimeKind, tuple[CoreResult, ...]] = {}
    for entry in claims:
        if (type(entry) is not SyntheticResultTrace
                or type(entry.kind) is not RuntimeKind
                or entry.kind in records
                or entry.claim_origin != "SYNTHETIC_TEST_FIXTURE_NOT_WORKER_OUTPUT"
                or type(entry.results) is not tuple
                or not 1 <= len(entry.results) <= _MAX_BARS
                or any(type(r) is not CoreResult for r in entry.results)):
            raise CertA4Refused("CERT_A4_UNTRUSTED_RESULT_CLAIM_SCHEMA_INVALID")
        records[entry.kind] = entry.results
    if set(records) != set(_KINDS):
        raise CertA4Refused("CERT_A4_MISSING_SYNTHETIC_LANGUAGE")
    sizes = {len(x) for x in records.values()}
    if len(sizes) != 1:
        raise CertA4Refused("CERT_A4_LANGUAGE_TRACE_LENGTH_MISMATCH")
    return records


def review_synthetic_core_result_traces(
    repository_root: Path, data_file: Path, *,
    spec: HistoricalFileSpec,
    manifest: CoreManifest,
    binding: CoreBinding,
    sources: tuple[RuntimeSourceSubmission, ...],
    claims: tuple[SyntheticResultTrace, ...],
    prior_a3_claim: CertA3Review | None = None,
    operator_ack: bool = False,
) -> CertA4ResultReview:
    """Recreate A3 wire evidence and check independently built DATA-A1 events.

    CoreResult validation checks structure, identity, setup, entry stop
    geometry and event semantics; it DOES NOT prove code produced results.
    Accepting an entry INTENT-shaped claim NEVER routes it to PAPER orders.
    """
    _gate(operator_ack)
    if (type(spec) is not HistoricalFileSpec
            or type(spec.max_rows) is not int
            or not 1 <= spec.max_rows <= _MAX_BARS
            or not isinstance(data_file, Path) or not data_file.is_absolute()
            or type(manifest) is not CoreManifest
            or type(binding) is not CoreBinding
            or (prior_a3_claim is not None
                and type(prior_a3_claim) is not CertA3Review)):
        raise CertA4Refused("CERT_A4_BOUNDED_EXACT_CONTEXT_REQUIRED")
    indexed = _traces(claims)
    try:
        a3 = reproduce_four_runtime_wires(
            repository_root, data_file, spec=spec, manifest=manifest,
            binding=binding, sources=sources, operator_ack=True,
        )
    except CertA3Refused as exc:
        raise CertA4Refused("CERT_A4_FOUR_LANGUAGE_REPLAY_REFUSED") from exc
    if (prior_a3_claim is not None and prior_a3_claim != a3):
        raise CertA4Refused("CERT_A4_PRIOR_A3_CLAIM_NOT_REPRODUCED")
    if (a3.worker_execution_authorized is not False
            or a3.actual_worker_executed is not False
            or a3.paper_order_sent is not False
            or a3.broker_order_sent is not False
            or a3.telegram_sent is not False
            or a3.quarantine_release_authorized is not False):
        raise CertA4Refused("CERT_A4_A3_AUTHORITY_DRIFT")
    expected = a3.language_traces
    if (len(expected) != 4
            or tuple(x.language for x in expected) != tuple(k.value for k in _KINDS)
            or any(x.actual_worker_executed is not False
                   or x.actual_core_result_verified is not False
                   for x in expected)):
        raise CertA4Refused("CERT_A4_A3_EXECUTION_PROOF_DRIFT")
    frame_count = expected[0].frames_prepared
    if (frame_count == 0 or any(len(rows) != frame_count for rows in indexed.values())
            or any(item.frames_prepared != frame_count for item in expected)):
        raise CertA4Refused("CERT_A4_RESULT_COUNT_VS_FRAMES_MISMATCH")
    try:
        approved = validate_historical_file(data_file, spec)
        engine = OfflineMarketDataEngine(enabled=True)
        engine.register_feed(spec.feed)
        engine.subscribe(spec.feed.feed_id, manifest, binding)
        ready = count = decisions = entries = 0
        rolling = _GENESIS
        for packet in approved.packets():
            count += 1
            dispatch = engine.ingest(packet)
            if dispatch.status is PacketStatus.WARMING:
                if dispatch.deliveries:
                    raise CertA4Refused("CERT_A4_WARMUP_HAS_RESULT_DISPATCH")
                continue
            if (dispatch.status is not PacketStatus.ACCEPTED
                    or len(dispatch.deliveries) != 1):
                raise CertA4Refused("CERT_A4_MARKET_DATA_DISPATCH_INVALID")
            event = dispatch.deliveries[0].event
            if (event.origin is not DataOrigin.REPLAY
                    or event.binding != binding
                    or event.event is not spec.feed.event
                    or event.observed_at != packet.observed_at
                    or event.observed_at > packet.received_at
                    or event.source_ref != spec.feed.source_ref):
                raise CertA4Refused("CERT_A4_CAUSAL_EVENT_OR_IDENTITY_DRIFT")
            digests: list[str] = []
            for kind in _KINDS:
                result = indexed[kind][ready]
                try:
                    # Frozen Python dataclasses are not a security boundary;
                    # object.__setattr__ can still forge them. Reconstruct
                    # ALL decisions and the result to invoke their own
                    # post-init type/geometry checks anew.
                    if any(type(d) is not CoreDecision for d in result.decisions):
                        raise CoreContractError("INVALID_DECISION_TYPE")
                    validated = replace(
                        result, decisions=tuple(replace(d) for d in result.decisions),
                    )
                    validate_core_result(manifest, event, validated)
                except (CoreContractError, ValueError, TypeError, AttributeError) as exc:
                    raise CertA4Refused("CERT_A4_RESULT_CONTRACT_OR_PROVENANCE_REFUSED") from exc
                if not 1 <= len(result.decisions) <= _MAX_DECISIONS:
                    raise CertA4Refused("CERT_A4_DECISION_BATCH_LIMIT")
                digests.append(content_digest(result.decisions))
            # Different language claims must agree *as submitted*. The
            # comparison is not evidence of runtime behavior equivalence.
            if len(set(digests)) != 1:
                raise CertA4Refused("CERT_A4_SYNTHETIC_LANGUAGE_DECISIONS_DISAGREE")
            first = indexed[_KINDS[0]][ready]
            decisions += len(first.decisions)
            entries += sum(d.kind is DecisionKind.ENTRY_INTENT
                           for d in first.decisions)
            rolling = hashlib.sha256(
                _DOMAIN + rolling + (ready + 1).to_bytes(8, "big")
                + event.input_digest.encode("ascii")
                + digests[0].encode("ascii"),
            ).digest()
            ready += 1
        if (count != a3.rows_replayed or ready != frame_count
                or engine.state(spec.feed.feed_id).quarantined):
            raise CertA4Refused("CERT_A4_INCOMPLETE_MARKET_REPLAY")
    except (HistoricalDataRefused, MarketDataRefused, CoreContractError) as exc:
        raise CertA4Refused("CERT_A4_DIRECT_DATA_REPLAY_INVALID") from exc
    fingerprint = hashlib.sha256(
        _DOMAIN + json.dumps({
            "dataset": a3.dataset_sha256, "a3": a3.fingerprint_sha256,
            "core": manifest.core_id, "binding": binding.binding_id,
            "bar_count": ready, "claims": len(_KINDS) * ready,
            "decision_trace": rolling.hex(),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"),
    ).hexdigest()
    return CertA4ResultReview(
        dataset_sha256=a3.dataset_sha256,
        four_language_wire_fingerprint_sha256=a3.fingerprint_sha256,
        core_id=manifest.core_id, binding_id=binding.binding_id,
        ready_bars_reviewed=ready, result_claims_checked=ready * len(_KINDS),
        decision_shapes_checked=decisions * len(_KINDS),
        entry_intent_shapes_checked=entries * len(_KINDS),
        decision_trace_sha256=rolling.hex(),
        report_fingerprint_sha256=fingerprint,
        prior_a3_claim_reproduced=prior_a3_claim is not None,
        synthetic_claims_matched=True,
    )


__all__ = [
    "CertA4Refused", "SyntheticResultTrace", "CertA4ResultReview",
    "review_synthetic_core_result_traces",
]
