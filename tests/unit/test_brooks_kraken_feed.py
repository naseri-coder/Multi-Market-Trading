"""Independent documented Kraken BTC/USD perpetual OHLCV validation."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError

import pytest

from naseri_markets import brooks_kraken_feed as kraken
from naseri_markets.brooks_replay import parse_candle_replay
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore

SOURCE = Path(__file__).resolve().parents[2] / "production_source"
START = datetime(2026, 1, 1, tzinfo=UTC)
CLOCK = START + timedelta(minutes=72 * 15 + 5)


def candles(*, count=73, start=START):
    return [{
        "time": int((start + timedelta(minutes=15 * i)).timestamp() * 1000),
        "open": "100", "high": "101", "low": "99", "close": "100",
        "volume": "10.0",
    } for i in range(count)]


def metadata(*, tick=0.5, tradeable=True, contract_type="futures_vanilla"):
    return json.dumps({
        "result": "success",
        "instruments": [{
            "symbol": "pf_xbtusd", "tickSize": tick,
            "tradeable": tradeable, "type": contract_type,
        }],
    }).encode()


def mock_metadata():
    return metadata()


def transport(rows, **extra):
    blob = json.dumps({"candles": rows, "more_candles": False, **extra}).encode()
    def get(symbol, timeframe, count, timeout):
        assert (symbol, timeframe, count) == ("PF_XBTUSD", "15m", 73)
        return blob
    return get


@pytest.fixture
def state(tmp_path):
    folder = tmp_path / "disposable-only"
    with EngineControlStore(folder) as store:
        core = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=core.revision, actor_id=123)
        prefs = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=123)
    return folder


def test_crypto_futures_provenance_finalization_not_binance():
    payload, latest = kraken.closed_kraken_candles(
        symbol="PF_XBTUSD", timeframe="15m", now=CLOCK,
        transport=transport(candles()))
    raw, instrument, bars = parse_candle_replay(payload)
    assert len(bars) == 72
    assert bars[-1]["close_time"] == latest
    assert raw["provider"] == "kraken_futures_trade_public"
    assert raw["exchange"] == "kraken_futures"
    assert raw["market_type"] == "futures"
    assert raw["symbol"] == "PF_XBTUSD"
    assert raw["quote_currency"] == "USD"
    assert instrument.symbol == "PF_XBTUSD"
    assert latest == START + timedelta(hours=18)
    assert all(bar["close_time"] < CLOCK for bar in bars)


@pytest.mark.parametrize("symbol,frame,bars", [
    ("BTCUSDT", "15m", 72), ("PI_XBTUSD", "15m", 72),
    ("PF_XBTUSD", "2m", 72), ("PF_XBTUSD", "15m", 4),
])
def test_market_identity_allowlist(symbol, frame, bars):
    with pytest.raises(kraken.KrakenFeedRefused, match="ALLOWLIST"):
        kraken.closed_kraken_candles(
            symbol=symbol, timeframe=frame, bars=bars, now=CLOCK,
            transport=transport(candles()))


def test_malformed_candles_always_fail_closed():
    invalid = (
        lambda r: r[4].__setitem__("low", "105"),
        lambda r: r[7].__setitem__("time", r[7]["time"] + 60000),
        lambda r: r[11].__setitem__("open", "NaN"),
        lambda r: r[9].__setitem__("time", r[8]["time"]),
        lambda r: r[0].__setitem__("volume", float("inf")),
        lambda r: r[6].__setitem__("open", 100),
    )
    for change in invalid:
        rows = candles()
        change(rows)
        with pytest.raises(kraken.KrakenFeedRefused):
            kraken.closed_kraken_candles(
                symbol="PF_XBTUSD", timeframe="15m", now=CLOCK,
                transport=transport(rows))


def test_stale_short_unclosed_interior_and_response_bounds():
    with pytest.raises(kraken.KrakenFeedRefused, match="INSUFFICIENT"):
        kraken.closed_kraken_candles(
            symbol="PF_XBTUSD", timeframe="15m", now=CLOCK,
            transport=transport(candles(count=60)))
    with pytest.raises(kraken.KrakenFeedRefused, match="STALE"):
        kraken.closed_kraken_candles(
            symbol="PF_XBTUSD", timeframe="15m",
            now=CLOCK + timedelta(hours=3), transport=transport(candles()))
    rows = candles()
    rows[1]["time"] = int((CLOCK + timedelta(hours=1)).timestamp() * 1000)
    with pytest.raises(kraken.KrakenFeedRefused):
        kraken.closed_kraken_candles(
            symbol="PF_XBTUSD", timeframe="15m", now=CLOCK,
            transport=transport(rows))
    with pytest.raises(kraken.KrakenFeedRefused, match="RESPONSE_BOUNDS"):
        kraken.closed_kraken_candles(
            symbol="PF_XBTUSD", timeframe="15m", now=CLOCK,
            transport=lambda *args: b"x" * (524288 + 1))


def test_operator_disabled_before_network(tmp_path):
    reached = []
    def forbidden(*args):
        reached.append(args)
        raise AssertionError("network reached while disabled")
    with pytest.raises(kraken.KrakenFeedRefused, match="NOT_ARMED"):
        kraken.poll_once(
            state_dir=tmp_path / "disarmed", legacy_source=SOURCE,
            transport=forbidden)
    assert not reached


def test_revoked_during_fetch_before_engine(state):
    def revoke(*args):
        with EngineControlStore(state) as store:
            current = store.get(BROOKS_ENGINE_ID)
            store.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=False,
                expected_revision=current.revision, actor_id=123)
        return json.dumps({
            "candles": candles(), "more_candles": False,
        }).encode()
    with pytest.raises(kraken.KrakenFeedRefused, match="SETTINGS_CHANGED"):
        kraken.poll_once(
            state_dir=state, legacy_source=SOURCE, now=CLOCK,
            transport=revoke, metadata_transport=mock_metadata)
    with EngineControlStore(state) as store:
        assert store.brooks_replay_status()["scans"] == 0


def test_real_frozen_brooks_worker_and_duplicate_journal(state):
    first = kraken.poll_once(
        state_dir=state, legacy_source=SOURCE, now=CLOCK,
        transport=transport(candles()), metadata_transport=mock_metadata)
    again = kraken.poll_once(
        state_dir=state, legacy_source=SOURCE, now=CLOCK,
        transport=transport(candles()), metadata_transport=mock_metadata)
    assert first["decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert first["mode"] == "KRAKEN_FUTURES_CLOSED_TRADE_PAPER"
    assert first["market_feed"] == "KRAKEN_FUTURES_TRADE_PUBLIC_HTTPS"
    assert first["telegram_sent"] is False
    assert first["live_publication_enabled"] is False
    assert first["exchange_price_tick"] == "0.5"
    assert again["scan_id"] == first["scan_id"]
    assert again["outcome"] == "DUPLICATE_SCAN"
    with EngineControlStore(state) as store:
        assert store.brooks_replay_status()["scans"] == 1
        assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        assert store.publication(BROOKS_ENGINE_ID)["effective_publication"] is False


def test_http_451_refused_with_no_raw_error_body(monkeypatch):
    class Refused:
        def open(self, req, timeout):
            raise HTTPError(req.full_url, 451, "secret response", None, None)
    monkeypatch.setattr(
        kraken.urllib.request, "build_opener", lambda *args: Refused())
    with pytest.raises(kraken.KrakenFeedRefused, match="KRAKEN_FEED_HTTP_451") as err:
        kraken._download("PF_XBTUSD", "15m", 73, 10)
    assert "secret" not in str(err.value)



def test_frozen_brooks_only_accepts_verified_kraken_tick_and_identity():
    assert kraken.verified_kraken_tick(transport=mock_metadata) == "0.5"
    for payload in (
        metadata(tick=-1),
        metadata(tick=101),
        metadata(tick="NaN"),
        metadata(tradeable=False),
        metadata(contract_type="spot"),
        b'{"result":"error","instruments":[]}',
    ):
        with pytest.raises(kraken.KrakenFeedRefused):
            kraken.verified_kraken_tick(transport=lambda payload=payload: payload)


def test_no_implicit_poll_or_publication(tmp_path):
    assert kraken.main([
        "--once", "--state-dir", str(tmp_path),
        "--legacy-source", str(SOURCE),
    ]) == 2
    assert kraken.main([
        "--cycles", "0", "--state-dir", str(tmp_path),
        "--legacy-source", str(SOURCE), "--ack-nonproduction-paper",
    ]) == 2
