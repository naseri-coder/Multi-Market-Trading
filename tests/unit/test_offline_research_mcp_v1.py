"""MCP dual-era wire/permission tests: synthetic messages and fixture data only."""
from __future__ import annotations

import io
import json
import math
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.offline_research_mcp_v1 import (
    BridgeRefused,
    OfflineMcpSession,
    _parse,
    run_stdio,
)

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "fixture", "version": "1.0"},
}


def modern(method, payload=None, *, request_id=1, meta=None):
    return {
        "jsonrpc": "2.0", "id": request_id, "method": method,
        "params": {"_meta": META if meta is None else meta, **(payload or {})},
    }


def legacy(method, params=None, *, request_id=1):
    return {
        "jsonrpc": "2.0", "id": request_id, "method": method,
        "params": {} if params is None else params,
    }


def open_legacy():
    server = OfflineMcpSession()
    result = server.handle(legacy("initialize", {
        "protocolVersion": "2025-11-25",
        "clientInfo": {"name": "fixture", "version": "1"},
        "capabilities": {},
    }))
    assert result["result"]["protocolVersion"] == "2025-11-25"
    assert server.handle({
        "jsonrpc": "2.0", "method": "notifications/initialized",
    }) is None
    return server


def decoded(server, name, args, *, modern_era=True):
    params = {"name": name, "arguments": args}
    response = server.handle(
        modern("tools/call", params) if modern_era
        else legacy("tools/call", params)
    )
    result = response["result"]
    return result["isError"], json.loads(result["content"][0]["text"])


def fixture():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candidates = ["alpha", "beta", "delta", "gamma"]
    rows = []
    for i in range(64):
        sample = {
            "alpha": ((i * 7 + 3) % 19 - 8) / 1000,
            "beta": ((i * 11 + 5) % 23 - 11) / 1000,
            "delta": ((i * 13 + 8) % 29 - 14) / 1000,
            "gamma": ((i * 17 + 2) % 31 - 15) / 1000,
        }
        rows.append({
            "period_start_utc": (start + timedelta(hours=i)).isoformat(),
            "period_end_utc": (start + timedelta(hours=i + 1)).isoformat(),
            "net_return_fraction": {
                key: format(sample[key], ".3f") for key in candidates
            },
        })
    return {
        "schema_version": 1,
        "study_id": "synthetic_mcp_fixture",
        "candidate_ids": candidates,
        "selected_candidate_id": "alpha",
        "declared_total_trials": len(candidates),
        "trial_inventory_complete": True,
        "cscv_blocks": 4,
        "reserved_holdout_start_utc": (start + timedelta(days=4)).isoformat(),
        "rows": rows,
    }


def test_modern_discover_advertises_only_one_current_revision():
    server = OfflineMcpSession()
    response = server.handle(modern("server/discover"))
    info = response["result"]
    assert info["resultType"] == "complete"
    assert info["supportedVersions"] == ["2026-07-28"]
    assert info["capabilities"] == {"tools": {"listChanged": False}}
    assert info["_meta"]["io.modelcontextprotocol/serverInfo"]["name"].startswith(
        "naseri-markets"
    )
    assert server.era == "modern"


def test_modern_direct_tool_call_without_initial_discover():
    server = OfflineMcpSession()
    is_error, data = decoded(server, "research_capabilities", {})
    assert not is_error
    assert data["scope"] == "OFFLINE_FIXTURE_ONLY"
    assert data["can_place_orders"] is False
    assert data["can_access_credentials"] is False
    assert server.era == "modern"


def test_modern_tool_inventory_is_closed_and_readonly():
    server = OfflineMcpSession()
    response = server.handle(modern("tools/list"))
    tools = response["result"]["tools"]
    assert len(tools) == 4
    assert {v["name"] for v in tools} == {
        "research_capabilities", "diagnose_exchange_failure",
        "normalize_order_status", "audit_overfit_fixture",
    }
    for tool in tools:
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False
        assert tool["annotations"]["openWorldHint"] is False
        assert tool["inputSchema"]["additionalProperties"] is False


def test_legacy_initialization_and_notification_gate():
    server = OfflineMcpSession()
    request = legacy("initialize", {
        "protocolVersion": "2025-11-25", "clientInfo": {
            "name": "local-fixture", "version": "1",
        }, "capabilities": {},
    })
    reply = server.handle(request)
    assert reply["result"]["protocolVersion"] == "2025-11-25"
    assert server.handle(legacy("tools/list"))["error"]["code"] == -32000
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert len(server.handle(legacy("tools/list"))["result"]["tools"]) == 4
    error, answer = decoded(server, "research_capabilities", {}, modern_era=False)
    assert not error and not answer["can_access_database"]


