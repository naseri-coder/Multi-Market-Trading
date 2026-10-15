"""CERT-A19-R24: signed Wolfi OCI base overlay, installer lock & static OCI-layer audit.

No executing any resulting target ELF, Python, JS, TS, WASM, Worker or guest code.
No image push; only source-authenticated apko in a constrained nonproduction runner.
"""
from __future__ import annotations
import base64,hashlib,io,json,os,pathlib,posixpath,re,tarfile
import urllib.request,zlib
from urllib.parse import urlsplit

IDX="8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
R18="78356a69bf4c7aa50856450b1b4f55f9aaaf4909072891909a9fe73697fd139b"
R23="1e649d3c64bcf70769b32885dcb192b2a3789a49852f1358460284692e814435"
LOADER_SHA="2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09"
CLEAR_SHA="98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed"
IMAGE="cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
MAX_FILE=125_000_000
MAX_TOTAL=450_000_000
SCOPED=("usr/bin/clear","usr/lib64","lib64","usr/lib/ld-linux-x86-64.so.2","usr/lib/apk/db/installed","lib/apk/db/installed")
ROOTS={"glibc-2.44":"2.44-r8","python-3.12":"3.12.15-r3","python-3.12-base":"3.12.15-r3","nodejs-24":"24.22.0-r0"}

def deny(x):raise RuntimeError("CERT_A19_R24_"+x)
def sha(b):return hashlib.sha256(b).hexdigest()
def root():
    if {k:os.getenv(k) for k in ("GITHUB_ACTIONS","GITHUB_REF","MMT_NONPRODUCTION")}!={"GITHUB_ACTIONS":"true","GITHUB_REF":"refs/heads/cert-a19-byte-audit-run","MMT_NONPRODUCTION":"1"}:
        deny("NONPRODUCTION_SCOPE")
    p=pathlib.Path(os.environ["RUNNER_TEMP"])/"cert-a19-r24"
    if not p.is_dir():deny("NO_SCRATCH_ROOT")
    return p
def read(p,limit):
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=limit:deny("FILE_MISSING_OR_TOO_BIG")
    return p.read_bytes()
def js(b):return json.loads(b)
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
def write_blob(layout,data):
    h=sha(data)
    dest=layout/"blobs"/"sha256"/h
    if not dest.exists():dest.write_bytes(data)
    return {"mediaType":"","digest":"sha256:"+h,"size":len(data)}
def host(url):
    u=urlsplit(url);h=(u.hostname or "").lower()
    if u.scheme!="https" or u.username or u.password or u.port not in (None,443) or (h!="apk.cgr.dev" and not h.endswith(".r2.cloudflarestorage.com")):
        deny("UNTRUSTED_CDN_HOST")
    return h
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        host(url)
        return super().redirect_request(req,fp,code,msg,headers,url)
OPENER=urllib.request.build_opener(Redirect())
def uncompress_one(b,pos,cap):
    if b[pos:pos+2]!=b"\x1f\x8b":deny("BAD_APK_GZIP")
    z=zlib.decompressobj(16+zlib.MAX_WBITS)
    out=z.decompress(b[pos:],cap+1)
    if not z.eof or len(out)>cap:deny("GZIP_INFLATION_LIMIT")
    consumed=len(b[pos:])-len(z.unused_data)
    return b[pos:pos+consumed],out,pos+consumed
