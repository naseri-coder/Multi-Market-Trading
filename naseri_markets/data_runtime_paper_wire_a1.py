"""DATA→RUNTIME bridge: inert, hash-chained Core API wire PREPARATION only.

Source bytes and market history never leave this process. Frames are built
using RUNTIME-A1's existing canonical contract, NOT dispatched to any Worker.
No dynamic strategy import, execution, broker, Telegram or live/PAPER orders.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .core_api_v1 import CoreBinding, CoreManifest, DataOrigin
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
from .multilang_runtime_a1 import (
    MultilangRefused,
    RuntimeKind,
    prepare_framed_request,
)

_MAX_WIRES = 2048
_GENESIS = b"\x00" * 32
_DOMAIN = b"MMT-DATA-RUNTIME-PAPER-WIRE-A1-V1\x00"


class PaperWireRefused(ValueError):
    """Fail closed; errors disclose neither user source nor historical prices."""


@dataclass(frozen=True, slots=True)
class PaperWireReview:
    """Aggregate outcome, not a launch or trading authorization."""

    source_sha256: str
    source_ref: str
    artifact_sha256: str
    language: str
    symbol: str
    timeframe: str
    core_id: str
    binding_id: str
    validated_rows: int
    warmup_rows: int
    frames_prepared: int
    peak_frame_bytes: int
    transcript_sha256: str
    first_ready_observed_at: datetime
    last_ready_observed_at: datetime
    status: str = "DATA_RUNTIME_PAPER_WIRE_VALIDATED_NO_WORKER_EXECUTION"
    market_source_authenticated: bool = False
    actual_point_in_time_proven: bool = False
    independent_host_certified: bool = False
    worker_executed: bool = False
    paper_order_sent: bool = False
    broker_order_sent: bool = False
    telegram_sent: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False


def review_file_to_runtime_wire(
    path: Path, *, spec: HistoricalFileSpec,
    manifest: CoreManifest, binding: CoreBinding, kind: RuntimeKind,
    artifact_name: str, artifact: bytes, artifact_sha256: str,
    max_frames: int = _MAX_WIRES, operator_ack: bool = False,
) -> PaperWireReview:
    """Review full pinned local dataset, then build A1 wire frames in memory.

    An operator-selected fixed CoreManifest and CoreBinding must match the
    historical feed precisely. Source and frames are not persisted or sent.
    If the file drifts or a later row fails, no success report is returned.
    """
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or operator_ack is not True):
        raise PaperWireRefused("BRIDGE_EXPLICIT_NONPRODUCTION_OPERATOR_ACK_REQUIRED")
    if (not isinstance(path, Path) or not path.is_absolute()
            or type(spec) is not HistoricalFileSpec
            or not isinstance(manifest, CoreManifest)
            or not isinstance(binding, CoreBinding)
            or not isinstance(kind, RuntimeKind)
            or type(artifact_name) is not str or type(artifact) is not bytes
            or type(artifact_sha256) is not str
            or type(max_frames) is not int or not 1 <= max_frames <= _MAX_WIRES):
        raise PaperWireRefused("BRIDGE_EXACT_TYPED_SCOPE_REQUIRED")

    feed = spec.feed
    if (feed.origin is not DataOrigin.REPLAY
            or binding.instrument != feed.instrument
            or binding.timeframe != feed.timeframe
            or binding.instrument.market not in manifest.supported_markets
            or feed.event not in manifest.accepted_events
            or (feed.event.value == "closed_candle"
                and manifest.minimum_closed_candles > feed.history_limit)):
        raise PaperWireRefused("BRIDGE_MANIFEST_BINDING_FEED_MISMATCH")

    if spec.max_rows > 5_000_000:
        raise PaperWireRefused("BRIDGE_MAX_ROWS_INVALID")

    try:
        approved = validate_historical_file(path, spec)
        engine = OfflineMarketDataEngine(enabled=True)
        engine.register_feed(feed)
        engine.subscribe(feed.feed_id, manifest, binding)
        count = warming = ready = peak = 0
        rolling = _GENESIS
        first_ready: datetime | None = None
        last_ready: datetime | None = None
        for packet in approved.packets():
            count += 1
            dispatch = engine.ingest(packet)
            if dispatch.status is PacketStatus.WARMING:
                if dispatch.deliveries or dispatch.waiting_bindings != (binding.binding_id,):
                    raise PaperWireRefused("BRIDGE_UNEXPECTED_WARMUP_DISPATCH")
                warming += 1
                continue
            if (dispatch.status is not PacketStatus.ACCEPTED
                    or len(dispatch.deliveries) != 1 or dispatch.waiting_bindings):
                raise PaperWireRefused("BRIDGE_INVALID_PAPER_DISPATCH")
            d = dispatch.deliveries[0]
            event = d.event
            if (d.binding_id != binding.binding_id
                    or event.core_id != manifest.core_id
                    or event.core_version != manifest.core_version
                    or event.binding != binding
                    or event.origin is not DataOrigin.REPLAY
                    or event.observed_at != packet.observed_at
                    or event.observed_at > packet.received_at
                    or event.source_ref != feed.source_ref
                    or (packet.candle is not None and (
                        not event.candles or event.candles[-1] != packet.candle
                        or any(c.close_at > event.observed_at for c in event.candles)
                    ))
                    or (packet.tick is not None and event.tick != packet.tick)):
                raise PaperWireRefused("BRIDGE_CAUSAL_OR_IDENTITY_DRIFT")
            ready += 1
            if ready > max_frames:
                raise PaperWireRefused("BRIDGE_MAX_FRAMES_EXCEEDED")
            # Contract framing ONLY. This intentionally does not instantiate
            # MultiLanguageOfflineHost, call evaluate, _run_oci or Docker.
            wire = prepare_framed_request(
                kind, manifest, event, artifact_name=artifact_name,
                artifact=artifact, approved_sha256=artifact_sha256,
            )
            if len(wire) > 192 * 1024:
                raise PaperWireRefused("BRIDGE_WIRE_SIZE_DRIFT")
            peak = max(peak, len(wire))
            rolling = hashlib.sha256(
                _DOMAIN + rolling + ready.to_bytes(8, "big")
                + hashlib.sha256(wire).digest(),
            ).digest()
            if first_ready is None:
                first_ready = event.observed_at
            last_ready = event.observed_at
        if (count != approved.report.rows_validated
                or ready == 0 or first_ready is None or last_ready is None
                or count != warming + ready
                or engine.state(feed.feed_id).quarantined):
            raise PaperWireRefused("BRIDGE_INCOMPLETE_VALIDATION")
        return PaperWireReview(
            source_sha256=approved.report.sha256,
            source_ref=feed.source_ref,
            artifact_sha256=artifact_sha256,
            language=kind.value,
            symbol=feed.instrument.symbol,
            timeframe=feed.timeframe,
            core_id=manifest.core_id,
            binding_id=binding.binding_id,
            validated_rows=count,
            warmup_rows=warming,
            frames_prepared=ready,
            peak_frame_bytes=peak,
            transcript_sha256=rolling.hex(),
            first_ready_observed_at=first_ready,
            last_ready_observed_at=last_ready,
        )
    except (HistoricalDataRefused, MarketDataRefused, MultilangRefused,
            ValueError, TypeError) as exc:
        if isinstance(exc, PaperWireRefused):
            raise
        raise PaperWireRefused("BRIDGE_INPUT_OR_WIRE_VALIDATION_FAILED") from exc


__all__ = ["PaperWireRefused", "PaperWireReview", "review_file_to_runtime_wire"]
