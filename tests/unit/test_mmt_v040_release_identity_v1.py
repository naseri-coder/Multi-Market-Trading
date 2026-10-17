"""Release-version boundary and malformed identity regressions (offline only)."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from naseri_markets._release_identity_v1 import (
    PLATFORM_DISTRIBUTION,
    PLATFORM_VERSION,
    exact_platform_version,
)
from scripts import a6_release_preflight


def test_current_candidate_metadata_exactly_matches_runtime_identity() -> None:
    root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((root / "platform_release/pyproject.toml").read_text())
    assert PLATFORM_DISTRIBUTION == "multi-market-trading"
    assert metadata["project"]["name"] == PLATFORM_DISTRIBUTION
    assert metadata["project"]["version"] == PLATFORM_VERSION == "0.4.0rc1"
    assert a6_release_preflight._platform_version() == PLATFORM_VERSION


@pytest.mark.parametrize("value", [
    "", "0.3.2", "0.4.0", "0.4.0rc2", "0.4.0rc1+local",
    "v0.4.0rc1", "0.4.0RC1", None, 1, True, ["0.4.0rc1"],
])
def test_installed_identity_refuses_unexpected_version(value: object) -> None:
    assert exact_platform_version(value) is False


def test_current_candidate_exact_version_accepted() -> None:
    assert exact_platform_version("0.4.0rc1") is True


@pytest.mark.parametrize(("assignment", "expected"), [
    ('PLATFORM_VERSION = "0.4.0rc1"\n', "0.4.0rc1"),
    ('PLATFORM_VERSION = "0.4.0"\n', "0.4.0"),
])
def test_static_identity_parser_recognizes_only_exact_release_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, assignment: str, expected: str,
) -> None:
    root = tmp_path / "repo"
    (root / "naseri_markets").mkdir(parents=True)
    (root / "naseri_markets/_release_identity_v1.py").write_text(assignment)
    monkeypatch.setattr(a6_release_preflight, "ROOT", root)
    assert a6_release_preflight._platform_version() == expected


@pytest.mark.parametrize("assignment", [
    'PLATFORM_VERSION = "0.3.2"\n',
    'PLATFORM_VERSION = "4.0.0"\n',
    'PLATFORM_VERSION = "0.4.0+local"\n',
    'PLATFORM_VERSION = 1\n',
    'PLATFORM_VERSION = "0.4.0rc1"\nPLATFORM_VERSION = "0.4.0"\n',
    'PLATFORM_VERSION = get_version()\n',
    'PLATFORM_VERSION = (\n',
    '# no declared version\n',
])
def test_static_identity_parser_denies_unsafe_or_ambiguous_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, assignment: str,
) -> None:
    root = tmp_path / "repo"
    (root / "naseri_markets").mkdir(parents=True)
    (root / "naseri_markets/_release_identity_v1.py").write_text(assignment)
    monkeypatch.setattr(a6_release_preflight, "ROOT", root)
    with pytest.raises((ValueError, SyntaxError)):
        a6_release_preflight._platform_version()
