"""Bounded MCP stdio research bridge; offline, inert and disabled by default.

Offers a small read-only MCP surface for public research fixtures, never
filesystem reads, plugin source inspection, credentials or real execution.
Protocol support: 2026-07-28 stateless discovery and legacy 2025-11-25.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, BinaryIO

from .exchange_failure_diagnostics_v1 import diagnose_exchange_failure
from .order_observation_normalizer_v1 import (
    ObservationRefused,
    normalize_native_order_status,
)
from .research_overfit_diagnostics_v1 import (
    OverfitEvidenceRefused,
    analyze_overfit_fixture,
)

MODERN = "2026-07-28"
LEGACY = "2025-11-25"
_NAME = "naseri-markets-offline-research"
_MAX_LINE_BYTES = 100_000
_MAX_MATRIX_BYTES = 80_000
_MAX_MATRIX_PERIODS = 128
_MAX_MATRIX_TRIALS = 8

_TOOL_SPEC = (
    {
        "name": "research_capabilities",
        "description": "List safe offline research tools and explicit nonproduction limits.",
        "inputSchema": {
            "type": "object", "properties": {}, "additionalProperties": False,
        },
    },
    {
        "name": "diagnose_exchange_failure",
        "description": (
            "Classify operator-supplied exchange error evidence, no raw echo and "
            "never permission to retry, place or cancel an order."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "venue": {"type": "string", "maxLength": 32},
                "http_status": {"type": "integer", "minimum": 100, "maximum": 599},
                "exchange_code": {"type": "string", "maxLength": 10},
                "message": {"type": "string", "maxLength": 256},
            },
            "required": ["venue"],
            "additionalProperties": False,
        },
    },
    {
        "name": "normalize_order_status",
        "description": (
            "Translate a small allowlisted vendor order-state token to the "
            "existing internal enum; unknown tokens require reconciliation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "venue": {"type": "string", "enum": [
                    "binance", "okx", "bybit", "bitget",
                ]},
                "native_status": {"type": "string", "maxLength": 48},
            },
            "required": ["venue", "native_status"],
            "additionalProperties": False,
        },
    },
    {
        "name": "audit_overfit_fixture",
        "description": (
            "Evaluate a bounded, synthetic or public complete pre-holdout "
            "portfolio-return matrix using the existing PBO/DSR research module. "
            "No file paths or final holdout data accepted; no trade approval."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "matrix_json": {"type": "string", "maxLength": _MAX_MATRIX_BYTES},
            },
            "required": ["matrix_json"],
            "additionalProperties": False,
        },
    },
)

_TOOLS = {
    spec["name"]: {
        **spec,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }
    for spec in _TOOL_SPEC
}


class BridgeRefused(ValueError):
    """No untrusted details should be included in any error response."""


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict:
    found: dict = {}
    for name, value in pairs:
        if name in found:
            raise BridgeRefused("DUPLICATE_REQUEST_KEY")
        found[name] = value
    return found


def _deny_constant(_value: str) -> None:
    raise BridgeRefused("NONFINITE_REQUEST")


def _parse(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_LINE_BYTES:
        raise BridgeRefused("INVALID_REQUEST_SIZE")
    try:
        value = json.loads(
            raw, object_pairs_hook=_strict_pairs, parse_constant=_deny_constant,
        )
    except BridgeRefused:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise BridgeRefused("INVALID_JSON") from exc
    if type(value) is not dict:
        raise BridgeRefused("REQUEST_OBJECT_REQUIRED")
    return value


def _is_rpc_id(value: object) -> bool:
    return (type(value) is int and -(2**53) < value < 2**53) or (
        type(value) is str and 1 <= len(value) <= 64
    )


def _response(request_id: str | int | None, *, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(
    request_id: str | int | None, code: int, message: str, *, data: dict | None = None,
) -> dict:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def _tool_result(
    value: dict, *, invalid: bool = False, modern: bool = False,
) -> dict:
    response = {
        "content": [{
            "type": "text",
            "text": json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ),
        }],
        "isError": invalid,
    }
    if modern:
        response["resultType"] = "complete"
    return response


def _args(name: str, args: object) -> dict:
    if type(args) is not dict or name not in _TOOLS:
        raise BridgeRefused("TOOL_OR_ARGUMENTS_REFUSED")
    expected = _TOOLS[name]["inputSchema"]
    allowed = expected["properties"]
    if set(args) - set(allowed) or not set(expected.get("required", ())) <= set(args):
        raise BridgeRefused("TOOL_ARGUMENTS_REFUSED")
    for key, value in args.items():
        field = allowed[key]
        kind = field["type"]
        if kind == "string":
            if type(value) is not str or len(value) > field.get("maxLength", 100000):
                raise BridgeRefused("TOOL_ARGUMENTS_REFUSED")
            if "enum" in field and value not in field["enum"]:
                raise BridgeRefused("TOOL_ARGUMENTS_REFUSED")
        elif kind == "integer":
            if (type(value) is not int
                    or not field["minimum"] <= value <= field["maximum"]):
                raise BridgeRefused("TOOL_ARGUMENTS_REFUSED")
        else:
            raise BridgeRefused("TOOL_ARGUMENTS_REFUSED")
    return args


def _call(name: str, raw_args: object) -> dict:
    args = _args(name, raw_args)
    if name == "research_capabilities":
        return {
            "scope": "OFFLINE_FIXTURE_ONLY",
            "tools": sorted(_TOOLS),
            "protocol_versions": [MODERN, LEGACY],
            "modes": ["research", "diagnostic"],
            "can_read_files": False,
            "can_access_network": False,
            "can_access_database": False,
            "can_access_credentials": False,
            "can_call_plugin_code": False,
            "can_change_settings": False,
            "can_send_signals": False,
            "can_place_orders": False,
            "research_edge_verified": False,
        }
    if name == "diagnose_exchange_failure":
        diagnosis = diagnose_exchange_failure(
            venue=args["venue"], http_status=args.get("http_status"),
            exchange_code=args.get("exchange_code"),
            message=args.get("message"), request_submitted=True,
        )
        return {
            "venue": diagnosis.venue,
            "category": diagnosis.category.value,
            "operator_review": diagnosis.action.value,
            "evidence_tag": diagnosis.evidence,
            "execution_authorized": False,
            "retry_authorized": False,
        }
    if name == "normalize_order_status":
        status = normalize_native_order_status(
            args["venue"], args["native_status"],
        )
        return {
            "normalized_status": status.value if status is not None else "unknown",
            "requires_reconciliation": status is None,
            "fill_booked": False,
            "execution_authorized": False,
        }
    if name == "audit_overfit_fixture":
        raw = args["matrix_json"].encode("utf-8")
        if len(raw) > _MAX_MATRIX_BYTES:
            raise BridgeRefused("MATRIX_TOO_LARGE")
        # Guard computational complexity before invoking exhaustive CSCV.
        try:
            matrix = _parse(raw)
        except BridgeRefused as exc:
            raise BridgeRefused("INVALID_MATRIX") from exc
        if (
            type(matrix.get("rows")) is not list
            or len(matrix["rows"]) > _MAX_MATRIX_PERIODS
            or type(matrix.get("candidate_ids")) is not list
            or len(matrix["candidate_ids"]) > _MAX_MATRIX_TRIALS
            or type(matrix.get("cscv_blocks")) is not int
            or matrix["cscv_blocks"] not in (4, 6)
        ):
            raise BridgeRefused("MATRIX_RESOURCE_FENCE")
        report = analyze_overfit_fixture(raw)
        return {
            "scope": report["mode"],
            "pbo": report["pbo"],
            "dsr": report["dsr"],
            "candidate_count": report["candidate_count"],
            "period_count": report["period_count"],
            "holdout_rows_loaded": 0,
            "readiness": "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF",
            "trading_authorized": False,
            "source_authenticated": False,
        }
    raise BridgeRefused("UNKNOWN_TOOL")


@dataclass
class OfflineMcpSession:
    """A single stdio connection, with explicit dual-era handshake fences."""

    era: str = "new"
    initialized: bool = False

    def _modern_meta(self, params: object, request_id: str | int) -> dict | None:
        if type(params) is not dict or type(params.get("_meta")) is not dict:
            return _error(request_id, -32602, "Modern MCP metadata required")
        meta = params["_meta"]
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        if version != MODERN:
            return _error(
                request_id, -32022, "Unsupported protocol version",
                data={
                    "supported": [MODERN],
                    "requested": version if type(version) is str and len(version) <= 32
                    else "missing",
                },
            )
        if type(meta.get("io.modelcontextprotocol/clientCapabilities")) is not dict:
            return _error(request_id, -32602, "Client capabilities required")
        return None

    def handle(self, request: object) -> dict | None:
        """Never echo unknown methods, parameters, IDs or raw exceptions."""
        if type(request) is not dict or request.get("jsonrpc") != "2.0":
            return _error(None, -32600, "Invalid JSON-RPC request")
        method = request.get("method")
        id_present = "id" in request
        request_id = request.get("id")
        if not id_present:
            if method == "notifications/initialized" and self.era == "legacy":
                self.initialized = True
            # Other notifications have no reply or state effect.
            return None
        if not _is_rpc_id(request_id) or type(method) is not str:
            return _error(None, -32600, "Invalid JSON-RPC request")
        if any(key not in ("jsonrpc", "id", "method", "params") for key in request):
            return _error(request_id, -32600, "Invalid JSON-RPC fields")
        params = request.get("params", {})
        if method == "initialize":
            if self.era != "new" or type(params) is not dict:
                return _error(request_id, -32600, "Initialization refused")
            if params.get("protocolVersion") != LEGACY:
                return _error(
                    request_id, -32022, "Unsupported protocol version",
                    data={"supported": [LEGACY], "requested": "unsupported"},
                )
            if (type(params.get("clientInfo")) is not dict
                    or type(params.get("capabilities")) is not dict):
                return _error(request_id, -32602, "Invalid initialize parameters")
            self.era = "legacy"
            return _response(request_id, result={
                "protocolVersion": LEGACY,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": _NAME, "version": "1.0.0"},
                "instructions": "Offline public/synthetic research only. No trading.",
            })
        if self.era == "new" or self.era == "modern":
            if self.era == "new" and method != "server/discover":
                # The new era also permits a direct, fully annotated tool request.
                error = self._modern_meta(params, request_id)
                if error is not None:
                    return error
                self.era = "modern"
            else:
                error = self._modern_meta(params, request_id)
                if error is not None:
                    return error
                self.era = "modern"
        elif self.era == "legacy" and not self.initialized:
            return _error(request_id, -32000, "MCP initialize notification required")
        if method == "server/discover":
            if self.era != "modern":
                return _error(request_id, -32601, "Method not found")
            if set(params) != {"_meta"}:
                return _error(request_id, -32602, "Discovery parameters refused")
            return _response(request_id, result={
                "resultType": "complete",
                "supportedVersions": [MODERN],
                "capabilities": {"tools": {"listChanged": False}},
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {
                        "name": _NAME, "version": "1.0.0",
                    },
                },
                "instructions": "Read-only diagnostic and synthetic research fixtures only.",
                "ttlMs": 0,
                "cacheScope": "private",
            })
        if method == "ping":
            return _response(
                request_id, result={"resultType": "complete"}
                if self.era == "modern" else {},
            )
        if method == "tools/list":
            allowed = {"_meta"} if self.era == "modern" else set()
            if type(params) is not dict or set(params) != allowed:
                return _error(request_id, -32602, "Tool-list parameters refused")
            output = {"tools": list(_TOOLS.values())}
            if self.era == "modern":
                output["resultType"] = "complete"
            return _response(request_id, result=output)
        if method == "tools/call":
            allowed = {"_meta", "name", "arguments"} if self.era == "modern" else {
                "name", "arguments",
            }
            if type(params) is not dict or set(params) != allowed:
                return _error(request_id, -32602, "Tool-call parameters refused")
            name = params.get("name")
            if type(name) is not str or name not in _TOOLS:
                return _error(request_id, -32602, "Unknown research tool")
            try:
                output = _call(name, params.get("arguments", {}))
            except (
                BridgeRefused, ValueError, ObservationRefused,
                OverfitEvidenceRefused, UnicodeError, OverflowError,
            ):
                return _response(request_id, result=_tool_result(
                    {"status": "REFUSED", "reason": "INVALID_OR_UNTRUSTED_EVIDENCE"},
                    invalid=True, modern=self.era == "modern",
                ))
            return _response(
                request_id, result=_tool_result(
                    output, modern=self.era == "modern",
                ),
            )
        return _error(request_id, -32601, "Method not found")


def run_stdio(
    instream: BinaryIO, outstream: BinaryIO, *, approved: bool = False,
) -> int:
    """No input/output other than JSON-RPC lines; silent unless approved."""
    if approved is not True:
        return 2
    session = OfflineMcpSession()
    while True:
        line = instream.readline(_MAX_LINE_BYTES + 2)
        if not line:
            return 0
        if len(line) > _MAX_LINE_BYTES + 1 or not line.endswith(b"\n"):
            # Drain the current oversized frame in bounded chunks.
            while line and not line.endswith(b"\n"):
                line = instream.readline(_MAX_LINE_BYTES + 2)
            reply = _error(None, -32700, "Invalid or oversized JSON-RPC frame")
        else:
            try:
                request = _parse(line.rstrip(b"\r\n"))
                reply = session.handle(request)
            except BridgeRefused:
                reply = _error(None, -32700, "Invalid or oversized JSON-RPC frame")
        if reply is not None:
            encoded = json.dumps(
                reply, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
            outstream.write(encoded + b"\n")
            outstream.flush()


__all__ = ["OfflineMcpSession", "run_stdio", "BridgeRefused"]
