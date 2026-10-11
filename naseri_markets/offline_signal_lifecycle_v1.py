"""Stage 10: inert OFFLINE signal lifecycle and durable Telegram-shaped outbox.

NO Telegram transport, socket, token, account, broker, order, public delivery,
or LIVE data handling. All acknowledgements are LOCAL SIMULATIONS ONLY.
This is a new research database, NOT migration of the legacy SignalLedger.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from .contracts import Direction, Instrument, Market
from .core_api_v1 import (
    BidAskTick, CoreDecision, CoreEventType, CoreInput, CoreManifest,
    CoreResult, DataOrigin, DecisionKind, ManagementAction,
    _canonical, _utc, validate_core_result,
)
from .market_data_engine_v1 import PriceBasis, VolumeSemantics


class SignalLifecycleRefused(ValueError):
    """Safe refusal. Never treat it as a broker fill or a sent Telegram message."""


class SignalState(StrEnum):
    WAITING_ENTRY = "WAITING_ENTRY"
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    TARGETS_COMPLETE = "TARGETS_COMPLETE"
    EXPIRED = "EXPIRED"


class OutboxState(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SIMULATED_ACK = "SIMULATED_ACK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DryRunCommand:
    signal_key: str
    revision: int
    command: str
    channel_id: int
    text: str
    message_id: int | None
    state: OutboxState


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    key: str
    core_id: str
    instance_id: str
    binding_id: str
    setup_id: str
    instrument: Instrument
    direction: Direction
    entry: Decimal
    initial_stop: Decimal
    stop: Decimal
    targets: tuple[Decimal, ...]
    hit_targets: int
    state: SignalState
    revision: int
    observed_r: Decimal
    channel_id: int
    last_seen_at: datetime
    last_sequence: int | None
    message_id: int | None


def _json(data: object) -> str:
    return json.dumps(_canonical(data), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _digest(data: object) -> str:
    return hashlib.sha256(_json(data).encode("utf-8")).hexdigest()


def _positive(value: object, label: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise SignalLifecycleRefused("INVALID_" + label)
    return value


def _safe_label(value: str, label: str) -> None:
    if (type(value) is not str or not 1 <= len(value) <= 96 or
            any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise SignalLifecycleRefused("UNSAFE_" + label)


def _status_view(row: sqlite3.Row) -> SignalSnapshot:
    return SignalSnapshot(
        key=row["signal_key"], core_id=row["core_id"],
        instance_id=row["instance_id"], binding_id=row["binding_id"],
        setup_id=row["setup_id"],
        instrument=Instrument(Market(row["market"]), row["provider"],
                              row["symbol"], row["timezone"], row["currency"]),
        direction=Direction(row["direction"]),
        entry=Decimal(row["entry_price"]),
        initial_stop=Decimal(row["initial_stop"]),
        stop=Decimal(row["current_stop"]),
        targets=tuple(Decimal(v) for v in json.loads(row["targets_json"])),
        hit_targets=row["targets_hit"], state=SignalState(row["status"]),
        revision=row["revision"], observed_r=Decimal(row["observed_r"]),
        channel_id=row["channel_id"],
        last_seen_at=datetime.fromisoformat(row["last_observed_at"]),
        last_sequence=row["last_sequence"], message_id=row["message_id"],
    )


def render_signal(snapshot: SignalSnapshot) -> str:
    """Plain-text Telegram preview. No parse_mode or untrusted markup."""
    if not isinstance(snapshot, SignalSnapshot):
        raise SignalLifecycleRefused("SNAPSHOT_REQUIRED")
    title = ("OFFLINE PAPER SIGNAL — NOT SENT\n"
             f"{snapshot.instrument.market.value.upper()} | "
             f"{snapshot.instrument.provider} / {snapshot.instrument.symbol}\n"
             f"Setup: {snapshot.setup_id}\n"
             f"Side: {snapshot.direction.value.upper()}\n"
             f"Entry (theoretical): {snapshot.entry}\n"
             f"Stop (observational): {snapshot.stop}\n"
             + "Targets: " + ", ".join(str(p) for p in snapshot.targets) + "\n")
    status = (f"State: {snapshot.state.value} | targets observed: "
              f"{snapshot.hit_targets}/{len(snapshot.targets)}\n"
              f"Gross observed R (NO costs/fills): {snapshot.observed_r}\n"
              f"Event revision: {snapshot.revision}\n"
              "Observed signal outcome only; no exchange/broker PnL, no actual execution.")
    if len(title + status) > 3500:
        raise SignalLifecycleRefused("TELEGRAM_PREVIEW_TOO_LARGE")
    return title + status


class OfflineSignalLifecycle:
    """Durable isolated signal observer, no real transport and no auto-dispatch.

    Only known nonproduction Core API results may be registered. The operator
    controls channel and intent binding, never the strategy. A signal cannot
    place, reserve, modify or close a broker order from this API.
    """

    def __init__(self, path: str | Path, *, enabled: bool = False):
        if type(enabled) is not bool:
            raise SignalLifecycleRefused("EXPLICIT_ENABLE_FLAG_REQUIRED")
        p = Path(path)
        if str(path) == ":memory:" or p.is_symlink() or (p.exists() and not p.is_file()):
            raise SignalLifecycleRefused("ISOLATED_DISK_DATABASE_REQUIRED")
        if not p.parent.is_dir():
            raise SignalLifecycleRefused("EXISTING_DIRECTORY_REQUIRED")
        self.enabled = enabled
        self._db = sqlite3.connect(str(p), timeout=8, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA busy_timeout=8000")
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS offline_signal_states (
          signal_key TEXT PRIMARY KEY, core_id TEXT NOT NULL,
          instance_id TEXT NOT NULL, binding_id TEXT NOT NULL,
          setup_id TEXT NOT NULL, decision_id TEXT NOT NULL,
          initial_digest TEXT NOT NULL, source_ref TEXT NOT NULL,
          market TEXT NOT NULL, provider TEXT NOT NULL, symbol TEXT NOT NULL,
          timezone TEXT NOT NULL, currency TEXT NOT NULL,
          direction TEXT NOT NULL, entry_price TEXT NOT NULL,
          initial_stop TEXT NOT NULL, current_stop TEXT NOT NULL,
          targets_json TEXT NOT NULL, targets_hit INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL CHECK(status IN
            ('WAITING_ENTRY','ACTIVE','STOPPED','TARGETS_COMPLETE','EXPIRED')),
          observed_r TEXT NOT NULL, revision INTEGER NOT NULL,
          created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
          last_observed_at TEXT NOT NULL, last_sequence INTEGER,
          last_event_digest TEXT, channel_id INTEGER NOT NULL CHECK(channel_id<0),
          message_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS offline_signal_events (
          signal_key TEXT NOT NULL REFERENCES offline_signal_states(signal_key),
          revision INTEGER NOT NULL, event_name TEXT NOT NULL,
          payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
          PRIMARY KEY (signal_key, revision)
        );
        CREATE TABLE IF NOT EXISTS offline_signal_commands (
          signal_key TEXT NOT NULL REFERENCES offline_signal_states(signal_key),
          revision INTEGER NOT NULL, command TEXT NOT NULL
            CHECK(command IN ('SEND','EDIT')),
          state TEXT NOT NULL CHECK(state IN
            ('PENDING','CLAIMED','SIMULATED_ACK','UNKNOWN')),
          text TEXT NOT NULL, channel_id INTEGER NOT NULL CHECK(channel_id<0),
          message_id INTEGER, PRIMARY KEY (signal_key, revision)
        );
        CREATE INDEX IF NOT EXISTS offline_signal_outbox_pending
          ON offline_signal_commands(state, signal_key, revision);
        """)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "OfflineSignalLifecycle":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _require(self) -> None:
        if not self.enabled:
            raise SignalLifecycleRefused("OFFLINE_SIGNAL_ENGINE_DISABLED")

    def _row(self, key: str) -> sqlite3.Row:
        if type(key) is not str or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise SignalLifecycleRefused("INVALID_SIGNAL_KEY")
        row = self._db.execute(
            "SELECT * FROM offline_signal_states WHERE signal_key=?", (key,)
        ).fetchone()
        if row is None:
            raise SignalLifecycleRefused("UNKNOWN_SIGNAL")
        return row

    def snapshot(self, key: str) -> SignalSnapshot:
        return _status_view(self._row(key))

    def events(self, key: str) -> tuple[dict, ...]:
        self._row(key)
        return tuple(dict(row) for row in self._db.execute(
            "SELECT revision,event_name,payload_json,payload_sha256 "
            "FROM offline_signal_events WHERE signal_key=? ORDER BY revision", (key,)
        ))

    def _event(self, key: str, revision: int, name: str, data: dict) -> None:
        body = _json(data)
        self._db.execute("INSERT INTO offline_signal_events VALUES (?,?,?,?,?)",
                         (key, revision, name, body, hashlib.sha256(body.encode()).hexdigest()))

    def _outbox(self, key: str, revision: int, command: str) -> None:
        snapshot = self.snapshot(key)
        self._db.execute(
            "INSERT INTO offline_signal_commands "
            "(signal_key,revision,command,state,text,channel_id) "
            "VALUES (?,?,?,'PENDING',?,?)",
            (key, revision, command, render_signal(snapshot), snapshot.channel_id),
        )

    def register(self, manifest: CoreManifest, event: CoreInput, result: CoreResult,
                 decision: CoreDecision, *, channel_id: int,
                 price_basis: PriceBasis, volume_semantics: VolumeSemantics,
                 expires_at: datetime, operator_ack: bool = False) -> SignalSnapshot:
        self._require()
        if operator_ack is not True or type(channel_id) is not int or channel_id >= 0:
            raise SignalLifecycleRefused("OFFLINE_OPERATOR_CHANNEL_ACK_REQUIRED")
        validate_core_result(manifest, event, result)
        if (event.origin not in (DataOrigin.REPLAY, DataOrigin.SYNTHETIC)
                or event.event not in (CoreEventType.CLOSED_CANDLE, CoreEventType.QUOTE_TICK)
                or decision not in result.decisions
                or decision.kind is not DecisionKind.ENTRY_INTENT):
            raise SignalLifecycleRefused("OFFLINE_ENTRY_DECISION_REQUIRED")
        if (not isinstance(price_basis, PriceBasis)
                or not isinstance(volume_semantics, VolumeSemantics)
                or price_basis is PriceBasis.INDEX or price_basis is PriceBasis.MARK
                or (event.event is CoreEventType.CLOSED_CANDLE and price_basis is PriceBasis.BID_ASK)
                or (event.event is CoreEventType.QUOTE_TICK and price_basis is not PriceBasis.BID_ASK)):
            raise SignalLifecycleRefused("INVALID_SIGNAL_PRICE_BASIS")
        # A bid-only FX reference does not prove executable ask-entry.
        if event.binding.instrument.market is Market.FOREX and price_basis is not PriceBasis.BID_ASK:
            raise SignalLifecycleRefused("FOREX_EXECUTABLE_QUOTE_UNVERIFIED")
        until = _utc(expires_at)
        if not event.observed_at < until <= event.observed_at + timedelta(days=7):
            raise SignalLifecycleRefused("INVALID_ENTRY_EXPIRY")
        if decision.expires_at is not None and until > decision.expires_at:
            raise SignalLifecycleRefused("ENTRY_EXPIRY_EXCEEDS_CORE_DECISION")
        if (tuple(decision.targets) != tuple(sorted(decision.targets,
                reverse=decision.direction is Direction.SHORT))
                or len(set(decision.targets)) != len(decision.targets)):
            raise SignalLifecycleRefused("TARGET_ORDER_INVALID")
        i = event.binding.instrument
        for field, value in (("PROVIDER", i.provider), ("SYMBOL", i.symbol),
                             ("SETUP", decision.setup_id)):
            _safe_label(value, field)
        identity = {"core":event.core_id,"version":event.core_version,
                    "instance":event.binding.instance_id,"binding":event.binding.binding_id,
                    "decision":decision.decision_id}
        key = _digest(identity)
        contract = {"identity":identity,"event":event.input_digest,
                    "result":_digest(result),"channel":channel_id,
                    "basis":price_basis.value,"volume":volume_semantics.value,
                    "expires_at":until.isoformat()}
        digest = _digest(contract)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            old = self._db.execute("SELECT initial_digest FROM offline_signal_states "
                                   "WHERE signal_key=?", (key,)).fetchone()
            if old is not None:
                if old["initial_digest"] != digest:
                    raise SignalLifecycleRefused("SIGNAL_IDENTITY_PAYLOAD_CONFLICT")
                self._db.execute("COMMIT")
                return self.snapshot(key)
            self._db.execute("""INSERT INTO offline_signal_states (
                signal_key,core_id,instance_id,binding_id,setup_id,decision_id,
                initial_digest,source_ref,market,provider,symbol,timezone,currency,
                direction,entry_price,initial_stop,current_stop,targets_json,
                status,observed_r,revision,created_at,expires_at,last_observed_at,
                channel_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'WAITING_ENTRY','0',1,?,?,?,?)""",
                (key,event.core_id,event.binding.instance_id,event.binding.binding_id,
                 decision.setup_id,decision.decision_id,digest,event.source_ref,
                 i.market.value,i.provider,i.symbol,i.timezone,i.quote_currency,
                 decision.direction.value,str(decision.entry),str(decision.stop),
                 str(decision.stop),_json(decision.targets), event.observed_at.isoformat(),
                 until.isoformat(),event.observed_at.isoformat(),channel_id))
            self._event(key,1,"REGISTER",contract)
            self._outbox(key,1,"SEND")
            self._db.execute("COMMIT")
            return self.snapshot(key)
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def observe(self, key: str, *, instrument: Instrument, tick: BidAskTick,
                origin: DataOrigin, source_ref: str, sequence: int,
                operator_ack: bool = False) -> SignalSnapshot:
        self._require()
        if (operator_ack is not True or not isinstance(instrument, Instrument)
                or not isinstance(tick, BidAskTick) or type(origin) is not DataOrigin or origin not in
                (DataOrigin.REPLAY, DataOrigin.SYNTHETIC) or
                type(source_ref) is not str or not source_ref or
                type(sequence) is not int or sequence <= 0):
            raise SignalLifecycleRefused("UNVERIFIED_OFFLINE_OBSERVATION")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._row(key)
            snap = _status_view(row)
            if (instrument != snap.instrument or source_ref != row["source_ref"]):
                raise SignalLifecycleRefused("OBSERVATION_INSTRUMENT_OR_SOURCE_MISMATCH")
            digest = _digest({"instrument":instrument,"tick":tick,"origin":origin.value,
                              "source":source_ref,"sequence":sequence})
            if row["last_sequence"] is not None and sequence == row["last_sequence"]:
                if digest != row["last_event_digest"]:
                    raise SignalLifecycleRefused("CONFLICTING_OBSERVATION_SEQUENCE")
                self._db.execute("COMMIT")
                return snap
            if (row["last_sequence"] is not None and sequence != row["last_sequence"] + 1):
                raise SignalLifecycleRefused("OBSERVATION_SEQUENCE_GAP")
            if tick.occurred_at <= snap.last_seen_at:
                raise SignalLifecycleRefused("OBSERVATION_NOT_CAUSAL")
            is_terminal = snap.state in (SignalState.STOPPED,SignalState.TARGETS_COMPLETE,SignalState.EXPIRED)
            next_state = snap.state
            next_hits = snap.hit_targets
            obs_r = snap.observed_r
            next_name = "OBSERVED_NO_CHANGE"
            if not is_terminal and snap.state is SignalState.WAITING_ENTRY:
                if tick.occurred_at > datetime.fromisoformat(row["expires_at"]):
                    next_state, next_name = SignalState.EXPIRED, "ENTRY_EXPIRED"
                elif ((snap.direction is Direction.LONG and tick.ask <= snap.entry)
                      or (snap.direction is Direction.SHORT and tick.bid >= snap.entry)):
                    next_state, next_name = SignalState.ACTIVE, "ENTRY_OBSERVED"
                # Deliberately no target or stop credit on the first entry tick.
            elif not is_terminal and snap.state is SignalState.ACTIVE:
                exit_price = tick.bid if snap.direction is Direction.LONG else tick.ask
                stop_touched = (exit_price <= snap.stop if snap.direction is Direction.LONG
                                else exit_price >= snap.stop)
                sign = Decimal(1) if snap.direction is Direction.LONG else Decimal(-1)
                unit_r = abs(snap.entry - snap.initial_stop)
                slots = Decimal(len(snap.targets))
                if stop_touched:
                    # Adverse gap handling; never assume execution at the stop.
                    stop_value = min(exit_price, snap.stop) if sign == 1 else max(exit_price, snap.stop)
                    obs_r += (slots-Decimal(next_hits))/slots * sign*(stop_value-snap.entry)/unit_r
                    next_state, next_name = SignalState.STOPPED, "STOP_OBSERVED"
                else:
                    while next_hits < len(snap.targets):
                        target = snap.targets[next_hits]
                        touched = exit_price >= target if sign == 1 else exit_price <= target
                        if not touched:
                            break
                        obs_r += sign*(target-snap.entry)/unit_r/slots
                        next_hits += 1
                    if next_hits == len(snap.targets):
                        next_state, next_name = SignalState.TARGETS_COMPLETE, "ALL_TARGETS_OBSERVED"
                    elif next_hits > snap.hit_targets:
                        next_name = "TARGET_OBSERVED"
            new_revision = snap.revision + (next_name != "OBSERVED_NO_CHANGE")
            self._db.execute("UPDATE offline_signal_states SET status=?,targets_hit=?,observed_r=?,"
                             "revision=?,last_sequence=?,last_event_digest=?,last_observed_at=? "
                             "WHERE signal_key=?",
                             (next_state.value,next_hits,str(obs_r),new_revision,
                              sequence,digest,tick.occurred_at.isoformat(),key))
            if next_name != "OBSERVED_NO_CHANGE":
                self._event(key,new_revision,next_name, {"sequence":sequence,
                    "event_at":tick.occurred_at.isoformat(),"bid":str(tick.bid),
                    "ask":str(tick.ask),"status":next_state.value,
                    "targets_hit":next_hits,"observed_r":str(obs_r)})
                self._outbox(key,new_revision,"EDIT")
            self._db.execute("COMMIT")
            return self.snapshot(key)
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def tighten_stop_from_core(self, key: str, manifest: CoreManifest,
                               event: CoreInput, result: CoreResult,
                               decision: CoreDecision, *, expected_revision: int,
                               operator_ack: bool = False) -> SignalSnapshot:
        """Only a validated hypothetical position snapshot can move the signal stop."""
        self._require()
        if operator_ack is not True or type(expected_revision) is not int:
            raise SignalLifecycleRefused("STOP_UPDATE_OPERATOR_REVISION_REQUIRED")
        validate_core_result(manifest,event,result)
        if (decision not in result.decisions or decision.kind is not DecisionKind.MANAGEMENT_INTENT
                or decision.action is not ManagementAction.MOVE_STOP or
                event.event is not CoreEventType.POSITION_UPDATE
                or event.origin not in (DataOrigin.REPLAY,DataOrigin.SYNTHETIC)):
            raise SignalLifecycleRefused("VALIDATED_CORE_MOVE_STOP_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row=self._row(key)
            snap=_status_view(row)
            p=event.position
            if (snap.state is not SignalState.ACTIVE or snap.revision != expected_revision
                    or event.core_id != snap.core_id or
                    event.binding.instance_id != snap.instance_id or
                    event.binding.binding_id != snap.binding_id or
                    event.binding.instrument != snap.instrument or
                    event.source_ref != row["source_ref"] or
                    decision.setup_id != snap.setup_id or
                    p is None or p.position_id != key or p.setup_id != snap.setup_id or
                    p.direction != snap.direction or p.entry != snap.entry or
                    p.initial_stop != snap.initial_stop or p.current_stop != snap.stop or
                    p.revision != expected_revision or
                    event.observed_at <= snap.last_seen_at):
                raise SignalLifecycleRefused("SIGNAL_CORE_POSITION_IDENTITY_OR_REVISION_MISMATCH")
            next_stop=_positive(decision.new_stop,"NEXT_STOP")
            if (snap.direction is Direction.LONG and next_stop <= snap.stop or
                    snap.direction is Direction.SHORT and next_stop >= snap.stop):
                raise SignalLifecycleRefused("STOP_MUST_TIGHTEN")
            self._db.execute("UPDATE offline_signal_states SET current_stop=?,revision=?,"
                             "last_observed_at=? WHERE signal_key=?",
                             (str(next_stop),snap.revision+1,event.observed_at.isoformat(),key))
            self._event(key,snap.revision+1,"CORE_STOP_TIGHTENED",
                {"decision_id":decision.decision_id,"new_stop":str(next_stop),
                 "event":event.input_digest})
            self._outbox(key,snap.revision+1,"EDIT")
            self._db.execute("COMMIT")
            return self.snapshot(key)
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def commands(self, key: str) -> tuple[DryRunCommand, ...]:
        self._row(key)
        rows=self._db.execute("SELECT * FROM offline_signal_commands WHERE signal_key=? "
                              "ORDER BY revision",(key,))
        return tuple(DryRunCommand(r["signal_key"],r["revision"],r["command"],
                r["channel_id"],r["text"],r["message_id"],OutboxState(r["state"])) for r in rows)

    def claim_dry_run(self, key: str, *, operator_ack: bool = False) -> DryRunCommand | None:
        """Claim next eligible preview operation; never invokes a transport."""
        self._require()
        if operator_ack is not True:
            raise SignalLifecycleRefused("DRY_RUN_OPERATOR_ACK_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row=self._row(key)
            command=self._db.execute("SELECT * FROM offline_signal_commands WHERE "
                "signal_key=? AND state='PENDING' ORDER BY revision LIMIT 1",(key,)).fetchone()
            if command is None:
                self._db.execute("COMMIT")
                return None
            older=self._db.execute("SELECT count(*) AS n FROM offline_signal_commands "
                "WHERE signal_key=? AND revision<? AND state!='SIMULATED_ACK'",
                (key,command["revision"])).fetchone()["n"]
            if older:
                self._db.execute("COMMIT")
                return None
            if command["command"] == "EDIT" and row["message_id"] is None:
                self._db.execute("COMMIT")
                return None
            self._db.execute("UPDATE offline_signal_commands SET state='CLAIMED',message_id=? "
                "WHERE signal_key=? AND revision=?",
                (row["message_id"],key,command["revision"]))
            self._db.execute("COMMIT")
            return self.commands(key)[command["revision"]-1]
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def acknowledge_dry_run(self, key: str, revision: int, *,
                            fake_message_id: int, operator_ack: bool = False,
                            reconciled_unknown: bool = False) -> DryRunCommand:
        """LOCAL fake receipt, never proves Telegram accepted a message."""
        self._require()
        if (operator_ack is not True or type(revision) is not int or revision <= 0
                or type(fake_message_id) is not int or fake_message_id <= 0):
            raise SignalLifecycleRefused("SIMULATED_ACK_INPUT_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row=self._row(key)
            pending=self._db.execute("SELECT * FROM offline_signal_commands WHERE "
                "signal_key=? AND revision=?",(key,revision)).fetchone()
            if (pending is None or pending["state"] not in
                    (("CLAIMED","UNKNOWN") if reconciled_unknown else ("CLAIMED",))):
                raise SignalLifecycleRefused("NO_SIMULATED_INFLIGHT_COMMAND")
            if pending["command"] == "EDIT" and fake_message_id != row["message_id"]:
                raise SignalLifecycleRefused("EDIT_MESSAGE_ID_MISMATCH")
            if pending["command"] == "SEND" and row["message_id"] is not None:
                raise SignalLifecycleRefused("MESSAGE_ALREADY_BOUND")
            self._db.execute("UPDATE offline_signal_commands SET state='SIMULATED_ACK',"
                             "message_id=? WHERE signal_key=? AND revision=?",
                             (fake_message_id,key,revision))
            if pending["command"] == "SEND":
                self._db.execute("UPDATE offline_signal_states SET message_id=? WHERE signal_key=?",
                                 (fake_message_id,key))
            self._db.execute("COMMIT")
            return self.commands(key)[revision-1]
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def quarantine_inflight(self) -> int:
        """Restart: uncertain preview operations stay UNKNOWN, never auto-retried."""
        self._require()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            count=self._db.execute("UPDATE offline_signal_commands SET state='UNKNOWN' "
                                   "WHERE state='CLAIMED'").rowcount
            self._db.execute("COMMIT")
            return count
        except BaseException:
            self._db.execute("ROLLBACK")
            raise


__all__ = ["OfflineSignalLifecycle","SignalLifecycleRefused", "SignalState",
           "SignalSnapshot","DryRunCommand","OutboxState","render_signal"]
