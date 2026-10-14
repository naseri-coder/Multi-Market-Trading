"""CERT-A19-R15: immutable Wolfi index native solver and per-APK signatures.

DO NOT install .apk, construct Worker, run untrusted source, alter A6 or declare CVEs closed.
Native apk fetch --recursive --simulate --url provides actual solver's selected URL list;
each archive is downloaded bounded, then signature-verified by the trusted base apk.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

IMAGE = ("cgr.dev/chainguard/wolfi-base@sha256:"
         "256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43")
INDEX_SHA = "15f8b555714bfe44b0f4de0ee24910e0533f7b4fbb4a650cf533115c6a4f281a"
BASE_URL = "https://apk.cgr.dev/chainguard/x86_64/"
ROOTS = {
    "glibc-2.44": "2.44-r8",
    "python-3.12": "3.12.15-r3",
    "python-3.12-base": "3.12.15-r3",
    "nodejs-24": "24.22.0-r0",
}
MAX_PACKAGE_COUNT = 180
MAX_TOTAL_BYTES = 650_000_000
MAX_SINGLE_BYTES = 135_000_000
URL_RE = re.compile(r"^(?:file:///mnt/apkrepo|https://apk\.cgr\.dev/chainguard)/x86_64/([A-Za-z0-9_+~.-]+)\.apk$")


def require_public_https(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or not host or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)
            or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test"))
            or host.replace(".", "").isdigit() or ":" in host):
        fail("UNSAFE_PACKAGE_REDIRECT_URL")
    return host


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


DOWNLOAD_OPENER = build_opener(SafeRedirect())


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def fail(code):
    raise ValueError("CERT_A19_R15_" + code)


def path(name):
    return Path(os.environ["RUNNER_TEMP"]) / "cert-a19-r15" / name


def index_entries():
    raw = path("APKINDEX.tar.gz").read_bytes()
    if not 1_000_000 < len(raw) < 30_000_000 or sha(raw) != INDEX_SHA:
        fail("R14_SIGNED_INDEX_BYTES_CHANGED")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        members = [m for m in archive if m.name == "APKINDEX" and m.isfile()]
        if len(members) != 1:
            fail("INDEX_FORMAT_INVALID")
        f = archive.extractfile(members[0])
        if f is None:
            fail("INDEX_DATA_MISSING")
        content = f.read(60_000_001)
    if len(content) > 60_000_000:
        fail("INDEX_UNBOUNDED")
    entries = {}
    for para in content.decode("utf-8").strip().split("\n\n"):
        data = {}
        for line in para.splitlines():
            if len(line) > 2 and line[1] == ":":
                if line[0] in data:
                    fail("INDEX_DUPLICATE_FIELD")
                data[line[0]] = line[2:]
        if all(k in data for k in ("P", "V", "C")):
            key = (data["P"], data["V"])
            if key in entries:
                fail("INDEX_DUPLICATE_PACKAGE_VERSION")
            entries[key] = data
    if len(entries) < 1000:
        fail("INDEX_EMPTY")
    for pkg, ver in ROOTS.items():
        if (pkg, ver) not in entries:
            fail("ROOT_VERSION_ABSENT_FROM_R14_SNAPSHOT")
    return entries


def scope():
    for k, v in {
        "GITHUB_ACTIONS": "true",
        "MMT_NONPRODUCTION": "1",
        "GITHUB_REF": "refs/heads/cert-a19-byte-audit-run",
    }.items():
        if os.environ.get(k) != v:
            fail("SCOPE_RESTRICTED")
    if path("image.txt").read_text().strip() != IMAGE:
        fail("BASE_IDENTITY_CHANGED")
    if path("sigstore.status").read_text().strip() != "FIXED_CHAINGUARD_PUBLISHER_SIGNED":
        fail("SIGNED_BASE_MISSING")
    if path("index.status").read_text().strip() != "SIGNED_INDEX_VALIDATED_BY_NATIVE_APK":
        fail("SIGNED_INDEX_MISSING")


def parse_solver(entries):
    raw = path("solver.urls").read_text()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) > MAX_PACKAGE_COUNT * 2:
        fail("SOLVER_OUTPUT_TOO_BIG")
    urls = []
    for line in lines:
        m = URL_RE.fullmatch(line)
        if not m:
            fail("SOLVER_UNEXPECTED_LINE_OR_URL")
        if line in urls:
            fail("DUPLICATE_SOLVER_ARCHIVE")
        urls.append(line)
    if not 3 <= len(urls) <= MAX_PACKAGE_COUNT:
        fail("SOLVER_CLOSURE_UNBOUNDED")
    result = []
    for url in urls:
        filename = url.rsplit("/", 1)[1]
        match = [((n, v), d) for (n, v), d in entries.items()
                 if filename == n + "-" + v + ".apk"]
        if len(match) != 1:
            fail("SOLVER_ARCHIVE_NOT_UNIQUELY_IDENTIFIED_BY_SIGNED_INDEX")
        ((name, ver), data), = match
        try:
            compressed = int(data.get("S", "0"))
        except ValueError:
            fail("SIGNED_PACKAGE_SIZE_INVALID")
        if not 100 < compressed < MAX_SINGLE_BYTES:
            fail("SIGNED_PACKAGE_UNBOUNDED")
        result.append({
            "filename": filename,
            "name": name,
            "version": ver,
            "url": BASE_URL + filename,
            "index_control_checksum": data["C"],
            "signed_index_size": compressed,
            "index_dependencies": data.get("D", "").split(),
        })
    picked = {(x["name"], x["version"]) for x in result}
    if any((n, v) not in picked for n, v in ROOTS.items()):
        fail("SOLVER_DID_NOT_SELECT_EXACT_ROOT_VERSIONS")
    if sum(x["signed_index_size"] for x in result) > MAX_TOTAL_BYTES:
        fail("SOLVER_SELECTED_BYTES_TOO_LARGE")
    return result


def resolver():
    """Record only the four exact pinned R14 direct packages; NOT transitive closure."""
    scope()
    entries = index_entries()
    selected = []
    for name, version in sorted(ROOTS.items()):
        data = entries[(name, version)]
        size = int(data.get("S", "0"))
        if not 100 < size <= MAX_SINGLE_BYTES:
            fail("DIRECT_PACKAGE_ARCHIVE_SIZE_INVALID")
        filename = name + "-" + version + ".apk"
        selected.append({
            "name": name, "version": version, "filename": filename,
            "url": BASE_URL + filename,
            "index_control_checksum": data["C"],
            "signed_index_size": size,
            "index_dependencies": data.get("D", "").split(),
        })
    report = {
        "stage": "CERT-A19-R15",
        "phase": "FOUR_DIRECT_ROOT_PACKAGE_ARCHIVE_PROOF_PENDING",
        "base": IMAGE,
        "signed_index_sha256": INDEX_SHA,
        "exact_direct_packages": ROOTS,
        "native_recursive_solver_completed": False,
        "native_solver_blocker": "ISOLATED_APK_FETCH_RESOLUTION_FAILED_UNRESOLVED",
        "selected_direct_package_count": len(selected),
        "solver_selected_packages": selected,
        "complete_transitive_dependency_closure": False,
        "apk_archives_verified": 0,
        "full_archive_sha256_lock": False,
        "worker_executed": False,
        "original_199_review_open": True,
        "runtime_a6_denied": True,
        "production_authorized": False,
    }
    path("selection.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    path("package_urls.txt").write_text("\n".join(x["url"] for x in selected)+"\n")
    print("R15_EXACT_DIRECT_INDEX_PACKAGE_COUNT=" + str(len(selected)))

def download():
    report = json.loads(path("selection.json").read_text())
    packages = report["solver_selected_packages"]
    folder = path("archives")
    folder.mkdir(mode=0o700, exist_ok=False)
    total = 0
    for i, x in enumerate(packages):
        if not URL_RE.fullmatch(x["url"]) or x["url"].rsplit("/", 1)[-1] != x["filename"]:
            fail("URL_CHANGED")
        req = Request(x["url"], headers={"User-Agent": "MMT-CERT-A19-R15-audit-only"})
        with DOWNLOAD_OPENER.open(req, timeout=38) as response:
            verified_public_host = require_public_https(response.url)
            bytes_ = response.read(MAX_SINGLE_BYTES + 1)
        if not 100 < len(bytes_) <= MAX_SINGLE_BYTES:
            fail("ARCHIVE_BYTES_OUTSIDE_BOUNDS")
        # Index 'S' describes APK compressed-size metadata, never treat as a hash.
        total += len(bytes_)
        if total > MAX_TOTAL_BYTES:
            fail("TOTAL_ARCHIVE_BUDGET_EXCEEDED")
        (folder / x["filename"]).write_bytes(bytes_)
        x["observed_apk_sha256"] = sha(bytes_)
        x["observed_apk_bytes"] = len(bytes_)
        x["final_https_distribution_host"] = verified_public_host
        print("R15_FETCHED_PACKAGE=" + x["filename"])
    report["phase"] = "FOUR_DIRECT_ARCHIVES_FETCHED_PENDING_NATIVE_SIGNATURE_VERIFICATION"
    report["total_downloaded_bytes"] = total
    path("selection.json").write_text(json.dumps(report, sort_keys=True, indent=2)+"\n")


def complete():
    scope()
    report = json.loads(path("selection.json").read_text())
    if report.get("phase") != "ARCHIVES_FETCHED_UNTRUSTED_PENDING_NATIVE_SIGNATURE_VERIFICATION":
        fail("NO_ARCHIVE_BYTES")
    if path("verified.status").read_text().strip() != "ALL_APK_ARCHIVE_SIGNATURES_VERIFIED_BY_NATIVE_APK":
        fail("ARCHIVE_NATIVE_SIGNATURE_PROOF_ABSENT")
    log = path("verify.log").read_text()
    if ("BAD signature" in log or "UNTRUSTED" in log or "ERROR" in log):
        fail("ARCHIVE_VERIFIER_ERROR")
    for item in report["solver_selected_packages"]:
        p = path("archives") / item["filename"]
        if not p.is_file() or p.is_symlink() or sha(p.read_bytes()) != item["observed_apk_sha256"]:
            fail("ARCHIVE_SHA_DRIFT_AFTER_NATIVE_VERIFIER")
    report["phase"] = "FOUR_DIRECT_ROOT_APK_SIGNATURES_AND_SHA256_CAPTURED__CLOSURE_NOT_RESOLVED"
    report["apk_archives_verified"] = len(report["solver_selected_packages"])
    report["full_archive_sha256_lock"] = False
    report["direct_root_apk_archive_full_sha256_verified"] = True
    report["complete_transitive_dependency_closure"] = False
    report["signature_key_independent_custody_certified"] = False
    report["apk_files_executed_or_installed"] = False
    report["native_apk_verifier_executed_on_fixed_signed_image"] = True
    report["native_python_node_glibc_abi_tested"] = False
    report["typescript_wasmtime_installed"] = False
    report["four_language_parity_tested"] = False
    report["independent_host_certification"] = False
    report["cves_closed"] = 0
    report["original_199_review_open"] = True
    report["production_authorized"] = False
    path("r15-custody.json").write_text(json.dumps(report, sort_keys=True, indent=2)+"\n")
    print("CERT_A19_R15_VERIFIED_DIRECT_ROOT_APK_ARCHIVES=" + str(report["apk_archives_verified"]))
    print("CERT_A19_R15_ABI_NOT_RUN_A6_DENY_199_OPEN")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("resolve", "download", "complete"))
    args = p.parse_args()
    {"resolve": resolver, "download": download, "complete": complete}[args.phase]()
