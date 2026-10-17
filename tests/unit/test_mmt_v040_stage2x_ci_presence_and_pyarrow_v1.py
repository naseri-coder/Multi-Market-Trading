"""Stage2X regression: CI nonproduction presence-fence and locked dev extras.

No external venue, database, secrets, network, or live routes are used.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".github" / "workflows"
NONPROD_WORKFLOWS = (
    "stage15-real-brooks-historical-research.yml",
    "stage16-binance-archive-economics.yml",
    "stage21b-real-original-source-research.yml",
    "mmt-r23-original-tsa-offline-preflight.yml",
    "stage10-installed-integrated-paper.yml",
)
PYARROW_WORKFLOWS = NONPROD_WORKFLOWS[:2]
PAPER_CLI = NONPROD_WORKFLOWS[-1]


@pytest.mark.parametrize("name", NONPROD_WORKFLOWS)
def test_nonproduction_workflows_never_set_presence_trigger(name: str) -> None:
    text = (WORK / name).read_text(encoding="utf-8")
    assert 'MMT_NONPRODUCTION: "1"' in text
    assert "MMT_PRODUCTION:" not in text


@pytest.mark.parametrize("name", PYARROW_WORKFLOWS)
def test_research_jobs_use_existing_dev_pyarrow_pin_without_conflict(name: str) -> None:
    t = (WORK / name).read_text(encoding="utf-8")
    root = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pyarrow==26.0.0"' in root
    assert "python -m pip install -e '.[dev]'" in t
    assert "pyarrow==21.0.0" not in t
    assert "pyarrow==26.0.0" not in t  # no duplicate installation override


def test_installed_paper_workflow_never_injects_production_zero_in_child() -> None:
    text = (WORK / PAPER_CLI).read_text(encoding="utf-8")
    assert 'env = dict(os.environ, PYTHONPATH="", MMT_NONPRODUCTION="1")' in text
    assert 'assert "MMT_PRODUCTION" not in env' in text
    assert 'MMT_PRODUCTION="0"' not in text


@pytest.mark.parametrize(
    "relative",
    ("scripts/accept_paper07_installed.py", "scripts/accept_paper09_installed.py"),
)
def test_installed_paper_acceptance_uses_fail_closed_presence_gate(relative: str) -> None:
    content = (ROOT / relative).read_text(encoding="utf-8")
    assert '"MMT_PRODUCTION" in os.environ' in content
    assert 'os.environ.get("MMT_PRODUCTION") == "1"' not in content
    assert '"MMT_PRODUCTION": "0"' not in content


@pytest.mark.parametrize("production_value", ["0", "1", "false", ""])
def test_paper_replay_scripts_reject_any_defined_production_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, production_value: str,
) -> None:
    from scripts import accept_paper07_installed as p07
    from scripts import accept_paper09_installed as p09

    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", production_value)
    with pytest.raises(ValueError, match="EXPLICIT_NONROOT_NONPRODUCTION_REQUIRED"):
        p07.accept(tmp_path, tmp_path)
    with pytest.raises(ValueError, match="P09_DISPOSABLE_NONROOT_ONLY"):
        p09.accept(tmp_path, tmp_path)
