from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.market_data.entities import Candle
from app.modules.operations.lifecycle import LiveSignalLifecycleService


def _service():
    return LiveSignalLifecycleService(
        database=object(), provider=object(), bot=object(), vip_channel_id=1,
        cutover_at=datetime(2026, 9, 1, tzinfo=UTC), candle_limit=20,
    )


def _candle(*, low: str, high: str, close: str):
    opened = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    return Candle(
        open_time=opened, close_time=opened + timedelta(minutes=1),
        open=Decimal(close), high=Decimal(high), low=Decimal(low),
        close=Decimal(close), volume=Decimal("1"),
    )


@pytest.mark.asyncio
async def test_pending_stop_before_entry_is_cancelled_and_completed() -> None:
    service = _service()
    repo = AsyncMock()
    repo.cancel_pending_targets.return_value = 2
    repo.append_event.return_value = SimpleNamespace(id=501)
    signal = SimpleNamespace(id=70, stop_loss=Decimal("95"), direction="LONG")
    state = SimpleNamespace(
        state="WAITING_ENTRY", last_processed_candle_close=None,
        last_market_price=None, updated_at=None,
    )
    candle = _candle(low="94", high="96", close="94.5")

    event_id = await service._cancel_invalid_pending(
        repo=repo, signal=signal, state=state, candle=candle,
    )

    assert event_id == 501
    assert state.state == "COMPLETE"
    assert state.last_market_price == Decimal("94.5")
    repo.update_signal.assert_awaited_once()
    repo.append_event.assert_awaited_once()
    event_kwargs = repo.append_event.await_args.kwargs
    assert event_kwargs["event_type"] == "CANCELLED"
    assert event_kwargs["metadata"]["reason"] == "PENDING_ENTRY_STRUCTURAL_STOP_TOUCHED"



def test_entry_and_stop_same_candle_is_not_pre_entry_cancellation_case() -> None:
    service = _service()
    signal = SimpleNamespace(
        id=71, direction="LONG", entry_price=Decimal("100"), stop_loss=Decimal("95")
    )
    candle = _candle(low="94", high="101", close="99")
    entry_touched = candle.low <= signal.entry_price <= candle.high
    touched_stop = service._stop_touched(signal, candle)

    assert entry_touched is True
    assert touched_stop is True
    assert (touched_stop and not entry_touched) is False
