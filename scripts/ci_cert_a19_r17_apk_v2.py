"""CERT-A19-R17: independently check APK v2 segments against a signed index.

Read-only parsing and OpenSSL verification. Never execute archive members.
A signed APKINDEX Q1 checksum is SHA-1 of the compressed control member,
not the whole APK. Record SHA-256 of all three raw streams as additional custody.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import zlib

ROOTS = {
    "glibc-2.44": "2.44-r8",
    "python-3.12": "3.12.15-r3",
    "python-3.12-base": "3.12.15-r3",
    "nodejs-24": "24.22.0-r0",
}
PINS = {
    ("glibc-2.44", "2.44-r8"): "e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0",
    ("python-3.12", "3.12.15-r3"): "8086d4e00e7c479957b6b863a31958f9de8e54e2890ca8624dd5dab37f047293",
    ("python-3.12-base", "3.12.15-r3"): "ca4ac0aef2c9dea512ce43510b247a8b082593a8af3e50842b06fadc3935db0a",
    ("nodejs-24", "24.22.0-r0"): "8c007c9f6027020d5cc580613d59ade62205b0875d93d6be8c2042ce8b130bcf",
}
REPO="https://apk.cgr.dev/chainguard"
PREFIX="CERT_A19_R17_"
MAGIC=b"\x1f\x8b"


def fail(code):
    raise ValueError(PREFIX+code)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def check_environment():
    if (os.environ.get("GITHUB_ACTIONS")!="true"
        or os.environ.get("GITHUB_REF")!="refs/heads/cert-a19-byte-audit-run"
        or os.environ.get("MMT_NONPRODUCTION")!="1"):
        fail("FIXED_NONPRODUCTION_SCOPE")
    return Path(os.environ["RUNNER_TEMP"])/"cert-a19-r17"


def read(path, maximum=90_000_000):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
        fail("MISSING_OR_UNBOUNDED_INPUT")
    return path.read_bytes()


def parse_signed_index(raw):
    try:
        with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
            x=[m for m in t.getmembers() if m.name=="APKINDEX" and m.isfile()]
            if len(x)!=1 or x[0].size>65_000_000:fail("BAD_INDEX_STRUCTURE")
            content=t.extractfile(x[0]).read(65_000_001).decode("utf-8")
        if len(content)>65_000_000:fail("INDEX_UNBOUNDED")
        matches={}
        for para in content.split("\n\n"):
            p={}
            for line in para.splitlines():
                if len(line)>2 and line[1]==":" and line[0].isalpha():
                    p[line[0]]=line[2:]
            if p.get("P") in ROOTS and p.get("V")==ROOTS[p["P"]]:
                key=(p["P"],p["V"])
                if key in matches: fail("DUPLICATE_ROOT_INDEX_ENTRY")
                matches[key]=p
        if set(matches)!=set(PINS):fail("FROZEN_ROOT_INDEX_IDENTITY_MISSING")
        return matches
    except (tarfile.TarError,UnicodeError,AttributeError) as e:
        raise ValueError(PREFIX+"INDEX_PARSE_FAILED") from e


def split_stream(raw, off, max_output):
    if not raw[off:].startswith(MAGIC):fail("NOT_GZIP_STREAM")
    z=zlib.decompressobj(wbits=16+zlib.MAX_WBITS)
    out=z.decompress(raw[off:],max_output+1)
    if len(out)>max_output or not z.eof:
        print("R17_GZIP_STREAM_DIAGNOSTIC_offset="+str(off)+"_inflated="+str(len(out))+"_limit="+str(max_output)+"_eof="+str(z.eof)+"_unconsumed="+str(len(z.unconsumed_tail)))
        fail("GZIP_STREAM_TRUNCATED_OR_UNBOUNDED")
    taken=len(raw[off:])-len(z.unused_data)
    if taken<16:fail("GZIP_STREAM_TOO_SHORT")
    return raw[off:off+taken],out,off+taken


def safe_tar(blob,max_total):
    if len(blob)>max_total:fail("TAR_TOO_BIG")
    try:
        with tarfile.open(fileobj=io.BytesIO(blob),mode="r:") as archive:
            files={}
            for m in archive:
                if not m.isfile():continue
                if m.size>max_total or m.name in files:fail("INVALID_TAR_ENTRY")
                if len(files)>=20:fail("TOO_MANY_CONTROL_FILES")
                f=archive.extractfile(m)
                if f is None:fail("EMPTY_TAR_MEMBER")
                files[m.name]=f.read(max_total+1)
                if len(files[m.name])>max_total:fail("TAR_MEMBER_TOO_LARGE")
            return files
    except (tarfile.TarError,OSError) as exc:
        raise ValueError(PREFIX+"INVALID_CONTROL_OR_SIGNATURE_TAR") from exc


def find_pkinfo(text):
    out={}
    for line in text.decode("utf-8","strict").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k,v=line.split("=",1)
            out[k.strip()]=v.strip()
    return out


def validate_pkg(path,idx,keydir,temp):
    raw=read(path)
    name,version=idx["P"],idx["V"]
    if sha(raw)!=PINS[(name,version)] or len(raw)!=int(idx["S"]):
        fail("ARCHIVE_FULL_SHA256_OR_INDEX_SIZE_MISMATCH")
    first_gz,first_blob,pos=split_stream(raw,0,15_000_000)
    files=safe_tar(first_blob,15_000_000)
    print("R17_FIRST_STREAM_PACKAGE="+name+"_gz="+str(len(first_gz))+
          "_inflated="+str(len(first_blob))+"_names="+",".join(sorted(files)[:8]))
    sig_filenames=[x for x in files if x.startswith(".SIGN.")]
    standalone_signature_present=bool(sig_filenames)

    if standalone_signature_present:
        if len(sig_filenames)!=1 or len(files)!=1:
            fail("SIGNATURE_MEMBER_FORMAT_UNEXPECTED")
        signature_name=sig_filenames[0]
        signature=files[signature_name]
        control_gz,control_blob,nextpos=split_stream(raw,pos,15_000_000)
        meta=safe_tar(control_blob,15_000_000)
    else:
        # Some Wolfi direct APKs omit a per-archive RSA stream.
        # Signed repository index Q1 and PKGINFO datahash are distinct checks.
        signature_name=None
        signature=None
        control_gz,control_blob,nextpos=first_gz,first_blob,pos
        meta=files
    if ".PKGINFO" not in meta:
        fail("PKGINFO_NOT_FOUND_IN_CONTROL_SEGMENT")
    if nextpos>=len(raw) or not raw[nextpos:].startswith(MAGIC):
        fail("DATA_GZIP_STREAM_NOT_FOUND")
    data_gz=raw[nextpos:]
    props=find_pkinfo(meta[".PKGINFO"])
    if props.get("pkgname")!=name or props.get("pkgver")!=version:
        fail("PKGINFO_IDENTITY_CONFLICT")
    expected_q1=idx["C"]
    actual_q1="Q1"+base64.b64encode(hashlib.sha1(control_gz).digest()).decode("ascii")
    print("R17_Q1_PACKAGE="+name+"_EXPECTED="+expected_q1+"_ACTUAL="+actual_q1)
    if actual_q1!=expected_q1:
        fail("SIGNED_INDEX_CONTROL_STREAM_Q1_MISMATCH")
    modified=bytearray(control_gz)
    modified[len(modified)//2]^=1
    if "Q1"+base64.b64encode(hashlib.sha1(modified).digest()).decode("ascii")==expected_q1:
        fail("NEGATIVE_CONTROL_CONTROL_TAMPER_ACCEPTED")
    pkghash=props.get("datahash","")
    if not re.fullmatch("[a-f0-9]{64}",pkghash):
        fail("PKGINFO_DATAHASH_MISSING")
    observed_data_sha=sha(data_gz)
    print("R17_DATA_PACKAGE="+name+"_PKGINFO_DATAHASH="+pkghash+"_RAW_GZIP_SHA256="+observed_data_sha)
    if observed_data_sha!=pkghash:
        fail("PKGINFO_DATA_SHA256_MISMATCH")
    modified_data=bytearray(data_gz)
    modified_data[len(modified_data)//2]^=1
    if sha(modified_data)==pkghash:
        fail("NEGATIVE_CONTROL_DATA_TAMPER_ACCEPTED")
    rsa_validated=False
    signer_name=None
    algo=None
    if standalone_signature_present:
        match=re.fullmatch(r"\.SIGN\.RSA(256)?\.([a-zA-Z0-9_.@+-]+\.rsa\.pub)",signature_name)
        if match is None:fail("UNKNOWN_RSA_SIGNATURE_FORMAT")
        algo="sha256" if match[1]=="256" else "sha1"
        key=keydir/match[2]
        if not key.is_file() or key.is_symlink() or not 100<len(signature)<5000:
            fail("SIGNED_BASE_PUBLIC_KEY_MISSING")
        prefix=re.sub("[^a-zA-Z0-9_-]","_",name)
        compressed=temp/(prefix+".control.gz")
        signature_file=temp/(prefix+".sig")
        compressed.write_bytes(control_gz)
        signature_file.write_bytes(signature)
        result=subprocess.run(["openssl","dgst","-"+algo,"-verify",str(key),
                                "-signature",str(signature_file),str(compressed)],
                                capture_output=True,text=True,check=False,timeout=20)
        if result.returncode!=0 or "Verified OK" not in result.stdout:
            fail("RSA_CONTROL_SIGNATURE_VERIFICATION_FAILED")
        rsa_validated=True
        signer_name=key.name
    return {
        "package":name,"version":version,"archive_bytes":len(raw),
        "archive_full_sha256":sha(raw),
        "apk_v2_gzip_stream_count_minimum":3 if standalone_signature_present else 2,
        "standalone_archive_rsa_signature_present":standalone_signature_present,
        "rsa_signature_cryptographically_verified":rsa_validated,
        "rsa_signature_algorithm":algo,
        "rsa_signer_filename":signer_name,
        "signed_index_q1_sha1_control_checksum_match":True,
        "negative_control_mutated_control_digest_rejected":True,
        "signed_pkginfo_sha256_datahash_match":True,
        "negative_control_mutated_data_digest_rejected":True,
        "compressed_control_stream_sha256":sha(control_gz),
        "compressed_data_stream_sha256":observed_data_sha,
        "compressed_data_was_not_decompressed_or_executed":True,
        "archive_v2_index_q1_uses_legacy_sha1":True,
    }

def main():
    d=check_environment()
    ix=read(d/"APKINDEX.tar.gz",35_000_000)
    if read(d/"signed-index.status",150).decode().strip()!="SIGNED_APKINDEX_ACCEPTED":
        fail("SIGNED_INDEX_NOT_ACCEPTED")
    if read(d/"signed-base.status",150).decode().strip()!="PUBLISHER_IDENTITY_VERIFIED":
        fail("SIGNED_BASE_NOT_ACCEPTED")
    actual=parse_signed_index(ix)
    temp=d/"verify_tmp"
    temp.mkdir(mode=0o700,exist_ok=False)
    keydir=d/"base-keys"
    details=[]
    for key in sorted(PINS):
        name,ver=key
        details.append(validate_pkg(d/"apks"/(name+"-"+ver+".apk"),actual[key],keydir,temp))
    for f in temp.iterdir():
        f.unlink()
    temp.rmdir()
    report={
        "stage":"CERT-A19-R17",
        "result":"FOUR_APK_INDEX_Q1_AND_SIGNED_CONTROL_DATAHASH_CHECK__TRANSITIVE_CLOSURE_UNVERIFIED",
        "signed_index_archive_sha256":sha(ix),
        "signed_index_bytes_retained":True,
        "packages":details,
        "four_archive_index_control_q1_and_datahash_validated":len(details)==4,
        "four_archive_standalone_rsa_signatures_verified":sum(1 for p in details if p["rsa_signature_cryptographically_verified"]),
        "sha1_q1_is_legacy_control_format_not_modern_collision_resistant_identity":True,
        "independent_base_key_custody":False,
        "native_apk_solver_closure_validated":False,
        "trusted_verifier_code_executed":True,
        "worker_or_untrusted_guest_code_executed":False,
        "four_language_semantics_validated":False,
        "original_critical_high_review_open":199,
        "cve_closures":0,
        "runtime_a6_denied":True,
        "production_authorized":False,
    }
    (d/"r17-result.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("R17_ALL_FOUR_ARCHIVE_INDEX_Q1_AND_SIGNED_DATAHASH_PASS__RSA_SIGNATURE_COUNTS_SEPARATE")
    print("R17_SOLVER_CLOSURE_STILL_NOT_CERTIFIED_A6_DENY")


if __name__=="__main__":
    main()
