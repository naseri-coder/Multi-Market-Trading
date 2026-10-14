"""CERT-A19-R23: authentic offline APK bytes + actual apko minirootfs install.

STRICT SCOPE: package-only rootfs; NEVER claim that signed Wolfi base image was
overlaid. All downloaded package code is treated as data, and never executed.
"""
from __future__ import annotations
import base64,hashlib,io,json,os,pathlib,posixpath,re,tarfile
import urllib.request, zlib
from urllib.parse import urlsplit
ROOTS={"glibc-2.44":"2.44-r8","python-3.12":"3.12.15-r3",
       "python-3.12-base":"3.12.15-r3","nodejs-24":"24.22.0-r0"}
IDX="8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
R18="78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b"
R22="41cefc3fc5e72ca023b3f915b5605b9dd950f24860d313c37de56309d67efec7"
LOADER_SHA="2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09"
CLEAR_SHA="98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed"
CAP=95_000_000
TOTAL=450_000_000

def deny(msg):raise RuntimeError("CERT_A19_R23_"+msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def d():
    required={"GITHUB_ACTIONS":"true","GITHUB_REF":"refs/heads/cert-a19-byte-audit-run","MMT_NONPRODUCTION":"1"}
    if any(os.environ.get(k)!=v for k,v in required.items()):deny("SCOPE_MISMATCH")
    w=pathlib.Path(os.environ["RUNNER_TEMP"])/"cert-a19-r23"
    if not w.is_dir():deny("EVIDENCE_DIRECTORY_ABSENT")
    return w
def read(p,cap):
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=cap:deny("FILE_NOT_PRESENT_OR_OVERSIZED")
    return p.read_bytes()
def check_inputs(w):
    inputs=[("APKINDEX.tar.gz",IDX,35_000_000),
            ("r18-result.json",R18,700_000),
            ("r22-loader-and-conflicts.json",R22,30_000)]
    for fn,h,cap in inputs:
        if sha(read(w/fn,cap))!=h:deny("FROZEN_PROVENANCE_DRIFT_"+fn)
    r18=json.loads((w/"r18-result.json").read_text())
    if not r18.get("all_selected_archives_verified") or r18.get("resolved_package_count")!=36:deny("R18_NO_CLOSURE")
    pkgs=r18.get("archive_verification",[])
    if len(pkgs)!=36:deny("INVALID_PACKAGE_COUNT")
    if set(ROOTS)-{p["package"] for p in pkgs}:deny("ROOTS_ABSENT")
    for n,v in ROOTS.items():
        if len([p for p in pkgs if p["package"]==n and p["version"]==v])!=1:deny("ROOT_VERSION_DRIFT")
    return sorted(pkgs,key=lambda x:x["package"])
def host_check(uri):
    p=urlsplit(uri);h=(p.hostname or "").lower()
    if p.scheme!="https" or p.username or p.password or p.port not in (None,443) or (h!="apk.cgr.dev" and not h.endswith(".r2.cloudflarestorage.com")):deny("UNTRUSTED_REDIRECT")
    return h
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        host_check(url)
        return super().redirect_request(req,fp,code,msg,headers,url)
opener=urllib.request.build_opener(Redirect())
def first_gzip(b):
    if b[:2]!=b"\x1f\x8b":deny("ARCHIVE_CONTROL_NOT_GZIP")
    z=zlib.decompressobj(16+zlib.MAX_WBITS)
    decoded=z.decompress(b,12_000_001)
    if not z.eof or len(decoded)>12_000_000:deny("CONTROL_UNBOUNDED")
    length=len(b)-len(z.unused_data)
    return b[:length],decoded,length
def prepare():
    w=d();packages=check_inputs(w)
    if (w/"apko-verified.status").read_text().strip()!="APKO_COSIGN_AND_SHA_PASS":deny("APKO_SIGNATURE_NOT_VERIFIED")
    if (w/"index-verified.status").read_text().strip()!="FROZEN_NATIVE_SIGNED_INDEX_ACCEPTED":deny("INDEX_SIGNATURE_NOT_ACCEPTED")
    repo=w/"repo"/"x86_64";repo.mkdir(parents=True,exist_ok=False)
    (repo/"APKINDEX.tar.gz").write_bytes(read(w/"APKINDEX.tar.gz",35_000_000))
    total=0
    for i,p in enumerate(packages,1):
        name=p["package"]+"-"+p["version"]+".apk"
        uri="https://apk.cgr.dev/chainguard/x86_64/"+name
        host_check(uri)
        with opener.open(urllib.request.Request(uri,headers={"User-Agent":"MMT-CERT-A19-R23-readonly-custody"}),timeout=55) as response:
            host_check(response.url)
            blob=response.read(CAP+1)
        if sha(blob)!=p["whole_apk_sha256"] or len(blob)!=p["whole_apk_bytes"]:deny("ARCHIVE_DIGEST_DRIFT_"+name)
        cg,unpacked,at=first_gzip(blob)
        if sha(cg)!=p["control_compressed_sha256"] or sha(blob[at:])!=p["data_compressed_sha256"]:deny("CONTROL_DATA_DRIFT_"+name)
        with tarfile.open(fileobj=io.BytesIO(unpacked),mode="r:") as t:
            members=[m for m in t if m.name==".PKGINFO" and m.isfile()]
            if len(members)!=1:deny("CONTROL_IDENTITY_ABSENT")
            f=t.extractfile(members[0])
            if f is None:deny("PKGINFO_UNREADABLE")
            props=dict(line.split(" = ",1) for line in f.read(100_000).decode().splitlines() if " = " in line)
        if props.get("pkgname")!=p["package"] or props.get("pkgver")!=p["version"] or props.get("datahash")!=sha(blob[at:]):deny("CONTROL_PACKAGE_MISMATCH")
        total+=len(blob)
        if total>TOTAL:deny("TOTAL_DOWNLOAD_CAP")
        (repo/name).write_bytes(blob)
        print("R23_REHYDRATED_PACKAGE="+str(i)+"/36:"+name,flush=True)
    config=["contents:","  repositories:","    - /mnt/work/repo","  keyring:"]
    keys=sorted((w/"keys").glob("*.pub"))
    if not 1<=len(keys)<=10:deny("KEYSET_MISSING")
    config.extend("    - /mnt/work/keys/"+k.name for k in keys)
    config.append("  packages:")
    config.extend("    - "+p["package"]+"="+p["version"] for p in packages)
    config.extend(["archs:","  - x86_64"])
    (w/"r23-minirootfs.apko.yaml").write_text("\n".join(config)+"\n")
    report={"stage":"CERT-A19-R23","phase":"PACKAGES_VERIFIED_MINIROOTFS_NOT_BUILT",
            "signed_index_sha256":IDX,"r18_evidence_sha256":R18,"r22_evidence_sha256":R22,
            "exact_36_archives_verified":36,"downloaded_bytes":total,
            "contents_are_package_only_without_base_overlay":True,
            "full_base_image_package_composition_tested":False,
            "target_python_node_ts_wasmtime_code_executed":False,
            "A6_hard_DENY":True,"original_199_findings_open":True,"CVEs_certified_closed":0,
            "production_authorized":False}
    (w/"r23-report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("R23_ALL_36_PINNED_PACKAGE_BYTES_REHYDRATED")

def norm(path):
    p=posixpath.normpath(path.lstrip("/").removeprefix("./"))
    if p in ("",".","..") or p.startswith("../"):deny("UNSAFE_PATH_IN_ROOTFS")
    return p
def resolve(path,nodes):
    cur=norm(path);trace=[];seen=set()
    for _ in range(40):
        parts=cur.split("/")
        for i in range(len(parts)):
            prefix="/".join(parts[:i+1])
            v=nodes.get(prefix)
            if v and v["type"]=="symlink":
                if prefix in seen:deny("SYMLINK_CYCLE")
                seen.add(prefix)
                value=v["target"]
                new=norm(posixpath.join(posixpath.dirname(prefix),value)) if not value.startswith("/") else norm(value)
                cur=norm(posixpath.join(new,*parts[i+1:]))
                trace.append({"link":prefix,"target":value,"resolved":cur})
                break
        else:
            return {"requested":path,"resolved":cur,"trace":trace,
                    "terminal":nodes.get(cur),"exists":cur in nodes}
    deny("SYMLINK_LIMIT")
def inspect():
    w=d()
    report=json.loads(read(w/"r23-report.json",30_000))
    if report.get("phase")!="PACKAGES_VERIFIED_MINIROOTFS_NOT_BUILT":deny("PREPARE_NOT_COMPLETE")
    artifact=w/"package-only-minirootfs.tar.gz"
    if not 0<artifact.stat().st_size<250_000_000:deny("ROOTFS_TARBALL_SIZE_LIMIT")
    paths={};n=0
    with tarfile.open(artifact,"r:gz") as t:
        for m in t:
            n+=1
            if n>25000:deny("ROOTFS_TAR_ENTRIES_TOO_MANY")
            p=norm(m.name)
            if p in paths:deny("ROOTFS_DUPLICATE_PATH")
            if m.isdir():v={"type":"directory"}
            elif m.issym():v={"type":"symlink","target":m.linkname}
            elif m.isfile():
                v={"type":"file","size":m.size}
                if p in ("usr/lib/ld-linux-x86-64.so.2","usr/bin/clear","usr/lib/apk/db/installed"):
                    f=t.extractfile(m)
                    if f is None:deny("IMPORTANT_ROOTFS_FILE_NOT_READABLE")
                    b=f.read(10_000_000)
                    if len(b)!=m.size:deny("IMPORTANT_ROOTFS_FILE_TRUNCATED")
                    v["sha256"]=sha(b)
                    if p=="usr/lib/apk/db/installed":v["contains_package_names"]={name:("P:"+name+"\n" in b.decode(errors="replace")) for name in ROOTS}
            elif m.islnk():v={"type":"hardlink","target":m.linkname}
            else:v={"type":"special-metadata-only"}
            paths[p]=v
    loader=resolve("lib64/ld-linux-x86-64.so.2",paths)
    clear=resolve("usr/bin/clear",paths)
    lib64=resolve("usr/lib64",paths)
    report.update({"phase":"PACKAGE_ONLY_MINIROOTFS_INSTALLED_AND_INSPECTED",
      "minirootfs_tar_sha256":sha(read(artifact,250_000_000)),
      "rootfs_tar_size":artifact.stat().st_size,
      "rootfs_entry_count":len(paths),
      "loader_path":loader,"clear_path":clear,"usr_lib64_path":lib64,
      "exact_pinned_loader_sha256_in_package_only_rootfs":loader.get("terminal",{}).get("sha256")==LOADER_SHA,
      "exact_ncurses_clear_sha256_in_package_only_rootfs":clear.get("terminal",{}).get("sha256")==CLEAR_SHA,
      "base_vs_ncurses_clear_collision_resolved":False,
      "apko_package_to_package_usr_lib64_final_type_observed":True,
      "base_image_composition_attempted":False,
      "no_executable_targets_started":True,
      "no_worker_image_created":True,
      "production_authorized":False})
    (w/"r23-report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("R23_PACKAGE_ONLY_ROOTFS_LOADER_SHA_PASS="+str(report["exact_pinned_loader_sha256_in_package_only_rootfs"]))
    print("R23_PACKAGE_ONLY_ROOTFS_CLEAR_SHA_PASS="+str(report["exact_ncurses_clear_sha256_in_package_only_rootfs"]))
    print("R23_PACKAGE_ONLY_USR_LIB64_TYPE="+str(lib64.get("terminal",{}).get("type")))
    print("R23_BASE_COLLISION_NOT_TESTED_A6_DENY_199_OPEN")

if __name__=="__main__":
    import sys
    if sys.argv[1:]==["prepare"]:prepare()
    elif sys.argv[1:]==["inspect"]:inspect()
    else:deny("UNKNOWN_PHASE")
