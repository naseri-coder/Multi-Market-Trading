"""Exchange-native, immutable public futures instrument metadata and policy split."""
from __future__ import annotations

import json

import pytest

from naseri_markets import public_futures_contracts as contracts
from naseri_markets import brooks_kraken_feed as kraken
from naseri_markets import brooks_market_feed as binance
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.trusted_custom import LocalCustomRefused


def kraken_blob():
    return json.dumps({
        "result": "success",
        "instruments": [
            {"symbol": "pf_xbtusd", "type": "futures_vanilla",
             "tradeable": True, "tickSize": 0.5},
            {"symbol": "pf_ethusd", "type": "futures_vanilla",
             "tradeable": False, "tickSize": "0.05"},
            {"symbol": "pi_xbtusd", "type": "futures_vanilla",
             "tradeable": True, "tickSize": 0.1},
            {"symbol": "fi_xbtusd", "type": "futures_vanilla",
             "tradeable": True, "tickSize": 0.1},
        ],
    }).encode()


def kucoin_blob():
    return json.dumps({
        "code": "200000",
        "data": [
            {"symbol": "XBTUSDTM", "type": "FFWCSX", "status": "Open",
             "quoteCurrency": "USDT", "expireDate": None,
             "tickSize": "0.1"},
            {"symbol": "ETHUSDTM", "type": "FFWCSX", "status": "Halt",
             "quoteCurrency": "USDT", "expireDate": None,
             "tickSize": "0.01"},
            {"symbol": "XBTZ26", "type": "FFICSX", "status": "Open",
             "quoteCurrency": "USD", "expireDate": 1798420000000,
             "tickSize": "0.1"},
        ],
    }).encode()


def test_real_exchange_native_contract_symbols_are_not_catalog_guesses():
    k = contracts.discover_public_contracts(
        "kraken", transport=lambda venue: kraken_blob())
    assert k["mode"] == "PUBLIC_FUTURES_METADATA_RESEARCH_ONLY"
    assert k["contract_count"] == 2
    assert [x["symbol"] for x in k["contracts"]] == [
        "PF_ETHUSD", "PF_XBTUSD"]
    assert k["contracts"][0]["tick_size"] == "0.05"
    assert k["contracts"][0]["exchange_tradeable"] is False
    assert k["contracts"][0]["quote_currency"] == "USD"
    assert not k["iran_resident_futures_approved"]
    assert not k["account_trading_authorized"]
    assert not k["paper_signal_generation_authorized"]
    assert not k["telegram_publication_authorized"]
    assert not k["market_orders_authorized"]
    q = contracts.discover_public_contracts(
        "kucoin", transport=lambda venue: kucoin_blob())
    assert [x["symbol"] for x in q["contracts"]] == ["ETHUSDTM", "XBTUSDTM"]
    assert q["contracts"][1]["quote_currency"] == "USDT"
    assert q["contracts"][1]["contract_kind"] == "PERPETUAL"
    assert q["contracts"][1]["exchange_tradeable"] is True
    assert q["policy"] == "ELIGIBILITY_UNVERIFIED"
    assert not q["iran_resident_futures_approved"]
    limited = contracts.discover_public_contracts(
        "kucoin", max_results=1, transport=lambda venue: kucoin_blob())
    assert limited["contract_count"] == 2
    assert limited["truncated"] is True
    assert len(limited["contracts"]) == 1


@pytest.mark.parametrize("venue,body", [
    ("kraken", b"{}"),
    ("kraken", b'{"result":"success","instruments":[]}'),
    ("kraken", b'{"result":"success","instruments":[{"symbol":"PF_XBTUSD","type":"futures_vanilla","tradeable":true,"tickSize":0.0}]}'),
    ("kraken", b'{"result":"success","instruments":[{"symbol":"PF_XBTUSD","type":"futures_vanilla","tradeable":true,"tickSize":-1}]}'),
    ("kraken", b'{"result":"success","instruments":[{"symbol":"PF_XBTUSD","type":"futures_vanilla","tradeable":true,"tickSize":NaN}]}'),
    ("kraken", b'{"result":"success","instruments":[{"symbol":"PF_XBTUSD","symbol":"PF_ETHUSD","type":"futures_vanilla","tradeable":true,"tickSize":"0.1"}]}'),
    ("kraken", b'{"result":"success","instruments":[{"symbol":"PF_XBTUSD","type":"futures_vanilla","tradeable":true,"tickSize":"0.1"},{"symbol":"pf_xbtusd","type":"futures_vanilla","tradeable":true,"tickSize":"0.1"}]}'),
    ("kucoin", b'{"code":"200001","data":[]}'),
    ("kucoin", b'{"code":"200000","data":[{"symbol":"../BTC","type":"FFWCSX","status":"Open","quoteCurrency":"USDT","tickSize":0.1}]}'),
    ("kucoin", b'{"code":"200000","data":[{"symbol":"BTCUSDTM","type":"FFWCSX","status":"Open","quoteCurrency":"USDT","tickSize":"Infinity"}]}'),
])
def test_metadata_fail_closed_invalid_exchange_response(venue, body):
    with pytest.raises(contracts.PublicContractsRefused):
        contracts.parse_public_contracts(venue, body)


