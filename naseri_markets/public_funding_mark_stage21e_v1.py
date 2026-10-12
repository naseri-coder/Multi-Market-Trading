"""Stage 21E: bounded KuCoin public funding + *current* mark evidence.

No real execution, no signed exchange attestation, no authentic historical
mark series and no platform liquidation threshold. Funding is a retrospective
entry-notional scenario only, never a Stage9 realized accounting adjustment.
"""
from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from .kucoin_futures_replay_stage21_v1 import (
    SYMBOL, VenueReplayRefused, _public_get,
)
from .public_forward_capture_stage21c_v1 import (
    _gate, _json, _read_private, _sha, _utc, _write_new,
    verify_capture_bundle,
)

FUNDING_ENDPOINT = "https://api-futures.kucoin.com/api/v1/contract/funding-rates"
MARK_ENDPOINT_BASE = "https://api-futures.kucoin.com/api/v1/mark-price/"
MAX_PUBLIC_BYTES = 256 * 1024


class FundingMarkRefused(ValueError):
    """Public market-data research refused, not a PAPER safety approval."""


def _not_finite(_name: str) -> None:
    raise FundingMarkRefused("NONFINITE_RESPONSE_NUMBER")


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise FundingMarkRefused("DUPLICATE_MARKET_DATA_KEY")
        result[name] = value
    return result


