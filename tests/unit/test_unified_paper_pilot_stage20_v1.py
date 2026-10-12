"""Stage 20 operator-driven, two-binding integrated PAPER test corpus."""
from __future__ import annotations

import json

import pytest

from naseri_markets.unified_paper_pilot_stage20_v1 import main, run_paper_pilot


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def test_two_distinct_bindings_complete_closed_trades_and_audit(tmp_path):
    path = tmp_path / "first"
    report = run_paper_pilot(
        path, first_symbol="BTCUSD", second_symbol="ETHUSD",
        first_timeframe="5m", second_timeframe="1h")
    assert report["mode"] == "STAGE20_SYNTHETIC_PAPER_ONLY"
    assert report["core"] == "example.dual.setup"
    assert report["completed_jobs"] == report["closed_paper_trades"] == 2
    assert report["dry_run_commands"] == 2
    assert report["exact_effects"] == 6
    assert report["restart_verified"]
    assert report["integrity_verdict"] == "PASS"
    assert report["release_verdict"] == "BLOCKED_NONPRODUCTION_UNATTESTED"
    assert {b["symbol"] for b in report["bindings"]} == {"BTCUSD", "ETHUSD"}
    assert {b["timeframe"] for b in report["bindings"]} == {"5m", "1h"}
    assert len({b["binding_id"] for b in report["bindings"]}) == 2
    assert len({b["order_id"] for b in report["bindings"]}) == 2
    assert {b["status"] for b in report["bindings"]} == {"CLOSED"}
    for flag in ("telegram_sent", "broker_order_sent", "real_feed_used",
                 "live_trading_enabled", "profitability_proven",
                 "public_release_authorized", "brooks_core_api_integrated"):
        assert report[flag] is False
    with pytest.raises(ValueError, match="NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED"):
        run_paper_pilot(path)


def test_paper_remains_on_when_no_send_intent_off(tmp_path):
    report = run_paper_pilot(tmp_path / "without_signals", dry_run_signals=False)
    assert report["closed_paper_trades"] == 2
    assert report["dry_run_commands"] == 0
    assert report["exact_effects"] == 4
    assert report["integrity_verdict"] == "PASS"


def test_production_and_invalid_specs_refused_without_writes(tmp_path, monkeypatch):
    path = tmp_path / "must_not_exist"
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(ValueError, match="NONPRODUCTION_REQUIRED"):
        run_paper_pilot(path)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="NONPRODUCTION_REQUIRED"):
        run_paper_pilot(path)
    monkeypatch.delenv("MMT_PRODUCTION")
    for kwargs in (
        {"first_symbol": "BTC/USDT"},
        {"second_symbol": "ABCUSD"},
        {"second_timeframe": "7m"},
    ):
        with pytest.raises(ValueError, match="TWO_DISTINCT_SYNTHETIC_BINDINGS_REQUIRED"):
            run_paper_pilot(path, **kwargs)
    assert not path.exists()
    actual = tmp_path / "actual"
    actual.mkdir()
    symlink = tmp_path / "alias"
    symlink.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED"):
        run_paper_pilot(symlink)


def test_operator_explicit_cli_ack(tmp_path, capsys):
    path = tmp_path / "cli"
    assert main(["--state-dir", str(path)]) == 2
    assert not path.exists()
    assert "STAGE20_PILOT_REFUSED" in capsys.readouterr().err
    assert main(["--state-dir", str(path), "--ack-synthetic-offline"]) == 0
    assert json.loads(capsys.readouterr().out)["completed_jobs"] == 2
