"""PAPER persistence + safe private-test delivery orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.paper_runtime.entities import (
    PaperPublishPayload,
    PaperRunResult,
    PaperSignalCandidate,
)
from app.modules.paper_runtime.protocols import PaperPublisher
from app.modules.paper_runtime.repository import SQLAlchemySignalDeliveryRepository
from app.modules.signal_automation.entities import BrooksSignalImport
from app.modules.signal_automation.service import BrooksSignalIntegrationService

Clock = Callable[[], datetime]
CHANNEL_KIND = "TELEGRAM_PRIVATE_TEST"


def utc_now() -> datetime:
    return datetime.now(UTC)


class PaperRuntimeService:
    """Persist one PAPER candidate and deliver it only to the private test channel.

    Delivery semantics are fail-closed:
    - SENT is never auto-sent again.
    - SENDING/AMBIGUOUS is never auto-retried.
    - FAILED may be retried by processing the same candidate again.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        publisher: PaperPublisher,
        private_test_channel_id: int,
        default_leverage: Decimal,
        clock: Clock = utc_now,
        integration_service_factory=BrooksSignalIntegrationService,
        delivery_repository_factory=SQLAlchemySignalDeliveryRepository,
    ) -> None:
        if private_test_channel_id == 0:
            raise ValueError("private_test_channel_id must be non-zero")
        if default_leverage <= 0:
            raise ValueError("default_leverage must be positive")
        self.session = session
        self.publisher = publisher
        self.private_test_channel_id = private_test_channel_id
        self.default_leverage = default_leverage
        self.clock = clock
        self.integration_service_factory = integration_service_factory
        self.delivery_repository_factory = delivery_repository_factory

    async def process(
        self,
        candidate: PaperSignalCandidate,
        *,
        signal_quality=None,
    ) -> PaperRunResult:
        command = BrooksSignalImport(
            source_signal_id=candidate.source_signal_id,
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            targets=candidate.targets,
            leverage=self.default_leverage,
            exchange=candidate.exchange,
            market_type=candidate.market_type,
            timeframe=candidate.timeframe,
            setup_type=candidate.setup_type,
            market_snapshot_id=candidate.market_snapshot_id,
            market_snapshot_hash=candidate.market_snapshot_hash,
            engine_version=candidate.engine_version,
            rule_set_version=candidate.rule_set_version,
            configuration_version=candidate.configuration_version,
            reasoning=candidate.reasoning,
            rule_ids=candidate.rule_ids,
            failed_rules=candidate.failed_rules,
            rule_evidence=candidate.rule_evidence,
            target_source_identities=getattr(candidate, "target_source_identities", ()),
            stop_source_identity=getattr(candidate, "stop_source_identity", None),
            target_plan_lifecycle=getattr(candidate, "target_plan_lifecycle", None),
            reversal_outcome_context=getattr(candidate, "reversal_outcome_context", None),
            semantic_cohort_id=getattr(candidate, "semantic_cohort_id", None),
            generation_mode="PAPER",
            publication_scope="PRIVATE_TEST",
            counts_toward_performance=False,
            description="Automatically generated Brooks PAPER signal",
        )

        integration = self.integration_service_factory(self.session)
        imported = await integration.import_signal(command)
        if not imported.created and imported.disposition != "SKIPPED_DUPLICATE":
            return PaperRunResult(
                signal_id=imported.signal_id, signal_created=False,
                delivery_status=imported.disposition, external_message_id=None,
            )
        destination = str(self.private_test_channel_id)

        async with self.session.begin():
            deliveries = self.delivery_repository_factory(self.session)
            delivery = await deliveries.get(
                signal_id=imported.signal_id,
                channel_kind=CHANNEL_KIND,
                destination_id=destination,
            )
            if delivery is None:
                delivery = await deliveries.create_pending(
                    signal_id=imported.signal_id,
                    channel_kind=CHANNEL_KIND,
                    destination_id=destination,
                    now=self.clock(),
                )

            if delivery.status == "SENT":
                return PaperRunResult(
                    signal_id=imported.signal_id,
                    signal_created=imported.created,
                    delivery_status="SENT",
                    external_message_id=delivery.external_message_id,
                )
            if delivery.status in {"SENDING", "AMBIGUOUS"}:
                return PaperRunResult(
                    signal_id=imported.signal_id,
                    signal_created=imported.created,
                    delivery_status=delivery.status,
                    external_message_id=delivery.external_message_id,
                )
            sending = await deliveries.mark_sending(delivery.id, now=self.clock())

        payload = PaperPublishPayload(
            signal_id=imported.signal_id,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            direction=candidate.direction,
            setup_type=candidate.setup_type,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            targets=candidate.targets,
            reasoning=candidate.reasoning,
            rule_ids=candidate.rule_ids,
            market_snapshot_id=candidate.market_snapshot_id,
            market_snapshot_hash=candidate.market_snapshot_hash,
            chart_path=candidate.chart_path,
        )

        try:
            message_id = await self.publisher.publish(payload)
        except Exception as exc:
            async with self.session.begin():
                deliveries = self.delivery_repository_factory(self.session)
                await deliveries.mark_failed(
                    sending.id,
                    error_code=type(exc).__name__,
                    now=self.clock(),
                )
            raise

        try:
            async with self.session.begin():
                deliveries = self.delivery_repository_factory(self.session)
                sent = await deliveries.mark_sent(
                    sending.id,
                    message_id=message_id,
                    now=self.clock(),
                )
        except Exception:
            try:
                async with self.session.begin():
                    deliveries = self.delivery_repository_factory(self.session)
                    await deliveries.mark_ambiguous(sending.id, now=self.clock())
            except Exception:
                pass
            raise

        return PaperRunResult(
            signal_id=imported.signal_id,
            signal_created=imported.created,
            delivery_status=sent.status,
            external_message_id=sent.external_message_id,
        )
