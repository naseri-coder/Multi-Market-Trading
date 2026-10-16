"""R28: one guarded, operator-invoked OFFLINE route over existing Stage 16/17.

This is an orchestration and audit facade, NOT a new trading strategy, risk
calculator, order sender, market adapter, multi-database transaction, or
permission to connect PAPER/LIVE. Stage 17 owns claims and restart fences;
Stage 16 owns the existing synthetic fixture data->strategy->risk->paper/no-send
handoff. Stage 18 audits four independent, stopped-state database snapshots.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from ._contract_acceptance_fixture_v1 import OfflineContractFixture
from .offline_runtime_supervisor_v1 import (
    OfflineRuntimeSupervisor,
    Stage16ReplayExecutor,
)
from .operational_reconciliation_v1 import (
    RecoveryPaths,
    evaluate_operational_recovery,
)


class R28RuntimeRefused(ValueError):
    """Operator-facing fail-closed condition."""


@dataclass(frozen=True, slots=True)
class R28RuntimeView:
    protocol: str
    state: str
    queue_counts: dict[str, int]
    unresolved_jobs: int
    done_without_exact_cross_ledger_proof: int
    path: str = "STAGE12_CONTROL_STAGE17_QUEUE_STAGE16_STRATEGY_RISK_PAPER_SIGNAL"
    mode: str = "NONPRODUCTION_SYNTHETIC_OR_REPLAY_ONLY"
    external_market_feed_connected: bool = False
    broker_order_enabled: bool = False
    telegram_send_enabled: bool = False
    connected_paper_enabled: bool = False
    live_enabled: bool = False
    atomic_cross_database_commit_proven: bool = False
    automatic_retry_enabled: bool = False


def _require_offline(operator_ack: bool) -> None:
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise R28RuntimeRefused("R28_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")


class R28UnifiedOfflineRuntime:
    """One *local* entrypoint. All four older ledgers retain their ownership.

    Explicit human invocation is required for every dispatch; no background
    daemon starts. Even a Stage17 DONE row proves only a hashed callback
    receipt, not exact journal side effects. Interrupted and quarantined work
    never resumes automatically.
    """

    def __init__(
        self,
        supervisor: OfflineRuntimeSupervisor,
        executor: Stage16ReplayExecutor,
        *,
        operator_ack: bool = False,
    ) -> None:
        _require_offline(operator_ack)
        if (type(supervisor) is not OfflineRuntimeSupervisor
                or type(executor) is not Stage16ReplayExecutor
                or type(executor.integration.core) is not OfflineContractFixture
                or supervisor.panel is not executor.integration.panel
                or supervisor.actor_id != executor.integration.actor_id):
            raise R28RuntimeRefused("R28_REVIEWED_STAGE16_17_FIXTURE_PAIR_REQUIRED")
        self._supervisor = supervisor
        self._executor = executor

    def inspect(self) -> R28RuntimeView:
        _require_offline(True)
        health = self._supervisor.health()
        counts = health["counts"]
        if (health.get("broker_order_sent") is not False
                or health.get("telegram_sent") is not False
                or health.get("live_trading_enabled") is not False):
            raise R28RuntimeRefused("R28_UNSAFE_STAGE17_HEALTH")
        unsafe = counts["CLAIMED"] + counts["QUARANTINED"]
        return R28RuntimeView(
            protocol="MMT_R28_OFFLINE_UNIFIED_RUNTIME_V1",
            state=("HALTED_MANUAL_RECONCILIATION" if unsafe
                   else "OFFLINE_OPERATOR_READY_NO_LIVE_AUTHORITY"),
            queue_counts=dict(counts),
            unresolved_jobs=unsafe,
            done_without_exact_cross_ledger_proof=counts["DONE"],
        )

    def run_one(self, *, now: datetime, operator_ack: bool = False) -> dict[str, Any]:
        """Dispatch at most one due event via real Stage17 -> Stage16 code.

        Stage17 validates immutable payload, panel revision, checked origin and
        inert receipt. Any claim failure quarantines; no exception is replayed.
        """
        _require_offline(operator_ack)
        if (not isinstance(now, datetime)
                or now.tzinfo is None or now.utcoffset() is None):
            raise R28RuntimeRefused("R28_TIMEZONE_AWARE_CLOCK_REQUIRED")
        before = self.inspect()
        if before.unresolved_jobs:
            raise R28RuntimeRefused("R28_UNRESOLVED_SIDE_EFFECTS_NO_DISPATCH")
        # Stage17's BEGIN IMMEDIATE atomic claim is the sole queue authority.
        # It also blocks *later* jobs on a quarantined binding (R28 fix).
        work = self._supervisor.run_due(
            self._executor, now=now, limit=1, operator_ack=True,
        )
        after = self.inspect()
        return {
            "protocol": "MMT_R28_OFFLINE_UNIFIED_RUNTIME_V1",
            "events": list(work),
            "state_after": after.state,
            "cross_ledger_effects_independently_attested": False,
            "broker_order_sent": False,
            "telegram_sent": False,
            "connected_paper_enabled": False,
            "live_enabled": False,
            "automatic_retry": False,
        }

    @staticmethod
    def inspect_stopped_snapshots(
        paths: RecoveryPaths,
        *,
        all_workers_stopped: bool = False,
        operator_ack: bool = False,
    ) -> dict[str, Any]:
        """Stage18 read-only four-ledger audit; never grants resume/retry."""
        _require_offline(operator_ack)
        if all_workers_stopped is not True or not isinstance(paths, RecoveryPaths):
            raise R28RuntimeRefused("R28_STOPPED_FOUR_SNAPSHOT_EVIDENCE_REQUIRED")
        report = evaluate_operational_recovery(paths)
        return {
            "protocol": "MMT_R28_OFFLINE_RECOVERY_REVIEW_V1",
            "read_only": True,
            "source_stage18_report": report.as_dict(),
            "automated_replay_approved": False,
            "cross_ledger_atomicity_claimed": False,
            "paper_or_live_enabled": False,
        }

    @staticmethod
    def verify_frozen_brooks_model(
        *, operator_ack: bool = False, **r27_inputs: Any,
    ) -> dict[str, Any]:
        """Run genuine R27 independent *research* parity; never forward as order."""
        _require_offline(operator_ack)
        from .brooks_independent_lifecycle_economics_mmt_r27_v1 import (
            run_r27_brooks_two_pass_model_crosscheck,
        )
        report = run_r27_brooks_two_pass_model_crosscheck(
            **r27_inputs, operator_ack=True,
        )["r27_independent_review"]
        forbidden_true = (
            "market_data_independently_issuer_authenticated",
            "broker_actual_order_type_and_fill_verified",
            "actual_account_fee_tier_and_funding_settlement_verified",
            "realized_pnl_evidenced",
            "prospective_oos_edge_established",
            "paper_connected_or_live_enabled",
            "production_modified",
        )
        if (not all(report.get(flag) is False for flag in forbidden_true)
                or report.get("hypothetical_order_path_recomputed_separately") is not True
                or report.get("actual_frozen_worker_rerun_and_decision_hash_equal") is not True):
            raise R28RuntimeRefused("R28_R27_RESEARCH_ORIGIN_SAFETY_VIOLATION")
        return {
            "protocol": "MMT_R28_BROOKS_MODEL_ONLY_V1",
            "r27_report_sha256": report["report_sha256"],
            "disposition": "RESEARCH_ONLY_NO_ORDER_ROUTING",
            "broker_order_enabled": False,
            "paper_connected_or_live_enabled": False,
        }


__all__ = [
    "R28UnifiedOfflineRuntime", "R28RuntimeView", "R28RuntimeRefused",
]
