from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.signal_automation.entities import (
    AutomationMetadataRecord,
    BrooksRuleEvidence,
    BrooksSignalImport,
)
from app.modules.signal_automation.errors import (
    DuplicateAutomatedSignalError,
    SignalAutomationRepositoryError,
)
from app.modules.signal_automation.service import BrooksSignalIntegrationService


class Tx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.begins += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.session.commits += 1
        else:
            self.session.rollbacks += 1
        return False


class FakeSession:
    def __init__(self):
        self.begins = 0
        self.commits = 0
        self.rollbacks = 0

    def begin(self):
        return Tx(self)


def command():
    return BrooksSignalImport(
        source_signal_id="core-1",
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"), Decimal("120")),
        leverage=Decimal("1"),
        exchange="binance",
        market_type="spot",
        timeframe="15m",
        setup_type="H2",
        market_snapshot_id="snap-1",
        market_snapshot_hash="hash-1",
        engine_version="0.10.0",
        rule_set_version="phase2-catalog-v1",
        configuration_version="cfg-001",
        reasoning=("ok",),
        rule_ids=("BR-007",),
        failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BR-007", "PASS", (11,)),),
        generation_mode="PAPER",
        publication_scope="PRIVATE_TEST",
    )


def record(signal_id: int) -> AutomationMetadataRecord:
    c = command()
    return AutomationMetadataRecord(
        signal_id,
        "BROOKS",
        "PAPER",
        "binance",
        "spot",
        "15m",
        "H2",
        "core-1",
        c.idempotency_key,
        "snap-1",
        "hash-1",
        "0.10.0",
        "phase2-catalog-v1",
        "cfg-001",
        ("ok",),
        ("BR-007",),
        (),
        False,
    )


@pytest.mark.asyncio
async def test_existing_idempotency_returns_without_creating() -> None:
    session = FakeSession()
    auto = AsyncMock()
    auto.get_by_idempotency_key.return_value = record(77)
    signal_service = AsyncMock()

    service = BrooksSignalIntegrationService(
        session,
        automation_repository_factory=lambda _: auto,
        signal_service_factory=lambda _: signal_service,
    )
    result = await service.import_signal(command())

    assert result.created is False
    assert result.signal_id == 77
    assert result.disposition == "SKIPPED_DUPLICATE"
    assert session.commits == 1
    assert session.rollbacks == 0
    signal_service.create_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_happy_path_is_one_atomic_transaction() -> None:
    session = FakeSession()
    auto = AsyncMock()
    auto.get_by_idempotency_key.return_value = None
    auto.get_signal_conflict_contexts.return_value = ()
    signal_service = AsyncMock()
    signal_service.create_signal.return_value = SimpleNamespace(id=123)

    service = BrooksSignalIntegrationService(
        session,
        automation_repository_factory=lambda _: auto,
        signal_service_factory=lambda _: signal_service,
    )
    result = await service.import_signal(command())

    assert result.created is True
    assert result.signal_id == 123
    assert session.begins == 1
    assert session.commits == 1
    assert session.rollbacks == 0
    assert signal_service.add_target.await_count == 2
    auto.set_publication_scope.assert_awaited_once_with(123, "PRIVATE_TEST")
    auto.create_metadata.assert_awaited_once()
    auto.create_rule_evidence.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_race_rolls_back_then_resolves_winner() -> None:
    session = FakeSession()
    first = AsyncMock()
    second = AsyncMock()
    first.get_by_idempotency_key.return_value = None
    first.get_signal_conflict_contexts.return_value = ()
    first.create_metadata.side_effect = DuplicateAutomatedSignalError("duplicate")
    second.get_by_idempotency_key.return_value = record(88)
    repos = iter((first, second))

    signal_service = AsyncMock()
    signal_service.create_signal.return_value = SimpleNamespace(id=123)

    service = BrooksSignalIntegrationService(
        session,
        automation_repository_factory=lambda _: next(repos),
        signal_service_factory=lambda _: signal_service,
    )
    result = await service.import_signal(command())

    assert result.created is False
    assert result.signal_id == 88
    assert result.disposition == "SKIPPED_DUPLICATE"
    assert session.rollbacks == 1
    assert session.commits == 1
    assert session.begins == 2


@pytest.mark.asyncio
async def test_unexpected_failure_rolls_back_all() -> None:
    session = FakeSession()
    auto = AsyncMock()
    auto.get_by_idempotency_key.return_value = None
    auto.get_signal_conflict_contexts.return_value = ()
    auto.create_rule_evidence.side_effect = SignalAutomationRepositoryError("boom")
    signal_service = AsyncMock()
    signal_service.create_signal.return_value = SimpleNamespace(id=123)

    service = BrooksSignalIntegrationService(
        session,
        automation_repository_factory=lambda _: auto,
        signal_service_factory=lambda _: signal_service,
    )

    with pytest.raises(SignalAutomationRepositoryError):
        await service.import_signal(command())
    assert session.rollbacks == 1
    assert session.commits == 0
