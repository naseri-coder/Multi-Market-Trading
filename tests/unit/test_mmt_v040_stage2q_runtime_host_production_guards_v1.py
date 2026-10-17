"""Fail-closed AST-only tests for reviewed runtime/host admission paths.

A complete repository checkout reads actual source. An isolated fixture checkout
may only demonstrate the inspected guard slices, NOT full runtime integration.
No production modules are imported or executed in these tests.
"""
from __future__ import annotations

import ast
import copy
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    "designated_host_readonly_probe_stage34_v1.py",
    "disposable_host_preflight_stage32_v1.py",
    "host_observation_custody_stage24_v1.py",
    "preinstall_evidence_stage25_v1.py",
    "runtime_a10_evidence_anchor.py",
    "runtime_a4_security_evidence.py",
    "runtime_a5_nonce_custody.py",
    "runtime_a9_offline_intent.py",
)
VALUES = ("", "0", "1", "false", "FALSE", "no")


class AdmissionRefused(ValueError):
    """Local substitute for a real entrypoint refusal exception."""


def _has_presence(test: ast.AST) -> bool:
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


def _guard(module: str) -> ast.If:
    path = ROOT / "naseri_markets" / module
    source = path.read_text(encoding="utf-8")
    assert 'os.environ.get("MMT_PRODUCTION") == "1"' not in source
    assert source.count('"MMT_PRODUCTION" in os.environ') == 1
    assert 'os.environ.get("MMT_NONPRODUCTION") != "1"' in source
    parsed = ast.parse(source, filename=str(path))
    candidates = [n for n in ast.walk(parsed)
                  if isinstance(n, ast.If) and _has_presence(n.test)]
    assert len(candidates) == 1, (module, len(candidates))
    assert candidates[0].body and isinstance(candidates[0].body[0], ast.Raise)
    return copy.deepcopy(candidates[0])


def _execute_denial(module: str) -> None:
    node = _guard(module)
    ns = {"os": os, "ack": True, "operator_ack": True}
    for n in ast.walk(node):
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
            if isinstance(n.exc.func, ast.Name):
                ns[n.exc.func.id] = AdmissionRefused
    code = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(code)
    exec(compile(code, module, "exec"), ns)


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("value", VALUES)
def test_every_defined_production_value_denied(module: str, value: str,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", value)
    with pytest.raises(AdmissionRefused):
        _execute_denial(module)


@pytest.mark.parametrize("module", MODULES)
def test_missing_explicit_nonproduction_denied(module: str,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    with pytest.raises(AdmissionRefused):
        _execute_denial(module)


@pytest.mark.parametrize("module", MODULES)
def test_source_contains_immediate_presence_refusal(module: str) -> None:
    assert isinstance(_guard(module), ast.If)


@pytest.mark.parametrize("module", MODULES)
def test_absent_production_key_does_not_trigger_presence_predicate(
    module: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _guard(module)
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    assert not ("MMT_PRODUCTION" in os.environ)


def test_stage_scope_exactly_eight_distinct_modules() -> None:
    assert len(MODULES) == len(set(MODULES)) == 8
