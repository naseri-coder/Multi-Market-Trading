from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.modules.ai_council.service import AICouncilService
from app.modules.brooks_core.advanced_context import assess_advanced_context
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.brooks_core.engine_contract import (
    Chapter4PostEntryBarEvidence,
    Chapter4PostEntryLifecycle,
    Chapter4SignalEntryLifecycle,
)
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.risk_engine.service import RiskEngineService
from app.modules.signal_automation.entities import BrooksRuleEvidence, BrooksSignalImport
from app.modules.signal_automation.repository import (
    _brooks_core_typed_metadata,
    _chapter4_lifecycle_seed,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def minute_bar(minute: int, open_price: str = "100", close_price: str = "101") -> Candle:
    opened = BASE + timedelta(minutes=minute)
    o = D(open_price)
    c = D(close_price)
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=1),
        open=o,
        high=max(o, c) + D("1"),
        low=min(o, c) - D("1"),
        close=c,
        volume=D("1"),
    )


def lifecycle(
    *,
    direction: str = "LONG",
    timeframe: str = "5m",
    potential_index: int = 10,
    potential_open: datetime = BASE,
    intent_state: str = "CONFIRMED",
) -> Chapter4SignalEntryLifecycle:
    seconds = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "1h": 3600}[timeframe]
    potential_close = potential_open + timedelta(seconds=seconds)
    return Chapter4SignalEntryLifecycle(
        setup_identity_id="CH4:SETUP:ECON-1",
        source_signal_id="SRC-1",
        economic_opportunity_id="ECON-1",
        market_snapshot_id="SNAP-1",
        market_snapshot_hash="HASH-1",
        setup_type="TEST_SETUP",
        direction=direction,
        source_timeframe=timeframe,
        potential_signal_bar_identity_id="CH4:POTENTIAL:1",
        potential_signal_bar_index=potential_index,
        potential_signal_bar_open_time=potential_open.isoformat(),
        potential_signal_bar_close_time=potential_close.isoformat(),
        state="POTENTIAL_SIGNAL_WAITING_ENTRY",
        entry_intent_confirmation_scope="PRE_FILL_ENTRY_METHOD_OR_PATTERN_CONFIRMATION",
        entry_intent_confirmation_state=intent_state,
    )


def service() -> LiveSignalLifecycleService:
    return object.__new__(LiveSignalLifecycleService)


def promote(
    base: Chapter4SignalEntryLifecycle | None = None,
    *,
    activation_minute: int = 7,
) -> Chapter4SignalEntryLifecycle:
    item = lifecycle() if base is None else base
    return service()._promote_chapter4_entry(item, minute_bar(activation_minute))


def feed_bucket(
    item: Chapter4SignalEntryLifecycle,
    start_minute: int,
    relation: str,
) -> Chapter4SignalEntryLifecycle:
    span = {"3m": 3, "5m": 5}[item.source_timeframe]
    current = item
    for offset in range(span):
        if relation == "FAVORABLE":
            o = D("100") + offset
            c = o + D("1") if item.direction == "LONG" else o - D("1")
        elif relation == "ADVERSE":
            o = D("100") - offset
            c = o - D("1") if item.direction == "LONG" else o + D("1")
        else:
            o = c = D("100")
        current = service()._advance_chapter4_post_entry(
            current,
            minute_bar(start_minute + offset, str(o), str(c)),
        )
    return current


