"""A5 identity and module planning tests; no network, Docker or credentials."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from naseri_markets.engine_plan import plan

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/engine-plan.example.json"


def test_offline_plan_bundled_legacy_and_private_excluded():
    items = plan(EXAMPLE)
    assert len(items) == 2
    assert {row.engine_id for row in items} == {"brooks_crypto", "nyfr"}
    assert all(not row.enabled for row in items)
    assert next(row for row in items if row.engine_id == "nyfr").status == (
        "PRIVATE_PROVISIONING_REQUIRED"
    )


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"schema_version": 2}),
    lambda d: d["engines"][0].update({"enabled": True}),
    lambda d: d["engines"][1].update({"enabled": 1}),
    lambda d: d["engines"][0].update({"source": "https://secret.example"}),
    lambda d: d["engines"][0].update({"extra": "secret"}),
    lambda d: d["engines"][1].update({"engine_id": "brooks_crypto"}),
    lambda d: d["engines"][0].update({"market": "unknown"}),
    lambda d: d["engines"][0].update({"version": "../secret"}),
])
def test_plan_rejects_unsafe_configuration(tmp_path, mutate):
    content = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    mutate(content)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError):
        plan(path)


def test_plan_rejects_duplicate_json_properties(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1,"engines":[]}')
    with pytest.raises(ValueError, match="DUPLICATE_MANIFEST_KEY"):
        plan(path)


def test_plan_refuses_symlink_to_manifest(tmp_path):
    link = tmp_path / "external.json"
    link.symlink_to(EXAMPLE)
    with pytest.raises(ValueError):
        plan(link)


def test_identity_preflight_is_compatibility_only():
    result = subprocess.run(
        [sys.executable, "scripts/identity_preflight.py", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["repository"] == "naseri-coder/Multi-Market-Trading"
    assert data["historical_volume"] == "crypto-price-action_postgres_data"
    assert data["historical_version"] == "0.3.2"
    assert data["runtime_migration_performed"] is False
    assert data["live_trading_approved"] is False


def test_identity_preflight_rejects_volume_rename(tmp_path):
    from scripts.identity_preflight import inspect

    root = tmp_path
    (root / "scripts/lib").mkdir(parents=True)
    (root / "production_source").mkdir()
    (root / "naseri_markets").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname="crypto-price-action"\nversion="0.3.2"\n'
        '[project.scripts]\ncrypto-signal-bot="app.main:cli"\n'
    )
    (root / "compose.yaml").write_text(
        "name: multi-market-trading\nimage: crypto-price-action:v0.3.2\n"
        "postgres_data:/var/lib/postgresql/data\n"
    )
    (root / "scripts/lib/manager_common.sh").write_text("")
    (root / "Dockerfile.production").write_text("")
    with pytest.raises(ValueError, match="LEGACY_COMPOSE_PROJECT_CHANGED"):
        inspect(root)


def test_compatibility_and_canonical_launchers_do_not_mutate_config():
    for name in ("markets.sh", "naseri.sh"):
        script = (ROOT / name).read_text()
        assert "exec bash" in script
        assert "scripts/manager.sh" in script
        assert "docker compose" not in script
