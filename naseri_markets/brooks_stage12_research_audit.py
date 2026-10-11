"""Stage 12: read-only, scope-exhaustive Brooks PAPER cohort verification.

This is a diagnostic study of existing Stage-10/11 evidence, NOT a market
backtest or proof that any sample was obtained from a real broker. No database
writes, source-code changes, execution, publications or thresholds are made.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import quote

from .brooks_paper_receipts import _digest as receipt_digest
from .brooks_replay import SECONDS, _unique
from .brooks_stage10_paper_bridge import STAGE10_FILENAME, _signal
from .brooks_stage11_candle_replay import _sha
from .engine_control_store import BROOKS_ENGINE_ID

MAX_MANIFEST_BYTES = 65536
MAX_LINKS = 5000
MIN_CLOSED_FOR_DESCRIPTIVE_ASSESSMENT = 20


class Stage12ResearchRefused(ValueError):
    """Study refused: wrong scope, missing original evidence or data corruption."""


def _clock(value: object) -> datetime:
    if type(value) is not str or len(value) > 45:
        raise Stage12ResearchRefused("INVALID_UTC_DATETIME")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("not exact UTC")
        return parsed.astimezone(UTC)
    except ValueError as exc:
        raise Stage12ResearchRefused("INVALID_UTC_DATETIME") from exc


def _amount(value: Any, key: str) -> Decimal:
    if type(value) is not str or not 0 < len(value) <= 80:
        raise Stage12ResearchRefused("INVALID_DECIMAL_" + key)
    try:
        num = Decimal(value)
    except InvalidOperation as exc:
        raise Stage12ResearchRefused("INVALID_DECIMAL_" + key) from exc
    if not num.is_finite():
        raise Stage12ResearchRefused("NONFINITE_DECIMAL_" + key)
    return num


def _readonly(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise Stage12ResearchRefused("RESEARCH_EVIDENCE_DATABASE_MISSING")
    uri = "file:" + quote(path.absolute().as_posix(), safe="/:") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("BEGIN")
    return con


def _manifest(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_MANIFEST_BYTES:
        raise Stage12ResearchRefused("STUDY_MANIFEST_BOUNDS")
    try:
        data = json.loads(
            raw, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                Stage12ResearchRefused("STUDY_NONFINITE_JSON")
            ),
        )
    except Stage12ResearchRefused:
        raise
    except (ValueError, UnicodeError) as exc:
        raise Stage12ResearchRefused("STUDY_MANIFEST_JSON_INVALID") from exc
    required = {
        "schema_version", "purpose", "study_id", "account_id",
        "provider", "symbol", "timeframe", "quote_currency",
        "window_start_utc", "training_end_utc", "validation_end_utc",
        "window_end_utc", "expected_signal_ids", "dataset_origin",
        "dataset_sha256", "protocol_frozen_before_outcomes",
    }
    if type(data) is not dict or set(data) != required:
        raise Stage12ResearchRefused("STUDY_MANIFEST_SCHEMA")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise Stage12ResearchRefused("STUDY_MANIFEST_VERSION")
    if data["purpose"] != "offline_paper_cohort_diagnostic":
        raise Stage12ResearchRefused("STUDY_RESEARCH_ONLY")
    if (
        type(data["protocol_frozen_before_outcomes"]) is not bool
        or data["protocol_frozen_before_outcomes"] is not True
    ):
        raise Stage12ResearchRefused("STUDY_PRE_REGISTRATION_NOT_DECLARED")
    if (
        data["dataset_origin"] not in ("synthetic_fixture", "operator_offline_unverified")
        or type(data["dataset_sha256"]) is not str
        or len(data["dataset_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in data["dataset_sha256"])
    ):
        raise Stage12ResearchRefused("UNVERIFIED_DATASET_DECLARATION_REQUIRED")
    for field in ("study_id", "account_id", "provider", "symbol", "quote_currency"):
        value = data[field]
        if (
            type(value) is not str or not 1 <= len(value) <= 96
            or any(not (c.isalnum() and c.isascii() or c in "._:-") for c in value)
        ):
            raise Stage12ResearchRefused("INVALID_STUDY_IDENTITY_" + field)
    if data["timeframe"] not in SECONDS:
        raise Stage12ResearchRefused("UNSUPPORTED_TIMEFRAME")
    starts = [_clock(data[key]) for key in (
        "window_start_utc", "training_end_utc", "validation_end_utc", "window_end_utc",
    )]
    if not starts[0] < starts[1] < starts[2] < starts[3]:
        raise Stage12ResearchRefused("OVERLAPPING_OR_REVERSED_STUDY_PARTITIONS")
    if starts[3]-starts[0] > timedelta(days=400):
        raise Stage12ResearchRefused("STUDY_TIME_HORIZON_EXCEEDS_400_DAYS")
    ids = data["expected_signal_ids"]
    if (
        type(ids) is not list or not 1 <= len(ids) <= MAX_LINKS
        or any(type(x) is not str or not 1 <= len(x) <= 96 for x in ids)
        or len(set(ids)) != len(ids)
    ):
        raise Stage12ResearchRefused("STUDY_SIGNAL_LIST_INVALID")
    return data


def _tables(conn: sqlite3.Connection, names: tuple[str, ...]) -> None:
    available = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if not set(names) <= available:
        raise Stage12ResearchRefused("STUDY_REQUIRED_EVIDENCE_TABLE_MISSING")


def _segment(when: datetime, bounds: list[datetime]) -> str:
    if bounds[0] <= when < bounds[1]:
        return "training"
    if bounds[1] <= when < bounds[2]:
        return "validation"
    if bounds[2] <= when < bounds[3]:
        return "holdout"
    return "outside"


def _metrics(rows: list[dict]) -> dict:
    closed = [r for r in rows if r["outcome"] == "CLOSED_PAPER"]
    r_values = [r["realized_r"] for r in closed]
    gains = [r["net_pnl"] for r in closed if r["net_pnl"] > 0]
    losses = [r["net_pnl"] for r in closed if r["net_pnl"] < 0]
    costs = [r["fees"]+r["slippage"] for r in closed]
    return {
        "linked_signals": len(rows),
        "closed_paper_trades": len(closed),
        "not_closed_or_not_replayed": len(rows)-len(closed),
        "winners": sum(v > 0 for v in r_values),
        "losers": sum(v < 0 for v in r_values),
        "breakeven": sum(v == 0 for v in r_values),
        "win_rate": str(Decimal(sum(v > 0 for v in r_values))/len(r_values))
                    if r_values else None,
        "mean_net_realized_r": str(sum(r_values, Decimal(0))/len(r_values))
                               if r_values else None,
        "median_net_realized_r": str(median(r_values)) if r_values else None,
        "sum_net_pnl": str(sum((r["net_pnl"] for r in closed), Decimal(0))),
        "sum_gross_pnl": str(sum((r["gross_pnl"] for r in closed), Decimal(0))),
        "sum_modeled_costs": str(sum(costs, Decimal(0))),
        "stress_2x_cost_mean_r": str(sum(
            (r["realized_r"]-c/r["risk_notional"]
             for r,c in zip(closed,costs)), Decimal(0),
        )/len(closed)) if closed else None,
        "profit_factor": (
            str(sum(gains, Decimal(0))/-sum(losses, Decimal(0)))
            if losses else None
        ),
    }


def evaluate_brooks_stage12(state_dir: str | Path, manifest_bytes: bytes) -> dict[str, Any]:
    """Never mutate SOURCE, Stage-10/11 destination or a private config file."""
    study = _manifest(manifest_bytes)
    root = Path(state_dir).absolute()
    source = _readonly(root/"custom_paper.db")
    try:
        paper = _readonly(root/STAGE10_FILENAME)
        try:
            _tables(source, ("a7_paper_intents", "brooks_replay_scans", "brooks_paper_receipts"))
            _tables(paper, ("brooks_stage10_links", "paper_orders",
                            "paper_risk_reservations", "paper_order_events"))
            stage11_present = bool(paper.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='brooks_stage11_positions'"
            ).fetchone())
            if stage11_present:
                _tables(paper, ("brooks_stage11_bars",))
            links = paper.execute(
                "SELECT account_id,signal_id,order_id,request_digest,content_json "
                "FROM brooks_stage10_links WHERE account_id=? ORDER BY signal_id",
                (study["account_id"],),
            ).fetchall()
            if len(links) > MAX_LINKS:
                raise Stage12ResearchRefused("STUDY_LINK_COUNT_LIMIT")
            if not links:
                raise Stage12ResearchRefused("STUDY_NO_BROOKS_LINKS_FOR_ACCOUNT")
            expected = set(study["expected_signal_ids"])
            actual = {row["signal_id"] for row in links}
            # Whole risk account is the cohort: filtering out known losers
            # or pending links is not allowed.
            if expected != actual:
                raise Stage12ResearchRefused("STUDY_INCOMPLETE_ACCOUNT_SIGNAL_UNIVERSE")
            bounds = [_clock(study[key]) for key in (
                "window_start_utc", "training_end_utc", "validation_end_utc",
                "window_end_utc",
            )]
            results = []
            for link in links:
                signal_row = source.execute(
                    "SELECT payload,digest FROM a7_paper_intents "
                    "WHERE engine_id=? AND signal_id=?",
                    (BROOKS_ENGINE_ID,link["signal_id"]),
                ).fetchone()
                if signal_row is None:
                    raise Stage12ResearchRefused("STUDY_MISSING_SOURCE_SIGNAL")
                try:
                    signal = _signal(
                        signal_row["payload"], signal_row["digest"], link["signal_id"]
                    )
                except ValueError as exc:
                    raise Stage12ResearchRefused("STUDY_INVALID_SOURCE_SIGNAL") from exc
                if (
                    signal.instrument.provider != study["provider"]
                    or signal.instrument.symbol != study["symbol"]
                    or signal.instrument.quote_currency != study["quote_currency"]
                ):
                    raise Stage12ResearchRefused("STUDY_HETEROGENEOUS_ACCOUNT_INSTRUMENT")
                when = signal.observed_at.astimezone(UTC)
                segment = _segment(when, bounds)
                if segment == "outside":
                    raise Stage12ResearchRefused("STUDY_SIGNAL_OUTSIDE_DECLARED_WINDOW")
                scans = source.execute(
                    "SELECT scan_id FROM brooks_replay_scans WHERE signal_id=?",
                    (link["signal_id"],),
                ).fetchall()
                if len(scans) != 1:
                    raise Stage12ResearchRefused("STUDY_SOURCE_SCAN_NOT_UNIQUE")
                rr = source.execute(
                    "SELECT receipt_json,receipt_sha256 FROM brooks_paper_receipts "
                    "WHERE scan_id=?", (scans[0]["scan_id"],),
                ).fetchone()
                if rr is None or receipt_digest(rr["receipt_json"]) != rr["receipt_sha256"]:
                    raise Stage12ResearchRefused("STUDY_RECEIPT_HASH_FAILURE")
                receipt = json.loads(rr["receipt_json"])
                if (
                    receipt.get("timeframe") != study["timeframe"]
                    or receipt.get("signal_id") != link["signal_id"]
                    or receipt.get("signal_evidence") != "PAPER"
                    or receipt.get("broker_order_authorized") is not False
                    or receipt.get("telegram_delivery_authorized") is not False
                    or receipt.get("closed_candle_time") != signal.observed_at.isoformat()
                ):
                    raise Stage12ResearchRefused("STUDY_SOURCE_RECEIPT_CONFLICT")
                bound = json.loads(link["content_json"])
                if (
                    link["request_digest"] != _sha(bound)
                    or bound.get("signal_digest") != signal_row["digest"]
                    or bound.get("receipt_digest") != rr["receipt_sha256"]
                    or bound.get("account_id") != study["account_id"]
                    or bound.get("signal_id") != link["signal_id"]
                    or bound.get("order_id") != link["order_id"]
                ):
                    raise Stage12ResearchRefused("STUDY_STAGE10_BINDING_CORRUPTED")
                order_row = paper.execute(
                    "SELECT snapshot FROM paper_orders WHERE order_id=?",
                    (link["order_id"],),
                ).fetchone()
                risk_row = paper.execute(
                    "SELECT status,contract_json FROM paper_risk_reservations "
                    "WHERE order_id=?", (link["order_id"],),
                ).fetchone()
                if order_row is None or risk_row is None:
                    raise Stage12ResearchRefused("STUDY_MISSING_STAGE3_ORDER_OR_RISK")
                order = json.loads(order_row["snapshot"])
                spec = order["spec"]
                if (
                    spec != json.loads(risk_row["contract_json"])
                    or order["order_id"] != link["order_id"]
                    or spec["account_id"] != study["account_id"]
                    or spec["signal_id"] != signal.signal_id
                    or spec["engine_id"] != BROOKS_ENGINE_ID
                    or spec["kind"] != "LIMIT" or spec["mode"] != "paper"
                    or spec["reference_entry"] != str(signal.entry)
                    or spec["stop"] != str(signal.stop)
                    or spec["target"] != str(signal.targets[0])
                    or spec["direction"] != signal.direction.value
                ):
                    raise Stage12ResearchRefused("STUDY_STAGE3_ORDER_CONFLICT")
                evidence_row = paper.execute(
                    "SELECT metadata_json,state_sha256 FROM brooks_stage11_positions "
                    "WHERE order_id=?", (link["order_id"],),
                ).fetchone() if stage11_present else None
                if evidence_row is None:
                    if order["status"] != "CREATED" or risk_row["status"] != "ACTIVE":
                        raise Stage12ResearchRefused("STUDY_UNTRACKED_PAPER_LIFECYCLE")
                    results.append({"segment": segment, "when": when,
                                    "outcome": "UNREPLAYED_OR_PENDING"})
                    continue
                meta = json.loads(evidence_row["metadata_json"])
                if evidence_row["state_sha256"] != _sha(order):
                    raise Stage12ResearchRefused("STUDY_PAPER_ORDER_DIGEST_MISMATCH")
                if meta.get("quote_currency") != study["quote_currency"]:
                    raise Stage12ResearchRefused("STUDY_REPLAY_CURRENCY_CONFLICT")
                count = paper.execute(
                    "SELECT COUNT(*),MIN(seq),MAX(seq) FROM brooks_stage11_bars "
                    "WHERE order_id=?", (link["order_id"],),
                ).fetchone()
                if (
                    type(meta.get("bars_committed")) is not int
                    or meta["bars_committed"] <= 0
                    or count[0] != meta["bars_committed"]
                    or count[1] != 1 or count[2] != meta["bars_committed"]
                ):
                    raise Stage12ResearchRefused("STUDY_BAR_JOURNAL_INCOMPLETE")
                if order["status"] != "CLOSED":
                    if risk_row["status"] != "ACTIVE" or meta.get("risk_released") is not False:
                        raise Stage12ResearchRefused("STUDY_OPEN_RISK_INCONSISTENT")
                    results.append({"segment": segment, "when": when,
                                    "outcome": "OPEN_PAPER"})
                    continue
                if risk_row["status"] != "RELEASED" or meta.get("risk_released") is not True:
                    raise Stage12ResearchRefused("STUDY_TERMINAL_RISK_NOT_RELEASED")
                events = [r["event_type"] for r in paper.execute(
                    "SELECT event_type FROM paper_order_events WHERE order_id=? ORDER BY seq",
                    (link["order_id"],),
                )]
                if events != ["CREATE", "SUBMIT", "ACK", "FILL", "CLOSE_FILL"]:
                    raise Stage12ResearchRefused("STUDY_UNEXPECTED_EXECUTION_EVENT_CHAIN")
                gross = _amount(meta.get("gross_pnl"), "GROSS")
                fees = _amount(meta.get("estimated_fees"), "FEES")
                slip = _amount(meta.get("estimated_slippage"), "SLIPPAGE")
                net = _amount(meta.get("net_realized_pnl"), "NET")
                rvalue = _amount(meta.get("realized_r"), "R")
                if fees < 0 or slip < 0 or gross-fees-slip != net:
                    raise Stage12ResearchRefused("STUDY_NET_ACCOUNTING_CONFLICT")
                quantity = _amount(spec["quantity"], "QUANTITY")
                init_risk = abs(Decimal(spec["reference_entry"]) - Decimal(spec["stop"])) * quantity
                # Stage-11 policy multiplier is not carried in the immutable
                # order specification. Check recorded R's implicit multiplier
                # remains strictly positive and agrees with computed gross.
                multiplier = (
                    gross / ((Decimal(meta["exit_price"])-Decimal(meta["entry_price"]))
                             * quantity * (1 if spec["direction"] == "long" else -1))
                    if gross else None
                )
                if (
                    multiplier is None or not multiplier.is_finite() or multiplier <= 0
                    or init_risk <= 0 or net/(init_risk*multiplier) != rvalue
                    or meta.get("entry_time_utc") is None
                    or meta.get("exit_time_utc") is None
                ):
                    raise Stage12ResearchRefused("STUDY_REALIZED_R_RECONCILIATION_FAILED")
                results.append({
                    "segment": segment, "when": when, "outcome": "CLOSED_PAPER",
                    "net_pnl": net, "gross_pnl": gross, "fees": fees,
                    "slippage": slip, "realized_r": rvalue,
                    "risk_notional": init_risk*multiplier,
                })
            ordered = sorted(results, key=lambda r: (r["when"], r["segment"]))
            stats = {seg: _metrics([r for r in ordered if r["segment"] == seg])
                     for seg in ("training", "validation", "holdout")}
            overall = _metrics(ordered)
            total_closed = overall["closed_paper_trades"]
            if overall["not_closed_or_not_replayed"]:
                verdict = "INCOMPLETE_PAPER_OUTCOMES"
            elif total_closed < MIN_CLOSED_FOR_DESCRIPTIVE_ASSESSMENT:
                verdict = "INSUFFICIENT_CLOSED_PAPER_SAMPLES"
            else:
                verdict = "RESEARCH_ONLY_REAL_MARKET_PROVENANCE_UNVERIFIED"
            return {
                "schema_version": 1,
                "study_id": study["study_id"],
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "dataset_origin_claim": study["dataset_origin"],
                "dataset_sha256_claim": study["dataset_sha256"],
                "actual_provider_dataset_verified": False,
                "pre_registration_independently_verified": False,
                "frozen_protocol_claim_only": True,
                "observed_full_signal_universe": False,
                "account_link_universe_complete": True,
                "baseline_brooks_thresholds_changed": False,
                "all_results_synthetic_paper_only": True,
                "time_partition_method": "nonoverlapping_signal_close_utc",
                "quote_currency": study["quote_currency"],
                "overall": overall, "partitions": stats,
                "status": verdict,
                "may_activate_core": False, "may_publish_signal": False,
                "may_execute_broker_order": False,
                "profitability_or_live_edge_proven": False,
            }
        finally:
            paper.close()
    finally:
        source.close()
