"""Read-only Stage-19 exact Job-to-Effect evidence audit; no commands to replay."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from naseri_markets import job_effect_intent_v1, job_effect_reconciliation_v1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effects", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--paper", required=True, type=Path)
    parser.add_argument("--signal", required=True, type=Path)
    parser.add_argument("--ack-offline-readonly", action="store_true")
    args = parser.parse_args(argv)
    try:
        if (not args.ack_offline_readonly
                or os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_PRODUCTION") == "1"):
            raise job_effect_intent_v1.IntentRefused("EXPLICIT_OFFLINE_AUDIT_REQUIRED")
        report = job_effect_reconciliation_v1.evaluate_effect_evidence(
            job_effect_reconciliation_v1.EffectEvidencePaths(
                args.effects, args.runtime, args.paper, args.signal,
            )
        )
    except (job_effect_intent_v1.IntentRefused, OSError, sqlite3.Error,
            ValueError, TypeError) as exc:
        print("STAGE19_EVIDENCE_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report.as_dict(), sort_keys=True, allow_nan=False))
    return 0 if report.blocking_effects == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
