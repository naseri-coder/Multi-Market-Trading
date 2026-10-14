"""CERT-A19-R18 bounded, offline-index apko resolver and legacy APK member-chain audit.

All checks are non-production and use the *exact R17 signed index bytes*.
Index Q1 is legacy SHA-1 of the compressed control, not independent
modern SHA-256 package-signature security. Never build or run a Worker.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import os
import re
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
import zlib

R17_SHA = "8011fbdaf70278ae83e3729dc2c44a8148a91cf03ea0ef7a3d049e30a65e36a5"
SIGNED_BASE = "cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
APKO_RELEASE = "1.4.11"
APKO_TARBALL_SHA = "5445ea2467a4ab0db3e31d9f795133128d0564c7afdaa46fcdaa1ee3cf92c757"
ORIGIN = "https://apk.cgr.dev/chainguard/x86_64/"
ROOTS = {"glibc-2.44": "2.44-r8", "python-3.12": "3.12.15-r3",
         "python-3.12-base": "3.12.15-r3", "nodejs-24": "24.22.0-r0"}
NAME = re.compile(r"^[A-Za-z0-9+~._-]+$")
VERSION = re.compile(r"^[A-Za-z0-9+~._:-]+$")
MAX_COUNT = 175
MAX_SINGLE = 105_000_000
MAX_TOTAL = 450_000_000

def abort(reason):
    raise ValueError("CERT_A19_R18_" + reason)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def work():
    env = {"GITHUB_ACTIONS": "true", "MMT_NONPRODUCTION": "1",
           "GITHUB_REF": "refs/heads/cert-a19-byte-audit-run"}
    if any(os.environ.get(k) != v for k, v in env.items()):
        abort("FIXED_NONPRODUCTION_BRANCH_REQUIRED")
    d = Path(os.environ["RUNNER_TEMP"]) / "cert-a19-r18"
    if not d.is_dir() or d.is_symlink():
        abort("EVIDENCE_ROOT_MISSING")
    return d

def read(p, limit):
    if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= limit:
        abort("ABSENT_OR_OVERSIZED_FILE")
    return p.read_bytes()

def index_entries(d):
    b = read(d / "APKINDEX.tar.gz", 35_000_000)
    if sha(b) != R17_SHA:
        abort("R17_INDEX_SHA_MISMATCH")
    if (d / "index-verified.status").read_text().strip() != "SIGNED_R17_INDEX_NATIVE_ACCEPTED":
        abort("R17_INDEX_SIGNATURE_EVIDENCE_MISSING")
    with tarfile.open(fileobj=io.BytesIO(b), mode="r:gz") as t:
        members = [m for m in t.getmembers() if m.name == "APKINDEX" and m.isfile()]
        if len(members) != 1 or members[0].size > 65_000_000:
            abort("INDEX_FORMAT_INVALID")
        file = t.extractfile(members[0])
        if file is None:
            abort("INDEX_PAYLOAD_MISSING")
        data = file.read(65_000_001)
    if len(data) > 65_000_000:
        abort("INDEX_INFLATION_UNBOUNDED")
    entries = {}
    for paragraph in data.decode().split("\n\n"):
        fields = {}
        for ln in paragraph.splitlines():
            if len(ln) > 2 and ln[1] == ":":
                if ln[0] in fields:
                    abort("INDEX_DUPLICATE_FIELD")
                fields[ln[0]] = ln[2:]
        if all(k in fields for k in ("P", "V", "S", "C")):
            key = (fields["P"], fields["V"])
            if key in entries:
                abort("INDEX_DUPLICATE_NAME_VERSION")
            entries[key] = fields
    if len(entries) < 120000:
        abort("INDEX_ENTRY_COUNT_UNEXPECTED")
    for k, v in ROOTS.items():
        if (k, v) not in entries:
            abort("ROOT_NOT_IN_AUTHENTICATED_INDEX")
    return entries

def phase_resolve():
    d = work()
    if (d / "base.txt").read_text().strip() != SIGNED_BASE:
        abort("BASE_IDENTITY_MISMATCH")
    if (d / "apko-verified.status").read_text().strip() != "APKO_RELEASE_SIGSTORE_VERIFIED":
        abort("APKO_BINARY_PROVENANCE_UNVERIFIED")
    entries = index_entries(d)
    raw = read(d / "show-packages.txt", 75_000).decode().splitlines()
    if not 4 <= len(raw) <= MAX_COUNT:
        abort("SOLVER_RESULT_NOT_BOUNDED")
    matched = []
    seen = set()
    for line in raw:
        if line.count("=") != 1:
            abort("SOLVER_NON_PACKAGE_OUTPUT")
        pkg, ver = line.split("=", 1)
        if not NAME.fullmatch(pkg) or not VERSION.fullmatch(ver) or (pkg, ver) in seen:
            abort("SOLVER_DUPLICATE_OR_INVALID_RECORD")
        seen.add((pkg, ver))
        entry = entries.get((pkg, ver))
        if not entry:
            abort("SOLVER_PACKAGE_ABSENT_FROM_SIGNED_INDEX")
        size = int(entry["S"])
        if not 100 < size < MAX_SINGLE:
            abort("INDEX_PACKAGE_ARCHIVE_SIZE_INVALID")
        matched.append({
            "name": pkg, "version": ver, "filename": pkg + "-" + ver + ".apk",
            "signed_index_control_checksum": entry["C"],
            "signed_index_archive_size": size,
            "direct_dependencies": entry.get("D", "").split(),
            "url": ORIGIN + pkg + "-" + ver + ".apk",
        })
    if not all((pkg, version) in seen for pkg, version in ROOTS.items()):
        abort("NATIVE_SOLVER_DID_NOT_SELECT_EXACT_ROOTS")
    if sum(x["signed_index_archive_size"] for x in matched) > MAX_TOTAL:
        abort("SOLVER_ARCHIVE_SUM_OVERSIZED")
    matched.sort(key=lambda x: (x["name"], x["version"]))
    state = {
        "stage": "CERT-A19-R18",
        "phase": "APKO_SOURCE_VERIFIED_OFFLINE_R17_INDEX_CLOSURE_SOLVED_PENDING_APK_BYTES",
        "base_oci": SIGNED_BASE,
        "apko_release": "v" + APKO_RELEASE,
        "apko_release_tgz_sha256": APKO_TARBALL_SHA,
        "apko_signature_verification": "PASS_EXPECTED_PUBLISHER_IDENTITY",
        "raw_r17_signed_index_sha256": R17_SHA,
        "r17_signed_index_bytes_available": True,
        "resolved_package_count": len(matched),
        "requested_direct_roots": ROOTS,
        "resolved_packages": matched,
        "resolver_output_from_offline_signed_index": True,
        "all_selected_archives_verified": False,
        "no_apk_install_or_runtime_build": True,
        "worker_or_guest_code_executed": False,
        "original_199_findings_review_open": True,
        "a6_hard_deny": True,
        "production_authorized": False
    }
    (d / "r18-resolver.json").write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
    print("CERT_A19_R18_OFFLINE_APKO_PACKAGE_SELECTION_COUNT=" + str(len(matched)))

def split_gzip(data, offset, max_unpacked):
    if data[offset:offset+2] != b"\x1f\x8b":
        abort("APK_STREAM_NOT_GZIP")
    decomp = zlib.decompressobj(16+zlib.MAX_WBITS)
    output = decomp.decompress(data[offset:], max_unpacked+1)
    if not decomp.eof or len(output) > max_unpacked:
        abort("APK_GZIP_MEMBER_INFLATION_LIMIT_OR_TRUNCATION")
    consumed = len(data[offset:]) - len(decomp.unused_data)
    if consumed < 18:
        abort("APK_GZIP_MEMBER_TOO_SMALL")
    return data[offset:offset+consumed], output, offset+consumed

def control_members(raw):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        out = {}
        for m in archive:
            if not m.isfile():
                continue
            if len(out) >= 24 or m.size > 10_000_000 or m.name in out:
                abort("APK_CONTROL_MEMBER_INVALID")
            f = archive.extractfile(m)
            if f is None:
                abort("APK_CONTROL_MEMBER_MISSING")
            out[m.name] = f.read(10_000_001)
    return out

def unpack_control(blob):
    first, decoded, pos = split_gzip(blob, 0, 18_000_000)
    files = control_members(decoded)
    if any(x.startswith(".SIGN.") for x in files):
        # Encountering standalone signatures is not a license to skip verification.
        abort("STANDALONE_SIGNED_PACKAGE_UNSUPPORTED_WITHOUT_CRYPTO_CHECK")
    if ".PKGINFO" not in files:
        abort("CONTROL_PKGINFO_MISSING")
    return first, files[".PKGINFO"], pos

def member_proof(blob, entry):
    if len(blob) != entry["signed_index_archive_size"]:
        abort("APK_SIZE_MISMATCH_SIGNED_INDEX")
    control, pkgi, end = unpack_control(blob)
    expected = entry["signed_index_control_checksum"]
    q1 = "Q1" + base64.b64encode(hashlib.sha1(control).digest()).decode()
    if q1 != expected:
        abort("APK_SHA1_Q1_CONTROL_NOT_IN_SIGNED_INDEX")
    props = {}
    for line in pkgi.decode("utf-8", "strict").splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            props[key.strip()] = value.strip()
    if props.get("pkgname") != entry["name"] or props.get("pkgver") != entry["version"]:
        abort("APK_PKGINFO_IDENTITY_MISMATCH")
    if end >= len(blob) or blob[end:end+2] != b"\x1f\x8b":
        abort("APK_DATA_STREAM_MISSING")
    actual_data = sha(blob[end:])
    declared_data = props.get("datahash", "")
    if not re.fullmatch(r"[0-9a-f]{64}", declared_data) or actual_data != declared_data:
        abort("APK_SHA256_DATAHASH_MISMATCH")
    tampered = bytearray(control)
    tampered[len(tampered)//2] ^= 1
    if "Q1"+base64.b64encode(hashlib.sha1(tampered).digest()).decode() == expected:
        abort("APK_CONTROL_NEGATIVE_MUTATION_INCORRECTLY_ACCEPTED")
    data_neg = bytearray(blob[end:])
    data_neg[len(data_neg)//2] ^= 1
    if sha(data_neg) == declared_data:
        abort("APK_DATA_NEGATIVE_MUTATION_INCORRECTLY_ACCEPTED")
    return {"whole_apk_sha256": sha(blob), "whole_apk_bytes": len(blob),
            "control_compressed_sha256": sha(control),
            "data_compressed_sha256": actual_data,
            "signed_index_Q1_control_sha1_matches": True,
            "signed_pkginfo_data_sha256_matches": True,
            "two_negative_controls_rejected": True,
            "legacy_Q1_sha1_collision_resistance_limit": True,
            "standalone_apk_rsa_signature_present": False}

def safe_origin(url):
    u = urlsplit(url)
    h = (u.hostname or "").lower()
    if (u.scheme != "https" or u.username or u.password
            or u.port not in (None, 443) or
            (h != "apk.cgr.dev" and not h.endswith(".r2.cloudflarestorage.com"))):
        abort("UNEXPECTED_PACKAGE_DISTRIBUTION_HOST")
    return h

class RedirectPolicy(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        safe_origin(url)
        return super().redirect_request(req, fp, code, msg, headers, url)

OPENER = urllib.request.build_opener(RedirectPolicy())

def phase_verify():
    d = work()
    entries = index_entries(d)
    state = json.loads(read(d/"r18-resolver.json", 120_000))
    if state.get("phase") != "APKO_SOURCE_VERIFIED_OFFLINE_R17_INDEX_CLOSURE_SOLVED_PENDING_APK_BYTES":
        abort("PREVIOUS_RESOLVER_STAGE_NOT_PASSED")
    packages = state["resolved_packages"]
    if not 4 <= len(packages) <= MAX_COUNT:
        abort("SUSPICIOUS_LOCK_PACKAGE_COUNT")
    total = 0
    proof = []
    for i, entry in enumerate(packages, 1):
        pkg,ver = entry["name"],entry["version"]
        item = entries.get((pkg,ver))
        if not item or item["C"] != entry["signed_index_control_checksum"]:
            abort("SIGNED_INDEX_ENTRY_CHANGED")
        safe_origin(entry["url"])
        rq = urllib.request.Request(entry["url"],headers={"User-Agent":"MMT-A19-R18-custody-only"})
        with OPENER.open(rq, timeout=40) as response:
            host = safe_origin(response.url)
            archive = response.read(MAX_SINGLE+1)
        if len(archive) > MAX_SINGLE:
            abort("APK_SINGLE_DOWNLOAD_OVERSIZED")
        total += len(archive)
        if total > MAX_TOTAL:
            abort("APK_CUMULATIVE_DOWNLOAD_OVERSIZED")
        check = member_proof(archive,entry)
        check.update({"package":pkg, "version":ver,"signed_index_size":int(item["S"]),
                      "cdn_hostname":host})
        proof.append(check)
        print("R18_CHECKED_SIGNED_INDEX_APK="+pkg+"="+ver)
    state["phase"] = "SOLVER_SELECTED_TRANSITIVE_CLOSURE_ALL_APK_LEGACY_SIGNED_INDEX_CHAINS_VERIFIED"
    state["all_selected_archives_verified"] = True
    state["archive_verification"] = proof
    state["total_archive_bytes_verified"] = total
    state["full_modern_apk_signature_certification"] = False
    state["solver_and_signed_index_compatibility"] = "PASS"
    state["native_ABI_and_four_language_equivalence_tested"] = False
    state["rootless_gvisor_host_independently_certified"] = False
    state["cves_certified_closed"] = 0
    (d/"r18-result.json").write_text(json.dumps(state, indent=2, sort_keys=True)+"\n")
    print("CERT_A19_R18_VERIFIED_RESOLVED_ARCHIVE_COUNT="+str(len(proof)))
    print("CERT_A19_R18_FULL_WORKER_RUNTIME_SECURITY_NOT_CERTIFIED_199_OPEN_A6_DENY")

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=("resolve","verify"))
    method=p.parse_args().phase
    {"resolve":phase_resolve,"verify":phase_verify}[method]()
