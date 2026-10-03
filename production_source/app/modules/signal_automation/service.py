"""Atomic import of Brooks signals into the existing signal lifecycle."""

from __future__ import annotations

from collections.abc import Callable
import logging
from datetime import UTC, datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.signal_automation.entities import (
    BrooksSignalImport,
    BrooksSignalImportResult,
)
from app.modules.signal_automation.errors import (
    DuplicateAutomatedSignalError,
    SignalAutomationConsistencyError,
)
from app.modules.signal_automation.repository import SQLAlchemySignalAutomationRepository
from app.modules.signals.repository import SQLAlchemySignalRepository
from app.modules.signals.service import SignalService
from app.modules.signal_automation.conflict_guard import (
    SignalConflictCategory,
    check_signal_conflict,
)

Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)

_SKIP_DISPOSITION = {
    SignalConflictCategory.DUPLICATE_CANDIDATE: "SKIPPED_DUPLICATE",
    SignalConflictCategory.ACTIVE_POSITION_CONFLICT: "SKIPPED_ACTIVE_POSITION_CONFLICT",
    SignalConflictCategory.VALID_PENDING_ENTRY_CONFLICT: "SKIPPED_VALID_PENDING_CONFLICT",
}


def _skip_disposition(category: SignalConflictCategory) -> str:
    try:
        return _SKIP_DISPOSITION[category]
    except KeyError as exc:
        raise SignalAutomationConsistencyError(
            f"Unsupported blocking conflict category: {category.value}"
        ) from exc


def utc_now() -> datetime:
    return datetime.now(UTC)


