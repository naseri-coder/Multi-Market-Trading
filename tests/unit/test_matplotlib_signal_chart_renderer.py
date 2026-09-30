from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from app.modules.charting.matplotlib_renderer import MatplotlibSignalChartRenderer
from app.modules.market_data.entities import Candle, MarketSnapshot

def make_snapshot():
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    candles = []
    price = Decimal("100")
    for i in range(30):
        ot = start + timedelta(minutes=15*i)
        close = price + Decimal(i % 3 - 1)
        high = max(price, close) + Decimal("2")
        low = min(price, close) - Decimal("2")
        candles.append(Candle(
            open_time=ot,
            close_time=ot + timedelta(minutes=15),
            open=price,
            high=high,
            low=low,
            close=close,
            volume=Decimal("10"),
        ))
        price = close
    return MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time + timedelta(seconds=1),
    )

def test_renderer_writes_png(tmp_path: Path):
    output = tmp_path / "signal.png"
    result = MatplotlibSignalChartRenderer().render(
        snapshot=make_snapshot(),
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"), Decimal("120")),
        setup_type="H2",
        output_path=output,
    )
    assert result == output
    assert output.is_file()
    assert output.stat().st_size > 1000
