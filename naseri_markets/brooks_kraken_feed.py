"""Explicit, public Kraken Futures TRADE candles -> real Brooks V5 PAPER only.

This is an INDEPENDENT, nonproduction BTC/USD futures provider. Do not
substitute Kraken's USD futures for Binance's USDT futures or use this as a
hidden fallback. No trades, bots, channels, crons, production or secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from .brooks_replay import (
    MAX_BARS, MAX_REPLAY_BYTES, MIN_BARS, SECONDS,
    BrooksReplayRefused, parse_candle_replay, replay_once,
)
from .engine_control_store import BROOKS_ENGINE_ID, EngineControlStore

_SYMBOL = "PF_XBTUSD"  # verified Kraken USD linear perpetual, NOT BTCUSDT
_ENDPOINT = "https://futures.kraken.com/api/charts/v1/trade"
_FEED = "KRAKEN_FUTURES_TRADE_PUBLIC_HTTPS"
_INSTRUMENT_ENDPOINT = "https://futures.kraken.com/derivatives/api/v3/instruments"
_MAX_REPLY = 524288
_FINALITY_LAG = timedelta(seconds=2)


class KrakenFeedRefused(BrooksReplayRefused):
    """Fail closed before engine evaluation or persistence."""


def _download(symbol: str, timeframe: str, limit: int, timeout: int) -> bytes:
    url = f"{_ENDPOINT}/{symbol}/{timeframe}?count={limit}"
    class RefuseRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise KrakenFeedRefused("KRAKEN_FEED_REDIRECT_DENIED")

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), RefuseRedirect())
    request = urllib.request.Request(
        url, headers={"Accept": "application/json",
                      "User-Agent": "brooks-nonprod-futures-paper/0.1"})
    try:
        with opener.open(request, timeout=timeout) as response:
            if (response.status != 200 or response.geturl() != url or
                    not response.headers.get(
                        "Content-Type", "").lower().startswith("application/json")):
                raise KrakenFeedRefused("KRAKEN_FEED_UNEXPECTED_RESPONSE")
            raw = response.read(_MAX_REPLY + 1)
    except KrakenFeedRefused:
        raise
    except urllib.error.HTTPError as exc:
        raise KrakenFeedRefused(f"KRAKEN_FEED_HTTP_{exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise KrakenFeedRefused("KRAKEN_FEED_NETWORK_UNAVAILABLE") from exc
    if not 0 < len(raw) <= _MAX_REPLY:
        raise KrakenFeedRefused("KRAKEN_FEED_RESPONSE_BOUNDS")
    return raw



def _download_instruments() -> bytes:
    """Read only independent Kraken Futures instrument metadata over TLS."""
    url = _INSTRUMENT_ENDPOINT
    class RefuseRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise KrakenFeedRefused("KRAKEN_TICK_REDIRECT_DENIED")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), RefuseRedirect())
    request = urllib.request.Request(
        url, headers={"Accept": "application/json",
                      "User-Agent": "brooks-nonprod-futures-paper/0.1"})
    try:
        with opener.open(request, timeout=10) as response:
            if (response.status != 200 or response.geturl() != url or
                    not response.headers.get(
                        "Content-Type", "").lower().startswith("application/json")):
                raise KrakenFeedRefused("KRAKEN_TICK_UNEXPECTED_RESPONSE")
            raw = response.read(2 * 1024 * 1024 + 1)
    except KrakenFeedRefused:
        raise
    except urllib.error.HTTPError as exc:
        raise KrakenFeedRefused(f"KRAKEN_TICK_HTTP_{exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise KrakenFeedRefused("KRAKEN_TICK_NETWORK_UNAVAILABLE") from exc
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise KrakenFeedRefused("KRAKEN_TICK_RESPONSE_BOUNDS")
    return raw


def verified_kraken_tick(
        *, symbol: str = _SYMBOL,
        transport: Callable[[], bytes] | None = None) -> str:
    """Fail closed unless official public instrument is tradeable and tick bound."""
    if symbol != _SYMBOL:
        raise KrakenFeedRefused("KRAKEN_TICK_IDENTITY_DENIED")
    if transport is None:
        transport = _download_instruments
    try:
        raw = transport()
    except KrakenFeedRefused:
        raise
    except Exception as exc:
        raise KrakenFeedRefused("KRAKEN_TICK_TRANSPORT_FAILED") from exc
    if type(raw) is not bytes or not 0 < len(raw) <= 2 * 1024 * 1024:
        raise KrakenFeedRefused("KRAKEN_TICK_RESPONSE_BOUNDS")
    try:
        blob = json.loads(
            raw, parse_float=Decimal,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError) as exc:
        raise KrakenFeedRefused("KRAKEN_TICK_JSON_INVALID") from exc
    if (type(blob) is not dict or blob.get("result") != "success"
            or type(blob.get("instruments")) is not list):
        raise KrakenFeedRefused("KRAKEN_TICK_SCHEMA_INVALID")
    matches = [row for row in blob["instruments"]
               if type(row) is dict and type(row.get("symbol")) is str
               and row["symbol"].upper() == symbol]
    if len(matches) != 1 or matches[0].get("tradeable") is not True:
        raise KrakenFeedRefused("KRAKEN_TICK_INSTRUMENT_NOT_TRADEABLE")
    row = matches[0]
    if (type(row.get("type")) is not str
            or "futures" not in row["type"].lower()):
        raise KrakenFeedRefused("KRAKEN_TICK_CONTRACT_TYPE_INVALID")
    try:
        tick = Decimal(str(row["tickSize"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise KrakenFeedRefused("KRAKEN_TICK_VALUE_INVALID") from exc
    if (not tick.is_finite() or not Decimal("0") < tick <= Decimal("100")
            or tick.as_tuple().exponent < -8):
        raise KrakenFeedRefused("KRAKEN_TICK_VALUE_BOUNDS")
    return str(tick)


def closed_kraken_candles(*, symbol: str, timeframe: str, bars: int = 72,
                          now: datetime | None = None,
                          transport: Callable[[str, str, int, int], bytes] | None = None,
                          timeout: int = 10) -> tuple[bytes, datetime]:
    """Strict actual Kraken TRADE stream candle finalization and provenance."""
    if (symbol != _SYMBOL or timeframe not in SECONDS or
            type(bars) is not int or not MIN_BARS <= bars <= MAX_BARS or
            type(timeout) is not int or not 1 <= timeout <= 15):
        raise KrakenFeedRefused("KRAKEN_FEED_ALLOWLIST_REQUIRED")
    clock = datetime.now(UTC) if now is None else now
    if (not isinstance(clock, datetime) or clock.tzinfo is None
            or clock.utcoffset() is None):
        raise KrakenFeedRefused("KRAKEN_FEED_AWARE_CLOCK_REQUIRED")
    clock = clock.astimezone(UTC)
    if transport is None:
        transport = _download
    try:
        raw = transport(symbol, timeframe, bars + 1, timeout)
    except KrakenFeedRefused:
        raise
    except Exception as exc:
        raise KrakenFeedRefused("KRAKEN_FEED_TRANSPORT_FAILED") from exc
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_REPLY:
        raise KrakenFeedRefused("KRAKEN_FEED_RESPONSE_BOUNDS")
    try:
        decoded = json.loads(
            raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError) as exc:
        raise KrakenFeedRefused("KRAKEN_FEED_JSON_INVALID") from exc
    if (type(decoded) is not dict
            or type(decoded.get("candles")) is not list
            or not 1 <= len(decoded["candles"]) <= bars + 1
            or type(decoded.get("more_candles")) is not bool):
        raise KrakenFeedRefused("KRAKEN_FEED_SCHEMA_INVALID")
    step_ms = SECONDS[timeframe] * 1000
    complete: list[dict] = []
    last_open = None
    rows = decoded["candles"]
    for i, row in enumerate(rows):
        if type(row) is not dict or set(row) != {
                "time", "open", "high", "low", "close", "volume"}:
            raise KrakenFeedRefused("KRAKEN_FEED_BAR_SCHEMA")
        opened = row["time"]
        if (type(opened) is not int or not 0 <= opened <= 4102444800000
                or opened % step_ms != 0 or
                (last_open is not None and opened <= last_open)):
            raise KrakenFeedRefused("KRAKEN_FEED_BAR_CLOCK")
        last_open = opened
        end = datetime.fromtimestamp((opened + step_ms) / 1000, tz=UTC)
        if end > clock - _FINALITY_LAG:
            if i != len(rows) - 1:
                raise KrakenFeedRefused("KRAKEN_FEED_UNCLOSED_INTERIOR")
            continue
        if any(type(row[p]) is not str or not 0 < len(row[p]) <= 48
               for p in ("open", "high", "low", "close")):
            raise KrakenFeedRefused("KRAKEN_FEED_PRICE_STRING")
        volume = row["volume"]
        if (type(volume) not in (str, int, float)
                or len(str(volume)) > 48):
            raise KrakenFeedRefused("KRAKEN_FEED_VOLUME_INVALID")
        complete.append({
            "open_time": datetime.fromtimestamp(opened / 1000, tz=UTC).isoformat(),
            "close_time": end.isoformat(),
            "open": row["open"], "high": row["high"], "low": row["low"],
            "close": row["close"], "volume": str(volume),
        })
    if len(complete) < bars:
        raise KrakenFeedRefused("KRAKEN_FEED_INSUFFICIENT_CLOSED")
    selected = complete[-bars:]
    latest = datetime.fromisoformat(selected[-1]["close_time"])
    if not timedelta(0) <= clock - latest <= timedelta(
            seconds=SECONDS[timeframe] + 30):
        raise KrakenFeedRefused("KRAKEN_FEED_STALE_OR_FUTURE")
    data = json.dumps({
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "kraken_futures_trade_public", "symbol": _SYMBOL,
        "timezone": "UTC", "quote_currency": "USD",
        "exchange": "kraken_futures", "market_type": "futures",
        "timeframe": timeframe, "candles": selected,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_REPLAY_BYTES:
        raise KrakenFeedRefused("KRAKEN_FEED_REPLAY_BOUNDS")
    try:
        parse_candle_replay(data)
    except BrooksReplayRefused as exc:
        raise KrakenFeedRefused("KRAKEN_FEED_REPLAY_VALIDATION_FAILED") from exc
    return data, latest


def poll_once(*, state_dir: str | Path, legacy_source: str | Path,
              symbol: str = _SYMBOL, bars: int = 72,
              now: datetime | None = None,
              transport: Callable[[str, str, int, int], bytes] | None = None,
              metadata_transport: Callable[[], bytes] | None = None) -> dict:
    """Independently check PAPER and scope before and after remote I/O."""
    with EngineControlStore(state_dir) as store:
        engine = store.get(BROOKS_ENGINE_ID)
        pref = store.preferences(BROOKS_ENGINE_ID)
        if (engine is None or not engine.requested_enabled
                or pref["signal_environment"] != "PAPER"
                or pref["market_scope"] not in ("all", "crypto")):
            raise KrakenFeedRefused("KRAKEN_FEED_PAPER_NOT_ARMED")
        rev, pref_rev, timeframe = (
            engine.revision, pref["revision"], pref["timeframe"])
    tick = verified_kraken_tick(symbol=symbol, transport=metadata_transport)
    payload, latest = closed_kraken_candles(
        symbol=symbol, timeframe=timeframe, bars=bars, now=now,
        transport=transport)
    with EngineControlStore(state_dir) as store:
        engine = store.get(BROOKS_ENGINE_ID)
        pref = store.preferences(BROOKS_ENGINE_ID)
        if (engine is None or not engine.requested_enabled
                or engine.revision != rev or pref["revision"] != pref_rev
                or pref["signal_environment"] != "PAPER"
                or pref["timeframe"] != timeframe
                or pref["market_scope"] not in ("all", "crypto")):
            raise KrakenFeedRefused("KRAKEN_FEED_SETTINGS_CHANGED")
    report = replay_once(
        state_dir=state_dir, legacy_source=legacy_source, replay_json=payload,
        kraken_tick_size=tick)
    return {
        **report, "mode": "KRAKEN_FUTURES_CLOSED_TRADE_PAPER",
        "market_feed": _FEED, "symbol": symbol,
        "quote_currency": "USD", "market_type": "futures",
        "exchange_price_tick": tick,
        "timeframe": timeframe, "last_closed_candle": latest.isoformat(),
        "telegram_sent": False, "live_publication_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    option = parser.add_mutually_exclusive_group(required=True)
    option.add_argument("--once", action="store_true")
    option.add_argument("--cycles", type=int, help="2-3 bounded cycles only")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--symbol", default=_SYMBOL)
    parser.add_argument("--bars", type=int, default=72)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--ack-nonproduction-paper", action="store_true")
    args = parser.parse_args(argv)
    if not args.ack_nonproduction_paper:
        print("KRAKEN_FEED_REFUSED:ACK_REQUIRED", file=sys.stderr)
        return 2
    if args.cycles is not None and (
            not 2 <= args.cycles <= 3 or not 30 <= args.poll_seconds <= 3600):
        print("KRAKEN_FEED_REFUSED:BOUNDED_CYCLES_REQUIRED", file=sys.stderr)
        return 2
    try:
        total = 1 if args.once else args.cycles
        for index in range(total):
            if index:
                time.sleep(args.poll_seconds)
            report = poll_once(
                state_dir=args.state_dir, legacy_source=args.legacy_source,
                symbol=args.symbol, bars=args.bars)
            print(json.dumps(report, sort_keys=True), flush=True)
    except (BrooksReplayRefused, OSError, ValueError):
        print("KRAKEN_FEED_REFUSED:FAIL_CLOSED", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
