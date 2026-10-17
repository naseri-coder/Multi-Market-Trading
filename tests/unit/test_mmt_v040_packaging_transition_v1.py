"""Offline v0.4.0 RC/stable package staging regression; never installs code."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import scripts.a6_prepare_package as staging
import scripts.a6_release_preflight as preflight

REPO = Path(__file__).resolve().parents[2]


def fake_source(tmp_path, version):
    root = tmp_path / "public-checkout"
    for directory in ("platform_release", "naseri_markets", "production_source"):
        (root / directory).mkdir(parents=True)
    (root / "pyproject.toml").write_bytes((REPO / "pyproject.toml").read_bytes())
    original = (REPO / "platform_release/pyproject.toml").read_text()
    assert original.count('version = "0.4.0rc1"') == 1
    metadata = original.replace('version = "0.4.0rc1"', 'version = "' + version + '"')
    (root / "platform_release/pyproject.toml").write_text(metadata)
    (root / "platform_release/README.md").write_text("Isolated offline test fixture\n")
    (root / "naseri_markets/platform_cli.py").write_text('"""Synthetic inert module."""\n')
    (root / "compose.yaml").write_text(
        "name: crypto-price-action\n"
        "volumes:\n  postgres_data:\n"
        "services:\n  database:\n    volumes:\n"
        "      - postgres_data:/var/lib/postgresql/data\n"
    )
    (root / "compose.platform.yaml").write_text(
        'name: multi-market-trading\nprofiles: ["validation"]\n'
        "network_mode: none\nread_only: true\n"
    )
    (root / "Dockerfile.platform").write_text("USER 10001:10001\n")
    (root / "production_source/SHA256SUMS").write_text("untouched-test-sentinel\n")
    return root


@pytest.mark.parametrize("identity", ("0.4.0rc1", "0.4.0"))
def test_a6_preflight_and_source_staging_follow_exact_metadata(
    tmp_path, monkeypatch, identity
):
    root = fake_source(tmp_path, identity)
    monkeypatch.setattr(preflight, "ROOT", root)
    monkeypatch.setattr(staging, "ROOT", root)
    review = preflight.check()
    assert review["preview_version"] == identity
    assert review["legacy_version"] == "0.3.2"
    assert review["legacy_database_attached"] is False
    assert review["database_migration_executed"] is False
    assert review["preview_runtime_enabled"] is False
    dest = tmp_path / "new-staging"
    evidence = staging.prepare(dest)
    assert evidence["version"] == identity
    assert evidence["source_was_mutated"] is False
    assert (dest / "pyproject.toml").read_bytes() == (
        root / "platform_release/pyproject.toml"
    ).read_bytes()
    assert (root / "production_source/SHA256SUMS").read_text() == (
        "untouched-test-sentinel\n"
    )


@pytest.mark.parametrize("identity", (
    "v0.4.0", "4.0.0", "0.4.1", "0.4.0+untrusted", "0.4.0rc2",
))
def test_a6_unknown_release_refused_without_creating_output(
    tmp_path, monkeypatch, identity
):
    root = fake_source(tmp_path, identity)
    monkeypatch.setattr(preflight, "ROOT", root)
    monkeypatch.setattr(staging, "ROOT", root)
    with pytest.raises(ValueError, match="A6_VERSION_OR_NAME_MISMATCH"):
        preflight.check()
    dest = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="PACKAGE_METADATA_INVALID"):
        staging.prepare(dest)
    assert not dest.exists()


@pytest.mark.parametrize("identity", ("0.4.0rc1", "0.4.0"))
def test_a6_deferred_runtime_dependencies_fail_closed(
    tmp_path, monkeypatch, identity
):
    root = fake_source(tmp_path, identity)
    path = root / "platform_release/pyproject.toml"
    original = path.read_text()
    assert "dependencies = []" in original
    path.write_text(original.replace(
        "dependencies = []", 'dependencies = ["requests>=1"]', 1,
    ))
    monkeypatch.setattr(preflight, "ROOT", root)
    monkeypatch.setattr(staging, "ROOT", root)
    with pytest.raises(ValueError, match="UNREVIEWED_RUNTIME_DEPENDENCIES"):
        preflight.check()
    dest = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="PACKAGE_METADATA_INVALID"):
        staging.prepare(dest)
    assert not dest.exists()


def test_r38_signed_preview_installer_is_parseable():
    path = REPO / "scripts/mmt_r38_signed_offline_preview_install_v1.py"
    source = path.read_bytes()
    ast.parse(source, filename=str(path))
    assert b"import os\nfrom pathlib import Path\n" in source
    assert b"import osfrom pathlib import Path" not in source


def test_development_installer_remains_explicitly_nonproduction_only():
    script = (REPO / "scripts/install_platform_dev.sh").read_text()
    assert 'MMT_NONPRODUCTION:-' in script
    assert "-v MMT_PRODUCTION" in script
    assert 'id -u' in script
    assert 'RELEASE_VERSION="$(python3 -' in script
    assert 'multi_market_trading-${RELEASE_VERSION}-py3-none-any.whl' in script
    assert 'EXPECTED_PLATFORM_VERSION="$RELEASE_VERSION"' in script
    assert "--ack-isolated-dev-install" in script
