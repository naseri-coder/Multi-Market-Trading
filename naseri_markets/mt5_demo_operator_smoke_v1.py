"""Stage 9: nonproduction MT5 DEMO operator-only read-only smoke acceptance.

Nothing in this module starts MT5, logs in, sends orders, touches PAPER
or evidence custody. Provider is injected and MUST be initialized only by
an explicitly consenting operator-controlled entrypoint. All output is
redacted of login, server, symbol, tickets, prices and balances.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .mt5_demo_evidence_custody_v1 import _margin_mode
from .mt5_demo_history_readonly_v1 import MT5DemoHistoryReaderV1
from .mt5_demo_readonly_adapter_v1 import (
    DemoAccountExpectation,
    MT5DemoReadOnlyAdapterV1,
)

# Minimum SDK operations required by Stages 5-9. Do not introspect any
# trading method and do not grant broker execution authority.
_REQUIRED_READ_CALLS = (
    "terminal_info", "account_info", "positions_get", "orders_get",
    "history_orders_get", "history_deals_get",
    "history_orders_total", "history_deals_total",
)
_REQUIRED_SESSION_CALLS = ("initialize", "shutdown")
_REQUIRED_CONSTANTS = (
    "ACCOUNT_TRADE_MODE_DEMO",
    "ACCOUNT_MARGIN_MODE_RETAIL_NETTING",
    "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING",
)


class MT5DemoSmokeRefused(ValueError):
    """Unverified provider, DEMO identity or nonproduction time window."""


def sdk_contract_preflight(provider: Any, *, need_session: bool = True) -> dict[str, Any]:
    """Read-only introspection; never invokes MT5.initialize or account_info."""
    missing = sorted(
        name for name in (
            _REQUIRED_READ_CALLS
            + (_REQUIRED_SESSION_CALLS if need_session else ())
        )
        if not callable(getattr(provider, name, None))
    )
    invalid = sorted(
        name for name in _REQUIRED_CONSTANTS
        if type(getattr(provider, name, None)) is not int
    )
    demo = getattr(provider, "ACCOUNT_TRADE_MODE_DEMO", None)
    hedge = getattr(provider, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", None)
    netting = getattr(provider, "ACCOUNT_MARGIN_MODE_RETAIL_NETTING", None)
    if hedge is not None and netting is not None and hedge == netting:
        invalid.append("DISTINCT_HEDGING_NETTING_CONSTANTS")
    if missing or invalid:
        # Deliberately do not reveal provider internals or account metadata.
        raise MT5DemoSmokeRefused(
            "SDK_READ_CONTRACT_MISSING_OR_INVALID:"
            + ",".join(missing + invalid)
        )
    if type(demo) is not int:
        raise MT5DemoSmokeRefused("SDK_DEMO_TRADE_MODE_UNKNOWN")
    return {
        "mode": "MT5_READONLY_SDK_CONTRACT_CHECK",
        "read_methods_verified": len(_REQUIRED_READ_CALLS),
        "session_functions_present": need_session,
        "demo_mode_constant_present": True,
        "account_mode_constants_distinct": True,
        "terminal_connected": False,
        "sdk_version": None,  # Never claim a package version without a live SDK report.
        "order_execution_authorized": False,
        "live_demo_compatibility_verified": False,
    }


def _utc(value: datetime, label: str) -> datetime:
    if (
        not isinstance(value, datetime) or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise MT5DemoSmokeRefused(f"{label}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def preflight_window(
    start: datetime, end: datetime, *, now: datetime | None = None,
) -> tuple[datetime, datetime]:
    first, last = _utc(start, "START"), _utc(end, "END")
    clock = _utc(now or datetime.now(UTC), "CLOCK")
    if first >= last or last - first > timedelta(days=1):
        raise MT5DemoSmokeRefused("HISTORY_WINDOW_MUST_BE_0_TO_24_HOURS")
    if last > clock:
        raise MT5DemoSmokeRefused("HISTORY_END_IN_THE_FUTURE")
    return first, last


def observe_demo_smoke(
    provider: Any, expected: DemoAccountExpectation,
    start: datetime, end: datetime, *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Capture active/history/active with no persistence and no trade calls.

    PASS means broker API *read compatibility observed* on one DEMO
    terminal only. It never proves all-time history, broker correctness,
    snapshot atomicity, trade safety, margin or live readiness.
    """
    if not isinstance(expected, DemoAccountExpectation):
        raise MT5DemoSmokeRefused("PINNED_DEMO_ACCOUNT_REQUIRED")
    first, last = preflight_window(start, end, now=now)
    sdk_contract_preflight(provider, need_session=False)
    adapter = MT5DemoReadOnlyAdapterV1(provider, expected)
    # The first account read must be a guarded official trade mode check.
    margin_before = _margin_mode(provider, adapter)
    active_before = adapter.capture(observed_at=last)
    history = MT5DemoHistoryReaderV1(provider, expected).capture(
        first, last, captured_at=last,
    )
    active_after = adapter.capture(observed_at=last)
    margin_after = _margin_mode(provider, adapter)
    if margin_before != margin_after:
        raise MT5DemoSmokeRefused("ACCOUNT_MARGIN_MODE_DRIFT")
    changed = (
        active_before.positions != active_after.positions
        or active_before.pending_orders != active_after.pending_orders
    )
    # A zero-filled fresh DEMO account cannot exercise the historical
    # deal schema, even though history APIs returned valid empty tuples.
    if changed:
        status = "INCONCLUSIVE_ACTIVE_EXPOSURE_CHANGED"
    elif not history.orders or not history.deals:
        status = "INCONCLUSIVE_NO_MATCHED_HISTORY_ACTIVITY"
    else:
        status = "PASS_DEMO_READONLY_API_OBSERVATION"
    return {
        "mode": "MT5_DEMO_READONLY_SMOKE_OBSERVATION",
        "status": status,
        "account_trade_mode": "DEMO",
        "account_margin_mode": margin_after,
        "window_start_utc": first.isoformat(),
        "window_end_utc": last.isoformat(),
        "observed_positions": len(active_after.positions),
        "observed_pending_orders": len(active_after.pending_orders),
        "historical_order_count": len(history.orders),
        "historical_deal_count": len(history.deals),
        "checked_slices": history.slices,
        "history_content_sha256": history.digest,
        "active_exposure_stable_during_scan": not changed,
        "window_endpoint_counts_consistent": True,
        "all_time_history_proven": False,
        "broker_authenticated": False,
        "atomic_account_snapshot": False,
        "may_release_paper_risk": False,
        "may_unlock_stage4": False,
        "may_execute_orders": False,
        "may_publish_signals": False,
        "production_ready": False,
        "sensitive_broker_records_in_output": False,
    }
