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
    pkey=(idx["P"],idx["V"])
    if sha(raw)!=PINS[pkey] or len(raw)!=int(idx["S"]):
        fail("ARCHIVE_FULL_SHA256_OR_INDEX_SIZE_MISMATCH")

    # APKv2 has 3 concatenated gzip members: signature, control, data.
    print("R17_PARSING_APK="+idx["P"]+"_bytes="+str(len(raw)))
    sign_gz,sign_blob,pos=split_stream(raw,0,10_000_000)
    print("R17_FIRST_STREAM="+str(len(sign_gz))+"_inflated="+str(len(sign_blob)))
    control_gz,control_blob,pos2=split_stream(raw,pos,15_000_000)
    print("R17_SECOND_STREAM="+str(len(control_gz))+"_inflated="+str(len(control_blob)))
    if pos2>=len(raw) or not raw[pos2:].startswith(MAGIC):
        fail("DATA_STREAM_NOT_FOUND")
    data_gz=raw[pos2:]
    files=safe_tar(sign_blob,10_000_000)
    if len(files)!=1:fail("SIGNATURE_MEMBER_COUNT")
    sig_filename,signature=next(iter(files.items()))
    m=re.fullmatch(r"\.SIGN\.RSA(256)?\.([a-zA-Z0-9_.@+-]+\.rsa\.pub)",sig_filename)
    if m is None:fail("UNRECOGNIZED_SIGNATURE_FORMAT")
    algo="sha256" if m[1]=="256" else "sha1"
    key=keydir/m[2]
    if key.is_symlink() or not key.is_file() or len(signature)<100:
        fail("SIGNER_KEY_NOT_IN_SIGNED_BASE")
    metadata=safe_tar(control_blob,15_000_000)
    if ".PKGINFO" not in metadata:fail("PKGINFO_ABSENT")
    props=find_pkinfo(metadata[".PKGINFO"])
    if props.get("pkgname")!=idx["P"] or props.get("pkgver")!=idx["V"]:
        fail("PKGINFO_PACKAGE_IDENTITY_CONFLICT")

    claimed_q1=idx["C"]
    measured_q1="Q1"+base64.b64encode(hashlib.sha1(control_gz).digest()).decode("ascii")
    if measured_q1!=claimed_q1:fail("SIGNED_INDEX_CONTROL_Q1_MISMATCH")
    if (hashlib.sha1(control_gz+b"\x00").digest()
         ==hashlib.sha1(control_gz).digest()):
        fail("NEGATIVE_CONTROL_SHA1_UNEXPECTED")
    altered=bytearray(control_gz)
    altered[len(altered)//2]^=1
    negative_q1="Q1"+base64.b64encode(hashlib.sha1(altered).digest()).decode()
    if negative_q1==claimed_q1:fail("NEGATIVE_CONTROL_TAMPER_ACCEPTED")

    # Verify signature on COMPRESSED control bytes with public key
    # extracted from the exact Sigstore-authenticated Wolfi base.
    filebase=re.sub("[^a-zA-Z0-9_-]","_",idx["P"])
    ctr=temp/(filebase+".control.gz")
    sig=temp/(filebase+".signature")
    ctr.write_bytes(control_gz)
    sig.write_bytes(signature)
    proc=subprocess.run(["openssl","dgst","-"+algo,
                         "-verify",str(key),
                         "-signature",str(sig),str(ctr)],
                        capture_output=True,text=True,timeout=20,check=False)
    if proc.returncode!=0 or "Verified OK" not in proc.stdout:
        fail("OPENSSL_PACKAGE_SIGNATURE_NOT_VERIFIED")

    dh=props.get("datahash")
    compressed_data_sha=sha(data_gz)
    if not dh or not re.fullmatch("[0-9a-f]{64}",dh):
        fail("SIGNED_PKGINFO_DATAHASH_MISSING")
    if compressed_data_sha != dh:
        fail("SIGNED_PKGINFO_DATA_STREAM_SHA256_MISMATCH")

    return {
        "package":idx["P"],
        "version":idx["V"],
        "apk_size":len(raw),
        "apk_full_sha256":sha(raw),
        "index_control_checksum":claimed_q1,
        "computed_apk_control_q1_matches_signed_index":True,
        "negative_control_modified_control_q1_rejected":True,
        "signature_entry":sig_filename,
        "signature_algorithm":algo,
        "signer_public_key_filename":key.name,
        "openssl_control_signature_verified":True,
        "raw_signature_member_sha256":sha(sign_gz),
        "raw_compressed_control_sha256":sha(control_gz),
        "raw_compressed_data_sha256":compressed_data_sha,
        "pkginfo_signed_datahash_matches_compressed_data":True,
        "data_member_executed_or_extracted":False,
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
        "result":"FOUR_APK_V2_SIGNED_CONTROL_AND_DATAHASH_PASS__TRANSITIVE_CLOSURE_UNVERIFIED",
        "signed_index_archive_sha256":sha(ix),
        "signed_index_bytes_retained":True,
        "packages":details,
        "four_archive_crypto_validated":len(details)==4,
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
    print("R17_ALL_FOUR_ARCHIVE_Q1_AND_OPENSSL_SIGNATURE_AND_DATAHASH_PASS")
    print("R17_SOLVER_CLOSURE_STILL_NOT_CERTIFIED_A6_DENY")


if __name__=="__main__":
    main()
