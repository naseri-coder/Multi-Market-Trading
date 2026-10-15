"""CERT-A19-R30 signed gVisor apt Release -> Packages -> .deb -> runsc inventory.

Nonproduction repository custody only. Downloaded native binaries are NEVER
installed, loaded or executed. A vendor-HTTPS fetched apt signing key is not an
independently pinned or audited key: keep this limitation explicit.
"""
from __future__ import annotations
import gzip
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timezone
import tempfile

ORIGIN="https://storage.googleapis.com/gvisor/releases/"
KEY_URL="https://gvisor.dev/archive.key"
R29_REPORT_SHA="16400ae6890cbc5aae0a26df3179ab91db049b2d8fbce60c8e45646af2b0b160"
GITHUB_TAG="release-20261005.0"
R29_TARBALL_SHA="0a8a9058b9f11791a2097f03190c2ddc5b963c3dbee5bb9fd8497f4801c42f92"
MAX_DEB=240_000_000
MAX_DECOMPRESSED_MEMBER=250_000_000

def stop(reason):raise RuntimeError("CERT_A19_R30_"+reason)
def sha(data):return hashlib.sha256(data).hexdigest()
def wd():
    required={"GITHUB_ACTIONS":"true","MMT_NONPRODUCTION":"1","GITHUB_REF":"refs/heads/cert-a19-byte-audit-run"}
    if any(os.environ.get(k)!=v for k,v in required.items()):stop("NONPRODUCTION_BRANCH_REQUIRED")
    folder=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r30"
    if folder.is_symlink() or not folder.is_dir():stop("SCOPED_WORKDIR_REQUIRED")
    return folder
def file(path,maximum):
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=maximum:
        stop("MISSING_OR_UNBOUNDED_FILE")
    return path.read_bytes()
def source_host(url):
    u=urlsplit(url)
    if u.scheme!="https" or u.username or u.password or u.port not in (None,443):
        stop("UNSAFE_SOURCE_SCHEME")
    h=(u.hostname or "").lower()
    if h not in ("storage.googleapis.com","gvisor.dev"):
        stop("SOURCE_HOST_NOT_AUTHORIZED")
    return h
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        source_host(url)
        return super().redirect_request(req,fp,code,msg,headers,url)
OPENER=urllib.request.build_opener(Redirect())
def fetch(url,limit):
    source_host(url)
    req=urllib.request.Request(url,headers={"User-Agent":"CERT-A19-R30-static-package-custody"})
    with OPENER.open(req,timeout=55) as r:
        source_host(r.url)
        raw=r.read(limit+1)
    if not 0<len(raw)<=limit:stop("DOWNLOAD_OVERSIZED_OR_EMPTY")
    return raw

def clean_rel(path):
    if not re.fullmatch(r"[A-Za-z0-9._/+\-]+",path):stop("PATH_NOT_SAFE_ASCII")
    q=PurePosixPath(path)
    if path.startswith("/") or ".." in q.parts or path.startswith("./") or str(q)!=path:
        stop("UNSAFE_RELATIVE_REPOSITORY_PATH")
    return path

def parse_release(b):
    text=b.decode("utf-8","strict")
    # InRelease and Release can contain a signed plaintext header.
    if text.startswith("-----BEGIN PGP SIGNED MESSAGE-----"):
        delim="\n\n"
        if delim not in text:stop("CLEARSIGN_NO_BODY")
        clean=text.split(delim,1)[1].split("-----BEGIN PGP SIGNATURE-----",1)[0]
        clean=clean.replace("\n- - ","\n- ")
    else:clean=text
    rows={}
    active=None
    for line in clean.splitlines():
        if line=="SHA256:":active="sha256";continue
        if re.match(r"^\S[^:\n]*:",line):active=None
        if active=="sha256" and line.startswith(" "):
            m=re.fullmatch(r"\s+([0-9a-f]{64})\s+(\d{1,12})\s+(\S+)\s*",line)
            if m:
                digest,length,p=m.groups()
                clean_rel(p)
                if p in rows:stop("DUPLICATE_APT_INDEX_SHA")
                rows[p]={"sha256":digest,"size":int(length)}
    if not rows:stop("SIGNED_RELEASE_LACKS_SHA256_TABLE")
    return rows

