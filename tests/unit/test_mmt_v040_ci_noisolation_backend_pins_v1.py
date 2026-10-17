"""Prevent CI failures when real Wheel rehearsals use --no-build-isolation.

This is a workflow preflight assertion, not an independent release signature.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/full-corpus-postgres.yml",
    ".github/workflows/native-postgres16.yml",
)
INSTALL = (
    '          python -m pip install --disable-pip-version-check --no-deps '
    '"setuptools==80.9.0" "wheel==0.45.1"'
)
CHECK = (
    '          from setuptools import build_meta  # noqa: F401\n'
    '          assert metadata.version("setuptools") == "80.9.0"\n'
    '          assert metadata.version("wheel") == "0.45.1"'
)


def _backend_contract(text: str) -> bool:
    root_install = text.find('          python -m pip install ')
    pinned = text.find(INSTALL)
    verified = text.find(CHECK)
    suite = text.find("          python -m pytest -q")
    return (
        root_install >= 0
        and pinned > root_install
        and verified > pinned
        and suite > verified
        and text.count(INSTALL) == 1
        and text.count(CHECK) == 1
        and "PYTHONDONTWRITEBYTECODE: \"1\"" in text
    )


@pytest.mark.parametrize("relative", WORKFLOWS)
def test_full_corpus_workflow_installs_and_checks_pinned_build_backend(relative: str):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert _backend_contract(text)


@pytest.mark.parametrize("relative", WORKFLOWS)
def test_full_corpus_workflow_refuses_missing_or_unpinned_backend(relative: str):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert not _backend_contract(text.replace(INSTALL, ""))
    assert not _backend_contract(text.replace('"setuptools==80.9.0"', '"setuptools>=75"'))
    assert not _backend_contract(text.replace('"wheel==0.45.1"', '"wheel>=0.45"'))
    assert not _backend_contract(text.replace(CHECK, ""))
