"""CERT-A19-R25 static-only FINAL composed Wolfi OCI filesystem / ELF / OS paths.

Inspects exactly 40-package R24-shaped output after independently rerunning signed
base, archived-index and apko lock+build. TARGET BINARIES NEVER EXECUTED.
All inspection uses GitHub runner Python/binutils, not Python/Node inside OCI.
"""
from __future__ import annotations
import gzip,hashlib,io,json,os,pathlib,posixpath,re,subprocess,tarfile
from collections import defaultdict

R24_PRIOR_SHA="284ccd9f9549fbcd6572c442cc5f9ebf5759d4cdf5ccb419f2235bff8a3e2f61"
BASE_IMAGE="cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
LOADER="2b1529d949956d0913dce1809976adf339adc0d992de5ae6eba21dad0fa9fb09"
NCURSES_CLEAR="98011ef86e4d2985ccc4d4a4e529c7790d1cc2e2f94ffa3296d4dc17f51377ed"
ROOTS={"nodejs-24","python-3.12","python-3.12-base","glibc-2.44"}
MAX_BLOB=260_000_000
MAX_TAR=480_000_000
MAX_EACH=125_000_000
MAX_FILES=33000
MAX_ELFS=500

def fatal(s):raise RuntimeError("CERT_A19_R25_"+s)
def digest(b):return hashlib.sha256(b).hexdigest()
def root():
    if any(os.environ.get(k)!=v for k,v in {
        "GITHUB_ACTIONS":"true","GITHUB_REF":"refs/heads/cert-a19-byte-audit-run",
        "MMT_NONPRODUCTION":"1"}.items()):fatal("SCOPED_NONPRODUCTION_RUNNER_REQUIRED")
    d=pathlib.Path(os.environ["RUNNER_TEMP"])/"cert-a19-r24"
    if not d.is_dir():fatal("NO_R24_OUTPUT_IN_CURRENT_RUN")
    return d
def read(path,maximum):
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=maximum:
        fatal("MISSING_OR_OVERSIZED_SOURCE_FILE")
    return path.read_bytes()
def blob(layout,ref):
    if not isinstance(ref,str) or not re.fullmatch(r"sha256:[0-9a-f]{64}",ref):fatal("INVALID_OCI_DIGEST")
    b=read(layout/"blobs"/"sha256"/ref[7:],MAX_BLOB)
    if digest(b)!=ref[7:]:fatal("OCI_CONTENT_MISMATCH")
    return b
def pathsafe(path):
    p=posixpath.normpath(path.lstrip("/").removeprefix("./"))
    if p in (".","","..") or p.startswith("../") or "\x00" in p:fatal("UNSAFE_TAR_ENTRY")
    return p
def target(path,value):
    if not value or "\x00" in value:fatal("BAD_SYMLINK")
    return pathsafe(value) if value.startswith("/") else pathsafe(posixpath.join(posixpath.dirname(path),value))
def resolve(path,nodes):
    p=pathsafe(path);trace=[];seen=set()
    for _ in range(45):
        parts=p.split("/")
        for i in range(len(parts)):
            prefix="/".join(parts[:i+1])
            v=nodes.get(prefix)
            if v and v["kind"] in ("symlink","hardlink"):
                if prefix in seen:fatal("SYMLINK_CYCLE")
                seen.add(prefix)
                nex=target(prefix,v["link"])
                p=pathsafe(posixpath.join(nex,*parts[i+1:]))
                trace.append({"path":prefix,"link":v["link"],"resolves":p})
                break
        else:return {"requested":path,"resolved":p,"found":p in nodes,
                     "terminal":nodes.get(p),"trace":trace}
    fatal("LINK_DEPTH_EXCEEDED")

def readelf(path):
    def invoke(flag):
        cmd=subprocess.run(["readelf","--wide",flag,str(path)],capture_output=True,text=True,
                           timeout=45,check=False)
        if cmd.returncode!=0:fatal("READ_ELF_"+flag.replace("-","_")+"_FAIL")
        return cmd.stdout[:400000]
    hdr=invoke("-h")
    if "Advanced Micro Devices X86-64" not in hdr:fatal("UNEXPECTED_ELF_ARCH")
    dyn=invoke("-d"); vers=invoke("-V"); prog=invoke("-l")
    glibc=sorted(set(re.findall(r"GLIBC_([0-9]+\.[0-9]+)",vers)),
                 key=lambda a:tuple(map(int,a.split("."))))
    return {"arch":"ELF64-x86_64","needed":sorted(set(re.findall(
            r"\(NEEDED\).*?Shared library:\s*\[([^\]]+)\]",dyn))),
        "soname":sorted(set(re.findall(
            r"\(SONAME\).*?Library soname:\s*\[([^\]]+)\]",dyn))),
        "interpreter":re.findall(r"\[Requesting program interpreter:\s*([^\]]+)\]",prog),
        "rpath_runpath":re.findall(r"\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]",dyn),
        "highest_required_glibc":glibc[-1] if glibc else None}

