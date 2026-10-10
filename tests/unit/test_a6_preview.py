"""A6-only tests; offline release preview, not live runtime."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import pytest
from naseri_markets import platform_cli
from scripts.a6_prepare_package import prepare
from scripts.a6_release_preflight import check

ROOT = Path(__file__).resolve().parents[2]


def test_historical_release_identity_unchanged():
    result = check()
    assert result["legacy_version"] == "0.3.2"
    assert result["preview_version"] == "0.4.0rc1"
    assert result["legacy_database_attached"] is False
    assert result["database_migration_executed"] is False


def test_staging_matches_public_source(tmp_path):
    target = tmp_path / "a6-new"
    result = prepare(target)
    assert result["module_count"] >= 14
    assert result["source_was_mutated"] is False
    assert "naseri_markets/platform_cli.py" in result["sha256"]
    for name, digest in result["sha256"].items():
        copied = target / name
        source = ROOT / name if name.startswith("naseri_markets/") else ROOT / "platform_release" / name
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == digest
        assert source.read_bytes() == copied.read_bytes()


def test_staging_refuses_overwrite(tmp_path):
    dst = tmp_path / "existing"
    dst.mkdir()
    with pytest.raises(ValueError, match="OUTPUT_MUST_NOT_EXIST"):
        prepare(dst)


def test_staging_refuses_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="OUTPUT_MUST_NOT_EXIST"):
        prepare(link)


def test_offline_cli_advertises_no_runtime(monkeypatch, capsys):
    monkeypatch.setattr(platform_cli, "_installed_version", lambda: "0.4.0rc1")
    assert platform_cli.main(["--check"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["registered_engines"] == 0
    assert result["mode"] == "OFFLINE_PREVIEW"
    assert not any(result[k] for k in ("network_enabled", "orders_enabled", "telegram_enabled"))


def test_cli_manifest_is_all_disabled(monkeypatch, capsys):
    monkeypatch.setattr(platform_cli, "_installed_version", lambda: "0.4.0rc1")
    assert platform_cli.main(["--engine-plan", str(ROOT / "examples/engine-plan.example.json")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "OFFLINE_PLAN_ONLY"
    assert all(e["enabled"] is False for e in result["engines"])


def test_cli_wrong_distribution_fails_closed(monkeypatch):
    monkeypatch.setattr(platform_cli, "_installed_version", lambda: "0.3.2")
    assert platform_cli.main(["--check"]) == 2


def test_cli_invalid_manifest_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(platform_cli, "_installed_version", lambda: "0.4.0rc1")
    p = tmp_path / "plan.json"
    p.write_text('{"schema_version":1,"engines":[]}', encoding="utf-8")
    assert platform_cli.main(["--engine-plan", str(p)]) == 2


def test_no_private_strategy_modules_imported():
    forbidden = {"r0_engine", "private_nyfr_core"}
    for p in (ROOT / "naseri_markets").glob("*.py"):
        assert p.stem not in forbidden
        for n in ast.walk(ast.parse(p.read_bytes())):
            if isinstance(n, ast.Import):
                assert all(alias.name.split(".")[0] not in forbidden for alias in n.names)
            if isinstance(n, ast.ImportFrom):
                assert (n.module or "").split(".")[0] not in forbidden


def test_platform_compose_is_not_a_live_service():
    content = (ROOT / "compose.platform.yaml").read_text()
    assert 'profiles: ["validation"]' in content
    assert "network_mode: none" in content
    assert "read_only: true" in content
    for disallowed in ("ports:", "postgres_data", "telegram", "privileged: true"):
        assert disallowed not in content


def test_frozen_legacy_release_is_not_renamed():
    p = (ROOT / "pyproject.toml").read_text()
    assert 'name = "crypto-price-action"' in p
    assert 'version = "0.3.2"' in p
    assert len((ROOT / "production_source/SHA256SUMS").read_text().splitlines()) == 362
    assert "name: crypto-price-action" in (ROOT / "compose.yaml").read_text()
