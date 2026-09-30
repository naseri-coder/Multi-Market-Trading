"""Async PostgreSQL repository for Brooks automation metadata."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brooks_core.engine_contract import Chapter4SignalEntryLifecycle
from app.modules.signal_automation.entities import (
    AutomationMetadataRecord,
    BrooksRuleEvidence,
    BrooksSignalImport,
)
from app.modules.signal_automation.conflict_guard import SignalConflictContext
from app.modules.signal_automation.errors import (
    DuplicateAutomatedSignalError,
    SignalAutomationRepositoryError,
)
from app.modules.signal_automation.models import (
    SignalAutomationMetadata,
    SignalRuleEvidence,
)
from app.modules.operations.models import SignalLifecycleState
from app.modules.signals.models import Signal


def _chapter4_lifecycle_seed(
    command: BrooksSignalImport,
) -> Chapter4SignalEntryLifecycle | None:
    for item in command.rule_evidence:
        if item.rule_id != "BB-RNG-29-SIGNAL-BAR-STOP" or item.status != "PASS":
            continue
        data = {str(key): str(value) for key, value in item.evidence}
        if data.get("chapter4_signal_bar_state") != "POTENTIAL_SIGNAL_BAR":
            continue
        required = {
            "chapter4_setup_identity_id",
            "chapter4_potential_signal_bar_identity_id",
            "chapter4_potential_signal_bar_index",
            "chapter4_potential_signal_bar_open_time",
            "chapter4_potential_signal_bar_close_time",
            "economic_opportunity_id",
            "entry_intent_confirmation_scope",
            "entry_intent_confirmation_state",
        }
        if not required.issubset(data) or command.setup_type is None:
            return None
        try:
            return Chapter4SignalEntryLifecycle(
                setup_identity_id=data["chapter4_setup_identity_id"],
                source_signal_id=command.source_signal_id,
                economic_opportunity_id=data["economic_opportunity_id"],
                market_snapshot_id=command.market_snapshot_id,
                market_snapshot_hash=command.market_snapshot_hash,
                setup_type=command.setup_type,
                direction=command.direction,
                source_timeframe=command.timeframe,
                potential_signal_bar_identity_id=(
                    data["chapter4_potential_signal_bar_identity_id"]
                ),
                potential_signal_bar_index=int(
                    data["chapter4_potential_signal_bar_index"]
                ),
                potential_signal_bar_open_time=(
                    data["chapter4_potential_signal_bar_open_time"]
                ),
                potential_signal_bar_close_time=(
                    data["chapter4_potential_signal_bar_close_time"]
                ),
                state="POTENTIAL_SIGNAL_WAITING_ENTRY",
                entry_intent_confirmation_scope=(
                    data["entry_intent_confirmation_scope"]
                ),
                entry_intent_confirmation_state=(
                    data["entry_intent_confirmation_state"]
                ),
            )
        except (TypeError, ValueError):
            return None
    return None


def _brooks_core_typed_metadata(command: BrooksSignalImport) -> dict[str, object]:
    """Persist additive Brooks typed contracts and HP semantic cohort in JSONB."""
    metadata: dict[str, object] = {}
    if command.semantic_cohort_id is not None:
        metadata["hp_semantic_cohort_id"] = command.semantic_cohort_id
    if command.bootstrap_provenance is not None:
        metadata["hp_cold_start_bootstrap"] = dict(command.bootstrap_provenance)
    chapter4 = _chapter4_lifecycle_seed(command)
    if chapter4 is not None:
        metadata["brooks_chapter4_lifecycle"] = chapter4.to_metadata()

    if (
        command.target_source_identities
        or command.stop_source_identity is not None
        or command.target_plan_lifecycle is not None
        or command.reversal_outcome_context is not None
    ):
        metadata["brooks_core_typed_contract"] = {
            "target_source_identities": [
                item.to_metadata() for item in command.target_source_identities
            ],
            "stop_source_identity": (
                None
                if command.stop_source_identity is None
                else command.stop_source_identity.to_metadata()
            ),
            "target_plan_lifecycle": (
                None
                if command.target_plan_lifecycle is None
                else command.target_plan_lifecycle.to_metadata()
            ),
            "reversal_outcome_context": (
                None
                if command.reversal_outcome_context is None
                else command.reversal_outcome_context.to_metadata()
            ),
        }
    return metadata


def _to_record(model: SignalAutomationMetadata) -> AutomationMetadataRecord:
    return AutomationMetadataRecord(
        signal_id=model.signal_id,
        producer=model.producer,
        generation_mode=model.generation_mode,
        exchange=model.exchange,
        market_type=model.market_type,
        timeframe=model.timeframe,
        setup_type=model.setup_type,
        source_signal_id=model.source_signal_id,
        idempotency_key=model.idempotency_key,
        market_snapshot_id=model.market_snapshot_id,
        market_snapshot_hash=model.market_snapshot_hash,
        engine_version=model.engine_version,
        rule_set_version=model.rule_set_version,
        configuration_version=model.configuration_version,
        reasoning=tuple(model.reasoning),
        rule_ids=tuple(model.rule_ids),
        failed_rules=tuple(model.failed_rules),
        counts_toward_performance=model.counts_toward_performance,
        opportunity_variant=model.opportunity_variant,
        opportunity_key=model.opportunity_key,
    )


class SQLAlchemySignalAutomationRepository:
    """Persistence operations bound to the same caller-owned AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> AutomationMetadataRecord | None:
        statement = select(SignalAutomationMetadata).where(
            SignalAutomationMetadata.producer == "BROOKS",
            SignalAutomationMetadata.idempotency_key == idempotency_key,
        )
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SignalAutomationRepositoryError(
                "Unable to load automation metadata"
            ) from exc
        return None if model is None else _to_record(model)

    async def get_by_opportunity(
        self, *, generation_mode: str, variant: str, key: str,
    ) -> AutomationMetadataRecord | None:
        statement = (
            select(SignalAutomationMetadata)
            .where(
                SignalAutomationMetadata.producer == "BROOKS",
                SignalAutomationMetadata.generation_mode == generation_mode,
                SignalAutomationMetadata.opportunity_variant == variant,
                SignalAutomationMetadata.opportunity_key == key,
            )
            .with_for_update()
        )
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SignalAutomationRepositoryError(
                "Unable to load ii opportunity"
            ) from exc
        return None if model is None else _to_record(model)

    async def record_confirmed_ii_view(
        self, *, signal_id: int, snapshot_hash: str,
    ) -> bool:
        metadata = await self.session.get(SignalAutomationMetadata, signal_id)
        signal = await self.session.get(Signal, signal_id)
        if metadata is None or signal is None or signal.status != "OPEN":
            return False
        details = dict(metadata.analysis_metadata or {})
        ii_view = dict(details.get("ii_pair_opportunity") or {})
        if ii_view.get("state") == "PENDING":
            ii_view["state"] = "CONFIRMED"
            ii_view["confirmed_snapshot_hash"] = snapshot_hash
            details["ii_pair_opportunity"] = ii_view
            metadata.analysis_metadata = details
        return True

    async def create_metadata(
        self,
        *,
        signal_id: int,
        command: BrooksSignalImport,
        created_at: datetime,
    ) -> AutomationMetadataRecord:
        statement = (
            insert(SignalAutomationMetadata)
            .values(
                signal_id=signal_id,
                producer="BROOKS",
                generation_mode=command.generation_mode,
                exchange=command.exchange,
                market_type=command.market_type,
                timeframe=command.timeframe,
                setup_type=command.setup_type,
                source_signal_id=command.source_signal_id,
                idempotency_key=command.idempotency_key,
                opportunity_variant=command.opportunity_variant,
                opportunity_key=command.opportunity_key,
                market_snapshot_id=command.market_snapshot_id,
                market_snapshot_hash=command.market_snapshot_hash,
                engine_version=command.engine_version,
                rule_set_version=command.rule_set_version,
                configuration_version=command.configuration_version,
                reasoning=list(command.reasoning),
                rule_ids=list(command.rule_ids),
                failed_rules=list(command.failed_rules),
                analysis_metadata={
                    **_brooks_core_typed_metadata(command),
                    **({
                        "ii_pair_opportunity": {
                            "state": command.opportunity_view,
                            "first_snapshot_hash": command.market_snapshot_hash,
                            "first_open_time": command.ii_first_open_time.isoformat(),
                            "second_open_time": command.ii_second_open_time.isoformat(),
                        },
                    } if command.opportunity_variant is not None else {}),
                },
                counts_toward_performance=command.counts_toward_performance,
                created_at=created_at,
            )
            .returning(SignalAutomationMetadata)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one()
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name is None:
                constraint_name = getattr(
                    getattr(exc.orig, "__cause__", None), "constraint_name", None
                )
            if constraint_name in {
                "uq_signal_automation_metadata_producer_idempotency",
                "uq_signal_automation_metadata_producer_source_signal",
                "uq_signal_automation_metadata_ii_opportunity",
            }:
                raise DuplicateAutomatedSignalError(
                    "Automated signal already exists"
                ) from exc
            raise SignalAutomationRepositoryError(
                "Unable to create automation metadata"
            ) from exc
        except SQLAlchemyError as exc:
            raise SignalAutomationRepositoryError(
                "Unable to create automation metadata"
            ) from exc
        return _to_record(model)

    async def create_rule_evidence(
        self,
        *,
        signal_id: int,
        evidence: Sequence[BrooksRuleEvidence],
        created_at: datetime,
    ) -> None:
        if not evidence:
            return
        rows = [
            {
                "signal_id": signal_id,
                "ordinal": ordinal,
                "rule_id": item.rule_id,
                "status": item.status,
                "source_pages": list(item.source_pages),
                "evidence": [list(pair) for pair in item.evidence],
                "failed_conditions": list(item.failed_conditions),
                "confidence_components": [list(pair) for pair in item.confidence_components],
                "created_at": created_at,
            }
            for ordinal, item in enumerate(evidence, start=1)
        ]
        try:
            await self.session.execute(insert(SignalRuleEvidence), rows)
        except SQLAlchemyError as exc:
            raise SignalAutomationRepositoryError(
                "Unable to create rule evidence"
            ) from exc

    async def get_signal_conflict_contexts(
        self,
        *,
        symbol: str,
        timeframe: str,
        generation_mode: str,
    ) -> tuple[SignalConflictContext, ...]:
        statement = (
            select(Signal, SignalLifecycleState)
            .join(
                SignalAutomationMetadata,
                SignalAutomationMetadata.signal_id == Signal.id,
            )
            .outerjoin(
                SignalLifecycleState,
                SignalLifecycleState.signal_id == Signal.id,
            )
            .where(
                Signal.symbol == symbol,
                SignalAutomationMetadata.timeframe == timeframe,
                SignalAutomationMetadata.generation_mode == generation_mode,
                Signal.status == "OPEN",
            )
            .order_by(Signal.id.desc())
        )
        try:
            rows = tuple((await self.session.execute(statement)).all())
        except SQLAlchemyError as exc:
            raise SignalAutomationRepositoryError(
                "Unable to load signal conflict contexts"
            ) from exc
        return tuple(
            SignalConflictContext(
                signal_id=signal.id,
                direction=signal.direction,
                signal_status=signal.status,
                lifecycle_state=(lifecycle.state if lifecycle is not None else None),
                entry_activated_at=(lifecycle.entry_activated_at if lifecycle is not None else None),
                last_market_price=(lifecycle.last_market_price if lifecycle is not None else None),
                stop_loss=signal.stop_loss,
            )
            for signal, lifecycle in rows
        )

    async def complete_reconciled_pending_lifecycle(
        self, *, signal_id: int, now: datetime
    ) -> None:
        try:
            metadata = await self.session.get(SignalAutomationMetadata, signal_id)
            if metadata is not None:
                raw = dict(metadata.analysis_metadata or {})
                chapter4_raw = raw.get("brooks_chapter4_lifecycle")
                if isinstance(chapter4_raw, dict):
                    try:
                        chapter4 = Chapter4SignalEntryLifecycle.from_metadata(
                            chapter4_raw
                        )
                    except (KeyError, TypeError, ValueError):
                        chapter4 = None
                    if (
                        chapter4 is not None
                        and chapter4.state == "POTENTIAL_SIGNAL_WAITING_ENTRY"
                    ):
                        raw["brooks_chapter4_lifecycle"] = {
                            **chapter4.to_metadata(),
                            "state": "UNFILLED_TERMINAL",
                            "unfilled_terminal_reason": (
                                "RECONCILED_STALE_PENDING_SIGNAL"
                            ),
                        }
                        metadata.analysis_metadata = raw
            await self.session.execute(
                update(SignalLifecycleState)
                .where(SignalLifecycleState.signal_id == signal_id)
                .values(state="COMPLETE", updated_at=now)
            )
        except SQLAlchemyError as exc:
            raise SignalAutomationRepositoryError(
                "Unable to complete reconciled pending lifecycle"
            ) from exc

    async def set_publication_scope(self, signal_id: int, scope: str) -> None:
        statement = (
            update(Signal)
            .where(Signal.id == signal_id)
            .values(publication_scope=scope)
        )
        try:
            result = await self.session.execute(statement)
        except SQLAlchemyError as exc:
            raise SignalAutomationRepositoryError(
                "Unable to set signal publication scope"
            ) from exc
        if not result.rowcount:
            raise SignalAutomationRepositoryError("Signal does not exist")
