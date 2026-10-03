from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

from research_layer.phase_4_2_41_88f.contract import SYMBOLS, TIMEFRAMES, assert_contract

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/legacy/research_layer/phase_4_2_41_88f/live_shadow.py.txt"
EXPECTED = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "SOLUSDT",
    "TRXUSDT",
    "HYPEUSDT",
    "ZECUSDT",
    "DOGEUSDT",
    "XMRUSDT",
)


def fixture():
    return json.loads((ROOT / "tests/fixtures/research/synthetic_manifest.json").read_text())


def archived_tree():
    raw = ARCHIVE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "c420570012286333011a4626cfd964033000e04be2a72a8145c1047ef14cb16a"
    )
    assert "d932afdc9d16de3781747c0c53a3e085e4720a41fd4d5dde41ae3add6d169b3b" in raw.decode()
    return ast.parse(raw.decode()[raw.decode().index("from __future__") :])


def scheduler():
    cls = next(
        n for n in archived_tree().body if isinstance(n, ast.ClassDef) and n.name == "ForwardShadow"
    )
    return next(
        n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "process_due_scans"
    )


def call_names(node):
    return [ast.unparse(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)]


def test_contract_and_symbol_universe_frozen():
    assert_contract()
    assert SYMBOLS == EXPECTED
    assert TIMEFRAMES == ("15m", "1h")
    assert (ROOT / "research_layer/phase_4_2_41_88f/statistics.py").read_bytes() == (
        ROOT / "research_layer/phase_4_2_41_88e/statistics.py"
    ).read_bytes()


def test_manifest_hashes_and_no_backfill_gates():
    manifest = fixture()["88f_manifest"]
    assert manifest["phase"] == "4.2.41.88F"
    assert tuple(manifest["symbols"]) == EXPECTED
    assert manifest["scan_grace_seconds"] == 90
    assert manifest["no_backfill"] is True
    assert all(
        manifest["rules"][key] is False
        for key in (
            "backfill",
            "production_write",
            "telegram_publication",
            "economic_analysis_before_end",
        )
    )
    assert all(
        hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
        for p, h in manifest["source_hashes"].items()
    )
    assert manifest["source_hashes"]


def test_initialization_is_development_only_and_excludes_interrupted_88e():
    data = fixture()
    initialization = data["88f_initialization"]
    assert len(initialization["cases"]) == 72
    assert len({c["candidate_identity"] for c in initialization["cases"]}) == 72
    assert initialization["source_role"] == "MODEL_DEVELOPMENT_INITIALIZATION"
    assert initialization["excluded_sources"]["phase_88e_interrupted_forward"] == 0
    assert data["88f_manifest"]["phase88e_interruption"]["forward_rows_imported"] == 0


def test_stale_slot_is_marked_missed_and_never_scanned():
    node = scheduler()
    loops = [n for n in node.body if isinstance(n, ast.While)]
    assert len(loops) == 1
    guard = next(n for n in loops[0].body if isinstance(n, ast.If))
    policy = next(n for n in guard.body if isinstance(n, ast.If))
    assert ast.unparse(policy.test) == "timedelta(0) <= age <= grace"
    overdue = policy.orelse[0]
    assert isinstance(overdue, ast.If)
    assert ast.unparse(overdue.test) == "age > grace"
    assert "self.scan" not in call_names(overdue)
    detail = next(n for n in overdue.body if isinstance(n, ast.Assign))
    values = dict(zip((k.value for k in detail.value.keys), detail.value.values))
    assert isinstance(values["backfill_performed"], ast.Constant)
    assert values["backfill_performed"].value is False
    calls = [n for n in ast.walk(overdue) if isinstance(n, ast.Call)]
    record = next(n for n in calls if ast.unparse(n.func) == "self.store.record_scan")
    event = next(n for n in calls if ast.unparse(n.func) == "self.store.event")
    assert record.args[1].value == "MISSED_NOT_BACKFILLED"
    assert event.args[1].value == "MISSED_SCAN_NOT_BACKFILLED"
    assert ast.unparse(record.args[2]) == ast.unparse(event.args[2]) == "detail"


def test_due_slot_inside_grace_is_scanned_once():
    node = scheduler()
    assert any(
        isinstance(n, ast.Assign)
        and ast.unparse(n.value) == "timedelta(seconds=self.scan_grace_seconds)"
        for n in node.body
    )
    loop = next(n for n in node.body if isinstance(n, ast.While))
    guard = next(n for n in loop.body if isinstance(n, ast.If))
    assert isinstance(guard.test, ast.BoolOp) and isinstance(guard.test.op, ast.And)
    predicates = [ast.unparse(n) for n in guard.test.values]
    assert "t.minute % 15 == 0" in predicates
    assert "t.second == 5" in predicates
    duplicate = guard.test.values[-1]
    assert isinstance(duplicate, ast.Compare)
    assert isinstance(duplicate.ops[0], ast.Is)
    assert isinstance(duplicate.comparators[0], ast.Constant)
    assert duplicate.comparators[0].value is None
    assert (
        ast.unparse(duplicate.left.func)
        == "self.store.db.execute('SELECT 1 FROM scan_cycles WHERE scan_timestamp=?', (key,)).fetchone"
    )
    policy = next(n for n in guard.body if isinstance(n, ast.If))
    assert ast.unparse(policy.test) == "timedelta(0) <= age <= grace"
    calls = [
        n
        for n in ast.walk(policy)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "self.scan"
    ]
    assert len(calls) == 1 and ast.unparse(calls[0]) == "self.scan(t)"
    assert isinstance(policy.body[0], ast.Expr)
    assert isinstance(policy.body[0].value, ast.Await)
    assert ast.unparse(loop.body[-1]) == "t += timedelta(minutes=15)"


def test_no_production_writers_or_publication_imports():
    tree = archived_tree()
    forbidden = (
        "app.db",
        "app.modules.signal_intelligence",
        "app.modules.signal_gate",
        "app.modules.operations.telegram",
        "app.modules.signals.repository",
        "app.modules.signals.service",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not any((node.module or "").startswith(p) for p in forbidden)
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith(p) for a in node.names for p in forbidden)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"send_message", "publish"}


def test_archived_runner_is_not_importable():
    assert ARCHIVE.suffixes == [".py", ".txt"]
    assert importlib.util.find_spec("research_layer.phase_4_2_41_88f.live_shadow") is None
    assert not (ROOT / "research_layer/phase_4_2_41_88f/live_shadow.py").exists()
