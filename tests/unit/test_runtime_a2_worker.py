"""Real benign Python/JS/TS/WASM Worker execution, NOT sandbox certification."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle,
    CoreBinding,
    CoreEventType,
    CoreInput,
    DataOrigin,
)
from naseri_markets.multilang_runtime_a1 import (
    RuntimeKind,
    prepare_framed_request,
)
from naseri_markets.secure_plugin_runtime_v1 import parse_core_result

CORE = OfflineContractFixture()
WORKER = Path(__file__).resolve().parents[2] / "scripts/runtime_a2_worker.py"
PY_FIXTURE = (
    b"def evaluate(event):\n"
    b"    return [{'decision_id': 'python_demo', 'kind': 'no_setup'}]\n"
)
JS_FIXTURE = (
    b"function evaluate(event) { "
    b"return [{decision_id: 'javascript_demo', kind: 'no_setup'}]; }\n"
)
TS_FIXTURE = (
    b"function evaluate(event: unknown): object[] { "
    b"return [{decision_id: 'typescript_demo', kind: 'no_setup'}]; }\n"
)


def _event() -> CoreInput:
    observed = datetime(2026, 10, 13, 10, tzinfo=UTC)
    binding = CoreBinding(
        "instance_synthetic", "binding_synthetic",
        Instrument(Market.CRYPTO, "fixture_provider", "ABCUSD", "UTC", "USD"),
        "15m",
    )
    candles = (
        ClosedCandle(
            observed, observed + timedelta(minutes=15),
            Decimal("100"), Decimal("102"), Decimal("98"),
            Decimal("100"), Decimal("10"),
        ),
        ClosedCandle(
            observed + timedelta(minutes=15),
            observed + timedelta(minutes=30),
            Decimal("100"), Decimal("108"), Decimal("99"),
            Decimal("106"), Decimal("11"),
        ),
    )
    return CoreInput(
        CORE.manifest.core_id, CORE.manifest.core_version, binding,
        CoreEventType.CLOSED_CANDLE, candles[-1].close_at,
        DataOrigin.SYNTHETIC, "reviewed_static_fixture", candles,
    )


def _wasm_fixture() -> bytes:
    wasmtime = pytest.importorskip("wasmtime")
    outcome = b'[{"decision_id":"wasm_demo","kind":"no_setup"}]'
    literal = "".join(f"\\{ch:02x}" for ch in outcome)
    address = (4096 << 32) + len(outcome)
    return bytes(wasmtime.wat2wasm(
        '(module (memory (export "memory") 1) '
        f'(data (i32.const 4096) "{literal}") '
        '(func (export "evaluate") (param i32 i32) (result i64) '
        f'i64.const {address}))'
    ))


def benign_fixtures():
    return (
        (RuntimeKind.PYTHON, "sample.py", PY_FIXTURE, "python_demo"),
        (RuntimeKind.JAVASCRIPT, "sample.js", JS_FIXTURE, "javascript_demo"),
        (RuntimeKind.TYPESCRIPT, "sample.ts", TS_FIXTURE, "typescript_demo"),
        (RuntimeKind.WASM, "sample.wasm", _wasm_fixture(), "wasm_demo"),
    )


def _frame(kind, filename, data):
    return prepare_framed_request(
        kind, CORE.manifest, _event(), artifact_name=filename,
        artifact=data, approved_sha256=hashlib.sha256(data).hexdigest(),
    )


def _run(kind, framed):
    env = dict(os.environ)
    env["MMT_RUNTIME_KIND"] = kind.value
    candidate = env.get("MMT_A2_IMAGE")
    argv = [sys.executable, str(WORKER)]
    if candidate:
        # Only committed harmless fixture input. Normal Docker is NOT runsc.
        argv = [
            "docker", "run", "--rm", "-i", "--pull=never",
            "--network=none", "--ipc=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=32", "--memory=128m", "--cpus=0.5",
            "--user=65534:65534",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
            "--env=MMT_RUNTIME_KIND=" + kind.value, candidate,
        ]
    return subprocess.run(
        argv, input=framed, capture_output=True,
        env=env, timeout=30 if candidate else 9, check=False,
    )


def test_exact_four_language_benign_fixture_roundtrips():
    assert WORKER.is_file()
    for kind, filename, source, decision in benign_fixtures():
        p = _run(kind, _frame(kind, filename, source))
        assert p.returncode == 0, (kind, p.returncode, p.stderr[:256])
        typed = parse_core_result(p.stdout, CORE.manifest, _event())
        assert typed.decisions[0].decision_id == decision
        assert typed.decisions[0].kind.value == "no_setup"
        assert len(typed.decisions) == 1


@pytest.mark.parametrize("kind,filename,source", [
    (RuntimeKind.PYTHON, "x.py", PY_FIXTURE),
    (RuntimeKind.JAVASCRIPT, "x.js", JS_FIXTURE),
    (RuntimeKind.TYPESCRIPT, "x.ts", TS_FIXTURE),
])
def test_corrupted_frame_digest_denied_without_output(kind, filename, source):
    framed = _frame(kind, filename, source)
    poisoned = framed[:4] + bytes([framed[4] ^ 1]) + framed[5:]
    p = _run(kind, poisoned)
    assert p.returncode != 0
    assert p.stdout == b""


def test_manifest_and_event_digest_tamper_denied():
    framed = _frame(RuntimeKind.PYTHON, "x.py", PY_FIXTURE)
    n = int.from_bytes(framed[:4], "big")
    req = json.loads(framed[4+n:])
    req["manifest_digest"] = "0" * 64
    poisoned = framed[:4+n] + json.dumps(req).encode()
    out = _run(RuntimeKind.PYTHON, poisoned)
    assert out.returncode != 0 and not out.stdout
    req = json.loads(framed[4+n:])
    req["event"]["binding"]["binding_id"] = "forged_binding"
    poisoned = framed[:4+n] + json.dumps(req).encode()
    out = _run(RuntimeKind.PYTHON, poisoned)
    assert out.returncode != 0 and not out.stdout


def test_language_confusion_refused():
    framed = _frame(RuntimeKind.PYTHON, "x.py", PY_FIXTURE)
    p = _run(RuntimeKind.JAVASCRIPT, framed)
    assert p.returncode != 0 and not p.stdout


def test_too_large_frame_and_duplicate_json_refused():
    framed = _frame(RuntimeKind.PYTHON, "x.py", PY_FIXTURE)
    p = _run(RuntimeKind.PYTHON, framed + b"x" * (196609))
    assert p.returncode != 0 and p.stdout == b""
    n = int.from_bytes(framed[:4], "big")
    malformed = framed[:4+n] + framed[4+n:-1] + b',"protocol":"RUNTIME_A1_FRAMED_V1"}'
    p = _run(RuntimeKind.PYTHON, malformed)
    assert p.returncode != 0 and not p.stdout


def test_unsupported_kind_refused():
    p = subprocess.run(
        [sys.executable, str(WORKER)], input=b"any",
        env={"PATH": os.environ.get("PATH", ""), "MMT_RUNTIME_KIND": "mt5"},
        capture_output=True, timeout=4, check=False,
    )
    assert p.returncode != 0 and p.stdout == b""


def test_wasm_imports_denied():
    wasmtime = pytest.importorskip("wasmtime")
    malicious = bytes(wasmtime.wat2wasm(
        '(module (import "host" "unsafe" (func)) '
        '(memory (export "memory") 1) '
        '(func (export "evaluate") (param i32 i32) (result i64) i64.const 0))'
    ))
    p = _run(RuntimeKind.WASM, _frame(RuntimeKind.WASM, "x.wasm", malicious))
    assert p.returncode != 0 and p.stdout == b""


def test_no_binary_or_user_language_is_registered_by_default():
    from naseri_markets.multilang_runtime_a1 import MultiLanguageOfflineHost
    assert all(state == "WORKER_NOT_INSTALLED"
               for state in MultiLanguageOfflineHost().status().values())
