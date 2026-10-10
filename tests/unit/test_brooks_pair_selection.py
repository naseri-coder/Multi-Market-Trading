"""Real selected Kraken futures contracts; catalog venues are fail-closed."""
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from naseri_markets.brooks_kraken_feed import (
    KrakenFeedRefused, poll_once, verified_kraken_tick,
)
from naseri_markets.brooks_paper_service import BrooksPaperService
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.futures_pairs import (
    KRAKEN_PAIRS, CATALOG_CANDIDATES, pair_choices, require_pair,
)
from naseri_markets.trusted_custom import LocalCustomRefused

SOURCE = Path(__file__).resolve().parents[2] / "production_source"
CLOCK = datetime(2026, 1, 1, 18, 5, tzinfo=UTC)
START = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def change(host, name, value):
    prefs = host.preferences(BROOKS_ENGINE_ID)
    return host.change_preference(
        BROOKS_ENGINE_ID, field=name, value=value,
        expected_revision=prefs["revision"], actor_id=123)


def enable(host):
    engine = host.get(BROOKS_ENGINE_ID)
    host.toggle_as_admin(
        BROOKS_ENGINE_ID, enabled=True,
        expected_revision=engine.revision, actor_id=123)
    change(host, "signal_environment", "PAPER")


def pair_metadata(symbol):
    return json.dumps({
        "result": "success", "instruments": [
            {"symbol": symbol.lower(), "tickSize": "0.01",
             "tradeable": True, "type": "futures_vanilla"},
        ],
    }).encode()


def pair_rows():
    return [
        {"time": int((START + timedelta(minutes=i * 15)).timestamp() * 1000),
         "open": "100", "high": "101", "low": "99",
         "close": "100", "volume": 10}
        for i in range(73)]


def pair_candles(symbol):
    def call(actual, timeframe, limit, timeout):
        assert (actual, timeframe, limit) == (symbol, "15m", 73)
        return json.dumps({"candles": pair_rows(), "more_candles": False}).encode()
    return call


def test_selection_table_lists_three_documented_kraken_contracts():
    assert KRAKEN_PAIRS == ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD")
    assert pair_choices("kraken") == KRAKEN_PAIRS
    assert pair_choices("toobit") == CATALOG_CANDIDATES
    assert all(x.endswith("USDT") for x in CATALOG_CANDIDATES)
    for wrong in ("BTCUSDT", "PF_ETHUSD;DROP", "PF_UNKNOWN", ""):
        with pytest.raises(ValueError, match="IDENTITY"):
            require_pair("kraken", wrong)


