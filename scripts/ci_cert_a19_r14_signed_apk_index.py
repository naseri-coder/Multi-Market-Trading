"""CERT-A19-R14: inspect ONLY independently signed Wolfi x86_64 APK index.

This verifier relies on an ephemeral apk-tools signature validation step against
the specific index downloaded from the exact repository declared by the already
Sigstore-verified, digest-pinned Wolfi base. It does not install any APK package
or execute any container, Worker or arbitrary source code.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
from pathlib import Path

BASE_DIGEST = "sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43"
OCI_BASE = "cgr.dev/chainguard/wolfi-base@" + BASE_DIGEST
REPOS = {
    "https://apk.cgr.dev/chainguard",
    "https://packages.wolfi.dev/os",
}
INTEREST = {
    "glibc", "glibc-2.43", "glibc-2.44",
    "python-3.12", "python-3.12-base",
    "nodejs-24", "nodejs-24-libs",
}
TARGETS = ["python-3.12", "nodejs-24"]


def fail(code: str) -> None:
    raise ValueError("CERT_A19_R14_" + code)


def load_safe(path: Path, limit: int = 30_000_000) -> bytes:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= limit:
        fail("EVIDENCE_FILE_NOT_REGULAR_OR_SIZE_INVALID")
    raw = path.read_bytes()
    if not raw or len(raw) > limit:
        fail("UNBOUNDED_OR_MISSING_EVIDENCE")
    return raw


def exact_repository(work: Path) -> str:
    raw = load_safe(work / "base-repositories", 4096).decode("utf-8")
    entries = [line.strip().rstrip("/") for line in raw.splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    if len(entries) != 1 or entries[0] not in REPOS:
        fail("SIGNED_BASE_REPOSITORY_NOT_FIXED_OR_PUBLIC")
    return entries[0]


def parse_index(index_bytes: bytes) -> list[dict[str, str]]:
    if len(index_bytes) > 30_000_000 or len(index_bytes) < 5000:
        fail("SIGNED_INDEX_INVALID_SIZE")
    try:
        with tarfile.open(fileobj=io.BytesIO(index_bytes), mode="r:gz") as tar:
            members = tar.getmembers()
            names = [x.name for x in members]
            matches = [x for x in members if x.name == "APKINDEX"]
            if len(matches) != 1 or len(members) > 10 or matches[0].size > 45_000_000:
                fail("SIGNED_INDEX_FORMAT_UNEXPECTED")
            file = tar.extractfile(matches[0])
            if file is None:
                fail("SIGNED_INDEX_DATA_MISSING")
            text = file.read(45_000_001).decode("utf-8", "strict")
            if len(text) > 45_000_000:
                fail("SIGNED_INDEX_DATA_TOO_BIG")
    except (tarfile.TarError, UnicodeDecodeError, OSError) as exc:
        raise ValueError("CERT_A19_R14_SIGNED_INDEX_PARSE_FAILED") from exc
    results = []
    for para in text.strip().split("\n\n"):
        entry: dict[str, str] = {}
        for line in para.splitlines():
            if len(line) >= 3 and line[1] == ":" and line[0].isalnum():
                if line[0] in entry:
                    fail("DUPLICATE_INDEX_FIELD")
                entry[line[0]] = line[2:]
        if "P" in entry and "V" in entry:
            results.append(entry)
    if len(results) < 1000 or len(results) > 140000:
        fail("PACKAGE_INDEX_COUNT_OUTSIDE_BOUNDS")
    return results


def make_report() -> dict:
    env = {
        "GITHUB_ACTIONS": "true",
        "MMT_NONPRODUCTION": "1",
        "GITHUB_REF": "refs/heads/cert-a19-byte-audit-run",
    }
    if any(os.environ.get(k) != v for k, v in env.items()):
        fail("NONPRODUCTION_FIXED_BRANCH_REQUIRED")
    work = Path(os.environ["RUNNER_TEMP"]) / "cert-a19-r14"
    repo = exact_repository(work)
    image = load_safe(work / "oci-base.txt", 300).decode().strip()
    if image != OCI_BASE:
        fail("SIGNED_BASE_IMAGE_IDENTITY_DRIFT")
    sig = load_safe(work / "cosign-status.txt", 400).decode().strip()
    if sig != "SIGNED_IMAGE_DIGEST_AND_IDENTITY_VERIFIED":
        fail("COSIGN_ATTESTATION_STEP_NOT_RECORDED")
    apkstatus = load_safe(work / "apk-index-verification-status.txt", 400).decode().strip()
    if apkstatus != "APK_TOOLS_SIGNED_INDEX_ACCEPTED_NO_ALLOW_UNTRUSTED":
        fail("APK_SIGNATURE_CHECK_NOT_CONFIRMED")
    root = work / "keydir"
    keys = sorted(root.rglob("*.pub"))
    if not 1 <= len(keys) <= 10 or any(not k.is_file() or k.is_symlink() for k in keys):
        fail("SIGNED_BASE_KEYRING_MISSING")
    fingerprints = [{"filename": k.name, "sha256": hashlib.sha256(load_safe(k, 5000)).hexdigest()}
                    for k in keys]
    raw = load_safe(work / "APKINDEX.tar.gz")
    pkgs = parse_index(raw)
    matching = {}
    for p in pkgs:
        name = p["P"]
        if name in INTEREST:
            value = {"name": name, "version": p["V"],
                     "index_control_checksum": p.get("C"),
                     "declared_runtime_dependencies": p.get("D", "").split(),
                     "declared_provides": p.get("p", "").split(),
                     "size": p.get("S")}
            matching.setdefault(name, []).append(value)
    for name, variants in matching.items():
        identities = [(v["version"], v["index_control_checksum"]) for v in variants]
        if len(identities) != len(set(identities)):
            fail("DUPLICATE_IDENTICAL_PACKAGE_VERSION")
        variants.sort(key=lambda v: (v["version"], v["index_control_checksum"] or ""))
    available = sorted(set(matching).intersection(TARGETS))
    missing = sorted(set(TARGETS) - set(available))
    glibc_options = sorted(k for k in matching if k.startswith("glibc"))
    result = {
        "stage": "CERT-A19-R14",
        "status": "SIGNED_APK_INDEX_METADATA_PROVENANCE_ONLY_NO_PACKAGE_BYTES",
        "signed_base": image,
        "repository_from_signed_base": repo,
        "repository_index_architecture": "x86_64",
        "repository_index_gzip_sha256": hashlib.sha256(raw).hexdigest(),
        "repository_index_bytes": len(raw),
        "key_material_sha256_from_signed_base": fingerprints,
        "apk_native_signature_validation_passed": True,
        "apk_signature_validation_was_run_against_exact_downloaded_index": True,
        "index_total_package_records": len(pkgs),
        "candidate_root_packages": matching,
        "package_names_with_multiple_index_versions": sorted(k for k,v in matching.items() if len(v) > 1),
        "exact_package_version_selection_without_resolver": False,
        "python_and_node_package_names_found": available,
        "python_and_node_package_names_missing": missing,
        "glibc_versioned_candidates_found": glibc_options,
        "index_control_checksums_are_NOT_full_apk_SHA256": True,
        "apk_archives_downloaded_and_sha256_pinned": 0,
        "full_transitive_dependency_closure_sha256_pinned": False,
        "verified_abi_python_node_glibc": False,
        "typescript_wasmtime_installed": False,
        "four_language_worker_parity_tested": False,
        "worker_or_any_container_code_executed": False,
        "no_new_docker_image_built": True,
        "source_risk_review_complete": False,
        "historic_199_findings_still_open": True,
        "any_cve_closed_or_suppressed": False,
        "independent_sandbox_host_certified": False,
        "runtime_a6_denied": True,
        "production_authorized": False,
    }
    (Path(os.environ["RUNNER_TEMP"]) / "cert-a19-r14-index-custody.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("CERT_A19_R14_APK_SIGNED_INDEX_SHA256=" + result["repository_index_gzip_sha256"])
    print("CERT_A19_R14_PYTHON_NODE_NAMES_FOUND=" + ",".join(available))
    print("CERT_A19_R14_GLIBC_CANDIDATES=" + ",".join(glibc_options))
    print("CERT_A19_R14_APK_ARCHIVES_AND_FULL_CLOSURE_NOT_YET_CERTIFIED")
    print("CERT_A19_R14_A6_DENY_199_REVIEW_OPEN")


if __name__ == "__main__":
    make_report()
