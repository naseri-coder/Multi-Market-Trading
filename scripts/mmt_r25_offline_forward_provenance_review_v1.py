#!/usr/bin/env python3
"""R25 offline CLI for Brooks future evidence policy and correction review.

No HTTP calls, exchange secrets, background work, PAPER or broker adapter.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from naseri_markets.brooks_forward_source_governance_mmt_r25_v1 import (
    r25_fixed_manual_96bar_schedule,
    r25_offline_chain_governance,
    r25_record_untrusted_revision_observation,
)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Research-only offline policy for the original Brooks V5 study",
    )
    parser.add_argument("--ack-research-only", action="store_true")
    parser.add_argument("--witness-dir", type=Path, required=True)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser(
        "schedule", help="Verify the original stamped plan; print 14 manual windows",
    )
    audit = commands.add_parser(
        "audit", help="Recheck original source chain and provenance flags offline",
    )
    audit.add_argument(
        "--prior-batch-dir", action="append", type=Path, default=[],
        help="All previous successful batches oldest first; may be empty",
    )
    later = commands.add_parser(
        "compare", help="Journal untrusted later bytes without replacing originals",
    )
    later.add_argument("--prior-batch-dir", action="append", type=Path, required=True)
    later.add_argument("--target-batch-index", required=True, type=int)
    later.add_argument("--later-original-response", required=True, type=Path)
    later.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = create_parser().parse_args(argv)
    if (args.ack_research_only is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise SystemExit("R25_EXPLICIT_NONPRODUCTION_RESEARCH_APPROVAL_REQUIRED")
    now = datetime.now(UTC)
    if args.action == "schedule":
        result = r25_fixed_manual_96bar_schedule(
            witness_directory=args.witness_dir,
            as_of_utc=now,
            operator_ack=True,
        )
    elif args.action == "audit":
        result = r25_offline_chain_governance(
            witness_directory=args.witness_dir,
            previous_directories=tuple(args.prior_batch_dir),
            as_of_utc=now,
            operator_ack=True,
        )
    else:
        result = r25_record_untrusted_revision_observation(
            witness_directory=args.witness_dir,
            previous_directories=tuple(args.prior_batch_dir),
            target_batch_index=args.target_batch_index,
            later_original_body_path=args.later_original_response,
            destination=args.output_dir,
            operator_observed_at_utc=now,
            operator_ack=True,
        )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
