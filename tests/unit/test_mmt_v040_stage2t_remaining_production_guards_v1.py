"""Source-bound fail-closed tests for reviewed Stage 2T entrypoint gates.

On a complete source checkout, AST reads the actual modules. Tests run only
boolean admission conditions; they cannot invoke worker, broker, DB or network.
Synthetic reduced fixtures are NOT full-source/module validation.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD_COUNTS = {
    "brooks_causal_execution_parity_audit_mmt_r26_v1.py": 2,
    "brooks_independent_lifecycle_economics_mmt_r27_v1.py": 2,
    "pine_a1_sma_cross_parity.py": 1,
    "public_candidate_lock_stage26_v1.py": 1,
    "public_forward_capture_stage21c_v1.py": 1,
    "public_futures_contracts.py": 1,
    "publisher_package_registry_stage28_v1.py": 1,
    "read_only_provider_adapters_v1.py": 2,
    "research_robustness_stage14_v1.py": 1,
    "signed_core_candidate_stage23_v1.py": 1,
    "supervisor_synthetic_smoke_v1.py": 1,
}
GATES = tuple((name, index) for name, count in GUARD_COUNTS.items() for index in range(count))
PRODUCTION_VALUES = ("", "0", "1", "false", "FALSE", "no")
NONPRODUCTION_VALUES = (None, "", "0", "false")


def _is_production_presence(test: ast.AST) -> bool:
    return any(
        isinstance(c, ast.Compare)
        and len(c.ops) == 1 and isinstance(c.ops[0], ast.In)
        and isinstance(c.left, ast.Constant) and c.left.value == "MMT_PRODUCTION"
        and len(c.comparators) == 1
        and isinstance(c.comparators[0], ast.Attribute)
        and isinstance(c.comparators[0].value, ast.Name)
        and c.comparators[0].value.id == "os"
        and c.comparators[0].attr == "environ"
        for c in ast.walk(test)
    )


def _guard(name: str, index: int) -> ast.If:
    path = ROOT / "naseri_markets" / name
    source = path.read_text(encoding="utf-8")
    count = GUARD_COUNTS[name]
    assert source.count("MMT_PRODUCTION") == count
    assert source.count('"MMT_PRODUCTION" in os.environ') + source.count("'MMT_PRODUCTION' in os.environ") == count
    assert 'os.environ.get("MMT_NONPRODUCTION") != "1"' in source or "os.environ.get('MMT_NONPRODUCTION') != '1'" in source
    parsed = ast.parse(source, filename=str(path))
    nodes = sorted(
        (n for n in ast.walk(parsed) if isinstance(n, ast.If) and _is_production_presence(n.test)),
        key=lambda n: n.lineno,
    )
    assert len(nodes) == count, (name, len(nodes), count)
    assert 0 <= index < len(nodes)
    node = nodes[index]
    assert node.body and (
        isinstance(node.body[0], ast.Raise)
        or (name == "public_futures_contracts.py" and any(isinstance(b, ast.Return) for b in node.body))
    )
    return node


def _admission_refuses(name: str, index: int, *, ack: bool = True) -> bool:
    node = _guard(name, index)
    guard = ast.Expression(node.test)
    ast.fix_missing_locations(guard)
    return bool(eval(compile(guard, name, "eval"), {"__builtins__": {}}, {
        "os": os,
        "ack": ack, "operator_ack": ack, "acknowledge_research": ack,
        "args": SimpleNamespace(ack_public_metadata_research=ack),
    }))


@pytest.mark.parametrize("name,index", GATES)
@pytest.mark.parametrize("value", PRODUCTION_VALUES)
def test_production_presence_blocks_every_literal_value(
    name: str, index: int, value: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", value)
    assert _admission_refuses(name, index)


@pytest.mark.parametrize("name,index", GATES)
@pytest.mark.parametrize("value", NONPRODUCTION_VALUES)
def test_missing_or_false_nonproduction_still_blocks(
    name: str, index: int, value: str | None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    if value is None:
        monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    else:
        monkeypatch.setenv("MMT_NONPRODUCTION", value)
    assert _admission_refuses(name, index)


@pytest.mark.parametrize("name,index", GATES)
def test_approved_initial_environment_does_not_trip_the_gate(
    name: str, index: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    assert not _admission_refuses(name, index)


@pytest.mark.parametrize("name,index", [g for g in GATES if g[0] != "supervisor_synthetic_smoke_v1.py"])
def test_missing_operator_approval_remains_refused(
    name: str, index: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    assert _admission_refuses(name, index, ack=False)


@pytest.mark.parametrize("name,index", GATES)
def test_guard_is_in_real_source_ast(name: str, index: int) -> None:
    assert isinstance(_guard(name, index), ast.If)


def test_exact_reviewed_scope() -> None:
    assert len(GUARD_COUNTS) == 11 and len(GATES) == 14