def get_layers(layout):
    index=json.loads(read(layout/"index.json",500000))
    if len(index.get("manifests",[]))!=1:fatal("OCI_EXPECTED_ONE_MANIFEST")
    man=json.loads(blob(layout,index["manifests"][0]["digest"]))
    if man.get("schemaVersion")!=2:fatal("MANIFEST_SCHEMA")
    layers=man.get("layers",[])
    if not 11<=len(layers)<=26:fatal("UNEXPECTED_LAYER_COUNT")
    return layers

def scan():
    d=root()
    original=read(d/"r24-result.json",300000)
    current=json.loads(original)
    prior=json.loads(read(d/"r24-prior-result.json",300000))
    if digest(read(d/"r24-prior-result.json",300000))!=R24_PRIOR_SHA:
        fatal("PRIOR_SUCCESS_PROOF_DRIFT")
    if (prior.get("installed_database",{}).get("installed_count")!=40 or
        prior.get("base",{}).get("base_image_source")!=BASE_IMAGE or
        prior.get("verdict")!="BASE_OVERLAY_STATIC_LOADER_CLEAR_USRLIB64_PASS__NO_RUNTIME_CERTIFICATION"):
        fatal("PRIOR_SUCCESS_INSUFFICIENT")
    if not (current.get("signed_base_layers_prefix_preserved") and
            current.get("installed_database",{}).get("installed_count")==40 and
            current.get("loader_exact_sha256_matches_frozen_source") and
            current.get("clear_exact_sha256_matches_ncurses")):
        fatal("CURRENT_R24_STATIC_GATE_NOT_PASSED")
    if current.get("base",{}).get("base_image_source")!=BASE_IMAGE:
        fatal("CURRENT_BASE_DIFFERS_FROM_CERTIFIED_SOURCE")
    if current.get("phase")!="BASE_IMAGE_AND_PACKAGES_OVERLAY_BUILT_NONPRODUCTION_STATIC_INSPECTION":
        fatal("WRONG_SOURCE_BUILD_PHASE")
    layout=d/"output"/"oci"
    layers=get_layers(layout)
    temp=d/"r25-inspect-scratch"
    temp.mkdir(mode=0o700,exist_ok=False)
    files={}
    counters={"whiteouts":0,"opaque_markers":0,"special_metadata_only":0,
              "file_path_type_overwrites":0,"tar_entry_count":0}
    stored_payload={}
    important={"etc/os-release","usr/lib/os-release","etc/passwd","etc/group",
        "etc/nsswitch.conf","etc/resolv.conf","etc/hosts",
        "etc/ssl/certs/ca-certificates.crt","etc/ssl/cert.pem",
        "usr/lib/ssl/cert.pem","usr/share/zoneinfo/UTC",
        "usr/lib/apk/db/installed","lib/apk/db/installed"}
    for layer_number,l in enumerate(layers):
        b=blob(layout,l["digest"]);media=l.get("mediaType","")
        if media.endswith("+gzip"):
            with gzip.GzipFile(fileobj=io.BytesIO(b)) as gz:
                raw=gz.read(MAX_TAR+1)
        elif media.endswith(".tar"):
            raw=b
        else:fatal("UNSUPPORTED_LAYER_FORMAT")
        if len(raw)>MAX_TAR:fatal("LAYER_EXPANSION_LIMIT")
        with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as tar:
            for member in tar:
                counters["tar_entry_count"]+=1
                if counters["tar_entry_count"]>MAX_FILES:fatal("ENTRY_COUNT_OVER")
                if member.name in ("",".","./"):continue
                path=pathsafe(member.name)
                parent=posixpath.dirname(path);base=posixpath.basename(path)
                if base.startswith(".wh."):
                    counters["whiteouts"]+=1
                    if base==".wh..wh..opq":
                        counters["opaque_markers"]+=1
                        prefix=parent+"/" if parent else ""
                        for old in [k for k in files if k.startswith(prefix) and k!=parent]:
                            files.pop(old,None)
                    else:
                        p=posixpath.join(parent,base[4:])
                        files.pop(p,None)
                    continue
                old=files.get(path)
                if member.isdir(): meta={"kind":"directory"}
                elif member.issym():meta={"kind":"symlink","link":member.linkname}
                elif member.islnk():meta={"kind":"hardlink","link":member.linkname}
                elif member.isfile():
                    if member.size>MAX_EACH:fatal("OVERSIZED_FILE_ENTRY")
                    meta={"kind":"file","size":member.size}
                    extract=tar.extractfile(member)
                    if extract is None:fatal("TAR_FILE_READ_FAILED")
                    # Read only head; read complete bounded selected files.
                    prefix=extract.read(4)
                    if prefix==b"\x7fELF":
                        payload=prefix+extract.read(MAX_EACH+1)
                        if len(payload)!=member.size:fatal("ELF_TRUNCATED")
                        sh=digest(payload)
                        payload_path=temp/sh
                        if not payload_path.exists():payload_path.write_bytes(payload)
                        meta["sha256"]=sh
                        meta["elf"]=True
                        stored_payload[sh]=payload_path
                    elif path in important:
                        payload=prefix+extract.read(3_000_001)
                        if len(payload)!=member.size or len(payload)>3_000_000:
                            fatal("TEXT_SYSTEM_FILE_SIZE_OR_TRUNCATION")
                        meta["sha256"]=digest(payload)
                        meta["inspect_text"]=payload.decode("utf-8",errors="replace")
                    elif path in ("usr/bin/node","usr/bin/python3.12",
                                  "usr/lib/ld-linux-x86-64.so.2","usr/bin/clear"):
                        payload=prefix+extract.read(MAX_EACH+1)
                        if len(payload)!=member.size:fatal("IMPORTANT_EXECUTABLE_TRUNCATED")
                        meta["sha256"]=digest(payload)
                    # All other file bodies ignored (no execution, no extraction).
                else:
                    counters["special_metadata_only"]+=1
                    meta={"kind":"special-metadata-only"}
                meta["layer"]=layer_number
                if old and old["kind"]!=meta["kind"]:
                    counters["file_path_type_overwrites"]+=1
                files[path]=meta
        print("R25_SCANNED_SIGNED_BASE_OR_OVERLAY_LAYER="+str(layer_number+1)+"/"+str(len(layers)),flush=True)
    elves=[]
    for path,info in files.items():
        if info.get("elf"):
            source=stored_payload.get(info["sha256"])
            if source is None:fatal("LOST_STATIC_ELF_SOURCE")
            if len(elves)>=MAX_ELFS:fatal("ELF_COUNT_OVER")
            e=readelf(source)
            e.update({"path":path,"sha256":info["sha256"],"layer":info["layer"]})
            elves.append(e)
    for payload in temp.iterdir():payload.unlink()
    temp.rmdir()
    if len(elves)<140:fatal("IMPLAUSIBLY_FEW_ELF_OBJECTS")
    basename={}
    for path,x in files.items():
        if x["kind"] in ("file","symlink","hardlink"):
            basename.setdefault(posixpath.basename(path),[]).append(path)
    for e in elves:
        for soname in e["soname"]:
            basename.setdefault(soname,[]).append(e["path"])
    missing={}
    multi={}
    for e in elves:
        for name in e["needed"]:
            found=sorted(set(basename.get(name,[])))
            if not found:missing.setdefault(name,set()).add(e["path"])
            elif len(found)>1:multi.setdefault(name,set()).update(found)
    missing={k:sorted(v) for k,v in sorted(missing.items())}
    multi={k:sorted(v) for k,v in sorted(multi.items())}
    loader=resolve("lib64/ld-linux-x86-64.so.2",files)
    clear=resolve("usr/bin/clear",files)
    node=resolve("usr/bin/node",files)
    python=resolve("usr/bin/python3.12",files)
    nss=resolve("etc/nsswitch.conf",files)
    trust_checks={}
    for path in ("etc/os-release","usr/lib/os-release","etc/passwd","etc/group",
                 "etc/nsswitch.conf","etc/ssl/certs/ca-certificates.crt",
                 "etc/ssl/cert.pem","usr/lib/ssl/cert.pem","usr/share/zoneinfo/UTC"):
        x=resolve(path,files)
        last=x["terminal"] or {}
        z={"found":x["found"],"kind":last.get("kind"),"resolved":x["resolved"]}
        if "inspect_text" in last:
            b=last["inspect_text"]
            z["sha256"]=last.get("sha256")
            if path.endswith("os-release"):
                z["ID_wolfi"]=bool(re.search(r"(?m)^ID=wolfi$",b))
            elif path.endswith("passwd"):
                z["root_uid_record_present"]=bool(re.search(r"(?m)^root:[^:]*:0:0:",b))
                z["unprivileged_user_record_present"]=bool(re.search(r"(?m)^[^:]+:[^:]*:(?:65534|65532):",b))
            elif path.endswith("group"):
                z["root_gid_record_present"]=bool(re.search(r"(?m)^root:[^:]*:0:",b))
            elif "cert" in path:
                z["PEM_CERTIFICATE_MARKER_COUNT"]=b.count("-----BEGIN CERTIFICATE-----")
            elif "nsswitch" in path:
                z["hosts_or_passwd_service_entries"]=list(re.findall(r"(?m)^(?:hosts|passwd|group):[^\n]*",b))
        trust_checks[path]=z
    max_glibc=max([tuple(map(int,e["highest_required_glibc"].split(".")))
                   for e in elves if e["highest_required_glibc"]]+[(0,0)])
    loader_ok=loader["terminal"] and loader["terminal"].get("sha256")==LOADER
    clear_ok=clear["terminal"] and clear["terminal"].get("sha256")==NCURSES_CLEAR
    absent_python=not python["found"]
    absent_node=not node["found"]
    hard_fail=bool(not loader_ok or not clear_ok or absent_node or absent_python
         or max_glibc>(2,44))
    status=("STATIC_OCI_ELF_PATH_HARD_GATE_FAIL" if hard_fail else
            "40_PACKAGE_COMPOSED_OCI_STATIC_ELF_AND_OS_IDENTITY_AUDITED__RUNTIME_NOT_CERTIFIED")
    output={
      "stage":"CERT-A19-R25","verdict":status,
      "prior_successful_R24_JSON_sha256":R24_PRIOR_SHA,
      "current_R24_JSON_sha256":digest(original),
      "current_output_OCI_index_sha256":digest(read(layout/"index.json",500000)),
      "original_base_digest":BASE_IMAGE,
      "final_installed_package_count":40,
      "signed_base_layer_count":11,
      "final_oci_layer_count":len(layers),
      "total_merged_final_file_paths":len(files),
      "tar_and_whiteout_observations":counters,
      "ELF_objects_static_readelf_count":len(elves),
      "elf_max_GLIBC_required":"%d.%d"%max_glibc,
      "DT_NEEDED_names_without_filename_or_SONAME_candidate":missing,
      "DT_NEEDED_names_with_multiple_candidate_paths":multi,
      "final_loader_path":loader,"final_clear_path":clear,
      "final_node_path":node,"final_python3_12_path":python,
      "final_OS_NSS_CA_and_tz_source_path_observations":trust_checks,
      "ELF_objects":elves,
      "all_needed_names_statically_linked_at_elf_loader_runtime":False,
      "actual_OS_network_tls_certificate_verification_tested":False,
      "actual_python_node_wasmtime_typescript_execution_tested":False,
      "typescript_5_9_3_and_wasmtime_49_installed_in_this_image":False,
      "four_language_worker_fixture_equivalence_tested":False,
      "independent_rootless_oci_gvisor_host_certified":False,
      "original_199_security_findings_review_open":True,
      "cves_certified_closed":0,
      "A6_hard_DENY":True,
      "production_authorized":False,
      "no_guest_executable_or_worker_was_run":True
    }
    (d/"r25-static-final-oci.json").write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    print("R25_COMPOSED_OCI_FINAL_ELF_COUNT="+str(len(elves)))
    print("R25_COMPOSED_OCI_MISSING_DT_NEEDED_NAMES="+str(len(missing)))
    print("R25_COMPOSED_OCI_NODE_PYTHON_LOADER_STATIC_PRESENT="+str(not hard_fail))
    print("R25_FINAL_VERDICT="+status)
    print("R25_A6_HARD_DENY_199_OPEN_NO_WORKER_EXECUTED")
    if hard_fail:fatal("FINAL_OCI_STATIC_HARD_GATE_BLOCKED")

if __name__=="__main__":scan()
