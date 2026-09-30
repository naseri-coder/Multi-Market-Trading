from datetime import UTC, datetime

from app.modules.shadow_replay.entities import (
    ShadowReplayMetrics,
    ShadowReplayReport,
)
from app.modules.shadow_replay.json_report import report_to_json


def test_json_report_is_deterministic():
    report = ShadowReplayReport(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        window_size=100,
        source_candle_count=500,
        observations=(),
        metrics=ShadowReplayMetrics(
            evaluated_snapshots=0,
            h2_count=0,
            l2_count=0,
            ambiguous_count=0,
            blocked_count=0,
            no_signal_count=0,
            detections_per_1000_snapshots=0.0,
        ),
    )
    assert report_to_json(report) == report_to_json(report)
    assert '"symbol": "BTCUSDT"' in report_to_json(report)