def _body(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_PUBLIC_BYTES:
        raise FundingMarkRefused("BOUNDED_PUBLIC_RESPONSE_REQUIRED")
    try:
        data = json.loads(raw.decode("utf-8"), parse_float=Decimal,
                          parse_constant=_not_finite, object_pairs_hook=_pairs)
    except FundingMarkRefused:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FundingMarkRefused("INVALID_PUBLIC_RESPONSE_JSON") from exc
    if type(data) is not dict or data.get("code") != "200000":
        raise FundingMarkRefused("PUBLIC_RESPONSE_NOT_SUCCESS")
    return data


def _number(value: object, *, signed: bool = False) -> Decimal:
    if type(value) not in (str, int, Decimal) or type(value) is bool:
        raise FundingMarkRefused("UNSUPPORTED_PUBLIC_NUMBER")
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise FundingMarkRefused("INVALID_PUBLIC_DECIMAL") from exc
    if not d.is_finite() or (not signed and d <= 0):
        raise FundingMarkRefused("NONFINITE_OR_NONPOSITIVE_PUBLIC_NUMBER")
    return d


def _time(ms: object) -> datetime:
    if type(ms) is not int or ms < 0 or ms > 32503680000000:
        raise FundingMarkRefused("INVALID_PUBLIC_TIMESTAMP")
    try:
        return datetime.fromtimestamp(ms / 1000, tz=UTC)
    except (OverflowError, ValueError, OSError) as exc:
        raise FundingMarkRefused("INVALID_PUBLIC_TIMESTAMP") from exc


def _ms(value: datetime) -> int:
    value = _utc(value)
    if value.microsecond % 1000:
        raise FundingMarkRefused("MILLISECOND_ALIGNED_CLOCK_REQUIRED")
    return int(value.timestamp() * 1000)


@dataclass(frozen=True, slots=True)
class FundingRequest:
    symbol: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or not SYMBOL.fullmatch(self.symbol):
            raise FundingMarkRefused("NATIVE_KUCOIN_FUTURES_SYMBOL_REQUIRED")
        start, end = _utc(self.start), _utc(self.end)
        if not timedelta(0) < end - start <= timedelta(hours=24):
            raise FundingMarkRefused("BOUNDED_FUNDING_WINDOW_REQUIRED")
        _ms(start)
        _ms(end)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def url(self) -> str:
        return FUNDING_ENDPOINT + "?" + urllib.parse.urlencode({
            "symbol": self.symbol, "from": _ms(self.start), "to": _ms(self.end)})


@dataclass(frozen=True, slots=True)
class FundingSettlement:
    symbol: str
    settled_at: datetime
    rate: Decimal


@dataclass(frozen=True, slots=True)
class CurrentMark:
    symbol: str
    observed_for: datetime
    value: Decimal
    index_price: Decimal


def parse_funding_history(raw: bytes, req: FundingRequest) -> tuple[FundingSettlement, ...]:
    body = _body(raw)
    rows = body.get("data")
    if type(rows) is not list or len(rows) > 128:
        raise FundingMarkRefused("BOUNDED_FUNDING_ROWS_REQUIRED")
    settlements = []
    stamps = set()
    for row in rows:
        if type(row) is not dict or row.get("symbol") != req.symbol:
            raise FundingMarkRefused("FUNDING_CONTRACT_MISMATCH")
        stamp = _time(row.get("timepoint"))
        rate = _number(row.get("fundingRate"), signed=True)
        if (stamp in stamps or not req.start < stamp <= req.end
                or abs(rate) > Decimal("0.1")):
            raise FundingMarkRefused("FUNDING_EVENT_RANGE_OR_RATE_INVALID")
        stamps.add(stamp)
        settlements.append(FundingSettlement(req.symbol, stamp, rate))
    settlements.sort(key=lambda row: row.settled_at)
    return tuple(settlements)


def parse_current_mark(raw: bytes, symbol: str, *, observed_at: datetime
                       ) -> CurrentMark:
    body = _body(raw)
    obj = body.get("data")
    if type(obj) is not dict or obj.get("symbol") != symbol:
        raise FundingMarkRefused("MARK_CONTRACT_MISMATCH")
    stamp = _time(obj.get("timePoint"))
    observation = _utc(observed_at)
    if not timedelta(0) <= observation - stamp <= timedelta(seconds=30):
        raise FundingMarkRefused("STALE_OR_FUTURE_MARK_REFUSED")
    value = _number(obj.get("value"))
    index = _number(obj.get("indexPrice"))
    return CurrentMark(symbol, stamp, value, index)


def _read_annex(folder: Path) -> tuple[dict, dict, tuple, tuple, object]:
    """Offline verified Stage21C + 21E bytes; never trusts a caller's hash label."""
    record, datasets, metadata = verify_capture_bundle(folder)
    manifest = json.loads(_read_private(folder / "stage21e.json", 8192))
    if (type(manifest) is not dict or manifest.get("version") != 1
            or manifest.get("sealed_stage21c_sha256") != _sha(
                _read_private(folder / "sealed.json", 8192))
            or manifest.get("metadata_sha256") != record["contracts_sha256"]
            or manifest.get("capture_mode") != record["capture_mode"]
            or type(manifest.get("sources")) is not list
            or len(manifest["sources"]) != 2):
        raise FundingMarkRefused("ANNEX_CAPTURE_BINDING_DRIFT")
    funding, marks = [], []
    for i, (query, _bytes) in enumerate(datasets):
        row = manifest["sources"][i]
        f_raw = _read_private(folder / f"stage21e_funding_{i}.json", MAX_PUBLIC_BYTES)
        m_raw = _read_private(folder / f"stage21e_mark_{i}.json", MAX_PUBLIC_BYTES)
        if (row.get("symbol") != query.symbol
                or row.get("funding_sha256") != _sha(f_raw)
                or row.get("mark_sha256") != _sha(m_raw)
                or row.get("funding_start") != query.start.isoformat()
                or row.get("funding_end") != query.end.isoformat()):
            raise FundingMarkRefused("ANNEX_RAW_EVIDENCE_TAMPERED")
        req = FundingRequest(query.symbol, query.start, query.end)
        funding.append(parse_funding_history(f_raw, req))
        marks.append(parse_current_mark(
            m_raw, query.symbol, observed_at=datetime.fromisoformat(
                row["mark_received_at"])))
    return record, manifest, tuple(funding), tuple(marks), metadata


def capture_public_funding_and_mark(
    folder: Path, *, operator_ack: bool = False,
    transport: Callable[[str], bytes] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    """Exactly 4 bounded public GETs, on one separate operator invocation.

    No automatic poll/retry or exchange credential. Partial file writes require
    manual reconciliation; repeat invocations must refuse.
    """
    _gate(operator_ack)
    record, datasets, _meta = verify_capture_bundle(folder)
    if any((folder / x).exists() for x in (
            "stage21e.json", "stage21e_funding_0.json",
            "stage21e_funding_1.json", "stage21e_mark_0.json",
            "stage21e_mark_1.json")):
        raise FundingMarkRefused("ANNEX_EXISTS_OR_PARTIAL_WRITES")
    if transport is not None and not callable(transport):
        raise FundingMarkRefused("INVALID_PUBLIC_RESEARCH_TRANSPORT")
    if (record["capture_mode"] == "INJECTED_TEST_TRANSPORT") != (transport is not None):
        raise FundingMarkRefused("MIXED_SOURCE_PROVENANCE_REFUSED")
    if clock is None:
        clock = lambda: datetime.now(UTC)
    started = _utc(clock())
    if any(query.end > started for query, _raw in datasets):
        raise FundingMarkRefused("FUNDING_NOT_SETTLED_WINDOW")
    responses = []
    for query, _raw in datasets:
        req = FundingRequest(query.symbol, query.start, query.end)
        mark_url = MARK_ENDPOINT_BASE + query.symbol + "/current"
        try:
            funding_raw = (_public_get(req.url) if transport is None
                           else transport(req.url))
            mark_raw = (_public_get(mark_url) if transport is None
                        else transport(mark_url))
        except (OSError, ValueError, VenueReplayRefused) as exc:
            raise FundingMarkRefused("PUBLIC_MARK_OR_FUNDING_UNAVAILABLE") from exc
        received = _utc(clock())
        if not timedelta(0) <= received - started <= timedelta(minutes=2):
            raise FundingMarkRefused("RESEARCH_CLOCK_JUMP_OR_OVERRUN")
        fund = parse_funding_history(funding_raw, req)
        mark = parse_current_mark(mark_raw, query.symbol, observed_at=received)
        responses.append((query, funding_raw, mark_raw, received, fund, mark))
    # Validate both instruments before any persistent write.
    for i, (_q, f_raw, m_raw, _t, _fund, _mark) in enumerate(responses):
        _write_new(folder / f"stage21e_funding_{i}.json", f_raw)
        _write_new(folder / f"stage21e_mark_{i}.json", m_raw)
    annex = {
        "version": 1, "metadata_sha256": record["contracts_sha256"],
        "sealed_stage21c_sha256": _sha(_read_private(folder / "sealed.json", 8192)),
        "capture_mode": record["capture_mode"],
        "sources": [
            {"symbol": q.symbol, "funding_start": q.start.isoformat(),
             "funding_end": q.end.isoformat(), "funding_sha256": _sha(f_raw),
             "mark_sha256": _sha(m_raw), "mark_received_at": received.isoformat(),
             "settlements_returned": len(fund),
             "snapshot_at": mark.observed_for.isoformat()}
            for q, f_raw, m_raw, received, fund, mark in responses
        ],
        "funding_event_completeness_verified": False,
        "historic_mark_series_available": False,
        "exchange_attestation": False,
        "broker_order_sent": False, "telegram_sent": False,
    }
    _write_new(folder / "stage21e.json", _json(annex))
    return {
        "status": "PUBLIC_MARK_AND_FUNDING_ANNEX_CAPTURED_UNATTESTED",
        "source_labels": annex["sources"],
        "funding_event_completeness_verified": False,
        "historic_mark_series_available": False,
        "broker_order_sent": False, "telegram_sent": False,
    }


def analyze_funding_and_mark(
    folder: Path, *, operator_ack: bool = False,
    mark_dislocation_limit: Decimal = Decimal("0.02"),
    hypothetical_leverage: Decimal = Decimal("5"),
    hypothetical_mmr: Decimal = Decimal("0.01"),
    paper_path: Path | None = None,
) -> dict:
    """Read-only *scenario*, never post-hoc modification of stored PAPER PnL.

    Mark is current after capture, NOT a historical mark for candle bars.
    This makes actual liquidation and historical margin assessment UNKNOWN.
    """
    _gate(operator_ack)
    for d, name in ((mark_dislocation_limit, "BASIS"),
                    (hypothetical_leverage, "LEVERAGE"),
                    (hypothetical_mmr, "MMR")):
        if type(d) is not Decimal or not d.is_finite() or d <= 0:
            raise FundingMarkRefused("EXPLICIT_POSITIVE_" + name)
    if (mark_dislocation_limit > Decimal("0.5")
            or hypothetical_leverage > Decimal(50)
            or hypothetical_mmr >= Decimal("0.5")):
        raise FundingMarkRefused("UNSUPPORTED_STRESS_ASSUMPTION")
    record, manifest, funding, marks, _metadata = _read_annex(folder)
    from .public_forward_capture_stage21c_v1 import PublicContractGeometry
    from .paper_contract_economics_stage21d_v1 import PaperContractEconomics
    origin = ("INJECTED_TEST_CONTRACT_FIXTURE" if
              record["capture_mode"] == "INJECTED_TEST_TRANSPORT"
              else "PUBLIC_CONTRACT_SNAPSHOT_UNATTESTED")
    econ = tuple(PaperContractEconomics.from_public(
        PublicContractGeometry(**item), metadata_sha256=record["contracts_sha256"],
        origin=origin) for item in record["contract_geometry"])
    per_symbol = []
    for i, mark in enumerate(marks):
        basis = (mark.value - mark.index_price) / mark.index_price
        alerts = ["MARK_INDEX_DISLOCATION"] if abs(basis) > mark_dislocation_limit else []
        # 1-contract illustrative margin buffer; actual maintenance tiers and
        # account equity are UNKNOWN. This is NOT a liquidation price.
        policy = econ[i]
        notional = policy.notional(policy.quantity_step, mark.value)
        margin = notional / hypothetical_leverage
        maintenance = notional * (hypothetical_mmr + policy.taker_fee_fraction)
        headroom = margin - maintenance
        if headroom <= 0:
            alerts.append("HYPOTHETICAL_MAINTENANCE_BUFFER_NONPOSITIVE")
        per_symbol.append({
            "symbol": mark.symbol, "current_mark": str(mark.value),
            "current_index": str(mark.index_price),
            "mark_index_basis": str(basis), "mark_time": mark.observed_for.isoformat(),
            "funding_settlements": [
                {"at": e.settled_at.isoformat(), "rate": str(e.rate)}
                for e in funding[i]],
            "funding_history_completeness": "UNATTESTED",
            "hypothetical_contracts": str(policy.quantity_step),
            "hypothetical_mark_notional": str(notional),
            "hypothetical_isolated_margin": str(margin),
            "hypothetical_maintenance_plus_close_fee": str(maintenance),
            "hypothetical_buffer": str(headroom),
            "alerts": alerts,
            "liquidation_price": None,
            "historical_mark_risk": "NOT_ASSESSED_NO_HISTORICAL_MARK_SERIES",
        })
    funding_scenario = None
    if paper_path is not None:
        from .paper_funding_scenario_stage21e_v1 import estimate_ledger_funding
        funding_scenario = estimate_ledger_funding(
            paper_path, policies=econ, settlements=funding)
    return {
        "stage": "21E", "mode": "READONLY_PUBLIC_FUNDING_MARK_RESEARCH",
        "paper_funding_scenario": funding_scenario,
        "capture_mode": manifest["capture_mode"],
        "items": per_symbol,
        "current_snapshot_is_historical_price": False,
        "funding_history_complete": False,
        "historical_margin_backtest_credible": False,
        "funding_applied_to_stage9_pnl": False,
        "liquidation_price_verified": False,
        "profitability_proven": False, "live_trading_authorized": False,
        "broker_order_sent": False, "telegram_sent": False,
    }


__all__ = [
    "FundingMarkRefused", "FundingRequest", "FundingSettlement", "CurrentMark",
    "parse_funding_history", "parse_current_mark",
    "capture_public_funding_and_mark", "analyze_funding_and_mark",
]
