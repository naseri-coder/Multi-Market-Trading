"""CERT-A19-R8: verify pinned Debian signed source, never execute Worker code."""
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

VER = "5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4"
DSC_SHA = "6befcb981dea58f2fdb9bc0d78624d829090105ab955d48e617a02ead37fd44c"
R7_FILE_SHA = "06e20567449a6131d5ae6f049b5d85f17c3139f2fed6a2783f656429180ff865"
PRE = "node-undici_5.15.0+dfsg1+~cs20.10.9.3"
FILES = {
    PRE + ".orig-binary-search.tar.xz", PRE + ".orig-llhttp.tar.xz",
    PRE + ".orig-llparse-builder.tar.xz", PRE + ".orig-llparse-frontend.tar.xz",
    PRE + ".orig-llparse.tar.xz", PRE + ".orig.tar.xz",
    "node-undici_" + VER + ".debian.tar.xz",
}
BASE = "https://deb.debian.org/debian/pool/main/n/node-undici/"


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def download(name, limit):
    if name != "node-undici_" + VER + ".dsc" and name not in FILES:
        raise ValueError("A19_UNEXPECTED_ARCHIVE_NAME")
    request = urllib.request.Request(BASE + name, headers={"User-Agent": "MMT-A19-custody-only"})
    with urllib.request.urlopen(request, timeout=35) as response:
        if not response.url.startswith(BASE):
            raise ValueError("A19_UNEXPECTED_REDIRECT")
        data = response.read(limit + 1)
    if not 0 < len(data) <= limit:
        raise ValueError("A19_INVALID_ARCHIVE_SIZE")
    return data


def signed_files(raw):
    s = raw.decode("utf-8")
    if (s.count("\nChecksums-Sha256:\n") != 1
            or "Source: node-undici\n" not in s or "Version: " + VER + "\n" not in s):
        raise ValueError("A19_DSC_IDENTITY_MISMATCH")
    chunk = s.split("\nChecksums-Sha256:\n", 1)[1]
    found = []
    for line in chunk.splitlines():
        if not line or not line[0].isspace():
            break
        match = re.fullmatch(r"\s+([0-9a-f]{64})\s+([0-9]{1,9})\s+([A-Za-z0-9+~._-]+)\s*", line)
        if not match:
            raise ValueError("A19_UNTRUSTED_DSC_RECORD")
        found.append((match[3], int(match[2]), match[1]))
    if len(found) != 7 or {r[0] for r in found} != FILES:
        raise ValueError("A19_DSC_COMPONENT_SET_DRIFT")
    if any(not 0 < r[1] <= 7_500_000 for r in found):
        raise ValueError("A19_UNBOUNDED_DSC_COMPONENT")
    return found


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("GITHUB_REF") != "refs/heads/cert-a19-byte-audit-run"):
        raise ValueError("A19_NONPRODUCTION_FIXED_BRANCH_REQUIRED")
    work = Path(os.environ["RUNNER_TEMP"]) / "cert-a19-source"
    work.mkdir(mode=0o700)
    name = "node-undici_" + VER + ".dsc"
    dsc = download(name, 16000)
    if sha(dsc) != DSC_SHA:
        raise ValueError("A19_DSC_SHA_MISMATCH")
    (work / name).write_bytes(dsc)
    keys = ["/usr/share/keyrings/debian-keyring.gpg",
            "/usr/share/keyrings/debian-maintainers.gpg"]
    if any(not Path(p).is_file() for p in keys):
        raise ValueError("A19_SIGNER_KEYRING_ABSENT")
    args = ["gpgv", "--status-fd", "1"]
    for key in keys:
        args.extend(["--keyring", key])
    checked = subprocess.run([*args, str(work / name)],
                             capture_output=True, text=True, timeout=20, check=False)
    fingerprints = re.findall(r"\[GNUPG:\] VALIDSIG ([0-9A-Fa-f]{40,64})\b", checked.stdout)
    if checked.returncode != 0 or len(fingerprints) != 1:
        raise ValueError("A19_DSC_DEVELOPER_SIGNATURE_NOT_TRUSTED")
    rows = signed_files(dsc)
    components = []
    for filename, size, expected in sorted(rows):
        data = download(filename, size)
        if len(data) != size or sha(data) != expected:
            raise ValueError("A19_DSC_COMPONENT_HASH_MISMATCH")
        (work / filename).write_bytes(data)
        components.append({"name": filename, "size": size, "sha256": expected})
    patched = work / "patched-source"
    result = subprocess.run(["dpkg-source", "-x", str(work / name), str(patched)],
                            capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        raise ValueError("A19_DPKG_SOURCE_PATCH_APPLICATION_FAILED")
    p = patched / "lib/balanced-pool.js"
    if not p.is_file() or p.is_symlink():
        raise ValueError("A19_SIGNED_SOURCE_BALANCED_POOL_MISSING")
    code = p.read_bytes()
    if b"Object.assign({}, this[kOptions])" not in code or b"JSON.parse(JSON.stringify" in code:
        raise ValueError("A19_SOURCE_BALANCED_POOL_MECHANISM_UNEXPECTED")
    if (patched / "lib/interceptor/cache.js").exists():
        raise ValueError("A19_SOURCE_CACHE_INTERCEPTOR_FOUND")
    source_hash = sha(code)
    report = {
        "stage": "CERT-A19-R8",
        "debian_dsc_sha256": DSC_SHA,
        "debian_developer_signature_verified_using_host_keyring": True,
        "signer_fingerprint": fingerprints[0].lower(),
        "source_components_verified": components,
        "patched_source_balanced_pool_sha256": source_hash,
        "r7_debian_binary_balanced_pool_sha256": R7_FILE_SHA,
        "source_and_r7_binary_balanced_pool_equal": source_hash == R7_FILE_SHA,
        "debian_signer_keyring_independent_custody": False,
        "a18_worker_balanced_pool_sha256": None,
        "a18_worker_parity": "UNVERIFIED_IMAGE_NOT_EXPORTED",
        "fixed_or_false_positive_cves_certified": 0,
        "original_critical_high_findings_review_open": 199,
        "production_authorized": False
    }
    (Path(os.environ["RUNNER_TEMP"]) / "cert-a19-source-chain.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("CERT_A19_DSC_SIGNED_AND_ALL_7_SOURCE_ARCHIVES_HASHED")
    print("CERT_A19_PATCHED_SOURCE_SHA=" + source_hash)
    print("CERT_A19_SOURCE_R7_BINARY_EQUAL=" + str(report["source_and_r7_binary_balanced_pool_equal"]))
    print("CERT_A19_A18_WORKER_UNVERIFIED_NO_CVE_CLOSED")


if __name__ == "__main__":
    main()
