"""Inspect four already-existing OFFLINE snapshots; never execute jobs."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from naseri_markets.offline_recovery_review_v1 import record_operator_review
from naseri_markets.operational_reconciliation_v1 import (
    RecoveryPaths, RecoveryRefused, evaluate_operational_recovery,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("runtime", "control", "paper", "signal"):
        parser.add_argument("--" + field + "-db", type=Path, required=True)
    parser.add_argument("--ack-nonproduction-readonly", action="store_true")
    parser.add_argument("--review-db", type=Path)
    parser.add_argument("--review-job")
    parser.add_argument("--evidence-sha256")
    parser.add_argument("--operator-id", type=int)
    parser.add_argument("--review-note")
    parser.add_argument("--ack-all-workers-stopped", action="store_true")
    parser.add_argument("--ack-manual-review", action="store_true")
    args = parser.parse_args(argv)
    if not args.ack_nonproduction_readonly:
        print("STAGE18_REFUSED:ACK_REQUIRED", file=sys.stderr)
        return 2
    paths = RecoveryPaths(args.runtime_db, args.control_db, args.paper_db, args.signal_db)
    try:
        if any(v is not None for v in (args.review_db, args.review_job,
                                       args.evidence_sha256, args.operator_id,
                                       args.review_note)):
            if any(v is None for v in (args.review_db, args.review_job,
                                       args.evidence_sha256, args.operator_id,
                                       args.review_note)):
                raise RecoveryRefused("COMPLETE_REVIEW_ARGUMENTS_REQUIRED")
            output = record_operator_review(
                paths, args.review_db, job_id=args.review_job,
                evidence_sha256=args.evidence_sha256, note=args.review_note,
                operator_id=args.operator_id,
                operator_ack=args.ack_manual_review,
                all_workers_stopped=args.ack_all_workers_stopped)
        else:
            output = evaluate_operational_recovery(paths).as_dict()
    except (RecoveryRefused, sqlite3.Error, OSError, TypeError) as exc:
        print("STAGE18_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
