from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.signal_automation.conflict_guard import SignalConflictContext
from app.modules.signal_automation.entities import BrooksRuleEvidence, BrooksSignalImport
from app.modules.signal_automation.repository import SQLAlchemySignalAutomationRepository
from app.modules.signal_automation.service import BrooksSignalIntegrationService


class _Tx:
    def __init__(self, session): self.session = session
    async def __aenter__(self): self.session.begins += 1; return self
    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None: self.session.commits += 1
        else: self.session.rollbacks += 1
        return False


class _Session:
    def __init__(self):
        self.begins = self.commits = self.rollbacks = 0
    def begin(self): return _Tx(self)


def _command(
    *,
    mode: str,
    source: str,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    direction: str = "LONG",
    setup: str = "H2_CONFIRMED",
) -> BrooksSignalImport:
    if direction == "LONG":
        entry, stop, targets = Decimal("100"), Decimal("95"), (Decimal("105"),)
    else:
        entry, stop, targets = Decimal("100"), Decimal("105"), (Decimal("95"),)
    publication_scope = {"LIVE": "VIP", "SHADOW": "INTERNAL", "PAPER": "PRIVATE_TEST"}[mode]
    return BrooksSignalImport(
        source_signal_id=source,
        symbol=symbol,
        direction=direction,
        entry_price=entry,
        stop_loss=stop,
        targets=targets,
        leverage=Decimal("1"),
        exchange="binance",
        market_type="futures",
        timeframe=timeframe,
        setup_type=setup,
        market_snapshot_id=f"snap-{source}",
        market_snapshot_hash=f"hash-{source}",
        engine_version="core-final",
        rule_set_version="rules-final",
        configuration_version="cfg-final",
        reasoning=("fixture",),
        rule_ids=("BR",),
        failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BR", "PASS", (1,)),),
        generation_mode=mode,
        publication_scope=publication_scope,
        counts_toward_performance=(mode == "LIVE"),
    )


def _pending(signal_id: int, direction: str = "LONG") -> SignalConflictContext:
    return SignalConflictContext(
        signal_id=signal_id,
        direction=direction,
        signal_status="OPEN",
        lifecycle_state="WAITING_ENTRY",
        entry_activated_at=None,
        last_market_price=Decimal("101"),
        stop_loss=Decimal("95") if direction == "LONG" else Decimal("105"),
    )


class _ModeAwareRepo:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.requested_modes: list[str] = []
        self.get_by_idempotency_key = AsyncMock(return_value=None)
        self.set_publication_scope = AsyncMock()
        self.create_metadata = AsyncMock()
        self.create_rule_evidence = AsyncMock()
        self.complete_reconciled_pending_lifecycle = AsyncMock()

    async def get_signal_conflict_contexts(self, *, symbol, timeframe, generation_mode):
        self.requested_modes.append(generation_mode)
        return tuple(
            row.context
            for row in self.rows
            if row.symbol == symbol
            and row.timeframe == timeframe
            and row.generation_mode == generation_mode
            and row.context.signal_status == "OPEN"
        )


async def _run(command: BrooksSignalImport, rows=()):
    session = _Session()
    repo = _ModeAwareRepo(rows)
    signal_service = AsyncMock()
    signal_service.create_signal.return_value = SimpleNamespace(id=999)
    service = BrooksSignalIntegrationService(
        session,
        automation_repository_factory=lambda _: repo,
        signal_service_factory=lambda _: signal_service,
    )
    result = await service.import_signal(command)
    return result, repo, signal_service


def _row(mode: str, *, signal_id: int, symbol="BTCUSDT", timeframe="15m", direction="LONG"):
    return SimpleNamespace(
        generation_mode=mode,
        symbol=symbol,
        timeframe=timeframe,
        context=_pending(signal_id, direction),
    )


@pytest.mark.asyncio
async def test_live_no_conflict_allowed_and_mode_passed_to_repository():
    result, repo, _ = await _run(_command(mode="LIVE", source="live-no-conflict"))
    assert result.created is True
    assert repo.requested_modes == ["LIVE"]


@pytest.mark.asyncio
async def test_live_open_live_conflict_preserved():
    result, _, service = await _run(
        _command(mode="LIVE", source="live-blocked", direction="SHORT"),
        (_row("LIVE", signal_id=1, direction="LONG"),),
    )
    assert result.created is False
    assert result.disposition == "SKIPPED_VALID_PENDING_CONFLICT"
    service.create_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_shadow_open_does_not_block_live():
    result, repo, _ = await _run(
        _command(mode="LIVE", source="live-vs-shadow", direction="SHORT"),
        (_row("SHADOW", signal_id=2, direction="LONG"),),
    )
    assert result.created is True
    assert repo.requested_modes == ["LIVE"]


