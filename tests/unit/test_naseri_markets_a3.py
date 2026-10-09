"""A3 persistent idempotency, outbox crash safety and forward observation tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from naseri_markets import (
    ChannelRoute, Direction, EngineDescriptor, EngineRegistry, EvidenceMode,
    Instrument, Market, SignalIntent,
)
from naseri_markets.delivery_ledger import IdentityConflict, SignalLedger, UnsafeDelivery
from naseri_markets.forward_metrics import ForwardObserver, ForwardState
from naseri_markets.quotes import QuoteOrigin, QuoteTick

TS = datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)
FX = Instrument(Market.FOREX, "mt5:demo", "EURUSD", "America/New_York", "USD")
INDEX = Instrument(Market.INDEX, "mt5:demo", "US30", "America/New_York", "USD")


def sig(engine="fx_01", inst=FX, direction=Direction.LONG, suffix="a"):
    return SignalIntent(
        f"sig-{suffix}", engine, "1.0", inst, direction, TS,
        Decimal("1.10100") if inst == FX else Decimal("43010"),
        Decimal("1.09900") if inst == FX else Decimal("42950"),
        (Decimal("1.10300") if inst == FX else Decimal("43100"),),
        EvidenceMode.FORWARD,
    )


def registry():
    r = EngineRegistry()
    r.register(EngineDescriptor("fx_01", "1.0", frozenset({Market.FOREX})))
    r.register(EngineDescriptor("index_01", "1.0", frozenset({Market.INDEX})))
    return r


def route(engine="fx_01", market=Market.FOREX, channel=-1001112223334):
    return ChannelRoute(engine, market, channel, True, True, True)


def tick(inst=FX, at=TS, bid="1.10000", ask="1.10004",
         origin=QuoteOrigin.LIVE):
    return QuoteTick(inst, at, Decimal(bid), Decimal(ask), origin)


def test_rejects_in_memory_database(tmp_path):
    with pytest.raises(ValueError):
        SignalLedger(":memory:")


def test_signal_idempotency_survives_restart(tmp_path):
    path = tmp_path / "outbox.db"
    db = SignalLedger(path)
    assert db.record(sig(), registry(), route())
    assert not db.record(sig(), registry(), route())
    assert len(db.pending("fx_01")) == 1
    db.close()
    reopened = SignalLedger(path)
    assert not reopened.record(sig(), registry(), route())
    assert reopened.get("fx_01", "sig-a").state == "PENDING"
    reopened.close()


def test_conflicting_content_or_channel_rejected(tmp_path):
    db = SignalLedger(tmp_path / "outbox.db")
    db.record(sig(), registry(), route())
    with pytest.raises(IdentityConflict):
        db.record(replace(sig(), entry=Decimal("1.10500"),
                          targets=(Decimal("1.10800"),)), registry(), route())
    with pytest.raises(IdentityConflict):
        db.record(sig(), registry(), route(channel=-1002223334445))
    assert db.get("fx_01", "sig-a").state == "PENDING"
    db.close()


def test_isolated_cross_engine_identical_signal_id(tmp_path):
    db = SignalLedger(tmp_path / "signals.db")
    db.record(sig(), registry(), route())
    db.record(sig(engine="index_01",inst=INDEX), registry(),
              route("index_01",Market.INDEX,-1006667778889))
    assert len(db.pending("fx_01")) == 1
    assert len(db.pending("index_01")) == 1
    db.close()


def test_invalid_route_writes_nothing(tmp_path):
    db = SignalLedger(tmp_path / "signals.db")
    with pytest.raises(UnsafeDelivery):
        db.record(sig(), registry(), replace(route(), channel_verified_private=False))
    assert db.get("fx_01", "sig-a") is None
    db.close()


def test_claim_requires_same_verified_private_route(tmp_path):
    db = SignalLedger(tmp_path / "signals.db")
    db.record(sig(), registry(), route())
    with pytest.raises(UnsafeDelivery):
        db.claim("fx_01", "sig-a", route=route(channel=-1009998887776),now=TS+timedelta(seconds=2))
    with pytest.raises(UnsafeDelivery):
        db.claim("fx_01", "sig-a", route=replace(route(), enabled=False),now=TS+timedelta(seconds=2))
    assert db.claim("fx_01", "sig-a", route=route(),now=TS+timedelta(seconds=2)).state == "CLAIMED"
    assert db.claim("fx_01", "sig-a", route=route(),now=TS+timedelta(seconds=2)) is None
    db.close()


def test_claim_without_ack_is_unknown_after_restart(tmp_path):
    path = tmp_path / "outbox.db"
    db = SignalLedger(path)
    db.record(sig(), registry(), route())
    db.claim("fx_01", "sig-a", route=route(),now=TS+timedelta(seconds=2))
    db.close()
    db2 = SignalLedger(path)
    assert db2.quarantine_inflight() == 1
    assert db2.get("fx_01", "sig-a").state == "UNKNOWN"
    assert db2.claim("fx_01", "sig-a", route=route(),now=TS+timedelta(seconds=2)) is None
    assert db2.pending("fx_01") == ()
    db2.close()


def test_acked_outbox_persists_as_sent(tmp_path):
    path = tmp_path / "outbox.db"
    db = SignalLedger(path)
    db.record(sig(), registry(), route())
    db.claim("fx_01", "sig-a", route=route(),now=TS+timedelta(seconds=2))
    assert db.acknowledge_sent("fx_01", "sig-a", message_id=123)
    assert not db.acknowledge_sent("fx_01", "sig-a", message_id=999)
    db.close()
    again = SignalLedger(path)
    assert again.get("fx_01", "sig-a").state == "SENT"
    assert again.get("fx_01", "sig-a").message_id == 123
    assert again.quarantine_inflight() == 0
    again.close()


def test_unclaimed_sent_ack_rejected(tmp_path):
    db = SignalLedger(tmp_path / "signals.db")
    db.record(sig(), registry(), route())
    assert not db.acknowledge_sent("fx_01", "sig-a", message_id=1)
    with pytest.raises(ValueError):
        db.acknowledge_sent("fx_01", "sig-a", message_id=True)
    db.close()


def test_foreign_instrument_tick_does_not_resolve_position(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    s=sig()
    assert ob.open(s, tick(), verified_live_source=True)
    with pytest.raises(ValueError):
        ob.observe(s, tick(INDEX,TS+timedelta(seconds=1), "43000","43002"),
                   verified_live_source=True)
    assert ob.get("fx_01", "sig-a").state is ForwardState.OPEN
    ob.close()


def test_forward_requires_attested_real_bid_ask_at_signal_time(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    with pytest.raises(ValueError):
        ob.open(sig(), tick(origin=QuoteOrigin.REPLAY), verified_live_source=True)
    with pytest.raises(ValueError):
        ob.open(sig(), tick(), verified_live_source=False)
    with pytest.raises(ValueError):
        ob.open(sig(), tick(at=TS+timedelta(seconds=1)), verified_live_source=True)
    assert ob.open(sig(), tick(), verified_live_source=True)
    assert not ob.open(sig(), tick(), verified_live_source=True)
    ob.close()


def test_forward_long_target_observed_using_bid(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    s=sig()
    ob.open(s,tick(),verified_live_source=True)
    row=ob.observe(s,tick(at=TS+timedelta(seconds=1),bid="1.10300",ask="1.10304"),
                   verified_live_source=True)
    assert row.state is ForwardState.TARGET_OBSERVED
    assert row.observed_r == Decimal("0.00296")/Decimal("0.00104")
    assert ob.summary("fx_01")["observed_mean_r"] == row.observed_r
    assert ob.summary("fx_01")["is_broker_filled"] is False
    ob.close()


def test_forward_long_stop_observed_using_bid(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    s=sig()
    ob.open(s,tick(),verified_live_source=True)
    result=ob.observe(s,tick(at=TS+timedelta(seconds=1),bid="1.09890",ask="1.09900"),
                      verified_live_source=True)
    assert result.state is ForwardState.STOP_OBSERVED
    assert result.observed_r < Decimal("-1")
    ob.close()


def test_forward_short_target_using_ask(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    short=SignalIntent(
        "sig-short","fx_01","1.0",FX,Direction.SHORT,TS,Decimal("1.10"),
        Decimal("1.10100"),(Decimal("1.09800"),),EvidenceMode.FORWARD,
    )
    ob.open(short,tick(bid="1.10000",ask="1.10004"),verified_live_source=True)
    row=ob.observe(short,tick(at=TS+timedelta(seconds=1),
                              bid="1.09790",ask="1.09800"),verified_live_source=True)
    assert row.state is ForwardState.TARGET_OBSERVED
    assert row.observed_r == Decimal("2")
    ob.close()


def test_data_gap_causes_unknown_not_fake_loss(tmp_path):
    path=tmp_path/"forward.db"
    s=sig()
    ob=ForwardObserver(path,max_gap_seconds=2)
    ob.open(s,tick(),verified_live_source=True)
    row=ob.observe(s,tick(at=TS+timedelta(seconds=5),bid="1.099",ask="1.0991"),
                   verified_live_source=True)
    assert row.state is ForwardState.UNKNOWN and row.observed_r is None
    assert ob.summary("fx_01")["resolved"] == 0
    ob.close()
    again=ForwardObserver(path,max_gap_seconds=2)
    assert again.get("fx_01","sig-a").state is ForwardState.UNKNOWN
    again.close()


def test_unverified_tick_after_open_marks_unknown(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    s=sig()
    ob.open(s,tick(),verified_live_source=True)
    row=ob.observe(s,tick(at=TS+timedelta(seconds=1),origin=QuoteOrigin.REPLAY),
                   verified_live_source=True)
    assert row.state is ForwardState.UNKNOWN
    ob.close()


def test_open_missing_gap_data_keeps_unresolved(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    s=sig()
    ob.open(s,tick(),verified_live_source=True)
    assert ob.get("fx_01","sig-a").state is ForwardState.OPEN
    assert ob.summary("fx_01")["observed_mean_r"] is None
    ob.close()


def test_forward_same_id_payload_collision(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    s=sig()
    ob.open(s,tick(),verified_live_source=True)
    with pytest.raises(ValueError):
        ob.open(replace(s,targets=(Decimal("1.10400"),)),
                tick(),verified_live_source=True)
    ob.close()


def test_forward_report_isolated_per_engine(tmp_path):
    ob=ForwardObserver(tmp_path/"forward.db")
    ob.open(sig(),tick(),verified_live_source=True)
    assert ob.summary("index_01")["total"] == 0
    assert ob.summary("fx_01")["total"] == 1
    ob.close()


def test_expired_pending_signal_never_claimed_after_restart(tmp_path):
    path = tmp_path / "signals.db"
    db = SignalLedger(path)
    db.record(sig(), registry(), route())
    assert db.claim("fx_01", "sig-a", route=route(),
                    now=TS+timedelta(minutes=2)) is None
    assert db.get("fx_01", "sig-a").state == "EXPIRED"
    assert db.pending("fx_01") == ()
    db.close()
    db2 = SignalLedger(path)
    assert db2.claim("fx_01", "sig-a", route=route(), now=TS) is None
    db2.close()


def test_claim_rejects_time_travel_and_zero_max_age(tmp_path):
    db = SignalLedger(tmp_path / "signals.db")
    db.record(sig(), registry(), route())
    with pytest.raises(ValueError):
        db.claim("fx_01", "sig-a", route=route(), now=TS, max_age_seconds=0)
    assert db.claim("fx_01", "sig-a", route=route(),
                    now=TS-timedelta(seconds=1)) is None
    assert db.get("fx_01", "sig-a").state == "EXPIRED"
    db.close()


def test_observation_refuses_price_already_beyond_target_at_entry(tmp_path):
    ob = ForwardObserver(tmp_path / "forward.db")
    with pytest.raises(ValueError, match="geometry"):
        ob.open(sig(), tick(bid="1.10400", ask="1.10404"),
                verified_live_source=True)
    ob.close()
