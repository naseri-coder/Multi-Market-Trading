"""Bid/Ask forward-observation ledger; NO broker executions or P&L claims.

Position outcomes are hypothetical at OBSERVED bid/ask prices. Missing ticks,
lost authentication or a large time gap means UNKNOWN instead of assumed win.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from .contracts import Direction, EvidenceMode, Instrument, SignalIntent
from .quotes import QuoteOrigin, QuoteTick, _utc
from .delivery_ledger import open_sqlite, _wire_intent


class ForwardState(StrEnum):
    OPEN = "OPEN"
    TARGET_OBSERVED = "TARGET_OBSERVED"
    STOP_OBSERVED = "STOP_OBSERVED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ForwardRow:
    engine_id: str
    signal_id: str
    state: ForwardState
    observed_r: Decimal | None
    reason: str | None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS forward_observations (
    engine_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    signal_json TEXT NOT NULL,
    market TEXT NOT NULL,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry TEXT NOT NULL,
    stop TEXT NOT NULL,
    target TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_tick_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN
        ('OPEN','TARGET_OBSERVED','STOP_OBSERVED','UNKNOWN')),
    observed_r TEXT,
    reason TEXT,
    PRIMARY KEY (engine_id, signal_id)
);
CREATE INDEX IF NOT EXISTS forward_market_idx ON forward_observations(engine_id,market,state);
"""


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class ForwardObserver:
    """Durable, provider-scoped forward simulation based on explicit live quotes.

    The Boolean feed attestation is caller-supplied, not an authenticated
    brokerage or market-feed connection. First configured target only (T1).
    This class cannot certify a live trading return.
    """

    def __init__(self, path: str | Path, *, max_gap_seconds: float = 10.0) -> None:
        if not 0 < max_gap_seconds <= 3600:
            raise ValueError("invalid maximum observation gap")
        self.max_gap_seconds = max_gap_seconds
        self._db = open_sqlite(path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _valid_tick(tick: QuoteTick, instrument: Instrument, verified: bool) -> bool:
        return tick.instrument == instrument and tick.origin is QuoteOrigin.LIVE and verified

    def open(self, signal: SignalIntent, tick: QuoteTick, *,
             verified_live_source: bool) -> bool:
        """Start hypothetical paper observation at observed executable side.

        Requires an exact same-timestamp quote; no assumed fill at signal.entry.
        A3 does not permit publication of these outcomes as broker-filled trades.
        """
        if signal.evidence_mode is not EvidenceMode.FORWARD:
            raise ValueError("only forward-observed signal intents")
        if (not self._valid_tick(tick, signal.instrument, verified_live_source)
                or tick.occurred_at != _utc(signal.observed_at)):
            raise ValueError("live tick provenance/identity/time verification required")
        entry = tick.ask if signal.direction is Direction.LONG else tick.bid
        if ((signal.direction is Direction.LONG and
             (entry <= signal.stop or entry >= signal.targets[0]))
                or (signal.direction is Direction.SHORT and
                    (entry >= signal.stop or entry <= signal.targets[0]))):
            raise ValueError("invalid observed entry stop/target geometry")
        raw = _wire_intent(signal)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            current = self._db.execute(
                "SELECT signal_json FROM forward_observations "
                "WHERE engine_id=? AND signal_id=?", (signal.engine_id, signal.signal_id)
            ).fetchone()
            if current:
                if current["signal_json"] != raw:
                    raise ValueError("forward signal identity collision")
                self._db.execute("COMMIT")
                return False
            self._db.execute(
                "INSERT INTO forward_observations "
                "(engine_id,signal_id,signal_json,market,provider,symbol,direction,"
                "entry,stop,target,started_at,last_tick_at,state) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (signal.engine_id, signal.signal_id, raw,
                 signal.instrument.market.value, signal.instrument.provider,
                 signal.instrument.symbol, signal.direction.value, str(entry),
                 str(signal.stop), str(signal.targets[0]),
                 tick.occurred_at.isoformat(), tick.occurred_at.isoformat(),
                 ForwardState.OPEN.value),
            )
            self._db.execute("COMMIT")
            return True
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def get(self, engine_id: str, signal_id: str) -> ForwardRow | None:
        row = self._db.execute(
            "SELECT engine_id,signal_id,state,observed_r,reason FROM forward_observations "
            "WHERE engine_id=? AND signal_id=?", (engine_id, signal_id)
        ).fetchone()
        if row is None:
            return None
        return ForwardRow(
            row["engine_id"], row["signal_id"], ForwardState(row["state"]),
            Decimal(row["observed_r"]) if row["observed_r"] is not None else None,
            row["reason"],
        )

    def observe(self, signal: SignalIntent, tick: QuoteTick, *,
                verified_live_source: bool) -> ForwardRow:
        """Observe only the exact signal/instrument on a strictly later tick.

        No inference across missing ticks. UNKNOWN is terminal until an audited
        reconciliation policy is implemented in a separate stage.
        """
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM forward_observations WHERE engine_id=? AND signal_id=?",
                (signal.engine_id, signal.signal_id),
            ).fetchone()
            if row is None:
                raise ValueError("unknown forward intent")
            if row["signal_json"] != _wire_intent(signal):
                raise ValueError("forward signal identity collision")
            if row["state"] != ForwardState.OPEN.value:
                self._db.execute("COMMIT")
                return self.get(signal.engine_id, signal.signal_id)
            if tick.instrument != signal.instrument:
                raise ValueError("tick belongs to a different instrument")
            previous = _parse_time(row["last_tick_at"])
            gap = (tick.occurred_at - previous).total_seconds()
            if (not self._valid_tick(tick, signal.instrument, verified_live_source)
                    or gap <= 0 or gap > self.max_gap_seconds):
                next_state = ForwardState.UNKNOWN
                reason = "UNVERIFIED_TICK_OR_GAP"
                observed_r = None
            else:
                entry = Decimal(row["entry"])
                stop = Decimal(row["stop"])
                target = Decimal(row["target"])
                if signal.direction is Direction.LONG:
                    exit_side = tick.bid
                    hit_stop = exit_side <= stop
                    hit_target = exit_side >= target
                    risk = entry - stop
                    gain = exit_side - entry
                else:
                    exit_side = tick.ask
                    hit_stop = exit_side >= stop
                    hit_target = exit_side <= target
                    risk = stop - entry
                    gain = entry - exit_side
                next_state = (ForwardState.STOP_OBSERVED if hit_stop else
                              ForwardState.TARGET_OBSERVED if hit_target else
                              ForwardState.OPEN)
                observed_r = (gain / risk) if next_state is not ForwardState.OPEN else None
                reason = None
            self._db.execute(
                "UPDATE forward_observations "
                "SET last_tick_at=?, state=?, observed_r=?, reason=? "
                "WHERE engine_id=? AND signal_id=?",
                (tick.occurred_at.isoformat(), next_state.value,
                 str(observed_r) if observed_r is not None else None,
                 reason, signal.engine_id, signal.signal_id),
            )
            self._db.execute("COMMIT")
            return self.get(signal.engine_id, signal.signal_id)
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def summary(self, engine_id: str) -> dict[str, object]:
        rows = self._db.execute(
            "SELECT state,observed_r FROM forward_observations WHERE engine_id=?",
            (engine_id,),
        ).fetchall()
        counts = {state.value: 0 for state in ForwardState}
        realized: list[Decimal] = []
        for row in rows:
            counts[row["state"]] += 1
            if row["state"] in (ForwardState.TARGET_OBSERVED.value,
                                ForwardState.STOP_OBSERVED.value):
                realized.append(Decimal(row["observed_r"]))
        return {
            "engine_id": engine_id,
            "total": len(rows),
            "states": counts,
            "resolved": len(realized),
            "observed_mean_r": (
                sum(realized, Decimal("0")) / len(realized) if realized else None
            ),
            "is_broker_filled": False,
        }
