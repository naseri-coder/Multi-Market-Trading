"""Cross-symbol economic identity and HP market-cohort isolation."""
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.signal_automation.entities import (
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID as FINAL,
    HP_COLD_START_BOOTSTRAP_POLICY_ID as POLICY,
)
from app.modules.signal_intelligence import probability as hp
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
    HistoricalProbabilityRepository,
    _deduplicate_hp_economic_opportunities,
    historical_probability_sample_accounting,
)


def economic(symbol, *, origin=119, explicit=None, timeframe="15m"):
    metadata = () if explicit is None else (("economic_opportunity_id", explicit),)
    candidate = NS(
        metadata=metadata,
        family="BREAKOUT",
        setup_type="BREAKOUT_LONG",
        direction="LONG",
        signal_index=origin,
        symbol=symbol,
        timeframe=timeframe,
    )
    return BrooksTrilogyFullCoreEngine()._entry_execution_intent(
        candidate,
        timeframe=timeframe,
    ).economic_opportunity_id


def candidate(symbol="BTCUSDT", *, setup="H2_CONFIRMED", cohort=FINAL):
    return NS(
        symbol=symbol,
        setup_type=setup,
        timeframe="15m",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"),),
        rule_evidence=(),
        semantic_cohort_id=cohort,
    )


def case(
    signal_id,
    *,
    symbol="BTCUSDT",
    setup="H2_CONFIRMED",
    timeframe="15m",
    cohort=FINAL,
    econ=None,
    mode="LIVE",
    policy=None,
    outcome=1,
):
    return HistoricalCase(
        signal_id=signal_id,
        setup_type=setup,
        timeframe=timeframe,
        direction="LONG",
        structure_quality=80.0,
        context_quality=80.0,
        entry_quality=80.0,
        risk_feature=50.0,
        outcome=outcome,
        rule_ids=(),
        semantic_cohort_id=cohort,
        generation_mode=mode,
        bootstrap_policy_id=policy,
        economic_opportunity_id=econ,
        symbol=symbol,
    )


def test_economic_identity_is_stable_within_symbol_and_separate_across_symbols():
    btc_a = economic("BTCUSDT")
    btc_b = economic("btcusdt")
    eth = economic("ETHUSDT")
    assert btc_a == btc_b == "BTCUSDT:15m:BREAKOUT:BREAKOUT_LONG:LONG:119"
    assert eth == "ETHUSDT:15m:BREAKOUT:BREAKOUT_LONG:LONG:119"
    assert btc_a != eth


def test_explicit_upstream_identity_gets_one_symbol_component():
    assert economic("BTCUSDT", explicit="opaque") == "BTCUSDT:15m:opaque"
    assert economic("BTCUSDT", explicit="BTCUSDT:opaque") == "BTCUSDT:15m:opaque"


def test_distinct_same_symbol_origins_remain_distinct():
    assert economic("BTCUSDT", origin=119) != economic("BTCUSDT", origin=120)


def test_timeframe_is_an_explicit_economic_identity_dimension():
    assert economic("BTCUSDT", timeframe="15m") != economic("BTCUSDT", timeframe="1h")


@pytest.mark.parametrize("order", [("SHADOW", "LIVE"), ("LIVE", "SHADOW")])
def test_live_shadow_precedence_is_symbol_aware(order):
    rows = {
        "SHADOW": case(2, econ="BTCUSDT:opaque", mode="SHADOW", policy=POLICY),
        "LIVE": case(1, econ="BTCUSDT:opaque", mode="LIVE"),
    }
    selected = _deduplicate_hp_economic_opportunities(tuple(rows[x] for x in order))
    assert len(selected) == 1
    assert selected[0].generation_mode == "LIVE"


def test_distinct_symbols_are_not_collapsed_by_hp_dedup():
    rows = (
        case(1, symbol="BTCUSDT", econ="same-structure"),
        case(2, symbol="ETHUSDT", econ="same-structure"),
    )
    assert len(_deduplicate_hp_economic_opportunities(rows)) == 2


def test_legacy_economic_id_is_not_collapsed_across_timeframes():
    rows = (
        case(1, timeframe="15m", econ="legacy-same-id"),
        case(2, timeframe="1h", econ="legacy-same-id"),
    )
    assert len(_deduplicate_hp_economic_opportunities(rows)) == 2


