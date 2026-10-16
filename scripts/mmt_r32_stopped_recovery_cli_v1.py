"""Offline four-ledger Stage18 review CLI; never a restore or dispatcher."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from naseri_markets.mmt_r32_stopped_recovery_review_v1 import (
    R32RecoveryRefused, review_r32_stopped_snapshots,
)
from naseri_markets.operational_reconciliation_v1 import RecoveryPaths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R32 read-only stopped-state review (NO restore/retry)"
    )
    for role in ("runtime", "control", "paper", "signal"):
        parser.add_argument("--" + role, type=Path, required=True)
    parser.add_argument("--all-writers-stopped", action="store_true")
    parser.add_argument("--ack-nonproduction-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = review_r32_stopped_snapshots(
            RecoveryPaths(
                runtime=args.runtime.absolute(), control=args.control.absolute(),
                paper=args.paper.absolute(), signal=args.signal.absolute(),
            ),
            all_writers_stopped=args.all_writers_stopped,
            operator_ack=args.ack_nonproduction_review,
        )
    except (ValueError, OSError, R32RecoveryRefused):
        print(json.dumps({
            "status": "REFUSED_MANUAL_REVIEW_REQUIRED",
            "retry_authorized": False, "live_trading_authorized": False,
            "production_modified": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
