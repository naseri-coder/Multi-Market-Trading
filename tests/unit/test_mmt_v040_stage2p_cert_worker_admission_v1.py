"""AST-only admission regression for eight real certification/worker modules.

On a complete checkout this reads the current module bodies; the isolated
sandbox may run on explicit small guard fixtures. No worker or data IO occurs.
"""
from __future__ import annotations

import ast
import copy
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    "cert_a1_offline_candidate_review.py",
    "cert_a1_paper_format_inventory.py",
    "cert_a2_direct_paper_replay.py",
    "cert_a3_four_language_wire_replay.py",
    "cert_a4_synthetic_result_contract.py",
    "cert_a6_disposable_containment.py",
    "runtime_a6_dispatch_fence.py",
    "runtime_a7_disposable_host_preflight.py",
)
VALUES = ("", "0", "1", "false", "FALSE", "no")


class AdmissionRefused(ValueError):
    """Harmless stand-in for each module's original refusal type."""


def _has_production_presence(tree: ast.AST) -> bool:
    return any(
        isinstance(c, ast.Compare) and len(c.ops) == 1
        and isinstance(c.ops[0], ast.In)
        and isinstance(c.left, ast.Constant)
        and c.left.value == "MMT_PRODUCTION"
        and len(c.comparators) == 1
        and isinstance(c.comparators[0], ast.Attribute)
        and isinstance(c.comparators[0].value, ast.Name)
        and c.comparators[0].value.id == "os"
        and c.comparators[0].attr == "environ"
        for c in ast.walk(tree)
    )


def _guard(module: str) -> ast.If:
    path = ROOT / "naseri_markets" / module
    source = path.read_text(encoding="utf-8")
    assert 'os.environ.get("MMT_PRODUCTION") == "1"' not in source
    parsed = ast.parse(source, filename=str(path))
    nodes = [n for n in ast.walk(parsed)
             if isinstance(n, ast.If) and _has_production_presence(n.test)]
    assert len(nodes) == 1, (module, len(nodes))
    assert len(nodes[0].body) >= 1 and isinstance(nodes[0].body[0], ast.Raise)
    return copy.deepcopy(nodes[0])


def _execute_initial_guard(module: str) -> None:
    node = _guard(module)
    ns = {
        "os": os,
        "ack": True,
        "operator_ack": True,
    }
    for n in ast.walk(node):
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
            if isinstance(n.exc.func, ast.Name):
                ns[n.exc.func.id] = AdmissionRefused
    code = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(code)
    exec(compile(code, module, "exec"), ns)


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("value", VALUES)
def test_every_production_assignment_denied_before_data_or_worker(
    module: str, value: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED", "1")
    monkeypatch.setenv("MMT_PRODUCTION", value)
    with pytest.raises(AdmissionRefused):
        _execute_initial_guard(module)


@pytest.mark.parametrize("module", MODULES)
def test_no_production_flag_with_approved_nonproduction_passes_gate(
    module: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    _execute_initial_guard(module)


@pytest.mark.parametrize("module", MODULES)
def test_missing_nonproduction_ack_denied(
    module: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED", "1")
    with pytest.raises(AdmissionRefused):
        _execute_initial_guard(module)


def test_disposable_cert_still_needs_separate_host_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.delenv("MMT_CERT_A6_DISPOSABLE_HOST_APPROVED", raising=False)
    with pytest.raises(AdmissionRefused):
        _execute_initial_guard("cert_a6_disposable_containment.py")


@pytest.mark.parametrize("module", MODULES)
def test_exactly_one_guard_is_reviewed(module: str) -> None:
    assert isinstance(_guard(module), ast.If)


def test_scope_is_exactly_eight_distinct_modules() -> None:
    assert len(MODULES) == len(set(MODULES)) == 8
