"""R29 manual read-only audit of retained original-source shadow decisions.

The audit never starts the Brooks worker, requests market data, retries an
unknown side effect, sends Telegram, or routes a broker order.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from naseri_markets.brooks_future_shadow_paper_mmt_r29_v1 import R29ShadowRefused
from naseri_markets.mmt_r29_shadow_session_audit_v1 import (
    audit_r29_original_source_shadow_session,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only validate every retained R29 original-source decision"
    )
    parser.add_argument("--witness-dir", required=True, type=Path)
    parser.add_argument("--batch-dir", required=True, action="append", type=Path)
    parser.add_argument("--receipt", action="append", type=Path, default=[])
    parser.add_argument("--ack-nonproduction-readonly", action="store_true")
    args = parser.parse_args(argv)
    if (args.ack_nonproduction_readonly is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        parser.error("R29_READONLY_NONPRODUCTION_ACK_REQUIRED")
    try:
        result = audit_r29_original_source_shadow_session(
            witness_directory=args.witness_dir.absolute(),
            previous_directories=tuple(p.absolute() for p in args.batch_dir),
            shadow_receipts=tuple(p.absolute() for p in args.receipt),
            operator_ack=True,
        )
    except (R29ShadowRefused, ValueError, OSError):
        print(json.dumps({
            "protocol": "MMT_R29_SHADOW_SESSION_CLI",
            "status": "REFUSED_REVIEW_REQUIRED",
            "orders_sent": False,
        }))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
