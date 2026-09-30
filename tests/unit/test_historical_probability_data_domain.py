import pytest

from app.modules.signal_intelligence.probability import HistoricalProbabilityRepository


class _EmptyResult:
    def all(self):
        return []


class _RecordingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyResult()


def _compiled_sql(session: _RecordingSession) -> str:
    assert session.statement is not None
    return str(session.statement.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_legacy_mixed_preserves_existing_unfiltered_history_query():
    session = _RecordingSession()
    cases = await HistoricalProbabilityRepository(session, data_domain="LEGACY_MIXED").load_cases()
    sql = _compiled_sql(session)
    assert cases == ()
    assert "signal_automation_metadata.exchange = 'binance'" not in sql
    assert "signal_automation_metadata.market_type = 'futures'" not in sql


@pytest.mark.asyncio
async def test_futures_only_adds_binance_futures_history_filter():
    session = _RecordingSession()
    cases = await HistoricalProbabilityRepository(session, data_domain="FUTURES_ONLY").load_cases()
    sql = _compiled_sql(session)
    assert cases == ()
    assert "signal_automation_metadata.exchange = 'binance'" in sql
    assert "signal_automation_metadata.market_type = 'futures'" in sql


def test_unknown_probability_data_domain_fails_closed():
    with pytest.raises(ValueError, match="unsupported Historical Probability data domain"):
        HistoricalProbabilityRepository(_RecordingSession(), data_domain="SPOT")
