"""CERT-A19-R13: Wolfi base provenance-only, never run an OCI image.

Inputs originate from a dedicated GitHub-hosted CI run. No production or
sandbox certification can be inferred from this verifier.
"""
import hashlib
import json
import os
import re
from pathlib import Path

DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
IMAGE = "cgr.dev/chainguard/wolfi-base"
IDENTITY = "https://github.com/chainguard-images/images/.github/workflows/release.yaml@refs/heads/main"
ISSUER = "https://token.actions.githubusercontent.com"


def fail(code):
    raise ValueError("CERT_A19_R13_" + code)


def parse_manifest(text):
    # Inspect output is untrusted registry metadata, NOT publisher authentication.
    data = json.loads(text)
    if not isinstance(data, dict):
        fail("INVALID_MANIFEST")
    entries = data.get("manifests")
    if not isinstance(entries, list) or not entries or len(entries) > 50:
        fail("NO_BOUNDED_MANIFEST_LIST")
    amd64 = [m for m in entries if isinstance(m, dict)
             and m.get("platform", {}).get("os") == "linux"
             and m.get("platform", {}).get("architecture") == "amd64"]
    if len(amd64) != 1 or not DIGEST.fullmatch(amd64[0].get("digest", "")):
        fail("NO_EXACT_AMD64_DIGEST")
    return amd64[0]["digest"], len(entries)


def parse_signatures(text, expected):
    data = json.loads(text)
    if not isinstance(data, list) or not 1 <= len(data) <= 30:
        fail("NO_SIGNER_VERIFICATION_RECORD")
    values = []
    for item in data:
        if not isinstance(item, dict):
            fail("INVALID_SIGNER_VERIFICATION_RECORD")
        digest = ((item.get("critical") or {}).get("image") or {}).get("docker-manifest-digest")
        if digest == expected:
            values.append(digest)
    if not values:
        fail("COSIGN_SIGNATURE_DIGEST_MISMATCH")
    return len(values)


def parse_os_release(text):
    lines = [v.split("=", 1) for v in text.splitlines() if "=" in v]
    items = {k: v.strip('"') for k, v in lines}
    if items.get("ID", "").lower() != "wolfi":
        fail("OS_NOT_WOLFI")
    return items.get("ID"), items.get("VERSION_ID")


def inspect_packages(text):
    # Wolfi apk database is informative only. Repository index is not a frozen,
    # signed package closure for the final Worker.
    records = []
    for record in text.split("\n\n"):
        fields = dict(line.split(":", 1) for line in record.splitlines()
                      if ":" in line and line[:2] in {"P:", "V:"})
        if "P" in fields and "V" in fields:
            records.append((fields["P"], fields["V"]))
    glibc = [(p, v) for p, v in records if p in ("glibc", "glibc-locale-posix")]
    # A base image is not expected to pre-install the final Worker native ABI.
    # Report absence without falsely certifying glibc compatibility.
    return sorted(glibc), len(records)


def main():
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/cert-a19-byte-audit-run",
        "MMT_NONPRODUCTION": "1",
    }
    if any(os.environ.get(k) != v for k, v in required.items()):
        fail("RESEARCH_SCOPE_REQUIRED")
    root = Path(os.environ["RUNNER_TEMP"]) / "cert-a19-r13"
    root.resolve().relative_to(Path(os.environ["RUNNER_TEMP"]).resolve())
    plain = (root / "resolved-digest.txt").read_text().strip()
    if not DIGEST.fullmatch(plain):
        fail("REGISTRY_DIGEST_NOT_FROZEN")
    manifest_digest, count = parse_manifest((root / "raw-manifest.json").read_text())
    signed_count = parse_signatures((root / "cosign-verify.json").read_text(), plain)
    os_name, os_version = parse_os_release((root / "os-release").read_text())
    glibc, installed_count = inspect_packages((root / "apk-installed").read_text())
    repo_digests = json.loads((root / "repo-digests.json").read_text())
    if not isinstance(repo_digests, list) or IMAGE + "@" + plain not in repo_digests:
        fail("STOPPED_IMAGE_DIGEST_IDENTITY_DRIFT")
    if (root / "container-state.txt").read_text().strip() != "created":
        fail("CONTAINER_WAS_EXECUTED_OR_STATE_CHANGED")

    registry_packages = []
    raw_index = root / "apk-index-list.txt"
    if raw_index.is_file():
        lines = raw_index.read_text()[:2_000_000].splitlines()
        for line in lines:
            if line.startswith("P:") and (
                "python-3.12" in line or "nodejs-24" in line
                or line in ("P:python3", "P:nodejs")
            ):
                registry_packages.append(line[2:])
    summary = {
        "stage": "CERT-A19-R13",
        "status": ("WOLFI_SIGNED_BASE_PROVENANCE__GLIBC_INSTALLED_NOT_ABI_TESTED"
                   if glibc else "WOLFI_SIGNED_BASE_PROVENANCE__GLIBC_NOT_INSTALLED"),
        "candidate_image": IMAGE + "@" + plain,
        "manifest_index_digest": plain,
        "linux_amd64_manifest_digest": manifest_digest,
        "manifest_architecture_count": count,
        "cosign_signatures_matching_exact_manifest_digest": signed_count,
        "verified_cosign_signer_identity": IDENTITY,
        "verified_cosign_oidc_issuer": ISSUER,
        "observed_container_os": os_name,
        "os_version": os_version,
        "observed_installed_glibc_packages": glibc,
        "glibc_already_present_in_base": bool(glibc),
        "glibc_worker_abi_compatibility_verified": False,
        "observed_installed_apk_package_count": installed_count,
        "apk_index_candidate_name_observations_unattested": sorted(set(registry_packages)),
        "python_3_12_in_final_image_verified": False,
        "node_24_in_final_image_verified": False,
        "wasmtime_49_in_final_image_verified": False,
        "typescript_5_9_3_in_final_image_verified": False,
        "four_language_fixture_equivalence_verified": False,
        "full_software_bill_of_materials_attested": False,
        "apk_repository_index_signature_verified": False,
        "worker_or_guest_code_executed": False,
        "runtime_a6_security_gate_unchanged": True,
        "independent_sandbox_host_certified": False,
        "cves_fixed_or_false_positive_certified": 0,
        "original_critical_high_findings_review_open": 199,
        "production_authorized": False,
    }
    (Path(os.environ["RUNNER_TEMP"]) / "cert-a19-r13-provenance.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print("CERT_A19_R13_WOLFI_SIGNED_IMAGE_DIGEST_VERIFIED=" + plain)
    print("CERT_A19_R13_WOLFI_GLIBC_INSTALLED_APK_PACKAGE_COUNT=" + str(installed_count))
    print("CERT_A19_R13_FULL_WORKER_ABI_AND_SECURITY_NOT_CERTIFIED_199_OPEN")


if __name__ == "__main__":
    main()
