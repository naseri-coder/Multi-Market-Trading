"""Exercise the real eight source entry-guard ASTs without importing workers.

A narrow guard-only test: NOT a complete runtime, ledger or nonroot install test.
"""
from __future__ import annotations

import ast
import copy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    "mmt_r30_offline_risk_order_preflight_v1.py",
    "brooks_future_shadow_paper_mmt_r29_v1.py",
    "paper09_snapshot_v1.py",
    "paper_contract_economics_stage21d_v1.py",
    "signed_public_intake_stage27_v1.py",
    "offline_runtime_supervisor_v1.py",
    "mmt_r28_unified_offline_runtime_v1.py",
    "runtime_supervisor_health_v1.py",
)
VALUES = ("", "0", "1", "false", "FALSE", "no")


class AdmissionDenied(ValueError):
    pass


def _present(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Compare)
        and len(n.ops) == 1
        and isinstance(n.ops[0], ast.In)
        and isinstance(n.left, ast.Constant)
        and n.left.value == "MMT_PRODUCTION"
        and len(n.comparators) == 1
        and isinstance(n.comparators[0], ast.Attribute)
        and isinstance(n.comparators[0].value, ast.Name)
        and n.comparators[0].value.id == "os"
        and n.comparators[0].attr == "environ"
        for n in ast.walk(node)
    )


def _guard(name: str) -> ast.stmt:
    path = ROOT / "naseri_markets" / name
    source = path.read_text(encoding="utf-8")
    assert 'os.environ.get("MMT_PRODUCTION") == "1"' not in source
    root = ast.parse(source, filename=str(path))
    checks = []
    for node in ast.walk(root):
        if isinstance(node, ast.If) and _present(node.test):
            assert node.body and isinstance(node.body[0], ast.Raise)
            checks.append(node)
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and _present(node.value)):
            assert isinstance(node.value.func, ast.Name)
            assert node.value.func.id == "_fail"
            checks.append(node)
    assert len(checks) == 1, (name, len(checks))
    return copy.deepcopy(checks[0])


def _invoke(name: str, *, root_user: bool = False) -> None:
    guard = _guard(name)
    def _fail(should_refuse: bool, reason: str):
        if should_refuse:
            raise AdmissionDenied(reason)
    class FakePanel:
        pass
    scope = {
        "os": SimpleNamespace(environ=os.environ, geteuid=lambda: 0 if root_user else 1001),
        "operator_ack": True, "enabled": True, "panel": FakePanel(),
        "OfflineTradingControlCenter": FakePanel, "actor_id": 1,
        "_fail": _fail,
    }
    # Bind only static refusal exception identifiers referenced by the guard.
    for node in ast.walk(guard):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if isinstance(node.exc.func, ast.Name):
                scope[node.exc.func.id] = AdmissionDenied
    fragment = ast.Module(body=[guard], type_ignores=[])
    ast.fix_missing_locations(fragment)
    exec(compile(fragment, name, "exec"), scope)


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("production_setting", VALUES)
def test_all_production_flag_assignments_refused_before_worker_or_db(
    module: str, production_setting: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", production_setting)
    with pytest.raises(AdmissionDenied):
        _invoke(module)


@pytest.mark.parametrize("module", MODULES)
def test_no_flag_with_nonproduction_consent_passes_initial_gate(
    module: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    _invoke(module)


@pytest.mark.parametrize("module", MODULES)
def test_missing_nonproduction_consent_is_refused(
    module: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    with pytest.raises(AdmissionDenied):
        _invoke(module)


def test_snapshot_still_blocks_root_even_in_explicit_nonproduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    with pytest.raises(AdmissionDenied, match="P09_NONROOT_NONPRODUCTION_ACK_REQUIRED"):
        _invoke("paper09_snapshot_v1.py", root_user=True)


@pytest.mark.parametrize("module", MODULES)
def test_source_retains_exactly_one_reviewed_gate(module: str) -> None:
    assert _guard(module) is not None


def test_expected_stage2o_inventory_has_eight_distinct_modules() -> None:
    assert len(MODULES) == len(set(MODULES)) == 8