class BrooksSignalIntegrationService:
    """Own one atomic transaction spanning signal, targets, metadata and evidence."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Clock = utc_now,
        automation_repository_factory=SQLAlchemySignalAutomationRepository,
        signal_service_factory=None,
    ) -> None:
        self.session = session
        self.clock = clock
        self.automation_repository_factory = automation_repository_factory
        self.signal_service_factory = signal_service_factory or (
            lambda bound_session: SignalService(
                SQLAlchemySignalRepository(bound_session),
                clock=self.clock,
            )
        )

    async def import_signal(self, command: BrooksSignalImport) -> BrooksSignalImportResult:
        if not isinstance(command, BrooksSignalImport):
            raise TypeError("BrooksSignalImport is required")

        try:
            return await self._create_or_get(command)
        except DuplicateAutomatedSignalError as conflict:
            # The failed INSERT rolled back. Resolve the unique-index winner in a
            # fresh transaction, including the ii cross-snapshot opportunity key.
            async with self.session.begin():
                repository = self.automation_repository_factory(self.session)
                existing = None
                if command.opportunity_key is not None:
                    existing = await repository.get_by_opportunity(
                        generation_mode=command.generation_mode,
                        variant=command.opportunity_variant,
                        key=command.opportunity_key,
                    )
                    if existing is not None and command.opportunity_view == "CONFIRMED":
                        await repository.record_confirmed_ii_view(
                            signal_id=existing.signal_id,
                            snapshot_hash=command.market_snapshot_hash,
                        )
                if existing is None:
                    existing = await repository.get_by_idempotency_key(
                        command.idempotency_key
                    )
                if existing is None:
                    raise SignalAutomationConsistencyError(
                        "Unique conflict occurred but no existing signal was found"
                    ) from conflict
                if (
                    command.opportunity_key is not None
                    and existing.opportunity_key != command.opportunity_key
                ):
                    raise SignalAutomationConsistencyError(
                        "Snapshot identity collides with a different opportunity"
                    ) from conflict
                return BrooksSignalImportResult(
                    signal_id=existing.signal_id,
                    created=False,
                    idempotency_key=existing.idempotency_key,
                    publication_scope=command.publication_scope,
                    disposition=_skip_disposition(SignalConflictCategory.DUPLICATE_CANDIDATE),
                )

    async def _create_or_get(
        self,
        command: BrooksSignalImport,
    ) -> BrooksSignalImportResult:
        async with self.session.begin():
            automation_repository = self.automation_repository_factory(self.session)
            if command.opportunity_key is not None:
                matched = await automation_repository.get_by_opportunity(
                    generation_mode=command.generation_mode,
                    variant=command.opportunity_variant,
                    key=command.opportunity_key,
                )
                if matched is not None:
                    if command.opportunity_view == "CONFIRMED":
                        await automation_repository.record_confirmed_ii_view(
                            signal_id=matched.signal_id,
                            snapshot_hash=command.market_snapshot_hash,
                        )
                    return BrooksSignalImportResult(
                        signal_id=matched.signal_id,
                        created=False,
                        idempotency_key=matched.idempotency_key,
                        publication_scope=command.publication_scope,
                        disposition=_skip_disposition(SignalConflictCategory.DUPLICATE_CANDIDATE),
                    )
            existing = await automation_repository.get_by_idempotency_key(
                command.idempotency_key
            )
            if existing is not None:
                if (
                    command.opportunity_key is not None
                    and existing.opportunity_key != command.opportunity_key
                ):
                    raise SignalAutomationConsistencyError(
                        "Snapshot identity collides with a different opportunity"
                    )
                return BrooksSignalImportResult(
                    signal_id=existing.signal_id,
                    created=False,
                    idempotency_key=existing.idempotency_key,
                    publication_scope=command.publication_scope,
                    disposition=_skip_disposition(SignalConflictCategory.DUPLICATE_CANDIDATE),
                )

            conflict_contexts = await automation_repository.get_signal_conflict_contexts(
                symbol=command.symbol,
                timeframe=command.timeframe,
                generation_mode=command.generation_mode,
            )
            evaluated = tuple(
                (context, check_signal_conflict(context, command.direction))
                for context in conflict_contexts
            )
            blockers = tuple(
                (context, decision)
                for context, decision in evaluated
                if not decision.allowed
            )
            if blockers:
                # A genuine ACTIVE opposite position always outranks pending-order
                # conflicts, even when a newer WAITING_ENTRY row exists.
                conflict_context, decision = min(
                    blockers,
                    key=lambda item: (
                        0
                        if item[1].category == SignalConflictCategory.ACTIVE_POSITION_CONFLICT
                        else 1,
                        -item[0].signal_id,
                    ),
                )
                return BrooksSignalImportResult(
                    signal_id=conflict_context.signal_id, created=False,
                    idempotency_key=command.idempotency_key,
                    publication_scope=command.publication_scope,
                    disposition=_skip_disposition(decision.category),
                )

            signal_service = self.signal_service_factory(self.session)
            stale_contexts = tuple(
                (context, decision)
                for context, decision in evaluated
                if decision.reconcile_stale
            )
            for conflict_context, decision in stale_contexts:
                now = self.clock()
                await signal_service.cancel_signal(
                    conflict_context.signal_id,
                    reason=decision.reason,
                    event_metadata={
                        "reconciled_by_source_signal_id": command.source_signal_id,
                        "reconciled_by_direction": command.direction,
                        "reconciled_by_market_snapshot_id": command.market_snapshot_id,
                    },
                )
                await automation_repository.complete_reconciled_pending_lifecycle(
                    signal_id=conflict_context.signal_id, now=now
                )
                logger.info(
                    "Reconciled structurally invalid pending Brooks signal",
                    extra={
                        "event": "brooks_stale_pending_signal_reconciled",
                        "signal_id": conflict_context.signal_id,
                        "symbol": command.symbol, "timeframe": command.timeframe,
                        "reason": decision.reason,
                    },
                )
            reconciled_stale = bool(stale_contexts)

            signal = await signal_service.create_signal(command.to_create_signal())

            # Scope must be persisted before commit so PAPER/SHADOW can never become
            # publicly visible because of a partial integration write.
            await automation_repository.set_publication_scope(
                signal.id,
                command.publication_scope,
            )

            for target_price in command.targets:
                await signal_service.add_target(
                    signal.id,
                    target_price=target_price,
                )

            created_at = self.clock()
            await automation_repository.create_metadata(
                signal_id=signal.id,
                command=command,
                created_at=created_at,
            )
            await automation_repository.create_rule_evidence(
                signal_id=signal.id,
                evidence=command.rule_evidence,
                created_at=created_at,
            )

            return BrooksSignalImportResult(
                signal_id=signal.id, created=True,
                idempotency_key=command.idempotency_key,
                publication_scope=command.publication_scope,
                disposition=("STALE_SIGNAL_RECONCILED" if reconciled_stale else "CREATED"),
            )