def test_legacy_economic_id_still_deduplicates_within_timeframe():
    rows = (
        case(1, timeframe="15m", econ="legacy-same-id"),
        case(2, timeframe="15m", econ="legacy-same-id"),
    )
    assert len(_deduplicate_hp_economic_opportunities(rows)) == 1


def test_cross_symbol_exact_history_cannot_calibrate_candidate():
    rows = tuple(case(i, symbol="BTCUSDT") for i in range(1, 3))
    rows += tuple(case(i, symbol="ETHUSDT") for i in range(3, 11))
    result = HistoricalProbabilityEngine(rows).assess(candidate())
    assert result.calibrated is False
    assert result.compatible_case_count == 2


def test_same_symbol_exact_history_still_calibrates():
    rows = tuple(case(i, symbol="BTCUSDT") for i in range(1, 9))
    rows += tuple(case(i, symbol="ETHUSDT") for i in range(9, 17))
    result = HistoricalProbabilityEngine(rows).assess(candidate())
    assert result.calibrated is True
    assert result.sample_size == 8
    assert result.neighbor_signal_ids == tuple(range(1, 9))


def test_family_fallback_cannot_borrow_other_symbol():
    rows = tuple(case(i, symbol="BTCUSDT", setup="H2_OTHER_LONG") for i in range(1, 12))
    rows += tuple(case(i, symbol="ETHUSDT", setup="H2_OTHER_LONG") for i in range(12, 24))
    result = HistoricalProbabilityEngine(rows).assess(candidate(setup="H2_NEW_LONG"))
    assert result.calibrated is False
    assert result.compatible_case_count == 11


def test_direction_fallback_cannot_borrow_other_symbol():
    rows = tuple(case(i, symbol="BTCUSDT", setup=f"OTHER_{i}") for i in range(1, 20))
    rows += tuple(case(i, symbol="ETHUSDT", setup=f"FOREIGN_{i}") for i in range(20, 40))
    result = HistoricalProbabilityEngine(rows).assess(candidate(setup="UNSEEN"))
    assert result.calibrated is False
    assert result.compatible_case_count == 19


def test_unknown_symbol_and_wrong_cohort_are_excluded():
    rows = tuple(case(i, symbol=None) for i in range(1, 9))
    rows += tuple(case(i, symbol="BTCUSDT", cohort="LEGACY") for i in range(9, 17))
    result = HistoricalProbabilityEngine(rows).assess(candidate())
    assert result.calibrated is False
    assert result.compatible_case_count == 0


def test_nearest_neighbors_and_accounting_are_same_symbol_only():
    rows = tuple(case(i, symbol="BTCUSDT") for i in range(1, 9))
    rows += tuple(case(i, symbol="ETHUSDT") for i in range(9, 29))
    result = HistoricalProbabilityEngine(rows).assess(candidate())
    accounting = historical_probability_sample_accounting(rows, candidate())
    assert set(result.neighbor_signal_ids) == set(range(1, 9))
    assert accounting["total_eligible_same_cohort"] == 8


class _EmptyRows:
    def all(self):
        return ()


class _RecordingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyRows()


@pytest.mark.asyncio
async def test_repository_filters_symbol_before_loading_and_preserves_market_filters():
    session = _RecordingSession()
    repo = HistoricalProbabilityRepository(
        session,
        data_domain="FUTURES_ONLY",
        semantic_cohort_id=FINAL,
        symbol="btcusdt",
    )
    assert await repo.load_cases() == ()
    sql = str(session.statement)
    assert "signals.symbol" in sql
    assert "signal_automation_metadata.exchange" in sql
    assert "signal_automation_metadata.market_type" in sql
    assert repo.symbol == "BTCUSDT"


def test_thresholds_and_semantic_cohort_are_unchanged():
    assert (hp._MIN_EXACT, hp._MIN_FAMILY, hp._MIN_BROAD, hp._MAX_NEIGHBORS) == (
        8, 12, 20, 20
    )
    assert FINAL == "BROOKS_HP_SEMANTIC_COHORT_W01_W19_V1"