def import_command(*, include_chapter4: bool = True) -> BrooksSignalImport:
    evidence: tuple[BrooksRuleEvidence, ...] = ()
    if include_chapter4:
        evidence = (
            BrooksRuleEvidence(
                rule_id="BB-RNG-29-SIGNAL-BAR-STOP",
                status="PASS",
                source_pages=(202,),
                evidence=(
                    ("setup_type", "TEST_SETUP"),
                    ("direction", "LONG"),
                    ("entry_method", "STOP_TRIGGER_CONFIRMATION"),
                    ("entry_trigger_semantic", "SIGNAL_BAR_STOP_TRIGGER"),
                    ("economic_opportunity_id", "ECON-1"),
                    ("chapter4_setup_identity_id", "CH4:SETUP:ECON-1"),
                    ("chapter4_signal_bar_state", "POTENTIAL_SIGNAL_BAR"),
                    ("chapter4_potential_signal_bar_identity_id", "CH4:POTENTIAL:1"),
                    ("chapter4_potential_signal_bar_index", "10"),
                    ("chapter4_potential_signal_bar_open_time", BASE.isoformat()),
                    (
                        "chapter4_potential_signal_bar_close_time",
                        (BASE + timedelta(minutes=5)).isoformat(),
                    ),
                    (
                        "entry_intent_confirmation_scope",
                        "PRE_FILL_ENTRY_METHOD_OR_PATTERN_CONFIRMATION",
                    ),
                    ("entry_intent_confirmation_state", "CONFIRMED"),
                ),
            ),
        )
    return BrooksSignalImport(
        source_signal_id="SRC-1",
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=D("101"),
        stop_loss=D("99"),
        targets=(D("103"),),
        leverage=D("1"),
        exchange="binance",
        market_type="futures",
        timeframe="5m",
        setup_type="TEST_SETUP",
        market_snapshot_id="SNAP-1",
        market_snapshot_hash="HASH-1",
        engine_version="E1",
        rule_set_version="R1",
        configuration_version="C1",
        reasoning=(),
        rule_ids=tuple(item.rule_id for item in evidence),
        failed_rules=(),
        rule_evidence=evidence,
        generation_mode="LIVE",
        publication_scope="VIP",
    )


def test_c04_t001_prefill_potential_only():
    item = _chapter4_lifecycle_seed(import_command())
    assert item is not None
    assert item.state == "POTENTIAL_SIGNAL_WAITING_ENTRY"
    assert item.confirmed_signal_bar_identity_id is None
    assert item.entry_bar_identity_id is None
    assert item.post_entry_lifecycle is None


def test_c04_t002_actual_fill_promotes_same_bar_and_actual_interval():
    item = promote()
    assert item.state == "CONFIRMED_SIGNAL_ENTRY_ACTIVE"
    assert item.confirmed_signal_bar_identity_id == item.potential_signal_bar_identity_id
    assert item.confirmed_signal_bar_index == item.potential_signal_bar_index
    assert item.entry_bar_open_time == (BASE + timedelta(minutes=5)).isoformat()
    assert item.entry_bar_close_time == (BASE + timedelta(minutes=10)).isoformat()
    assert item.entry_activation_observed_at == (BASE + timedelta(minutes=8)).isoformat()
    assert item.fill_observation_resolution == "CLOSED_1M_CANDLE_TOUCH"


def test_c04_t003_signal_and_entry_nonconflation():
    item = promote()
    assert item.confirmed_signal_bar_identity_id != item.entry_bar_identity_id


def test_c04_t004_delayed_fill_uses_activation_interval():
    item = promote(activation_minute=17)
    assert item.entry_bar_open_time == (BASE + timedelta(minutes=15)).isoformat()
    assert item.entry_bar_index == 13
    assert item.entry_bar_index != item.potential_signal_bar_index + 1


def test_c04_t005_unfilled_waiting_entry_has_no_postfill_identity():
    item = lifecycle()
    assert item.confirmed_signal_bar_identity_id is None
    assert item.entry_bar_identity_id is None
    assert item.post_entry_lifecycle is None


@pytest.mark.parametrize(
    "reason",
    ["PENDING_ENTRY_STRUCTURAL_STOP_TOUCHED", "MONITORING_HISTORY_GAP"],
)
def test_c04_t006_terminal_unfilled_never_promotes(reason):
    item = service()._terminate_chapter4_unfilled(lifecycle(), reason)
    assert item.state == "UNFILLED_TERMINAL"
    assert item.unfilled_terminal_reason == reason
    assert item.confirmed_signal_bar_identity_id is None
    assert item.entry_bar_identity_id is None
    assert item.post_entry_lifecycle is None


