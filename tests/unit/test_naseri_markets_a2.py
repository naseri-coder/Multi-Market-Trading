"""Offline A2 contract, market, isolation, DST and data-integrity regression."""
from dataclasses import replace
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal

import pytest

from naseri_markets import Direction, EngineDescriptor, EngineRegistry, EvidenceMode
from naseri_markets import Instrument, Market, SignalIntent
from naseri_markets.adapters import normalize_binance_usdm_book_ticker, normalize_mt5_symbol_tick
from naseri_markets.quotes import FeedPolicy, QuoteOrigin, QuoteQualityGate, QuoteTick, QuoteVerdict
from naseri_markets.runtime import EngineBinding, MultiEngineRunner
from naseri_markets.sessions import SessionPolicy, TradingWindow

UTC = timezone.utc
TS = datetime(2026, 10, 9, 13, 30, tzinfo=UTC)
CRYPTO = Instrument(Market.CRYPTO, "binance-usdm", "BTCUSDT", "UTC", "USDT")
FX = Instrument(Market.FOREX, "mt5:demo", "EURUSD", "America/New_York", "USD")


def q(inst=FX, at=TS, origin=QuoteOrigin.REPLAY):
    return QuoteTick(inst, at, Decimal("1.10000"), Decimal("1.10004"), origin)


def rule(verified=True, timezone_name="UTC"):
    return SessionPolicy(timezone_name, tuple(
        TradingWindow(d, time(0), time(23, 59)) for d in range(7)
    ), verified=verified)


class FakeEngine:
    def __init__(self, engine_id, version="1.0", *, bad=False, fails=False):
        self.engine_id = engine_id
        self.engine_version = version
        self.bad = bad
        self.fails = fails
        self.calls = 0

    async def on_quote(self, tick):
        self.calls += 1
        if self.fails:
            raise RuntimeError("engine synthetic failure")
        return [SignalIntent(
            f"{self.engine_id}-{self.calls}", self.engine_id, self.engine_version,
            tick.instrument, Direction.LONG, tick.occurred_at,
            Decimal("1.10000"), Decimal("1.09900"), (Decimal("1.10200"),),
            EvidenceMode.FORWARD if self.bad else EvidenceMode.PAPER,
        )]


def setup(engines=("alpha",), active=True, verified=True, enabled=True):
    registry = EngineRegistry()
    runner = MultiEngineRunner(registry, active=active)
    fake = {}
    for engine_id in engines:
        desc = EngineDescriptor(engine_id, "1.0", frozenset({Market.FOREX}))
        registry.register(desc)
        engine = FakeEngine(engine_id)
        runner.attach(EngineBinding(
            desc, frozenset({FX}), rule(verified), enabled=enabled,
        ), engine)
        fake[engine_id] = engine
    return runner, fake


def test_quote_bid_ask_types_and_spread():
    assert q().spread == Decimal("0.00004")
    with pytest.raises(ValueError):
        replace(q(), bid=Decimal("2"))
    with pytest.raises(ValueError):
        replace(q(), ask=float("nan"))
    with pytest.raises(ValueError):
        replace(q(), bid=Decimal("NaN"))


def test_quote_timezone_required():
    with pytest.raises(ValueError):
        replace(q(), occurred_at=datetime(2026, 10, 9))


def test_provider_is_part_of_instrument_identity():
    assert FX != replace(FX, provider="mt5:other")


def test_binance_normalization_and_missing_event_time():
    event = {"E": 1791552600000, "s": "BTCUSDT", "b": "62000.1", "a": "62000.2"}
    tick = normalize_binance_usdm_book_ticker(event, CRYPTO)
    assert tick.origin is QuoteOrigin.REPLAY
    assert tick.bid == Decimal("62000.1")
    with pytest.raises(ValueError):
        normalize_binance_usdm_book_ticker({k:v for k,v in event.items() if k!="E"}, CRYPTO)
    with pytest.raises(ValueError):
        normalize_binance_usdm_book_ticker({**event, "s":"ETHUSDT"}, CRYPTO)


def test_mt5_normalization_and_no_missing_ms():
    event={"symbol":"EURUSD","time_msc":1791552600000,"bid":"1.10","ask":"1.11"}
    assert normalize_mt5_symbol_tick(event, FX).spread == Decimal("0.01")
    with pytest.raises(ValueError):
        normalize_mt5_symbol_tick({k:v for k,v in event.items() if k!="time_msc"}, FX)
    with pytest.raises(ValueError):
        normalize_mt5_symbol_tick({**event,"symbol":"GBPUSD"}, FX)


@pytest.mark.parametrize("val", [None, True, 0, -1, "1700000000000"])
def test_invalid_provider_timestamps_fail(val):
    with pytest.raises(ValueError):
        normalize_mt5_symbol_tick(
            {"symbol":"EURUSD","time_msc":val,"bid":"1.10","ask":"1.11"}, FX
        )


def test_quality_gate_rejects_untrusted_live():
    tick=q(origin=QuoteOrigin.LIVE)
    gate=QuoteQualityGate()
    assert gate.inspect(tick, now=TS) is QuoteVerdict.UNVERIFIED
    assert gate.inspect(tick, now=TS, trusted_live_source=True) is QuoteVerdict.ACCEPTED


