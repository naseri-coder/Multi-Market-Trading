"""CERT-A19-R29: offline host-accreditation policy self-test, NEVER a host certification.

All inputs in this stage are synthetic policy fixtures or source metadata. This
module may not execute Docker, runsc, container images, code guests, or a Worker.
The verified R28 GitHub Actions host is expressly NOT authorized as rootless.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re

STAGE="CERT-A19-R29"
GVISOR_TAG="release-20261005.0"
GVISOR_TAG_OBJECT="e1987e70c70be06e89be3bad7934f02ec715e333"
GVISOR_SOURCE_COMMIT="97e8e896904cb364319cd9758241d3f0bd27a6f4"
GVISOR_TARBALL="gvisor-x86_64.tar.zstd"
GVISOR_SHA256="0a8a9058b9f11791a2097f03190c2ddc5b963c3dbee5bb9fd8497f4801c42f92"
GVISOR_SUMS_SHA256="dc3ea2d7486b9c07d9ad0ae3880b69a1a020708b83c4a8fe3bb781a871ef2308"
R28_HOST_SHA256="94ad37614eb28a995d447148b9a90673831240735d399b5ae1d5a53e366a97b6"
R28_HOST_CONTRACT_SHA256="384fa24c19fcac781a1d5587dddf15f46d0644576b2682b92251e9fac73f24b7"
R27_VECTORS_SHA256="6f9c7847c5029d29f0f29fe5beae94c318bfc9a8c4f7f4a6512052e667812f1d"

def deny(code):
    raise ValueError(STAGE+"_"+code)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def cwd():
    required={"GITHUB_ACTIONS":"true","MMT_NONPRODUCTION":"1",
              "GITHUB_REF":"refs/heads/cert-a19-byte-audit-run"}
    if any(os.environ.get(k)!=v for k,v in required.items()):
        deny("NONPRODUCTION_SCRATCH_ONLY")
    root=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r29"
    if not root.is_dir() or root.is_symlink():
        deny("SCOPED_EVIDENCE_DIR_ABSENT")
    return root

def check_release_manifest(raw):
    if sha(raw)!=GVISOR_SUMS_SHA256:
        deny("OFFICIAL_CHECKSUM_MANIFEST_BYTES_DRIFT")
    records={}
    for line in raw.decode("utf-8","strict").splitlines():
        m=re.fullmatch(r"([0-9a-f]{64})[ \t]+\*?([A-Za-z0-9_.-]+)",line.strip())
        if not m:
            deny("MALFORMED_RELEASE_CHECKSUM_RECORD")
        checksum,filename=m.groups()
        if filename in records:
            deny("DUPLICATE_RELEASE_FILENAME")
        records[filename]=checksum
    if records.get(GVISOR_TARBALL)!=GVISOR_SHA256:
        deny("EXACT_ARCHIVE_HASH_NOT_IN_RELEASE_MANIFEST")
    return records

def check_host_claim(e):
    """Pure predicate: no actual host interrogation or runtime invocation."""
    failures=[]
    if e.get("evidence_type")!="independently_attested_host":
        failures.append("INDEPENDENT_HOST_EVIDENCE_MISSING")
    if e.get("synthetic_test_data") is not False:
        failures.append("SYNTHETIC_OR_UNDECLARED_ORIGIN")
    if e.get("explicit_user_authorization") is not True:
        failures.append("NO_EXPLICIT_HOST_AUTHORIZATION")
    if e.get("separate_independent_auditor_approval") is not True:
        failures.append("INDEPENDENT_AUDIT_APPROVAL_MISSING")
    if e.get("nonproduction_isolated_host") is not True:
        failures.append("ISOLATED_NONPRODUCTION_HOST_UNPROVEN")
    if e.get("not_production_or_telmivo") is not True:
        failures.append("PRODUCTION_SEPARATION_UNPROVEN")
    if e.get("daemon_is_rootless") is not True:
        failures.append("ROOTLESS_DAEMON_UNPROVEN")
    if e.get("rootful_fallback_disabled") is not True:
        failures.append("ROOTFUL_FALLBACK_POSSIBLE")
    if e.get("runsc_registered_as_runtime") is not True:
        failures.append("RUNSC_RUNTIME_NOT_REGISTERED")
    if e.get("runsc_binary_sha256")!=GVISOR_SHA256:
        # There is no runsc individual binary hash available yet. This field is
        # a *release-archive hash*, not binary hash. DO NOT certify based on it.
        failures.append("RUNSC_EXECUTABLE_DIGEST_NOT_INDEPENDENTLY_PINNED")
    else:
        failures.append("RUNSC_EXECUTABLE_DIGEST_NOT_INDEPENDENTLY_PINNED")
    if e.get("runsc_release_archive_sha256")!=GVISOR_SHA256:
        failures.append("RUNSC_RELEASE_ARCHIVE_DIGEST_DRIFT")
    if e.get("runsc_release_tag")!=GVISOR_TAG:
        failures.append("RUNSC_RELEASE_VERSION_DRIFT")
    if e.get("publisher_attestation_verified") is not True:
        failures.append("PUBLISHER_ATTESTATION_NOT_INDEPENDENTLY_VERIFIED")
    if e.get("signing_identity_bound_to_release") is not True:
        failures.append("PUBLISHER_IDENTITY_NOT_PROVEN")
    if e.get("host_kernel_security_review_passed") is not True:
        failures.append("KERNEL_HOST_REVIEW_NOT_PASSED")
    if e.get("daemon_socket_owned_by_nonroot_principal") is not True:
        failures.append("ROOTLESS_SOCKET_CUSTODY_MISSING")
    if e.get("socket_unavailable_to_untrusted_users") is not True:
        failures.append("UNTRUSTED_SOCKET_ACCESS_NOT_REJECTED")
    if e.get("namespace_and_cgroup_limits_attested") is not True:
        failures.append("NAMESPACE_CGROUP_LIMITS_NOT_ATTESTED")
    if e.get("no_network_and_no_host_mounts_enforced") is not True:
        failures.append("NETWORK_OR_HOST_MOUNTS_NOT_DENIED")
    if e.get("read_only_and_no_caps_and_no_new_privileges") is not True:
        failures.append("GUEST_FILESYSTEM_PRIVILEGES_UNPROVEN")
    if e.get("trusted_image_digest_fixed") is not True:
        failures.append("IMMUTABLE_OCI_IMAGE_NOT_ATTESTED")
    if e.get("developer_fixture_hashes_reviewed") is not True:
        failures.append("FIXTURE_ARTIFACT_REVIEW_MISSING")
    if e.get("independent_escape_and_negative_checks_passed") is not True:
        failures.append("NEGATIVE_SECURITY_TESTS_NOT_PASSED")
    if e.get("A6_unconditionally_denied") is not True:
        failures.append("A6_DENY_NOT_PRESERVED")
    if e.get("guest_executed") is not False:
        failures.append("UNKNOWN_EXECUTION_STATUS")
    return sorted(set(failures))

def baseline_synthetic():
    e={
      "evidence_type":"synthetic_contract_unit_test",
      "synthetic_test_data":True,
      "explicit_user_authorization":True,
      "separate_independent_auditor_approval":True,
      "nonproduction_isolated_host":True,
      "not_production_or_telmivo":True,
      "daemon_is_rootless":True,
      "rootful_fallback_disabled":True,
      "runsc_registered_as_runtime":True,
      "runsc_binary_sha256":"not-downloaded-or-signed",
      "runsc_release_archive_sha256":GVISOR_SHA256,
      "runsc_release_tag":GVISOR_TAG,
      "publisher_attestation_verified":False,
      "signing_identity_bound_to_release":False,
      "host_kernel_security_review_passed":True,
      "daemon_socket_owned_by_nonroot_principal":True,
      "socket_unavailable_to_untrusted_users":True,
      "namespace_and_cgroup_limits_attested":True,
      "no_network_and_no_host_mounts_enforced":True,
      "read_only_and_no_caps_and_no_new_privileges":True,
      "trusted_image_digest_fixed":True,
      "developer_fixture_hashes_reviewed":True,
      "independent_escape_and_negative_checks_passed":True,
      "A6_unconditionally_denied":True,
      "guest_executed":False
    }
    return e

def test_policy():
    obj=baseline_synthetic()
    base=check_host_claim(obj)
    required={
      "INDEPENDENT_HOST_EVIDENCE_MISSING","SYNTHETIC_OR_UNDECLARED_ORIGIN",
      "RUNSC_EXECUTABLE_DIGEST_NOT_INDEPENDENTLY_PINNED",
      "PUBLISHER_ATTESTATION_NOT_INDEPENDENTLY_VERIFIED","PUBLISHER_IDENTITY_NOT_PROVEN"
    }
    if not required.issubset(set(base)):
        deny("SYNTHETIC_DATA_INCORRECTLY_ACCREDITED")
    tests={
     "authorization_absent":("explicit_user_authorization",False,"NO_EXPLICIT_HOST_AUTHORIZATION"),
     "auditor_absent":("separate_independent_auditor_approval",False,"INDEPENDENT_AUDIT_APPROVAL_MISSING"),
     "production_mixed":("not_production_or_telmivo",False,"PRODUCTION_SEPARATION_UNPROVEN"),
     "daemon_rootful":("daemon_is_rootless",False,"ROOTLESS_DAEMON_UNPROVEN"),
     "rootful_fallback":("rootful_fallback_disabled",False,"ROOTFUL_FALLBACK_POSSIBLE"),
     "runsc_unregistered":("runsc_registered_as_runtime",False,"RUNSC_RUNTIME_NOT_REGISTERED"),
     "archive_tampered":("runsc_release_archive_sha256","0"*64,"RUNSC_RELEASE_ARCHIVE_DIGEST_DRIFT"),
     "socket_owner_root":("daemon_socket_owned_by_nonroot_principal",False,"ROOTLESS_SOCKET_CUSTODY_MISSING"),
     "socket_access_public":("socket_unavailable_to_untrusted_users",False,"UNTRUSTED_SOCKET_ACCESS_NOT_REJECTED"),
     "host_mount_allowed":("no_network_and_no_host_mounts_enforced",False,"NETWORK_OR_HOST_MOUNTS_NOT_DENIED"),
     "escapes_not_checked":("independent_escape_and_negative_checks_passed",False,"NEGATIVE_SECURITY_TESTS_NOT_PASSED"),
     "a6_removed":("A6_unconditionally_denied",False,"A6_DENY_NOT_PRESERVED"),
     "guest_executed":("guest_executed",True,"UNKNOWN_EXECUTION_STATUS")
    }
    result=[]
    for label,(key,value,code) in tests.items():
        case=copy.deepcopy(obj);case[key]=value
        reasons=check_host_claim(case)
        if code not in reasons:
            deny("NEGATIVE_CASE_FALSE_ACCEPT_"+label)
        result.append({"case":label,"expected_blocker":code,"fail_closed":True})
    # Historical R28 host deliberately fails: requires independent real evidence.
    r28={"evidence_type":"github_ephemeral_runner_probe",
         "synthetic_test_data":False,"daemon_is_rootless":False,
         "runsc_registered_as_runtime":False,"A6_unconditionally_denied":True,
         "guest_executed":False}
    r28_fail=check_host_claim(r28)
    for msg in ("ROOTLESS_DAEMON_UNPROVEN","RUNSC_RUNTIME_NOT_REGISTERED",
                "INDEPENDENT_HOST_EVIDENCE_MISSING","NO_EXPLICIT_HOST_AUTHORIZATION"):
        if msg not in r28_fail:
            deny("R28_HOST_WRONGLY_APPROVED")
    return base,result,r28_fail

def main():
    root=cwd()
    checksums=(root/"gvisor-SHA256SUMS").read_bytes()
    listing=check_release_manifest(checksums)
    base,neg,r28=test_policy()
    report={
      "stage":STAGE,
      "verdict":"HOST_ACREDITATION_POLICY_AND_13_NEGATIVE_CONTROLS_PASS__REAL_HOST_UNAUTHORIZED__A6_DENY",
      "gvisor_release_tag":GVISOR_TAG,
      "gvisor_tag_object_sha":GVISOR_TAG_OBJECT,
      "gvisor_tag_source_commit":GVISOR_SOURCE_COMMIT,
      "gvisor_github_tag_verified_signature":False,
      "release_checksum_manifest_full_sha256":sha(checksums),
      "gvisor_x86_64_release_tarball_expected_sha256":GVISOR_SHA256,
      "release_archive_bytes_downloaded":False,
      "runsc_binary_extracted_or_executed":False,
      "independent_publisher_signature_verified":False,
      "release_checksum_listing_entry_count":len(listing),
      "source_R28_live_host_json_sha256":R28_HOST_SHA256,
      "source_R28_fixture_contract_json_sha256":R28_HOST_CONTRACT_SHA256,
      "source_R27_fixed_vectors_sha256":R27_VECTORS_SHA256,
      "synthetic_preflight_fails_closed":base,
      "negative_policy_cases":neg,
      "R28_actual_observation_rejected_by_policy":r28,
      "policy_engine_unit_test_not_host_accreditation":True,
      "nonproduction_machine_accredited":False,
      "independent_rootless_gvisor_host_certified":False,
      "guest_fixture_or_worker_executed":False,
      "main_or_production_mutated":False,
      "199_historical_Critical_High_findings_review_open":True,
      "CVE_closures":0,
      "A6_hard_DENY":True
    }
    dest=root/"r29-policy-report.json"
    dest.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("CERT_A19_R29_RELEASE_SHA256SUMS_SNAPSHOT_MATCH_PASS")
    print("CERT_A19_R29_NEGATIVE_CASES="+str(len(neg)))
    print("CERT_A19_R29_R28_ROOTLESS_RUNSC_HOST_DENIED")
    print("CERT_A19_R29_NO_RUNTIME_EXECUTION_A6_DENY_199_OPEN")

if __name__=="__main__":
    main()
