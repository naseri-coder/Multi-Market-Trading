from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.brooks_core.source_rules import (
    br012_default_ema_length,
    br019_range_breakout_failure_heuristic,
    evaluate_br010_inside_bar,
    evaluate_br011_outside_bar,
)
from app.modules.market_data.entities import Candle


def candle(*, high: str, low: str) -> Candle:
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    return Candle(
        open_time=start,
        close_time=start + timedelta(minutes=15),
        open=Decimal("100"),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


def test_br010_inside_bar_allows_equal_boundaries() -> None:
    previous = candle(high="110", low="90")
    current = candle(high="110", low="90")
    result = evaluate_br010_inside_bar(current, previous)
    assert result.status == "PASS"
    assert result.output == "inside_bar"


def test_br011_outside_bar_allows_equal_boundaries() -> None:
    previous = candle(high="110", low="90")
    current = candle(high="110", low="90")
    result = evaluate_br011_outside_bar(current, previous)
    assert result.status == "PASS"
    assert result.output == "outside_bar"


def test_br012_default_ema_is_20() -> None:
    result = br012_default_ema_length()
    assert ("ema_length", "20") in result.evidence


def test_source_80_percent_is_not_calibrated_probability() -> None:
    result = br019_range_breakout_failure_heuristic()
    assert ("source_claim_percent", "80") in result.evidence
    assert ("calibrated_probability", "NO") in result.evidence
