"""CERT-A19-R26 — frozen Worker UTC/timezone and 4-language contract static audit.

NO imports of repository runtime code, no evaluation of guest fixtures, no
installation or execution of binaries from prior OCI/artifacts.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import re

SOURCE_BLOBS = {
    "scripts/runtime_a2_worker.py": "0c21b87b77604c4025b8ea44ba35a24664c1537b",
    "naseri_markets/core_api_v1.py": "23c3c07a8c05f0e70d56c59bf431f858dbd7e267",
    "naseri_markets/multilang_runtime_a1.py": "02478c2786488b1e28eaa2e113636dbf3c9b5a7e",
    "naseri_markets/secure_plugin_runtime_v1.py": "8d8c4b98023ce77d0ade78e1b2fc45f316d0bc75",
    "deploy/runtime_a2/Dockerfile": "83990d55ec888787e2457adcb12c39bcdd2072f6",
    "deploy/runtime_a2/Dockerfile.a15-lean": "4b76808a0745eabd6a4d7dc57982e1ad051b8eba",
    "deploy/runtime_a2/a15_export_runtime.py": "81cfd6761f04b0103a89958719226bf5b23b1afb",
    "naseri_markets/runtime_a6_dispatch_fence.py": "2299dba87a0ba3cd7095d97bca9ed6409adcb0ec",
}
R25_SHA="26bc9c72b4b49c396a973b783764875566f24b4b2568f9495032ad9dc51f9264"
R24_SHA="284ccd9f9549fbcd6572c442cc5f9ebf5759d4cdf5ccb419f2235bff8a3e2f61"
PINNED_BASE="cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"

def fail(code): raise ValueError("CERT_A19_R26_"+code)
def sha(data):return hashlib.sha256(data).hexdigest()
def must(cond,code):
    if not cond: fail(code)
def get_def(tree,name):
    matched=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name]
    must(len(matched)==1,"EXPECTED_FUNCTION_MISSING_"+name)
    return matched[0]
def get_text(tree,node):
    return ast.get_source_segment(tree["raw"],node)
def git_blob(content):
    data=content.encode("utf-8")
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\x00"+data).hexdigest()
def string_assignment(module,name):
    for node in module.body:
        if isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id==name for n in node.targets):
            return ast.literal_eval(node.value)
    fail("MISSING_STATIC_STRING_"+name)
def calls_named(expr,n):
    return any(isinstance(x,ast.Call) and (
        isinstance(x.func,ast.Name) and x.func.id==n or
        isinstance(x.func,ast.Attribute) and x.func.attr==n)
        for x in ast.walk(expr))
def localcode(path):
    d=Path(path)
    must(d.is_file() and not d.is_symlink(),"SOURCE_FILE_ABSENT")
    raw=d.read_bytes()
    must(len(raw)<300_000,"SOURCE_TOO_LARGE")
    expected=SOURCE_BLOBS[path]
    actual=sha(raw)
    must(hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()==expected,
         "SOURCE_GIT_BLOB_DRIFT_"+d.name.replace(".","_"))
    return raw.decode("utf-8"),actual
def source_snapshot():
    results={}
    for name in SOURCE_BLOBS:
        content,actual=localcode(name)
        results[name]={"main_git_blob_sha1":SOURCE_BLOBS[name],
                       "full_source_sha256":actual,"bytes":len(content.encode())}
    return results
def main():
    must(os.environ.get("GITHUB_ACTIONS")=="true" and
         os.environ.get("MMT_NONPRODUCTION")=="1" and
         os.environ.get("GITHUB_REF")=="refs/heads/cert-a19-byte-audit-run",
         "NONPRODUCTION_ONLY")
    d=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r26"
    must(d.is_dir(),"EVIDENCE_ROOT_MISSING")
    b=(d/"r25-static-final-oci.json").read_bytes()
    must(sha(b)==R25_SHA,"R25_SOURCE_REPORT_CHANGED")
    r25=json.loads(b)
    prior=(d/"r24-result.json").read_bytes()
    must(sha(prior)==R24_SHA,"R24_SOURCE_REPORT_CHANGED")
    must(r25.get("stage")=="CERT-A19-R25" and
         r25.get("final_installed_package_count")==40 and
         r25.get("ELF_objects_static_readelf_count")==153 and
         r25.get("no_guest_executable_or_worker_was_run") is True,
         "R25_PRECONDITION_NOT_ESTABLISHED")
    must(r25.get("original_base_digest")==PINNED_BASE,
         "R25_WRONG_IMMUTABLE_IMAGE")
    paths=r25.get("final_OS_NSS_CA_and_tz_source_path_observations",{})
    must(paths.get("usr/share/zoneinfo/UTC",{}).get("found") is False,
         "TZDATA_BASELINE_UNEXPECTED")
    must(paths.get("etc/ssl/certs/ca-certificates.crt",{}).get("found") is True and
         paths.get("etc/os-release",{}).get("ID_wolfi") is True,
         "OS_SOURCE_OBSERVATIONS_DRIFT")
    snapshots=source_snapshot()
    sources={name:Path(name).read_text() for name in SOURCE_BLOBS}
    worker=ast.parse(sources["scripts/runtime_a2_worker.py"])
    core=ast.parse(sources["naseri_markets/core_api_v1.py"])
    a1=ast.parse(sources["naseri_markets/multilang_runtime_a1.py"])
    plugin=ast.parse(sources["naseri_markets/secure_plugin_runtime_v1.py"])
    export=ast.parse(sources["deploy/runtime_a2/a15_export_runtime.py"])
    fence=ast.parse(sources["naseri_markets/runtime_a6_dispatch_fence.py"])

    utc=ast.unparse(get_def(core,"_utc"))
    must("value.tzinfo is None" in utc and "value.utcoffset() is None" in utc and
         "value.astimezone(UTC)" in utc,"CORE_AWARE_UTC_NORMALIZATION_CHANGED")
    parsedatetime=ast.unparse(get_def(plugin,"_when"))
    must("datetime.fromisoformat" in parsedatetime,"ISO8601_PARSE_CONTRACT_CHANGED")
    worker_process=ast.unparse(get_def(worker,"process"))
    must("'observed_at': event['observed_at']" in worker_process,
         "WORKER_TIMESTAMP_PASSTHROUGH_CHANGED")
    child=ast.unparse(get_def(worker,"_child"))
    must('NODE_PATH' in child and 'PATH' in child and '"TZ"' not in child and
         "timeout=3.0" in child and '"node"' in child,
         "CHILD_EXEC_ENV_OR_TIMEOUT_DRIFT")
    pychild=string_assignment(worker,"PY_CHILD")
    jschild=string_assignment(worker,"JS_CHILD")
    must('exec(compile(' in pychild and "vm.Script" in jschild and
         "typescript" in jschild,"FOUR_LANGUAGE_GUEST_CONTRACT_DRIFT")
    wasm=ast.unparse(get_def(worker,"_wasm"))
    must("wasmtime.Config" in wasm and "store.set_fuel" in wasm and
         "WASM_IMPORTS_DENIED" in wasm,"WASM_CONTRACT_DRIFT")
    a1run=ast.unparse(get_def(a1,"_run_oci"))
    must("require_worker_launch(profile, payload)" in a1run and
         "time.monotonic()" in a1run and '"TZ"' not in a1run,
         "A1_ROOTLESS_FENCE_OR_MONOTONIC_CLOCK_CHANGED")
    fence_source=sources["naseri_markets/runtime_a6_dispatch_fence.py"]
    must("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED" in fence_source and
         'raise RuntimeA6Denied("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED")' in fence_source,
         "A6_LAUNCH_DENIAL_DRIFT")
    candidate=sources["deploy/runtime_a2/Dockerfile"]
    lean=sources["deploy/runtime_a2/Dockerfile.a15-lean"]
    must("ENV TZ=" not in candidate and "tzdata" not in candidate.lower() and
         "ENV TZ=" not in lean and "tzdata" not in lean.lower(),
         "HISTORIC_TZDATA_CONTRACT_CHANGED")
    export_source=sources["deploy/runtime_a2/a15_export_runtime.py"]
    must('"18.20.4"' in export_source and
         '"5.9.3"' in export_source and '"49.0.0"' in export_source,
         "HISTORICAL_A15_LANGUAGE_VERSIONS_CHANGED")
    must(r25.get("typescript_5_9_3_and_wasmtime_49_installed_in_this_image") is False,
         "R25_TS_WASMTIME_STATUS_DRIFT")
    flags={
        "core_api_rejects_naive_datetime_and_normalizes_aware_to_UTC":True,
        "worker_observed_at_passes_through_event_without_timezone_lookup":True,
        "worker_uses_timezone_database_directly":False,
        "Python_child_executes_external_source_in_subprocess":True,
        "JavaScript_child_uses_node_vm_not_security_boundary":True,
        "typescript_transpile_requires_installed_typescript_package":True,
        "wasmtime_module_requires_installed_python_binding":True,
        "child_exec_environment_explicit_TZ_pinned":False,
        "host_A1_clock_uses_time_monotonic_for_deadline":True,
        "external_guest_source_timezone_behavior_proven_deterministic":False,
        "R25_UTC_IANA_zoneinfo_file_present":False,
        "runtime_TZ_configuration_and_iana_timezone_support_verified":False,
        "R25_CA_bundle_file_present_but_TLS_runtime_unverified":True,
        "legacy_A15_node_version_18_20_4_requires_requalification_for_Wolfi_node_24":True,
        "R25_image_contains_TypeScript_and_Wasmtime":False,
        "worker_or_guest_code_executed":False,
        "production_authorized":False,
        "A6_hard_DENY":True
    }
    report={
        "stage":"CERT-A19-R26",
        "verdict":"WORKER_CORE_AWARE_UTC_STATIC_CONTRACT_PASS__TZDB_GUEST_DETERMINISM_AND_FOUR_LANGUAGE_RUNTIME_NOT_CERTIFIED",
        "base_image":PINNED_BASE,"frozen_R25_report_sha256":R25_SHA,
        "frozen_R24_report_sha256":R24_SHA,
        "source_files_exact_git_blobs_verified":len(snapshots),
        "source_sha256_custody":snapshots,
        "R25_final_image_packages":40,"R25_ELF_statics":153,
        "core_datetime_semantics":{
          "CoreAPI_v1":"aware timestamp required; astimezone(datetime.UTC); no IANA tz name needed for this code path",
          "secure_plugin":"datetime.fromisoformat input parsing then CoreResult aware UTC contract",
          "worker":"framed input observed_at copied from event after digest/identity validation, no local timezone calculation",
          "host_A1":"time.monotonic controls subprocess deadline, not wall-clock zone conversion"
        },
        "worker_four_language_static_contract":{
          "python":"python -I -S child executes fixed or uploaded Python source; not certified safe outside approved host",
          "javascript":"node --input-type=commonjs --eval JS_CHILD; vm.Script not a security boundary",
          "typescript":"node's require('typescript') transpileModule to ES2022; TS artifact not installed in R25 image",
          "wasm":"Python wasmtime binding, fuel 1,000,000, memory 8MiB and no imports; wheel not installed in R25 image",
          "historical_vs_candidate_node":{"historical_A15":"18.20.4","R25_Wolfi_candidate":"24.22.0-r0",
                                         "behavior_equivalence_tested":False}
        },
        "flags":flags,
        "allow_UTC_core_only_without_installed_iana_db_as_product_feature":False,
        "source_does_not_directly_require_tzdb_for_UTC_normalization":True,
        "missing_tzdata_is_unresolved_for_arbitrary_guest_and_host_configuration":True,
        "package_mutation_or_tzdata_installation_performed":False,
        "source_or_image_or_production_changed":False,
        "original_199_review_open":True,
        "CVE_closures":0,
        "recommended_next_gate":"Specify deterministic TZ/UTC policy for guest runtimes, prove final image env+TZ behavior, source-verify timezone data if needed, then isolated benign fixture comparisons, never unlock A6 until independent gVisor security certification"
    }
    output=d/"r26-timezone-contract.json"
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R26_MAIN_SOURCE_BLOBS_VERIFIED="+str(len(snapshots)))
    print("R26_CORE_AWARE_UTC_STATIC_CONTRACT_PASS")
    print("R26_R25_TZDATA_NOT_IN_IMAGE__GUEST_TIMEZONE_DETERMINISM_UNPROVEN")
    print("R26_FOUR_LANGUAGE_RUNTIME_NOT_EXECUTED_A6_DENY_199_OPEN")
if __name__=="__main__": main()