def parse_packages(b):
    out=[]
    for para in b.decode("utf-8","strict").split("\n\n"):
        fields={}
        for line in para.splitlines():
            if not line.strip() or line.startswith((" ","\t")):continue
            if ":" in line:
                k,v=line.split(":",1)
                if k in fields:stop("DUPLICATE_PACKAGE_FIELD")
                fields[k]=v.strip()
        if fields.get("Package")=="runsc" and fields.get("Architecture") in ("amd64","all"):
            need=("Version","SHA256","Filename","Size")
            if not all(fields.get(x) for x in need):stop("RUNSC_APT_FIELDS_MISSING")
            if not re.fullmatch(r"[0-9a-f]{64}",fields["SHA256"]):stop("PACKAGE_DIGEST_INVALID")
            clean_rel(fields["Filename"])
            size=int(fields["Size"])
            if not 1_000_000<size<MAX_DEB:stop("RUNSC_APT_PACKAGE_SIZE_INVALID")
            out.append(fields)
    if not out:stop("RUNSC_ABSENT_FROM_SIGNED_PACKAGE_INDEX")
    if len(out)!=1:stop("MULTIPLE_RUNSC_APT_CANDIDATES_NEED_EXPLICIT_VERSION_SELECTION")
    return out[0]

def gpg_run(*args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=25,check=False)
    return p

def check_controls(record):
    cases=[]
    def case(label,fn):
        try:fn()
        except (ValueError,RuntimeError,AssertionError):
            cases.append(label);return
        stop("NEGATIVE_CONTROL_NOT_REJECTED_"+label)
    case("bad_sha256",lambda: stop("SHA_NOT_MATCH") if sha(b"tampered")!="0"*64 else None)
    case("absolute_filename",lambda:clean_rel("/pool/runsc.deb"))
    case("path_traversal",lambda:clean_rel("pool/../../bad.deb"))
    case("redirect_host",lambda:source_host("https://evil.example/runsc.deb"))
    case("http_scheme",lambda:source_host("http://storage.googleapis.com/gvisor/releases/dists/release/InRelease"))
    case("sha256_release_member_duplicate",lambda:parse_release(b"SHA256:\n "+"0"*64+" 4 main/binary-amd64/Packages.gz\n "+"1"*64+" 4 main/binary-amd64/Packages.gz\n"))
    case("package_without_signed_digest",lambda:parse_packages(b"Package: runsc\nArchitecture: amd64\nVersion: 1\nFilename: pool/a.deb\nSize: 5000000\n"))
    case("spoofed_version_or_path",lambda:parse_packages(b"Package: runsc\nArchitecture: amd64\nVersion: 1\nFilename: ../bad.deb\nSize: 5000000\nSHA256: "+b"0"*64+b"\n"))
    return cases

