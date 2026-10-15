"""CERT-A19-R28 — read-only physical host boundary/preflight evidence.

Only trusted host metadata commands run (docker info/version, command availability).
NEVER executes runsc, docker run/start, Python/Node/TypeScript/WASM guest, Worker.
The hosted Actions machine CANNOT self-attest independent confinement approval.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

R27_REPORT_SHA = "818e8b3165c53404d1e33ac7bfb04d51886288b5c40b37155681f756485dcf5b"
R27_VECTORS_SHA = "6f9c7847c5029d29f0f29fe5beae94c318bfc9a8c4f7f4a6512052e667812f1d"
R27_CANON_SHA = "0c1836b766d9cd93399ae86d2f093be2d7de85593077489d66ced0b46fb48fe0"
BASE = "cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
NEEDED_DOCKER_FLAGS = [
 "--runtime=runsc","--network=none","--ipc=none","--read-only",
 "--cap-drop=ALL","--security-opt=no-new-privileges",
 "--pids-limit=32","--user=65534:65534","--pull=never"
]
def fail(k):raise RuntimeError("CERT_A19_R28_"+k)
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p,cap):
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=cap:
        fail("INPUT_MISSING_OR_TOO_LARGE")
    return p.read_bytes()
def process(args):
    try:
        out=subprocess.run(args,capture_output=True,text=True,timeout=12,check=False)
        return {"ok":out.returncode==0,"stdout":out.stdout[:3500],"returncode":out.returncode}
    except (FileNotFoundError,OSError,subprocess.TimeoutExpired):
        return {"ok":False,"stdout":"","returncode":None}
def main():
    required={"GITHUB_ACTIONS":"true","GITHUB_REF":"refs/heads/cert-a19-byte-audit-run","MMT_NONPRODUCTION":"1"}
    if any(os.environ.get(k)!=v for k,v in required.items()):
        fail("FIXED_NONPRODUCTION_SCRATCH_BRANCH_ONLY")
    root=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r28"
    if not root.is_dir():fail("SCOPED_DIRECTORY_MISSING")
    rb=read(root/"r27-report.json",12000)
    vb=read(root/"r27-vectors.json",16000)
    if sha(rb)!=R27_REPORT_SHA or sha(vb)!=R27_VECTORS_SHA:
        fail("IMMUTABLE_R27_EVIDENCE_CHANGED")
    report=json.loads(rb)
    vec=json.loads(vb)
    canonical=json.dumps(vec,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    if (sha(canonical)!=R27_CANON_SHA or report.get("stage")!="CERT-A19-R27"
        or report.get("A6_unchanged_unconditional_hard_denial") is not True
        or report.get("physical_rootless_gvisor_host_verified") is not False
        or report.get("installed_packages_from_R25")!=40
        or report.get("approved_static_fixture_count")!=7
        or report.get("negative_fixture_count")!=4
        or vec.get("product_guest_input_restriction_implemented") is not False):
        fail("R27_UNSAFE_ASSUMPTION_OR_VECTOR_DRIFT")
    # Only inspect the actual CLI's current daemon target; an alternate
    # independent authorized remote host is NOT discovered from this result.
    docker_bin=shutil.which("docker")
    runsc_bin=shutil.which("runsc")
    rootlesskit_bin=shutil.which("rootlesskit")
    uid=os.geteuid()
    docker_version=process(["docker","version","--format","{{.Server.Version}}"]) if docker_bin else {"ok":False}
    docker_security=process(["docker","info","--format","{{json .SecurityOptions}}"]) if docker_bin else {"ok":False}
    docker_runtimes=process(["docker","info","--format","{{range $k, $v := .Runtimes}}{{$k}} {{end}}"]) if docker_bin else {"ok":False}
    sec=docker_security.get("stdout","")
    available_runtimes=docker_runtimes.get("stdout","").strip().split() if docker_runtimes.get("ok") else []
    # Do not leak daemon address/socket paths, labels, hostnames, username,
    # env vars, external networks, credentials or process command lines.
    rootless_current_target = bool(docker_security.get("ok") and "name=rootless" in sec)
    runsc_registered_current_target = bool(docker_runtimes.get("ok") and "runsc" in available_runtimes)
    rootless_socket = Path("/run/user")/str(uid)/"docker.sock"
    rootless_socket_present = rootless_socket.is_socket() if rootless_socket.exists() else False
    kernel_ns=Path("/proc/self/ns/user").exists() and Path("/proc/self/ns/mnt").exists()
    cgroup2=Path("/sys/fs/cgroup/cgroup.controllers").exists()
    options={"network_disabled":"--network=none" in NEEDED_DOCKER_FLAGS,
      "ipc_disabled":"--ipc=none" in NEEDED_DOCKER_FLAGS,
      "readonly_root":"--read-only" in NEEDED_DOCKER_FLAGS,
      "capabilities_dropped":"--cap-drop=ALL" in NEEDED_DOCKER_FLAGS,
      "no_new_privileges":"--security-opt=no-new-privileges" in NEEDED_DOCKER_FLAGS,
      "pids_bounded":"--pids-limit=32" in NEEDED_DOCKER_FLAGS,
      "nonroot_guest":"--user=65534:65534" in NEEDED_DOCKER_FLAGS,
      "gvisor_selected":"--runtime=runsc" in NEEDED_DOCKER_FLAGS,
      "no_implicit_image_pull":"--pull=never" in NEEDED_DOCKER_FLAGS}
    if len(options)!=9 or not all(options.values()):fail("BENIGN_TEST_POLICY_NOT_FAIL_CLOSED")
    # Static plan with mandatory cleanup and refusal conditions; no
    # commands to execute guest fixtures and no authorization to launch.
    plan={
      "stage":"CERT-A19-R28","kind":"BENIGN_FIXTURE_EXECUTION_PLAN_ONLY",
      "frozen_vector_sha256":R27_VECTORS_SHA,
      "allowed_guest_sources":"AUDITED_AND_HASH_PINNED_DEVELOPER_FIXED_FIXTURES_ONLY",
      "unknown_user_code":"DENIED",
      "network":"none","filesystem":"read-only",
      "guest_uid_gid":"65534:65534","capabilities":"ALL dropped",
      "no_new_privileges":True,"ipc":"none","pids_limit":32,
      "cpu_limit":"MUST_BE_EXPLICITLY_SET_BEFORE_EXECUTION",
      "memory_limit":"MUST_BE_EXPLICITLY_SET_BEFORE_EXECUTION",
      "read_only_inputs":"MUST_BE_EXACT_HASH_PINNED_NO_BROKER_SECRETS",
      "seccomp":"MUST_BE_INDEPENDENTLY_REVIEWED",
      "host_daemon":"MUST_BE_ATTESTED_ROOTLESS_AND_ISOLATED",
      "gvisor_runtime":"MUST_BE_SIGNED_PINNED_AND_ACTUALLY_REGISTERED",
      "privileged_mounts":"FORBIDDEN",
      "no_container_socket_mount":True,
      "cleanup":"MUST_BE_PROVED_AFTER_EACH_DISPOSABLE_FIXTURE",
      "A6_production_fence":"MUST_REMAIN_DENY",
      "test_image":"NOT_AUTHORIZED_FOR_BUILD_OR_LAUNCH_IN_R28",
      "fixture_execution_performed":False,
      "future_host_signoff_required":True
    }
    (root/"r28-fixture-host-contract.json").write_text(json.dumps(plan,sort_keys=True,indent=2)+"\n")
    # A hosted GitHub runner is not an independently entrusted user-owned
    # rootless/gVisor host, even if individual executable names exist.
    independently_certified=False
    actual_host_pass=bool(rootless_current_target and runsc_registered_current_target
       and runsc_bin and cgroup2 and kernel_ns)
    result={
      "stage":"CERT-A19-R28",
      "verdict":"LIVE_HOST_INSPECTION_COMPLETED__INDEPENDENT_ROOTLESS_GVISOR_HOST_NOT_CERTIFIED__A6_DENY",
      "github_hosted_temporary_runner":True,
      "previous_R27_report_sha256":R27_REPORT_SHA,
      "previous_R27_fixture_sha256":R27_VECTORS_SHA,
      "actual_current_Docker_daemon_query_success":bool(docker_version.get("ok") and docker_security.get("ok") and docker_runtimes.get("ok")),
      "Docker_server_version":docker_version.get("stdout","").strip() if docker_version.get("ok") else None,
      "Docker_security_rootless_option_observed":rootless_current_target,
      "Docker_registered_runsc_runtime_observed":runsc_registered_current_target,
      "host_runsc_in_PATH":bool(runsc_bin),
      "host_rootlesskit_in_PATH":bool(rootlesskit_bin),
      "user_rootless_Docker_socket_present":rootless_socket_present,
      "runner_process_is_root":uid==0,
      "user_and_mount_namespace_interfaces_present":kernel_ns,
      "cgroups_v2_controller_interface_present":cgroup2,
      "all_required_static_launch_flags_present":True,
      "additional_cpu_memory_seccomp_host_configuration_certified":False,
      "actual_host_environment_confinement_minimum_observed":actual_host_pass,
      "independent_host_ownership_and_security_review_certified":independently_certified,
      "physical_rootless_gvisor_host_certified":False,
      "R27_only_fixed_benign_vector_count":7,
      "R27_only_negative_vector_count":4,
      "guest_program_or_Worker_executed":False,
      "container_or_guest_launched_in_R28":False,
      "no_network_scan_or_package_install_performed":True,
      "cleanup_proof_for_actual_guest":"NOT_APPLICABLE_NO_GUEST_STARTED",
      "no_host_or_runtime_settings_mutated":True,
      "production_fence_A6_hard_DENY":True,
      "original_199_Critical_High_review_open":True,
      "CVE_closures":0,
      "production_authorized":False
    }
    (root/"r28-host-live-preflight.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("CERT_A19_R28_ROOTLESS_CURRENT_DAEMON="+str(rootless_current_target))
    print("CERT_A19_R28_RUNSC_RUNTIME_REGISTERED="+str(runsc_registered_current_target))
    print("CERT_A19_R28_HOST_RUNSC_PRESENT="+str(bool(runsc_bin)))
    print("CERT_A19_R28_INDEPENDENT_HOST_CERTIFIED=FALSE")
    print("CERT_A19_R28_A6_HARD_DENY__199_OPEN__NO_GUEST_EXECUTION")

if __name__=="__main__":main()
