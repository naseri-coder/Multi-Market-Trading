"""Stage21E manual, explicit-only public market-risk research CLI.

Two separate operator actions: capture once (4 public GETs), then analyze
offline (0 HTTP calls). No brokers, credentials, or Telegram functionality.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from .public_funding_mark_stage21e_v1 import (
    analyze_funding_and_mark, capture_public_funding_and_mark,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    fetch = sub.add_parser("capture", help="4 explicit public-only GETs")
    fetch.add_argument("--bundle-dir", required=True, type=Path)
    fetch.add_argument("--ack-public-readonly-get", action="store_true")
    verify = sub.add_parser("analyze", help="Offline evidence and hypothetical risk")
    verify.add_argument("--bundle-dir", required=True, type=Path)
    verify.add_argument("--paper-db", type=Path,
                        help="Optional existing Stage21D PAPER SQLite evidence, strictly read-only")
    verify.add_argument("--mark-basis-limit", default="0.02")
    verify.add_argument("--assumed-leverage", default="5")
    verify.add_argument("--assumed-maintenance-rate", default="0.01")
    verify.add_argument("--ack-offline-research", action="store_true")
    options = parser.parse_args(argv)
    try:
        if options.mode == "capture":
            result = capture_public_funding_and_mark(
                options.bundle_dir, operator_ack=options.ack_public_readonly_get)
        else:
            result = analyze_funding_and_mark(
                options.bundle_dir, operator_ack=options.ack_offline_research,
                mark_dislocation_limit=Decimal(options.mark_basis_limit),
                hypothetical_leverage=Decimal(options.assumed_leverage),
                hypothetical_mmr=Decimal(options.assumed_maintenance_rate),
                paper_path=options.paper_db)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError):
        print("STAGE21E_PUBLIC_RISK_RESEARCH_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