@pytest.mark.asyncio
async def test_shadow_open_shadow_conflict_preserved():
    result, _, service = await _run(
        _command(mode="SHADOW", source="shadow-blocked", direction="SHORT"),
        (_row("SHADOW", signal_id=3, direction="LONG"),),
    )
    assert result.created is False
    assert result.disposition == "SKIPPED_VALID_PENDING_CONFLICT"
    service.create_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_open_does_not_block_shadow():
    result, repo, _ = await _run(
        _command(mode="SHADOW", source="shadow-vs-live", direction="SHORT"),
        (_row("LIVE", signal_id=4, direction="LONG"),),
    )
    assert result.created is True
    assert repo.requested_modes == ["SHADOW"]


@pytest.mark.asyncio
async def test_paper_is_independent_conflict_domain():
    result, repo, _ = await _run(
        _command(mode="PAPER", source="paper-vs-live", direction="SHORT"),
        (_row("LIVE", signal_id=5, direction="LONG"),),
    )
    assert result.created is True
    assert repo.requested_modes == ["PAPER"]


@pytest.mark.asyncio
async def test_same_mode_opposite_direction_conflict_behavior_preserved():
    result, _, _ = await _run(
        _command(mode="LIVE", source="opposite", direction="SHORT"),
        (_row("LIVE", signal_id=6, direction="LONG"),),
    )
    assert result.created is False


@pytest.mark.asyncio
async def test_same_mode_same_direction_pending_conflict_behavior_preserved():
    result, _, _ = await _run(
        _command(mode="LIVE", source="same-dir", direction="LONG"),
        (_row("LIVE", signal_id=7, direction="LONG"),),
    )
    assert result.created is False


@pytest.mark.asyncio
async def test_different_timeframe_does_not_conflict():
    result, _, _ = await _run(
        _command(mode="LIVE", source="different-tf", timeframe="15m", direction="SHORT"),
        (_row("LIVE", signal_id=8, timeframe="1h", direction="LONG"),),
    )
    assert result.created is True


@pytest.mark.asyncio
async def test_different_setup_same_symbol_timeframe_preserves_existing_conflict_identity():
    result, _, _ = await _run(
        _command(mode="LIVE", source="different-setup", setup="MTR", direction="SHORT"),
        (_row("LIVE", signal_id=9, direction="LONG"),),
    )
    assert result.created is False


@pytest.mark.asyncio
async def test_closed_other_mode_row_does_not_conflict():
    row = _row("SHADOW", signal_id=10, direction="LONG")
    row.context = replace(row.context, signal_status="CLOSED")
    result, _, _ = await _run(
        _command(mode="LIVE", source="closed-shadow", direction="SHORT"),
        (row,),
    )
    assert result.created is True


@pytest.mark.asyncio
async def test_idempotency_key_remains_generation_mode_scoped():
    base = _command(mode="LIVE", source="same-source")
    shadow = replace(
        base,
        generation_mode="SHADOW",
        publication_scope="INTERNAL",
        counts_toward_performance=False,
    )
    assert base.idempotency_key != shadow.idempotency_key


@pytest.mark.asyncio
async def test_repository_conflict_statement_filters_generation_mode():
    captured = {}

    class _Rows:
        def all(self): return ()

    class _CaptureSession:
        async def execute(self, statement):
            captured["statement"] = statement
            return _Rows()

    repo = SQLAlchemySignalAutomationRepository(_CaptureSession())
    assert await repo.get_signal_conflict_contexts(
        symbol="BTCUSDT", timeframe="15m", generation_mode="SHADOW"
    ) == ()
    compiled = captured["statement"].compile()
    sql = str(compiled)
    params = compiled.params
    assert "generation_mode" in sql
    assert "SHADOW" in params.values()


@pytest.mark.asyncio
async def test_mode_isolation_does_not_change_create_mode_persistence_command():
    command = _command(mode="SHADOW", source="shadow-create")
    result, repo, _ = await _run(command)
    assert result.created is True
    persisted_command = repo.create_metadata.await_args.kwargs["command"]
    assert persisted_command.generation_mode == "SHADOW"
    assert persisted_command.publication_scope == "INTERNAL"
    assert persisted_command.counts_toward_performance is False

def test_null_generation_mode_is_structurally_rejected():
    with pytest.raises(ValueError, match="invalid generation_mode"):
        replace(
            _command(mode="LIVE", source="null-mode"),
            generation_mode=None,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_concurrent_cross_mode_conflict_lookups_remain_isolated():
    import asyncio

    live_row = _row("LIVE", signal_id=20, direction="LONG")
    shadow_row = _row("SHADOW", signal_id=21, direction="LONG")
    live_cmd = _command(mode="LIVE", source="concurrent-live", direction="SHORT")
    shadow_cmd = _command(mode="SHADOW", source="concurrent-shadow", direction="SHORT")

    live_result, shadow_result = await asyncio.gather(
        _run(live_cmd, (shadow_row,)),
        _run(shadow_cmd, (live_row,)),
    )
    assert live_result[0].created is True
    assert shadow_result[0].created is True
    assert live_result[1].requested_modes == ["LIVE"]
    assert shadow_result[1].requested_modes == ["SHADOW"]
