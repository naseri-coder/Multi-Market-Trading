"""Stage21G manual capture entrypoint: no background task, no broker, no retry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from naseri_markets.brooks_forward_source_custody_stage21g_v1 import (
    run_stage21g_manual_first_window,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit one-shot, read-only initial Brooks study Klines capture",
    )
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--bars", required=True, type=int, choices=(1, 4, 16, 32, 96))
    parser.add_argument("--ack-research-only", action="store_true")
    arguments = parser.parse_args()
    result = run_stage21g_manual_first_window(
        witness_directory=arguments.evidence_dir,
        destination=arguments.output_dir,
        number_of_closed_bars=arguments.bars,
        operator_ack=arguments.ack_research_only,
    )
    # Only public digests, not source-response bodies or future-trade data.
    print(json.dumps({
        "stage": result["protocol"] if "protocol" in result else "STAGE21G",
        "original_source_bytes_sha256": result["original_body_sha256"],
        "post_admission_receipt_sha256": result["post_admission_receipt_sha256"],
        "transport_receipt_sha256": result["receipt_sha256"],
        "source_origin_independently_attested": False,
        "connected_paper_enabled": False,
        "live_trading_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
