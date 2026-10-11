"""Stage 6 provider catalog & broker DEMO read-only acceptance tests."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from naseri_markets.contracts import Market
from naseri_markets.instrument_registry_v1 import (
    CatalogRefused, InstrumentMetadata, ListingStatus, MetadataOrigin,
    ProviderSnapshot, ResearchInstrumentCatalog,
)
from naseri_markets.read_only_provider_adapters_v1 import (
    discover_public_futures, futures_snapshot, mt5_demo_observation,
)

NOW = datetime(2026, 10, 11, 20, tzinfo=UTC)
RAW = (
    b'{"code":"200000","data":[{"symbol":"XBTUSDTM","type":"FFWCSX",'
    b'"quoteCurrency":"USDT","status":"Open","tickSize":"0.1",'
    b'"expireDate":null}]}'
)


def metadata(provider="kraken_futures", symbol="PF_XBTUSD", when=NOW):
    return InstrumentMetadata(
        provider, Market.CRYPTO, symbol, "UTC", "USD", D("0.5"),
        MetadataOrigin.PUBLIC_CONTRACT_RESEARCH, ListingStatus.OPEN,
        when, "USD_PERPETUAL",
    )


def snapshot(symbols=("PF_XBTUSD",), when=NOW, provider="kraken_futures"):
    return ProviderSnapshot(
        provider, MetadataOrigin.PUBLIC_CONTRACT_RESEARCH, when,
        tuple(metadata(provider, symbol, when) for symbol in symbols), "a" * 64,
    )


def test_catalog_revisions_freshness_and_negative_trading_grant():
    catalog = ResearchInstrumentCatalog(max_age_seconds=30)
    first = catalog.replace(snapshot())
    assert first.revision == 1 and not first.idempotent
    assert catalog.replace(snapshot()).idempotent
    record = catalog.lookup("kraken_futures", "PF_XBTUSD", now=NOW)
    assert record.instrument.market is Market.CRYPTO
    assert record.trading_authorized is False
    assert record.paper_signal_authorized is False
    with pytest.raises(CatalogRefused, match="NEVER_TRADING"):
        catalog.refuse_trading_binding(record)
    with pytest.raises(CatalogRefused, match="STALE"):
        catalog.lookup("kraken_futures", "PF_XBTUSD", now=NOW + timedelta(seconds=31))
    with pytest.raises(CatalogRefused, match="FUTURE"):
        catalog.lookup("kraken_futures", "PF_XBTUSD", now=NOW - timedelta(seconds=1))


def test_provider_snapshots_atomic_updates_and_no_cross_provider_leak():
    catalog = ResearchInstrumentCatalog()
    catalog.replace(snapshot(symbols=("PF_XBTUSD", "PF_ETHUSD")))
    catalog.replace(snapshot(provider="kucoin_futures", symbols=("XBTUSDTM",)))
    with pytest.raises(CatalogRefused, match="CONFLICTING"):
        catalog.replace(snapshot(symbols=("PF_OTHER",)))
    with pytest.raises(CatalogRefused, match="ROLLBACK"):
        catalog.replace(snapshot(when=NOW - timedelta(seconds=1)))
    assert catalog.lookup("kucoin_futures", "XBTUSDTM", now=NOW).provider == "kucoin_futures"
    receipt = catalog.replace(snapshot(("PF_ETHUSD",), NOW + timedelta(seconds=1)))
    assert receipt.revision == 2
    with pytest.raises(CatalogRefused, match="UNKNOWN_PROVIDER_OR_SYMBOL"):
        catalog.lookup("kraken_futures", "PF_XBTUSD", now=NOW + timedelta(seconds=1))


def test_duplicate_and_invalid_tick_refuse_before_commit():
    with pytest.raises(CatalogRefused, match="MIXED_OR_DUPLICATE"):
        ProviderSnapshot(
            "kraken_futures", MetadataOrigin.PUBLIC_CONTRACT_RESEARCH, NOW,
            (metadata(), metadata()), "c" * 64,
        )
    for bad in (D("NaN"), D("0"), D("-1"), D("Infinity")):
        with pytest.raises(CatalogRefused, match="PRICE_TICK"):
            InstrumentMetadata(
                "kraken_futures", Market.CRYPTO, "PF_XBTUSD", "UTC", "USD",
                bad, MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
                ListingStatus.OPEN, NOW, "USD_PERPETUAL",
            )


def test_public_research_is_off_by_default_no_network(monkeypatch):
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    with pytest.raises(CatalogRefused, match="NONPRODUCTION"):
        discover_public_futures("kucoin", observed_at=NOW,
                                transport=lambda _: (_ for _ in ()).throw(AssertionError()))


def test_existing_real_kucoin_parser_used_for_offline_bytes():
    data = futures_snapshot("kucoin", RAW, observed_at=NOW)
    assert data.provider == "kucoin_futures"
    assert data.instruments[0].symbol == "XBTUSDTM"
    assert data.instruments[0].contract_multiplier is None
    assert data.instruments[0].quantity_step is None
    assert data.instruments[0].trading_authorized is False
    assert data.raw_sha256 == hashlib.sha256(RAW).hexdigest()


def test_public_research_requires_both_explicit_gates(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(CatalogRefused, match="NONPRODUCTION"):
        discover_public_futures("kucoin", observed_at=NOW)
    calls = []
    result = discover_public_futures(
        "kucoin", observed_at=NOW, acknowledge_research=True,
        transport=lambda venue: (calls.append(venue) or RAW),
    )
    assert calls == ["kucoin"] and result.provider == "kucoin_futures"
    with pytest.raises(CatalogRefused, match="UNSUPPORTED"):
        discover_public_futures("https://unknown.invalid/", observed_at=NOW,
                                acknowledge_research=True)


class DemoSDK:
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self):
        self.calls = []
        self.mode = 0
        self.connected = True
        self.stamp = int(NOW.timestamp() * 1000)
        self.bid = 1.085
        self.ask = 1.086
        self.symbol = "EURUSD.a"

    def account_info(self):
        self.calls.append("account_info")
        return SimpleNamespace(trade_mode=self.mode)

    def terminal_info(self):
        self.calls.append("terminal_info")
        return SimpleNamespace(connected=self.connected)

    def symbol_info(self, symbol):
        self.calls.append("symbol_info")
        return SimpleNamespace(
            name=self.symbol, currency_base="EUR", currency_profit="USD",
            trade_tick_size=0.00001, volume_step=0.01,
            trade_contract_size=100000, visible=True,
        )

    def symbol_info_tick(self, symbol):
        self.calls.append("symbol_info_tick")
        return SimpleNamespace(time_msc=self.stamp, bid=self.bid, ask=self.ask)

    def order_send(self, *_args, **_kwargs):
        raise AssertionError("FORBIDDEN_ORDER_SEND")


def test_mt5_demo_only_four_read_methods_and_no_order(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    sdk = DemoSDK()
    report = mt5_demo_observation(sdk, broker="demo_broker", symbol="EURUSD.a",
                                  now=NOW, operator_ack=True)
    assert report.metadata.market is Market.FOREX
    assert report.metadata.quantity_step == D("0.01")
    assert report.metadata.contract_multiplier == D("100000")
    assert not report.authorized_to_trade and not report.verified_live_feed
    assert sdk.calls == ["account_info", "terminal_info", "symbol_info", "symbol_info_tick"]


@pytest.mark.parametrize("bad", ["live", "disconnect", "stale", "future", "crossed"])
def test_mt5_fail_closed_on_prohibited_account_or_quote(monkeypatch, bad):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    sdk = DemoSDK()
    if bad == "live":
        sdk.mode = 2
    if bad == "disconnect":
        sdk.connected = False
    if bad == "stale":
        sdk.stamp -= 30000
    if bad == "future":
        sdk.stamp += 3000
    if bad == "crossed":
        sdk.ask = 1.08
    with pytest.raises(CatalogRefused):
        mt5_demo_observation(sdk, broker="demo_broker", symbol="EURUSD.a",
                             now=NOW, operator_ack=True)
    assert "order_send" not in sdk.calls


def test_live_or_unapproved_environment_never_calls_mt5(monkeypatch):
    sdk = DemoSDK()
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    with pytest.raises(CatalogRefused, match="NONPRODUCTION"):
        mt5_demo_observation(sdk, broker="demo_broker", symbol="EURUSD.a",
                             now=NOW, operator_ack=True)
    assert sdk.calls == []
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(CatalogRefused, match="NONPRODUCTION"):
        mt5_demo_observation(sdk, broker="demo_broker", symbol="EURUSD.a",
                             now=NOW, operator_ack=True)
    assert sdk.calls == []