def test_quality_gate_rejects_fake_trusted_replay():
    assert QuoteQualityGate().inspect(q(), now=TS, trusted_live_source=True) is QuoteVerdict.UNVERIFIED


def test_quality_gate_stale_quarantine_and_reset():
    gate=QuoteQualityGate(FeedPolicy(max_age_seconds=5))
    assert gate.inspect(q(at=TS-timedelta(seconds=8)), now=TS) is QuoteVerdict.STALE
    assert gate.inspect(q(), now=TS) is QuoteVerdict.QUARANTINED
    gate.reset(FX)
    assert gate.inspect(q(), now=TS) is QuoteVerdict.ACCEPTED


def test_quality_gate_out_of_order_and_duplicate():
    gate=QuoteQualityGate()
    assert gate.inspect(q(), now=TS) is QuoteVerdict.ACCEPTED
    assert gate.inspect(q(), now=TS) is QuoteVerdict.DUPLICATE
    assert gate.inspect(q(at=TS-timedelta(seconds=1)), now=TS) is QuoteVerdict.OUT_OF_ORDER
    assert gate.inspect(q(at=TS+timedelta(milliseconds=1)), now=TS) is QuoteVerdict.QUARANTINED


def test_quality_gate_future_and_spread():
    assert QuoteQualityGate().inspect(
        q(at=TS+timedelta(seconds=2)), now=TS) is QuoteVerdict.FUTURE
    assert QuoteQualityGate().inspect(
        replace(q(), ask=Decimal("1.2")), now=TS) is QuoteVerdict.SPREAD


def test_session_requires_verification_and_holiday_override():
    assert not rule(False).is_open(TS)
    full=SessionPolicy("UTC", (TradingWindow(4,time(0),time(23,59)),),
                       frozenset({date(2026,10,9)}), True)
    assert not full.is_open(TS)


def test_dst_is_iana_based_not_fixed_utc():
    s=SessionPolicy("America/New_York",
                    (TradingWindow(4, time(9,30),time(10)),),verified=True)
    assert s.is_open(datetime(2026,3,6,14,30,tzinfo=UTC))
    monday=SessionPolicy("America/New_York",
                    (TradingWindow(0,time(9,30),time(10)),),verified=True)
    assert monday.is_open(datetime(2026,3,9,13,30,tzinfo=UTC))
    assert not monday.is_open(datetime(2026,3,9,14,30,tzinfo=UTC))


def test_session_overnight_and_weekend():
    s=SessionPolicy("UTC", (TradingWindow(6,time(17),time(2)),),verified=True)
    assert s.is_open(datetime(2026,10,11,18,tzinfo=UTC))
    assert s.is_open(datetime(2026,10,12,1,tzinfo=UTC))
    assert not s.is_open(datetime(2026,10,12,3,tzinfo=UTC))


@pytest.mark.asyncio
async def test_runtime_default_disabled():
    runner,_=setup(active=False)
    result=await runner.process(q(),now=TS)
    assert not result.by_engine


@pytest.mark.asyncio
async def test_runtime_binding_disabled():
    runner,fake=setup(enabled=False)
    result=await runner.process(q(),now=TS)
    assert not result.by_engine and fake["alpha"].calls==0


@pytest.mark.asyncio
async def test_runner_isolates_engines_and_instruments():
    runner,fake=setup(engines=("alpha","beta"))
    result=await runner.process(q(),now=TS)
    assert set(result.by_engine)=={"alpha","beta"}
    assert not result.faulted_engines
    foreign=replace(FX,provider="mt5:foreign")
    other=await runner.process(q(inst=foreign),now=TS)
    assert not other.by_engine
    assert fake["alpha"].calls==1


@pytest.mark.asyncio
async def test_runner_replay_output_never_forward():
    r,e=setup()
    e["alpha"].bad=True
    result=await r.process(q(),now=TS)
    assert result.faulted_engines==("alpha",)
    assert not result.by_engine


@pytest.mark.asyncio
async def test_runner_fault_isolation_and_recovery():
    r,e=setup(engines=("alpha","beta"))
    e["alpha"].fails=True
    result=await r.process(q(),now=TS)
    assert result.faulted_engines==("alpha",)
    assert "beta" in result.by_engine
    assert r.state("alpha")== (True,"RuntimeError")
    r.reset_engine("alpha")
    assert r.state("alpha")== (False,None)


@pytest.mark.asyncio
async def test_runner_does_not_process_unverified_calendar():
    r,e=setup(verified=False)
    assert not (await r.process(q(),now=TS)).by_engine
    assert e["alpha"].calls==0


@pytest.mark.asyncio
async def test_attested_live_with_forward_does_not_send_orders():
    r,e=setup()
    e["alpha"].bad=True
    result=await r.process(q(origin=QuoteOrigin.LIVE),now=TS,trusted_live_source=True)
    assert "alpha" in result.by_engine
    assert not hasattr(r,"place_order") and not hasattr(r,"send_message")
