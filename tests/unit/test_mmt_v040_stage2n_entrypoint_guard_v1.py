"""AST-isolated admission checks on the actual repository source guard nodes.

No modules are imported and no PAPER, broker, database, or network is reached.
The extracted branch is a narrow policy smoke test, NOT full runtime parity.
"""
from __future__ import annotations

import ast
import copy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    ("adapter_free_paper_runtime_v1.py", 1),
    ("binance_public_funding_mark_stage18_v1.py", 1),
    ("binance_vision_archive_stage16_v1.py", 2),
    ("captured_paper_cli_stage21b_v1.py", 1),
    ("captured_paper_pilot_stage21b_v1.py", 1),
    ("data_a1_file_intake.py", 1),
    ("data_runtime_paper_wire_a1.py", 1),
    ("mmt_r32_stopped_recovery_review_v1.py", 1),
)
CASES = tuple((name, index) for name, count in SOURCES for index in range(count))
PRODUCTION_SETTINGS = ("", "0", "1", "false", "FALSE", "no")


class PolicyRefused(ValueError):
    """The isolated original Raise branch uses this harmless class."""


def _contains_present_flag(test: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.In)
        and isinstance(node.left, ast.Constant)
        and node.left.value == "MMT_PRODUCTION"
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Attribute)
        and isinstance(node.comparators[0].value, ast.Name)
        and node.comparators[0].value.id == "os"
        and node.comparators[0].attr == "environ"
        for node in ast.walk(test)
    )


def _guard_nodes(filename: str) -> list[ast.If]:
    source = (ROOT / "naseri_markets" / filename).read_text(encoding="utf-8")
    # Presence admission, not the original value-only policy.
    assert 'os.environ.get("MMT_PRODUCTION") == "1"' not in source
    root = ast.parse(source, filename=filename)
    nodes = [node for node in ast.walk(root)
             if isinstance(node, ast.If) and _contains_present_flag(node.test)]
    expected = dict(SOURCES)[filename]
    assert len(nodes) == expected, (filename, len(nodes), expected)
    for node in nodes:
        assert node.body and isinstance(node.body[0], ast.Raise)
    return sorted(nodes, key=lambda node: node.lineno)


def _run_guard(filename: str, index: int) -> bool:
    """Executes ONLY the original If admission guard, never its sibling logic."""
    node = copy.deepcopy(_guard_nodes(filename)[index])
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    classes = (
        "PipelineRefused", "Stage18MarketEvidenceRefused", "VisionArchiveRefused",
        "CapturedPaperRefused", "HistoricalDataRefused", "PaperWireRefused",
        "R32RecoveryRefused",
    )
    scope = {name: PolicyRefused for name in classes}
    scope.update({
        "os": os, "operator_ack": True, "all_writers_stopped": True,
        "opts": SimpleNamespace(ack_offline_captured_paper=True),
    })
    exec(compile(isolated, filename, "exec"), scope)
    return True


@pytest.mark.parametrize("filename,index", CASES)
@pytest.mark.parametrize("production_value", PRODUCTION_SETTINGS)
def test_any_defined_production_environment_is_denied_before_side_effects(
    filename: str, index: int, production_value: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", production_value)
    with pytest.raises(PolicyRefused):
        _run_guard(filename, index)


@pytest.mark.parametrize("filename,index", CASES)
def test_nonproduction_absent_production_key_does_not_hit_guard(
    filename: str, index: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    assert _run_guard(filename, index) is True


@pytest.mark.parametrize("filename,index", CASES)
def test_missing_nonproduction_consent_is_denied(
    filename: str, index: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    with pytest.raises(PolicyRefused):
        _run_guard(filename, index)


@pytest.mark.parametrize("filename,count", SOURCES)
def test_source_guard_inventory_has_exact_expected_count(filename: str, count: int) -> None:
    assert len(_guard_nodes(filename)) == count


def test_all_targets_are_unique_and_explicit() -> None:
    assert len(SOURCES) == 8 and len(CASES) == 9
    assert len({name for name, _ in SOURCES}) == 8
