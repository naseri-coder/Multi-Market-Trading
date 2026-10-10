"""Read-only canonical repository / frozen runtime identity preflight (A5).

Never talks to GitHub, Docker, PostgreSQL, Telegram or a broker. Never writes
or migrates data. Avoid conflating a GitHub rename with a runtime migration.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path


def inspect(root: Path) -> dict[str, object]:
    root = root.resolve(strict=True)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    metadata = project["project"]
    if metadata["name"] != "crypto-price-action" or metadata["version"] != "0.3.2":
        raise ValueError("FROZEN_DISTRIBUTION_IDENTITY_CHANGED")
    if metadata.get("scripts", {}).get("crypto-signal-bot") != "app.main:cli":
        raise ValueError("FROZEN_ENTRYPOINT_CHANGED")

    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    if re.search(r"(?m)^name: crypto-price-action$", compose) is None:
        raise ValueError("LEGACY_COMPOSE_PROJECT_CHANGED")
    if "postgres_data:/var/lib/postgresql/data" not in compose:
        raise ValueError("POSTGRES_VOLUME_CONTRACT_CHANGED")
    if "image: crypto-price-action:" not in compose:
        raise ValueError("HISTORIC_IMAGE_IDENTITY_CHANGED")

    script = (root / "scripts/lib/manager_common.sh").read_text(encoding="utf-8")
    official_url = "https://github.com/naseri-coder/Multi-Market-Trading"
    if f'PROJECT_URL="{official_url}"' not in script:
        raise ValueError("CANONICAL_REPOSITORY_URL_MISMATCH")
    if 'PROJECT_NAME="crypto-price-action"' not in script:
        raise ValueError("LEGACY_VOLUME_NAMESPACE_CHANGED")
    if 'OFFICIAL_SSH_REMOTE="git@github.com:naseri-coder/Multi-Market-Trading.git"' not in script:
        raise ValueError("OFFICIAL_SSH_ORIGIN_NOT_UPDATED")

    production = (root / "Dockerfile.production").read_text(encoding="utf-8")
    if 'LABEL org.opencontainers.image.title="Crypto Price Action"' not in production:
        raise ValueError("FROZEN_DOCKER_IMAGE_LABEL_CHANGED")
    if "COPY production_source/SHA256SUMS ./PRODUCTION_SOURCE_SHA256SUMS" not in production:
        raise ValueError("SOURCE_INTEGRITY_GUARD_MISSING")
    manifest = root / "production_source/SHA256SUMS"
    if not manifest.is_file() or len(manifest.read_text().splitlines()) != 362:
        raise ValueError("SOURCE_MANIFEST_SHAPE_CHANGED")

    forbidden = {"r0_engine", "private_nyfr_core"}
    public_dir = root / "naseri_markets"
    for path in public_dir.glob("*.py"):
        if path.is_symlink():
            raise ValueError("PUBLIC_MODULE_SYMLINK_REFUSED")
        if path.name.removesuffix(".py") in forbidden:
            raise ValueError("PRIVATE_ENGINE_IN_PUBLIC_SOURCE")
        tree = ast.parse(path.read_bytes(), filename=path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if name.name.split(".")[0] in forbidden:
                        raise ValueError("PUBLIC_IMPORTS_PRIVATE_ENGINE")
            if isinstance(node, ast.ImportFrom) and (
                (node.module or "").split(".")[0] in forbidden
            ):
                raise ValueError("PUBLIC_IMPORTS_PRIVATE_ENGINE")

    if not (root / "markets.sh").is_file() or not (root / "naseri.sh").is_file():
        raise ValueError("CANONICAL_AND_COMPAT_LAUNCHERS_REQUIRED")

    return {
        "repository": "naseri-coder/Multi-Market-Trading",
        "brand": "NASERI MARKETS",
        "historical_distribution": "crypto-price-action",
        "historical_version": "0.3.2",
        "historical_compose_project": "crypto-price-action",
        "historical_volume": "crypto-price-action_postgres_data",
        "canonical_launcher": "markets.sh",
        "compatibility_launcher": "naseri.sh",
        "private_core_in_public_source": False,
        "live_trading_approved": False,
        "runtime_migration_performed": False,
        "verdict": "A5_COMPATIBILITY_PREFLIGHT_PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(Path(__file__).resolve().parents[1])
    except (OSError, ValueError, KeyError, SyntaxError, tomllib.TOMLDecodeError) as exc:
        print(f"A5_IDENTITY_PREFLIGHT_FAIL: {type(exc).__name__}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
