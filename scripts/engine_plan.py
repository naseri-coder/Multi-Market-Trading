"""Read-only offline CLI: review proposed engines; never installs or enables."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


def main() -> int:
    # Allow direct `python scripts/engine_plan.py ...` before installation.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from naseri_markets.engine_plan import plan

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        rows = plan(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError):
        print("ENGINE_PLAN_REJECTED", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"schema_version": 1, "engines": [asdict(x) for x in rows]}))
    else:
        for item in rows:
            print(f"{item.engine_id} {item.market} {item.version}: {item.status}")
        print("PLAN_ONLY: no engine installed, loaded, enabled or connected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
