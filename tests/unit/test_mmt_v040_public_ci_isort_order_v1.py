"""Require materialized frozen source before the PR's Ruff import gate."""
from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github/workflows/public-test-corpus.yml"
)
MATERIALIZE = "      - name: Materialize frozen release layout for path-contract tests"
LINT = "      - name: Reject new Ruff findings"
CORPUS = "      - name: Run reviewed public unit corpus"
COPIED_PACKAGE = "          cp -a production_source/app ./app"
BASE_REF = (
    "          RUFF_BASE_SHA: "
    "${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha "
    "|| github.event.before }}"
)


def _admitted(text: str) -> bool:
    if any(text.count(item) != 1 for item in (
        MATERIALIZE, LINT, CORPUS, COPIED_PACKAGE, BASE_REF
    )):
        return False
    return (
        text.index(MATERIALIZE)
        < text.index(COPIED_PACKAGE)
        < text.index(LINT)
        < text.index(CORPUS)
    )


def test_materialize_source_before_import_sensitive_ruff_gate():
    assert _admitted(WORKFLOW.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "mutation",
    (
        lambda s: s.replace(COPIED_PACKAGE, ""),
        lambda s: s.replace(BASE_REF, ""),
        lambda s: s.replace(MATERIALIZE, ""),
    ),
)
def test_ci_import_gate_denies_missing_source_or_baseline(mutation):
    assert not _admitted(mutation(WORKFLOW.read_text(encoding="utf-8")))


def test_ci_gate_rejects_ruff_before_source_materialization():
    text = WORKFLOW.read_text(encoding="utf-8")
    inverted = (
        text.replace(MATERIALIZE, "__MATERIALIZE_SENTINEL__")
        .replace(LINT, MATERIALIZE)
        .replace("__MATERIALIZE_SENTINEL__", LINT)
    )
    assert not _admitted(inverted)
