"""Multi Market Trading standalone preview CLI, without live network or trading."""
from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .engine_plan import plan


def _installed_version() -> str:
    try:
        return version("multi-market-trading")
    except PackageNotFoundError as exc:
        raise RuntimeError("A6_DISTRIBUTION_NOT_INSTALLED") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--engine-plan", type=Path)
    args = parser.parse_args(argv)
    try:
        release = _installed_version()
        if release != "0.4.0rc1":
            raise ValueError("UNEXPECTED_RELEASE_VERSION")
        if args.engine_plan is not None:
            engines = plan(args.engine_plan)
            output = {
                "version": release,
                "mode": "OFFLINE_PLAN_ONLY",
                "engines": [{
                    "id": e.engine_id,
                    "market": e.market,
                    "status": e.status,
                    "enabled": False,
                } for e in engines],
                "network_enabled": False,
                "orders_enabled": False,
                "telegram_enabled": False,
            }
        else:
            output = {
                "product": "Multi Market Trading",
                "distribution": "multi-market-trading",
                "version": release,
                "mode": "OFFLINE_PREVIEW",
                "registered_engines": 0,
                "network_enabled": False,
                "orders_enabled": False,
                "telegram_enabled": False,
                "legacy_database_attached": False,
            }
    except (RuntimeError, ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        # Do not leak secrets, file content, account details or private paths.
        print(f"A6_PREVIEW_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
