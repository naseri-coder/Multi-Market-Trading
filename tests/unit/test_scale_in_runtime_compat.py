from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.brooks_runtime.coordinator import BrooksFullCoreCoordinator
from app.modules.performance_intelligence.collector import PerformanceCollector
from app.modules.scale_in.runtime_observer import ShadowScaleInObserver


def test_performance_intelligence_collects_one_aggregate_trade():
    position = SimpleNamespace(
        id=7, signal_id=42, state="CLOSED",
        realized_net_pnl=Decimal("1.25"), initial_trade_risk_budget=Decimal("2.5"),
        position_version="brooks-multi-lot-position-v1",
        initial_source_signal_id="source-42", mode="LIVE",
    )
    snap = PerformanceCollector().collect_position(position, entry_lot_count=3)
    assert snap.signal_id == 42
    assert snap.profit_loss == Decimal("1.25")
    assert snap.rr == Decimal("0.5")
    assert snap.context["multi_lot_position"] is True
    assert snap.evidence["entry_lot_count"] == 3


def test_performance_intelligence_rejects_open_or_unlinked_aggregate():
    collector = PerformanceCollector()
    with pytest.raises(ValueError, match="CLOSED"):
        collector.collect_position(SimpleNamespace(state="OPEN"))
    with pytest.raises(ValueError, match="signal_id"):
        collector.collect_position(SimpleNamespace(
            state="CLOSED", signal_id=None, initial_trade_risk_budget=Decimal("1"),
            realized_net_pnl=Decimal("0"),
        ))


def test_coordinator_scale_in_observer_is_mode_gated():
    database = object()
    disabled = BrooksFullCoreCoordinator(
        settings=SimpleNamespace(brooks_scale_in_mode="disabled"), database=database
    )
    assert disabled._scale_in_shadow_observer is None
    shadow = BrooksFullCoreCoordinator(
        settings=SimpleNamespace(brooks_scale_in_mode="shadow"), database=database
    )
    assert isinstance(shadow._scale_in_shadow_observer, ShadowScaleInObserver)


def test_scale_in_observer_module_has_no_execution_or_signal_creation_dependency():
    import inspect
    import app.modules.scale_in.runtime_observer as observer
    source = inspect.getsource(observer)
    assert "SignalService" not in source
    assert "Publisher" not in source
    assert "exchange_order" not in source
    assert "LiveVipRuntimeService" not in source
