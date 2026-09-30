import asyncio
from types import SimpleNamespace

from app.modules.signal_automation.entities import FINAL_BROOKS_HP_SEMANTIC_COHORT_ID
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
    HistoricalProbabilityRepository,
)


class _EmptyResult:
    def all(self):
        return []


class _RecordingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyResult()


async def _sql(domain: str) -> str:
    session = _RecordingSession()
    assert await HistoricalProbabilityRepository(session, data_domain=domain).load_cases() == ()
    return str(session.statement.compile(compile_kwargs={"literal_binds": True}))


def _case(signal_id: int, *, cohort: str | None) -> HistoricalCase:
    return HistoricalCase(
        signal_id=signal_id,
        setup_type="FAILED_BREAKOUT_LONG",
        timeframe="15m",
        direction="LONG",
        structure_quality=80.0,
        context_quality=80.0,
        entry_quality=80.0,
        risk_feature=50.0,
        outcome=1,
        rule_ids=(),
        semantic_cohort_id=cohort,
    )


def _candidate():
    return SimpleNamespace(
        setup_type="FAILED_BREAKOUT_LONG",
        timeframe="15m",
        direction="LONG",
        entry_price=100.0,
        stop_loss=99.0,
        targets=(101.0,),
        rule_evidence=(),
        semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
    )


async def main() -> None:
    legacy = await _sql("LEGACY_MIXED")
    futures = await _sql("FUTURES_ONLY")
    assert "engine_version =" not in legacy
    assert "rule_set_version =" not in legacy
    assert "configuration_version =" not in legacy
    assert "signal_automation_metadata.exchange = 'binance'" not in legacy
    assert "signal_automation_metadata.market_type = 'futures'" not in legacy
    assert "signal_automation_metadata.exchange = 'binance'" in futures
    assert "signal_automation_metadata.market_type = 'futures'" in futures

    candidate = _candidate()
    contaminated = tuple(_case(i, cohort=None) for i in range(1, 25)) + tuple(
        _case(i, cohort=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID) for i in range(25, 27)
    )
    blocked = HistoricalProbabilityEngine(contaminated).assess(candidate)
    assert not blocked.calibrated
    assert blocked.cohort_isolation_applied
    assert blocked.semantic_cohort_id == FINAL_BROOKS_HP_SEMANTIC_COHORT_ID

    compatible = tuple(
        _case(i, cohort=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID) for i in range(1, 9)
    )
    calibrated = HistoricalProbabilityEngine(compatible).assess(candidate)
    assert calibrated.calibrated
    assert calibrated.sample_size == 8
    assert all(i in calibrated.neighbor_signal_ids for i in range(1, 9))
    print("PRODUCTION_HP_SEMANTIC_COHORT_GUARD=PASS")
    print("PRODUCTION_HP_REGRESSION_GUARD=PASS")


asyncio.run(main())
