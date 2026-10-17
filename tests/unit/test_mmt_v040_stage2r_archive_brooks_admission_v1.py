"""Source-bound AST admission regression for eight reviewed archive/Brooks modules.

Extracts and executes ONLY the initial refusal If from each original source.
On a full checkout the real source is inspected; local synthetic fixtures do not
count as a full-package test. Never starts engines, brokers, or data processing.
"""
from __future__ import annotations

import ast
import copy
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULES = {
    "futures_economic_scenario_stage16_v1.py": ("FuturesScenarioRefused", "ST16_EXPLICIT_RESEARCH_ACK_REQUIRED", True),
    "stage17_official_archive_capture_v1.py": ("Stage17Refused", "ST17_NONPRODUCTION_ONLY", False),
    "futures_economics_evidence_stage18_v1.py": ("Stage18Refused", "ST18_NONPRODUCTION_ACK_REQUIRED", True),
    "brooks_causal_backtest_preflight_stage19_v1.py": ("Stage19Refused", "ST19_EXPLICIT_NONPRODUCTION_ACK_REQUIRED", True),
    "brooks_walk_forward_preholdout_stage20_v1.py": ("Stage20Refused", "ST20_NONPRODUCTION_EXPLICIT_APPROVAL_REQUIRED", True),
    "brooks_causal_lifecycle_stage21_preflight_v1.py": ("Stage21StudyRefused", "ST21_EXPLICIT_OFFLINE_RESEARCH_ONLY", True),
    "brooks_primary_source_funding_join_stage21b_v1.py": ("Stage21SourceRefused", "ST21B_NONPRODUCTION_ACK_REQUIRED", True),
    "brooks_prospective_forward_custody_stage21c_v1.py": ("Stage21ForwardRefused", "ST21C_RESEARCH_NONPRODUCTION_APPROVAL_REQUIRED", True),
}
PRODUCTION_VALUES = ("", "0", "1", "false", "FALSE", "no")
NONPRODUCTION_VALUES = (None, "", "0", "false")


def _has_presence(node: ast.AST) -> bool:
    return any(
        isinstance(c, ast.Compare)
        and len(c.ops) == 1
        and isinstance(c.ops[0], ast.In)
        and isinstance(c.left, ast.Constant)
        and c.left.value == "MMT_PRODUCTION"
        and len(c.comparators) == 1
        and isinstance(c.comparators[0], ast.Attribute)
        and isinstance(c.comparators[0].value, ast.Name)
        and c.comparators[0].value.id == "os"
        and c.comparators[0].attr == "environ"
        for c in ast.walk(node)
    )


def _guard(module: str) -> ast.If:
    path = ROOT / "naseri_markets" / module
    source = path.read_text(encoding="utf-8")
    assert source.count("MMT_PRODUCTION") == 1, module
    assert source.count('"MMT_PRODUCTION" in os.environ') == 1, module
    assert 'os.environ.get("MMT_NONPRODUCTION") != "1"' in source
    tree = ast.parse(source, filename=str(path))
    nodes = [n for n in ast.walk(tree)
             if isinstance(n, ast.If) and _has_presence(n.test)]
    assert len(nodes) == 1, (module, len(nodes))
    guard = nodes[0]
    assert guard.body and isinstance(guard.body[0], ast.Raise)
    exc = guard.body[0].exc
    assert isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
    assert exc.func.id == MODULES[module][0]
    assert len(exc.args) == 1 and isinstance(exc.args[0], ast.Constant)
    assert exc.args[0].value == MODULES[module][1]
    return copy.deepcopy(guard)


def _execute_guard(module: str, *, ack: bool = True) -> None:
    node = _guard(module)
    exception_name = MODULES[module][0]
    exception_type = type(exception_name, (ValueError,), {})
    compiled = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(compiled)
    exec(compile(compiled, module, "exec"), {
        "os": os, "operator_ack": ack, exception_name: exception_type,
    })


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("value", PRODUCTION_VALUES)
def test_any_defined_production_value_is_refused(
    module: str, value: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", value)
    with pytest.raises(ValueError, match=MODULES[module][1]):
        _execute_guard(module)


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("value", NONPRODUCTION_VALUES)
def test_missing_or_invalid_nonproduction_is_refused(
    module: str, value: str | None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    if value is None:
        monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    else:
        monkeypatch.setenv("MMT_NONPRODUCTION", value)
    with pytest.raises(ValueError, match=MODULES[module][1]):
        _execute_guard(module)


@pytest.mark.parametrize("module", [name for name, entry in MODULES.items() if entry[2]])
def test_missing_operator_ack_is_refused(
    module: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(ValueError, match=MODULES[module][1]):
        _execute_guard(module, ack=False)


@pytest.mark.parametrize("module", MODULES)
def test_approved_no_production_flag_passes_initial_gate(
    module: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    _execute_guard(module)


@pytest.mark.parametrize("module", MODULES)
def test_original_source_has_immediate_exact_refusal(module: str) -> None:
    assert isinstance(_guard(module), ast.If)


def test_scope_is_exactly_eight_distinct_real_modules() -> None:
    assert len(MODULES) == len(set(MODULES)) == 8
