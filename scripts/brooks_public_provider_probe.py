"""Nonproduction public OHLCV provider reachability probe; read-only, no credentials.

The probe is NOT a market provider, signal engine, publisher or geo bypass.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

TARGETS = {
    "kraken_futures_linear_btcusd": (
        "https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/15m?count=73",
        "kraken",
    ),
    "kraken_futures_inverse_btcusd": (
        "https://futures.kraken.com/api/charts/v1/trade/PI_XBTUSD/15m?count=73",
        "kraken",
    ),
    "binance_spot_public_btcusdt": (
        "https://data-api.binance.vision/api/v3/klines?"
        "symbol=BTCUSDT&interval=15m&limit=73",
        "binance_spot",
    ),
}


def probe(name: str, url: str, kind: str) -> dict:
    class RefuseRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("redirect denied")

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), RefuseRedirect())
    try:
        request = urllib.request.Request(url, headers={
            "Accept": "application/json", "User-Agent": "brooks-paper-probe/0.1"})
        with opener.open(request, timeout=10) as response:
            if response.status != 200 or response.geturl() != url:
                raise ValueError("unexpected status or URL")
            data = response.read(256 * 1024 + 1)
            if not 0 < len(data) <= 256 * 1024:
                raise ValueError("response limit")
            blob = json.loads(data)
            rows = blob.get("candles") if kind == "kraken" else blob
            if not isinstance(rows, list) or not len(rows) >= 60:
                raise ValueError("insufficient rows")
            last = rows[-1]["time"] if kind == "kraken" else rows[-1][0]
            if not isinstance(last, int):
                raise ValueError("missing timestamp")
            # Time should be within recent 30 minutes; candle finality is
            # checked separately by the production-adjacent PAPER adapter.
            lag = datetime.now(UTC).timestamp() - last / 1000
            if lag < 0 or lag > 1800:
                raise ValueError("stale or future candle")
            return {"provider": name, "verdict": "REACHABLE",
                    "bars": len(rows), "last_bar_open_ms": last,
                    "market_type": "futures" if kind == "kraken" else "spot"}
    except urllib.error.HTTPError as exc:
        return {"provider": name, "verdict": "BLOCKED",
                "reason": f"HTTP_{exc.code}"}
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return {"provider": name, "verdict": "BLOCKED",
                "reason": type(exc).__name__}


if __name__ == "__main__":
    results = [probe(k, *v) for k, v in TARGETS.items()]
    for row in results:
        print("BROOKS_PUBLIC_PROBE=" + json.dumps(row, sort_keys=True))
    # Probing spot alone never qualifies as a proven futures market source.
    futures_ok = any(r["verdict"] == "REACHABLE"
                     and r.get("market_type") == "futures" for r in results)
    print("BROOKS_FUTURES_PROBE_VERDICT=" + (
        "REACHABLE" if futures_ok else "BLOCKED_NO_PUBLIC_FUTURES"))
    raise SystemExit(0 if futures_ok else 3)
