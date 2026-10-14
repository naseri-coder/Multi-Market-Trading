"""Only offline DATA-A1 -> RUNTIME-A1 frame construction, never execution."""
from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    CoreBinding,
    CoreEventType,
    CoreManifest,
    DataOrigin,
    SetupSpec,
)
from naseri_markets.data_runtime_paper_wire_a1 import (
    PaperWireRefused,
    review_file_to_runtime_wire,
)
from naseri_markets.historical_data_loader_a1 import HistoricalFileSpec
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition,
    PriceBasis,
    VolumeSemantics,
)
from naseri_markets.multilang_runtime_a1 import RuntimeKind
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)

T0 = datetime(2026, 10, 13, 10, tzinfo=UTC)
HEADER = b"open_at,close_at,open,high,low,close,volume\n"
ROWS = (
    b"2026-10-13T10:00:00Z,2026-10-13T10:15:00Z,100,102,98,101,10\n",
    b"2026-10-13T10:15:00Z,2026-10-13T10:30:00Z,101,104,99,103,11\n",
    b"2026-10-13T10:30:00Z,2026-10-13T10:45:00Z,103,105,100,102,12\n",
)
ROWS_BYTES = HEADER + b"".join(ROWS)
ARTIFACTS = {
    RuntimeKind.PYTHON: (
        "fixed.py",
        b"def evaluate(event):\n    return [{'decision_id': 'fixed', 'kind': 'no_setup'}]\n",
    ),
    RuntimeKind.JAVASCRIPT: (
        "fixed.js", b"function evaluate(event) { return []; }\n",
    ),
    RuntimeKind.TYPESCRIPT: (
        "fixed.ts", b"function evaluate(event: unknown) { return []; }\n",
    ),
    RuntimeKind.WASM: ("fixed.wasm", b"\x00asm\x01\x00\x00\x00"),
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _prepare(tmp_path: Path, kind=RuntimeKind.PYTHON, raw=None,
             minimum=2, event=CoreEventType.CLOSED_CANDLE):
    if raw is None:
        raw = ROWS_BYTES
    path = tmp_path / "approved.csv"
    path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    instrument = Instrument(Market.CRYPTO, "operator_declared_test_provider",
                            "ABCUSDT", "UTC", "USDT")
    feed = FeedDefinition(
        "bridge_test_feed", instrument, "15m", event, DataOrigin.REPLAY,
        "hist_" + sha[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120, history_limit=128,
    )
    spec = HistoricalFileSpec(feed, sha, availability_lag_seconds=7)
    manifest = CoreManifest(
        "FixedResearchCore", "1.0",
        (SetupSpec("fixed", "Fixed fixture, not evaluated"),),
        frozenset({Market.CRYPTO}), frozenset({event}),
        minimum_closed_candles=minimum,
    )
    binding = CoreBinding("fixture_instance", "fixture_binding",
                          instrument, "15m")
    name, artifact = ARTIFACTS[kind]
    args = dict(
        spec=spec, manifest=manifest, binding=binding, kind=kind,
        artifact_name=name, artifact=artifact,
        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
        operator_ack=True,
    )
    return path, args


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_each_language_prepares_only_two_causal_frames(kind, tmp_path, monkeypatch):
    import naseri_markets.data_runtime_paper_wire_a1 as bridge

    path, opts = _prepare(tmp_path, kind=kind)
    original = bridge.prepare_framed_request
    events = []

    def inspect(kind, manifest, event, **kwargs):
        events.append(event)
        wire = original(kind, manifest, event, **kwargs)
        size = int.from_bytes(wire[:4], "big")
        obj = json.loads(wire[4 + size:])
        assert obj["artifact_sha256"] == opts["artifact_sha256"]
        assert obj["input_digest"] == event.input_digest
        assert obj["protocol"] == "RUNTIME_A1_FRAMED_V1"
        assert obj["runtime_kind"] == kind.value
        assert obj["event"]["origin"] == "replay"
        assert obj["event"]["source_ref"] == opts["spec"].feed.source_ref
        return wire

    monkeypatch.setattr(bridge, "prepare_framed_request", inspect)
    first = review_file_to_runtime_wire(path, **opts)
    assert first.frames_prepared == 2
    assert first.warmup_rows == 1
    assert first.validated_rows == 3
    assert first.language == kind.value
    assert first.symbol == "ABCUSDT"
    assert first.timeframe == "15m"
    assert first.first_ready_observed_at == T0 + timedelta(minutes=30)
    assert first.last_ready_observed_at == T0 + timedelta(minutes=45)
    assert first.transcript_sha256 != "0" * 64
    assert first.peak_frame_bytes > 50
    assert len(events) == 2
    assert [len(e.candles) for e in events] == [2, 3]
    for e in events:
        assert e.origin is DataOrigin.REPLAY
        assert all(c.close_at <= e.observed_at for c in e.candles)
        assert e.candles[-1].close_at == e.observed_at
        assert e.input_digest
    assert first.market_source_authenticated is False
    assert first.actual_point_in_time_proven is False
    assert first.independent_host_certified is False
    assert first.worker_executed is False
    assert first.paper_order_sent is False
    assert first.broker_order_sent is False
    assert first.telegram_sent is False
    assert first.worker_execution_authorized is False
    assert first.quarantine_release_authorized is False
    assert sorted(p.name for p in tmp_path.iterdir()) == ["approved.csv"]
    assert path.read_bytes() == HEADER + b"".join(ROWS)


def test_deterministic_transcript_and_source_mutation_changes_hash(tmp_path):
    path, opts = _prepare(tmp_path)
    first = review_file_to_runtime_wire(path, **opts)
    second = review_file_to_runtime_wire(path, **opts)
    assert first == second
    revised = (HEADER + ROWS[0] + ROWS[1]
               + ROWS[2].replace(b",103,105,100,102,12", b",103,105,100,104,12"))
    other = tmp_path / "new"
    other.mkdir()
    newpath, newopts = _prepare(other, raw=revised)
    changed = review_file_to_runtime_wire(newpath, **newopts)
    assert changed.transcript_sha256 != first.transcript_sha256


def test_actual_parquet_groups_bridge_to_causal_wire(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path, opts = _prepare(tmp_path)
    out = tmp_path / "approved.parquet"
    records = {
        "open_at": ["2026-10-13T10:00:00Z", "2026-10-13T10:15:00Z",
                    "2026-10-13T10:30:00Z"],
        "close_at": ["2026-10-13T10:15:00Z", "2026-10-13T10:30:00Z",
                     "2026-10-13T10:45:00Z"],
        "open": ["100", "101", "103"],
        "high": ["102", "104", "105"],
        "low": ["98", "99", "100"],
        "close": ["101", "103", "102"],
        "volume": ["10", "11", "12"],
    }
    pq.write_table(pa.table({k: pa.array(v, type=pa.string())
                             for k, v in records.items()}), out, row_group_size=1)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    feed = opts["spec"].feed
    newfeed = FeedDefinition(
        feed.feed_id, feed.instrument, feed.timeframe, feed.event, feed.origin,
        "hist_" + digest[:40], feed.price_basis, feed.volume_semantics,
        max_latency_seconds=120, history_limit=128,
    )
    opts["spec"] = HistoricalFileSpec(newfeed, digest, availability_lag_seconds=7)
    review = review_file_to_runtime_wire(out, **opts)
    assert review.frames_prepared == 2
    assert review.validated_rows == 3
    assert review.source_sha256 == digest
    assert review.first_ready_observed_at == T0 + timedelta(minutes=30)


@pytest.mark.parametrize("tamper", ["symbol", "timeframe", "manifest_market", "event"])
def test_incompatible_feed_manifest_binding_refused(tmp_path, tamper):
    path, opts = _prepare(tmp_path)
    original = opts["binding"]
    if tamper == "symbol":
        instrument = Instrument(Market.CRYPTO, "operator_declared_test_provider",
                                "DIFFERENTUSDT", "UTC", "USDT")
        opts["binding"] = CoreBinding(original.instance_id, original.binding_id,
                                      instrument, original.timeframe)
    elif tamper == "timeframe":
        opts["binding"] = CoreBinding(original.instance_id, original.binding_id,
                                      original.instrument, "1h")
    elif tamper == "manifest_market":
        opts["manifest"] = CoreManifest(
            "DifferentCore", "1.0", (SetupSpec("fixed", "check"),),
            frozenset({Market.FOREX}), frozenset({CoreEventType.CLOSED_CANDLE}),
        )
    else:
        opts["manifest"] = CoreManifest(
            "DifferentCore", "1.0", (SetupSpec("fixed", "check"),),
            frozenset({Market.CRYPTO}), frozenset({CoreEventType.QUOTE_TICK}),
        )
    with pytest.raises(PaperWireRefused, match="BRIDGE_MANIFEST_BINDING_FEED_MISMATCH"):
        review_file_to_runtime_wire(path, **opts)


def test_mismatched_source_sha_bad_strategy_and_wrong_language_fail(tmp_path):
    path, opts = _prepare(tmp_path)
    with pytest.raises(PaperWireRefused, match="BRIDGE_INPUT_OR_WIRE_VALIDATION_FAILED"):
        review_file_to_runtime_wire(path, **(opts | {"artifact_sha256": "f" * 64}))
    with pytest.raises(PaperWireRefused, match="BRIDGE_INPUT_OR_WIRE_VALIDATION_FAILED"):
        review_file_to_runtime_wire(path, **(opts | {"kind": RuntimeKind.WASM}))
    unsafe_artifact = b"import os\nos.system('bad')\n"
    with pytest.raises(PaperWireRefused, match="BRIDGE_INPUT_OR_WIRE_VALIDATION_FAILED"):
        review_file_to_runtime_wire(path, **(opts | {
            "artifact": unsafe_artifact,
            "artifact_sha256": hashlib.sha256(unsafe_artifact).hexdigest(),
        }))
    path.write_bytes(ROWS_BYTES.replace(b",100,102,98,101,10", b",100,102,98,999,10"))
    with pytest.raises(PaperWireRefused, match="BRIDGE_INPUT_OR_WIRE_VALIDATION_FAILED"):
        review_file_to_runtime_wire(path, **opts)


def test_no_valid_frames_because_warmup_exceeds_history(tmp_path):
    path, opts = _prepare(tmp_path, minimum=4)
    with pytest.raises(PaperWireRefused, match="BRIDGE_INCOMPLETE_VALIDATION"):
        review_file_to_runtime_wire(path, **opts)


def test_max_frames_prevents_partial_success(tmp_path):
    path, opts = _prepare(tmp_path)
    with pytest.raises(PaperWireRefused, match="BRIDGE_MAX_FRAMES_EXCEEDED"):
        review_file_to_runtime_wire(path, **(opts | {"max_frames": 1}))
    for bad in (0, True, 2049):
        with pytest.raises(PaperWireRefused, match="BRIDGE_EXACT_TYPED_SCOPE_REQUIRED"):
            review_file_to_runtime_wire(path, **(opts | {"max_frames": bad}))


def test_readonly_no_network_no_worker_and_a6_still_blocks(tmp_path, monkeypatch):
    import naseri_markets.multilang_runtime_a1 as runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("BRIDGE_MUST_NOT_START_ANY_PROCESS_OR_NETWORK")

    monkeypatch.setattr(runtime, "_run_oci", forbidden)
    monkeypatch.setattr(runtime.MultiLanguageOfflineHost, "evaluate", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    path, opts = _prepare(tmp_path)
    before = path.read_bytes()
    report = review_file_to_runtime_wire(path, **opts)
    assert report.frames_prepared == 2
    assert path.read_bytes() == before
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")


def test_malformed_file_rejected_before_any_wire(tmp_path, monkeypatch):
    import naseri_markets.data_runtime_paper_wire_a1 as bridge

    path, opts = _prepare(tmp_path, raw=HEADER + ROWS[0] + ROWS[1] + ROWS[1])
    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("WIRE MUST NOT BE BUILT FROM INVALID FILE")

    monkeypatch.setattr(bridge, "prepare_framed_request", forbidden)
    with pytest.raises(PaperWireRefused, match="BRIDGE_INPUT_OR_WIRE_VALIDATION_FAILED"):
        review_file_to_runtime_wire(path, **opts)
    assert not called


def test_wrong_environment_ack_and_relative_source_are_denied(tmp_path, monkeypatch):
    path, opts = _prepare(tmp_path)
    with pytest.raises(PaperWireRefused, match="BRIDGE_EXPLICIT_NONPRODUCTION"):
        review_file_to_runtime_wire(path, **(opts | {"operator_ack": False}))
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(PaperWireRefused, match="BRIDGE_EXPLICIT_NONPRODUCTION"):
        review_file_to_runtime_wire(path, **opts)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(PaperWireRefused, match="BRIDGE_EXPLICIT_NONPRODUCTION"):
        review_file_to_runtime_wire(path, **opts)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(PaperWireRefused, match="BRIDGE_EXACT_TYPED_SCOPE_REQUIRED"):
        review_file_to_runtime_wire(Path("relative.csv"), **opts)
