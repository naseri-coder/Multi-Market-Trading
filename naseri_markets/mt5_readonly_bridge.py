"""Public, optional, read-only MT5 Bid/Ask quote-to-JSONL bridge.

Works with any explicitly selected broker symbol. Does NOT contain a strategy,
call order_send, publish signals, or place a trade. Running requires a local,
already-authorized MetaTrader 5 terminal and the optional MetaTrader5 package.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

UTC = timezone.utc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--poll-ms", type=int, default=250)
    p.add_argument("--lookback-seconds", type=int, default=2)
    p.add_argument("--max-backlog-seconds", type=int, default=8)
    args = p.parse_args()
    if not 100 <= args.poll_ms <= 5000:
        p.error("poll-ms must be 100..5000")
    if not 1 <= args.lookback_seconds <= 60 or not 1 <= args.max_backlog_seconds <= 60:
        p.error("invalid time bound")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit("OPTIONAL_METATRADER5_PACKAGE_NOT_INSTALLED")
    if not mt5.initialize():
        sys.exit("MT5_TERMINAL_CONNECTION_UNAVAILABLE")
    try:
        info = mt5.symbol_info(args.symbol)
        if info is None or not mt5.symbol_select(args.symbol, True):
            sys.exit("MT5_SYMBOL_NOT_AVAILABLE")
        if info.trade_tick_size <= 0:
            sys.exit("MT5_SYMBOL_TICK_SIZE_INVALID")
        print(
            f"READ_ONLY_FEED symbol={args.symbol} tick_size={info.trade_tick_size}",
            file=sys.stderr, flush=True,
        )
        cursor = int(datetime.now(UTC).timestamp() * 1000) - args.lookback_seconds * 1000
        seen: set[tuple[int, float, float]] = set()
        while True:
            now = datetime.now(UTC)
            quotes = mt5.copy_ticks_range(
                args.symbol,
                datetime.fromtimestamp((cursor - 1000) / 1000, tz=UTC),
                now,
                mt5.COPY_TICKS_ALL,
            )
            if quotes is None:
                sys.exit("MT5_TICK_QUERY_FAILURE_STOP")
            if len(quotes):
                latest = max(int(q["time_msc"]) for q in quotes)
                if now.timestamp() * 1000 - latest > args.max_backlog_seconds * 1000:
                    sys.exit("MT5_QUOTES_STALE_STOP")
                for quote in sorted(quotes, key=lambda q: int(q["time_msc"])):
                    ms = int(quote["time_msc"])
                    bid, ask = float(quote["bid"]), float(quote["ask"])
                    key = ms, bid, ask
                    if ms < cursor or key in seen:
                        continue
                    if bid <= 0 or ask < bid:
                        sys.exit("MT5_BAD_BID_ASK_STOP")
                    seen.add(key)
                    print(json.dumps({
                        "symbol": args.symbol,
                        "ts_utc": datetime.fromtimestamp(ms / 1000, UTC).isoformat(),
                        "bid": bid,
                        "ask": ask,
                    }), flush=True)
                cursor = max(cursor, latest - 1000)
                seen = {key for key in seen if key[0] >= cursor}
            elif now.timestamp() * 1000 - cursor > args.max_backlog_seconds * 1000:
                sys.exit("MT5_NO_FRESH_QUOTES_STOP")
            time.sleep(args.poll_ms / 1000)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
