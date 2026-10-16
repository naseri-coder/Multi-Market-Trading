"""MMT-FIX-03: offline research reliability and lint coverage."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from research_layer import run_research


def _candle(*, high: str = "101") -> dict:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "open_time": start.isoformat(),
        "close_time": (start + timedelta(minutes=15)).isoformat(),
        "open": "100", "high": high, "low": "99", "close": "100",
        "volume": "10",
    }


def test_valid_offline_market_extract_uses_canonical_candle(tmp_path: Path) -> None:
    path = tmp_path / "market.json"
    path.write_text(json.dumps({"series": [{
        "exchange": "offline", "market_type": "spot", "symbol": "BTCUSDT",
        "timeframe": "15m", "candles": [_candle()],
    }]}))
    market = run_research.load_market_extract(path)
    candle = market[("offline", "spot", "BTCUSDT", "15m")][0]
    assert candle.close == Decimal("100")
    assert candle.volume == Decimal("10")


def test_market_extract_rejects_invalid_candle_geometry(tmp_path: Path) -> None:
    path = tmp_path / "invalid-market.json"
    path.write_text(json.dumps({"series": [{
        "exchange": "offline", "market_type": "spot", "symbol": "BTCUSDT",
        "timeframe": "15m", "candles": [_candle(high="98")],
    }]}))
    with pytest.raises(ValueError, match="high|range"):
        run_research.load_market_extract(path)


class _EmptyResult:
    description = (("sample",),)

    def fetchone(self):
        return None

    def __iter__(self):
        return iter(())


class _NoTradeDatabase:
    def execute(self, _query: str):
        return _EmptyResult()


def test_report_market_counts_are_measured_not_assumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_research, "OUT", tmp_path)
    run_research.generate_report(
        _NoTradeDatabase(), [], {"signals": []}, 0, 0, [],
        market_series_count=2, raw_market_candles=7,
    )
    report = (tmp_path / "FINAL_RESEARCH_REPORT.md").read_text()
    assert "Raw market candles supplied: **7**" in report
    assert "**2** observed market series" in report
    assert "Production PostgreSQL was accessed" not in report
    assert "two days" not in report
    assert "BTC/ETH on 15m/1h" not in report
    assert "does not access Production PostgreSQL" in report
    assert "BTC/ETH/SOL, Spot/Futures and six timeframes" not in report


def test_report_does_not_invent_market_series_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_research, "OUT", tmp_path)
    run_research.generate_report(
        _NoTradeDatabase(), [], {"signals": []}, 0, 0, [],
        market_series_count=0, raw_market_candles=0,
    )
    report = (tmp_path / "FINAL_RESEARCH_REPORT.md").read_text()
    assert "Raw market candles supplied: **0**" in report
    assert "**0** observed market series" in report


def test_lint_scopes_include_platform_and_research() -> None:
    from scripts.ci_ruff_no_new_debt import LINT_SCOPES

    assert {"naseri_markets", "research_layer"}.issubset(LINT_SCOPES)
    assert {"production_source", "production_checks", "scripts"}.issubset(
        LINT_SCOPES
    )


def test_ruff_identifies_new_debt_in_both_new_scopes(tmp_path: Path) -> None:
    from scripts.ci_ruff_no_new_debt import _ruff_findings

    for scope in ("naseri_markets", "research_layer"):
        source_dir = tmp_path / scope
        source_dir.mkdir()
        (source_dir / "unresolved.py").write_text("result = missing_symbol\n")
    config = Path(__file__).resolve().parents[2] / "pyproject.toml"
    rows = _ruff_findings(tmp_path, config)
    flagged = {Path(row["filename"]).parts[-2] for row in rows if row.get("code") == "F821"}
    assert flagged == {"naseri_markets", "research_layer"}
