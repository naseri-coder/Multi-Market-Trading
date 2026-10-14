"""CERT-A19-R21 read-only stopped OCI + 36 APK loader path/symlink graph audit.

Never install .apk or execute any image, ELF, Worker or user code.
A static namespace/path mapping is NOT a loader ABI or guest security certification.
"""
from __future__ import annotations
import hashlib, io, json, os, posixpath, tarfile, zlib
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit

R18="78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b"
R20="72cd119a29ad364cb5cce4eb5e7536783582ccc4a7f4ecf98905f61972fc542b"
INDEX="8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
BASE="cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
PATH="/lib64/ld-linux-x86-64.so.2"
MAX_TAR=220_000_000
MAX_PACKAGE=105_000_000
MAX_TOTAL=450_000_000
MAX_GZIP_DATA=330_000_000
MAX_ENTRIES=30000

def error(x): raise ValueError("CERT_A19_R21_"+x)
def sha(b):return hashlib.sha256(b).hexdigest()
def droot():
    if any(os.environ.get(k)!=v for k,v in {
        "GITHUB_ACTIONS":"true","MMT_NONPRODUCTION":"1",
        "GITHUB_REF":"refs/heads/cert-a19-byte-audit-run"}.items()):
        error("NONPRODUCTION_FIXED_BRANCH_REQUIRED")
    d=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r21"
    if not d.is_dir():error("MISSING_EVIDENCE_DIRECTORY")
    return d
def read(p,max_size):
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=max_size:
        error("MISSING_OR_UNBOUNDED_INPUT")
    return p.read_bytes()
def canonical(name):
    name=name.removeprefix("./")
    if name.startswith("/"):name=name.lstrip("/")
    if name in ("","."):return ""
    raw=name.split("/")
    if any(part in (".","..") for part in raw if part):error("TAR_PATH_COMPONENT_TRAVERSAL")
    canon=posixpath.normpath(name)
    if canon in ("..",".") or canon.startswith("../") or "\x00" in canon:error("TAR_PATH_INVALID")
    return canon
def linktarget(p,target):
    if not target or "\x00" in target:error("UNSAFE_SYMLINK")
    if target.startswith("/"):
        combined=target.lstrip("/")
    else:
        combined=posixpath.join(posixpath.dirname(p),target)
    resolved=posixpath.normpath(combined)
    if resolved==".." or resolved.startswith("../"):error("SYMLINK_ESCAPES_ROOT")
    return canonical(resolved)

def entry(member,source):
    name=canonical(member.name)
    if not name:return None
    if member.isdir():kind="directory"
    elif member.isfile():kind="file"
    elif member.issym():kind="symlink"
    elif member.islnk():kind="hardlink"
    else:
        # Docker export can contain device/FIFO entries such as /dev/null.
        # Keep their names as metadata. Never create or execute them.
        kind="special-metadata-only"
    result={"kind":kind,"source":source}
    if kind in ("symlink","hardlink"):
        result["raw_target"]=member.linkname
        result["target"]=linktarget(name,member.linkname) if kind=="symlink" else canonical(member.linkname)
    if kind=="file":result["size"]=member.size
    return name,result

def merge(inventory,member,source,conflicts):
    result=entry(member,source)
    if not result:return
    name,item=result
    old=inventory.get(name)
    if old is not None and old["kind"]!=item["kind"]:
        conflicts.append({"path":name,"existing":old,"incoming":item})
    # A source overlap is not automatically a safe OCI overlay. Retain
    # the provenance of both occurrences and refuse to call this a built image.
    if old is None or old["kind"]=="directory":
        inventory[name]=item

def from_base(d,conflicts):
    data=read(d/"base-created-export.tar",MAX_TAR)
    entries={}
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:") as t:
        if len(t.getmembers())>MAX_ENTRIES:error("BASE_ROOTFS_TOO_MANY_PATHS")
        for m in t:merge(entries,m,"verified-signed-base",conflicts)
    return entries,len(data)

def gzmember(blob,offset,limit):
    if blob[offset:offset+2]!=b"\x1f\x8b":error("APKV2_MEMBER_NOT_GZIP")
    z=zlib.decompressobj(16+zlib.MAX_WBITS)
    output=z.decompress(blob[offset:],limit+1)
    if not z.eof or len(output)>limit:error("GZIP_MEMBER_INVALID_OR_LARGE")
    used=len(blob[offset:])-len(z.unused_data)
    if used<18:error("GZIP_MEMBER_SHORT")
    return blob[offset:offset+used],output,offset+used

def source_host(url):
    u=urlsplit(url);h=(u.hostname or "").lower()
    if u.scheme!="https" or u.username or u.password or u.port not in (None,443) or (
        h!="apk.cgr.dev" and not h.endswith(".r2.cloudflarestorage.com")):
        error("UNTRUSTED_SOURCE_REDIRECT")
    return h
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,url):
        source_host(url)
        return super().redirect_request(request,fp,code,msg,headers,url)