def test_c04_t007_identity_continuity():
    before = lifecycle()
    after = promote(before)
    for field in (
        "setup_identity_id",
        "source_signal_id",
        "economic_opportunity_id",
        "market_snapshot_id",
        "market_snapshot_hash",
        "setup_type",
        "direction",
        "source_timeframe",
        "potential_signal_bar_identity_id",
    ):
        assert getattr(after, field) == getattr(before, field)


def test_c04_t008_entry_intent_confirmed_is_not_brooks_signal_confirmed():
    item = lifecycle(intent_state="CONFIRMED")
    assert item.entry_intent_confirmation_state == "CONFIRMED"
    assert item.state == "POTENTIAL_SIGNAL_WAITING_ENTRY"
    assert item.confirmed_signal_bar_identity_id is None


def test_c04_t009_no_followthrough_before_entry():
    before = lifecycle()
    after = service()._advance_chapter4_post_entry(before, minute_bar(10))
    assert after == before
    assert after.post_entry_lifecycle is None


def test_c04_t010_no_followthrough_at_entry():
    item = promote()
    assert item.post_entry_lifecycle is not None
    assert item.post_entry_lifecycle.completed_bars == ()
    assert item.post_entry_lifecycle.first_follow_through_bar_identity_id is None


def test_c04_t011_first_complete_postentry_bar_only_after_bucket_close():
    current = promote()
    for minute in range(10, 14):
        current = service()._advance_chapter4_post_entry(
            current, minute_bar(minute, "100", "101")
        )
        assert current.post_entry_lifecycle.completed_bars == ()
    current = service()._advance_chapter4_post_entry(
        current, minute_bar(14, "104", "105")
    )
    assert len(current.post_entry_lifecycle.completed_bars) == 1
    bar = current.post_entry_lifecycle.completed_bars[0]
    assert bar.open_time == (BASE + timedelta(minutes=10)).isoformat()
    assert bar.close_time == (BASE + timedelta(minutes=15)).isoformat()


def test_c04_t012_favorable_continuation():
    item = feed_bucket(promote(), 10, "FAVORABLE")
    post = item.post_entry_lifecycle
    assert post.completed_bars[0].directional_relation == "FAVORABLE_CONTINUATION"
    assert post.first_follow_through_bar_identity_id == post.completed_bars[0].bar_identity_id


def test_c04_t013_neutral_sideways_postentry_bar():
    item = feed_bucket(promote(), 10, "NEUTRAL")
    post = item.post_entry_lifecycle
    assert post.completed_bars[0].directional_relation == "NEUTRAL_OR_SIDEWAYS"
    assert post.first_follow_through_bar_identity_id is None


def test_c04_t014_adverse_postentry_bar():
    item = feed_bucket(promote(), 10, "ADVERSE")
    post = item.post_entry_lifecycle
    assert post.completed_bars[0].directional_relation == "ADVERSE"
    assert post.first_follow_through_bar_identity_id is None


def test_c04_t015_delayed_favorable_followthrough():
    item = feed_bucket(promote(), 10, "NEUTRAL")
    item = feed_bucket(item, 15, "FAVORABLE")
    post = item.post_entry_lifecycle
    assert post.completed_bars[0].directional_relation == "NEUTRAL_OR_SIDEWAYS"
    assert post.first_follow_through_bar_identity_id == post.completed_bars[1].bar_identity_id


