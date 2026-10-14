"""CERT-A19-R16: atomic Wolfi APKINDEX custody and four root archive checks.

Strictly nonproduction. No Worker image, guest code or package install.
An upstream signer-checked index alone is not per-archive byte authentication.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

BASE="cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
REPO="https://apk.cgr.dev/chainguard"
ROOTS={
    "glibc-2.44": "2.44-r8",
    "python-3.12": "3.12.15-r3",
    "python-3.12-base": "3.12.15-r3",
    "nodejs-24": "24.22.0-r0",
}
MAX_ARCHIVE=90_000_000
MAX_TOTAL=175_000_000
MAX_INDEX=35_000_000
URL_RE=re.compile(r"^[a-z0-9.-]+$")
NAME_RE=re.compile(r"^[a-zA-Z0-9_+~.-]+$")


def deny(code):
    raise ValueError("CERT_A19_R16_"+code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def work():
    if (os.environ.get("GITHUB_ACTIONS")!="true"
        or os.environ.get("MMT_NONPRODUCTION")!="1"
        or os.environ.get("GITHUB_REF")!="refs/heads/cert-a19-byte-audit-run"):
        deny("ISOLATED_NONPRODUCTION_ONLY")
    d=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r16"
    if not d.is_dir():
        deny("EVIDENCE_DIR_MISSING")
    return d


def read(path, max_bytes):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        deny("EVIDENCE_FILE_ABSENT_OR_UNBOUNDED")
    return path.read_bytes()


def repo_identity(d):
    base=read(d/"base.txt",300).decode().strip()
    if base != BASE or read(d/"cosign.status",150).decode().strip()!="VERIFIED_EXACT_PUBLISHER":
        deny("BASE_PROVENANCE_UNVERIFIED")
    observed=read(d/"repositories-from-base",2000).decode().splitlines()
    if [x.strip() for x in observed if x.strip() and not x.startswith("#")] != [REPO]:
        deny("REPOSITORY_IDENTITY_DRIFT")
    keys=sorted((d/"keys").rglob("*.pub"))
    if not 1 <= len(keys) <= 10:
        deny("BASE_SIGNING_KEY_COUNT_INVALID")
    return [{"name":k.name,"sha256":sha(read(k,10_000))} for k in keys]


def parse_index(data):
    if not 1_000_000 < len(data) < MAX_INDEX:
        deny("INDEX_SIZE_OUT_OF_BOUNDS")
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as t:
        ms=[m for m in t.getmembers() if m.name=="APKINDEX" and m.isfile()]
        if len(ms)!=1 or ms[0].size>65_000_000:
            deny("INDEX_FORMAT_INVALID")
        f=t.extractfile(ms[0])
        if f is None:
            deny("INDEX_PAYLOAD_MISSING")
        txt=f.read(65_000_001)
    if len(txt)>65_000_000:
        deny("INDEX_DECOMPRESS_UNBOUNDED")
    records={}
    count=0
    for para in txt.decode("utf-8","strict").strip().split("\n\n"):
        fields={}
        for line in para.splitlines():
            if len(line)>2 and line[1]==":" and line[0].isalpha():
                if line[0] in fields: deny("DUPLICATE_INDEX_FIELD")
                fields[line[0]]=line[2:]
        if all(k in fields for k in ("P","V","S","C")):
            key=fields["P"],fields["V"]
            if key in records:deny("DUPLICATE_PACKAGE_NAME_VERSION")
            records[key]=fields
            count+=1
    if not 1000<count<150_000:
        deny("INDEX_PACKAGE_COUNT_OUT_OF_BOUNDS")
    return records,count


def report_base(d):
    keys=repo_identity(d)
    b=read(d/"APKINDEX.tar.gz",MAX_INDEX)
    if read(d/"index-signature.status",150).decode().strip()!="NATIVE_APK_ACCEPTED_SIGNED_SNAPSHOT":
        deny("NATIVE_SIGNED_INDEX_NOT_VERIFIED")
    entries,count=parse_index(b)
    entries_roots=[]
    for name,ver in sorted(ROOTS.items()):
        meta=entries.get((name,ver))
        if meta is None: deny("FROZEN_ROOT_VERSION_ABSENT_FROM_NEW_INDEX")
        namever=f"{name}-{ver}"
        if not NAME_RE.fullmatch(namever): deny("BAD_PACKAGE_NAME")
        size=int(meta["S"])
        if not 100<size<MAX_ARCHIVE:deny("ROOT_ARCHIVE_SIZE_INVALID")
        entries_roots.append({
            "name":name,"version":ver,
            "filename":namever+".apk",
            "signed_index_size":size,
            "index_control_checksum":meta["C"],
            "declared_dependencies":meta.get("D","").split(),
            "url":REPO+"/x86_64/"+namever+".apk",
            "native_archive_signature_verified":False,
        })
    o={
        "stage":"CERT-A19-R16",
        "phase":"SIGNED_INDEX_BYTES_FROZEN_ARCHIVES_NOT_YET_VERIFIED",
        "signed_base_digest":BASE,
        "base_keys_sha256":keys,
        "repository_source":REPO,
        "repository_arch":"x86_64",
        "snapshot_apkindex_sha256":sha(b),
        "snapshot_apkindex_size":len(b),
        "snapshot_exact_raw_bytes_retained_in_run_artifact":True,
        "snapshot_is_not_assumed_equal_to_R14":True,
        "older_R14_index_sha256":"15f8b555714bfe44b0f4de0ee24910e0533f7b4fbb4a650cf533115c6a4f281a",
        "native_signed_index_verification":"PASS",
        "package_index_record_count":count,
        "requested_direct_package_versions":ROOTS,
        "direct_package_entries":entries_roots,
        "native_apk_verify_result":"NOT_RUN",
        "transitive_solver_state":"NOT_VERIFIED",
        "all_transitive_apk_files_verified":False,
        "package_version_control_checksum_matched_to_downloaded_archive":False,
        "native_abi_qualification":"NOT_RUN",
        "four_language_parity":"NOT_RUN",
        "worker_or_untrusted_code_executed":False,
        "trusted_apk_utility_executed_in_restricted_container":True,
        "independent_host_certified":False,
        "original_critical_high_review_open":199,
        "cve_closures_certified":0,
        "runtime_a6":"DENY",
        "production_authorized":False
    }
    (d/"r16-report.json").write_text(json.dumps(o,sort_keys=True,indent=2)+"\n")
    print("R16_SIGNED_APKINDEX_SNAPSHOT_SHA="+o["snapshot_apkindex_sha256"])
    print("R16_PACKAGE_RECORDS="+str(count))


def url_safe(url):
    p=urlsplit(url)
    host=(p.hostname or "").lower()
    if (p.scheme!="https" or p.username or p.password or p.port not in (None,443)
        or not URL_RE.fullmatch(host)
        or (host!="apk.cgr.dev" and not host.endswith(".r2.cloudflarestorage.com"))):
        deny("UNEXPECTED_UNTRUSTED_DOWNLOAD_REDIRECT")
    return host


class RedirectGuard(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        url_safe(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


opener=build_opener(RedirectGuard())


def fetch():
    d=work()
    report=json.loads(read(d/"r16-report.json",150_000))
    if report.get("phase")!="SIGNED_INDEX_BYTES_FROZEN_ARCHIVES_NOT_YET_VERIFIED":
        deny("EXPECTED_FROZEN_INDEX_REPORT")
    folder=d/"apk"
    folder.mkdir(mode=0o755,exist_ok=False)
    total=0
    for pkg in report["direct_package_entries"]:
        url=pkg["url"]
        url_safe(url)
        with opener.open(Request(url,headers={"User-Agent":"MMT-A19-R16-audit-only"}),timeout=50) as response:
            host=url_safe(response.url)
            blob=response.read(MAX_ARCHIVE+1)
        if len(blob)!=pkg["signed_index_size"] or len(blob)>MAX_ARCHIVE:
            deny("INDEX_DECLARED_ARCHIVE_SIZE_MISMATCH")
        total+=len(blob)
        if total>MAX_TOTAL:deny("DOWNLOAD_TOTAL_EXCEEDED")
        f=folder/pkg["filename"]
        f.write_bytes(blob)
        f.chmod(0o644)
        pkg["measured_full_apk_sha256"]=sha(blob)
        pkg["downloaded_bytes"]=len(blob)
        pkg["verified_https_distribution_host"]=host
        print("R16_DOWNLOADED_INDEX_LISTED="+pkg["filename"])
    report["phase"]="ARCHIVES_DOWNLOADED_PENDING_SIGNATURES"
    report["downloaded_total_bytes"]=total
    (d/"r16-report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")


def finalize():
    d=work()
    report=json.loads(read(d/"r16-report.json",150_000))
    if report["phase"]!="ARCHIVES_DOWNLOADED_PENDING_SIGNATURES":deny("NO_ARCHIVE_STATE")
    native=(d/"apk-verify.status")
    if not native.is_file() or native.read_text().strip()!="FOUR_ARCHIVES_CRYPTOGRAPHICALLY_VERIFIED":
        deny("APK_ARCHIVE_SIGNATURE_NOT_PROVEN")
    log=read(d/"apk-verify.log",20_000).decode()
    if any(q in log.lower() for q in ("untrusted","bad signature","error:","failed")):
        deny("NATIVE_APK_SIGNATURE_LOG_FAILED")
    for pkg in report["direct_package_entries"]:
        data=read(d/"apk"/pkg["filename"],MAX_ARCHIVE)
        if sha(data)!=pkg["measured_full_apk_sha256"]:
            deny("APK_FILE_TAMPERED_AFTER_SIGNATURE")
        pkg["native_archive_signature_verified"]=True
    report["phase"]="FOUR_SIGNED_DIRECT_APK_ARCHIVES_SHA256_VERIFIED_TRANSITIVE_CLOSURE_UNRESOLVED"
    report["native_apk_verify_result"]="PASS"
    report["direct_package_signatures_verified_count"]=4
    report["full_direct_archive_sha256_frozen"]=True
    report["complete_transitive_dependency_closure"]=False
    solverfile=d/"solver.state"
    if solverfile.is_file():
        result=solverfile.read_text().strip()
        report["transitive_solver_state"]=result
    # No proof of complete resolver-selected archive closure, regardless of solver output.
    report["all_transitive_apk_files_verified"]=False
    (d/"r16-report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("R16_4_DIRECT_ROOT_APK_SIGNATURE_AND_SHA256_PASS")
    print("R16_FULL_TRANSITIVE_SOLVER_ARCHIVE_CLOSURE_STILL_UNVERIFIED__A6_DENY")


if __name__=="__main__":
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument("phase",choices=("index","fetch","finalize"))
    phase=a.parse_args().phase
    {"index":lambda:report_base(work()),"fetch":fetch,"finalize":finalize}[phase]()
