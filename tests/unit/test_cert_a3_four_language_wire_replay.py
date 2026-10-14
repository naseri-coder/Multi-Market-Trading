"""CERT-A3: rederived four-language PAPER framing; zero Worker evaluation."""
from __future__ import annotations

import hashlib
import socket
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from naseri_markets.cert_a3_four_language_wire_replay import (
    CertA3Refused,
    RuntimeSourceSubmission,
    reproduce_four_runtime_wires,
)
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    CoreBinding,
    CoreEventType,
    CoreManifest,
    DataOrigin,
    SetupSpec,
)
from naseri_markets.data_a1_file_intake import inspect_historical_for_paper
from naseri_markets.data_runtime_paper_wire_a1 import review_file_to_runtime_wire
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

ROOT = Path(__file__).resolve().parents[2]
CSV_HEADER = b"open_at,close_at,open,high,low,close,volume\n"
CSV_ROWS = (
    b"2026-10-13T10:00:00Z,2026-10-13T10:15:00Z,100,102,98,101,10\n",
    b"2026-10-13T10:15:00Z,2026-10-13T10:30:00Z,101,104,99,103,11\n",
    b"2026-10-13T10:30:00Z,2026-10-13T10:45:00Z,103,105,100,102,12\n",
)
ARTIFACTS = (
    (RuntimeKind.PYTHON, "fixed.py",
     b"def evaluate(event):\n    return [{'kind': 'no_setup'}]\n"),
    (RuntimeKind.JAVASCRIPT, "fixed.js",
     b"function evaluate(event) { return []; }\n"),
    (RuntimeKind.TYPESCRIPT, "fixed.ts",
     b"function evaluate(event: unknown) { return []; }\n"),
    (RuntimeKind.WASM, "fixed.wasm", b"\x00asm\x01\x00\x00\x00"),
)