def test_c04_t016_second_continuation_evidence():
    item = feed_bucket(promote(), 10, "FAVORABLE")
    item = feed_bucket(item, 15, "FAVORABLE")
    post = item.post_entry_lifecycle
    assert post.first_follow_through_bar_identity_id == post.completed_bars[0].bar_identity_id
    assert post.second_continuation_bar_identity_id == post.completed_bars[1].bar_identity_id
    assert post.first_follow_through_bar_identity_id != post.second_continuation_bar_identity_id


def test_c04_t017_generic_source_timeframe_aggregation():
    base = lifecycle(timeframe="3m", potential_index=20)
    active = promote(base, activation_minute=4)
    assert active.entry_bar_open_time == (BASE + timedelta(minutes=3)).isoformat()
    result = feed_bucket(active, 6, "FAVORABLE")
    assert len(result.post_entry_lifecycle.completed_bars) == 1
    assert result.post_entry_lifecycle.completed_bars[0].bar_index == 22


def test_c04_t018_aggregator_idempotency():
    item = feed_bucket(promote(), 10, "FAVORABLE")
    before = item.to_metadata()
    replayed = service()._advance_chapter4_post_entry(
        item, minute_bar(14, "104", "105")
    )
    assert replayed.to_metadata() == before
    assert len(replayed.post_entry_lifecycle.completed_bars) == 1


def test_c04_t019_future_evidence_does_not_rewrite_entry_snapshot():
    item = feed_bucket(promote(), 10, "FAVORABLE")
    entry_identity = item.entry_bar_identity_id
    first = item.post_entry_lifecycle.completed_bars[0]
    later = feed_bucket(item, 15, "FAVORABLE")
    assert later.entry_bar_identity_id == entry_identity
    assert later.post_entry_lifecycle.completed_bars[0] == first


def test_c04_t020_followthrough_has_no_trade_effect_helpers():
    source = inspect.getsource(LiveSignalLifecycleService._advance_chapter4_post_entry)
    for forbidden in (
        "update_stop_loss",
        "hit_target",
        "close_signal",
        "append_event",
        "publication",
        "leverage",
        "scale_in",
    ):
        assert forbidden not in source


def chapter4_snapshot(last_kind: str) -> MarketSnapshot:
    candles = []
    for index in range(30):
        opened = BASE + timedelta(minutes=15 * index)
        if index == 29 and last_kind == "BULL":
            o, c = D("100"), D("102")
        elif index == 29 and last_kind == "BEAR":
            o, c = D("102"), D("100")
        elif index == 29:
            o = c = D("101")
        else:
            o, c = D("100") + index, D("100.5") + index
        candles.append(
            Candle(
                open_time=opened,
                close_time=opened + timedelta(minutes=15),
                open=o,
                high=max(o, c) + D("1"),
                low=min(o, c) - D("1"),
                close=c,
                volume=D("10"),
            )
        )
    return MarketSnapshot(
        "binance",
        "futures",
        "BTCUSDT",
        "15m",
        tuple(candles),
        candles[-1].close_time,
    )


def one_bar_metadata(kind: str) -> dict[str, str]:
    snap = chapter4_snapshot(kind)
    policy = BrooksFullCorePolicy()
    context = assess_books_context(snap, policy=policy.context)
    advanced = assess_advanced_context(snap, policy=policy)
    evidence = BrooksTrilogyFullCoreEngine(policy=policy)._context_evidence(
        context, advanced, snapshot=snap
    )
    row = next(item for item in evidence if item.rule_id == "BB-V5-MARKET-PHASE")
    return dict(row.evidence)


@pytest.mark.parametrize("kind", ["BULL", "BEAR", "DOJI"])
def test_c04_t021_to_t023_one_bar_view_by_bar_kind(kind):
    data = one_bar_metadata(kind)
    assert data["chapter4_one_bar_range_state"] == "ONE_BAR_RANGE_VIEW"
    assert data["chapter4_one_bar_trade_eligible"] == "false"
    assert data["chapter4_established_range_identity"] == "false"