def archive_fetch(p):
    url="https://apk.cgr.dev/chainguard/x86_64/"+p["package"]+"-"+p["version"]+".apk"
    host(url)
    with OPENER.open(urllib.request.Request(url,headers={"User-Agent":"MMT-CERT-A19-R24-custody-only"}),timeout=45) as response:
        host(response.url)
        data=response.read(MAX_FILE+1)
    if len(data)!=p["whole_apk_bytes"] or sha(data)!=p["whole_apk_sha256"]:deny("ARCHIVE_WHOLE_SHA_DRIFT")
    control,contents,offset=uncompress_one(data,0,17_000_000)
    if sha(control)!=p["control_compressed_sha256"] or sha(data[offset:])!=p["data_compressed_sha256"]:
        deny("ARCHIVE_CONTROL_OR_DATA_DRIFT")
    with tarfile.open(fileobj=io.BytesIO(contents),mode="r:") as t:
        mi=[m for m in t if m.name==".PKGINFO" and m.isfile()]
        if len(mi)!=1:deny("PKGINFO_MISSING")
        h=t.extractfile(mi[0])
        if h is None:deny("PKGINFO_UNREADABLE")
        props=dict(l.split(" = ",1) for l in h.read(100_000).decode().splitlines() if " = " in l)
    if (props.get("pkgname")!=p["package"] or props.get("pkgver")!=p["version"]
        or props.get("datahash")!=sha(data[offset:])):deny("PKGINFO_IDENTITY_DRIFT")
    return data
