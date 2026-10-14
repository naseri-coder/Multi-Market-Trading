"""CERT-A19-R22 — stopped signed Wolfi base vs APK loader bytes; apko source-policy custody.

Static research only: no apko build/installation, no loaded ELF, no Worker, no OCI launch.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import zlib

INDEX_SHA="8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
R18_SHA="78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b"
R21_SHA="8ccc6f9a02a373d2262dad6e9ebd9d3bf07b523fa850bbb82e83e2d1591847e8"
IMAGE="cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
SOURCE_COMMIT="5b3c3182430465dd2212a656411267f150034255"
GIT_BLOBS={"install.go":"627e6aae37100935e7b298874e224e26d3311a1f",
           "implementation.go":"588398c9bf71aae2c43bfb167500d5746b87ea64"}
TARGETS=("ld-linux-2.44","ncurses","libffi","wolfi-baselayout")
LINK="usr/lib/ld-linux-x86-64.so.2"
MAX_IMAGE=220_000_000
MAX_APK=100_000_000
MAX_INFLATE=310_000_000

def bad(reason):
    raise RuntimeError("CERT_A19_R22_"+reason)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def checked_bytes(path,max_size):
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=max_size:
        bad("MISSING_OR_OVERSIZED_FILE")
    return path.read_bytes()
def scope():
    required={"GITHUB_ACTIONS":"true","MMT_NONPRODUCTION":"1",
              "GITHUB_REF":"refs/heads/cert-a19-byte-audit-run"}
    if any(os.environ.get(k)!=v for k,v in required.items()):
        bad("NONPRODUCTION_SCOPE_REQUIRED")
    path=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r22"
    if not path.is_dir():bad("WORKSPACE_NOT_AVAILABLE")
    return path
def norm(s):
    p=s.lstrip("/").removeprefix("./").rstrip("/")
    if "\x00" in p or any(k in ("..",".") for k in p.split("/")):
        bad("UNTRUSTED_TAR_PATH")
    return p
def tar_details(blob, selected):
    out={}
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:") as archive:
        for m in archive:
            path=norm(m.name)
            if path not in selected:continue
            if path in out:bad("DUPLICATE_INTERESTING_PATH")
            if m.isfile():
                if not 0<m.size<3_000_000:bad("UNBOUNDED_INTERESTING_FILE")
                h=archive.extractfile(m)
                if h is None:bad("FILE_NOT_READABLE")
                raw=h.read(3_000_001)
                if len(raw)!=m.size:bad("FILE_TRUNCATED")
                out[path]={"type":"file","sha256":sha(raw),"bytes":len(raw),
                           "ELF_magic":raw[:4]==b"\x7fELF"}
            elif m.issym():
                out[path]={"type":"symlink","target":m.linkname}
            elif m.isdir():
                out[path]={"type":"directory"}
            elif m.islnk():
                out[path]={"type":"hardlink","target":m.linkname}
            else:
                out[path]={"type":"special-metadata-only"}
    return out
def decompress_gzip(raw,off,cap):
    if raw[off:off+2]!=b"\x1f\x8b":bad("APK_NOT_GZIP")
    decomp=zlib.decompressobj(16+zlib.MAX_WBITS)
    result=decomp.decompress(raw[off:],cap+1)
    if not decomp.eof or len(result)>cap:bad("APK_DECOMPRESSION_LIMIT")
    taken=len(raw[off:])-len(decomp.unused_data)
    return raw[off:off+taken],result,off+taken
def control_identity(tar_data):
    with tarfile.open(fileobj=io.BytesIO(tar_data),mode="r:") as t:
        entries=[m for m in t if m.name==".PKGINFO" and m.isfile()]
        if len(entries)!=1:bad("PKGINFO_MISSING")
        f=t.extractfile(entries[0])
        if f is None:bad("PKGINFO_UNREADABLE")
        txt=f.read(120_000).decode("utf-8")
    data={}
    for line in txt.splitlines():
        if " = " in line:
            k,v=line.split(" = ",1)
            data.setdefault(k,[]).append(v)
    return data
def apk_details(d,p):
    name=p["package"]; version=p["version"]
    file=d/"apks"/(name+"-"+version+".apk")
    raw=checked_bytes(file,MAX_APK)
    if len(raw)!=p["whole_apk_bytes"] or sha(raw)!=p["whole_apk_sha256"]:
        bad("HISTORIC_APK_SHA256_MISMATCH")
    ctrl,decoded,offset=decompress_gzip(raw,0,12_000_000)
    if sha(ctrl)!=p["control_compressed_sha256"]:bad("HISTORIC_APK_CONTROL_DRIFT")
    info=control_identity(decoded)
    if info.get("pkgname")!=[name] or info.get("pkgver")!=[version]:
        bad("APK_CONTROL_NAME_VERSION_CHANGED")
    if sha(raw[offset:])!=p["data_compressed_sha256"] or sha(raw[offset:])!=info.get("datahash",[""])[0]:
        bad("PKGINFO_DATA_SHA256_MISMATCH")
    _,data,end=decompress_gzip(raw,offset,MAX_INFLATE)
    if end!=len(raw):bad("APK_TRAILING_STREAM")
    wanted=(
        ("usr/lib/ld-linux-x86-64.so.2",)
        if name=="ld-linux-2.44" else
        ("usr/bin/clear",) if name=="ncurses" else
        ("usr/lib64",) if name in ("libffi","wolfi-baselayout") else ())
    detail=tar_details(data,set(wanted))
    for path in wanted:
        if path not in detail:bad("EXPECTED_APK_FILE_ABSENT_"+name)
    return {"name":name,"version":version,"full_archive_sha256":sha(raw),
            "pkginfo_origin":info.get("origin",[]),
            "pkginfo_replaces":info.get("replaces",[]),
            "pkginfo_provides":info.get("provides",[])[:25],
            "pkginfo_replaces_priority":info.get("replaces_priority",[]),
            "interesting_paths":detail}
def source_policy(d):
    path=d/"source"
    observations={}
    for filename,digest in GIT_BLOBS.items():
        raw=checked_bytes(path/filename,140_000)
        p=path/filename
        expected=(path/(filename+".git-blob.sha")).read_text().strip()
        if expected!=digest:bad("APKO_PINNED_GIT_BLOB_DRIFT")
        text=raw.decode("utf-8")
        observations[filename]={"git_blob_sha1":digest,"file_sha256":sha(raw),
                                "downloaded_from_commit":SOURCE_COMMIT}
    install=(path/"install.go").read_text()
    implementation=(path/"implementation.go").read_text()
    guards={
      "different_origin_or_replaces_controls_file_overwrite":
        "pk.Origin != pkg.Origin && !isReplaced" in install,
      "identical_file_sha1_keeps_existing":
        "bytes.Equal(checksum, fileExistsError.Sha1)" in install,
      "directory_accepted_if_existing_symlink_to_directory":
        "existing.Mode()&os.ModeSymlink != 0" in install,
      "symlink_same_target_skipped":
        "target == header.Linkname" in install,
      "symlink_creation_uses_fs_Symlink":
        "a.fs.Symlink(header.Linkname, header.Name)" in install,
      "usr_merge_provider_merged_lib":
        'slices.Contains(pkg.Provides, "merged-lib")' in implementation,
      "installed_package_conflict_abort":
        'cannot install due to conflict with' in implementation
    }
    if not all(guards.values()):bad("APKO_SOURCE_COMPOSITION_SEMANTICS_UNEXPECTED")
    return {"verified_source":observations,"code_guards":guards,
            "warning":"Source checks establish generic apko v1.4.11 rules, not final image installation order or a successful build."}
def main():
    d=scope()
    if (d/"base.txt").read_text().strip()!=IMAGE or (d/"base-signature.status").read_text().strip()!="SIGNED_PUBLISHER_VERIFIED":
        bad("SIGNED_BASE_NOT_VERIFIED")
    if sha(checked_bytes(d/"APKINDEX.tar.gz",35_000_000))!=INDEX_SHA:bad("SIGNED_INDEX_CHANGED")
    if sha(checked_bytes(d/"r18-result.json",700_000))!=R18_SHA:bad("R18_CLOSURE_CHANGED")
    if sha(checked_bytes(d/"r21-static-rootfs-path.json",35_000))!=R21_SHA:bad("R21_EVIDENCE_CHANGED")
    r18=json.loads((d/"r18-result.json").read_text())
    r21=json.loads((d/"r21-static-rootfs-path.json").read_text())
    if r18.get("resolved_package_count")!=36 or not r18.get("all_selected_archives_verified"):
        bad("R18_CLOSURE_NOT_VALID")
    if not r21["static_union_interpreter_lookup"]["found"] or r21["union_conflict_count"]!=1 or r21["duplicate_kind_conflict_count"]!=1:
        bad("R21_STATIC_COLLISIONS_CHANGED")
    base=tar_details(checked_bytes(d/"base-created-export.tar",MAX_IMAGE),{
         LINK,"lib64","usr/bin/clear","usr/lib64"})
    if base.get(LINK,{}).get("type")!="file" or not base[LINK]["ELF_magic"]:
        bad("SIGNED_BASE_LOADER_MISSING_OR_NOT_ELF")
    if base.get("lib64")!={"type":"symlink","target":"usr/lib"}:
        bad("BASE_LOADER_ALIAS_CHANGED")
    selected=[x for x in r18["archive_verification"] if x["package"] in TARGETS]
    if len(selected)!=4:bad("EXPECTED_PACKAGE_PROVENANCE_MISSING")
    items={x["package"]:apk_details(d,x) for x in selected}
    pkgloader=items["ld-linux-2.44"]["interesting_paths"].get(LINK,{})
    if pkgloader.get("type")!="file" or not pkgloader["ELF_magic"]:
        bad("PINNED_APK_LOADER_MISSING_OR_NOT_ELF")
    if items["ncurses"]["interesting_paths"]["usr/bin/clear"]["type"]!="file":
        bad("NCURSES_REGULAR_FILE_ABSENT")
    if items["libffi"]["interesting_paths"]["usr/lib64"]["type"]!="directory":
        bad("LIBFFI_DIRECTORY_ABSENT")
    if items["wolfi-baselayout"]["interesting_paths"]["usr/lib64"].get("type")!="symlink":
        bad("WOLFI_BASELAYOUT_LIB64_SYMLINK_MISSING")
    sources=source_policy(d)
    loader_equal=base[LINK]["sha256"]==pkgloader["sha256"]
    report={
        "stage":"CERT-A19-R22",
        "verdict":("STATIC_LOADER_BASE_APK_BYTE_PARITY_PASS_TWO_COMPOSITION_COLLISIONS_REMAIN"
                   if loader_equal else "STATIC_LOADER_BASE_APK_BYTE_MISMATCH_HARD_BLOCK"),
        "base_signed_image":IMAGE,"original_r18_report_sha256":R18_SHA,
        "original_r21_report_sha256":R21_SHA,"archived_signed_index_sha256":INDEX_SHA,
        "base_loader":base[LINK],"pinned_package_loader":pkgloader,
        "base_and_package_loader_sha256_equal":loader_equal,
        "base_paths_inspected":base,"four_apk_metadata":items,
        "apko_v1_4_11_source":sources,
        "base_ncurses_collision":"usr/bin/clear symlink -> executable file; actual install requires policy and ownership check",
        "libffi_baselayout_collision":"usr/lib64 directory vs symlink; install order and target type must be proven",
        "rootfs_installation_order_reconstructed":False,
        "package_manager_installed_or_executed":False,
        "final_rootfs_created":False,
        "dynamic_loader_executed":False,
        "four_language_fixture_executed":False,
        "original_199_critical_high_findings_review_open":True,
        "CVE_closures":0,"A6_hard_DENY":True,
        "independent_rootless_gvisor_certified":False,
        "production_authorized":False
    }
    (d/"r22-loader-and-conflicts.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("CERT_A19_R22_BASE_LOADER_SHA256="+base[LINK]["sha256"])
    print("CERT_A19_R22_PACKAGE_LOADER_SHA256="+pkgloader["sha256"])
    print("CERT_A19_R22_LOADER_FULL_SHA256_PARITY="+str(loader_equal))
    print("CERT_A19_R22_APKO_SOURCE_GIT_BLOBS_VERIFIED=2")
    print("CERT_A19_R22_TWO_COMPOSITION_COLLISIONS_UNRESOLVED_A6_DENY_199_OPEN")

if __name__=="__main__":
    main()
