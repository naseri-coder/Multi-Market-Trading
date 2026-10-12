"""Manual Stage-21B CLI works from operator-held bytes; never uses a network."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.captured_paper_cli_stage21b_v1 import (
    _private_data, main,
)
from naseri_markets.captured_paper_pilot_stage21b_v1 import CapturedPaperRefused

T0 = datetime(2026, 10, 12, 10, tzinfo=UTC)


def prepare(tmp_path):
    private = tmp_path / "captures"
    private.mkdir(mode=0o700)
    metadata = {
        "code": "200000",
        "data": [
            {"symbol": symbol, "type": "FFWCSX",
             "quoteCurrency": "USDT", "status": "Open",
             "tickSize": "0.01", "expireDate": None}
            for symbol in ("XBTUSDTM", "ETHUSDTM")
        ],
    }
    meta = private / "metadata.json"
    meta.write_bytes(json.dumps(metadata).encode())
    meta.chmod(0o600)
    args = [
        "--state-dir", str(private / "result"),
        "--metadata-json", str(meta),
        "--metadata-asof", T0.isoformat(),
        "--capture-observed-at", (T0 + timedelta(hours=2)).isoformat(),
    ]
    for prefix, symbol, period in (
        ("first", "XBTUSDTM", 15), ("second", "ETHUSDTM", 5)
    ):
        interval = timedelta(minutes=period)
        bars = [
            [100, 102, 98, 100, 10, 1000],
            [100, 108, 99, 106, 10, 1000],
            [107, 108, 104, 107, 10, 1000],
            [107, 114, 104, 113, 10, 1000],
        ]
        rows = [
            [int((T0 + i * interval).timestamp() * 1000), *bar]
            for i, bar in enumerate(bars)
        ]
        raw_path = private / (prefix + ".json")
        raw_path.write_bytes(json.dumps({"code": "200000", "data": rows}).encode())
        raw_path.chmod(0o600)
        args.extend([
            "--" + prefix + "-symbol", symbol,
            "--" + prefix + "-timeframe", "15m" if period == 15 else "5m",
            "--" + prefix + "-start", T0.isoformat(),
            "--" + prefix + "-end", (T0+4*interval).isoformat(),
            "--" + prefix + "-json", str(raw_path),
        ])
    return args, private


def test_explicit_operator_cli_two_offline_sources(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    args, folder = prepare(tmp_path)
    assert main(args) == 2
    assert not (folder / "result").exists()
    assert "STAGE21B_CAPTURED_PAPER_REFUSED" in capsys.readouterr().err
    assert main(args + ["--ack-offline-captured-paper"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["completed_jobs"] == 2
    assert report["exact_effects"] == 6
    assert report["integrity_verdict"] == "PASS"
    assert report["real_network_used"] is False
    assert report["broker_order_sent"] is False
    assert report["provider_origin_independently_attested"] is False


def test_private_capture_symlink_refused(tmp_path):
    _args, folder = prepare(tmp_path)
    bad = folder / "alias"
    bad.symlink_to(folder / "first.json")
    with pytest.raises(CapturedPaperRefused, match="OWNER_PRIVATE_CAPTURE_REQUIRED"):
        _private_data(bad, limit=65536)