DOWNLOADER=urllib.request.build_opener(Redirect())

def download(pkg):
    url="https://apk.cgr.dev/chainguard/x86_64/"+pkg["package"]+"-"+pkg["version"]+".apk"
    with DOWNLOADER.open(urllib.request.Request(url,headers={
        "User-Agent":"CERT-A19-R21-static-only"}),timeout=42) as response:
        source_host(response.url)
        raw=response.read(MAX_PACKAGE+1)
    if sha(raw)!=pkg["whole_apk_sha256"] or len(raw)!=pkg["whole_apk_bytes"]:
        error("HISTORIC_R18_APK_CONTENT_CHANGED")
    control,ctrl,pos=gzmember(raw,0,20_000_000)
    if sha(control)!=pkg["control_compressed_sha256"]:
        error("CONTROL_BYTES_CHANGED")
    with tarfile.open(fileobj=io.BytesIO(ctrl),mode="r:") as t:
        pk=[m for m in t if m.name==".PKGINFO" and m.isfile()]
        if len(pk)!=1:error("PACKAGE_CONTROL_IDENTITY_MISSING")
        content=t.extractfile(pk[0])
        if content is None:error("PACKAGE_CONTROL_UNREADABLE")
        metadata=content.read(100_000).decode("utf-8")
        parsed=dict(line.split(" = ",1) for line in metadata.splitlines() if " = " in line)
    if (parsed.get("pkgname")!=pkg["package"] or parsed.get("pkgver")!=pkg["version"]
         or sha(raw[pos:])!=parsed.get("datahash")):error("SIGNED_INDEX_LINKED_PACKAGE_ID_DRIFT")
    _,payload,end=gzmember(raw,pos,MAX_GZIP_DATA)
    if end!=len(raw):error("UNEXPECTED_APKV2_MEMBER")
    return payload,len(raw)

def from_packages(packages,conflicts):
    nodes={}
    nbytes=0
    for i,pkg in enumerate(packages,1):
        b,size=download(pkg);nbytes+=size
        if nbytes>MAX_TOTAL:error("APK_DOWNLOAD_BUDGET_EXCEEDED")
        with tarfile.open(fileobj=io.BytesIO(b),mode="r:") as t:
            for m in t:merge(nodes,m,"apk:"+pkg["package"]+"@"+pkg["version"],conflicts)
        print("R21_PACKAGE_LINK_GRAPH="+str(i)+"/36:"+pkg["package"],flush=True)
    return nodes,nbytes

def resolve(path,nodes,max_depth=40):
    requested=canonical(path)
    if not requested:error("INVALID_LOOKUP_PATH")
    pending=requested
    steps=[]
    seen=set()
    for depth in range(max_depth):
        parts=pending.split("/")
        modified=False
        for i in range(len(parts)):
            prefix="/".join(parts[:i+1])
            item=nodes.get(prefix)
            if item is None:
                # Tar inventories may omit implicit parent directories.
                continue
            if item["kind"] in ("symlink","hardlink"):
                if prefix in seen:error("LOOP_IN_SYMLINK_CHAIN")
                seen.add(prefix)
                remainder="/".join(parts[i+1:])
                target=item["target"]
                candidate=posixpath.join(target,remainder) if remainder else target
                candidate=posixpath.normpath(candidate)
                if candidate==".." or candidate.startswith("../"):
                    error("LINK_CHAIN_ESCAPES_ROOT")
                steps.append({"link":prefix,"raw_target":item.get("raw_target"),"resolved_target":candidate,"source":item["source"]})
                pending=candidate
                modified=True
                break
        if not modified:
            final=nodes.get(pending)
            return {"requested":requested,"resolved_path":pending,
                    "found":bool(final and final["kind"]=="file"),
                    "terminal":final,"link_steps":steps,"trace_depth":depth}
    error("LINK_CHAIN_TOO_DEEP")

def create_union(base,apk,conflicts):
    nodes=base.copy()
    collisions=[]
    # No attempt to synthesize apk install or OCI layering. Conflicting
    # directory/symlink semantics remain FAIL-CLOSED in the report.
    for k,v in apk.items():
        old=nodes.get(k)
        if old is not None and old["kind"]!=v["kind"]:
            collisions.append({"path":k,"base":old,"package":v})
            continue
        if old is None or old["kind"]=="directory":
            nodes[k]=v
    return nodes,collisions

