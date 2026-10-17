"""Regression: every offline/PAPER entrypoint denies a defined production flag.

The AST tests read actual repository source and exercise the exact guard
expression without calling a trading service, DB, broker, or Telegram API.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROTECTED = (
    "naseri_markets/installed_preview_smoke_v1.py",
    "naseri_markets/installed_paper_pilot_stage10_v1.py",
    "naseri_markets/unified_paper_pilot_stage20_v1.py",
    "naseri_markets/paper_demo_cli_v1.py",
    "naseri_markets/bot_admin_app.py",
    "naseri_markets/brooks_paper_service.py",
)


def _production_presence_conditions(filename: str) -> list[ast.Compare]:
    tree = ast.parse((ROOT / filename).read_bytes(), filename=filename)
    conditions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for expression in ast.walk(node.test):
            if not isinstance(expression, ast.Compare):
                continue
            if (len(expression.ops) == 1
                    and isinstance(expression.ops[0], ast.In)
                    and isinstance(expression.left, ast.Constant)
                    and expression.left.value == "MMT_PRODUCTION"
                    and len(expression.comparators) == 1
                    and isinstance(expression.comparators[0], ast.Attribute)
                    and isinstance(expression.comparators[0].value, ast.Name)
                    and expression.comparators[0].value.id == "os"
                    and expression.comparators[0].attr == "environ"):
                conditions.append(expression)
    return conditions


@pytest.mark.parametrize("filename", PROTECTED)
def test_guard_has_one_explicit_production_presence_denial(filename: str) -> None:
    code = (ROOT / filename).read_text(encoding="utf-8")
    assert code.count('"MMT_PRODUCTION" in os.environ') == 1
    assert 'os.environ.get("MMT_PRODUCTION") == "1"' not in code
    assert len(_production_presence_conditions(filename)) == 1


@pytest.mark.parametrize("filename", PROTECTED)
@pytest.mark.parametrize("setting", ("", "0", "1", "false", "FALSE", "no"))
def test_actual_entrypoint_guard_blocks_any_defined_production_setting(
    filename: str, setting: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    presence = _production_presence_conditions(filename)
    assert len(presence) == 1
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    conditional = ast.Expression(body=presence[0])
    ast.fix_missing_locations(conditional)
    result = eval(compile(conditional, filename, "eval"), {"os": os})
    assert result is True


@pytest.mark.parametrize("filename", PROTECTED)
def test_guard_does_not_reject_absent_production_flag(
    filename: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    presence = _production_presence_conditions(filename)
    assert len(presence) == 1
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    conditional = ast.Expression(body=presence[0])
    ast.fix_missing_locations(conditional)
    result = eval(compile(conditional, filename, "eval"), {"os": os})
    assert result is False


@pytest.mark.parametrize("setting", ("", "0", "false", "1"))
def test_installed_pilot_gate_rejects_any_production_assignment_before_io(
    setting: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from naseri_markets import installed_paper_pilot_stage10_v1 as pilot

    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    with pytest.raises(pilot.InstalledPilotRefused,
                       match="EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        pilot._gate(ack=True, installed=False)


@pytest.mark.parametrize("setting", ("", "0", "false", "1"))
def test_installed_smoke_refuses_before_running_fixture(
    setting: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from naseri_markets import installed_preview_smoke_v1 as smoke

    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", setting)

    def forbidden_runtime() -> None:
        raise AssertionError("OFFLINE_SMOKE_MUST_NOT_RUN")

    monkeypatch.setattr(smoke, "run_offline_preview", forbidden_runtime)
    assert smoke.main(["--ack-isolated-preview"]) == 2