def unpack_deb_readonly(work,record,deb):
    # No dpkg -i; no container invocation; tar stream from trusted host dpkg-deb.
    path=work/"frozen-runsc.deb"
    path.write_bytes(deb)
    meta=subprocess.run(["dpkg-deb","-f",str(path),"Package","Version","Architecture"],
                        capture_output=True,text=True,check=False,timeout=35)
    if meta.returncode!=0:stop("DEB_CONTROL_UNREADABLE")
    v=meta.stdout.strip().splitlines()
    if len(v)<3 or v[0]!="runsc" or v[1]!=record["Version"] or v[2] not in ("amd64","all"):
        stop("DEB_CONTROL_DOES_NOT_MATCH_SIGNED_INDEX")
    process=subprocess.Popen(["dpkg-deb","--fsys-tarfile",str(path)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    binaries=[];entries=0;limit=0
    try:
        with tarfile.open(fileobj=process.stdout,mode="r|") as t:
            for m in t:
                entries+=1
                if entries>20000:stop("DEB_TOO_MANY_PAYLOAD_ENTRIES")
                n=m.name.removeprefix("./")
                if n.startswith("/") or ".." in PurePosixPath(n).parts:stop("DEB_UNSAFE_ENTRY")
                if not m.isfile():continue
                limit+=m.size
                if limit>800_000_000:stop("DEB_UNPACKED_TOO_LARGE")
                base=PurePosixPath(n).name
                interesting=base in ("runsc","containerd-shim-runsc-v1") or "/gvisor-bin/" in "/"+n
                if interesting:
                    if not 0<m.size<=MAX_DECOMPRESSED_MEMBER:stop("RUNSC_BINARY_ITEM_TOO_LARGE")
                    f=t.extractfile(m)
                    if f is None:stop("RUNSC_ITEM_UNREADABLE")
                    raw=f.read(MAX_DECOMPRESSED_MEMBER+1)
                    if len(raw)!=m.size:stop("RUNSC_ITEM_TRUNCATED")
                    binaries.append({"path":n,"bytes":len(raw),"sha256":sha(raw),
                                     "ELF_header":raw[:4]==b"\x7fELF"})
        process.stdout.close()
        stderr=process.stderr.read(12000).decode(errors="replace")
        rc=process.wait(timeout=40)
        if rc!=0:stop("DEB_TAR_DECODER_FAILED")
    finally:
        if process.poll() is None:process.kill()
        path.unlink(missing_ok=True)
    if not any(PurePosixPath(b["path"]).name=="runsc" and b["ELF_header"] for b in binaries):
        stop("RUNSC_EXECUTABLE_NOT_IN_SIGNED_APT_PACKAGE")
    return {"apt_deb_Package":"runsc","apt_deb_Version":v[1],"apt_deb_Architecture":v[2],
            "package_payload_entries":entries,"binary_files":binaries}

def main():
    w=wd()
    old=file(w/"r29-policy-report.json",100_000)
    if sha(old)!=R29_REPORT_SHA:stop("R29_EVIDENCE_DIGEST_DRIFT")
    key=fetch(KEY_URL,40_000)
    if b"BEGIN PGP PUBLIC KEY BLOCK" not in key:stop("WRONG_GVISOR_PUBLIC_KEY_FORMAT")
    (w/"archive.key").write_bytes(key)
    gpgdir=w/"gpg"
    gpgdir.mkdir(mode=0o700)
    status=gpg_run("gpg","--homedir",str(gpgdir),"--batch","--with-colons","--show-keys",str(w/"archive.key"))
    if status.returncode!=0:stop("GVISOR_GPG_KEY_PARSE_FAILED")
    fingerprints=[line.split(":")[9] for line in status.stdout.splitlines() if line.startswith("fpr:")]
    if len(fingerprints)!=1 or not re.fullmatch("[A-Fa-f0-9]{40}",fingerprints[0]):
        stop("GVISOR_SIGNING_KEY_FINGERPRINT_UNTRUSTED")
    ring=w/"keyring.gpg"
    p=gpg_run("gpg","--homedir",str(gpgdir),"--batch","--yes","--dearmor","--output",str(ring),str(w/"archive.key"))
    if p.returncode!=0:stop("GVISOR_KEY_DEARMOR_FAILED")

    release_mode=""
    try:
        x=fetch(ORIGIN+"dists/release/InRelease",2_500_000)
        (w/"InRelease").write_bytes(x)
        verify=gpg_run("gpgv","--keyring",str(ring),str(w/"InRelease"))
        if verify.returncode!=0:stop("APT_INRELEASE_GPGV_VERIFICATION_FAILED")
        release_mode="InRelease"
        signed=x
    except urllib.error.HTTPError as e:
        if e.code!=404:raise
        r=fetch(ORIGIN+"dists/release/Release",2_500_000)
        signature=fetch(ORIGIN+"dists/release/Release.gpg",100_000)
        (w/"Release").write_bytes(r);(w/"Release.gpg").write_bytes(signature)
        verify=gpg_run("gpgv","--keyring",str(ring),str(w/"Release.gpg"),str(w/"Release"))
        if verify.returncode!=0:stop("APT_DETACHED_GPGV_VERIFICATION_FAILED")
        release_mode="Release+Release.gpg"
        signed=r
    checksums=parse_release(signed)
    indexes=[k for k in checksums if re.fullmatch(r"main/binary-amd64/Packages(?:\.gz|\.xz|)",k)]
    if not indexes:stop("SIGNED_REPOSITORY_HAS_NO_AMD64_PACKAGES")
    names=sorted(indexes,key=lambda p:(0 if p.endswith(".gz") else 1 if p.endswith(".xz") else 2,p))
    pth=names[0];expected=checksums[pth]
    index=fetch(ORIGIN+"dists/release/"+pth,max(expected["size"]+500,14_000_000))
    if sha(index)!=expected["sha256"] or len(index)!=expected["size"]:
        stop("APT_PACKAGE_INDEX_SHA256_NOT_SIGNED")
    if pth.endswith(".gz"):index_raw=gzip.decompress(index)
    elif pth.endswith(".xz"):index_raw=lzma.decompress(index)
    else:index_raw=index
    if len(index_raw)>35_000_000:stop("APT_PACKAGE_INDEX_DECOMPRESS_TOO_LARGE")
    record=parse_packages(index_raw)
    deb=fetch(ORIGIN+record["Filename"],MAX_DEB)
    if sha(deb)!=record["SHA256"] or len(deb)!=int(record["Size"]):
        stop("RUNSC_DEB_DIGEST_MISMATCH_WITH_SIGNED_APT_INDEX")
    observed=unpack_deb_readonly(w,record,deb)
    controls=check_controls(record)
    result={
        "stage":"CERT-A19-R30",
        "verdict":"SIGNED_VENDOR_APT_REPOSITORY_TO_RUNSC_DEB_CUSTODY_PASS__FINGERPRINT_NOT_INDEPENDENTLY_ANCHORED_HOST_DENY",
        "R29_evidence_sha256":R29_REPORT_SHA,
        "apt_release_mode":release_mode,
        "apt_signing_key_vendor_url":KEY_URL,
        "apt_signing_key_download_sha256":sha(key),
        "apt_signing_key_observed_fingerprint":fingerprints[0].upper(),
        "apt_signing_key_independently_authorized_fingerprint":False,
        "apt_signature_gpgv_verified":True,
        "apt_signed_release_blob_sha256":sha(signed),
        "apt_verified_index_path":pth,
        "apt_verified_index_sha256":sha(index),
        "apt_signed_index_file_count":len(checksums),
        "runsc_signed_apt_version":record["Version"],
        "runsc_signed_apt_filename":record["Filename"],
        "runsc_deb_expected_and_observed_sha256":sha(deb),
        "runsc_deb_bytes":len(deb),
        "runsc_binary_inventory":observed,
        "offline_negative_controls_rejected":controls,
        "negative_control_count":len(controls),
        "same_artifact_version_as_R29_tag_20261005_proven":False,
        "runsc_or_sidecar_binaries_executed_or_installed":False,
        "physical_rootless_gvisor_host_certified":False,
        "A6_hard_DENY":True,
        "original_199_security_findings_open":True,
        "cve_certified_closures":0,
        "production_authorized":False,
        "main_or_pr_merged":False
    }
    (w/"r30-apt-custody.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("CERT_A19_R30_VENDOR_APT_GPGV_VERIFIED")
    print("CERT_A19_R30_SIGNED_RUNSC_DEB_BYTES="+str(len(deb)))
    print("CERT_A19_R30_EXTRACTED_NATIVE_COMPONENT_HASHES="+str(len(observed["binary_files"])))
    print("CERT_A19_R30_ROOTLESS_HOST_NOT_CERTIFIED_A6_DENY_199_OPEN")
if __name__=="__main__":main()
