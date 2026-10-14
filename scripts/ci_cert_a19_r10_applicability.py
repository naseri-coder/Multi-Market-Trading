"""CERT-A19-R10 static advisory applicability check; no Worker or guest execution.

Uses R8's authenticated Debian source chain on isolated hosted runner.
Evaluates *named mechanisms*, not global security or authoritative Debian CVE status.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

EXPECTED_BALANCED = "06e20567449a6131d5ae6f049b5d85f17c3139f2fed6a2783f656429180ff865"
EXPECTED_A6_DENY = "A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED"
EXPECTED_VERSION = "5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4"
ROOT = Path(__file__).resolve().parents[1]


def abort(code: str) -> None:
    raise ValueError("A19_R10_" + code)


def verified_source(work: Path) -> tuple[Path, dict]:
    evidence = json.loads((work.parent / "cert-a19-source-chain.json").read_text())
    if (evidence.get("stage") != "CERT-A19-R8"
            or not evidence.get("debian_developer_signature_verified_using_host_keyring")
            or not evidence.get("source_and_r7_binary_balanced_pool_equal")
            or evidence.get("patched_source_balanced_pool_sha256") != EXPECTED_BALANCED
            or len(evidence.get("source_components_verified", [])) != 7):
        abort("SIGNATURE_OR_FILE_SHA_EVIDENCE_MISSING")
    source = work / "patched-source"
    if not source.is_dir() or source.is_symlink():
        abort("PATCHED_SOURCE_UNAVAILABLE")
    return source, evidence


def read_source(path: Path, max_size: int = 160_000) -> bytes:
    if path.is_symlink() or not path.is_file():
        abort("SOURCE_FILE_ABSENT_OR_SYMLINK")
    size = path.stat().st_size
    if not 0 < size <= max_size:
        abort("SOURCE_FILE_SIZE_INVALID")
    raw = path.read_bytes()
    if len(raw) != size:
        abort("SOURCE_BYTES_DRIFT")
    return raw


def worker_wrapper() -> dict:
    worker = (ROOT / "scripts/runtime_a2_worker.py")
    py = read_source(worker, 100_000).decode("utf-8")
    module = ast.parse(py)
    found = [n.value for n in module.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "JS_CHILD" for t in n.targets)]
    if len(found) != 1:
        abort("JS_CHILD_NOT_UNIQUE")
    js = ast.literal_eval(found[0])
    if not isinstance(js, str):
        abort("JS_CHILD_NOT_LITERAL")
    required = [
        "const fs=require('node:fs'),vm=require('node:vm');",
        "const sandbox=Object.create(null);",
        "sandbox.event=req.event;",
        "new vm.Script(code,{filename:'<reviewed-oci-input>'}).runInNewContext(sandbox,{timeout:500});",
        "new vm.Script('evaluate(event)').runInNewContext(sandbox,{timeout:500});",
    ]
    if any(part not in js for part in required):
        abort("JS_CHILD_ENTRYPOINT_DRIFT")
    prohibited = ["require('undici')", 'require("undici")',
                  "new BalancedPool", "interceptors.cache(", "sandbox.fetch=",
                  "sandbox.require=", "sandbox.process="]
    if any(part in js for part in prohibited):
        abort("JS_CHILD_UNEXPECTED_EXPLICIT_UNDICI_ENTRY")
    if '"node", "--input-type=commonjs", "--eval", JS_CHILD' not in py:
        abort("NODE_WRAPPER_INVOCATION_DRIFT")
    if EXPECTED_A6_DENY not in read_source(ROOT / "naseri_markets/runtime_a6_dispatch_fence.py").decode():
        abort("A6_DENIAL_NOT_PRESENT")
    exporter = read_source(ROOT / "deploy/runtime_a2/a15_export_runtime.py").decode()
    if ('_UNDICI = Path("/usr/share/nodejs/undici")' not in exporter
            or "shutil.copytree(directory, target, symlinks=False)" not in exporter):
        abort("A15_UNDICI_TREE_CUSTODY_DRIFT")
    return {
        "trusted_wrapper_invokes_node_js_vm": True,
        "wrapper_explicitly_imports_undici": False,
        "wrapper_explicitly_constructs_balancedpool": False,
        "wrapper_explicitly_enables_cache_interceptor": False,
        "only_event_explicitly_injected_into_vm_sandbox": True,
        "vm_escape_and_runtime_integrity_independently_certified": False,
        "runtime_a6_fence_still_denies_uncertified_execution": True,
    }


def inspect(source: Path, evidence: dict) -> dict:
    balanced = read_source(source / "lib/balanced-pool.js")
    actual_sha = hashlib.sha256(balanced).hexdigest()
    if actual_sha != EXPECTED_BALANCED:
        abort("BALANCED_POOL_SHA_CHANGED")
    code = balanced.decode("utf-8")
    if ("this[kFactory](upstreamOrigin, Object.assign({}, this[kOptions]))" not in code
            or "JSON.parse(JSON.stringify" in code):
        abort("BALANCED_POOL_OPTIONS_PATH_DRIFT")
    index = read_source(source / "index.js").decode("utf-8")
    if ("require('./lib/balanced-pool')" not in index
            or "module.exports.BalancedPool = BalancedPool" not in index):
        abort("PUBLIC_BALANCED_POOL_EXPORT_CHANGED")
    util_cache = source / "lib/util/cache.js"
    interceptor_cache = source / "lib/interceptor/cache.js"
    if (util_cache.exists() or util_cache.is_symlink()
            or interceptor_cache.exists() or interceptor_cache.is_symlink()):
        abort("SPECIFIC_CACHE_ADVISORY_PATH_PRESENT")
    if "interceptors.cache()" in index or "interceptors.cache(" in index:
        abort("EXPLICIT_INDEX_CACHE_API_PRESENT")
    cache_related = sorted(
        str(f.relative_to(source)) for f in (source / "lib").rglob("*")
        if "cache" in f.name.lower() and f.is_file()
    )
    if len(cache_related) > 100:
        abort("UNBOUNDED_ALTERNATE_CACHE_INVENTORY")
    return {
        "debian_source_version": EXPECTED_VERSION,
        "debian_patched_source_balanced_pool_sha256": actual_sha,
        "ghsa_w293_exact_json_function_dropping_mechanism_present": False,
        "balanced_pool_public_export_present": True,
        "balanced_pool_function_preserving_object_assign_present": True,
        "ghsa_4cwx_lib_util_cache_js_present": False,
        "ghsa_4cwx_lib_interceptor_cache_js_present": False,
        "interceptors_cache_export_observed_in_index": False,
        "other_cache_named_lib_files": cache_related,
        "no_alternate_equivalent_code_proven": False,
        "nodejs_undici_npm_advisory_7x_8x_vs_debian_5x_version_discrepancy": True,
        "debian_security_tracker_bookworm_reported_vulnerable": True,
        "source_signer_independent_offline_custody": False,
        "r8_signed_component_count": 7,
        "worker": worker_wrapper(),
        "scope": "EXACT_DEBIAN_5_15_ADVISORY_MECHANISMS_AND_FIXED_WRAPPER_STATIC_ONLY",
        "runtime_dynamic_reachability_proven": False,
        "all_possible_node_or_vm_routes_excluded": False,
        "historical_a18_binary_exact_hash_verified": False,
        "affected_vendor_disposition": "DEBIAN_TRACKER_OPEN__INDEPENDENT_REVIEW_REQUIRED",
        "cves_fixed_or_false_positive_certified": 0,
        "original_critical_high_findings_review_open": 199,
        "production_authorized": False,
    }


def main() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REF") != "refs/heads/cert-a19-byte-audit-run"):
        abort("FIXED_NONPRODUCTION_CI_REQUIRED")
    work = Path(os.environ["RUNNER_TEMP"]) / "cert-a19-source"
    root, evidence = verified_source(work)
    result = inspect(root, evidence)
    out = Path(os.environ["RUNNER_TEMP"]) / "cert-a19-r10-applicability.json"
    out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("CERT_A19_R10_SIGNED_SOURCE_FROZEN_MECHANISM_INSPECTION_PASS")
    print("CERT_A19_R10_BALANCEDPOOL_API_EXPORT_PRESENT_BUT_JSON_CLONE_ABSENT")
    print("CERT_A19_R10_BOTH_NAMED_CACHE_IMPLEMENTATION_PATHS_ABSENT")
    print("CERT_A19_R10_WORKER_HAS_NO_EXPLICIT_UNDICI_IMPORT_VM_SECURITY_UNCERTIFIED")
    print("CERT_A19_R10_DEBIAN_TRACKER_OPEN_ZERO_CVE_CLOSED")


if __name__ == "__main__":
    main()
