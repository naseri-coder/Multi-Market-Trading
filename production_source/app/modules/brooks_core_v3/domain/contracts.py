"""Cross-artifact invariants for Phase 3."""

from __future__ import annotations

from .models import ChartSpecification, Signal


def assert_signal_chart_same_snapshot(
    signal: Signal,
    chart: ChartSpecification,
) -> None:
    if signal.signal_id != chart.signal_id:
        raise ValueError("chart signal_id does not match signal")
    if signal.market_snapshot_id != chart.market_snapshot_id:
        raise ValueError("signal/chart market_snapshot_id mismatch")
    if signal.market_snapshot_hash != chart.market_snapshot_hash:
        raise ValueError("signal/chart market_snapshot_hash mismatch")


def reproduction_key(signal: Signal) -> tuple[str, str, str, str]:
    return (
        signal.market_snapshot_hash,
        signal.rule_set_version,
        signal.engine_version,
        signal.configuration_version,
    )
