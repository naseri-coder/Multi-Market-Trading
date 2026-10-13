#!/usr/bin/env python3
"""RUNTIME-A2: framed four-language worker inside independently isolated OCI.

This script is executable but NOT a standalone security sandbox. NEVER run
untrusted input outside an independently reviewed rootless gVisor environment.
Developer fixtures in CI are fixed harmless source only, not user uploads.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

MAX_FRAME = 196608
MAX_ARTIFACT = 65536
MAX_STDOUT = 16384
SHA = re.compile(r"[a-f0-9]{64}\Z")
KINDS = {"python", "javascript", "typescript", "wasm"}

PY_CHILD = """
import json,sys
req=json.load(sys.stdin)
env={"__name__":"__main__"}
exec(compile(req["source"],"<core-fixture>","exec"),env)
fn=env.get("evaluate")
if not callable(fn): raise ValueError("MISSING_EVALUATE")
out=fn(req["event"])
if not isinstance(out,list): raise ValueError("NOT_A_DECISION_LIST")
sys.stdout.write(json.dumps(out,allow_nan=False,separators=(",",":")))
"""

JS_CHILD = r"""
const fs=require('node:fs'),vm=require('node:vm');
const req=JSON.parse(fs.readFileSync(0,'utf8'));
let code=req.source;
if(req.kind==='typescript'){
  const ts=require('typescript');
  code=ts.transpileModule(code,{compilerOptions:{
    target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None,
    isolatedModules:true
  },reportDiagnostics:true}).outputText;
}
const sandbox=Object.create(null);
sandbox.event=req.event;
new vm.Script(code,{filename:'<reviewed-oci-input>'}).runInNewContext(sandbox,{timeout:500});
if(typeof sandbox.evaluate!=='function') throw Error('MISSING_EVALUATE');
const decisions=new vm.Script('evaluate(event)').runInNewContext(sandbox,{timeout:500});
if(!Array.isArray(decisions)) throw Error('NOT_A_DECISION_LIST');
process.stdout.write(JSON.stringify(decisions));
"""


class WorkerRefused(ValueError):
    """Refuses an invalid input without echoing user-provided source."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise WorkerRefused("DUPLICATE_FIELD")
        result[key] = value
    return result


def _reject_float(_: str) -> None:
    raise WorkerRefused("FLOAT_NOT_ALLOWED")


def _parse(raw: bytes) -> object:
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_float=_reject_float, parse_constant=_reject_float,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise WorkerRefused("NOT_STRICT_JSON") from exc