def test_legacy_cannot_upgrade_without_a_new_connection():
    server = open_legacy()
    assert server.handle(modern("server/discover"))["error"]["code"] == -32601
    assert server.era == "legacy"


def test_modern_discovery_does_not_fall_back_to_legacy():
    server = OfflineMcpSession()
    server.handle(modern("server/discover"))
    assert server.handle(legacy("initialize", {
        "protocolVersion": "2025-11-25", "clientInfo": {}, "capabilities": {},
    }))["error"]["code"] == -32600


@pytest.mark.parametrize("version", ["2025-06-18", "2030-01-01", "", 42, None])
def test_unsupported_modern_versions_fail_with_supported_revision(version):
    server = OfflineMcpSession()
    metadata = dict(META)
    metadata["io.modelcontextprotocol/protocolVersion"] = version
    response = server.handle(modern("server/discover", meta=metadata))
    assert response["error"]["code"] == -32022
    assert response["error"]["data"]["supported"] == ["2026-07-28"]
    assert server.era == "new"


def test_unknown_or_unsupported_legacy_version_does_not_activate():
    server = OfflineMcpSession()
    reply = server.handle(legacy("initialize", {
        "protocolVersion": "2026-07-28", "clientInfo": {},
        "capabilities": {},
    }))
    assert reply["error"]["code"] == -32022
    assert server.era == "new"


@pytest.mark.parametrize("invalid", [
    {"jsonrpc": "1.0", "method": "ping", "id": 1},
    {"jsonrpc": "2.0", "method": "ping", "id": True},
    {"jsonrpc": "2.0", "method": "ping", "id": None},
    {"jsonrpc": "2.0", "method": "ping", "id": 1.5},
    {"jsonrpc": "2.0", "method": [], "id": 1},
    ["not an rpc"],
    {},
])
def test_invalid_rpc_envelope_refuses_without_echo(invalid):
    reply = OfflineMcpSession().handle(invalid)
    assert reply["error"]["code"] == -32600
    assert reply["id"] is None


@pytest.mark.parametrize("method", [
    "resources/list", "resources/read", "prompts/list", "completion/complete",
    "sampling/createMessage", "execute", "orders/place", "accounts/list",
])
def test_no_files_credentials_or_execution_methods(method):
    server = OfflineMcpSession()
    reply = server.handle(modern(method))
    assert reply["error"]["code"] == -32601


@pytest.mark.parametrize("unsafe", [
    {"name": "run_shell", "arguments": {}},
    {"name": "read_file", "arguments": {"path": "/etc/passwd"}},
    {"name": "diagnose_exchange_failure", "arguments": {
        "venue": "binance", "file_path": "/secrets/api.key",
    }},
    {"name": "normalize_order_status", "arguments": {
        "venue": "binance", "native_status": "NEW", "execute": True,
    }},
])
def test_unlisted_and_extra_arguments_cannot_expand_permissions(unsafe):
    reply = OfflineMcpSession().handle(modern("tools/call", unsafe))
    if "error" in reply:
        assert reply["error"]["code"] == -32602
    else:
        assert reply["result"]["isError"] is True


def test_exchange_error_tool_redacts_raw_secret_and_preserves_uncertainty():
    server = OfflineMcpSession()
    secret = "MCP_SECRET_VALUE_DO_NOT_REFLECT"
    failure, info = decoded(server, "diagnose_exchange_failure", {
        "venue": "binance", "http_status": 503,
        "message": "authentication key=" + secret,
    })
    assert not failure
    assert info["category"] == "transport_unknown"
    assert info["operator_review"] == "reconcile_before_any_retry"
    assert not info["retry_authorized"]
    assert secret not in json.dumps(info)


def test_invalid_error_payload_returns_bounded_generic_tool_failure():
    server = OfflineMcpSession()
    secret = "PROVIDER_PRIVATE_CREDENTIAL"
    error, value = decoded(server, "diagnose_exchange_failure", {
        "venue": "binance", "message": secret * 50,
    })
    assert error is True
    assert value["status"] == "REFUSED"
    assert secret not in json.dumps(value)


