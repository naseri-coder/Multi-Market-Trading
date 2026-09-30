from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest
from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.signal_automation.entities import BrooksRuleEvidence

def snap():
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    c = Candle(
        open_time=start,
        close_time=start + timedelta(minutes=15),
        open=Decimal("100"), high=Decimal("110"), low=Decimal("90"),
        close=Decimal("105"), volume=Decimal("1"),
    )
    return MarketSnapshot(
        exchange="binance", market_type="spot", symbol="BTCUSDT",
        timeframe="15m", candles=(c,),
        captured_at=start + timedelta(minutes=16),
    )

def decision(s, side="LONG"):
    return BrooksCoreDecision(
        decision=side,
        source_signal_id=None if side == "NO_SIGNAL" else "core-1",
        entry_price=None if side == "NO_SIGNAL" else Decimal("106"),
        stop_loss=None if side == "NO_SIGNAL" else Decimal("99"),
        targets=() if side == "NO_SIGNAL" else (Decimal("120"),),
        setup_type="H2",
        reasoning=("context aligned",),
        rule_ids=("BR-007",),
        failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BR-007", "PASS", (11,)),),
        engine_version="v1",
        rule_set_version="r1",
        configuration_version="c1",
        market_snapshot_id=s.snapshot_id,
        market_snapshot_hash=s.snapshot_hash,
        chart_path=None if side == "NO_SIGNAL" else "/tmp/chart.png",
    )

def test_tradeable_maps_to_paper_candidate():
    s = snap()
    c = to_paper_candidate(snapshot=s, decision=decision(s))
    assert c is not None
    assert c.market_snapshot_id == s.snapshot_id
    assert c.market_snapshot_hash == s.snapshot_hash

def test_no_signal_maps_to_none():
    s = snap()
    assert to_paper_candidate(snapshot=s, decision=decision(s, "NO_SIGNAL")) is None

def test_snapshot_id_mismatch_is_rejected():
    s = snap()
    d = decision(s)
    bad = BrooksCoreDecision(
        decision=d.decision, source_signal_id=d.source_signal_id,
        entry_price=d.entry_price, stop_loss=d.stop_loss, targets=d.targets,
        setup_type=d.setup_type, reasoning=d.reasoning, rule_ids=d.rule_ids,
        failed_rules=d.failed_rules, rule_evidence=d.rule_evidence,
        engine_version=d.engine_version, rule_set_version=d.rule_set_version,
        configuration_version=d.configuration_version,
        market_snapshot_id="wrong", market_snapshot_hash=d.market_snapshot_hash,
        chart_path=d.chart_path,
    )
    with pytest.raises(ValueError, match="snapshot_id mismatch"):
        to_paper_candidate(snapshot=s, decision=bad)