def main():
    d=droot()
    if (d/"base.txt").read_text().strip()!=BASE or (d/"base-signature.status").read_text().strip()!="SIGNED_PUBLISHER_VERIFIED":
        error("SIGNED_OCI_BASE_NOT_PROVEN")
    if sha(read(d/"APKINDEX.tar.gz",35_000_000))!=INDEX:
        error("SIGNED_INDEX_PIN_CHANGED")
    r18=json.loads(read(d/"r18-result.json",650_000))
    r20=json.loads(read(d/"r20-static-all-elf.json",260_000))
    if sha(read(d/"r18-result.json",650_000))!=R18 or sha(read(d/"r20-static-all-elf.json",260_000))!=R20:
        error("ORIGINAL_R18_R20_EVIDENCE_CHANGED")
    packages=r18["archive_verification"]
    if len(packages)!=36 or r20["ELF_files_statically_scanned"]!=150 or r20["total_symlinks"]!=75:
        error("R18_R20_SOURCE_NOT_RECOGNIZED")
    conflicts=[]
    base,base_bytes=from_base(d,conflicts)
    apk,apk_bytes=from_packages(packages,conflicts)
    combined,base_pkg_collisions=create_union(base,apk,conflicts)
    base_lookup=resolve(PATH,base)
    pkg_lookup=resolve(PATH,apk)
    composite_lookup=resolve(PATH,combined)
    lib64_alias={
        "base":base.get("lib64"),
        "packages":apk.get("lib64"),
        "composite":combined.get("lib64"),
        "usr_lib64_ld_linux_from_packages":apk.get("usr/lib64/ld-linux-x86-64.so.2"),
        "usr_lib64_ld_linux_from_base":base.get("usr/lib64/ld-linux-x86-64.so.2"),
        "usr_lib64_ld_linux_composite":combined.get("usr/lib64/ld-linux-x86-64.so.2")}
    missing_interps=r20.get("missing_exact_ELF_interpreter_paths",{})
    requested_paths=list(missing_interps)
    interpreter_resolution={p:resolve(p,combined) for p in requested_paths}
    alias_resolved_count=sum(x["found"] for x in interpreter_resolution.values())
    # Verify that a base layout alias is indeed observed, not invented.
    robust=bool(composite_lookup["found"] and not base_pkg_collisions)
    res="SIGNED_BASE_PLUS_APK_STATIC_INTERPRETER_PATH_PRESENT_NO_EXECUTION" if robust else "LOADER_PATH_STILL_BLOCKED_OR_UNION_COLLISION"
    report={
        "stage":"CERT-A19-R21","verdict":res,
        "signed_base":BASE,"source_r18_json_sha256":R18,"source_r20_json_sha256":R20,
        "signed_apkindex_sha256":INDEX,
        "base_export_tar_bytes":base_bytes,
        "base_rootfs_inventory_entries":len(base),
        "base_special_metadata_only_count":sum(1 for v in base.values() if v["kind"]=="special-metadata-only"),
        "apk_inventory_entries":len(apk),
        "combined_static_union_entries":len(combined),
        "whole_archive_bytes_verified":apk_bytes,
        "all_36_package_archives_sha256_checked":True,
        "base_only_interpreter_lookup":base_lookup,
        "packages_only_interpreter_lookup":pkg_lookup,
        "static_union_interpreter_lookup":composite_lookup,
        "lib64_and_ld_linux_explicit_entries":lib64_alias,
        "R20_missing_interpreter_paths":missing_interps,
        "resolved_interpreter_paths_static_union":interpreter_resolution,
        "interpreter_names_resolved_by_static_union":alias_resolved_count,
        "union_base_package_file_kind_conflicts":base_pkg_collisions[:60],
        "union_conflict_count":len(base_pkg_collisions),
        "source_duplicate_kind_conflicts":conflicts[:60],
        "duplicate_kind_conflict_count":len(conflicts),
        "R20_multiple_NEEDED_candidates":len(r20["ambiguous_DT_NEEDED_candidates"]),
        "loader_symlink_logic_verified_without_running_loader":True,
        "actual_rootfs_package_install_or_image_build_performed":False,
        "actual_dynamic_linker_path_execution_verified":False,
        "runtime_ABI_and_TLS_NSS_CA_verified":False,
        "four_language_fixture_executed":False,
        "worker_or_guest_executed":False,
        "independent_rootless_gvisor_host_certified":False,
        "A6_hard_DENY":True,
        "original_199_findings_review_open":True,
        "cves_certified_closed":0,"production_authorized":False
    }
    (d/"r21-static-rootfs-path.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("CERT_A19_R21_BASE_LIB64="+repr(base.get("lib64")))
    print("CERT_A19_R21_INTERPRETER_STATIC_UNION_FOUND="+str(composite_lookup["found"]))
    print("CERT_A19_R21_UNION_KIND_CONFLICTS="+str(len(base_pkg_collisions)))
    print("CERT_A19_R21_STATIC_VERDICT="+res)
    print("CERT_A19_R21_WORKER_NO_EXECUTE_A6_DENY_199_OPEN")

if __name__=="__main__":
    main()
