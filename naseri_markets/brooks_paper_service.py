"""Opt-in, long-running DEVELOPMENT Brooks Kraken Futures PAPER supervisor worker.

Never launched by imports, wheel installation, Telegram startup or admin
button presses. A separate operator-started process follows CAS-admin desired
state, reports real heartbeat, and stops all market requests while disarmed.
There is NO channel publisher or broker path.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable

from .brooks_kraken_feed import poll_once
from .brooks_replay import BrooksReplayRefused, SECONDS, verify_legacy_source
from .engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from .futures_venues import paper_feed_verified
from .trusted_custom import LocalCustomRefused

DEFAULT_SYMBOL = "PF_XBTUSD"
_MIN_POLL_SLEEP = 2
_MAX_POLL_SLEEP = 5
_FINALITY_SLACK_SECONDS = 5


class BrooksServiceRefused(LocalCustomRefused):
    """Refused unsafe, duplicate, non-development or unarmed operation."""


@contextmanager
def exclusive_worker_lock(state_dir: str | Path):
    """Advisory lock for exactly one worker per local state directory."""
    root = Path(state_dir).absolute()
    if root.is_symlink() or not root.is_dir():
        raise BrooksServiceRefused("BROOKS_WORKER_PRIVATE_STATE_DIR_REQUIRED")
    target = root / ".brooks-kraken-paper-worker.lock"
    if target.is_symlink():
        raise BrooksServiceRefused("BROOKS_WORKER_LOCK_SYMLINK")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        if os.fstat(fd).st_nlink != 1:
            raise BrooksServiceRefused("BROOKS_WORKER_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BrooksServiceRefused("BROOKS_WORKER_ALREADY_RUNNING") from exc
        yield
    finally:
        os.close(fd)


class BrooksPaperService:
    """One Kraken linear contract; independently controlled by /engines.

    The worker is a supervised idle process when disabled. UI enables
    analysis eligibility but cannot spawn hidden processes or brokers.
    """
    def __init__(self, *, state_dir: str | Path, legacy_source: str | Path,
                 reader: Callable[..., dict] = poll_once,
                 clock: Callable[[], float] = time.time):
        self.state_dir = Path(state_dir).absolute()
        self.legacy_source = Path(legacy_source).absolute()
        self.reader = reader
        self.clock = clock
        self.worker_id = uuid.uuid4().hex
        self.next_attempt_at = 0.0
        self.last_config: tuple[int, int] | None = None
        self.failures = 0
        self.quit_requested = False

    def start(self) -> None:
        # Verify historical Brooks and source before granting any process lease.
        verify_legacy_source(self.legacy_source)
        with EngineControlStore(self.state_dir) as store:
            store.brooks_worker_claim(worker_id=self.worker_id, now=int(self.clock()))

    def shutdown(self) -> None:
        with EngineControlStore(self.state_dir) as store:
            store.brooks_worker_heartbeat(
                worker_id=self.worker_id, now=int(self.clock()), phase="STOPPED")

    def step(self) -> dict:
        """One heartbeat and at most one real PAPER analysis; never publish."""
        now = int(self.clock())
        with EngineControlStore(self.state_dir) as store:
            state = store.get(BROOKS_ENGINE_ID)
            prefs = store.preferences(BROOKS_ENGINE_ID)
            armed = bool(
                state and state.requested_enabled
                and prefs["signal_environment"] == "PAPER"
                and prefs["market_scope"] in ("all", "crypto"))
            if not armed:
                self.next_attempt_at = 0
                self.last_config = None
                self.failures = 0
                store.brooks_worker_heartbeat(
                    worker_id=self.worker_id, now=now, phase="IDLE")
                return {"phase": "IDLE", "attempted": False}
            # A catalog entry is NOT a verified market-data integration.
            # No automatic fallback to Kraken when another venue was selected.
            if not paper_feed_verified(prefs["futures_exchange"]):
                self.next_attempt_at = 0
                self.last_config = None
                store.brooks_worker_heartbeat(
                    worker_id=self.worker_id, now=now, phase="IDLE")
                return {"phase": "IDLE", "attempted": False,
                        "reason": "BROOKS_SELECTED_EXCHANGE_FEED_NOT_READY"}
            config = (state.revision, prefs["revision"])
            if self.last_config != config:
                # New timeframe/PAPER or operator re-arming should get a fresh
                # last-closed snapshot, never keep another version's deadline.
                self.next_attempt_at = 0
                self.last_config = config
                self.failures = 0
            if now < self.next_attempt_at:
                store.brooks_worker_heartbeat(
                    worker_id=self.worker_id, now=now, phase="WAITING")
                return {"phase": "WAITING", "attempted": False}
            store.brooks_worker_heartbeat(
                worker_id=self.worker_id, now=now, phase="ANALYZING")

        try:
            report = self.reader(
                state_dir=self.state_dir, legacy_source=self.legacy_source,
                symbol=DEFAULT_SYMBOL, bars=72)
            if (type(report) is not dict or report.get("symbol") != DEFAULT_SYMBOL
                    or report.get("market_feed") !=
                    "KRAKEN_FUTURES_TRADE_PUBLIC_HTTPS"
                    or report.get("outcome") not in
                    ("RECORDED", "NO_SIGNAL", "DUPLICATE_SCAN")
                    or report.get("telegram_sent") is not False
                    or report.get("live_publication_enabled") is not False
                    or report.get("timeframe") != prefs["timeframe"]
                    or report.get("selected_exchange") != "kraken"):
                raise BrooksServiceRefused("BROOKS_WORKER_REPORT_INTEGRITY")
            closed = datetime.fromisoformat(report["last_closed_candle"])
            if closed.tzinfo is None or closed.utcoffset() is None:
                raise BrooksServiceRefused("BROOKS_WORKER_CLOSED_TIME_INVALID")
            completed = closed.timestamp()
            if completed > self.clock() or completed < 0:
                raise BrooksServiceRefused("BROOKS_WORKER_CLOSED_TIME_INVALID")
            self.failures = 0
            self.next_attempt_at = max(
                float(self.clock()) + 2,
                completed + SECONDS[prefs["timeframe"]] +
                _FINALITY_SLACK_SECONDS)
            with EngineControlStore(self.state_dir) as store:
                store.brooks_worker_heartbeat(
                    worker_id=self.worker_id, now=int(self.clock()),
                    phase="WAITING", last_closed_candle=report["last_closed_candle"],
                    outcome=report["outcome"])
            return {"phase": "WAITING", "attempted": True,
                    "outcome": report["outcome"], "decision": report["decision"]}
        except (BrooksReplayRefused, LocalCustomRefused, OSError, ValueError,
                KeyError, TypeError) as exc:
            # The existing poll_once refuses unsafe settings/malformed data
            # without a PAPER journal commit. A degraded worker may retry
            # after bounded backoff while still requiring admin PAPER ON.
            self.failures += 1
            self.next_attempt_at = float(self.clock()) + min(
                300, 10 * (2 ** min(self.failures - 1, 5)))
            error_code = str(exc)
            if (not error_code.isascii() or len(error_code) > 90
                    or not error_code.replace("_", "").isalnum()):
                error_code = "BROOKS_WORKER_CYCLE_REFUSED"
            with EngineControlStore(self.state_dir) as store:
                store.brooks_worker_heartbeat(
                    worker_id=self.worker_id, now=int(self.clock()),
                    phase="DEGRADED", error_code=error_code)
            return {"phase": "DEGRADED", "attempted": True,
                    "reason": error_code}

    def run(self, *, max_steps: int = 0,
            sleep: Callable[[float], None] = time.sleep) -> int:
        if type(max_steps) is not int or max_steps < 0:
            raise BrooksServiceRefused("BROOKS_WORKER_STEPS_INVALID")
        self.start()
        count = 0
        try:
            while not self.quit_requested and (
                    max_steps == 0 or count < max_steps):
                result = self.step()
                count += 1
                print(json.dumps(result, sort_keys=True), flush=True)
                if self.quit_requested or (max_steps and count >= max_steps):
                    break
                remaining = self.next_attempt_at - self.clock()
                sleep(min(_MAX_POLL_SLEEP, max(_MIN_POLL_SLEEP, remaining)))
        finally:
            self.shutdown()
        return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=0,
                        help="0=explicit foreground service; positive=bounded test")
    parser.add_argument("--ack-nonproduction-standalone-paper", action="store_true")
    args = parser.parse_args(argv)
    if (not args.ack_nonproduction_standalone_paper
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        print("BROOKS_SERVICE_REFUSED:NONPRODUCTION_OPERATOR_FENCE",
              file=sys.stderr)
        return 2
    worker = BrooksPaperService(
        state_dir=args.state_dir, legacy_source=args.legacy_source)
    def stop(_signum, _frame):
        worker.quit_requested = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        with exclusive_worker_lock(args.state_dir):
            worker.run(max_steps=args.max_steps)
        return 0
    except (BrooksReplayRefused, LocalCustomRefused, OSError, ValueError) as exc:
        print("BROOKS_SERVICE_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
