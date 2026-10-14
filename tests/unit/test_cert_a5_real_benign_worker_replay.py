"""CERT-A5: execute ONLY literal harmless fixtures on DATA-A1 replay events.

This is not a sandbox or an execution grant. Never replace these sources
with uploaded strategy code or run the suite on a production machine.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    CoreBinding,
    CoreEventType,
    CoreManifest,
    DataOrigin,
    SetupSpec,
    _canonical,
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
from naseri_markets.multilang_runtime_a1 import (
    MultiLanguageOfflineHost,
    RuntimeKind,
    prepare_framed_request,
)
from naseri_markets.secure_plugin_runtime_v1 import (
    SecurePluginRefused,
    parse_core_result,
)

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "scripts/runtime_a2_worker.py"
HEADER = b"open_at,close_at,open,high,low,close,volume\n"
ROWS = (
    b"2026-10-13T10:00:00Z,2026-10-13T10:15:00Z,100,102,98,101,10\n",
    b"2026-10-13T10:15:00Z,2026-10-13T10:30:00Z,101,104,99,103,11\n",
    b"2026-10-13T10:30:00Z,2026-10-13T10:45:00Z,103,105,100,102,12\n",
)

# These three strings are reviewed, benign fixtures committed in this test.
# They inspect candle count only; no broker, network, filesystem or imports.
PY_SOURCE = (
    b"def evaluate(event):\n"
    b"    return [{'decision_id':'bar_'+str(len(event['candles'])),"
    b"'kind':'no_setup'}]\n"
)
JS_SOURCE = (
    b"function evaluate(event) { return [{decision_id:"
    b" 'bar_' + event.candles.length, kind: 'no_setup'}]; }\n"
)
TS_SOURCE = (
    b"function evaluate(event: any): object[] { return [{decision_id:"
    b" 'bar_' + event.candles.length, kind: 'no_setup'}]; }\n"
)


@pytest.fixture(autouse=True)
def _fixture_only_gate():
    if os.environ.get("MMT_PRODUCTION") == "1":
        pytest.fail("CERT_A5_PRODUCTION_REFUSED")
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_CERT_A5_FIXED_FIXTURES_ONLY") != "1"):
        pytest.skip("CERT-A5 explicitly opt-in; committed harmless fixtures only")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _case(tmp_path: Path, parquet: bool):
    path = tmp_path / ("history.parquet" if parquet else "history.csv")
    if parquet:
        import pyarrow as pa
        import pyarrow.parquet as pq

        columns = {key: [] for key in (
            "open_at", "close_at", "open", "high", "low", "close", "volume"
        )}
        for row in ROWS:
            for name, value in zip(
                columns, row.decode("ascii").strip().split(","), strict=True
            ):
                columns[name].append(value)
        pq.write_table(
            pa.table({
                key: pa.array(values, type=pa.string())
                for key, values in columns.items()
            }), path, row_group_size=1,
        )
    else:
        path.write_bytes(HEADER + b"".join(ROWS))

    digest = _sha(path.read_bytes())
    instrument = Instrument(Market.CRYPTO, "fixture_provider",
                            "ABCUSDT", "UTC", "USDT")
    feed = FeedDefinition(
        "cert_a5_feed", instrument, "15m", CoreEventType.CLOSED_CANDLE,
        DataOrigin.REPLAY, "hist_" + digest[:40], PriceBasis.TRADE,
        VolumeSemantics.TRADED, max_latency_seconds=120, history_limit=128,
    )
    spec = HistoricalFileSpec(
        feed, digest, availability_lag_seconds=7, max_rows=100,
    )
    manifest = CoreManifest(
        "FixedA5ResearchCore", "1.0",
        (SetupSpec("fixture", "No order capability; harmless result"),),
        frozenset({Market.CRYPTO}),
        frozenset({CoreEventType.CLOSED_CANDLE}),
        minimum_closed_candles=2,
    )
    binding = CoreBinding(
        "cert_a5_instance", "cert_a5_binding", instrument, "15m",
    )
    engine = OfflineMarketDataEngine(enabled=True)
    engine.register_feed(feed)
    engine.subscribe(feed.feed_id, manifest, binding)
    events = []
    approved = validate_historical_file(path, spec)
    for packet in approved.packets():
        outcome = engine.ingest(packet)
        if outcome.status is PacketStatus.ACCEPTED:
            assert len(outcome.deliveries) == 1
            events.append(outcome.deliveries[0].event)
        else:
            assert outcome.status is PacketStatus.WARMING
    assert len(events) == 2
    assert [len(event.candles) for event in events] == [2, 3]
    assert all(event.origin is DataOrigin.REPLAY for event in events)
    assert not engine.state(feed.feed_id).quarantined
    return path, spec, manifest, binding, tuple(events)


def _wasm_source(events) -> bytes:
    # Wasm fixture has no imports or WASI. Branch by exact canonical event
    # length for the two pinned input shapes, not by a trading heuristic.
    import wasmtime

    lengths = [
        len(json.dumps(
            _canonical(event), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")) for event in events
    ]
    assert lengths[0] < lengths[1]
    threshold = (lengths[0] + lengths[1]) // 2

    def payload(count):
        wire = json.dumps(
            [{"decision_id": f"bar_{count}", "kind": "no_setup"}],
            separators=(",", ":"),
        ).encode("ascii")
        return "".join(f"\\{byte:02x}" for byte in wire), len(wire)

    first, n2 = payload(2)
    second, n3 = payload(3)
    addr2 = (4096 << 32) | n2
    addr3 = (8192 << 32) | n3
    wat = (
        '(module (memory (export "memory") 1) '
        f'(data (i32.const 4096) "{first}") '
        f'(data (i32.const 8192) "{second}") '
        '(func (export "evaluate") (param i32 i32) (result i64) '
        f'local.get 1 i32.const {threshold} i32.gt_u '
        f'if (result i64) i64.const {addr3} '
        f'else i64.const {addr2} end))'
    )
    return bytes(wasmtime.wat2wasm(wat))


def _sources(events):
    return (
        (RuntimeKind.PYTHON, "fixed.py", PY_SOURCE),
        (RuntimeKind.JAVASCRIPT, "fixed.js", JS_SOURCE),
        (RuntimeKind.TYPESCRIPT, "fixed.ts", TS_SOURCE),
        (RuntimeKind.WASM, "fixed.wasm", _wasm_source(events)),
    )


def _run(kind: RuntimeKind, frame: bytes) -> subprocess.CompletedProcess:
    # Subprocesses are restricted to these literal fixtures, never uploads.
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "NODE_PATH": os.environ.get("NODE_PATH", ""),
        "MMT_RUNTIME_KIND": kind.value,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, str(WORKER)], input=frame,
        capture_output=True, check=False,
        env=env, timeout=12,
    )


@pytest.mark.parametrize("parquet", [False, True])
def test_real_four_interpreters_read_causal_csv_or_parquet_replay(tmp_path, parquet):
    path, spec, manifest, binding, events = _case(tmp_path, parquet)
    assert _sha(path.read_bytes()) == spec.expected_sha256
    assert WORKER.is_file()
    outcome_hashes = {}
    for kind, filename, source in _sources(events):
        for event in events:
            framed = prepare_framed_request(
                kind, manifest, event, artifact_name=filename,
                artifact=source, approved_sha256=_sha(source),
            )
            process = _run(kind, framed)
            assert process.returncode == 0, (kind.value, process.returncode)
            assert process.stderr == b""
            result = parse_core_result(process.stdout, manifest, event)
            assert result.core_id == manifest.core_id
            assert result.binding_id == binding.binding_id
            assert result.input_digest == event.input_digest
            assert len(result.decisions) == 1
            decision = result.decisions[0]
            assert decision.kind.value == "no_setup"
            assert decision.decision_id == f"bar_{len(event.candles)}"
            # Compare independently executed *fixture* decisions, not
            # interpreter wire hashes or strategy profitability.
            outcome_hashes.setdefault(event.input_digest, set()).add(
                (decision.decision_id, decision.kind.value)
            )
    assert len(outcome_hashes) == 2
    assert all(len(decisions) == 1 for decisions in outcome_hashes.values())
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]
    assert all(
        state == "WORKER_NOT_INSTALLED"
        for state in MultiLanguageOfflineHost().status().values()
    )


def test_corrupted_actual_replay_frame_is_refused_without_output(tmp_path):
    _, _, manifest, _, events = _case(tmp_path, False)
    framed = prepare_framed_request(
        RuntimeKind.PYTHON, manifest, events[0],
        artifact_name="fixed.py", artifact=PY_SOURCE,
        approved_sha256=_sha(PY_SOURCE),
    )
    poisoned = framed[:4] + bytes([framed[4] ^ 1]) + framed[5:]
    result = _run(RuntimeKind.PYTHON, poisoned)
    assert result.returncode != 0
    assert result.stdout == b""


def test_forged_worker_identity_is_rejected_by_trusted_parser(tmp_path):
    _, _, manifest, _, events = _case(tmp_path, False)
    frame = prepare_framed_request(
        RuntimeKind.PYTHON, manifest, events[0],
        artifact_name="fixed.py", artifact=PY_SOURCE,
        approved_sha256=_sha(PY_SOURCE),
    )
    result = _run(RuntimeKind.PYTHON, frame)
    assert result.returncode == 0
    forged = json.loads(result.stdout)
    forged["binding_id"] = "forged_binding"
    with pytest.raises(SecurePluginRefused):
        parse_core_result(json.dumps(forged).encode("ascii"), manifest, events[0])
