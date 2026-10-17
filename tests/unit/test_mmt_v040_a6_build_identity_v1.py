"""Offline release metadata/safety gate regressions for 0.4.0rc1 → 0.4.0.

No live feed, Telegram, production database, package installation or network.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts import a6_prepare_package, a6_release_preflight


REPO = Path(__file__).resolve().parents[2]


def _copy_release_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "checkout"
    (root / "platform_release").mkdir(parents=True)
    (root / "production_source").mkdir()
    for filename in ("pyproject.toml", "compose.yaml", "compose.platform.yaml", "Dockerfile.platform"):
        shutil.copyfile(REPO / filename, root / filename)
    for filename in ("pyproject.toml", "README.md"):
        shutil.copyfile(REPO / "platform_release" / filename,
                        root / "platform_release" / filename)
    (root / "production_source/SHA256SUMS").write_text("frozen fixture only\n")
    (root / "naseri_markets").mkdir()
    (root / "naseri_markets/__init__.py").write_text("")
    (root / "naseri_markets/platform_cli.py").write_text("def main(): return 0\n")
    monkeypatch.setattr(a6_release_preflight, "ROOT", root)
    monkeypatch.setattr(a6_prepare_package, "ROOT", root)
    return root


def _update_version(root: Path, filename: str, value: str) -> None:
    target = root / filename
    content = target.read_text()
    assert "0.4.0rc1" in content
    target.write_text(content.replace("0.4.0rc1", value))


def test_rc_version_keeps_separate_nonproduction_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_release_fixture(tmp_path, monkeypatch)
    report = a6_release_preflight.check()
    assert report["preview_version"] == "0.4.0rc1"
    assert report["preview_runtime_enabled"] is False
    assert report["legacy_database_attached"] is False
    assert report["database_migration_executed"] is False
    assert report["nyfr_private_source_included"] is False
    assert (root / "production_source/SHA256SUMS").exists()


def test_coordinated_stable_metadata_remains_nonproduction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_release_fixture(tmp_path, monkeypatch)
    for filename in ("platform_release/pyproject.toml", "Dockerfile.platform",
                     "compose.platform.yaml"):
        _update_version(root, filename, "0.4.0")
    report = a6_release_preflight.check()
    assert report["preview_version"] == "0.4.0"
    assert report["preview_runtime_enabled"] is False
    assert report["legacy_database_attached"] is False


@pytest.mark.parametrize("filename", [
    "platform_release/pyproject.toml", "Dockerfile.platform", "compose.platform.yaml",
])
def test_unsynchronized_release_versions_refuse_before_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str,
) -> None:
    root = _copy_release_fixture(tmp_path, monkeypatch)
    _update_version(root, filename, "0.4.0")
    with pytest.raises(ValueError, match="A6_"):
        a6_release_preflight.check()


@pytest.mark.parametrize("bad", ["4.0.0", "0.4.0rc2", "0.4.0+local", "0.3.2"])
def test_invalid_metadata_refused_without_writing_build_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str,
) -> None:
    root = _copy_release_fixture(tmp_path, monkeypatch)
    _update_version(root, "platform_release/pyproject.toml", bad)
    target = tmp_path / "fresh-wheel-source"
    with pytest.raises(ValueError, match="A6_UNEXPECTED_PLATFORM_METADATA"):
        a6_prepare_package.prepare(target)
    assert not target.exists()


@pytest.mark.parametrize("release", ["0.4.0rc1", "0.4.0"])
def test_prepared_source_reports_actual_release_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release: str,
) -> None:
    root = _copy_release_fixture(tmp_path, monkeypatch)
    if release != "0.4.0rc1":
        _update_version(root, "platform_release/pyproject.toml", release)
    target = tmp_path / "fresh-wheel-source"
    report = a6_prepare_package.prepare(target)
    assert report["version"] == release
    assert report["source_was_mutated"] is False
    assert (target / "naseri_markets/platform_cli.py").is_file()
    assert (target / "pyproject.toml").is_file()