@pytest.mark.parametrize(("venue", "native", "expected"), [
    ("binance", "PARTIALLY_FILLED", "PARTIALLY_FILLED"),
    ("okx", "live", "ACKNOWLEDGED"),
    ("bybit", "Filled", "FILLED"),
    ("bitget", "unrecognized", "unknown"),
])
def test_native_status_mapping_never_books_a_fill(venue, native, expected):
    server = OfflineMcpSession()
    invalid, report = decoded(server, "normalize_order_status", {
        "venue": venue, "native_status": native,
    })
    assert not invalid
    assert report["normalized_status"] == expected
    assert not report["fill_booked"]
    assert not report["execution_authorized"]
    assert report["requires_reconciliation"] == (expected == "unknown")


def test_offline_pbo_dsr_matrix_tool_without_holdout_access():
    server = OfflineMcpSession()
    invalid, analysis = decoded(server, "audit_overfit_fixture", {
        "matrix_json": json.dumps(fixture(), separators=(",", ":")),
    })
    assert not invalid
    assert analysis["candidate_count"] == 4
    assert analysis["period_count"] == 64
    assert analysis["holdout_rows_loaded"] == 0
    assert analysis["pbo"]["split_count"] == math.comb(4, 2)
    assert 0 <= analysis["dsr"]["dsr_probability"] <= 1
    assert not analysis["trading_authorized"]
    assert not analysis["source_authenticated"]


def test_overfit_tool_rejects_large_or_unregistered_matrix():
    server = OfflineMcpSession()
    for matrix in ("{}",
                   '{"cscv_blocks":12,"candidate_ids":[],"rows":[]}',
                   "x" * 80001):
        error, report = decoded(server, "audit_overfit_fixture", {
            "matrix_json": matrix,
        })
        assert error is True
        assert report["reason"] == "INVALID_OR_UNTRUSTED_EVIDENCE"


def test_modern_missing_meta_does_not_accept_tools():
    server = OfflineMcpSession()
    msg = modern("tools/list", meta={})
    reply = server.handle(msg)
    assert reply["error"]["code"] == -32022
    assert server.era == "new"


def test_json_duplicate_fields_and_nonfinite_constants_refused():
    for payload in (
        b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}',
        b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}',
        b"\xff",
    ):
        with pytest.raises(BridgeRefused):
            _parse(payload)


def test_empty_unauthorized_server_is_silent_and_no_output():
    incoming = io.BytesIO(
        (json.dumps(modern("tools/list")) + "\n").encode("utf-8")
    )
    outgoing = io.BytesIO()
    assert run_stdio(incoming, outgoing, approved=False) == 2
    assert outgoing.getvalue() == b""


def test_stdio_multi_frame_exchange_and_notifications_are_silent():
    init = legacy("initialize", {
        "protocolVersion": "2025-11-25",
        "clientInfo": {"name": "test", "version": "1"},
        "capabilities": {},
    })
    frames = [
        init,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        legacy("tools/list", request_id=2),
        legacy("tools/call", {"name": "research_capabilities", "arguments": {}},
               request_id=3),
    ]
    incoming = io.BytesIO(
        b"".join(json.dumps(m).encode() + b"\n" for m in frames)
    )
    outgoing = io.BytesIO()
    assert run_stdio(incoming, outgoing, approved=True) == 0
    lines = [json.loads(t) for t in outgoing.getvalue().splitlines()]
    assert [t["id"] for t in lines] == [1, 2, 3]
    assert "tools" in lines[1]["result"]
    assert lines[-1]["result"]["isError"] is False


def test_oversize_frame_is_drained_and_next_frame_processed():
    incoming = io.BytesIO(
        b"x" * 120000 + b"\n" + json.dumps(modern("tools/list")).encode() + b"\n"
    )
    outgoing = io.BytesIO()
    assert run_stdio(incoming, outgoing, approved=True) == 0
    lines = [json.loads(t) for t in outgoing.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert len(lines[1]["result"]["tools"]) == 4


def test_cli_requires_explicit_ack_and_never_leaks_json_on_stdout():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.mmt_offline_mcp_v1"],
        input=(json.dumps(modern("tools/list")) + "\n").encode(),
        capture_output=True, timeout=10, check=False,
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"EXPLICIT_ACK_REQUIRED" in result.stderr


def test_cli_explicit_ack_responds_with_only_json_lines():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.mmt_offline_mcp_v1",
         "--ack-offline-research"],
        input=(json.dumps(modern("server/discover")) + "\n").encode(),
        capture_output=True, timeout=10, check=False,
    )
    assert result.returncode == 0
    assert not result.stderr
    messages = result.stdout.splitlines()
    assert len(messages) == 1
    assert json.loads(messages[0])["result"]["supportedVersions"] == ["2026-07-28"]
