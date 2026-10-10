"""Fail-closed A6 identity and preservation checks; no network or writes."""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check() -> dict:
    historical = tomllib.loads((ROOT / "pyproject.toml").read_text())
    newer = tomllib.loads((ROOT / "platform_release/pyproject.toml").read_text())
    if historical["project"]["name"] != "crypto-price-action" or historical["project"]["version"] != "0.3.2":
        raise ValueError("HISTORICAL_PACKAGE_CHANGED")
    if newer["project"]["name"] != "multi-market-trading" or newer["project"]["version"] != "0.4.0rc1":
        raise ValueError("A6_VERSION_OR_NAME_MISMATCH")
    if newer["project"]["dependencies"]:
        raise ValueError("UNREVIEWED_RUNTIME_DEPENDENCIES")
    if newer["project"]["scripts"] != {"naseri-markets": "naseri_markets.platform_cli:main"}:
        raise ValueError("A6_CLI_INVALID")
    old_compose = (ROOT / "compose.yaml").read_text()
    if "\nname: crypto-price-action\n" not in "\n" + old_compose:
        raise ValueError("HISTORICAL_COMPOSE_IDENTITY_CHANGED")
    if "postgres_data:/var/lib/postgresql/data" not in old_compose:
        raise ValueError("HISTORICAL_VOLUME_MISSING")
    preview = (ROOT / "compose.platform.yaml").read_text()
    if "name: multi-market-trading" not in preview or 'profiles: ["validation"]' not in preview:
        raise ValueError("PREVIEW_NOT_ISOLATED")
    if "network_mode: none" not in preview or "read_only: true" not in preview:
        raise ValueError("PREVIEW_NETWORK_OR_FILESYSTEM_UNSAFE")
    for unsafe in ("postgres_data", "DATABASE_URL", "ports:", "privileged: true", "telegram"):
        if unsafe in preview:
            raise ValueError("PREVIEW_REQUIRES_FORBIDDEN_SERVICE")
    docker = (ROOT / "Dockerfile.platform").read_text()
    if "COPY production_source" in docker or "COPY . ." in docker:
        raise ValueError("A6_IMAGE_IMPORTS_HISTORICAL_SOURCE")
    if "USER 10001:10001" not in docker:
        raise ValueError("A6_IMAGE_MUST_BE_NONROOT")
    if not (ROOT / "production_source/SHA256SUMS").is_file():
        raise ValueError("FROZEN_MANIFEST_NOT_PRESENT")
    return {
        "verdict": "A6_SEPARATE_RELEASE_PREVIEW_PASS",
        "preview_version": "0.4.0rc1",
        "legacy_version": "0.3.2",
        "legacy_database_attached": False,
        "database_migration_executed": False,
        "nyfr_private_source_included": False,
        "preview_runtime_enabled": False,
    }


def main() -> int:
    try:
        print(json.dumps(check(), sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"A6_PREFLIGHT_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
