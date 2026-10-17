"""Execute selected real Brooks gate functions in isolated AST namespaces.

This extracts the current repository functions without importing their mutable
services or opening a DB, network socket, worker or Telegram session.
"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_VALUES = ("", "0", "1", "false", "FALSE", "no")
CASES = (
    ("brooks_stage10_cli.py", "BrooksStage10Refused", "STAGE10_OPERATOR_NONPRODUCTION_OPTIN_REQUIRED"),
    ("brooks_stage11_cli.py", "BrooksStage11Refused", "EXPLICIT_NONPRODUCTION_FILE_REPLAY_REQUIRED"),
    ("brooks_stage12_cli.py", "Stage12ResearchRefused", "STAGE12_NONPRODUCTION_OPTIN_REQUIRED"),
)


def _source(module_name: str) -> str:
    return (ROOT / "naseri_markets" / module_name).read_text(encoding="utf-8")


def _isolated_function(module_name: str, name: str, globals_: dict) -> object:
    """Only compile the named function, not module imports/global initializers."""
    root = ast.parse(_source(module_name), filename=module_name)
    funcs = [n for n in root.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(funcs) == 1
    snippet = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
              copy.deepcopy(funcs[0])],
        type_ignores=[],
    )
    ast.fix_missing_locations(snippet)
    ns = dict(globals_)
    exec(compile(snippet, module_name, "exec"), ns)
    return ns[name]


@pytest.mark.parametrize("filename,exception,reason", CASES)
@pytest.mark.parametrize("setting", PRODUCTION_VALUES)
def test_brooks_operator_cli_rejects_any_defined_production_before_io(
    filename: str, exception: str, reason: str, setting: str,
) -> None:
    failure_type = type(exception, (ValueError,), {})
    run_once = _isolated_function(filename, "run_once", {exception: failure_type})
    args = argparse.Namespace(
        status=False, reconcile=False, ack_nonproduction_stage10_paper=True,
        ack_offline_paper_only=True, ack_offline_research_only=True,
        account_id=None, signal_id=None, candles_file=None, manifest=None,
        # Were the guards bypassed, non-existent dependencies would be touched.
        state_dir=Path("/not-a-real-state-dir"),
    )
    environment = {"MMT_NONPRODUCTION": "1", "MMT_PRODUCTION": setting}
    with pytest.raises(failure_type, match=reason):
        run_once(args, environment=environment)


@pytest.mark.parametrize("setting", PRODUCTION_VALUES)
def test_real_brooks_parent_denies_defined_production_before_archive_or_worker(
    monkeypatch: pytest.MonkeyPatch, setting: str,
) -> None:
    refusal = type("Stage15Refused", (ValueError,), {})
    review = _isolated_function("real_brooks_historical_stage15_v1.py",
                                "review_real_brooks_history", {"Stage15Refused": refusal,
                                                               "os": os})
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    with pytest.raises(refusal, match="EXPLICIT_NONPRODUCTION_OPERATOR_APPROVAL_REQUIRED"):
        review(None, None, receipt_bytes=b"", trusted_receipt_sha256="",
               archive_as_of_utc=None, legacy_source=None,
               evaluation_cutoffs_utc=(), operator_ack=True)


def test_worker_subprocess_receives_clean_explicit_offline_environment() -> None:
    """Call the real worker function body with subprocess.run replaced by a fake."""
    module = "real_brooks_historical_stage15_v1.py"
    fake_result = SimpleNamespace(returncode=0, stdout=b'{}')
    runner = Mock(return_value=fake_result)
    worker = _isolated_function(module, "_worker", {
        "tempfile": tempfile,
        "subprocess": SimpleNamespace(run=runner, TimeoutExpired=subprocess.TimeoutExpired,
                                     PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL),
        "sys": sys, "Path": Path, "json": json, "MAX_WORKER_BYTES": 8192,
        "__file__": str(ROOT / "naseri_markets" / module),
    })
    result = worker(Path("/disposable/readonly/legacy"), b'{}', 3)
    assert result == {}
    env = runner.call_args.kwargs["env"]
    assert env["MMT_NONPRODUCTION"] == "1"
    assert "MMT_PRODUCTION" not in env
    assert env["PYTHONNOUSERSITE"] == "1"
    assert runner.call_args.kwargs["input"] == b'{}'
    assert runner.call_count == 1


@pytest.mark.parametrize("setting", PRODUCTION_VALUES)
def test_termux_brooks_readiness_rejects_defined_production(
    setting: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal = type("R23ReadinessRefused", (ValueError,), {})
    readyness = _isolated_function("brooks_termux_readiness_mmt_r23_v1.py",
                                   "_research_only_ack", {
        "_gate": lambda _: None, "os": os, "R23ReadinessRefused": refusal,
    })
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    with pytest.raises(refusal, match="R23_PRODUCTION_ENVIRONMENT_REFUSED"):
        readyness(True)


@pytest.mark.parametrize("setting", PRODUCTION_VALUES)
def test_point_in_time_archive_gate_rejects_defined_production_before_disk(
    setting: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal = type("HistoricalPitRefused", (ValueError,), {})
    inspect = _isolated_function("historical_pit_quality_stage12_v1.py",
                                 "inspect_historical_pit_archive", {
        "os": os, "HistoricalPitRefused": refusal,
    })
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    with pytest.raises(refusal, match="PIT_EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        inspect(None, None, receipt_bytes=b"", trusted_receipt_sha256="",
                as_of_utc=None, operator_ack=True)


def test_read_only_brooks_stage10_diagnostic_branch_remains_unchanged() -> None:
    marker = {"safe": True, "order_sent": False}
    run_once = _isolated_function("brooks_stage10_cli.py", "run_once", {
        "panel_stage10_overview": lambda path: marker,
    })
    args = argparse.Namespace(status=True, state_dir=Path("/nonexistent"))
    assert run_once(args, environment={"MMT_PRODUCTION": "1"}) is marker


def test_no_child_process_explicitly_labels_itself_production() -> None:
    tree = ast.parse(_source("real_brooks_historical_stage15_v1.py"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "_worker")
    calls = [node for node in ast.walk(fn) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "run"]
    assert len(calls) == 1
    envs = [kw.value for kw in calls[0].keywords if kw.arg == "env"]
    assert len(envs) == 1 and isinstance(envs[0], ast.Dict)
    keys = [key.value for key in envs[0].keys if isinstance(key, ast.Constant)]
    assert "MMT_NONPRODUCTION" in keys
    assert "MMT_PRODUCTION" not in keys
