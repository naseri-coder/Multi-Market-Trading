"""Offline SDK CLI; import/inspect never executes a third-party plugin.

Run: python -m scripts.mmt_core_sdk_v1 pack --manifest <json> --source <py> --output <zip>
Or : python -m scripts.mmt_core_sdk_v1 inspect --bundle <zip>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from naseri_markets.core_certification_v1 import evaluate_candidate
from naseri_markets.core_developer_sdk_v1 import _parse_json, build_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    cmd = parser.add_subparsers(dest="action", required=True)
    pack = cmd.add_parser("pack")
    pack.add_argument("--manifest", type=Path, required=True)
    pack.add_argument("--source", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    inspect = cmd.add_parser("inspect")
    inspect.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "pack":
        declaration = _parse_json(args.manifest.read_bytes(), max_size=8_192)
        out = build_package(declaration, args.source.read_bytes())
        if args.output.exists() or args.output.is_symlink():
            parser.error("refusing to overwrite an existing package")
        args.output.write_bytes(out)
        print(json.dumps({"mode": "OFFLINE_PACKAGE_ONLY", "bytes": len(out)}))
    else:
        report = evaluate_candidate(args.bundle.read_bytes())
        print(json.dumps({
            "status": report.status, "core_id": report.core_id,
            "artifact_sha256": report.artifact_sha256,
            "source_sha256": report.source_sha256,
            "blockers": report.blockers,
            "approved_for_execution": report.approved_for_execution,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