@pytest.fixture(autouse=True)
def _nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path: Path, *, parquet: bool = False):
    values = {
        "open_at": ["2026-10-13T10:00:00Z", "2026-10-13T10:15:00Z",
                    "2026-10-13T10:30:00Z"],
        "close_at": ["2026-10-13T10:15:00Z", "2026-10-13T10:30:00Z",
                     "2026-10-13T10:45:00Z"],
        "open": ["100", "101", "103"], "high": ["102", "104", "105"],
        "low": ["98", "99", "100"], "close": ["101", "103", "102"],
        "volume": ["10", "11", "12"],
    }
    path = tmp_path / ("history.parquet" if parquet else "history.csv")
    if parquet:
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")
        pq.write_table(
            pa.table({k: pa.array(v, type=pa.string()) for k, v in values.items()}),
            path, row_group_size=1,
        )
    else:
        path.write_bytes(CSV_HEADER + b"".join(CSV_ROWS))
    digest = _sha(path.read_bytes())
    instrument = Instrument(
        Market.CRYPTO, "declared_fixture", "ABCUSDT", "UTC", "USDT",
    )
    feed = FeedDefinition(
        "cert_a3_fixture_feed", instrument, "15m",
        CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + digest[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120, history_limit=128,
    )
    spec = HistoricalFileSpec(feed, digest, availability_lag_seconds=7,
                              max_rows=100)
    manifest = CoreManifest(
        "FixedA3ResearchCore", "1.0",
        (SetupSpec("fixture", "Review only; no strategy"),),
        frozenset({Market.CRYPTO}),
        frozenset({CoreEventType.CLOSED_CANDLE}),
        minimum_closed_candles=2,
    )
    binding = CoreBinding(
        "cert_a3_instance", "cert_a3_binding", instrument, "15m",
    )
    sources = tuple(RuntimeSourceSubmission(
        kind, name, raw, _sha(raw),
    ) for kind, name, raw in ARTIFACTS)
    return path, spec, manifest, binding, sources


def _review(path, spec, manifest, binding, sources, **kwargs):
    return reproduce_four_runtime_wires(
        ROOT, path, spec=spec, manifest=manifest, binding=binding,
        sources=sources, operator_ack=True, **kwargs,
    )


@pytest.mark.parametrize("parquet", [False, True])
def test_all_four_language_frames_recreated_from_actual_files(tmp_path, parquet):
    inputs = _fixture(tmp_path, parquet=parquet)
    report = _review(*inputs)
    assert report.dataset_sha256 == inputs[1].expected_sha256
    assert report.dataset_format == ("parquet" if parquet else "csv")
    assert report.rows_replayed == 3
    assert report.paper_core_inputs_prepared == 3
    assert len(report.language_traces) == 4
    assert [x.language for x in report.language_traces] == [
        "python", "javascript", "typescript", "wasm",
    ]
    assert all(x.validated_rows == 3 and x.warmup_rows == 1
               and x.frames_prepared == 2 for x in report.language_traces)
    assert len({x.transcript_sha256 for x in report.language_traces}) == 4
    assert all(len(x.transcript_sha256) == 64 and x.peak_frame_bytes > 100
               for x in report.language_traces)
    assert report == _review(*inputs)
    assert len(report.fingerprint_sha256) == 64
    assert report.status == "CERT_A3_FOUR_LANGUAGE_PAPER_WIRES_REPRODUCED_EXECUTION_DENIED"
    assert not report.independently_authenticated_market_source
    assert not report.independently_verified_runtime_host
    assert not report.actual_worker_executed
    assert not report.actual_strategy_behavior_equivalent
    assert not report.paper_strategy_executed
    assert not report.paper_order_sent
    assert not report.broker_order_sent
    assert not report.telegram_sent
    assert not report.worker_execution_authorized
    assert not report.quarantine_release_authorized
    assert not report.production_release_authorized
    for item in report.language_traces:
        assert not item.actual_worker_executed
        assert not item.actual_core_result_verified
        assert not item.broker_or_telegram_authorized


def test_submission_order_is_canonical_and_fingerprint_identical(tmp_path):
    inputs = _fixture(tmp_path)
    first = _review(*inputs)
    shuffled = (inputs[4][3], inputs[4][1], inputs[4][0], inputs[4][2])
    assert first == _review(*inputs[:4], shuffled)


def test_recompute_exact_claims_but_never_authenticate_them(tmp_path):
    path, spec, manifest, binding, submissions = _fixture(tmp_path)
    actual_data = inspect_historical_for_paper(
        path, sha256=spec.expected_sha256,
        market=spec.feed.instrument.market, provider=spec.feed.instrument.provider,
        symbol=spec.feed.instrument.symbol, timezone=spec.feed.instrument.timezone,
        quote_currency=spec.feed.instrument.quote_currency, timeframe=spec.feed.timeframe,
        event=spec.feed.event, price_basis=spec.feed.price_basis,
        volume_semantics=spec.feed.volume_semantics,
        availability_lag_seconds=spec.availability_lag_seconds,
        max_rows=spec.max_rows, operator_ack=True,
    )
    prior = tuple(replace(item, prior_wire_claim=review_file_to_runtime_wire(
        path, spec=spec, manifest=manifest, binding=binding, kind=item.kind,
        artifact_name=item.artifact_name, artifact=item.artifact,
        artifact_sha256=item.approved_sha256, operator_ack=True,
    )) for item in submissions)
    result = _review(
        path, spec, manifest, binding, prior, prior_data_claim=actual_data,
    )
    assert all(item.prior_claim_matched for item in result.language_traces)
    assert not result.independently_authenticated_market_source
    assert not result.worker_execution_authorized


@pytest.mark.parametrize("mutation", [
    "missing", "extra", "duplicate", "name", "bad_hash", "wrong_suffix",
    "oversized", "non_tuple", "non_kind",
])
def test_malformed_four_language_bundle_refused(tmp_path, mutation):
    inputs = _fixture(tmp_path)
    candidates = list(inputs[4])
    if mutation == "missing":
        candidates.pop()
    elif mutation == "extra":
        candidates.append(candidates[0])
    elif mutation == "duplicate":
        candidates[3] = candidates[0]
    elif mutation == "name":
        candidates[1] = replace(candidates[1], artifact_name="../bad.js")
    elif mutation == "bad_hash":
        candidates[1] = replace(candidates[1], approved_sha256="a" * 64)
    elif mutation == "wrong_suffix":
        candidates[1] = replace(candidates[1], artifact_name="bad.py")
    elif mutation == "oversized":
        candidates[1] = replace(candidates[1], artifact=b"a" * (128 * 1024 + 1))
    elif mutation == "non_kind":
        candidates[1] = replace(candidates[1], kind="javascript")
    if mutation == "non_tuple":
        candidates = tuple(candidates)
        candidates = list(candidates)
    with pytest.raises(CertA3Refused):
        _review(*inputs[:4], candidates if mutation == "non_tuple" else tuple(candidates))


def test_mutated_data_bytes_rejected(tmp_path):
    inputs = _fixture(tmp_path)
    path = inputs[0]
    path.write_bytes(path.read_bytes().replace(b",103,105,100,102,12",
                                               b",103,105,100,104,12"))
    with pytest.raises(CertA3Refused, match="CERT_A3_DIRECT_DATA_REPLAY_REFUSED"):
        _review(*inputs)


def test_altered_prior_wire_claim_cannot_fake_execution(tmp_path):
    inputs = _fixture(tmp_path)
    path, spec, manifest, binding, subs = inputs
    item = subs[0]
    prior = review_file_to_runtime_wire(
        path, spec=spec, manifest=manifest, binding=binding, kind=item.kind,
        artifact_name=item.artifact_name, artifact=item.artifact,
        artifact_sha256=item.approved_sha256, operator_ack=True,
    )
    forged = replace(item, prior_wire_claim=replace(prior, worker_executed=True))
    with pytest.raises(CertA3Refused, match="CERT_A3_PRIOR_WIRE_CLAIM_NOT_REPRODUCED"):
        _review(path, spec, manifest, binding, (forged, *subs[1:]))


def test_invalid_binding_and_bad_manifest_rejected(tmp_path):
    path, spec, manifest, binding, subs = _fixture(tmp_path)
    other_instrument = Instrument(
        Market.CRYPTO, "declared_fixture", "OTHERUSDT", "UTC", "USDT",
    )
    mismatch = CoreBinding("other", "other", other_instrument, "15m")
    with pytest.raises(CertA3Refused, match="CERT_A3_DATA_IDENTITY_DRIFT"):
        _review(path, spec, manifest, mismatch, subs)
    wrong_manifest = CoreManifest(
        "OtherManifest", "1.0",
        (SetupSpec("fixture", "Other"),), frozenset({Market.FOREX}),
        frozenset({CoreEventType.CLOSED_CANDLE}), minimum_closed_candles=2,
    )
    with pytest.raises(CertA3Refused, match="CERT_A3_RUNTIME_WIRE_REPLAY_REFUSED"):
        _review(path, spec, wrong_manifest, binding, subs)


def test_operator_guard_and_row_limit(tmp_path, monkeypatch):
    inputs = _fixture(tmp_path)
    with pytest.raises(CertA3Refused, match="CERT_A3_EXPLICIT_NONPRODUCTION"):
        reproduce_four_runtime_wires(
            ROOT, inputs[0], spec=inputs[1], manifest=inputs[2],
            binding=inputs[3], sources=inputs[4], operator_ack=False,
        )
    with pytest.raises(CertA3Refused, match="CERT_A3_BOUNDED_EXACT_TYPED"):
        _review(
            inputs[0], replace(inputs[1], max_rows=2049),
            inputs[2], inputs[3], inputs[4],
        )
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(CertA3Refused, match="CERT_A3_EXPLICIT_NONPRODUCTION"):
        _review(*inputs)


def test_no_network_process_or_worker_execution(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("CERT_A3_MUST_NOT_USE_NETWORK_OR_RUN_USER_CODE")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    inputs = _fixture(tmp_path)
    report = _review(*inputs)
    assert all(not r.actual_worker_executed for r in report.language_traces)
    assert not report.worker_execution_authorized
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
