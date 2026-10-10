"""Exchange and period selection are tightly bound to PAPER execution."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.brooks_kraken_feed import (
    KrakenFeedRefused, poll_once as kraken_poll, closed_kraken_candles,
)
from naseri_markets.brooks_market_feed import (
    BrooksMarketFeedRefused, poll_once as binance_poll,
)
from naseri_markets.brooks_paper_service import BrooksPaperService
from naseri_markets.brooks_replay import SECONDS, parse_candle_replay
from naseri_markets.engine_control_store import (
    EngineControlStore, BROOKS_ENGINE_ID, OWNER_CORE_ID, TIMEFRAMES,
)
from naseri_markets.futures_venues import (
    FUTURES_VENUES, get_venue, paper_feed_verified,
)
from naseri_markets.trusted_custom import LocalCustomRefused

LEGACY = Path(__file__).resolve().parents[2] / "production_source"
PERIODS = ("1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d")


def set_pref(host, field, value):
    pref = host.preferences(BROOKS_ENGINE_ID)
    return host.change_preference(
        BROOKS_ENGINE_ID, field=field, value=value,
        expected_revision=pref["revision"], actor_id=123)


def arm(host):
    engine = host.get(BROOKS_ENGINE_ID)
    host.toggle_as_admin(
        BROOKS_ENGINE_ID, enabled=True,
        expected_revision=engine.revision, actor_id=123)
    set_pref(host, "signal_environment", "PAPER")


def candles(frame):
    seconds = SECONDS[frame]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {"time": int((start + timedelta(seconds=i * seconds)).timestamp() * 1000),
         "open": "100", "high": "101", "low": "99",
         "close": "100", "volume": "20"}
        for i in range(73)]
    return rows, start + timedelta(seconds=72 * seconds + 5)


def transport(frame, rows):
    def fetch(symbol, timeframe, count, timeout):
        assert (symbol, timeframe, count) == ("PF_XBTUSD", frame, 73)
        return json.dumps({"candles": rows, "more_candles": False}).encode()
    return fetch


def instruments():
    return json.dumps({"result": "success", "instruments": [{
        "symbol": "PF_XBTUSD", "tradeable": True, "type": "futures_vanilla",
        "tickSize": 0.5}]}).encode()


def test_exact_twenty_venues_and_geographic_caution():
    keys = [v.key for v in FUTURES_VENUES]
    assert len(keys) == len(set(keys)) == 20
    assert {"kraken", "binance", "weex", "coinex", "mexc"} <= set(keys)
    assert all(get_venue(x).iran_access in (
        "EXPLICIT_RESTRICTION", "UNVERIFIED") for x in keys)
    assert all(get_venue(x).name for x in keys)
    assert {x for x in keys if paper_feed_verified(x)} == {"kraken"}
    for key in ("kraken", "weex", "coinex"):
        assert get_venue(key).iran_access == "EXPLICIT_RESTRICTION"
    with pytest.raises(ValueError):
        get_venue("unknown")


def test_exact_eight_periods():
    assert TIMEFRAMES == PERIODS
    assert tuple(SECONDS) == PERIODS
    assert SECONDS["30m"] == 1800
    assert SECONDS["12h"] == 43200


@pytest.mark.parametrize("frame", PERIODS)
def test_eight_finalized_kraken_timeframes(frame):
    rows, now = candles(frame)
    data, last = closed_kraken_candles(
        symbol="PF_XBTUSD", timeframe=frame, bars=72,
        now=now, transport=transport(frame, rows))
    raw, instrument, parsed = parse_candle_replay(data)
    assert raw["timeframe"] == frame
    assert raw["market_type"] == "futures"
    assert instrument.symbol == "PF_XBTUSD"
    assert parsed[-1]["close_time"] == last


def test_cas_exchange_setting_persists_and_private_custom_denied(tmp_path):
    with EngineControlStore(tmp_path, owner_visible=True) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_exchange"] == "kraken"
        before = host.preferences(BROOKS_ENGINE_ID)["revision"]
        result = set_pref(host, "futures_exchange", "mexc")
        assert result["futures_feed_status"] == "CATALOG_ONLY"
        with pytest.raises(LocalCustomRefused, match="STALE"):
            host.change_preference(
                BROOKS_ENGINE_ID, field="futures_exchange",
                value="binance", expected_revision=before, actor_id=123)
        with pytest.raises(LocalCustomRefused, match="ALLOWLIST"):
            set_pref(host, "futures_exchange", "unknown")
        host.register_owner_reference(engine_id=OWNER_CORE_ID, actor_id=123)
        with pytest.raises(LocalCustomRefused, match="ALLOWLIST"):
            host.change_preference(
                OWNER_CORE_ID, field="futures_exchange", value="mexc",
                expected_revision=1, actor_id=123)
    with EngineControlStore(tmp_path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_exchange"] == "mexc"
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == result["revision"]


def test_unverified_selection_refuses_both_actual_provider_http(tmp_path):
    with EngineControlStore(tmp_path) as host:
        arm(host)
        set_pref(host, "futures_exchange", "lbank")
    calls = []
    def forbidden(*args):
        calls.append("HTTP")
        raise AssertionError("wrong venue contacted")
    with pytest.raises(KrakenFeedRefused, match="NOT_ARMED"):
        kraken_poll(state_dir=tmp_path, legacy_source=LEGACY,
                    transport=forbidden, metadata_transport=forbidden)
    with pytest.raises(BrooksMarketFeedRefused, match="NOT_ARMED"):
        binance_poll(state_dir=tmp_path, legacy_source=LEGACY,
                     symbol="BTCUSDT", transport=forbidden)
    assert calls == []


def test_catalog_only_worker_never_substitutes_kraken(tmp_path):
    with EngineControlStore(tmp_path) as host:
        arm(host)
        set_pref(host, "futures_exchange", "toobit")
    calls = []
    worker = BrooksPaperService(
        state_dir=tmp_path, legacy_source=LEGACY,
        reader=lambda **kw: calls.append(kw), clock=lambda: 1791658000.0)
    worker.start()
    try:
        step = worker.step()
        assert step["phase"] == "IDLE" and not step["attempted"]
        assert step["reason"] == "BROOKS_SELECTED_EXCHANGE_FEED_NOT_READY"
        assert calls == []
    finally:
        worker.shutdown()


@pytest.mark.parametrize("frame", ("30m", "12h"))
def test_real_frozen_v5_honors_new_selected_period(frame, tmp_path):
    rows, now = candles(frame)
    with EngineControlStore(tmp_path) as host:
        arm(host)
        set_pref(host, "timeframe", frame)
    options = dict(
        state_dir=tmp_path, legacy_source=LEGACY, symbol="PF_XBTUSD",
        bars=72, now=now, transport=transport(frame, rows),
        metadata_transport=instruments)
    first = kraken_poll(**options)
    second = kraken_poll(**options)
    assert first["timeframe"] == frame
    assert first["selected_exchange"] == "kraken"
    assert first["decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert second["outcome"] == "DUPLICATE_SCAN"
    with EngineControlStore(tmp_path) as host:
        assert host.brooks_replay_status()["scans"] == 1
        assert not host.publication(BROOKS_ENGINE_ID)["effective_publication"]
