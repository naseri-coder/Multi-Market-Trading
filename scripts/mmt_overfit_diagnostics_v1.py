"""Explicit opt-in, read-only PBO/DSR research using a local frozen fixture."""
from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

from naseri_markets.research_overfit_diagnostics_v1 import (
    OverfitEvidenceRefused,
    analyze_overfit_fixture,
)

_MAX_FILE_BYTES = 2_000_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, help="Local pre-holdout return matrix JSON")
    parser.add_argument("--ack-research-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.ack_research_only:
        print("OVERFIT_RESEARCH_REFUSED:OFFLINE_ACK_REQUIRED", file=sys.stderr)
        return 2
    try:
        source = Path(args.matrix)
        if source.is_symlink() or not source.is_file():
            raise OverfitEvidenceRefused("LOCAL_REGULAR_MATRIX_REQUIRED")
        metadata = source.stat()
        if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= _MAX_FILE_BYTES:
            raise OverfitEvidenceRefused("BOUNDED_REGULAR_MATRIX_REQUIRED")
        with source.open("rb") as handle:
            raw = handle.read(_MAX_FILE_BYTES + 1)
        report = analyze_overfit_fixture(raw)
    except (OverfitEvidenceRefused, OSError, ValueError):
        print("OVERFIT_RESEARCH_REFUSED:FAIL_CLOSED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