def base_oci_from_docker_save(w):
    raw_tar=w/"base-docker-save.tar"
    if not raw_tar.is_file():deny("DOCKER_SAVE_MISSING")
    layout=w/"base-oci"
    layout.mkdir(exist_ok=False)
    (layout/"blobs"/"sha256").mkdir(parents=True)
    (layout/"oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}\n')
    with tarfile.open(raw_tar,mode="r:") as archive:
        manifests=[m for m in archive if m.name=="manifest.json" and m.isfile()]
        if len(manifests)!=1:deny("DOCKER_SAVE_MANIFEST_NOT_FOUND")
        f=archive.extractfile(manifests[0])
        if f is None:deny("DOCKER_SAVE_MANIFEST_UNREADABLE")
        descriptors=json.loads(f.read(1_000_000))
        if len(descriptors)!=1:deny("DOCKER_SAVE_MULTI_IMAGE_NOT_EXPECTED")
        info=descriptors[0]
        layers=info.get("Layers",[])
        if not 1<=len(layers)<=40:deny("DOCKER_LAYERS_OUT_OF_RANGE")
        config_name=info.get("Config","")
        if not config_name.endswith(".json"):deny("CONFIG_NAME_INVALID")
        configmember=archive.getmember(config_name)
        fh=archive.extractfile(configmember)
        if fh is None:deny("CONFIG_UNREADABLE")
        cfg=fh.read(8_000_000)
        info_json=json.loads(cfg)
        if info_json.get("architecture")!="amd64" or info_json.get("os")!="linux":
            deny("OCI_WRONG_ARCH")
        if (w/"docker-image-id").read_text().strip()!="sha256:"+sha(cfg):
            deny("IMAGE_CONFIG_ID_DRIFT")
        blobc=write_blob(layout,cfg);blobc["mediaType"]="application/vnd.oci.image.config.v1+json"
        bl=[]
        for name in layers:
            member=archive.getmember(name)
            if not member.isfile() or member.size>180_000_000:deny("LAYER_TOO_LARGE")
            fh=archive.extractfile(member)
            if fh is None:deny("LAYER_NOT_READABLE")
            data=fh.read(180_000_001)
            if len(data)!=member.size:deny("LAYER_TRUNCATED")
            descriptor=write_blob(layout,data)
            descriptor["mediaType"]="application/vnd.oci.image.layer.v1.tar"
            bl.append(descriptor)
    manifest={"schemaVersion":2,"mediaType":"application/vnd.oci.image.manifest.v1+json",
        "config":blobc,"layers":bl}
    manifest_blob=write_blob(layout,canonical(manifest))
    manifest_blob["mediaType"]="application/vnd.oci.image.manifest.v1+json"
    manifest_blob["platform"]={"architecture":"amd64","os":"linux"}
    index={"schemaVersion":2,"mediaType":"application/vnd.oci.image.index.v1+json","manifests":[manifest_blob]}
    (layout/"index.json").write_bytes(canonical(index))
    return {"base_image_source":IMAGE,"docker_saved_config_sha256":sha(cfg),
            "oci_layout_manifest_digest":manifest_blob["digest"],"layer_count":len(layers)}
def prepare():
    w=root()
    for name,expected,cap in [("APKINDEX.tar.gz",IDX,35_000_000),
         ("r18-result.json",R18,700_000),("r23-package-only-rootfs.json",R23,60_000)]:
        if sha(read(w/name,cap))!=expected:deny("PRIOR_EVIDENCE_CHANGED_"+name)
    if (w/"base-signature.status").read_text().strip()!="BASE_SIGNED_IDENTITY_VERIFIED" or (w/"base-id").read_text().strip()!=IMAGE:
        deny("UNVERIFIED_BASE_SOURCE")
    if (w/"apko.status").read_text().strip()!="SIGNED_APKO_V1_4_11_CONFIRMED":deny("APKO_SOURCE_UNVERIFIED")
    if (w/"apkindex.status").read_text().strip()!="NATIVE_INDEX_SIGNATURE_ACCEPTED":deny("INDEX_SOURCE_UNVERIFIED")
    r18=js(read(w/"r18-result.json",700_000))
    packages=r18.get("archive_verification",[])
    if len(packages)!=36 or r18.get("resolved_package_count")!=36 or not r18.get("all_selected_archives_verified"):
        deny("R18_INVALID_PACKAGE_CLOSURE")
    base=base_oci_from_docker_save(w)
    # Authentic installed DB copied from CREATED and NOT STARTED signed image.
    installed=read(w/"base-installed",4_000_000)
    names=re.findall(rb"(?m)^P:([^\r\n]+)$",installed)
    if not 14<=len(names)<=60 or len(set(names))!=len(names):
        deny("BASE_INSTALLED_PACKAGE_RECORDS_UNEXPECTED")
    metadata=w/"base-metadata"/"x86_64"
    metadata.mkdir(parents=True)
    (metadata/"APKINDEX").write_bytes(installed)
    local=w/"repo"/"x86_64";local.mkdir(parents=True)
    (local/"APKINDEX.tar.gz").write_bytes(read(w/"APKINDEX.tar.gz",35_000_000))
    total=0
    for i,p in enumerate(packages,1):
        filename=p["package"]+"-"+p["version"]+".apk"
        data=archive_fetch(p)
        total+=len(data)
        if total>MAX_TOTAL:deny("DOWNLOAD_TOTAL_TOO_BIG")
        (local/filename).write_bytes(data)
        print("R24_VERIFIED_APK="+str(i)+"/36:"+filename,flush=True)
    keys=sorted((w/"keys").glob("*.pub"))
    if not 1<=len(keys)<=12:deny("WOLFI_KEYSET_ABSENT")
    config=["contents:","  baseimage:","    image: /work/base-oci",
            "    apkindex: /work/base-metadata","  repositories:",
            "    - /work/repo","  keyring:"]
    config.extend("    - /work/keys/"+k.name for k in keys)
    config.extend(["  packages:"])
    config.extend("    - "+p["package"]+"="+p["version"] for p in packages)
    config.extend(["archs:","  - x86_64"])
    (w/"r24-overlay.apko.yaml").write_text("\n".join(config)+"\n")
    obj={"stage":"CERT-A19-R24","phase":"BASE_OCI_AND_PINS_PREPARED__LOCK_AND_OVERLAY_NOT_YET_TESTED",
         "signed_base_image":IMAGE,"base":base,"base_installed_package_count":len(names),
         "base_installed_package_names":sorted(x.decode() for x in names),
         "R18_signed_index_sha256":IDX,"R18_report_sha256":R18,"R23_report_sha256":R23,
         "exact_package_archives_checked":36,"archive_total_bytes":total,
         "base_overlay_completed":False,"guest_or_worker_executed":False,
         "production_authorized":False,"A6_hard_DENY":True,"199_findings_open":True}
    (w/"r24-result.json").write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    print("R24_BASE_OCI_CONSTRUCTED_FROM_SIGNED_PULL__BASE_INSTALLED="+str(len(names)))
def inspect_lock():
    w=root()
    j=js(read(w/"r24-result.json",150_000))
    obj=js(read(w/"r24.lock.json",350_000))
    pk=obj.get("contents",{}).get("packages",[])
    if not isinstance(pk,list) or len(pk)>100:deny("LOCK_PACKAGES_INVALID")
    j.update({"lockfile_sha256":sha(read(w/"r24.lock.json",350_000)),
              "lockfile_package_count":len(pk),
              "lockfile_packages":[{"name":p.get("name"),"version":p.get("version")}
                                   for p in pk],
              "phase":"PINNED_BASE_OVERLAY_LOCK_CREATED__BUILD_PENDING"})
    (w/"r24-result.json").write_text(json.dumps(j,sort_keys=True,indent=2)+"\n")
    print("R24_BASE_OVERLAY_LOCKED_PACKAGE_COUNT="+str(len(pk)))
def norm(s):
    s=s.lstrip("/").removeprefix("./")
    if not s or "\x00" in s:deny("BAD_OCI_ENTRY_PATH")
    p=posixpath.normpath(s)
    if p in (".","..") or p.startswith("../"):deny("TAR_ENTRY_ESCAPE")
    return p
def resolve(path,entries):
    p=norm(path);steps=[];seen=set()
    for _ in range(35):
        parts=p.split("/")
        for i in range(len(parts)):
            part="/".join(parts[:i+1])
            m=entries.get(part)
            if m and m["type"]=="symlink":
                if part in seen:deny("LINK_CYCLE")
                seen.add(part)
                t=m["target"]
                tgt=norm(t) if t.startswith("/") else norm(posixpath.join(posixpath.dirname(part),t))
                p=norm(posixpath.join(tgt,*parts[i+1:]))
                steps.append({"path":part,"target":t,"resolved":p})
                break
        else:
            return {"path":path,"resolved":p,"steps":steps,"found":p in entries,
                    "terminal":entries.get(p)}
    deny("LINK_TOO_DEEP")
def apply_tar(b,entry,layer):
    with tarfile.open(fileobj=io.BytesIO(b),mode="r:") as t:
        for m in t:
            if m.name in (".","./",""):continue
            p=norm(m.name)
            dirname=posixpath.dirname(p);filename=posixpath.basename(p)
            if filename.startswith(".wh."):
                if filename==".wh..wh..opq":
                    base=dirname+"/" if dirname else ""
                    for old in [x for x in entry if x.startswith(base) and x!=dirname]:
                        del entry[old]
                else:
                    path=posixpath.join(dirname,filename[4:])
                    entry.pop(path,None)
                continue
            if p in SCOPED:
                if m.isdir(): obj={"type":"directory","layer":layer}
                elif m.issym(): obj={"type":"symlink","target":m.linkname,"layer":layer}
                elif m.isfile():
                    obj={"type":"file","size":m.size,"layer":layer}
                    f=t.extractfile(m)
                    if f is None:deny("FILE_ENTRY_UNREADABLE")
                    if m.size>5_000_000:deny("INTERESTING_FILE_OVERSIZED")
                    data=f.read(5_000_001)
                    if len(data)!=m.size:deny("FILE_ENTRY_TRUNCATED")
                    obj["sha256"]=sha(data)
                    if p.endswith("/installed"):
                        names=re.findall(rb"(?m)^P:([^\r\n]+)$",data)
                        obj["installed_count"]=len(names)
                        obj["installed_names"]=sorted(x.decode() for x in names)
                else:obj={"type":"special-or-hardlink","layer":layer}
                entry[p]=obj
            else:
                # Maintain at least all path existence and symlink routing.
                if m.isdir():obj={"type":"directory","layer":layer}
                elif m.issym():obj={"type":"symlink","target":m.linkname,"layer":layer}
                elif m.isfile():obj={"type":"file","size":m.size,"layer":layer}
                elif m.islnk():obj={"type":"hardlink","target":m.linkname,"layer":layer}
                else:obj={"type":"special","layer":layer}
                entry[p]=obj

def read_blob(layout,digest):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",digest):deny("BLOB_DIGEST_INVALID")
    b=read(layout/"blobs"/"sha256"/digest[7:],300_000_000)
    if sha(b)!=digest[7:]:deny("OCI_BLOB_SHA_MISMATCH")
    return b
def image_from_layout(layout):
    index=js(read(layout/"index.json",350_000))
    ms=index.get("manifests",[])
    if not len(ms)==1:deny("OCI_INDEX_MANIFEST_COUNT")
    x=js(read_blob(layout,ms[0]["digest"]))
    layers=x.get("layers",[])
    if not 1<=len(layers)<=60:deny("OCI_UNEXPECTED_LAYER_COUNT")
    return layers
def inspect_image():
    w=root()
    result=js(read(w/"r24-result.json",350_000))
    base_layout=w/"base-oci"
    output=w/"overlay-output"
    if not output.is_dir():deny("OCI_OVERLAY_NOT_CREATED")
    base_layers=image_from_layout(base_layout)
    final_layers=image_from_layout(output)
    # output OCI can be layered directly on base layer digests; if it is based
    # on the base OCI layout apko should preserve original layer references.
    if len(final_layers)<len(base_layers):deny("OUTPUT_FEWER_LAYERS_THAN_BASE")
    if [x["digest"] for x in final_layers[:len(base_layers)]]!=[x["digest"] for x in base_layers]:
        deny("BASE_LAYERS_NOT_PRESERVED_IN_OVERLAY")
    entries={}
    for i,layer in enumerate(final_layers):
        digest=layer["digest"]
        # apko output OCI may store the base blobs separately copied into output.
        b=read_blob(output,digest)
        media=layer["mediaType"]
        if media.endswith("+gzip"):
            import gzip
            payload=gzip.decompress(b)
        elif media.endswith(".tar"):
            payload=b
        else:deny("UNRECOGNIZED_OCI_LAYER_TYPE")
        apply_tar(payload,entries,i)
    loader=resolve("lib64/ld-linux-x86-64.so.2",entries)
    clear=resolve("usr/bin/clear",entries)
    lib64=resolve("usr/lib64",entries)
    xlib=entries.get("usr/lib/apk/db/installed") or entries.get("lib/apk/db/installed")
    loader_pass=loader.get("terminal",{}).get("sha256")==LOADER_SHA
    clear_pass=clear.get("terminal",{}).get("sha256")==CLEAR_SHA
    verdict=("BASE_OVERLAY_STATIC_LOADER_CLEAR_USRLIB64_PASS__NO_RUNTIME_CERTIFICATION"
             if loader_pass and clear_pass and lib64.get("terminal",{}).get("type")=="directory"
             else "BASE_OVERLAY_RESULT_DID_NOT_MATCH_ALL_EXPECTED_PATHS_FAIL_CLOSED")
    result.update({"phase":"BASE_IMAGE_AND_PACKAGES_OVERLAY_BUILT_NONPRODUCTION_STATIC_INSPECTION",
      "verdict":verdict,"base_oci_original_layer_count":len(base_layers),
      "output_oci_layer_count":len(final_layers),
      "output_index_sha256":sha(read(output/"index.json",350_000)),
      "signed_base_layers_prefix_preserved":True,
      "loader":loader,"clear":clear,"usr_lib64":lib64,
      "installed_database":xlib,
      "loader_exact_sha256_matches_frozen_source":loader_pass,
      "clear_exact_sha256_matches_ncurses":clear_pass,
      "output_not_published_and_not_executed":True,
      "four_language_fixture_executed":False,"independent_rootless_gvisor_certified":False,
      "original_199_security_findings_review_open":True,"CVEs_certified_closed":0,
      "A6_hard_DENY":True,"production_authorized":False})
    (w/"r24-result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("R24_BASE_OVERLAY_STATIC_LOADER_PASS="+str(loader_pass))
    print("R24_BASE_OVERLAY_STATIC_CLEAR_PASS="+str(clear_pass))
    print("R24_USR_LIB64="+str(lib64.get("terminal")))
    print("R24_FINAL_VERDICT="+verdict)
    print("R24_A6_DENY_199_OPEN_NO_WORKER_EXECUTION")

if __name__=="__main__":
    import sys
    modes={"prepare":prepare,"lock":inspect_lock,"inspect":inspect_image}
    if len(sys.argv)!=2 or sys.argv[1] not in modes:deny("PHASE_REQUIRED")
    modes[sys.argv[1]]()
