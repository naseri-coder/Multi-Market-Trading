"""CERT-A19-R27 — fixed explicit-offset time-vector and host-gate static preflight.

NO target app imports, Node/Python/TS/WASM guest execution, runtime sandbox
invocation, tzdata package changes, OCI creation, or production action.
Fixture outputs use ONLY GitHub runner's trusted Python standard library.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

R26_SHA="2de79cd86da7ccc17ce15952455c8b7673cf4161d3f99a32955d668e7e9f1667"
R25_SHA="26bc9c72b4b49c396a973b783764875566f24b4b2568f9495032ad9dc51f9264"
BASE="cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
BLOBS={
 "scripts/runtime_a2_worker.py":"0c21b87b77604c4025b8ea44ba35a24664c1537b",
 "naseri_markets/core_api_v1.py":"23c3c07a8c05f0e70d56c59bf431f858dbd7e267",
 "naseri_markets/multilang_runtime_a1.py":"02478c2786488b1e28eaa2e113636dbf3c9b5a7e",
 "naseri_markets/secure_plugin_runtime_v1.py":"8d8c4b98023ce77d0ade78e1b2fc45f316d0bc75",
 "naseri_markets/runtime_a6_dispatch_fence.py":"2299dba87a0ba3cd7095d97bca9ed6409adcb0ec",
}
# Vectors never request host localtime or ZoneInfo; explicit offsets are
# sufficient for deterministic UTC normalization on a trusted test runner.
VECTORS=(
 {"id":"utc-Z","input":"2026-10-15T09:00:00+00:00","expected_utc":"2026-10-15T09:00:00+00:00"},
 {"id":"offset-positive","input":"2026-10-15T12:30:00+03:30","expected_utc":"2026-10-15T09:00:00+00:00"},
 {"id":"offset-negative","input":"2026-10-15T05:00:00-04:00","expected_utc":"2026-10-15T09:00:00+00:00"},
 {"id":"spring-before-explicit","input":"2026-03-29T01:59:59+01:00","expected_utc":"2026-03-29T00:59:59+00:00"},
 {"id":"spring-after-explicit","input":"2026-03-29T03:00:00+02:00","expected_utc":"2026-03-29T01:00:00+00:00"},
 {"id":"autumn-fold-first-explicit","input":"2026-10-25T02:30:00+02:00","expected_utc":"2026-10-25T00:30:00+00:00"},
 {"id":"autumn-fold-second-explicit","input":"2026-10-25T02:30:00+01:00","expected_utc":"2026-10-25T01:30:00+00:00"},
)
INVALID=(
 {"id":"naive","value":"2026-10-25T02:30:00","reason":"NO_EXPLICIT_OFFSET"},
 {"id":"named-zone-string","value":"2026-10-25T02:30:00 Europe/Berlin","reason":"NAMED_ZONE_CONVERSION_NOT_CERTIFIED"},
 {"id":"invalid-time","value":"2026-10-25T25:30:00+01:00","reason":"INVALID_CLOCK"},
 {"id":"invalid-offset","value":"2026-10-25T02:30:00+25:00","reason":"INVALID_OFFSET"},
)

def deny(reason):raise ValueError("CERT_A19_R27_"+reason)
def sha(x):return hashlib.sha256(x).hexdigest()
def asbytes(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def frozen(path,digest,cap):
 p=Path(path)
 if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=cap:deny("EVIDENCE_NOT_AVAILABLE")
 b=p.read_bytes()
 if sha(b)!=digest:deny("PRIOR_EVIDENCE_HASH_DRIFT")
 return json.loads(b)
def git_blob(b):
 return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def code(path,blob):
 p=Path(path)
 if p.is_symlink() or not p.is_file() or p.stat().st_size>300_000:deny("CODE_SOURCE_MISSING")
 b=p.read_bytes()
 if git_blob(b)!=blob:deny("MAIN_SOURCE_GIT_BLOB_DRIFT_"+p.name)
 return b.decode("utf-8","strict")
def ast_fn(t,name):
 v=[n for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
 if len(v)!=1:deny("MISSING_FUNCTION_"+name)
 return ast.unparse(v[0])
def validate_vectors():
 seen=set()
 for v in VECTORS:
  if v["id"] in seen:deny("DUPLICATE_VECTOR")
  seen.add(v["id"])
  value=datetime.fromisoformat(v["input"])
  if value.tzinfo is None or value.utcoffset() is None:deny("ACCEPTED_VECTOR_HAS_NO_OFFSET")
  if value.astimezone(timezone.utc).isoformat()!=v["expected_utc"]:
   deny("EXPLICIT_OFFSET_REFERENCE_MISMATCH_"+v["id"])
 for v in INVALID:
  accepted=False
  try:
   value=datetime.fromisoformat(v["value"])
   accepted=(value.tzinfo is not None and value.utcoffset() is not None)
  except (TypeError,ValueError):pass
  if accepted:deny("NEGATIVE_VECTOR_NOT_REJECTED_"+v["id"])
 return len(VECTORS),len(INVALID)
def main():
 if {k:os.environ.get(k) for k in ("GITHUB_ACTIONS","MMT_NONPRODUCTION","GITHUB_REF")}!={
  "GITHUB_ACTIONS":"true","MMT_NONPRODUCTION":"1",
  "GITHUB_REF":"refs/heads/cert-a19-byte-audit-run"}:deny("SCOPE_NONPRODUCTION_ONLY")
 root=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r27"
 if not root.is_dir():deny("EVIDENCE_DIR_MISSING")
 r26=frozen(root/"r26-timezone-contract.json",R26_SHA,50_000)
 r25=frozen(root/"r25-static-final-oci.json",R25_SHA,130_000)
 if r26.get("stage")!="CERT-A19-R26" or r26.get("flags",{}).get("A6_hard_DENY") is not True:
  deny("R26_A6_FENCE_EVIDENCE_INVALID")
 if r25.get("stage")!="CERT-A19-R25" or r25.get("final_installed_package_count")!=40:
  deny("R25_OCI_PACKAGE_EVIDENCE_INVALID")
 if r25.get("original_base_digest")!=BASE or r25.get("ELF_objects_static_readelf_count")!=153:
  deny("R25_STATIC_BASE_DRIFT")
 sources={name:code(name,blob) for name,blob in BLOBS.items()}
 worker=ast.parse(sources["scripts/runtime_a2_worker.py"])
 core=ast.parse(sources["naseri_markets/core_api_v1.py"])
 a1=ast.parse(sources["naseri_markets/multilang_runtime_a1.py"])
 plugin=ast.parse(sources["naseri_markets/secure_plugin_runtime_v1.py"])
 a6=ast.parse(sources["naseri_markets/runtime_a6_dispatch_fence.py"])
 utc=ast_fn(core,"_utc")
 child=ast_fn(worker,"_child")
 worker_process=ast_fn(worker,"process")
 run_oci=ast_fn(a1,"_run_oci")
 polyglot=ast_fn(a1,"build_polyglot_command")
 docker_cmd=ast_fn(plugin,"build_run_command")
 daemon=ast_fn(plugin,"_ensure_rootless_daemon")
 fence=ast_fn(a6,"require_worker_launch")
 if not all(x in utc for x in ("value.tzinfo is None","value.utcoffset() is None","value.astimezone(UTC)")):
  deny("CORE_UTC_CONTRACT_DRIFT")
 if "NODE_PATH" not in child or "PATH" not in child or "'TZ'" in child or '"TZ"' in child:
  deny("RUNTIME_CHILD_ENV_CONTRACT_DRIFT")
 if "'observed_at': event['observed_at']" not in worker_process:
  deny("WORKER_EVENT_TIME_CONTRACT_DRIFT")
 if "require_worker_launch(profile, payload)" not in run_oci or "time.monotonic()" not in run_oci:
  deny("PROCESS_A6_OR_DEADLINE_CONTRACT_DRIFT")
 if "build_run_command(profile.policy, name)" not in polyglot:
  deny("POLYGLOT_INDEPENDENT_POLICY_NOT_REUSED")
 flags=("--runtime=runsc","--network=none","--ipc=none","--read-only","--cap-drop=ALL",
        "--security-opt=no-new-privileges","--pids-limit=32","--user=65534:65534",
        "--pull=never")
 if not all(flag in docker_cmd for flag in flags):deny("STATIC_CONTAINMENT_FLAGS_DRIFT")
 if "name=rootless" not in daemon or "ROOTLESS_DOCKER_NOT_VERIFIED" not in daemon:
  deny("ROOTLESS_DAEMON_SOURCE_CHECK_DRIFT")
 if "raise RuntimeA6Denied('A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED')" not in fence:
  deny("A6_NO_HARD_DENY")
 positive,negative=validate_vectors()
 manifest={"contract":"R27_FIXED_BENIGN_INPUTS_ONLY_V1",
  "timezone_policy":"EXPLICIT_UTC_OR_FIXED_NUMERIC_OFFSET_FOR_AUDITED_FIXTURE_VECTORS_ONLY",
  "named_iana_zone_behavior":"NOT_AUTHORIZED_FOR_PARITY_CLAIM_AND_UNTESTED",
  "product_guest_input_restriction_implemented":False,
  "vectors":[*VECTORS],"negative_vectors":[*INVALID],
  "node18_vs_node24_timezone_parity_executed":False,
  "python3_12_zoneinfo_supported_in_frozen_OCI":False,
  "wasmtime_timezone_support_executed":False,
  "typescript_compiler_executed":False,
  "no_named_zone_database_in_R25_OCI":True,
  "reference_calculation_only_trusted_host_python_datetime":True}
 (root/"r27-vectors.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
 report={"stage":"CERT-A19-R27",
  "verdict":"BENIGN_EXPLICIT_OFFSET_VECTOR_CONTRACT_AND_STATIC_A6_HOST_PREFLIGHT_PASS__GUEST_EXECUTION_BLOCKED",
  "r26_evidence_sha256":R26_SHA,"r25_evidence_sha256":R25_SHA,
  "historical_pinned_oci":BASE,"installed_packages_from_R25":40,
  "preexisting_ELF_static_count":153,
  "unchanged_main_git_blob_checks":len(sources),
  "approved_static_fixture_count":positive,"negative_fixture_count":negative,
  "fixture_contract_sha256":sha(asbytes(manifest)),
  "named_iana_fixture_execution_permitted":False,
  "host_utc_offset_math_reference_pass":True,
  "source_host_rootless_runsc_flags_static_presence":True,
  "physical_rootless_gvisor_host_verified":False,
  "A6_unchanged_unconditional_hard_denial":True,
  "node18_24_parity_executed":False,
  "runtime_python_javascript_typescript_wasmtime_executed":False,
  "worker_image_built_or_started":False,
  "tzdata_installed_or_working_zoneinfo_proven":False,
  "original_199_findings_review_open":True,"CVEs_certified_closed":0,
  "production_authorized":False}
 (root/"r27-report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
 print("CERT_A19_R27_MAIN_SOURCE_BLOBS_PASS="+str(len(sources)))
 print("CERT_A19_R27_EXPLICIT_OFFSET_CASES_PASS="+str(positive))
 print("CERT_A19_R27_NEGATIVE_CASES_REJECTED="+str(negative))
 print("CERT_A19_R27_HOST_SECURITY_CODE_STATIC_ONLY__A6_HARD_DENY")
 print("CERT_A19_R27_GUEST_CODE_NOT_EXECUTED_199_OPEN")

if __name__=="__main__":main()