def test_c04_t024_bidirectional_breakout_and_fade_context_coexist():
    data = one_bar_metadata("BULL")
    assert data["chapter4_long_breakout_potential"] == "ABOVE_PRIOR_HIGH"
    assert data["chapter4_short_breakout_potential"] == "BELOW_PRIOR_LOW"
    assert data["chapter4_short_fade_potential"] == "AT_OR_ABOVE_PRIOR_HIGH"
    assert data["chapter4_long_fade_potential"] == "AT_OR_BELOW_PRIOR_LOW"


def test_c04_t025_one_bar_view_is_nontrade():
    data = one_bar_metadata("BULL")
    assert data["chapter4_one_bar_trade_eligible"] == "false"
    source = inspect.getsource(BrooksTrilogyFullCoreEngine._context_evidence)
    assert "BrooksPatternCandidate(" not in source


def test_c04_t026_one_bar_view_has_no_established_range_identity():
    data = one_bar_metadata("BEAR")
    assert data["chapter4_established_range_identity"] == "false"
    assert "range_id" not in data
    assert "range_episode_id" not in data


def test_c04_t027_one_bar_view_prefix_uses_closed_snapshot_bar():
    snap = chapter4_snapshot("BULL")
    data = one_bar_metadata("BULL")
    assert data["chapter4_one_bar_close_time"] == snap.candles[-1].close_time.isoformat()
    assert data["chapter4_one_bar_index"] == str(len(snap.candles) - 1)


def test_c04_t028_full_filled_lifecycle():
    stored = _brooks_core_typed_metadata(import_command())
    item = Chapter4SignalEntryLifecycle.from_metadata(
        stored["brooks_chapter4_lifecycle"]
    )
    assert item.state == "POTENTIAL_SIGNAL_WAITING_ENTRY"
    item = promote(item)
    assert item.state == "CONFIRMED_SIGNAL_ENTRY_ACTIVE"
    item = feed_bucket(item, 10, "FAVORABLE")
    assert len(item.post_entry_lifecycle.completed_bars) == 1


def test_c04_t029_full_nonfill_lifecycle():
    item = _chapter4_lifecycle_seed(import_command())
    item = service()._terminate_chapter4_unfilled(
        item, "PENDING_ENTRY_STRUCTURAL_STOP_TOUCHED"
    )
    assert item.state == "UNFILLED_TERMINAL"
    assert item.confirmed_signal_bar_identity_id is None
    assert item.entry_bar_identity_id is None
    assert item.post_entry_lifecycle is None


def production_candidate_from_fixture():
    raw = json.loads(
        (Path(__file__).parent / "fixtures/v5_council_geometry.json").read_text()
    )
    bars = []
    for row in raw:
        values = {
            key: D(row[key])
            for key in ("open", "high", "low", "close", "volume")
        }
        bars.append(
            Candle(
                open_time=datetime.fromisoformat(row["open_time"]),
                close_time=datetime.fromisoformat(row["close_time"]),
                **values,
            )
        )
    snapshot = MarketSnapshot(
        "binance", "futures", "BNBUSDT", "15m", tuple(bars), bars[-1].close_time
    )
    result = asyncio.run(
        BrooksTrilogyFullCoreEngine(
            policy=BrooksFullCorePolicy(enable_trade_decisions=True)
        ).evaluate(snapshot)
    )
    fields = {
        field.name: getattr(result, field.name)
        for field in dataclasses.fields(PaperSignalCandidate)
        if hasattr(result, field.name)
    }
    fields.update(
        source_signal_id="TEST_ONLY",
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        direction=result.decision,
        exchange=snapshot.exchange,
        market_type=snapshot.market_type,
        market_snapshot_id=snapshot.snapshot_id,
        market_snapshot_hash=snapshot.snapshot_hash,
        chart_path="TEST_NO_PUBLICATION",
        snapshot=snapshot,
    )
    return result, PaperSignalCandidate(**fields)


