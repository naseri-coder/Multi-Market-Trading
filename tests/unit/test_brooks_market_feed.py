"""Offline transport-fixture tests of automatic market PAPER ingestion.

All HTTP is replaced by exact Binance-format bytes. One test executes the
real SHA-pinned V5 engine in its child process; no real network or Telegram.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets import brooks_market_feed
from naseri_markets.brooks_market_feed import (
    BrooksMarketFeedRefused, closed_candle_payload, poll_loop, poll_once,
)
from naseri_markets.brooks_replay import parse_candle_replay
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore

LEGACY = Path(__file__).resolve().parents[2] / "production_source"
START = datetime(2026, 1, 1, tzinfo=UTC)
CLOCK = START + timedelta(minutes=15 * 72 + 5)


def klines(count=73, start=START):
    rows = []
    for index in range(count):
        opened = int((start + timedelta(minutes=15 * index)).timestamp() * 1000)
        rows.append([
            opened, "100", "101", "99", "100", "10",
            opened + 900000 - 1, "1000", 10, "5", "500", "0",
        ])
    return rows


def mock_transport(rows):
    raw = json.dumps(rows).encode()
    def transport(symbol, timeframe, limit, timeout):
        assert (symbol, timeframe, limit) == ("BTCUSDT", "15m", 73)
        assert timeout <= 15
        return raw
    return transport


@pytest.fixture
def state(tmp_path):
    private = tmp_path / "dev-only"
    with EngineControlStore(private) as store:
        engine = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=engine.revision, actor_id=123)
        preferences = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment",
            value="PAPER", expected_revision=preferences["revision"],
            actor_id=123)
    return private


def test_binance_finalization_and_crypto_replay_window():
    payload, latest = closed_candle_payload(
        symbol="BTCUSDT", timeframe="15m", bars=72, now=CLOCK,
        transport=mock_transport(klines()))
    raw, instrument, bars = parse_candle_replay(payload)
    assert len(bars) == 72
    assert latest == START + timedelta(hours=18)
    assert bars[-1]["close_time"] == latest
    assert raw["provider"] == "binance_usdm_public"
    assert raw["market_type"] == "futures"
    assert instrument.symbol == "BTCUSDT"
    assert all(bar["close_time"] <= CLOCK - timedelta(seconds=2) for bar in bars)


@pytest.mark.parametrize("bad", ["lowercase", "wrong_tf", "few_bars", "bad_clock"])
def test_explicit_input_allowlists_fail_closed(bad):
    params = {"symbol": "BTCUSDT", "timeframe": "15m", "bars": 72,
              "now": CLOCK, "transport": mock_transport(klines())}
    if bad == "lowercase":
        params["symbol"] = "btcusdt"
    elif bad == "wrong_tf":
        params["timeframe"] = "2m"
    elif bad == "few_bars":
        params["bars"] = 20
    else:
        params["now"] = datetime(2026, 1, 1)
    with pytest.raises(BrooksMarketFeedRefused):
        closed_candle_payload(**params)


def test_malformed_bad_close_and_gap_never_reach_engine():
    original = klines()
    for modify in (
        lambda r: r[7].__setitem__(6, r[7][6] - 1),
        lambda r: r[8].__setitem__(4, "102"),
        lambda r: r[8].__setitem__(0, r[7][0]),
        lambda r: r[8].__setitem__(1, "NaN"),
        lambda r: r[8].__setitem__(0, r[8][0] + 60000),
    ):
        rows = [list(row) for row in original]
        modify(rows)
        with pytest.raises(BrooksMarketFeedRefused):
            closed_candle_payload(
                symbol="BTCUSDT", timeframe="15m", bars=72, now=CLOCK,
                transport=mock_transport(rows))


def test_insufficient_stale_and_nonfinite_feed_fail_closed():
    with pytest.raises(BrooksMarketFeedRefused, match="INSUFFICIENT"):
        closed_candle_payload(
            symbol="BTCUSDT", timeframe="15m", bars=72, now=CLOCK,
            transport=lambda *args: json.dumps(klines(60)).encode())
    with pytest.raises(BrooksMarketFeedRefused, match="STALE"):
        closed_candle_payload(
            symbol="BTCUSDT", timeframe="15m", bars=72,
            now=CLOCK + timedelta(hours=2),
            transport=mock_transport(klines()))
    with pytest.raises(BrooksMarketFeedRefused, match="JSON"):
        closed_candle_payload(
            symbol="BTCUSDT", timeframe="15m", bars=72, now=CLOCK,
            transport=lambda *args: b'{"code":-1003,"msg":"rate limit"}')


def test_actual_frozen_brooks_on_market_closed_candles_and_idempotency(state):
    result = poll_once(
        state_dir=state, legacy_source=LEGACY, symbol="BTCUSDT", bars=72,
        now=CLOCK, transport=mock_transport(klines()))
    assert result["mode"] == "AUTOMATIC_MARKET_CLOSED_CANDLE_PAPER"
    assert result["market_feed"] == "BINANCE_USDM_PUBLIC_HTTPS"
    assert result["decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert result["outcome"] in ("NO_SIGNAL", "RECORDED")
    assert result["telegram_sent"] is False
    assert result["live_publication_enabled"] is False
    duplicate = poll_once(
        state_dir=state, legacy_source=LEGACY, symbol="BTCUSDT", bars=72,
        now=CLOCK, transport=mock_transport(klines()))
    assert duplicate["outcome"] == "DUPLICATE_SCAN"
    with EngineControlStore(state) as store:
        assert store.brooks_replay_status()["scans"] == 1
        assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        assert store.publication(BROOKS_ENGINE_ID)["effective_publication"] is False


def test_disabled_permission_checks_before_network_and_no_paper_write(tmp_path):
    calls = []
    def unexpected(*args):
        calls.append(args)
        return b"[]"
    with pytest.raises(BrooksMarketFeedRefused, match="NOT_ARMED"):
        poll_once(state_dir=tmp_path / "disabled", legacy_source=LEGACY,
                  symbol="BTCUSDT", bars=72, transport=unexpected)
    assert calls == []
    with EngineControlStore(tmp_path / "disabled") as store:
        assert store.brooks_replay_status()["scans"] == 0


def test_disable_during_fetch_refused_before_engine(state):
    def revoke(*args):
        with EngineControlStore(state) as store:
            engine = store.get(BROOKS_ENGINE_ID)
            store.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=False,
                expected_revision=engine.revision, actor_id=123)
        return json.dumps(klines()).encode()
    with pytest.raises(BrooksMarketFeedRefused, match="SETTINGS_CHANGED"):
        poll_once(state_dir=state, legacy_source=LEGACY, symbol="BTCUSDT",
                  bars=72, now=CLOCK, transport=revoke)
    with EngineControlStore(state) as store:
        assert store.brooks_replay_status()["scans"] == 0


def test_polling_is_opt_in_bounded_and_stops_on_failure():
    attempts = []
    slept = []
    emitted = []
    def fake_runner(**kwargs):
        attempts.append(kwargs["symbol"])
        return {"outcome": "NO_SIGNAL"}
    total = poll_loop(
        state_dir="/unused", legacy_source="/unused", symbol="BTCUSDT",
        interval_seconds=30, max_cycles=3, sleep=slept.append,
        emit=emitted.append, runner=fake_runner)
    assert total == 3
    assert attempts == ["BTCUSDT"] * 3
    assert slept == [30, 30]
    assert len(emitted) == 3
    with pytest.raises(BrooksMarketFeedRefused, match="POLL_LIMITS"):
        poll_loop(state_dir="/unused", legacy_source="/unused",
                  symbol="BTCUSDT", interval_seconds=1, max_cycles=1)
    def error(**kwargs):
        raise BrooksMarketFeedRefused("BROOKS_FEED_STALE_OR_FUTURE_CANDLE")
    with pytest.raises(BrooksMarketFeedRefused):
        poll_loop(state_dir="/unused", legacy_source="/unused",
                  symbol="BTCUSDT", max_cycles=3, runner=error,
                  sleep=lambda _: pytest.fail("must not retry a failed cycle"))


def test_cli_requires_explicit_development_ack_and_never_starts_implicitly():
    assert brooks_market_feed.main([
        "--once", "--state-dir", "/unused", "--legacy-source", "/unused",
        "--symbol", "BTCUSDT",
    ]) == 2