def test_saving_exchange_resets_pair_atomically_and_old_click_cannot_mutate(tmp_path):
    with EngineControlStore(tmp_path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_symbol"] == "PF_XBTUSD"
        picked = change(host, "futures_symbol", "PF_ETHUSD")
        assert picked["futures_symbol"] == "PF_ETHUSD"
        selected = change(host, "futures_exchange", "toobit")
        assert selected["futures_exchange"] == "toobit"
        assert selected["futures_symbol"] == "BTCUSDT"
        with pytest.raises(LocalCustomRefused, match="ALLOWLIST"):
            change(host, "futures_symbol", "PF_ETHUSD")
        selected = change(host, "futures_symbol", "XRPUSDT")
        assert selected["futures_symbol"] == "XRPUSDT"
        selected = change(host, "futures_exchange", "kraken")
        assert selected["futures_symbol"] == "PF_XBTUSD"
    with EngineControlStore(tmp_path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_symbol"] == "PF_XBTUSD"


def test_pre_pair_database_migration_respects_selected_exchange(tmp_path):
    path = tmp_path / "old"
    path.mkdir(mode=0o700)
    db = path / "custom_paper.db"
    with sqlite3.connect(db) as con:
        con.execute("""CREATE TABLE managed_engine_preferences(
            engine_id TEXT PRIMARY KEY, timeframe TEXT NOT NULL DEFAULT '15m',
            market_scope TEXT NOT NULL DEFAULT 'all',
            futures_exchange TEXT NOT NULL DEFAULT 'kraken',
            signal_environment TEXT NOT NULL DEFAULT 'OFF',
            revision INTEGER NOT NULL DEFAULT 1)""")
        con.execute("INSERT INTO managed_engine_preferences VALUES(?,?,?,?,?,?)",
                    (BROOKS_ENGINE_ID, "4h", "crypto", "binance", "PAPER", 17))
    db.chmod(0o600)
    with EngineControlStore(path) as host:
        prefs = host.preferences(BROOKS_ENGINE_ID)
        assert (prefs["futures_exchange"], prefs["futures_symbol"]) == (
            "binance", "BTCUSDT")
        assert prefs["timeframe"] == "4h"
        assert prefs["revision"] == 17


@pytest.mark.parametrize("symbol", KRAKEN_PAIRS)
def test_actual_frozen_brooks_per_pair_close_and_replay_idempotent(symbol, tmp_path):
    with EngineControlStore(tmp_path) as host:
        enable(host)
        change(host, "futures_symbol", symbol)
    kwargs = dict(state_dir=tmp_path, legacy_source=SOURCE, symbol=symbol,
                  now=CLOCK, transport=pair_candles(symbol),
                  metadata_transport=lambda: pair_metadata(symbol))
    first = poll_once(**kwargs)
    again = poll_once(**kwargs)
    assert first["symbol"] == symbol
    assert first["quote_currency"] == "USD"
    assert first["exchange_price_tick"] == "0.01"
    assert first["decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert again["outcome"] == "DUPLICATE_SCAN"
    with EngineControlStore(tmp_path) as host:
        assert host.brooks_replay_status()["scans"] == 1
        assert host.publication(BROOKS_ENGINE_ID)["effective_publication"] is False


def test_wider_symbol_rejected_before_any_metadata_network(tmp_path):
    with EngineControlStore(tmp_path) as host:
        enable(host)
        change(host, "futures_symbol", "PF_ETHUSD")
    called = []
    def forbidden(*args):
        called.append(1)
        raise AssertionError("wrong pair used")
    with pytest.raises(KrakenFeedRefused, match="NOT_ARMED"):
        poll_once(state_dir=tmp_path, legacy_source=SOURCE,
                  symbol="PF_XBTUSD", metadata_transport=forbidden,
                  transport=forbidden)
    assert called == []


def test_mid_fetch_pair_change_fails_closed_before_worker_or_journal(tmp_path):
    with EngineControlStore(tmp_path) as host:
        enable(host)
        change(host, "futures_symbol", "PF_ETHUSD")
    def swapped():
        with EngineControlStore(tmp_path) as host:
            change(host, "futures_symbol", "PF_SOLUSD")
        return pair_metadata("PF_ETHUSD")
    with pytest.raises(KrakenFeedRefused, match="SETTINGS_CHANGED"):
        poll_once(state_dir=tmp_path, legacy_source=SOURCE,
                  symbol="PF_ETHUSD", now=CLOCK, metadata_transport=swapped,
                  transport=pair_candles("PF_ETHUSD"))
    with EngineControlStore(tmp_path) as host:
        assert host.brooks_replay_status()["scans"] == 0


def test_worker_passes_selected_pair_not_hardcoded_btc(tmp_path):
    with EngineControlStore(tmp_path) as host:
        enable(host)
        change(host, "futures_symbol", "PF_SOLUSD")
    now = [CLOCK.timestamp()]
    seen = []
    def reader(**kwargs):
        seen.append(kwargs["symbol"])
        return {
            "symbol": kwargs["symbol"], "selected_exchange": "kraken",
            "market_feed": "KRAKEN_FUTURES_TRADE_PUBLIC_HTTPS",
            "outcome": "NO_SIGNAL", "decision": "NO_SIGNAL",
            "telegram_sent": False, "live_publication_enabled": False,
            "timeframe": "15m", "last_closed_candle":
                (datetime.fromtimestamp(now[0], tz=UTC) - timedelta(minutes=5)).isoformat(),
        }
    worker = BrooksPaperService(
        state_dir=tmp_path, legacy_source=SOURCE,
        reader=reader, clock=lambda: now[0])
    worker.start()
    try:
        result = worker.step()
        assert result["attempted"]
        assert seen == ["PF_SOLUSD"]
    finally:
        worker.shutdown()


@pytest.mark.asyncio
async def test_private_telegram_pair_choices_and_callback_revision(tmp_path):
    pytest.importorskip("telegram")
    from naseri_markets.custom_admin_panel import _token
    from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
    folder = tmp_path / "private"
    panel = IntegratedEnginePanel(state_dir=folder, admin_ids={123}, owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    with EngineControlStore(folder) as host:
        keyboard = panel.pair_keyboard(host, BROOKS_ENGINE_ID)
        choices = [b.callback_data for row in keyboard.inline_keyboard for b in row
                   if b.callback_data.startswith("ep:set:")]
        assert len(choices) == 3
        assert max(map(len, choices)) <= 64
        assert "ep:list:" + token in [
            b.callback_data for row in panel.settings_keyboard(
                host, BROOKS_ENGINE_ID).inline_keyboard for b in row]
    def req(data, user):
        msg = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(data=data, message=msg, answer=AsyncMock())
        update = SimpleNamespace(
            callback_query=query, effective_user=SimpleNamespace(id=user),
            effective_chat=SimpleNamespace(type="private", id=user))
        return update, msg
    wrong, msg = req(f"ep:set:{token}:1:1", 999)
    await panel.callback(wrong, SimpleNamespace())
    msg.reply_text.assert_not_awaited()
    update, msg = req(f"ep:set:{token}:1:1", 123)
    await panel.callback(update, SimpleNamespace())
    with EngineControlStore(folder) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_symbol"] == "PF_ETHUSD"
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 2
    await panel.callback(update, SimpleNamespace())
    with EngineControlStore(folder) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 2