def test_c04_t030_trade_output_equivalence():
    result, candidate = production_candidate_from_fixture()
    assert result.decision == "SHORT"
    assert result.setup_type == "BULL_REVERSAL_BAR_FAILURE_SHORT"
    assert result.entry_price == D("721.780")
    assert result.stop_loss == D("723.51600")
    assert result.targets == (D("717.580"),)
    assert len(result.rule_evidence) == 55
    row = next(
        item
        for item in result.rule_evidence
        if item.rule_id == "BB-RNG-29-SIGNAL-BAR-STOP"
    )
    data = dict(row.evidence)
    assert data["economic_opportunity_id"] == (
        "BNBUSDT:15m:FAILED_FAILURE:BULL_REVERSAL_BAR_FAILURE_SHORT:SHORT:119"
    )
    assert data["chapter4_potential_signal_bar_index"] == "119"
    ai = AICouncilService().evaluate(candidate)
    risk = RiskEngineService().evaluate(candidate)
    assert ai.approved is True
    assert ai.final_score == 93.33
    assert risk.approved is True
    assert risk.risk_score == 82.0
    structural = risk.metadata["risk_semantic_breakdown"]["structural_validation"]
    assert structural["signal_index"] == 119
    assert structural["valid"] is True


def test_backward_compatibility_without_chapter4_metadata():
    command = import_command(include_chapter4=False)
    assert _chapter4_lifecycle_seed(command) is None
    assert "brooks_chapter4_lifecycle" not in _brooks_core_typed_metadata(command)


def test_typed_contract_roundtrip():
    active = feed_bucket(promote(), 10, "FAVORABLE")
    assert Chapter4SignalEntryLifecycle.from_metadata(active.to_metadata()) == active
    bar = active.post_entry_lifecycle.completed_bars[0]
    assert Chapter4PostEntryBarEvidence.from_metadata(bar.to_metadata()) == bar
    post = Chapter4PostEntryLifecycle.from_metadata(
        active.post_entry_lifecycle.to_metadata()
    )
    assert post == active.post_entry_lifecycle


def test_runtime_reachability_wiring():
    engine = inspect.getsource(BrooksTrilogyFullCoreEngine.evaluate)
    operations = inspect.getsource(LiveSignalLifecycleService._process_item)
    repository = inspect.getsource(_brooks_core_typed_metadata)
    assert "_context_evidence(context, advanced, snapshot=snapshot)" in engine
    assert "_chapter4_lifecycle_seed(command)" in repository
    assert "_promote_chapter4_entry" in operations
    assert "_advance_chapter4_post_entry" in operations


def test_post_entry_aggregator_has_no_hardcoded_timeframes():
    source = inspect.getsource(LiveSignalLifecycleService._advance_chapter4_post_entry)
    assert "15m" not in source
    assert "1h" not in source
    assert "TIMEFRAME_SECONDS" in source


def test_signal_index_remains_preentry_geometry_anchor():
    source = inspect.getsource(BrooksTrilogyFullCoreEngine._entry_execution_intent)
    assert "candidate.signal_index" in source
    result, _ = production_candidate_from_fixture()
    row = next(
        item
        for item in result.rule_evidence
        if item.rule_id == "BB-RNG-29-SIGNAL-BAR-STOP"
    )
    assert dict(row.evidence)["chapter4_potential_signal_bar_index"] == "119"


def test_reconciled_pending_path_marks_unfilled_without_promotion():
    from app.modules.signal_automation.repository import (
        SQLAlchemySignalAutomationRepository,
    )
    source = inspect.getsource(
        SQLAlchemySignalAutomationRepository.complete_reconciled_pending_lifecycle
    )
    assert "UNFILLED_TERMINAL" in source
    assert "RECONCILED_STALE_PENDING_SIGNAL" in source
    assert "CONFIRMED_SIGNAL_ENTRY_ACTIVE" not in source
