"""Opt-in nonproduction Binance USD-M closed-candle PAPER polling for real Brooks V5.

Never opens a broker, trades, publishes to Telegram or starts a bot poller.
The frozen legacy engine is only called through brooks_replay.replay_once.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from .brooks_replay import (
    MAX_BARS, MAX_REPLAY_BYTES, MIN_BARS, SECONDS,
    BrooksReplayRefused, parse_candle_replay, replay_once,
)
from .engine_control_store import BROOKS_ENGINE_ID, EngineControlStore

_SYMBOL = re.compile(r"[A-Z0-9]{2,16}USDT\Z")
_ENDPOINT = "https://fapi.binance.com/fapi/v1/klines"
_MAX_REPLY = 524288
_FEED_NAME = "BINANCE_USDM_PUBLIC_HTTPS"
_MIN_FINALITY_LAG = timedelta(seconds=2)


class BrooksMarketFeedRefused(BrooksReplayRefused):
    """Fail closed on unavailable, malformed, unfinalized or stale market data."""


def _download_klines(symbol: str, timeframe: str, limit: int, timeout: int) -> bytes:
    query = urllib.parse.urlencode({
        "symbol": symbol, "interval": timeframe, "limit": str(limit),
    })
    url = _ENDPOINT + "?" + query
    request = urllib.request.Request(
        url, headers={"Accept": "application/json",
                      "User-Agent": "multi-market-trading-paper/0.4"})
    # HTTPS certificate verification is provided by the standard urllib TLS stack.
    # Disable environment-configured proxies and refuse cross-host redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise BrooksMarketFeedRefused("BROOKS_FEED_REDIRECT_DENIED")

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if (response.status != 200 or response.geturl() != url or
                    not response.headers.get("Content-Type", "").lower().startswith(
                        "application/json")):
                raise BrooksMarketFeedRefused("BROOKS_FEED_UNEXPECTED_RESPONSE")
            data = response.read(_MAX_REPLY + 1)
    except BrooksMarketFeedRefused:
        raise
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise BrooksMarketFeedRefused("BROOKS_FEED_NETWORK_UNAVAILABLE") from exc
    if not 0 < len(data) <= _MAX_REPLY:
        raise BrooksMarketFeedRefused("BROOKS_FEED_RESPONSE_BOUNDS")
    return data


def closed_candle_payload(*, symbol: str, timeframe: str, bars: int = 128,
                          now: datetime | None = None,
                          transport: Callable[[str, str, int, int], bytes] | None = None,
                          timeout: int = 8) -> tuple[bytes, datetime]:
    """Normalize Binance USD-M klines into a validated canonical V5 input window.

    Binance's close time is inclusive (end - 1 ms); Brooks' close time is
    exclusive (next candle open). Never pass the forming candle to V5.
    """
    if (type(symbol) is not str or not _SYMBOL.fullmatch(symbol)
            or type(timeframe) is not str or timeframe not in SECONDS
            or type(bars) is not int or not MIN_BARS <= bars <= MAX_BARS
            or type(timeout) is not int or not 1 <= timeout <= 15):
        raise BrooksMarketFeedRefused("BROOKS_FEED_ALLOWLIST_REQUIRED")
    clock = datetime.now(UTC) if now is None else now
    if (not isinstance(clock, datetime) or clock.tzinfo is None
            or clock.utcoffset() is None):
        raise BrooksMarketFeedRefused("BROOKS_FEED_AWARE_CLOCK_REQUIRED")
    clock = clock.astimezone(UTC)
    step_ms = SECONDS[timeframe] * 1000
    if transport is None:
        transport = _download_klines
    try:
        data = transport(symbol, timeframe, bars + 1, timeout)
    except BrooksMarketFeedRefused:
        raise
    except Exception as exc:
        raise BrooksMarketFeedRefused("BROOKS_FEED_TRANSPORT_FAILED") from exc
    if type(data) is not bytes or not 0 < len(data) <= _MAX_REPLY:
        raise BrooksMarketFeedRefused("BROOKS_FEED_RESPONSE_BOUNDS")
    try:
        response = json.loads(
            data, parse_constant=lambda _:
            (_ for _ in ()).throw(ValueError("nonfinite")))
    except (UnicodeError, ValueError) as exc:
        raise BrooksMarketFeedRefused("BROOKS_FEED_JSON_INVALID") from exc
    if type(response) is not list or len(response) > bars + 1:
        raise BrooksMarketFeedRefused("BROOKS_FEED_KLINES_SCHEMA")
    complete = []
    previous_open = None
    for row in response:
        if type(row) is not list or len(row) != 12:
            raise BrooksMarketFeedRefused("BROOKS_FEED_KLINES_SCHEMA")
        opened, inclusive_close = row[0], row[6]
        if (type(opened) is not int or type(inclusive_close) is not int
                or opened < 0 or opened % step_ms != 0
                or inclusive_close != opened + step_ms - 1):
            raise BrooksMarketFeedRefused("BROOKS_FEED_CANDLE_CLOCK_INVALID")
        if previous_open is not None and opened <= previous_open:
            raise BrooksMarketFeedRefused("BROOKS_FEED_CANDLE_ORDER_INVALID")
        previous_open = opened
        final_time = datetime.fromtimestamp(
            (opened + step_ms) / 1000, tz=UTC)
        if final_time > clock - _MIN_FINALITY_LAG:
            continue  # current not-yet-final candle, never evaluated
        prices = row[1:6]
        if any(type(x) is not str or len(x) > 48 for x in prices):
            raise BrooksMarketFeedRefused("BROOKS_FEED_DECIMAL_STRING_REQUIRED")
        opened_at = datetime.fromtimestamp(opened / 1000, tz=UTC)
        complete.append({
            "open_time": opened_at.isoformat(),
            "close_time": final_time.isoformat(),
            "open": prices[0], "high": prices[1], "low": prices[2],
            "close": prices[3], "volume": prices[4],
        })
    if len(complete) < bars:
        raise BrooksMarketFeedRefused("BROOKS_FEED_INSUFFICIENT_CLOSED_CANDLES")
    selected = complete[-bars:]
    latest = datetime.fromisoformat(selected[-1]["close_time"])
    if not timedelta(0) <= clock - latest <= timedelta(
            seconds=SECONDS[timeframe] + 30):
        raise BrooksMarketFeedRefused("BROOKS_FEED_STALE_OR_FUTURE_CANDLE")
    payload = json.dumps({
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_usdm_public", "symbol": symbol, "timezone": "UTC",
        "quote_currency": "USDT", "exchange": "binance",
        "market_type": "futures", "timeframe": timeframe, "candles": selected,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_REPLAY_BYTES:
        raise BrooksMarketFeedRefused("BROOKS_FEED_REPLAY_BOUNDS")
    # Reuse the genuine strict contiguous OHLCV validator before any engine call.
    try:
        parse_candle_replay(payload)
    except BrooksReplayRefused as exc:
        raise BrooksMarketFeedRefused("BROOKS_FEED_REPLAY_VALIDATION_FAILED") from exc
    return payload, latest


def poll_once(*, state_dir: str | Path, legacy_source: str | Path,
              symbol: str, bars: int = 128, now: datetime | None = None,
              transport: Callable[[str, str, int, int], bytes] | None = None) -> dict:
    """Check operator PAPER permission, fetch closed bars, execute real Brooks.

    Repeat safety checks inside replay_once before and after the child worker.
    """
    with EngineControlStore(state_dir) as store:
        engine = store.get(BROOKS_ENGINE_ID)
        preferences = store.preferences(BROOKS_ENGINE_ID)
        if (engine is None or not engine.requested_enabled
                or preferences["signal_environment"] != "PAPER"
                or preferences["market_scope"] not in ("all", "crypto")):
            raise BrooksMarketFeedRefused("BROOKS_FEED_PAPER_NOT_ARMED")
        engine_revision = engine.revision
        preferences_revision = preferences["revision"]
        timeframe = preferences["timeframe"]
    payload, latest = closed_candle_payload(
        symbol=symbol, timeframe=timeframe, bars=bars, now=now,
        transport=transport)
    with EngineControlStore(state_dir) as store:
        engine = store.get(BROOKS_ENGINE_ID)
        prefs = store.preferences(BROOKS_ENGINE_ID)
        if (engine is None or engine.revision != engine_revision
                or prefs["revision"] != preferences_revision
                or not engine.requested_enabled
                or prefs["signal_environment"] != "PAPER"
                or prefs["timeframe"] != timeframe):
            raise BrooksMarketFeedRefused("BROOKS_FEED_SETTINGS_CHANGED")
    report = replay_once(
        state_dir=state_dir, legacy_source=legacy_source, replay_json=payload)
    return {
        **report,
        "mode": "AUTOMATIC_MARKET_CLOSED_CANDLE_PAPER",
        "market_feed": _FEED_NAME,
        "symbol": symbol,
        "timeframe": timeframe,
        "last_closed_candle": latest.isoformat(),
        "telegram_sent": False,
        "live_publication_enabled": False,
    }


def poll_loop(*, state_dir: str | Path, legacy_source: str | Path,
              symbol: str, bars: int = 128, interval_seconds: int = 60,
              max_cycles: int = 0, sleep: Callable[[float], None] = time.sleep,
              emit: Callable[[dict], None] | None = None,
              runner: Callable[..., dict] = poll_once) -> int:
    """Only starts when invoked explicitly; halt on first failed safety check.

    max_cycles=0 is an explicit operator-requested continuous polling session.
    On any transport or engine error exit nonzero instead of spinning.
    """
    if (type(interval_seconds) is not int or not 30 <= interval_seconds <= 3600
            or type(max_cycles) is not int or max_cycles < 0):
        raise BrooksMarketFeedRefused("BROOKS_FEED_POLL_LIMITS_INVALID")
    cycle = 0
    while max_cycles == 0 or cycle < max_cycles:
        result = runner(
            state_dir=state_dir, legacy_source=legacy_source,
            symbol=symbol, bars=bars)
        if emit is not None:
            emit(result)
        cycle += 1
        if max_cycles == 0 or cycle < max_cycles:
            sleep(interval_seconds)
    return cycle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    schedule = parser.add_mutually_exclusive_group(required=True)
    schedule.add_argument("--once", action="store_true")
    schedule.add_argument("--loop", action="store_true")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
    parser.add_argument("--bars", type=int, default=128)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--ack-nonproduction-paper", action="store_true",
                        help="explicitly acknowledge PAPER only, no channel sends")
    args = parser.parse_args(argv)
    if not args.ack_nonproduction_paper:
        print("BROOKS_FEED_REFUSED:EXPLICIT_NONPRODUCTION_ACK_REQUIRED",
              file=sys.stderr)
        return 2
    try:
        def output(report: dict) -> None:
            print(json.dumps(report, sort_keys=True), flush=True)

        if args.once:
            output(poll_once(
                state_dir=args.state_dir, legacy_source=args.legacy_source,
                symbol=args.symbol, bars=args.bars))
        else:
            poll_loop(
                state_dir=args.state_dir, legacy_source=args.legacy_source,
                symbol=args.symbol, bars=args.bars,
                interval_seconds=args.poll_seconds,
                max_cycles=args.max_cycles, emit=output)
    except (BrooksReplayRefused, OSError, ValueError):
        print("BROOKS_FEED_REFUSED:FAIL_CLOSED", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
