#!/usr/bin/env python3
"""Manual Android Termux/Brooks R23 witness preparation and research capture.

Usage is deliberately three separate operator-invoked commands. No cron,
background process, funding settlement or live/PAPER order is implemented.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from naseri_markets.brooks_forward_source_custody_stage21g_v1 import (
    run_stage21g_manual_first_window,
)
from naseri_markets.brooks_termux_readiness_mmt_r23_v1 import (
    stage23_offline_witness_preflight,
    stage23_prepare_witness_from_original_zip,
)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Brooks V5 real original RFC3161 witness; no PAPER/live trading",
    )
    parser.add_argument(
        "--ack-research-only",
        action="store_true",
        help="Explicitly confirm local nonproduction research; never authorize orders",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Verify and unpack exact original FreeTSA ZIP")
    prepare.add_argument("--original-zip", required=True, type=Path)
    prepare.add_argument("--evidence-dir", required=True, type=Path)
    preflight = commands.add_parser("status", help="Offline check of original witness and clock")
    preflight.add_argument("--evidence-dir", required=True, type=Path)
    capture = commands.add_parser(
        "capture",
        help="ONE live read-only public Binance HTTPS GET inside precommitted study window",
    )
    capture.add_argument("--evidence-dir", required=True, type=Path)
    capture.add_argument("--output-dir", required=True, type=Path)
    capture.add_argument("--bars", required=True, type=int, choices=(1, 4, 16, 32, 96))
    capture.add_argument(
        "--confirm-one-readonly-public-get",
        required=True,
        choices=("I_APPROVE_ONE_READONLY_PUBLIC_BINANCE_GET",),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = make_parser().parse_args(argv)
    if not args.ack_research_only or os.environ.get("MMT_NONPRODUCTION") != "1":
        raise SystemExit("R23_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if os.environ.get("MMT_PRODUCTION") == "1":
        raise SystemExit("R23_PRODUCTION_FORBIDDEN")
    if args.command == "prepare":
        report = stage23_prepare_witness_from_original_zip(
            original_zip=args.original_zip,
            destination=args.evidence_dir,
            operator_ack=True,
        )
        report = {
            "status": "ORIGINAL_EXTERNAL_WITNESS_PREPARED_OFFLINE_ONLY",
            "original_zip_sha256": report["source_original_zip_sha256"],
            "canonical_plan_sha256": report["canonical_plan_sha256"],
            "timestamper_signed_utc": report["externally_signed_timestamp_utc"],
            "market_source_captured": False,
        }
    elif args.command == "status":
        report = stage23_offline_witness_preflight(
            evidence_directory=args.evidence_dir,
            at_utc=datetime.now(UTC),
            operator_ack=True,
        )
    else:
        # Only an operator-initiated capture command reaches Stage21G.
        # Stage21G independently refuses any request outside the signed
        # study window and does not have an order/trading adapter.
        report = stage23_offline_witness_preflight(
            evidence_directory=args.evidence_dir,
            at_utc=datetime.now(UTC),
            operator_ack=True,
        )
        os.environ["ST21G_EXPLICIT_MANUAL_CAPTURE"] = "1"
        observed = run_stage21g_manual_first_window(
            witness_directory=args.evidence_dir,
            destination=args.output_dir,
            number_of_closed_bars=args.bars,
            operator_ack=True,
        )
        report = {
            "status": "FIRST_MANUAL_PUBLIC_HTTPS_SOURCE_QUARANTINED_ONLY",
            "raw_original_binance_body_sha256": observed["original_body_sha256"],
            "tls_http_trace_sha256": observed["receipt_sha256"],
            "canonical_plan_sha256": report["canonical_frozen_plan_sha256"],
            "source_origin_independently_signed": False,
            "actual_brooks_trades_executed": False,
            "paper_mode_enabled": False,
            "live_orders_authorized": False,
        }
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
