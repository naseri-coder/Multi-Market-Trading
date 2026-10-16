"""R32 stopped-state recovery *REVIEW* of four distinct offline ledgers.

Uses the existing Stage18 read-only evaluator and intentionally returns no
restoration, job replay, backfill, risk release, Telegram or trading grant.
Never point at active/live sources. The caller asserts writer shutdown and
supplies already frozen, private, consistent offline snapshot paths.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter

from .operational_reconciliation_v1 import (
    RecoveryPaths, evaluate_operational_recovery,
)


class R32RecoveryRefused(ValueError):
    """Constant rejection, no private ledger contents in errors."""


def review_r32_stopped_snapshots(
    paths: RecoveryPaths, *, all_writers_stopped: bool = False,
    operator_ack: bool = False,
) -> dict:
    if (operator_ack is not True or all_writers_stopped is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise R32RecoveryRefused("R32_STOP_WRITERS_AND_APPROVE_NONPRODUCTION")
    if type(paths) is not RecoveryPaths:
        raise R32RecoveryRefused("R32_EXACT_STAGE18_FOUR_ROLES_REQUIRED")
    # Stage18 validates role isolation, on-disk mode/ownership/bounds,
    # SQLite integrity, local identities and hash-chain evidence. It never
    # repairs existing risk, order, signal or runtime state.
    report = evaluate_operational_recovery(paths)
    if (report.broker_authorized is not False
            or report.telegram_authorized is not False
            or report.live_authorized is not False
            or report.replay_authorized is not False):
        raise R32RecoveryRefused("R32_STAGE18_AUTHORIZATION_DRIFT")
    categories = Counter(f.verdict for f in report.jobs)
    payload = {
        "protocol": "MMT_R32_FOUR_LEDGER_STOPPED_RECOVERY_REVIEW_V1",
        "source_stage18_evidence_sha256": report.evidence_sha256,
        "cross_ledger_evidence_sha256": report.cross_ledger_evidence_sha256,
        "cross_ledger_verdict": report.cross_ledger_verdict,
        "stage18_status": report.status,
        "jobs_examined": len(report.jobs),
        "blocking_jobs": report.blocking_jobs,
        "unverified_done_jobs": report.unverified_done_jobs,
        "verdict_counts": dict(sorted(categories.items())),
        "disposition": "STOPPED_SNAPSHOT_REVIEW_ONLY_MANUAL_DECISION_REQUIRED",
        "writer_shutdown_independently_attested": False,
        "four_snapshots_externally_authenticated": False,
        "independent_db_consistency_at_capture_proven": False,
        "operator_review_required": True,
        "checkpoint_restore_performed": False,
        "backup_created": False,
        "retry_authorized": False,
        "order_resubmission_authorized": False,
        "risk_release_authorized": False,
        "telegram_send_authorized": False,
        "live_trading_authorized": False,
        "production_modified": False,
    }
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    payload["local_review_sha256"] = hashlib.sha256(raw).hexdigest()
    return payload


__all__ = ["R32RecoveryRefused", "review_r32_stopped_snapshots"]
