"""Installed synthetic full JOURNEY tests; no mock risk/order internals."""
from __future__ import annotations

import pytest

from naseri_markets.panel_paper_synthetic_demo_v1 import (
    main, run_synthetic_demo,
)


def test_nonproduction_gate_precedes_any_write(tmp_path, monkeypatch):
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    destination = tmp_path / "must_not_exist"
    with pytest.raises(ValueError, match="NONPRODUCTION_ENV_REQUIRED"):
        run_synthetic_demo(destination)
    assert not destination.exists()


@pytest.mark.parametrize("period", ("5m", "15m", "1h"))
def test_full_paper_close_restart_and_signal_separation(tmp_path, monkeypatch, period):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    destination = tmp_path / ("demo-" + period)
    result = run_synthetic_demo(
        destination, symbol="XYZUSD", timeframe=period)
    assert result["mode"] == "SYNTHETIC_INSTALLED_PAPER_ONLY"
    assert result["timeframe"] == period and result["symbol"] == "XYZUSD"
    assert result["decision_count"] == result["paper_closed_trades"] == 1
    assert result["dry_run_commands"] == 1 and result["restart_verified"]
    assert result["integrity_verdict"] == "PASS"
    assert result["release_verdict"] == "BLOCKED_NONPRODUCTION_UNATTESTED"
    assert not result["telegram_sent"] and not result["broker_order_sent"]
    assert not result["live_trading_enabled"] and not result["profitability_proven"]
    assert (destination / "paper.sqlite").is_file()
    with pytest.raises(ValueError, match="FRESH_PRIVATE_STATE_REQUIRED"):
        run_synthetic_demo(destination, timeframe=period)


def test_bad_input_and_symlink_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(ValueError, match="SYMBOL_OR_TIMEFRAME_INVALID"):
        run_synthetic_demo(tmp_path / "bad", symbol="BTC/USDT")
    assert not (tmp_path / "bad").exists()
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="FRESH_PRIVATE_STATE_REQUIRED"):
        run_synthetic_demo(alias)


def test_cli_requires_explicit_ack(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    path = tmp_path / "not_created"
    assert main(["--state-dir", str(path)]) == 2
    assert "STAGE16_SYNTHETIC_REFUSED" in capsys.readouterr().err
    assert not path.exists()
