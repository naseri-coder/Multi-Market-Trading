"""CERT-A4: four synthetic CoreResult claim streams; NO language executes."""
from __future__ import annotations

import hashlib
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from naseri_markets.cert_a3_four_language_wire_replay import (
    RuntimeSourceSubmission,
    reproduce_four_runtime_wires,
)
from naseri_markets.cert_a4_synthetic_result_contract import (
    CertA4Refused,
    SyntheticResultTrace,
    review_synthetic_core_result_traces,
)
from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.core_api_v1 import (
    CoreBinding,
    CoreDecision,
    CoreEventType,
    CoreManifest,
    CoreResult,
    DataOrigin,
    DecisionKind,
    SetupSpec,
)
from naseri_markets.historical_data_loader_a1 import (
    HistoricalFileSpec,
    validate_historical_file,
)
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition,
    OfflineMarketDataEngine,
    PacketStatus,
    PriceBasis,
    VolumeSemantics,
)
from naseri_markets.multilang_runtime_a1 import RuntimeKind
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)

ROOT = Path(__file__).resolve().parents[2]
ROWS = (
    b"2026-10-13T10:00:00Z,2026-10-13T10:15:00Z,100,102,98,101,10\n",
    b"2026-10-13T10:15:00Z,2026-10-13T10:30:00Z,101,104,99,103,11\n",
    b"2026-10-13T10:30:00Z,2026-10-13T10:45:00Z,103,105,100,102,12\n",
)
LANGUAGES = (
    (RuntimeKind.PYTHON, "fixed.py", b"def evaluate(e): return []\n"),
    (RuntimeKind.JAVASCRIPT, "fixed.js", b"function evaluate(e) { return []; }\n"),
    (RuntimeKind.TYPESCRIPT, "fixed.ts", b"function evaluate(e: unknown) { return []; }\n"),
    (RuntimeKind.WASM, "fixed.wasm", b"\x00asm\x01\x00\x00\x00"),
)


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _case(tmp_path, *, parquet=False):
    path = tmp_path / ("candles.parquet" if parquet else "candles.csv")
    if not parquet:
        path.write_bytes(b"open_at,close_at,open,high,low,close,volume\n" + b"".join(ROWS))
    else:
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")
        columns = {
            "open_at": [], "close_at": [], "open": [], "high": [],
            "low": [], "close": [], "volume": [],
        }
        for row in ROWS:
            for name, value in zip(columns, row.decode().strip().split(","), strict=True):
                columns[name].append(value)
        pq.write_table(pa.table({
            name: pa.array(values, type=pa.string())
            for name, values in columns.items()
        }), path, row_group_size=1)
    digest = _sha(path.read_bytes())
    instrument = Instrument(
        Market.CRYPTO, "declared_fixture", "ABCUSDT", "UTC", "USDT",
    )
    feed = FeedDefinition(
        "cert_a4_sample_feed", instrument, "15m",
        CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + digest[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120, history_limit=128,
    )
    spec = HistoricalFileSpec(feed, digest, availability_lag_seconds=2, max_rows=100)
    manifest = CoreManifest(
        "FixedA4ResearchCore", "1.0",
        (SetupSpec("fixture", "Only synthetic output checks"),),
        frozenset({Market.CRYPTO}), frozenset({CoreEventType.CLOSED_CANDLE}),
        minimum_closed_candles=2,
    )
    binding = CoreBinding("a4_instance", "a4_binding", instrument, "15m")
    sources = tuple(RuntimeSourceSubmission(k, name, raw, _sha(raw))
                    for k, name, raw in LANGUAGES)
    approved = validate_historical_file(path, spec)
    engine = OfflineMarketDataEngine(enabled=True)
    engine.register_feed(feed)
    engine.subscribe(feed.feed_id, manifest, binding)
    events = []
    for packet in approved.packets():
        delivery = engine.ingest(packet)
        if delivery.status is PacketStatus.ACCEPTED:
            events.append(delivery.deliveries[0].event)
    assert len(events) == 2
    results = []
    for index, event in enumerate(events):
        decisions = (
            (CoreDecision("fixture_none", DecisionKind.NO_SETUP),)
            if index == 0 else (
                CoreDecision(
                    "fixture_entry", DecisionKind.ENTRY_INTENT,
                    setup_id="fixture", direction=Direction.LONG,
                    entry=Decimal("100"), stop=Decimal("95"),
                    targets=(Decimal("110"),),
                    expires_at=event.observed_at + timedelta(minutes=15),
                ),
            )
        )
        results.append(CoreResult(
            event.core_id, event.core_version,
            binding.instance_id, binding.binding_id,
            event.observed_at, event.input_digest, decisions,
        ))
    claims = tuple(
        SyntheticResultTrace(kind, tuple(results)) for kind in RuntimeKind
    )
    return path, spec, manifest, binding, sources, claims


def _run(case, **kwargs):
    path, spec, manifest, binding, sources, claims = case
    return review_synthetic_core_result_traces(
        ROOT, path, spec=spec, manifest=manifest, binding=binding,
        sources=sources, claims=claims, operator_ack=True, **kwargs,
    )


@pytest.mark.parametrize("parquet", [False, True])
def test_local_csv_parquet_four_claims_match_contract_but_not_execution(tmp_path, parquet):
    case = _case(tmp_path, parquet=parquet)
    report = _run(case)
    assert report.dataset_sha256 == case[1].expected_sha256
    assert report.ready_bars_reviewed == 2
    assert report.result_claims_checked == 8
    assert report.decision_shapes_checked == 8
    assert report.entry_intent_shapes_checked == 4
    assert report.synthetic_claims_matched
    assert not report.prior_a3_claim_reproduced
    assert len(report.decision_trace_sha256) == 64
    assert len(report.report_fingerprint_sha256) == 64
    assert report == _run(case)
    assert report.status == "CERT_A4_SYNTHETIC_RESULT_CONTRACT_REPLAY_ONLY_ALL_EXECUTION_DENIED"
    assert not report.independent_claim_origins_authenticated
    assert not report.actual_runtime_results_authenticated
    assert not report.strategy_equivalence_proven
    assert not report.paper_strategy_executed
    assert not report.paper_order_sent
    assert not report.broker_order_sent
    assert not report.telegram_sent
    assert not report.worker_execution_authorized
    assert not report.quarantine_release_authorized
    assert not report.production_release_authorized
    assert sorted(p.name for p in tmp_path.iterdir()) == [case[0].name]


def test_previous_a3_claim_recomputed_not_trusted(tmp_path):
    case = _case(tmp_path)
    expected = reproduce_four_runtime_wires(
        ROOT, case[0], spec=case[1], manifest=case[2],
        binding=case[3], sources=case[4], operator_ack=True,
    )
    actual = _run(case, prior_a3_claim=expected)
    assert actual.prior_a3_claim_reproduced
    with pytest.raises(CertA4Refused, match="CERT_A4_PRIOR_A3_CLAIM_NOT_REPRODUCED"):
        _run(case, prior_a3_claim=replace(expected, worker_execution_authorized=True))


@pytest.mark.parametrize("failure", [
    "wrong_digest", "stale_timestamp", "wrong_binding", "reordered",
    "wrong_core", "wrong_instance", "wrong_version", "unknown_setup",
])
def test_bad_result_provenance_is_rejected(tmp_path, failure):
    case = _case(tmp_path)
    sample = list(case[5])
    result = sample[1].results[1]
    if failure == "wrong_digest":
        result = replace(result, input_digest="1" * 64)
    elif failure == "stale_timestamp":
        result = replace(result, observed_at=result.observed_at - timedelta(minutes=15))
    elif failure == "wrong_binding":
        result = replace(result, binding_id="forged_binding")
    elif failure == "wrong_core":
        result = replace(result, core_id="FakeResearchCore")
    elif failure == "wrong_instance":
        result = replace(result, instance_id="forged_instance")
    elif failure == "wrong_version":
        result = replace(result, core_version="2.0")
    elif failure == "unknown_setup":
        result = replace(result, decisions=(
            replace(result.decisions[0], setup_id="other_setup"),))
    if failure == "reordered":
        sample[1] = replace(
            sample[1], results=tuple(reversed(sample[1].results)),
        )
    else:
        sample[1] = replace(sample[1], results=(sample[1].results[0], result))
    with pytest.raises(CertA4Refused, match="CERT_A4_RESULT_CONTRACT_OR_PROVENANCE_REFUSED"):
        _run((*case[:5], tuple(sample)))


def test_a_broken_entry_geometry_forged_post_init_is_rechecked(tmp_path):
    case = _case(tmp_path)
    entries = list(case[5])
    original = entries[2].results[1]
    dirty = replace(original, decisions=(replace(original.decisions[0]),))
    object.__setattr__(dirty.decisions[0], "stop", Decimal("120"))
    entries[2] = replace(entries[2], results=(entries[2].results[0], dirty))
    with pytest.raises(CertA4Refused, match="CERT_A4_RESULT_CONTRACT_OR_PROVENANCE_REFUSED"):
        _run((*case[:5], tuple(entries)))


@pytest.mark.parametrize("difference", [
    "different_decision_id", "different_valid_target", "no_setup_instead",
])
def test_four_claimed_languages_must_agree_without_asserting_runtime_equivalence(
    tmp_path, difference,
):
    case = _case(tmp_path)
    traces = list(case[5])
    last = traces[0].results[1]
    if difference == "different_decision_id":
        changed = replace(last.decisions[0], decision_id="different_id")
        result = replace(last, decisions=(changed,))
    elif difference == "different_valid_target":
        changed = replace(last.decisions[0], targets=(Decimal("120"),))
        result = replace(last, decisions=(changed,))
    else:
        result = replace(last, decisions=(
            CoreDecision("fixture_none_other", DecisionKind.NO_SETUP),))
    traces[0] = replace(traces[0], results=(traces[0].results[0], result))
    with pytest.raises(CertA4Refused, match="CERT_A4_SYNTHETIC_LANGUAGE_DECISIONS_DISAGREE"):
        _run((*case[:5], tuple(traces)))


@pytest.mark.parametrize("change", [
    "missing", "duplicate", "non_tuple", "mismatched_length",
    "fake_claim_origin", "invalid_kind",
])
def test_synthetic_result_bundle_exactness(tmp_path, change):
    case = _case(tmp_path)
    traces = list(case[5])
    if change == "missing":
        traces.pop()
    elif change == "duplicate":
        traces[2] = traces[0]
    elif change == "mismatched_length":
        traces[0] = replace(traces[0], results=traces[0].results[:1])
    elif change == "fake_claim_origin":
        traces[0] = replace(traces[0], claim_origin="WORKER_PROVEN")
    elif change == "invalid_kind":
        traces[0] = replace(traces[0], kind="python")
    if change == "non_tuple":
        shaped = traces
    else:
        shaped = tuple(traces)
    with pytest.raises(CertA4Refused):
        _run((*case[:5], shaped))


def test_data_hash_mutation_rejected_and_cannot_publish(tmp_path):
    case = _case(tmp_path)
    path = case[0]
    path.write_bytes(path.read_bytes().replace(b",101,10", b",102,10", 1))
    with pytest.raises(CertA4Refused, match="CERT_A4_FOUR_LANGUAGE_REPLAY_REFUSED"):
        _run(case)


def test_guard_fails_closed_on_production_and_missing_ack(tmp_path, monkeypatch):
    case = _case(tmp_path)
    with pytest.raises(CertA4Refused, match="CERT_A4_EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        review_synthetic_core_result_traces(
            ROOT, case[0], spec=case[1], manifest=case[2],
            binding=case[3], sources=case[4], claims=case[5],
        )
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(CertA4Refused, match="CERT_A4_EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        _run(case)


def test_no_process_socket_worker_or_broker_and_unchanged_a6(tmp_path, monkeypatch):
    case = _case(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("CERT_A4_MUST_NOT_LAUNCH_OR_CONNECT")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    report = _run(case)
    assert report.entry_intent_shapes_checked == 4
    assert not report.paper_order_sent
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
