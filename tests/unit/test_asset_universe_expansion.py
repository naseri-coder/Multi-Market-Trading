"""Dedicated contract tests for the authorized Binance Futures universe expansion."""

from decimal import Decimal

from app.core.config import Settings
from app.modules.brooks_core.books_policy import BrooksBooksPolicy

EXPECTED_SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT",
    "TRXUSDT", "ZECUSDT", "HYPEUSDT", "DOGEUSDT", "XMRUSDT",
    "LINKUSDT", "ADAUSDT", "XLMUSDT", "UNIUSDT", "NEARUSDT",
    "BCHUSDT", "AVAXUSDT", "LTCUSDT", "CCUSDT", "GRAMUSDT",
    "HBARUSDT", "SUIUSDT", "MUSDT", "1000SHIBUSDT", "TAOUSDT",
)

EXPECTED_NEW_TICKS = {
    "TRXUSDT": "0.00001",
    "ZECUSDT": "0.01",
    "HYPEUSDT": "0.00100",
    "DOGEUSDT": "0.000010",
    "XMRUSDT": "0.01",
    "LINKUSDT": "0.001",
    "ADAUSDT": "0.00010",
    "XLMUSDT": "0.00001",
    "UNIUSDT": "0.0010",
    "NEARUSDT": "0.0010",
    "BCHUSDT": "0.01",
    "AVAXUSDT": "0.0010",
    "LTCUSDT": "0.01",
    "CCUSDT": "0.0000100",
    "GRAMUSDT": "0.001000",
    "HBARUSDT": "0.00001",
    "SUIUSDT": "0.000100",
    "MUSDT": "0.0001000",
    "1000SHIBUSDT": "0.000001",
    "TAOUSDT": "0.01",
}


def test_canonical_env_loads_exact_ordered_unique_universe():
    settings = Settings(
        database_url="postgresql+asyncpg://synthetic:synthetic@localhost/synthetic",
        telegram_runtime_enabled=False,
        brooks_symbols=",".join(EXPECTED_SYMBOLS),
        _env_file=None,
    )
    assert settings.brooks_symbols == EXPECTED_SYMBOLS
    assert len(settings.brooks_symbols) == len(set(settings.brooks_symbols)) == 25
    assert settings.brooks_symbols[-1] == "TAOUSDT"


def test_existing_five_are_preserved_and_leo_is_excluded():
    assert EXPECTED_SYMBOLS[:5] == (
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT",
    )
    assert "LEOUSDT" not in EXPECTED_SYMBOLS
    assert "1000LEOUSDT" not in EXPECTED_SYMBOLS


def test_exchange_specific_symbol_contracts_are_preserved():
    assert "1000SHIBUSDT" in EXPECTED_SYMBOLS
    assert "SHIBUSDT" not in EXPECTED_SYMBOLS
    assert "MUSDT" in EXPECTED_SYMBOLS


def test_all_configured_symbols_have_unique_positive_tick_metadata():
    policy = BrooksBooksPolicy()
    configured = dict(policy.futures_tick_sizes)
    assert len(configured) == len(policy.futures_tick_sizes)
    assert set(configured) == set(EXPECTED_SYMBOLS)
    assert all(value > 0 for value in configured.values())


def test_new_tick_metadata_is_exact_and_lookup_normalizes_symbols():
    policy = BrooksBooksPolicy()
    for symbol, expected in EXPECTED_NEW_TICKS.items():
        assert policy.tick_size_for_symbol(symbol) == Decimal(expected)
        assert policy.tick_size_for_symbol(f"  {symbol.lower()}  ") == Decimal(expected)
