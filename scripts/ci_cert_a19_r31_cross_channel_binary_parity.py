"""CERT-A19-R31 — cross-distribution gVisor release byte parity (INERT DATA ONLY).

Compare official unsigned GitHub pinned SHA256 tar.zstd files against the
signed-vendor-APT OBSERVED R30 seven hashes. NOT independent GPG key approval,
NOT host qualification or target code execution, no install or guest launch.
"""
from __future__ import annotations
import hashlib,io,json,os,posixpath,re,subprocess,tarfile
from pathlib import Path

R29_REPORT="16400ae6890cbc5aae0a26df3179ab91db049b2d8fbce60c8e45646af2b0b160"
R30_REPORT="baefb28f1ee94932362078246cf6e6c8b4845b0c920938764d8e7926adc764da"
RELEASE_SHA="0a8a9058b9f11791a2097f03190c2ddc5b963c3dbee5bb9fd8497f4801c42f92"
CHECKSUM_SHA="dc3ea2d7486b9c07d9ad0ae3880b69a1a020708b83c4a8fe3bb781a871ef2308"
PUB_KEY_FPR_R30="6F1DF85E3A71C24918E727D56FC6D554E32BD943"
PUB_KEY_SHA_R30="757d2ebdf00cdc5661f88443e2bea848d3e2ded0780cbcd2d811be05e0c1d5dd"
STAGE="CERT-A19-R31"

def fail(x): raise ValueError(STAGE+"_"+x)
def sha(x):return hashlib.sha256(x).hexdigest()
def digest_file(path,cap):
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=cap:
        fail("UNBOUNDED_OR_MISSING_INPUT")
    h=hashlib.sha256()
    with path.open("rb") as f:
        while piece:=f.read(2**20):h.update(piece)
    return h.hexdigest()
def check_scope():
    for key,expected in {
        "GITHUB_ACTIONS":"true",
        "MMT_NONPRODUCTION":"1",
        "GITHUB_REF":"refs/heads/cert-a19-byte-audit-run"
    }.items():
        if os.getenv(key)!=expected:fail("RESTRICTED_SCRATCH_SCOPE")
    p=Path(os.environ["RUNNER_TEMP"])/"cert-a19-r31"
    if not p.is_dir():fail("EVIDENCE_ROOT_MISSING")
    return p
def safe_rel(name):
    n=name.removeprefix("./").rstrip("/")
    if n.startswith("/") or any(x in (".","..") for x in n.split("/")) or "\x00" in n:fail("TARBALL_UNSAFE_PATH")
    n=posixpath.normpath(n)
    if n==".":return "."
    if n.startswith("../"):fail("TARBALL_UNSAFE_NAME")
    if n.startswith("usr/bin/"):n=n[len("usr/bin/"):]
    return n
