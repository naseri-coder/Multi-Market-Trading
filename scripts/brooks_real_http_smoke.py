"""Ephemeral, opt-in E2E: PUBLIC Binance HTTP -> real frozen Brooks V5 -> PAPER.

No persistent service, no trading credentials, no live Telegram or production DB.
This script is deliberately never invoked on module import / ordinary CI tests.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from naseri_markets.brooks_market_feed import BrooksMarketFeedRefused, poll_loop, poll_once
from naseri_markets.brooks_replay import BrooksReplayRefused, verify_legacy_source
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore


def run(*, source: Path, cycles: int = 2) -> dict:
    """Demonstrate operator permission and genuine independent data origin."""
    if not 2 <= cycles <= 3:
        raise ValueError("BROOKS_SMOKE_BOUNDED_CYCLES_REQUIRED")
    source_pin = verify_legacy_source(source)  # source never changed
    with tempfile.TemporaryDirectory(prefix="brooks-public-http-paper-") as temporary:
        state_dir = Path(temporary) / "disposable-private-state"
        # Fail closed BEFORE fetching market data when the operator disabled PAPER.
        calls = []
        def forbidden_transport(*args):
            calls.append("unexpected")
            raise AssertionError("Network reached while disarmed")

        try:
            poll_once(
                state_dir=state_dir, legacy_source=source,
                symbol="BTCUSDT", bars=72, transport=forbidden_transport)
            raise AssertionError("Disarmed poll unexpectedly succeeded")
        except BrooksMarketFeedRefused as exc:
            assert str(exc) == "BROOKS_FEED_PAPER_NOT_ARMED", str(exc)
        assert not calls, "Disarmed poll touched transport"

        # Mimics exactly the CAS-backed actions in the private admin UI,
        # but uses an ephemeral local DB and no Telegram bot/application.
        with EngineControlStore(state_dir) as store:
            entry = store.get(BROOKS_ENGINE_ID)
            assert entry and not entry.requested_enabled
            store.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=True,
                expected_revision=entry.revision, actor_id=123)
            preferences = store.preferences(BROOKS_ENGINE_ID)
            store.change_preference(
                BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
                expected_revision=preferences["revision"], actor_id=123)
            pub = store.publication(BROOKS_ENGINE_ID)
            store.request_publication(
                BROOKS_ENGINE_ID, enabled=True,
                expected_revision=pub["revision"], actor_id=123)
            assert store.publication(BROOKS_ENGINE_ID)["requested_publication"]
            assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
            assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"

        # Only these cycles make HTTPS GETs to Binance. Network failures are
        # classified externally blocked, not papered over with fake candles.
        reports: list[dict] = []
        poll_loop(
            state_dir=state_dir, legacy_source=source, symbol="BTCUSDT",
            bars=72, max_cycles=cycles, interval_seconds=30,
            emit=reports.append)
        assert len(reports) == cycles
        assert all(
            result["mode"] == "AUTOMATIC_MARKET_CLOSED_CANDLE_PAPER"
            and result["market_feed"] == "BINANCE_USDM_PUBLIC_HTTPS"
            and result["decision"] in ("LONG", "SHORT", "NO_SIGNAL")
            and not result["telegram_sent"]
            and not result["live_publication_enabled"]
            for result in reports
        )
        assert len(set(row["scan_id"] for row in reports)) <= cycles
        assert all(row["source_manifest_sha256"] == source_pin for row in reports)
        with EngineControlStore(state_dir) as store:
            metrics = store.brooks_replay_status()
            assert 1 <= metrics["scans"] <= cycles
            assert metrics["paper_signals"] >= 0
            assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
            assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
            current = store.get(BROOKS_ENGINE_ID)
            store.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=False,
                expected_revision=current.revision, actor_id=123)
            assert not store.get(BROOKS_ENGINE_ID).requested_enabled
            before = store.brooks_replay_status()

        # A disabled core cannot reach the real Binance endpoint or the child.
        try:
            poll_once(
                state_dir=state_dir, legacy_source=source,
                symbol="BTCUSDT", bars=72, transport=forbidden_transport)
            raise AssertionError("Revoked poll unexpectedly succeeded")
        except BrooksMarketFeedRefused as exc:
            assert str(exc) == "BROOKS_FEED_PAPER_NOT_ARMED", str(exc)
        assert not calls
        with EngineControlStore(state_dir) as store:
            assert store.brooks_replay_status() == before
            assert store.publication(BROOKS_ENGINE_ID)["effective_publication"] is False
            assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        return {
            "verdict": "PASS_ACTUAL_PUBLIC_HTTPS_BROOKS_PAPER",
            "utc_completed_at": datetime.now(UTC).isoformat(),
            "symbol": "BTCUSDT", "timeframe": "15m",
            "cycles": cycles, "scans": metrics["scans"],
            "no_signal": metrics["no_signal"],
            "paper_signals": metrics["paper_signals"],
            "last_closed_candle": reports[-1]["last_closed_candle"],
            "last_decision": reports[-1]["decision"],
            "idempotent": (metrics["scans"] == len(set(x["scan_id"] for x in reports))),
            "operator_disarm_verified": True,
            "requested_publication_did_not_enable_delivery": True,
            "channel_sent": False, "broker_orders": False,
            "production_db_touched": False, "source_manifest_sha256": source_pin,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--ack-public-http-paper", action="store_true",
                        help="one-off real public HTTPS, ephemeral PAPER only")
    args = parser.parse_args(argv)
    if not args.ack_public_http_paper:
        print('BROOKS_HTTP_E2E={"verdict":"REFUSED_NO_OPERATOR_ACK"}')
        return 2
    try:
        result = run(source=args.legacy_source, cycles=args.cycles)
    except BrooksMarketFeedRefused as exc:
        # The allowed reader is deliberately hardcoded to public Binance.
        result = {"verdict": "BLOCKED_EXTERNAL_MARKET_FEED",
                  "reason": str(exc), "real_http_verified": False,
                  "source_not_modified": True, "production_untouched": True}
        print("BROOKS_HTTP_E2E=" + json.dumps(result, sort_keys=True))
        return 3
    except BrooksReplayRefused as exc:
        result = {"verdict": "BLOCKED_BROOKS_VALIDATION",
                  "reason": str(exc), "real_http_verified": False,
                  "production_untouched": True}
        print("BROOKS_HTTP_E2E=" + json.dumps(result, sort_keys=True))
        return 4
    print("BROOKS_HTTP_E2E=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
