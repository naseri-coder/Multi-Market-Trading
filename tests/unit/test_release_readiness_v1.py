"""Stage-15 source-only gates: deny release even after an excellent unit run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from naseri_markets.release_readiness_v1 import (
    ReadinessRefused, _REQUIRED, evaluate_source_readiness,
)
from scripts.mmt_stage15_readiness import main as gate_main


def fake_repo(tmp_path: Path):
    (tmp_path / "platform_release").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="crypto-price-action"\nversion="0.3.2"\n', encoding="utf-8")
    (tmp_path / "platform_release/pyproject.toml").write_text(
        '[project]\nname="multi-market-trading"\nversion="0.4.0rc1"\n'
        '[project.scripts]\nnaseri-markets="naseri_markets.platform_cli:main"\n',
        encoding="utf-8",
    )
    for rel in _REQUIRED.values():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# safe offline fixture\n', encoding="utf-8")
    return tmp_path


def test_required_source_present_but_product_still_blocked(tmp_path):
    repo = fake_repo(tmp_path)
    result = evaluate_source_readiness(repo)
    assert result.schema_version == 1
    assert result.source_verdict == "SOURCE_PREFLIGHT_PASS"
    assert result.offline_preview_candidate
    assert result.release_verdict == "PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE"
    assert not result.live_orders_authorized and not result.telegram_publication_authorized
    assert not result.untrusted_plugins_authorized and not result.production_deployment_authorized
    assert len(result.release_blockers) >= 8
    assert all(x.status == "UNVERIFIED_BLOCKER" for x in result.release_blockers)
    assert json.loads(result.json()) == result.to_dict()
    assert result == evaluate_source_readiness(repo)


def test_missing_module_fail_closed(tmp_path):
    repo = fake_repo(tmp_path)
    (repo / _REQUIRED["control_center"]).unlink()
    result = evaluate_source_readiness(repo)
    assert result.source_verdict == "SOURCE_PREFLIGHT_BLOCKED"
    assert not result.offline_preview_candidate
    assert any(x.code == "MODULE_CONTROL_CENTER" and x.status == "MISSING"
               for x in result.source_gates)
    assert not result.production_deployment_authorized


@pytest.mark.parametrize("bad_version,bad_name", [
    ("0.4.0", "multi-market-trading"),
    ("0.4.0rc1", "fake-preview"),
])
def test_preview_identity_and_version_drift_block(tmp_path, bad_version, bad_name):
    repo = fake_repo(tmp_path)
    (repo / "platform_release/pyproject.toml").write_text(
        '[project]\nname="' + bad_name + '"\nversion="' + bad_version + '"\n'
        '[project.scripts]\nnaseri-markets="naseri_markets.platform_cli:main"\n',
        encoding="utf-8",
    )
    assert evaluate_source_readiness(repo).source_verdict == "SOURCE_PREFLIGHT_BLOCKED"


def test_legacy_identity_drift_blocks(tmp_path):
    repo = fake_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project]\nname="wrong"\nversion="1"\n')
    assert not evaluate_source_readiness(repo).offline_preview_candidate


def test_missing_preview_entrypoint_blocks(tmp_path):
    repo = fake_repo(tmp_path)
    (repo / "platform_release/pyproject.toml").write_text(
        '[project]\nname="multi-market-trading"\nversion="0.4.0rc1"\n',
        encoding="utf-8")
    assert evaluate_source_readiness(repo).source_verdict == "SOURCE_PREFLIGHT_BLOCKED"


def test_symlink_module_refused(tmp_path):
    repo = fake_repo(tmp_path)
    source = repo / _REQUIRED["contract_fixture"]
    source.unlink()
    source.symlink_to(repo / _REQUIRED["core_api"])
    with pytest.raises(ReadinessRefused, match="SYMLINK"):
        evaluate_source_readiness(repo)


def test_malformed_toml_refused_without_public_release(tmp_path):
    repo = fake_repo(tmp_path)
    (repo / "pyproject.toml").write_text('[project\ninvalid')
    with pytest.raises(ReadinessRefused, match="PYPROJECT"):
        evaluate_source_readiness(repo)


def test_nonexistent_directory_refused(tmp_path):
    with pytest.raises(ReadinessRefused, match="REPOSITORY"):
        evaluate_source_readiness(tmp_path / "not-exists")


def test_cli_requires_ack_and_offline_env(tmp_path, monkeypatch, capsys):
    repo = fake_repo(tmp_path)
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    assert gate_main(["--repository", str(repo), "--ack-source-audit"]) == 2
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    assert gate_main(["--repository", str(repo)]) == 2
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    assert gate_main(["--repository", str(repo), "--ack-source-audit"]) == 2
    monkeypatch.delenv("MMT_PRODUCTION")
    assert gate_main(["--repository", str(repo), "--ack-source-audit"]) == 0
    actual = json.loads(capsys.readouterr().out)
    assert actual["source_verdict"] == "SOURCE_PREFLIGHT_PASS"
    assert actual["production_deployment_authorized"] is False


def test_cli_missing_source_exits_one(tmp_path, monkeypatch, capsys):
    repo = fake_repo(tmp_path)
    (repo / _REQUIRED["plugin_sdk"]).unlink()
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    assert gate_main(["--repository", str(repo), "--ack-source-audit"]) == 1
    assert json.loads(capsys.readouterr().out)["release_verdict"].startswith("PRODUCT_NOT_READY")


def test_source_digest_change_does_not_grant_permissions(tmp_path):
    repo = fake_repo(tmp_path)
    before = evaluate_source_readiness(repo)
    (repo / _REQUIRED["core_api"]).write_text("# change not production\n")
    after = evaluate_source_readiness(repo)
    assert before.inspected_sha256 != after.inspected_sha256
    assert before.release_verdict == after.release_verdict
    assert not before.public_signal_authorized and not after.public_signal_authorized


def test_python_source_size_limit_refuses(tmp_path):
    repo = fake_repo(tmp_path)
    (repo / _REQUIRED["market_data"]).write_bytes(b"x" * 256_001)
    with pytest.raises(ReadinessRefused, match="OVERSIZED"):
        evaluate_source_readiness(repo)
