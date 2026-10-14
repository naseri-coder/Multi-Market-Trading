"""CERT-A19-R23: nonproduction signed-index APK minirootfs composition qualification.

No Worker, OCI image, guest-code execution, install scripts, production state.
Phase prepare downloads exact R18 archives and validates legacy signed-index
Q1 + PKGINFO datahash; inspect parses only output tar and refuses to call it
the final base+package composition (build-minirootfs excludes baseimage).
"""
from __future__ import annotations
import argparse, base64, hashlib, io, json, os, posixpath, re, tarfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import zlib

INDEX_SHA="8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
R18_SHA="78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b"
R22_SHA="41cefc3fc5e72ca023b3f915b5605b9dd950f24860d313c37de56309d67efec7"
LOADER_SHA="2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09"
APKO_RELEASE_SHA="5445ea2467a4ab0db3e31d9f795133128d0564c7afdaa46fcdaa1ee3cf92c757"
ROOTS={"glibc-2.44":"2.44-r8","python-3.12":"3.12.15-r3",
       "python-3.12-base":"3.12.15-r3","nodejs-24":"24.22.0-r0"}
N=36
MAX_APK=105_000_000
MAX_ALL=450_000_000
MAX_ARCHIVE=300_000_000

def deny(code):raise ValueError("CERT_A19_R23_"+code)
def sha(x):return hashlib.sha256(x).hexdigest()
def working():
    req={"GITHUB_ACTIONS":"true","GITHUB_REF":"refs/heads/cert-a19-byte-audit-run",
         "MMT_NONPRODUCTION":"1"}
    if any(os.environ.get(k)!=v for k,v in req.items()):deny("SCOPE_MUST_REMAIN_NONPRODUCTION")
    d=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r23"
    if not d.is_dir() or d.is_symlink():deny("WORKDIR_MISSING")
    return d
def read(p,cap):
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=cap:
        deny("EVIDENCE_MISSING_OR_OVERSIZED")
    return p.read_bytes()
def trusted(url):
    u=urlsplit(url); h=(u.hostname or "").lower()
    if (u.scheme!="https" or u.username or u.password or u.port not in (None,443) or
        (h!="apk.cgr.dev" and not h.endswith(".r2.cloudflarestorage.com"))):
        deny("BAD_PACKAGE_DOWNLOAD_HOST")
    return h
class Redirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        trusted(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
OPENER=build_opener(Redirect())

def member(raw,offset,cap):
    if raw[offset:offset+2]!=b"\x1f\x8b":deny("APK_MEMBER_NOT_GZIP")
    z=zlib.decompressobj(16+zlib.MAX_WBITS)
    buf=z.decompress(raw[offset:],cap+1)
    if not z.eof or len(buf)>cap:deny("APK_MEMBER_TRUNCATED_OR_OVERSIZED")
    used=len(raw[offset:])-len(z.unused_data)
    if used<18:deny("APK_GZIP_MEMBER_TOO_SMALL")
    return raw[offset:offset+used],buf,offset+used

def metadata(buf):
    with tarfile.open(fileobj=io.BytesIO(buf),mode="r:") as t:
        files=[x for x in t if x.name==".PKGINFO" and x.isfile()]
        if len(files)!=1:deny("PKGINFO_COUNT_INVALID")
        f=t.extractfile(files[0])
        if f is None:deny("PKGINFO_UNREADABLE")
        x=f.read(150_000).decode("utf8")
    out={}
    for line in x.splitlines():
        if " = " in line:
            k,v=line.split(" = ",1)
            out.setdefault(k,[]).append(v)
    return out

def state(d):
    if sha(read(d/"APKINDEX.tar.gz",35_000_000))!=INDEX_SHA:deny("R17_INDEX_DRIFT")
    if sha(read(d/"r18-result.json",700_000))!=R18_SHA:deny("R18_RESULT_DRIFT")
    if sha(read(d/"r22-loader-and-conflicts.json",25_000))!=R22_SHA:deny("R22_RESULT_DRIFT")
    j=json.loads((d/"r18-result.json").read_text())
    if j.get("resolved_package_count")!=36 or not j.get("all_selected_archives_verified"):
        deny("FROZEN_CLOSURE_UNRECOGNIZED")
    packages=j.get("resolved_packages",[])
    archive=j.get("archive_verification",[])
    if len(packages)!=36 or len(archive)!=36:deny("BAD_OR_DUPLICATE_CLOSURE")
    index={(x["name"],x["version"]):x for x in packages}
    observed={(x["package"],x["version"]):x for x in archive}
    if len(index)!=36 or set(index)!=set(observed):deny("CLOSURE_IDENTITY_MISMATCH")
    if not all((p,v) in index for p,v in ROOTS.items()):deny("MISSING_EXACT_ROOTS")
    return index,observed

def prepare():
    d=working()
    index,observed=state(d)
    repo=d/"localrepo"/"x86_64"
    repo.mkdir(parents=True,mode=0o755,exist_ok=False)
    (repo/"APKINDEX.tar.gz").write_bytes(read(d/"APKINDEX.tar.gz",35_000_000))
    total=0
    records=[]
    for i,(pkg,idx) in enumerate(sorted(index.items()),1):
        name,version=pkg
        obs=observed[pkg]
        basename=f"{name}-{version}.apk"
        url=f"https://apk.cgr.dev/chainguard/x86_64/{basename}"
        trusted(url)
        with OPENER.open(Request(url,headers={"User-Agent":"MMT-CERT-A19-R23-single-rootfs-nonproduction"}),timeout=50) as response:
            host=trusted(response.url)
            blob=response.read(MAX_APK+1)
        if len(blob)!=int(idx["signed_index_archive_size"]) or len(blob)>MAX_APK:
            deny("SIGNED_INDEX_ARCHIVE_SIZE_DISAGREEMENT")
        if sha(blob)!=obs["whole_apk_sha256"]:deny("R18_WHOLE_APK_SHA256_CHANGED")
        control,decoded,pos=member(blob,0,20_000_000)
        q1="Q1"+base64.b64encode(hashlib.sha1(control).digest()).decode()
        if q1!=idx["signed_index_control_checksum"] or sha(control)!=obs["control_compressed_sha256"]:
            deny("SIGNED_INDEX_Q1_CONTROL_DISAGREEMENT")
        props=metadata(decoded)
        if props.get("pkgname")!=[name] or props.get("pkgver")!=[version]:
            deny("PACKAGE_IDENTITY_INVALID")
        data_sha=sha(blob[pos:])
        if data_sha!=obs["data_compressed_sha256"] or props.get("datahash")!=[data_sha]:
            deny("CONTROL_BOUND_DATA_SHA256_INVALID")
        dest=repo/basename
        dest.write_bytes(blob)
        dest.chmod(0o644)
        total+=len(blob)
        if total>MAX_ALL:deny("TOTAL_PACKAGE_DOWNLOAD_OVER_CAP")
        records.append({"package":name,"version":version,"archive_sha256":sha(blob),
                        "distribution_host":host,"bytes":len(blob)})
        print("R23_REVALIDATED_SIGNED_INDEX_APK="+str(i)+"/36 "+basename,flush=True)
    keys=d/"keys"
    if not keys.is_dir() or not 1<=len(list(keys.glob("*.pub")))<=10:
        deny("SIGNED_BASE_KEYRING_NOT_PROVIDED")
    config=["contents:","  repositories:","    - /work/localrepo","  keyring:"]
    for key in sorted(keys.glob("*.pub")):
        config.append("    - /work/keys/"+key.name)
    config += ["  packages:"]
    for name,v in sorted(ROOTS.items()):
        config.append(f"    - {name}={v}")
    config+=["archs:","  - x86_64","entrypoint:","  command: /bin/true"]
    (d/"candidate.yaml").write_text("\n".join(config)+"\n")
    (d/"candidate.yaml").chmod(0o644)
    (d/"prepared.json").write_text(json.dumps({
        "stage":"CERT-A19-R23","phase":"SIGNED_INDEX_36_APK_BYTES_STAGED",
        "index_sha256":INDEX_SHA,"r18_report_sha256":R18_SHA,"r22_report_sha256":R22_SHA,
        "roots":ROOTS,"archive_count":len(records),"total_archive_bytes":total,
        "verified_archives":records,"apko_version":"v1.4.11",
        "apko_release_tarball_sha256":APKO_RELEASE_SHA,
        "base_image_not_part_of_minirootfs":True,
        "base_overlay_clear_collision_unproven":True,
        "worker_execution":False,"production_authorized":False},sort_keys=True,indent=2)+"\n")
    print("R23_ALL_36_APK_BYTES_VALIDATED_AND_LOCAL_SIGNED_INDEX_READY")

def cleanpath(s):
    s=s.lstrip("/").removeprefix("./").rstrip("/")
    if not s or any(x in (".","..") for x in s.split("/")) or "\x00" in s:
        deny("ROOTFS_UNSAFE_TAR_PATH")
    return posixpath.normpath(s)
def item(t,m):
    if m.isfile():
        if m.size>MAX_APK:deny("ROOTFS_FILE_SIZE_EXCEEDS_LIMIT")
        if m.name in ("usr/lib/ld-linux-x86-64.so.2","usr/bin/clear"):
            f=t.extractfile(m)
            if f is None:deny("ROOTFS_TARGET_FILE_CANNOT_READ")
            data=f.read(MAX_APK+1)
            return {"type":"file","bytes":len(data),"sha256":sha(data),
                    "elf_magic":data.startswith(b"\x7fELF")}
        return {"type":"file","bytes":m.size}
    if m.issym():return {"type":"symlink","target":m.linkname}
    if m.isdir():return {"type":"directory"}
    if m.islnk():return {"type":"hardlink","target":m.linkname}
    return {"type":"special-metadata-only"}
def resolve(name,table):
    path=cleanpath(name)
    seen=set()
    steps=[]
    for _ in range(40):
        parts=path.split("/")
        nextpath=None
        for k in range(len(parts)):
            prefix="/".join(parts[:k+1])
            p=table.get(prefix)
            if p and p["type"]=="symlink":
                if prefix in seen:deny("ROOTFS_SYMLINK_CYCLE")
                seen.add(prefix)
                parent=posixpath.dirname(prefix)
                target=p["target"]
                new=posixpath.normpath(posixpath.join(parent,target)) if not target.startswith("/") else cleanpath(target)
                remain="/".join(parts[k+1:])
                nextpath=posixpath.normpath(posixpath.join(new,remain)) if remain else new
                if nextpath.startswith("../"):deny("ROOTFS_SYMLINK_ESCAPES_NAMESPACE")
                steps.append({"link":prefix,"target":target,"result":nextpath})
                break
        if nextpath is None:
            target=table.get(path)
            return {"requested":name,"resolved_path":path,
                    "target":target,"found_regular_file":bool(target and target["type"]=="file"),
                    "symlink_chain":steps}
        path=cleanpath(nextpath)
    deny("ROOTFS_SYMLINK_DEPTH_EXCEEDED")
def installed_db(t,table):
    paths=[p for p in table if p.endswith("/apk/db/installed") and table[p]["type"]=="file"]
    results={}
    for path in paths:
        m=t.getmember(path)
        if m.size>600_000:deny("INSTALLED_DB_SIZE_EXCESS")
        f=t.extractfile(m)
        if f is None:deny("INSTALLED_DB_UNREADABLE")
        contents=f.read(600_001).decode("utf-8")
        records=[]
        for stanza in contents.split("\n\n"):
            fields=dict(line.split(":",1) for line in stanza.splitlines() if len(line)>2 and line[1]==":")
            if "P" in fields and "V" in fields:
                records.append((fields["P"],fields["V"]))
        results[path]=sorted(set(records))
    return results

def inspect():
    d=working()
    index,observed=state(d)
    prep=json.loads(read(d/"prepared.json",150_000))
    if prep.get("archive_count")!=36 or prep.get("index_sha256")!=INDEX_SHA:
        deny("ROOTFS_WITHOUT_PROVEN_PACKAGE_INPUTS")
    raw=read(d/"output"/"nonproduction-minirootfs.tar.gz",MAX_ARCHIVE)
    table={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:*") as t:
        members=t.getmembers()
        if len(members)>12000:deny("ROOTFS_TOO_MANY_MEMBERS")
        for m in members:
            if m.name in (".","./","/"):continue
            path=cleanpath(m.name)
            if path in table and table[path]["type"]!=("directory" if m.isdir() else "file" if m.isfile() else "symlink" if m.issym() else "other"):
                deny("ROOTFS_COLLIDING_DUPLICATE_TYPES")
            table[path]=item(t,m)
        loader=resolve("/lib64/ld-linux-x86-64.so.2",table)
        usr=resolve("/usr/lib64",table) if "usr/lib64" in table else None
        clear=resolve("/usr/bin/clear",table) if "usr/bin/clear" in table else None
        records=installed_db(t,table)
    package_list=set((name,version) for x in records.values() for name,version in x)
    exactly_matched=package_list==set(index)
    loader_sha=(loader["target"] or {}).get("sha256")
    loader_ok=loader["found_regular_file"] and loader_sha==LOADER_SHA
    usr_ok=bool(usr and usr["resolved_path"]=="usr/lib" and usr["target"] and usr["target"]["type"]=="directory")
    clear_ok=bool(clear and clear["found_regular_file"] and clear["target"].get("elf_magic"))
    decision=("PACKAGE_ONLY_MINIROOTFS_STATIC_LOADER_AND_LIB64_PASS_BASE_OVERLAY_NOT_TESTED"
              if loader_ok and usr_ok and clear_ok and exactly_matched else
              "PACKAGE_ONLY_MINIROOTFS_FAILED_EXACT_STATIC_AND_PACKAGE_DB_ASSERTIONS")
    report={
        "stage":"CERT-A19-R23","verdict":decision,
        "apko_version":"v1.4.11","apko_signer": "chainguard-dev/apko release.yaml pinned identity",
        "r18_pinned_signed_index_sha256":INDEX_SHA,"source_package_count":36,
        "source_archive_sha256_count":len(observed),
        "actual_apko_package_only_minirootfs_constructed_on_ephemeral_runner":True,
        "actual_wolfi_base_overlay_composition_tested":False,
        "base_usr_bin_clear_busybox_collision_closed":False,
        "mini_rootfs_sha256":sha(raw),"mini_rootfs_bytes":len(raw),
        "rootfs_entry_count":len(table),"installed_db_paths_found":list(records),
        "installed_package_count":len(package_list),"exact_36_package_db_match":exactly_matched,
        "final_usr_lib64":usr,"final_usr_bin_clear":clear,
        "final_loader_path":loader,"expected_loader_sha256":LOADER_SHA,
        "actual_loader_sha256":loader_sha,
        "loader_sha256_parity":loader_ok,
        "libffi_vs_baselayout_usr_lib64_dir_symlink_supported":usr_ok,
        "ncurses_clear_file_in_package_only_rootfs":clear_ok,
        "installed_database_package_matches":exactly_matched,
        "dynamic_loader_or_target_ELF_executed":False,
        "four_language_runtime_fixture_executed":False,
        "untrusted_worker_code_executed":False,
        "signed_apko_executed_in_restricted_nonproduction_container":True,
        "independent_rootless_gvisor_certified":False,
        "A6_hard_DENY":True,"199_findings_review_open":True,"CVE_closures":0,
        "production_authorized":False,"PR_merge_authorized":False,
        "post_build_output_rootfs_deleted_in_runner":False,
        "limitations":"Only package-only minirootfs; does not prove signed Wolfi base overlay, arbitrary code security, production viability or modern APK signatures."}
    (d/"r23-package-only-rootfs.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R23_STATIC_PACKAGE_ONLY_ROOTFS="+decision)
    print("R23_INSTALLED_PACKAGES="+str(len(package_list)))
    print("R23_LOADER_SHA256_MATCH="+str(loader_ok))
    print("R23_USR_LIB64_COMPATIBLE="+str(usr_ok))
    print("R23_BASE_USR_BIN_CLEAR_OVERLAY=NOT_TESTED")
    if not loader_ok or not usr_ok or not exactly_matched or not clear_ok:
        deny("COMPOSITION_FROZEN_EXPECTATIONS_UNMET")

if __name__=="__main__":
    cmd=argparse.ArgumentParser()
    cmd.add_argument("phase",choices=["prepare","inspect"])
    phase=cmd.parse_args().phase
    {"prepare":prepare,"inspect":inspect}[phase]()
