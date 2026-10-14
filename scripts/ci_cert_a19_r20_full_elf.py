"""CERT-A19-R20: full static x86_64 ELF and symlink inventory of all R18 Wolfi APKs.

This is NOT a loader test, runtime/worker execution, or secure host attestation.
Only archived R18 signed-index-bound packages are accepted. Archive entries are
parsed as data and NEVER extracted onto the host's executable search paths.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import tarfile
import urllib.request
from urllib.parse import urlsplit
import zlib

R18_SHA="78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b"
R17_INDEX="8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
R19_SHA="aeacd3dee432ebbebd2bf3b94f41b13aff5c94bd7eb34dcd16814ad4c6166d55"
N=36
MAX_APK=105_000_000
MAX_DEFLATED=300_000_000
MAX_TOTAL_BYTES=450_000_000
MAX_ELF_BYTES=110_000_000
MAX_ELF_COUNT=3000
ROOTS={"glibc-2.44","python-3.12","python-3.12-base","nodejs-24"}
def fail(code):raise RuntimeError("CERT_A19_R20_"+code)
def sha(data):return hashlib.sha256(data).hexdigest()
def read(path,cap):
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=cap:
        fail("MISSING_OR_UNBOUNDED_EVIDENCE")
    return path.read_bytes()
def root():
    if (os.environ.get("GITHUB_ACTIONS")!="true"
        or os.environ.get("MMT_NONPRODUCTION")!="1"
        or os.environ.get("GITHUB_REF")!="refs/heads/cert-a19-byte-audit-run"):
        fail("ISOLATED_NONPRODUCTION_ONLY")
    base=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r20"
    if not base.is_dir():fail("EVIDENCE_DIR_MISSING")
    return base

def origin(uri):
    u=urlsplit(uri)
    h=(u.hostname or "").lower()
    if (u.scheme!="https" or u.username or u.password or u.port not in (None,443)
        or (h!="apk.cgr.dev" and not h.endswith(".r2.cloudflarestorage.com"))):
        fail("UNTRUSTED_APK_DOWNLOAD_HOST")
    return h
class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        origin(url)
        return super().redirect_request(req,fp,code,msg,headers,url)
OPENER=urllib.request.build_opener(Redirects())
def download(uri,cap):
    origin(uri)
    with OPENER.open(urllib.request.Request(uri,headers={"User-Agent":"CERT-A19-R20-read-only-research"}),timeout=45) as r:
        host=origin(r.url)
        b=r.read(cap+1)
    if not 0<len(b)<=cap:fail("APKPAYLOAD_DOWNLOAD_OVER_BUDGET")
    return b,host

def decompress_member(b,offset,limit):
    if b[offset:offset+2]!=b"\x1f\x8b":fail("APKV2_NON_GZIP_STREAM")
    z=zlib.decompressobj(16+zlib.MAX_WBITS)
    output=z.decompress(b[offset:],limit+1)
    if not z.eof or len(output)>limit:fail("APKV2_TRUNCATED_OR_TOO_BIG")
    taken=len(b[offset:])-len(z.unused_data)
    if taken<18:fail("APKV2_INVALID_STREAM")
    return b[offset:offset+taken],output,offset+taken

def safe_path(name):
    raw=name.removeprefix("./").lstrip("/")
    p=posixpath.normpath(raw)
    if not p or p=="." or p==".." or p.startswith("../") or "\x00" in p:
        fail("MALICIOUS_APK_PATH")
    return p

def apk_verify_unpack(b,pkg):
    if len(b)!=pkg["whole_apk_bytes"] or sha(b)!=pkg["whole_apk_sha256"]:
        fail("R18_APK_WHOLE_ARCHIVE_DRIFT")
    control_gz,control,pos=decompress_member(b,0,18_000_000)
    with tarfile.open(fileobj=io.BytesIO(control),mode="r:") as t:
        items=[x for x in t if x.isfile() and x.name==".PKGINFO"]
        if len(items)!=1:fail("APK_CONTROL_PKGINFO_ABSENT")
        f=t.extractfile(items[0])
        if f is None:fail("APK_CONTROL_UNREADABLE")
        pkgi=f.read(120_000).decode("utf-8","strict")
    props=dict(v.split(" = ",1) for v in pkgi.splitlines() if " = " in v)
    if props.get("pkgname")!=pkg["package"] or props.get("pkgver")!=pkg["version"]:
        fail("APK_CONTROL_IDENTITY_MISMATCH")
    if sha(control_gz)!=pkg["control_compressed_sha256"]:
        fail("R18_CONTROL_HASH_DRIFT")
    data_gz=b[pos:]
    if sha(data_gz)!=props.get("datahash") or sha(data_gz)!=pkg["data_compressed_sha256"]:
        fail("SIGNED_CONTROL_DATAHASH_DRIFT")
    _,uncompressed,at_end=decompress_member(b,pos,MAX_DEFLATED)
    if at_end!=len(b):fail("APK_V2_UNEXPECTED_EXTRA_STREAM")
    return uncompressed

def safe_target(current,target):
    if target.startswith("/"):
        return safe_path(target)
    parent=posixpath.dirname(current)
    normalized=posixpath.normpath(posixpath.join(parent,target))
    if normalized==".." or normalized.startswith("../"):
        fail("APK_LINK_ESCAPES_IMAGE_ROOT")
    return safe_path(normalized)

def readelf(binary_file):
    def cmd(flag):
        p=subprocess.run(["readelf","--wide",flag,str(binary_file)],
                         capture_output=True,text=True,timeout=30,check=False)
        if p.returncode!=0:fail("READELF_STATIC_FAILURE_"+flag.replace("-","_"))
        return p.stdout[:250_000]
    h=cmd("-h")
    if "Advanced Micro Devices X86-64" not in h:fail("NON_AMD64_ELF")
    d=cmd("-d")
    v=cmd("-V")
    ph=cmd("-l")
    needed=sorted(set(re.findall(r"\(NEEDED\).*?Shared library:\s*\[([^\]]+)\]",d)))
    soname=re.findall(r"\(SONAME\).*?Library soname:\s*\[([^\]]+)\]",d)
    interp=re.findall(r"\[Requesting program interpreter:\s*([^\]]+)\]",ph)
    runpaths=re.findall(r"\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]",d)
    glibc=sorted(set(re.findall(r"GLIBC_([0-9]+\.[0-9]+)",v)),
                key=lambda x:tuple(map(int,x.split("."))))
    return {"DT_NEEDED":needed,"DT_SONAME":soname[:3],
            "ELF_interpreter":interp[:2],"RPATH_RUNPATH":runpaths[:6],
            "max_required_GLIBC":glibc[-1] if glibc else None,
            "static_inspection_no_execution":True}

def main():
    d=root()
    raw_report=read(d/"r18-result.json",650_000)
    if sha(raw_report)!=R18_SHA:fail("R18_ORIGINAL_PROOF_CHANGED")
    r18=json.loads(raw_report)
    if not r18.get("all_selected_archives_verified") or r18.get("resolved_package_count")!=36:
        fail("R18_VERDICT_INSUFFICIENT")
    if sha(read(d/"APKINDEX.tar.gz",35_000_000))!=R17_INDEX:
        fail("ORIGINAL_SIGNED_APKINDEX_CHANGED")
    r19_raw=read(d/"r19-report.json",350_000)
    if sha(r19_raw)!=R19_SHA:fail("R19_ORIGINAL_PROOF_CHANGED")
    r19=json.loads(r19_raw)
    if r19.get("ELF_files_inspected")!=19:fail("R19_STATIC_RESULT_UNRECOGNIZED")
    packages=r18.get("archive_verification",[])
    if len(packages)!=36:fail("WRONG_TRANSITIVE_PACKAGE_COUNT")

    elfs=[]
    files={}
    symlinks={}
    hardlinks={}
    nbytes=0
    download_hosts=set()
    auditdir=d/"elfscratch"
    auditdir.mkdir(mode=0o700,exist_ok=False)
    package_summaries=[]
    for i,p in enumerate(packages):
        name,version=p["package"],p["version"]
        filename=f"{name}-{version}.apk"
        url=f"https://apk.cgr.dev/chainguard/x86_64/{filename}"
        b,host=download(url,MAX_APK)
        download_hosts.add(host)
        nbytes+=len(b)
        if nbytes>MAX_TOTAL_BYTES:fail("WHOLE_CLOSURE_ARCHIVES_TOO_BIG")
        uncompressed=apk_verify_unpack(b,p)
        pkgelf=0
        pkgfiles=0
        with tarfile.open(fileobj=io.BytesIO(uncompressed),mode="r:") as archive:
            for member in archive:
                if member.isdir():continue
                path=safe_path(member.name)
                if member.issym():
                    target=safe_target(path,member.linkname)
                    old=symlinks.get(path)
                    if old is not None and old!=target:fail("SYMLINK_PATH_CONFLICT")
                    symlinks[path]=target
                elif member.islnk():
                    target=safe_path(member.linkname)
                    old=hardlinks.get(path)
                    if old is not None and old!=target:fail("HARDLINK_PATH_CONFLICT")
                    hardlinks[path]=target
                elif member.isfile():
                    if member.size>MAX_ELF_BYTES:fail("APK_MEMBER_TOO_LARGE")
                    file=archive.extractfile(member)
                    if file is None:fail("APK_MEMBER_MISSING")
                    prefix=file.read(4)
                    if path in files:
                        fail("DUPLICATE_PACKAGE_FILE_PATH")
                    files[path]={"package":name,"size":member.size}
                    pkgfiles+=1
                    if prefix!=b"\x7fELF":continue
                    if len(elfs)>=MAX_ELF_COUNT:fail("ELF_ITEM_LIMIT")
                    blob=prefix+file.read(MAX_ELF_BYTES+1)
                    if len(blob)!=member.size:fail("ELF_MEMBER_SIZE_MISMATCH")
                    tmp=auditdir/"examined.elf"
                    tmp.write_bytes(blob)
                    result=readelf(tmp)
                    tmp.unlink()
                    result.update({"path":path,"package":name,"version":version,
                                   "file_sha256":sha(blob),"file_bytes":len(blob)})
                    elfs.append(result)
                    pkgelf+=1
                else:
                    # Device or FIFO in APK payload is a separate hardening concern.
                    fail("SPECIAL_FILE_IN_PACKAGE")
        package_summaries.append({"package":name,"version":version,
                                  "apk_sha256":sha(b),"regular_files":pkgfiles,
                                  "ELF_count":pkgelf})
        print(f"R20_CHECKED_APK {i+1}/36 {name} {version} elf={pkgelf}",flush=True)

    if set(p["package"] for p in package_summaries).intersection(ROOTS)!=ROOTS:
        fail("MISSING_ROOT_PACKAGE")
    if not elfs:fail("NO_ELF_DISCOVERED")
    if len(elfs)<19:fail("LESS_THAN_R19_SUBSET")
    # Do NOT pretend this is kernel ld.so resolution. This only tests for
    # existence of candidate filenames/SONAMEs in the frozen APK inventory.
    basenames={}
    for p in files:
        basenames.setdefault(posixpath.basename(p),[]).append(p)
    for p in symlinks:
        basenames.setdefault(posixpath.basename(p),[]).append(p)
    for p in hardlinks:
        basenames.setdefault(posixpath.basename(p),[]).append(p)
    for elf in elfs:
        for so in elf["DT_SONAME"]:
            basenames.setdefault(so,[]).append(elf["path"])
    missing={}
    ambiguous={}
    for elf in elfs:
        for need in elf["DT_NEEDED"]:
            candidates=sorted(set(basenames.get(need,[])))
            if not candidates:
                missing.setdefault(need,[]).append(elf["path"])
            elif len(candidates)>1:
                ambiguous.setdefault(need,[]).extend(candidates)
    for k in list(missing):
        missing[k]=sorted(set(missing[k]))[:30]
    for k in list(ambiguous):
        ambiguous[k]=sorted(set(ambiguous[k]))[:30]
    no_such_interp={}
    for elf in elfs:
        for interp in elf["ELF_interpreter"]:
            p=safe_path(interp)
            if p not in files and p not in symlinks and p not in hardlinks:
                no_such_interp.setdefault(interp,[]).append(elf["path"])
    maxgl=max((tuple(map(int,e["max_required_GLIBC"].split("."))) for e in elfs if e["max_required_GLIBC"]),default=(0,0))
    # Include R19 Wasmtime ELF as external supplementary evidence — NOT in 36 APKs.
    wasmtime=[e for e in r19["static_elf_provenance"] if e.get("source_package")=="wasmtime-49.0.0-wheel"]
    wheel_missing=sorted(set(n for e in wasmtime for n in e["needed"] if n not in basenames))
    status=("STATIC_FILESYSTEM_NAME_COVERAGE_PASS_ONLY__LOADER_TEST_UNPROVEN"
            if not missing and not no_such_interp
            else "STATIC_ELF_INVENTORY_PASS_WITH_UNRESOLVED_LIBRARY_PATHS__FAIL_CLOSED")
    report={
        "stage":"CERT-A19-R20",
        "verdict":status,
        "original_R18_report_sha256":R18_SHA,
        "original_R19_report_sha256":R19_SHA,
        "signed_R17_index_sha256":R17_INDEX,
        "source_package_closure_count":len(packages),
        "downloaded_apk_payload_bytes":nbytes,
        "download_source_hosts":sorted(download_hosts),
        "all_36_exact_archive_SHA256_and_compressed_datahash_reverified":True,
        "total_regular_files":len(files),"total_symlinks":len(symlinks),
        "total_hardlinks":len(hardlinks),
        "ELF_files_statically_scanned":len(elfs),
        "max_GLIBC_version_seen":str(maxgl[0])+"."+str(maxgl[1]),
        "all_observed_elf_glibc_requirements_at_or_below_2_44":maxgl<=(2,44),
        "unresolved_DT_NEEDED_by_name":missing,
        "ambiguous_DT_NEEDED_candidates":ambiguous,
        "missing_exact_ELF_interpreter_paths":no_such_interp,
        "wasmtime_R19_external_ELF_needed_names_not_found_in_R18_package_inventory":wheel_missing,
        "package_summary":package_summaries,
        "ELF_details":elfs,
        "note":"Only static basename/soname presence, NOT dynamic-loader order, symbol binding, NSS/CA/TLS, runtime compatibility, or secure host certification.",
        "all_runtime_loader_paths_and_symlink_targets_resolved":False,
        "four_language_fixed_fixture_execution_performed":False,
        "worker_or_untrusted_guest_code_executed":False,
        "no_new_worker_image_built":True,
        "independent_rootless_gvisor_host_certified":False,
        "A6_hard_DENY":True,
        "original_199_security_findings_review_open":True,
        "CVE_closures":0,
        "production_authorized":False,
    }
    (d/"r20-static-all-elf.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("CERT_A19_R20_ALL_36_APKS_STATIC_INVENTORY_COMPLETE="+str(len(elfs)))
    print("CERT_A19_R20_UNRESOLVED_NEEDED_NAMES="+str(len(missing)))
    print("CERT_A19_R20_MISSING_INTERPRETER_PATHS="+str(len(no_such_interp)))
    print("CERT_A19_R20_HOST_AND_RUNTIME_EQUIVALENCE_NOT_CERTIFIED__A6_DENY_199_OPEN")

if __name__=="__main__":
    main()
