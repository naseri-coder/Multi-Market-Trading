"""Stage-13 read-only OFFLINE evidence gate; never performs network or trading."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from naseri_markets.reliability_acceptance_v1 import (
    AcceptanceRefused, LedgerPaths, evaluate_offline_reliability,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-db", type=Path, required=True)
    parser.add_argument("--paper-db", type=Path, required=True)
    parser.add_argument("--signal-db", type=Path, required=True)
    parser.add_argument("--ack-offline-readonly", action="store_true")
    args = parser.parse_args(argv)
    if (not args.ack_offline_readonly or os.getenv("MMT_NONPRODUCTION") != "1"
            or os.getenv("MMT_PRODUCTION") == "1"):
        print("STAGE13_REFUSED:EXPLICIT_OFFLINE_FENCE_REQUIRED", file=sys.stderr)
        return 2
    try:
        result = evaluate_offline_reliability(
            LedgerPaths(args.control_db, args.paper_db, args.signal_db))
    except (AcceptanceRefused, OSError, ValueError):
        print("STAGE13_REFUSED:INVALID_EVIDENCE", file=sys.stderr)
        return 2
    print(json.dumps(result.as_dict(), sort_keys=True, ensure_ascii=True))
    return 0 if result.integrity_verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