def files_stream(path,wanted):
    p=subprocess.Popen(["zstd","--decompress","--stdout","--",str(path)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    if p.stdout is None:fail("ZSTD_STREAM_UNAVAILABLE")
    found={}
    regular_count=0
    meta_count=0
    size_sum=0
    try:
        with tarfile.open(fileobj=p.stdout,mode="r|") as t:
            for member in t:
                meta_count+=1
                if meta_count>800:fail("TOO_MANY_TAR_ENTRIES")
                n=safe_rel(member.name)
                if member.isdir():continue
                if n==".":fail("NON_DIRECTORY_ROOT_TAR_ENTRY")
                if member.isfile():
                    regular_count+=1
                    if not 0<=member.size<=160_000_000:fail("TAR_MEMBER_SIZE_LIMIT")
                    size_sum+=member.size
                    if size_sum>1_250_000_000:fail("TOTAL_TAR_BYTES_LIMIT")
                    if n in wanted:
                        if n in found:fail("DUPLICATE_EXPECTED_TARBALL_PATH")
                        f=t.extractfile(member)
                        if f is None:fail("EXPECTED_FILE_UNAVAILABLE")
                        d=hashlib.sha256()
                        prefix=b""
                        read_size=0
                        while chunk:=f.read(1024*1024):
                            if len(prefix)<4:prefix=(prefix+chunk)[:4]
                            d.update(chunk);read_size+=len(chunk)
                        if read_size!=member.size:fail("EXPECTED_FILE_TRUNCATED")
                        found[n]={"sha256":d.hexdigest(),"bytes":read_size,"ELF_header":prefix==b"\x7fELF"}
                elif n in wanted:
                    found[n]={"member_type":"symlink_or_other","original_path":member.name}
    finally:
        p.stdout.close()
        try:p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill();p.wait();fail("ZSTD_PROCESS_TIMEOUT")
    if p.returncode!=0:fail("ZSTD_STREAM_INTEGRITY_FAILED")
    return found,regular_count,meta_count,size_sum
def main():
    d=check_scope()
    raw29=(d/"r29-policy-report.json").read_bytes()
    raw30=(d/"r30-apt-custody.json").read_bytes()
    if sha(raw29)!=R29_REPORT or sha(raw30)!=R30_REPORT:fail("SOURCE_EVIDENCE_DRIFT")
    r29=json.loads(raw29);r30=json.loads(raw30)
    if r30.get("stage")!="CERT-A19-R30" or r30.get("apt_signing_key_independently_authorized_fingerprint") is not False:fail("APT_PROOF_STATE_NOT_MATCHED")
    if r30.get("apt_signing_key_observed_fingerprint")!=PUB_KEY_FPR_R30 or r30.get("apt_signing_key_download_sha256")!=PUB_KEY_SHA_R30:fail("VENDOR_KEY_OBSERVATION_DRIFT")
    if not r30.get("apt_signature_gpgv_verified") or r30.get("physical_rootless_gvisor_host_certified") is not False:fail("R30_UNEXPECTED_PROOF_STATE")
    if digest_file(d/"SHA256SUMS",10_000)!=CHECKSUM_SHA:fail("R29_RELEASE_CHECKSUM_LISTING_DRIFT")
    index=(d/"SHA256SUMS").read_text()
    items={}
    for line in index.splitlines():
        m=re.fullmatch(r"([0-9a-f]{64})\s+\*?([A-Za-z0-9_.-]+)",line.strip())
        if not m or m.group(2) in items:fail("RELEASE_CHECKSUM_FORMAT_OR_DUPLICATE")
        items[m.group(2)]=m.group(1)
    filename="gvisor-x86_64.tar.zstd"
    if items.get(filename)!=RELEASE_SHA or digest_file(d/filename,150_000_000)!=RELEASE_SHA:
        fail("EXACT_GITHUB_RELEASE_TARBALL_SHA_MISMATCH")
    original=r30["runsc_binary_inventory"]["binary_files"]
    if len(original)!=7:fail("APT_ORIGINAL_BINARY_INVENTORY_INVALID")
    expected={}
    for row in original:
        path=row["path"]
        if not path.startswith("usr/bin/"):fail("APT_ARCHIVE_PATH_UNEXPECTED")
        name=path[len("usr/bin/"):]
        if name in expected:fail("DUPLICATE_APT_EXPECTED_FILENAME")
        expected[name]={"apt_sha256":row["sha256"],"apt_size":row["bytes"]}
    observed,count,metas,total=files_stream(d/filename,set(expected))
    records=[]
    for path in sorted(expected):
        apt=expected[path];github=observed.get(path)
        match=(github is not None and github.get("sha256")==apt["apt_sha256"] and github.get("bytes")==apt["apt_size"])
        records.append({"filename":path,"r30_signed_apt":apt,"github_release_archive":github,
                        "raw_sha256_and_size_match":bool(match)})
    actual=sum(int(x["raw_sha256_and_size_match"]) for x in records)
    status=("ALL_SEVEN_BINARY_BYTES_IDENTICAL_ACROSS_TWO_VENDOR_CHANNELS"
            if actual==7 else "VENDOR_RELEASE_AND_APT_BINARY_CONTENT_DIFFER__NOT_EQUIVALENT")
    report={
       "stage":STAGE,"status":status,
       "github_release_tag":"release-20261005.0",
       "github_tag_signer_verified":False,
       "github_release_asset_immutable":False,
       "github_release_checksum_file_sha256":CHECKSUM_SHA,
       "github_release_tarball_sha256":RELEASE_SHA,
       "r29_json_sha256":R29_REPORT,"r30_signed_apt_json_sha256":R30_REPORT,
       "signed_vendor_APT_GPGV_pass_from_R30":True,
       "vendor_key_observed_fingerprint":PUB_KEY_FPR_R30,
       "vendor_key_independently_approved":False,
       "bin_content_equal_count":actual,
       "bin_compared":7,
       "tar_regular_members_read":count,
       "tar_members_seen":metas,
       "tar_uncompressed_bytes_inspected":total,
       "compared_files":records,
       "vendor_channels_not_independent_publisher_attestation":True,
       "host_rootless_runsc_certified":False,
       "worker_or_guest_code_executed":False,
       "gvisor_binary_installed_or_executed":False,
       "original_199_security_findings_open":True,
       "CVEs_certified_closed":0,
       "A6_hard_DENY":True,
       "production_authorized":False
    }
    (d/"r31-two-channel-byte-parity.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("CERT_A19_R31_RELEASE_SHA256_CHECK_PASS")
    print("CERT_A19_R31_APT_VS_GITHUB_BINARY_MATCHES="+str(actual)+"/7")
    print("CERT_A19_R31_KEY_INDEPENDENT_APPROVAL=False_HOST_DENY_A6_DENY_199_OPEN")

if __name__=="__main__":main()
