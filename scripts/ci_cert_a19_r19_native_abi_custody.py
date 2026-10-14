"""CERT-A19-R19 — source-bound TS/Wasmtime + static Wolfi ABI (no execution).

Research-only: the downloaded TypeScript code, Wasmtime shared libraries and
Wolfi native runtime must NEVER be imported, loaded, installed or executed.
Only bounded metadata parsing and the hosted runner's trusted readelf execute.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.request
from urllib.parse import urlsplit
import zipfile
import zlib

R18_INDEX_SHA="8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
R18_REPORT_SHA="78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b"
WASM_WHEEL="wasmtime-49.0.0-py3-none-manylinux1_x86_64.whl"
WASM_SHA="94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a"
APK_PIN={
    "glibc-2.44": ("2.44-r8","e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0"),
    "ld-linux-2.44": ("2.44-r8","e0c7e3b457c86a7d672a339a166ee13959356ac8a5b19ab4af5a771fee6c699f"),
    "python-3.12-base": ("3.12.15-r3","ca4ac0aef2c9dea512ce43510b247a8b082593a8af3e50842b06fadc3935db0a"),
    "nodejs-24": ("24.22.0-r0","8c007c9f6027020d5cc580613d59ade62205b0875d93d6be8c2042ce8b130bcf"),
    "openssl-4.0-libcrypto": ("4.0.3-r6","902627db5c736916f3ba34ca2ae95a034e877cd06b0636f4d01d1ceec81d331e"),
    "openssl-4.0-libssl": ("4.0.3-r6","65e30d6a2cc79e9bf5f744b013451cd7267470ee61743f4d84418b51cf56ab73"),
}
MAX_FILE=110_000_000
OUT_MAX=250_000_000
REGISTRY_HOSTS={"registry.npmjs.org","pypi.org","files.pythonhosted.org","apk.cgr.dev"}
MAX_DOWNLOAD_TOTAL=180_000_000

def stop(why): raise RuntimeError("CERT_A19_R19_"+why)
def sha(data):return hashlib.sha256(data).hexdigest()
def project_dir():
    if (os.environ.get("GITHUB_ACTIONS")!="true"
        or os.environ.get("GITHUB_REF")!="refs/heads/cert-a19-byte-audit-run"
        or os.environ.get("MMT_NONPRODUCTION")!="1"):stop("SCOPE")
    return Path(os.environ["RUNNER_TEMP"])/"cert-a19-r19"

def bounded_read(path,cap):
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=cap:
        stop("MISSING_OR_OVERSIZED_FILE")
    return path.read_bytes()

def host_ok(url):
    u=urlsplit(url)
    host=(u.hostname or "").lower()
    if (u.scheme!="https" or u.username or u.password or u.port not in (None,443)
        or host not in REGISTRY_HOSTS and not host.endswith(".r2.cloudflarestorage.com")):
        stop("UNTRUSTED_DISTRIBUTION_HOST")
    return host

class RedirectCheck(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host_ok(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

OPENER=urllib.request.build_opener(RedirectCheck())
def download(url, limit):
    host_ok(url)
    with OPENER.open(urllib.request.Request(url,headers={"User-Agent":"MMT-R19-research-custody-only"}),timeout=55) as r:
        redirected=host_ok(r.url)
        payload=r.read(limit+1)
    if not 0<len(payload)<=limit:stop("REMOTE_BYTES_NOT_BOUNDED")
    return payload, redirected

def r18_closure(root):
    index=bounded_read(root/"APKINDEX.tar.gz",35_000_000)
    if sha(index)!=R18_INDEX_SHA:stop("IMMUTABLE_R18_INDEX_NOT_REUSED")
    report=bounded_read(root/"r18-result.json",600_000)
    if sha(report)!=R18_REPORT_SHA:stop("R18_REPORT_SHA_DRIFT")
    j=json.loads(report)
    packages=j.get("archive_verification",[])
    if len(packages)!=36 or j.get("resolved_package_count")!=36 or not j.get("all_selected_archives_verified"):
        stop("R18_FULL_CLOSURE_EVIDENCE_INVALID")
    for n,(v,h) in APK_PIN.items():
        x=[p for p in packages if p.get("package")==n and p.get("version")==v and p.get("whole_apk_sha256")==h]
        if len(x)!=1: stop("R18_NATIVE_ROOT_PIN_DRIFT_"+n)
    return packages

def npm_metadata():
    json_bytes,_=download("https://registry.npmjs.org/typescript/5.9.3",500_000)
    info=json.loads(json_bytes)
    if info.get("name")!="typescript" or info.get("version")!="5.9.3":stop("NPM_TS_REGISTRY_VERSION_MISMATCH")
    dist=info.get("dist",{})
    url=dist.get("tarball","")
    if url!="https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz":stop("TS_REGISTRY_TARBALL_UNEXPECTED")
    integrity=dist.get("integrity","")
    if not integrity.startswith("sha512-"):stop("TS_NPM_SHA512_INTEGRITY_ABSENT")
    tar,host=download(url,65_000_000)
    if hashlib.sha512(tar).digest()!=base64.b64decode(integrity.split("-",1)[1],validate=True):
        stop("TS_REGISTRY_SHA512_INTEGRITY_FAIL")
    with tarfile.open(fileobj=io.BytesIO(tar),mode="r:gz") as t:
        names={x.name:x for x in t if x.isfile()}
        required=("package/package.json","package/lib/tsc.js","package/lib/typescript.js")
        if any(n not in names for n in required):stop("TYPESCRIPT_COMPILER_FILES_MISSING")
        meta=t.extractfile(names["package/package.json"])
        if meta is None:stop("TYPESCRIPT_PACKAGE_METADATA_UNREADABLE")
        manifest=json.loads(meta.read(200_000))
        if manifest.get("name")!="typescript" or manifest.get("version")!="5.9.3":
            stop("TYPESCRIPT_INTERNAL_PACKAGE_VERSION_DRIFT")
        compiled=[{"path":n,"bytes":names[n].size} for n in required if n.endswith(".js")]
    return {"version":"5.9.3","source":"npm official registry", "download_host":host,
        "archive_sha256":sha(tar),"sha512_integrity_matched_registry_metadata":True,
        "npm_registry_integrity":integrity,
        "files_present_not_executed":compiled,
        "independently_verified_npm_release_signature":False,
        "npm_registry_metadata_is_not_independent_publisher_attestation":True}

def wheel_metadata(root):
    metadata,_=download("https://pypi.org/pypi/wasmtime/49.0.0/json",4_000_000)
    info=json.loads(metadata)
    if info.get("info",{}).get("version")!="49.0.0":stop("WASMTIME_PYPI_VERSION_DRIFT")
    files=[x for x in info.get("urls",[]) if x.get("filename")==WASM_WHEEL]
    if len(files)!=1 or files[0].get("digests",{}).get("sha256")!=WASM_SHA:
        stop("WASMTIME_EXPECTED_WHEEL_HASH_ABSENT")
    url=files[0]["url"]
    if not url.startswith("https://files.pythonhosted.org/packages/"):
        stop("UNEXPECTED_WASMTIME_WHEEL_URL")
    b,host=download(url,24_000_000)
    if sha(b)!=WASM_SHA:stop("WASMTIME_WHEEL_SHA256_DRIFT")
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        names=z.namelist()
        if len(names)>300 or any(".." in Path(n).parts for n in names):stop("WHEEL_PATH_OR_SIZE_UNSAFE")
        wheels=[n for n in names if n.endswith(".dist-info/WHEEL")]
        metas=[n for n in names if n.endswith(".dist-info/METADATA")]
        records=[n for n in names if n.endswith(".dist-info/RECORD")]
        shared=[n for n in names if n.endswith(".so")]
        if len(wheels)!=1 or len(metas)!=1 or len(records)!=1 or not shared:
            stop("WASMTIME_WHEEL_NATIVE_OR_METADATA_MISSING")
        wheel_text=z.read(wheels[0]).decode()
        if "Tag: py3-none-manylinux1_x86_64" not in wheel_text:
            stop("WHEEL_MANYLINUX_ARCH_TAG_INVALID")
        meta=z.read(metas[0]).decode()
        if "Name: wasmtime" not in meta or "Version: 49.0.0" not in meta:
            stop("WASMTIME_WHEEL_INTERNAL_IDENTITY_INVALID")
        extracts=[]
        for n in shared:
            item=z.getinfo(n)
            if not 10_000<item.file_size<=MAX_FILE:stop("WASMTIME_SO_SIZE_UNSAFE")
            binary=z.read(n)
            if not binary.startswith(b"\x7fELF"):stop("WASMTIME_LIBRARY_NOT_ELF")
            target=root/"native"
            target.mkdir(exist_ok=True)
            dest=target/("wasmtime-"+str(len(extracts))+".elf")
            dest.write_bytes(binary)
            extracts.append({"path_in_wheel":n, "bytes":len(binary),
                             "sha256":sha(binary), "audit_path":str(dest)})
    return {"version":"49.0.0","wheel_filename":WASM_WHEEL,"wheel_sha256":sha(b),
        "wheel_architecture":"py3-none-manylinux1_x86_64","wheel_download_host":host,
        "python_distribution_metadata_version_verified":True,"wheel_sha256_matched_pypi":True,
        "trusted_publishing_pypi_marked":bool(files[0].get("upload_time_iso_8601") and False),
        "independent_publisher_signature_verified":False,
        "native_elf_files_not_executed":extracts}

def gzip_stream(raw,pos,limit):
    if raw[pos:pos+2]!=b"\x1f\x8b":stop("APK_MEMBER_IS_NOT_GZIP")
    zipobj=zlib.decompressobj(wbits=16+zlib.MAX_WBITS)
    data=zipobj.decompress(raw[pos:],limit+1)
    if not zipobj.eof or len(data)>limit:stop("APK_MEMBER_INFLATE_TOO_LARGE_OR_TRUNCATED")
    size=len(raw[pos:])-len(zipobj.unused_data)
    if size<18:stop("APK_MEMBER_TOO_SHORT")
    return raw[pos:pos+size],data,pos+size

def elf_from_apk(root,name,version,pinned_sha):
    url="https://apk.cgr.dev/chainguard/x86_64/"+name+"-"+version+".apk"
    blob,host=download(url,MAX_FILE)
    if sha(blob)!=pinned_sha:stop("R18_FULL_APK_HASH_DRIFT_"+name)
    ctrl,unpacked,pos=gzip_stream(blob,0,15_000_000)
    with tarfile.open(fileobj=io.BytesIO(unpacked),mode="r:") as tar:
        m=[x for x in tar if x.name==".PKGINFO"]
        if len(m)!=1:stop("APK_PKGINFO_MISSING")
        f=tar.extractfile(m[0])
        if f is None:stop("APK_PKGINFO_READ_FAILED")
        info=f.read(100_000).decode("utf-8")
    entry=dict(line.split(" = ",1) for line in info.splitlines() if " = " in line)
    if entry.get("pkgname")!=name or entry.get("pkgver")!=version:stop("APK_INTERNAL_IDENTITY_DRIFT")
    if sha(blob[pos:])!=entry.get("datahash"):stop("APK_COMPRESSED_DATA_DIGEST_MISMATCH")
    _,data,nextpos=gzip_stream(blob,pos,OUT_MAX)
    if nextpos!=len(blob):stop("APK_DATA_EXTRA_STREAMS_UNREVIEWED")
    chosen=[]
    native_dir=root/"native"
    native_dir.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:") as t:
        for member in t:
            if not member.isfile() or member.size<1000 or member.size>MAX_FILE:continue
            # Static ELF only; never execute or import any downloaded binary.
            path=member.name
            if (not ("/bin/" in "/"+path or "/lib" in "/"+path)
                or len(chosen)>=7):continue
            obj=t.extractfile(member)
            if obj is None:continue
            payload=obj.read(MAX_FILE+1)
            if not payload.startswith(b"\x7fELF"):continue
            file=native_dir/(re.sub(r"[^A-Za-z0-9_-]","_",name)+"-"+str(len(chosen))+".elf")
            file.write_bytes(payload)
            chosen.append({"archive_path":path,"bytes":len(payload),"sha256":sha(payload),
                           "audit_path":str(file)})
    return {"package":name,"version":version,"whole_archive_sha256":pinned_sha,
            "verified_r18_whole_archive_byte_match":True,
            "compressed_datahash_matched_PKGINFO":True,
            "download_host":host,"elf_files":chosen}

def elf_readelf(path):
    if not path.is_file() or not bounded_read(path,MAX_FILE).startswith(b"\x7fELF"):
        stop("BAD_ELF_FILE")
    def cmd(*args):
        p=subprocess.run(["readelf","--wide",*args,str(path)],capture_output=True,text=True,timeout=30,check=False)
        if p.returncode!=0:stop("READELF_STATIC_INSPECTION_FAILED")
        return p.stdout[:200_000]
    header=cmd("-h")
    if "Advanced Micro Devices X86-64" not in header:stop("STATIC_ELF_NOT_X86_64")
    dynamic=cmd("-d")
    version=cmd("-V")
    phdr=cmd("-l")
    needed=sorted(set(re.findall(r"\(NEEDED\).*?Shared library:\s*\[([^\]]+)\]",dynamic)))
    sonames=sorted(set(re.findall(r"\(SONAME\).*?Library soname:\s*\[([^\]]+)\]",dynamic)))
    glibc=sorted(set(re.findall(r"GLIBC_([0-9]+\.[0-9]+)",version)),key=lambda s:tuple(map(int,s.split("."))))
    highest=glibc[-1] if glibc else None
    if highest and tuple(map(int,highest.split(".")))>(2,44):
        stop("ABI_REQUIRES_GLIBC_NEWER_THAN_SELECTED_2_44")
    runpath=re.findall(r"\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]",dynamic)
    interp=re.findall(r"\[Requesting program interpreter:\s*([^\]]+)\]",phdr)
    return {"elf_format":"ELF64_x86_64","needed":needed,"soname":sonames,
            "max_required_glibc_version":highest,"runpath_or_rpath":runpath,
            "requested_interpreter":interp,"readelf_static_only":True}

def main():
    root=project_dir()
    ref=r18_closure(root)
    npm=npm_metadata()
    wasm=wheel_metadata(root)
    native=[]
    all_elf=[]
    for name,(version,digest) in APK_PIN.items():
        entry=elf_from_apk(root,name,version,digest)
        for e in entry["elf_files"]:
            data=elf_readelf(Path(e["audit_path"]))
            data.update({"source_package":name,"archive_path":e["archive_path"],
                         "file_sha256":e["sha256"]})
            all_elf.append(data)
        native.append({"package":name,"version":version,"apk_sha256":digest,
                       "elf_files_identified":len(entry["elf_files"]),
                       "ELF_file_paths":[q["archive_path"] for q in entry["elf_files"]]})
    for e in wasm["native_elf_files_not_executed"]:
        data=elf_readelf(Path(e["audit_path"]))
        data.update({"source_package":"wasmtime-49.0.0-wheel",
                     "archive_path":e["path_in_wheel"],"file_sha256":e["sha256"]})
        all_elf.append(data)
    if len(all_elf)<5 or not any(x["source_package"]=="nodejs-24" for x in all_elf):
        stop("INSUFFICIENT_NATIVE_ELF_EVIDENCE")
    if not any(x["source_package"]=="wasmtime-49.0.0-wheel" for x in all_elf):
        stop("WASMTIME_ELF_NOT_REVIEWED")
    need=sorted(set(v for x in all_elf for v in x["needed"]))
    report={
        "stage":"CERT-A19-R19",
        "verdict":"TYPESCRIPT_AND_WASMTIME_ARTIFACT_HASHES_PLUS_SELECTED_STATIC_ELF_PASS__FULL_NATIVE_RUNTIME_ABI_NOT_CERTIFIED",
        "R18_full_36_package_closure_evidence_sha256":R18_REPORT_SHA,
        "R18_signed_index_reused_sha256":R18_INDEX_SHA,
        "R18_resolver_selected_and_legacy_byte_verified_package_count":36,
        "typescript":npm,"wasmtime":wasm,"wolfi_native_selected_apk_archives":native,
        "static_elf_provenance":all_elf,
        "union_of_observed_NEEDED_libraries":need,
        "ELF_files_inspected":len(all_elf),
        "native_glibc_2_44_symbol_upper_bound_checked":True,
        "all_36_package_ELF_transitive_runtime_linking_tested":False,
        "dynamic_loader_runtime_invoked":False,
        "CPython_Node_TypeScript_Wasmtime_code_executed":False,
        "typescript_compiler_semantic_parity_tested":False,
        "wasmtime_wasm_module_semantic_parity_tested":False,
        "four_language_worker_parity_tested":False,
        "full_Wolfi_OCI_image_built":False,
        "independent_rootless_gvisor_host_certified":False,
        "original_199_findings_open":True,
        "CVE_closures_certified":0,
        "A6_hard_DENY":True,
        "production_authorized":False,
    }
    (root/"r19-report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    for e in (root/"native").iterdir():e.unlink()
    (root/"native").rmdir()
    print("CERT_A19_R19_TYPESCRIPT_REGISTRY_SHA512_MATCH_PASS")
    print("CERT_A19_R19_WASMTIME_PYPI_WHEEL_SHA256_MATCH_PASS")
    print("CERT_A19_R19_STATIC_ELF_FILE_COUNT="+str(len(all_elf)))
    print("CERT_A19_R19_ABI_RUNTIME_NOT_CERTIFIED_A6_DENY_199_OPEN")

if __name__=="__main__":
    main()
