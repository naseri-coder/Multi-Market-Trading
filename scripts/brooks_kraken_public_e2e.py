"""Real Kraken public BTC/USD futures -> frozen Brooks -> ephemeral PAPER E2E.

NO operator exchange key, broker, channel, production state or persistent
worker. Explicit acknowledgement required. Runs once and exits.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from naseri_markets.brooks_kraken_feed import KrakenFeedRefused, poll_once
from naseri_markets.brooks_replay import BrooksReplayRefused, verify_legacy_source
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore


def run(*, source: Path) -> dict:
    pinned = verify_legacy_source(source)
    with tempfile.TemporaryDirectory(prefix="brooks-kraken-futures-paper-") as temp:
        state = Path(temp) / "isolated-state"
        network_calls = []
        def forbidden(*args):
            network_calls.append("breach")
            raise AssertionError("network accessed with Brooks OFF")

        try:
            poll_once(state_dir=state, legacy_source=source, transport=forbidden)
            raise AssertionError("disarmed Brooks unexpectedly analyzed")
        except KrakenFeedRefused as error:
            assert str(error) == "KRAKEN_FEED_PAPER_NOT_ARMED"
        assert not network_calls

        with EngineControlStore(state) as store:
            core = store.get(BROOKS_ENGINE_ID)
            store.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=True,
                expected_revision=core.revision, actor_id=123)
            pref = store.preferences(BROOKS_ENGINE_ID)
            store.change_preference(
                BROOKS_ENGINE_ID, field="signal_environment",
                value="PAPER", expected_revision=pref["revision"], actor_id=123)
            pub = store.publication(BROOKS_ENGINE_ID)
            store.request_publication(
                BROOKS_ENGINE_ID, enabled=True,
                expected_revision=pub["revision"], actor_id=123)
            assert store.publication(BROOKS_ENGINE_ID)["requested_publication"]
            assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
            assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"

        # Two actual network reads with a physical 30-second pause.
        first = poll_once(
            state_dir=state, legacy_source=source, symbol="PF_XBTUSD",
            bars=72)
        time.sleep(30)
        second = poll_once(
            state_dir=state, legacy_source=source, symbol="PF_XBTUSD",
            bars=72)
        results = [first, second]
        assert all(
            x["market_feed"] == "KRAKEN_FUTURES_TRADE_PUBLIC_HTTPS"
            and x["market_type"] == "futures"
            and x["quote_currency"] == "USD"
            and x["symbol"] == "PF_XBTUSD"
            and x["mode"] == "KRAKEN_FUTURES_CLOSED_TRADE_PAPER"
            and x["decision"] in ("NO_SIGNAL", "LONG", "SHORT")
            and not x["telegram_sent"]
            and not x["live_publication_enabled"]
            for x in results
        )
        seen = {x["scan_id"] for x in results}
        with EngineControlStore(state) as store:
            status = store.brooks_replay_status()
            assert status["scans"] == len(seen) <= 2
            assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
            assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
            core = store.get(BROOKS_ENGINE_ID)
            store.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=False,
                expected_revision=core.revision, actor_id=123)
            frozen_status = store.brooks_replay_status()
        try:
            poll_once(state_dir=state, legacy_source=source, transport=forbidden)
            raise AssertionError("revoked Brooks unexpectedly analyzed")
        except KrakenFeedRefused as error:
            assert str(error) == "KRAKEN_FEED_PAPER_NOT_ARMED"
        assert not network_calls
        with EngineControlStore(state) as store:
            assert store.brooks_replay_status() == frozen_status
            assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        return {
            "verdict": "PASS_REAL_KRAKEN_FUTURES_BROOKS_PAPER",
            "utc_completed_at": datetime.now(UTC).isoformat(),
            "provider": "kraken_futures_trade_public",
            "contract": "PF_XBTUSD", "quote": "USD",
            "market_type": "futures", "timeframe": "15m",
            "http_cycles": 2, "unique_scans": len(seen),
            "no_signal": status["no_signal"],
            "paper_signal_count": status["paper_signals"],
            "decisions": [x["decision"] for x in results],
            "outcomes": [x["outcome"] for x in results],
            "last_closed_candle": second["last_closed_candle"],
            "requested_publication_never_enabled_delivery": True,
            "revoked_before_http_verified": True,
            "telegram_sent": False, "broker_orders": False,
            "production_db_touched": False, "source_pin": pinned,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--ack-ephemeral-public-paper", action="store_true")
    args = parser.parse_args(argv)
    if not args.ack_ephemeral_public_paper:
        print('BROOKS_KRAKEN_E2E={"verdict":"REFUSED_NO_ACK"}')
        return 2
    try:
        result = run(source=args.legacy_source)
    except (KrakenFeedRefused, BrooksReplayRefused) as exc:
        print("BROOKS_KRAKEN_E2E=" + json.dumps({
            "verdict": "BLOCKED_OR_FAILED_NOT_PASS", "reason": str(exc),
            "production_untouched": True, "telegram_sent": False,
        }, sort_keys=True))
        return 3
    print("BROOKS_KRAKEN_E2E=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
