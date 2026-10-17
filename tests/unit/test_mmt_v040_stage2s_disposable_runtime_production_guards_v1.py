"""AST-only regression for sixteen reviewed runtime, host and recovery gates.

In a full checkout, real source is read. Synthetic guard fixtures are useful
only for an isolated smoke test and do not validate full-module dependencies.
No market, database, network, broker, or Telegram operation is performed.
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
    "dev_operator.py",
    "disposable_gvisor_canary_cli_stage23_v1.py",
    "disposable_gvisor_canary_stage23_v1.py",
    "durable_isolated_core_gate_stage22_v1.py",
    "durable_runtime_a3.py",
    "executable_walk_forward_stage13_v1.py",
    "job_effect_intent_v1.py",
    "job_effect_reconciliation_v1.py",
    "kucoin_futures_replay_stage21_v1.py",
    "mmt_r31_private_admin_console_v1.py",
    "mmt_r33_live_hard_deny_readiness_v1.py",
    "mmt_r34_offline_stack_acceptance_v1.py",
    "mt_a1_offline_artifact_preflight.py",
    "native_a1_inert_binary_preflight.py",
    "operational_reconciliation_v1.py",
    "panel_paper_synthetic_demo_v1.py",
)
PRODUCTION_VALUES = ("", "0", "1", "false", "FALSE", "no")
NONPRODUCTION_VALUES = (None, "", "0", "false")


def _is_production_presence(test: ast.AST) -> bool:
    return any(
        isinstance(c, ast.Compare)
        and len(c.ops) == 1 and isinstance(c.ops[0], ast.In)
        and isinstance(c.left, ast.Constant)
        and c.left.value == "MMT_PRODUCTION"
        and len(c.comparators) == 1
        and isinstance(c.comparators[0], ast.Attribute)
        and isinstance(c.comparators[0].value, ast.Name)
        and c.comparators[0].value.id == "os"
        and c.comparators[0].attr == "environ"
        for c in ast.walk(test)
    )


def _read_gate(name: str) -> ast.If:
    path = ROOT / "naseri_markets" / name
    source = path.read_text(encoding="utf-8")
    assert source.count("MMT_PRODUCTION") == 1, name
    assert source.count('"MMT_PRODUCTION" in os.environ') == 1, name
    assert 'os.environ.get("MMT_PRODUCTION") == "1"' not in source
    assert 'os.environ.get("MMT_NONPRODUCTION") != "1"' in source
    nodes = [node for node in ast.walk(ast.parse(source, str(path)))
             if isinstance(node, ast.If) and _is_production_presence(node.test)]
    assert len(nodes) == 1, (name, len(nodes))
    node = nodes[0]
    assert node.body and isinstance(node.body[0], ast.Raise)
    assert isinstance(node.body[0].exc, ast.Call)
    assert isinstance(node.body[0].exc.func, ast.Name)
    return copy.deepcopy(node)


def _execute_gate(name: str) -> None:
    node = _read_gate(name)
    error_name = node.body[0].exc.func.id
    error_class = type(error_name, (ValueError,), {})
    evidence_type = type("R34OfflineEvidence", (), {})
    paths_type = type("EffectEvidencePaths", (), {})
    namespace = {
        "os": SimpleNamespace(environ=os.environ, geteuid=lambda: 1000),
        "operator_ack": True, "ack": True, "enabled": True,
        "opts": SimpleNamespace(ack_disposable_host_canary=True),
        "R34OfflineEvidence": evidence_type, "evidence": evidence_type(),
        "EffectEvidencePaths": paths_type, "paths": paths_type(),
        error_name: error_class,
    }
    executable = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(executable)
    exec(compile(executable, name, "exec"), namespace)


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize("value", PRODUCTION_VALUES)
def test_defined_production_flag_always_refused(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    monkeypatch.setenv("MMT_PRODUCTION", value)
    with pytest.raises(ValueError):
        _execute_gate(name)


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize("value", NONPRODUCTION_VALUES)
def test_missing_nonproduction_approval_refused(
    name: str, value: str | None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    if value is None:
        monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    else:
        monkeypatch.setenv("MMT_NONPRODUCTION", value)
    with pytest.raises(ValueError):
        _execute_gate(name)


@pytest.mark.parametrize("name", MODULES)
def test_only_approved_initial_gate_reachable(
    name: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    _execute_gate(name)


@pytest.mark.parametrize("name", MODULES)
def test_real_source_guard_shape_and_immediate_refusal(name: str) -> None:
    assert isinstance(_read_gate(name), ast.If)


def test_scope_is_exactly_sixteen_distinct_modules() -> None:
    assert len(MODULES) == len(set(MODULES)) == 16