def _digest(data: object) -> str:
    wire = json.dumps(data, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")
    return hashlib.sha256(wire).hexdigest()


def _frame(raw: bytes, runtime_kind: str) -> tuple[bytes, dict]:
    if len(raw) < 8 or len(raw) > MAX_FRAME + 4:
        raise WorkerRefused("FRAME_SIZE_INVALID")
    length = int.from_bytes(raw[:4], "big")
    if length <= 0 or length > MAX_ARTIFACT or len(raw) <= 4 + length:
        raise WorkerRefused("ARTIFACT_SIZE_INVALID")
    artifact, request = raw[4:4+length], _parse(raw[4+length:])
    expected = {
        "abi_major", "abi_minor", "protocol", "runtime_kind", "artifact_sha256",
        "manifest_digest", "manifest", "input_digest", "event",
    }
    if type(request) is not dict or set(request) != expected:
        raise WorkerRefused("REQUEST_SCHEMA_INVALID")
    if (type(request["abi_major"]) is not int or request["abi_major"] != 1
            or type(request["abi_minor"]) is not int or request["abi_minor"] != 0
            or request["protocol"] != "RUNTIME_A1_FRAMED_V1"
            or request["runtime_kind"] != runtime_kind
            or runtime_kind not in KINDS):
        raise WorkerRefused("RUNTIME_ABI_MISMATCH")
    if (type(request["manifest_digest"]) is not str
            or not SHA.fullmatch(request["manifest_digest"])
            or type(request["input_digest"]) is not str
            or not SHA.fullmatch(request["input_digest"])
            or type(request["artifact_sha256"]) is not str
            or not SHA.fullmatch(request["artifact_sha256"])):
        raise WorkerRefused("DIGEST_SCHEMA_INVALID")
    if (hashlib.sha256(artifact).hexdigest() != request["artifact_sha256"]
            or _digest(request["event"]) != request["input_digest"]
            or _digest(request["manifest"]) != request["manifest_digest"]):
        raise WorkerRefused("DIGEST_MISMATCH")
    e, m = request["event"], request["manifest"]
    if (type(e) is not dict or type(m) is not dict
            or type(e.get("binding")) is not dict
            or e.get("origin") not in ("synthetic", "replay")
            or e.get("core_id") != m.get("core_id")
            or e.get("core_version") != m.get("core_version")):
        raise WorkerRefused("CORE_IDENTITY_INVALID")
    return artifact, request


def _child(kind: str, artifact: bytes, event: dict) -> bytes:
    try:
        source = artifact.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise WorkerRefused("NOT_UTF8_SOURCE") from exc
    request = json.dumps({"source": source, "kind": kind, "event": event},
                         separators=(",", ":"), allow_nan=False).encode()
    argv = (
        [sys.executable, "-I", "-S", "-c", PY_CHILD]
        if kind == "python"
        else ["node", "--input-type=commonjs", "--eval", JS_CHILD]
    )
    try:
        result = subprocess.run(
            argv, input=request, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=3.0, check=False,
            env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                 "NODE_PATH": os.environ.get("NODE_PATH", "")},
            cwd="/tmp" if os.path.isdir("/tmp") else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkerRefused("CHILD_RUNTIME_UNAVAILABLE") from exc
    if result.returncode != 0 or not 0 < len(result.stdout) <= MAX_STDOUT:
        raise WorkerRefused("CHILD_REFUSED")
    return result.stdout


def _wasm(artifact: bytes, event: dict) -> bytes:
    try:
        import wasmtime
    except ImportError as exc:
        raise WorkerRefused("WASMTIME_MISSING") from exc
    config = wasmtime.Config()
    config.consume_fuel = True
    engine = wasmtime.Engine(config)
    try:
        module = wasmtime.Module(engine, artifact)
        if module.imports:
            raise WorkerRefused("WASM_IMPORTS_DENIED")
        store = wasmtime.Store(engine)
        store.set_fuel(1_000_000)
        store.set_limits(memory_size=8*1024*1024, instances=1,
                         tables=1, memories=1)
        instance = wasmtime.Instance(store, module, [])
        exports = instance.exports(store)
        memory = exports.get("memory")
        fn = exports.get("evaluate")
        if not isinstance(memory, wasmtime.Memory) or not isinstance(fn, wasmtime.Func):
            raise WorkerRefused("WASM_EXPORTS_REQUIRED")
        if memory.data_len(store) > 8*1024*1024:
            raise WorkerRefused("WASM_MEMORY_EXCESS")
        wire = json.dumps(event, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode()
        if len(wire) > 65535:
            raise WorkerRefused("WASM_EVENT_TOO_LARGE")
        memory.write(store, wire, 0)
        ref = fn(store, 0, len(wire))
        if type(ref) is not int or ref < 0:
            raise WorkerRefused("WASM_ABI_INVALID")
        ptr, size = ref >> 32, ref & 0xffffffff
        if size <= 0 or size > MAX_STDOUT or ptr < len(wire):
            raise WorkerRefused("WASM_OUTPUT_RANGE_INVALID")
        if ptr + size > memory.data_len(store):
            raise WorkerRefused("WASM_MEMORY_RANGE_INVALID")
        return bytes(memory.read(store, ptr, ptr+size))
    except WorkerRefused:
        raise
    except (ValueError, TypeError, RuntimeError, OSError, wasmtime.WasmtimeError) as exc:
        raise WorkerRefused("WASM_EXECUTION_FAILED") from exc


def process(raw: bytes, runtime_kind: str) -> bytes:
    """All four language executions return DECISIONS ONLY; host owns identity."""
    artifact, request = _frame(raw, runtime_kind)
    data = (
        _wasm(artifact, request["event"])
        if runtime_kind == "wasm"
        else _child(runtime_kind, artifact, request["event"])
    )
    decisions = _parse(data)
    if (type(decisions) is not list or not 1 <= len(decisions) <= 12
            or any(type(d) is not dict for d in decisions)):
        raise WorkerRefused("DECISIONS_SCHEMA_INVALID")
    event = request["event"]
    result = {
        "abi_major": 1, "abi_minor": 0,
        "core_id": event["core_id"], "core_version": event["core_version"],
        "instance_id": event["binding"]["instance_id"],
        "binding_id": event["binding"]["binding_id"],
        "observed_at": event["observed_at"],
        "input_digest": request["input_digest"],
        "decisions": decisions,
    }
    wire = json.dumps(result, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(wire) > MAX_STDOUT:
        raise WorkerRefused("RESULT_TOO_LARGE")
    return wire


def main() -> int:
    runtime_kind = os.environ.get("MMT_RUNTIME_KIND", "")
    if runtime_kind not in KINDS:
        return 64
    # Plus one byte ensures over-sized input fails, never truncates silently.
    raw = sys.stdin.buffer.read(MAX_FRAME + 5)
    try:
        wire = process(raw, runtime_kind)
    except (WorkerRefused, ValueError, TypeError, KeyError, RecursionError):
        return 65
    sys.stdout.buffer.write(wire)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
