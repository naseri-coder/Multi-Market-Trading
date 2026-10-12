"""Read-only Stage 15 source audit. Exit 0 = SOURCE checks only, NOT release."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from naseri_markets.release_readiness_v1 import ReadinessRefused, evaluate_source_readiness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--ack-source-audit", action="store_true")
    args = parser.parse_args(argv)
    if (not args.ack_source_audit or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        print("STAGE15_REFUSED:NONPRODUCTION_ACK_REQUIRED", file=sys.stderr)
        return 2
    try:
        report = evaluate_source_readiness(args.repository)
    except (ReadinessRefused, OSError) as exc:
        print(f"STAGE15_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2
    print(report.json())
    return 0 if report.source_verdict == "SOURCE_PREFLIGHT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
