"""CERT-A2: re-derive PAPER evidence from actual pinned files (NO execution).

This is an independent *calculation* within the same software process,
not independently authenticated source provenance, TradingView parity,
host isolation or a permission to trade. Every authority field is DENY.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .core_api_v1 import CoreEventType
from .data_a1_file_intake import HistoricalIntakeReport, inspect_historical_for_paper
from .historical_data_loader_a1 import HistoricalDataRefused, HistoricalFileSpec
from .pine_a1_sma_cross_parity import (
    PineA1Refused,
    PineTraceReview,
    compare_pine_trace,
    parse_pine_sma_cross,
)
from .runtime_a13_security_contract_audit import (
    A13AuditRefused,
    audit_repository,
)

_DOMAIN = b"MMT-CERT-A2-DIRECT-PAPER-REPLAY-V1\x00"
_LIMIT = 10_000


class CertA2Refused(ValueError):
    """Stable refusal codes only, never file paths, values or source bytes."""


@dataclass(frozen=True, slots=True)
class CertA2DirectReplayReview:
    dataset_sha256: str
    dataset_format: str
    claimed_provider: str
    symbol: str
    timeframe: str
    data_rows_replayed: int
    data_core_inputs_prepared: int
    data_prior_claim_checked: bool
    pine_source_sha256: str | None
    pine_oracle_sha256: str | None
    pine_bars_compared: int
    pine_long_signals: int
    pine_short_signals: int
    pine_trace_sha256: str | None
    pine_prior_claim_checked: bool
    report_fingerprint_sha256: str
    status: str = "CERT_A2_DIRECT_REPLAY_REPRODUCED_ONLY_ALL_EXECUTION_DENIED"
    independent_market_source_authenticated: bool = False
    independent_stage_evidence_authenticated: bool = False
    real_tradingview_parity_proven: bool = False
    real_terminal_or_sandbox_attested: bool = False
    paper_strategy_executed: bool = False
    paper_order_sent: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    production_release_authorized: bool = False


def reverify_paper_evidence(
    repository_root: Path,
    data_file: Path, *,
    spec: HistoricalFileSpec,
    operator_ack: bool = False,
    prior_data_claim: HistoricalIntakeReport | None = None,
    pine_source: bytes | None = None,
    pine_source_sha256: str | None = None,
    pine_oracle: bytes | None = None,
    pine_oracle_sha256: str | None = None,
    prior_pine_claim: PineTraceReview | None = None,
) -> CertA2DirectReplayReview:
    """Re-read pinned CSV/Parquet and optionally calculate Pine trace anew.

    The operator must provide ALL Pine inputs together. A matched prior
    dataclass is still an unauthenticated claim; it is NOT a signed receipt.
    """
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or operator_ack is not True):
        raise CertA2Refused("CERT_A2_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if (type(spec) is not HistoricalFileSpec or type(spec.max_rows) is not int
            or not 1 <= spec.max_rows <= _LIMIT
            or not isinstance(data_file, Path) or not data_file.is_absolute()):
        raise CertA2Refused("CERT_A2_EXACT_PINNED_FILE_SPEC_REQUIRED")
    if (prior_data_claim is not None
            and type(prior_data_claim) is not HistoricalIntakeReport):
        raise CertA2Refused("CERT_A2_UNEXPECTED_DATA_CLAIM_TYPE")
    if (prior_pine_claim is not None
            and type(prior_pine_claim) is not PineTraceReview):
        raise CertA2Refused("CERT_A2_UNEXPECTED_PINE_CLAIM_TYPE")

    pine_inputs = (pine_source, pine_source_sha256, pine_oracle, pine_oracle_sha256)
    pine_requested = any(value is not None for value in pine_inputs)
    if (pine_requested and not all(value is not None for value in pine_inputs)
            or prior_pine_claim is not None and not pine_requested):
        raise CertA2Refused("CERT_A2_INCOMPLETE_PINE_REFERENCE")
    if pine_requested and spec.feed.event is not CoreEventType.CLOSED_CANDLE:
        raise CertA2Refused("CERT_A2_PINE_REQUIRES_CLOSED_CANDLES")

    try:
        audit = audit_repository(repository_root)
    except A13AuditRefused as exc:
        raise CertA2Refused("CERT_A2_RUNTIME_SOURCE_HARD_STOP_DRIFT") from exc
    if (audit.hard_stop_checks != 3 or audit.worker_execution_authorized is not False
            or audit.quarantine_release_authorized is not False):
        raise CertA2Refused("CERT_A2_A6_UNCONDITIONAL_DENIAL_REQUIRED")

    feed = spec.feed
    instrument = feed.instrument
    try:
        actual_data = inspect_historical_for_paper(
            data_file, sha256=spec.expected_sha256,
            market=instrument.market, provider=instrument.provider,
            symbol=instrument.symbol, timezone=instrument.timezone,
            quote_currency=instrument.quote_currency,
            timeframe=feed.timeframe, event=feed.event,
            price_basis=feed.price_basis,
            volume_semantics=feed.volume_semantics,
            availability_lag_seconds=spec.availability_lag_seconds,
            max_rows=spec.max_rows, operator_ack=True,
        )
    except (HistoricalDataRefused, ValueError, TypeError) as exc:
        raise CertA2Refused("CERT_A2_ACTUAL_DATA_REPLAY_FAILED") from exc
    if (actual_data.rows_validated != actual_data.paper_core_inputs_validated
            or actual_data.sha256 != spec.expected_sha256
            or actual_data.rows_validated > _LIMIT):
        raise CertA2Refused("CERT_A2_REPLAY_COVERAGE_NOT_COMPLETE")
    if prior_data_claim is not None and prior_data_claim != actual_data:
        raise CertA2Refused("CERT_A2_DATA_CLAIM_DIFFERS_FROM_REPLAY")

    actual_pine: PineTraceReview | None = None
    if pine_requested:
        try:
            rule = parse_pine_sma_cross(
                pine_source, expected_sha256=pine_source_sha256,
            )
            actual_pine = compare_pine_trace(
                data_file, spec=spec, rule=rule,
                oracle_bytes=pine_oracle,
                expected_oracle_sha256=pine_oracle_sha256,
                operator_ack=True,
            )
        except (PineA1Refused, HistoricalDataRefused, TypeError, ValueError) as exc:
            raise CertA2Refused("CERT_A2_ACTUAL_PINE_TRACE_FAILED") from exc
        if (actual_pine.offline_fixture_trace_matched is not True
                or actual_pine.mismatch_bars != 0
                or actual_pine.bars_compared != actual_data.rows_validated
                or actual_pine.symbol != instrument.symbol
                or actual_pine.timeframe != feed.timeframe
                or actual_pine.historical_sha256 != spec.expected_sha256):
            raise CertA2Refused("CERT_A2_PINE_TRACE_DISAGREEMENT")
        if prior_pine_claim is not None and prior_pine_claim != actual_pine:
            raise CertA2Refused("CERT_A2_PINE_CLAIM_DIFFERS_FROM_REPLAY")

    fingerprint = hashlib.sha256(
        _DOMAIN + json.dumps({
            "data_sha": actual_data.sha256,
            "data_type": actual_data.format,
            "symbol": actual_data.symbol,
            "provider": actual_data.provider_claim,
            "timeframe": actual_data.timeframe,
            "data_rows": actual_data.rows_validated,
            "data_last": actual_data.last_observed_at.isoformat(),
            "pine_sha": actual_pine.source_sha256 if actual_pine else None,
            "oracle_sha": actual_pine.oracle_sha256 if actual_pine else None,
            "pine_trace": actual_pine.trace_sha256 if actual_pine else None,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii"),
    ).hexdigest()
    return CertA2DirectReplayReview(
        dataset_sha256=actual_data.sha256,
        dataset_format=actual_data.format,
        claimed_provider=actual_data.provider_claim,
        symbol=actual_data.symbol,
        timeframe=actual_data.timeframe,
        data_rows_replayed=actual_data.rows_validated,
        data_core_inputs_prepared=actual_data.paper_core_inputs_validated,
        data_prior_claim_checked=prior_data_claim is not None,
        pine_source_sha256=actual_pine.source_sha256 if actual_pine else None,
        pine_oracle_sha256=actual_pine.oracle_sha256 if actual_pine else None,
        pine_bars_compared=actual_pine.bars_compared if actual_pine else 0,
        pine_long_signals=actual_pine.long_signals if actual_pine else 0,
        pine_short_signals=actual_pine.short_signals if actual_pine else 0,
        pine_trace_sha256=actual_pine.trace_sha256 if actual_pine else None,
        pine_prior_claim_checked=prior_pine_claim is not None,
        report_fingerprint_sha256=fingerprint,
    )


__all__ = ["CertA2Refused", "CertA2DirectReplayReview", "reverify_paper_evidence"]