def test_no_unlisted_domain_or_url_is_ever_networked():
    visited = []
    def forbidden(venue):
        visited.append(venue)
        return kraken_blob()
    with pytest.raises(contracts.PublicContractsRefused):
        contracts.discover_public_contracts("https://attacker.test", transport=forbidden)
    with pytest.raises(contracts.PublicContractsRefused):
        contracts.discover_public_contracts("binance", transport=forbidden)
    assert visited == []
    with pytest.raises(contracts.PublicContractsRefused):
        contracts.discover_public_contracts("kucoin", max_results=10000)


def test_mutations_require_resident_eligibility_even_outside_telegram(tmp_path):
    with EngineControlStore(tmp_path / "private") as store:
        old = store.preferences(BROOKS_ENGINE_ID)
        assert old["futures_exchange"] == "kraken"
        for field, value in (
                ("futures_exchange", "kucoin"),
                ("futures_exchange", "binance"),
                ("futures_exchange", "kraken"),
                ("futures_symbol", "PF_ETHUSD")):
            with pytest.raises(
                    LocalCustomRefused, match="ENGINE_IRAN_FUTURES_ELIGIBILITY_DENIED"):
                store.change_preference(
                    BROOKS_ENGINE_ID, field=field, value=value,
                    expected_revision=old["revision"], actor_id=123)
        assert store.preferences(BROOKS_ENGINE_ID) == old
        assert store.admin_history(BROOKS_ENGINE_ID) == []
        # Timeframe is still configurable; no implicit activation.
        updated = store.change_preference(
            BROOKS_ENGINE_ID, field="timeframe", value="4h",
            expected_revision=old["revision"], actor_id=123)
        assert updated["timeframe"] == "4h"


def test_direct_kraken_paper_call_rejected_before_any_network(tmp_path):
    from pathlib import Path
    folder = tmp_path / "state"
    with EngineControlStore(folder) as store:
        core = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=core.revision, actor_id=123)
        prefs = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=123)
    touched = []
    def forbidden(*_args, **_kwargs):
        touched.append(1)
        raise AssertionError("must not be called")
    with pytest.raises(kraken.KrakenFeedRefused, match="NOT_ARMED"):
        kraken.poll_once(
            state_dir=folder, legacy_source=Path("irrelevant"),
            transport=forbidden, metadata_transport=forbidden)
    assert not touched
    with EngineControlStore(folder) as store:
        assert store.brooks_replay_status()["scans"] == 0


def test_direct_binance_paper_call_rejected_before_any_network(tmp_path):
    from pathlib import Path
    folder = tmp_path / "state"
    with EngineControlStore(folder) as store:
        core = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=core.revision, actor_id=123)
        prefs = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=123)
        # Historical persisted venue is still readable after policy tightening.
        store._db.execute(
            "UPDATE managed_engine_preferences SET futures_exchange='binance', "
            "futures_symbol='BTCUSDT' WHERE engine_id=?", (BROOKS_ENGINE_ID,))
    touched = []
    def forbidden(*_args, **_kwargs):
        touched.append(1)
        raise AssertionError("must not be called")
    with pytest.raises(binance.BrooksMarketFeedRefused, match="NOT_ARMED"):
        binance.poll_once(
            state_dir=folder, legacy_source=Path("irrelevant"),
            symbol="BTCUSDT", transport=forbidden)
    assert not touched
    with EngineControlStore(folder) as store:
        assert store.brooks_replay_status()["scans"] == 0


def test_cli_research_requires_opt_in_but_never_opens_trade(tmp_path, monkeypatch,
                                                            capsys):
    from naseri_markets import dev_operator
    folder = tmp_path / "state"
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    assert dev_operator.main([
        "--state-dir", str(folder), "init", "--ack-nonproduction-init"]) == 0
    called = []
    def stub(venue, max_results=100):
        called.append((venue, max_results))
        return contracts.discover_public_contracts(
            venue, max_results=max_results,
            transport=lambda x: kucoin_blob())
    monkeypatch.setattr(contracts, "discover_public_contracts", stub)
    # Stub would recurse if invoked; denial test ensures it never invokes it.
    assert dev_operator.main([
        "--state-dir", str(folder), "contracts", "--venue", "kucoin"]) == 2
    assert not called
    monkeypatch.setattr(contracts, "discover_public_contracts",
                        lambda venue, max_results=100: {
                            "venue": venue, "mode": "PUBLIC_FUTURES_METADATA_RESEARCH_ONLY",
                            "iran_resident_futures_approved": False,
                            "paper_signal_generation_authorized": False,
                            "contracts": [],
                        })
    assert dev_operator.main([
        "--state-dir", str(folder), "contracts", "--venue", "kucoin",
        "--ack-public-metadata-research"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])[
        "iran_resident_futures_approved"] is False
    with EngineControlStore(folder) as store:
        assert store.brooks_replay_status()["scans"] == 0
