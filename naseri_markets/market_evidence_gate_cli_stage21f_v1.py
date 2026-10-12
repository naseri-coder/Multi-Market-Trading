"""Explicit Stage21F controls: 2 public Funding reads or offline audit.

The optional 'corroborate' action observes KuCoin AGAIN, not an independent
market-data provider. The 'audit' command has zero network operations.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .market_evidence_gate_stage21f_v1 import (
    evaluate_market_evidence_gate, recapture_funding_for_comparison,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("corroborate")
    compare.add_argument("--bundle-dir", type=Path, required=True)
    compare.add_argument("--ack-two-public-gets", action="store_true")
    audit = sub.add_parser("audit")
    audit.add_argument("--bundle-dir", type=Path, required=True)
    audit.add_argument("--paper-db", type=Path)
    audit.add_argument("--ack-offline-readonly", action="store_true")
    audit.add_argument("--permit-no-recheck", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "corroborate":
            result = recapture_funding_for_comparison(
                args.bundle_dir, operator_ack=args.ack_two_public_gets)
        else:
            result = evaluate_market_evidence_gate(
                args.bundle_dir, operator_ack=args.ack_offline_readonly,
                paper_path=args.paper_db,
                require_recheck=not args.permit_no_recheck)
    except (ValueError, TypeError, OSError, RuntimeError, KeyError):
        print("STAGE21F_RESEARCH_EVIDENCE_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
