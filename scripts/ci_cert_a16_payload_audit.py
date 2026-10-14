"""CERT-A16: non-mutating byte-level CVE inventory/retention audit.

The only real-image action is Docker CREATE and CP from two fixed, already
built benign images on a disposable GitHub-hosted runner. Containers never
start. A Grype disappearance is NOT accepted as a vulnerability fix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

_IMAGES = ("mmt/runtime-a2-candidate:pr", "mmt/runtime-a15-lean:pr")
_PATH_OWNERS = {
    "node-undici": "/usr/share/nodejs/undici/undici-fetch.js",
    "libc6": "/usr/lib/x86_64-linux-gnu/libc.so.6",
    "libc-bin": "/usr/lib/x86_64-linux-gnu/libc.so.6",
    "libsqlite3-0": "/usr/lib/x86_64-linux-gnu/libsqlite3.so.0.8.6",
    "nodejs": "/usr/bin/node",
    "libnode108": "/usr/lib/x86_64-linux-gnu/libnode.so.108",
}
_PATHS = tuple(sorted(set(_PATH_OWNERS.values())))
_SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DOMAIN = b"MMT-CERT-A16-NONRELEASE-PAYLOAD-BYTE-AUDIT-V1\x00"


class A16Refused(ValueError):
    """Fixed error codes only, not untrusted scanner/path output."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for name, value in pairs:
        if name in obj:
            raise A16Refused("A16_DUPLICATE_JSON_FIELD")
        obj[name] = value
    return obj


def _read(path: Path, maximum: int) -> tuple[dict, str]:
    try:
        if path.is_symlink() or not path.is_file():
            raise A16Refused("A16_REQUIRED_REGULAR_FILE_MISSING")
        stat = path.stat()
        if not 0 < stat.st_size <= maximum or stat.st_nlink != 1:
            raise A16Refused("A16_FILE_SIZE_OR_HARDLINK_INVALID")
        raw = path.read_bytes()
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, A16Refused):
            raise
        raise A16Refused("A16_FILE_MISSING_OR_NOT_JSON") from exc
    if type(parsed) is not dict:
        raise A16Refused("A16_JSON_ROOT_NOT_OBJECT")
    return parsed, hashlib.sha256(raw).hexdigest()


def _run(argv: tuple[str, ...], timeout: int = 20) -> str:
    try:
        response = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            check=False, timeout=timeout, shell=False, close_fds=True,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise A16Refused("A16_DOCKER_INSPECTION_UNAVAILABLE") from exc
    if response.returncode != 0 or len(response.stdout) > 1024:
        raise A16Refused("A16_DOCKER_INSPECTION_FAILED")
    return response.stdout.decode("ascii").strip()


def _runner_guard() -> None:
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1",
        "MMT_CERT_A16_READ_ONLY": "1",
    }
    if (os.geteuid() == 0 or os.environ.get("MMT_PRODUCTION") == "1"
            or any(os.environ.get(key) != val
                   for key, val in required.items())):
        raise A16Refused("A16_ONLY_DISPOSABLE_HOSTED_NONPRODUCTION")


def capture_fixed_payload_sha() -> dict:
    """Never docker run/exec/start. Docker create + cp + rm on fixed local tags."""
    _runner_guard()
    results: dict[str, dict[str, str]] = {}
    for name in _IMAGES:
        image_id = _run(("/usr/bin/docker", "image", "inspect", name,
                         "--format", "{{.Id}}"))
        if _IMAGE_SHA.fullmatch(image_id) is None:
            raise A16Refused("A16_IMAGE_NOT_CONTENT_ADDRESSED")
        cid = _run(("/usr/bin/docker", "container", "create",
                    "--pull=never", "--entrypoint", "/bin/true", name))
        if not re.fullmatch(r"[0-9a-f]{64}", cid):
            raise A16Refused("A16_CONTAINER_ID_INVALID")
        files = {}
        try:
            with tempfile.TemporaryDirectory(prefix="a16-probe-") as folder:
                for index, path in enumerate(_PATHS):
                    destination = Path(folder) / str(index)
                    _run(("/usr/bin/docker", "cp", "-L",
                          f"{cid}:{path}", str(destination)), timeout=30)
                    if (not destination.is_file()
                            or not 0 < destination.stat().st_size < 70_000_000):
                        raise A16Refused("A16_EXPECTED_PAYLOAD_NOT_RETRIEVED")
                    with destination.open("rb") as handle:
                        files[path] = hashlib.file_digest(
                            handle, "sha256",
                        ).hexdigest()
            if image_id != _run(("/usr/bin/docker", "image", "inspect", name,
                                  "--format", "{{.Id}}")):
                raise A16Refused("A16_IMAGE_ID_CHANGED_DURING_INSPECTION")
        finally:
            _run(("/usr/bin/docker", "rm", "-f", cid))
        results[name] = {"id": image_id, "files": files}
    return {
        "schema": 1,
        "scope": "FIXED_LOCAL_IMAGE_CREATE_CP_NO_GUEST_PROCESS_STARTED",
        "baseline": results[_IMAGES[0]],
        "lean": results[_IMAGES[1]],
        "no_worker_launch_authorization": True,
    }


def _signature(match: dict) -> tuple[str, str, str, str]:
    item = match.get("artifact")
    v = match.get("vulnerability")
    if type(item) is not dict or type(v) is not dict:
        raise A16Refused("A16_MATCH_FIELDS_INVALID")
    fields = (
        v.get("id"), item.get("type"), item.get("name"),
        item.get("version"),
    )
    if any(type(x) is not str or not 0 < len(x) <= 256 for x in fields):
        raise A16Refused("A16_MATCH_IDENTITY_INVALID")
    return fields


def _file_sha_map(sbom: dict) -> dict[str, str]:
    if sbom.get("bomFormat") != "CycloneDX":
        raise A16Refused("A16_SBOM_FORMAT_INVALID")
    items = sbom.get("components")
    if type(items) is not list or not 1 <= len(items) <= 50_000:
        raise A16Refused("A16_SBOM_COMPONENTS_INVALID")
    output = {}
    for component in items:
        if type(component) is not dict:
            raise A16Refused("A16_SBOM_COMPONENT_MALFORMED")
        if component.get("type") != "file":
            continue
        path = component.get("name")
        if type(path) is not str or not path.startswith("/"):
            continue
        hashes = component.get("hashes", [])
        if type(hashes) is not list:
            raise A16Refused("A16_SBOM_HASHES_INVALID")
        for entry in hashes:
            if (type(entry) is dict and entry.get("alg") == "SHA-256"
                    and type(entry.get("content")) is str
                    and _HEX.fullmatch(entry["content"])):
                if path in output and output[path] != entry["content"]:
                    raise A16Refused("A16_CONFLICTING_SBOM_SHA")
                output[path] = entry["content"]
    if len(output) < 100:
        raise A16Refused("A16_SBOM_HAS_TOO_FEW_FILE_DIGESTS")
    return output


def audit(base_sbom: dict, base_scan: dict, lean_sbom: dict,
          lean_scan: dict, comparison: dict, probes: dict,
          actual_hashes: dict[str, str]) -> dict:
    """No CVE row receives a disposition of remediated or false-positive."""
    if type(comparison) is not dict or comparison.get("schema") != 1:
        raise A16Refused("A16_A15_COMPARISON_SCHEMA_INVALID")
    baseline, lean = comparison.get("baseline"), comparison.get("lean")
    if type(baseline) is not dict or type(lean) is not dict:
        raise A16Refused("A16_PAIRWISE_COMPARISON_MISSING")
    expected_hash_fields = (
        ("sbom_sha256", "base_sbom"), ("scan_sha256", "base_scan"),
    )
    for name, field in expected_hash_fields:
        if baseline.get(name) != actual_hashes.get(field):
            raise A16Refused("A16_BASE_SCAN_OR_SBOM_HASH_DRIFT")
    for name, field in expected_hash_fields:
        if lean.get(name) != actual_hashes.get("lean_" + field[5:]):
            raise A16Refused("A16_LEAN_SCAN_OR_SBOM_HASH_DRIFT")
    if (baseline.get("vulnerability_db_built")
            != lean.get("vulnerability_db_built")
            or comparison.get("worker_execution_authorized") is not False
            or comparison.get("production_authorized") is not False
            or comparison.get("reduced_grype_matches_do_not_establish_cve_remediation")
            is not True):
        raise A16Refused("A16_DB_OR_RELEASE_CONTRACT_MISMATCH")
    if (type(probes) is not dict or probes.get("schema") != 1
            or probes.get("scope") != "FIXED_LOCAL_IMAGE_CREATE_CP_NO_GUEST_PROCESS_STARTED"
            or probes.get("no_worker_launch_authorization") is not True):
        raise A16Refused("A16_UNTRUSTED_PAYLOAD_PROBE")
    for label, record in (("baseline", baseline), ("lean", lean)):
        observed = probes.get(label)
        if (type(observed) is not dict
                or observed.get("id") != record.get("image_id")
                or type(observed.get("files")) is not dict
                or set(observed["files"]) != set(_PATHS)
                or any(type(value) is not str or _HEX.fullmatch(value) is None
                       for value in observed["files"].values())):
            raise A16Refused("A16_IMAGE_OR_PAYLOAD_IDENTITY_NOT_VERIFIED")

    bfiles = _file_sha_map(base_sbom)
    lfiles = _file_sha_map(lean_sbom)
    common = set(bfiles) & set(lfiles)
    identical_sbom = sum(bfiles[path] == lfiles[path] for path in common)
    # Critical: copying retained bytes is NOT equivalent to fixing them.
    retained_probes = {
        path: {
            "baseline_sha256": probes["baseline"]["files"][path],
            "lean_sha256": probes["lean"]["files"][path],
            "bytes_identical": (
                probes["baseline"]["files"][path]
                == probes["lean"]["files"][path]
            ),
        }
        for path in _PATHS
    }
    for path in common & set(retained_probes):
        if (retained_probes[path]["baseline_sha256"] != bfiles[path]
                or retained_probes[path]["lean_sha256"] != lfiles[path]):
            raise A16Refused("A16_SBOM_AND_DOCKER_COPY_HASH_CONFLICT")
    for label, sbom_map in (("baseline", bfiles), ("lean", lfiles)):
        for path, evidence in retained_probes.items():
            if path in sbom_map and sbom_map[path] != evidence[label + "_sha256"]:
                raise A16Refused("A16_IMAGE_FILE_HASH_CONFLICT")

    base_matches = base_scan.get("matches")
    lean_matches = lean_scan.get("matches")
    if type(base_matches) is not list or type(lean_matches) is not list:
        raise A16Refused("A16_SCAN_MATCHES_NOT_LIST")
    for matches, record in ((base_matches, baseline), (lean_matches, lean)):
        if (len(matches) != record.get("matched_advisories")
                or len(matches) > 100_000):
            raise A16Refused("A16_GRYPE_MATCH_COUNTS_NOT_RECONCILED")
    lean_counts = Counter()
    for match in lean_matches:
        if type(match) is not dict or type(match.get("vulnerability")) is not dict:
            raise A16Refused("A16_LEAN_SCAN_ROW_INVALID")
        if match["vulnerability"].get("severity") in ("Critical", "High"):
            lean_counts[_signature(match)] += 1

    rows = []
    classifications = Counter()
    for match in base_matches:
        if type(match) is not dict or type(match.get("vulnerability")) is not dict:
            raise A16Refused("A16_BASE_SCAN_ROW_INVALID")
        severity = match["vulnerability"].get("severity")
        if severity not in _SEVERITIES:
            raise A16Refused("A16_UNKNOWN_SEVERITY")
        if severity not in ("Critical", "High"):
            continue
        key = _signature(match)
        path = _PATH_OWNERS.get(key[2])
        sampled_sha_identical = (
            retained_probes[path]["bytes_identical"]
            if path else None
        )
        if lean_counts[key] > 0:
            lean_counts[key] -= 1
            state = "SAME_ADVISORY_PACKAGE_VERSION_DETECTED_IN_LEAN"
        elif sampled_sha_identical is True:
            state = "NOT_SCANNER_MATCHED_SAMPLED_PAYLOAD_BYTES_RETAINED"
        else:
            state = "NOT_SCANNER_MATCHED_PAYLOAD_REMOVAL_UNPROVEN"
        classifications[state] += 1
        rows.append({
            "advisory_id": key[0],
            "severity": severity,
            "ecosystem": key[1],
            "package": key[2],
            "version": key[3],
            "observed_in_lean_by_same_grype_identity":
                state == "SAME_ADVISORY_PACKAGE_VERSION_DETECTED_IN_LEAN",
            "sampled_payload_path": path,
            "sampled_payload_equal_sha256": sampled_sha_identical,
            "evidence_class": state,
            "cve_fixed": False,
            "false_positive_confirmed": False,
            "exploitable_or_reachable_proven": False,
            "security_review_state": "OPEN",
        })
    rows.sort(key=lambda x: (x["severity"] != "Critical",
                              x["ecosystem"], x["package"],
                              x["advisory_id"], x["version"]))
    result = {
        "schema": 1,
        "status": "CERT_A16_BYTE_RETENTION_MEASURED_199_FINDINGS_UNRESOLVED",
        "baseline_image": baseline["image_id"],
        "lean_image": lean["image_id"],
        "same_advisory_db_built": baseline["vulnerability_db_built"],
        "base_sbom_files_with_sha256": len(bfiles),
        "lean_sbom_files_with_sha256": len(lfiles),
        "same_sbom_file_path_count": len(common),
        "identical_shared_sbom_file_sha256_count": identical_sbom,
        "critical_or_high_baseline_count": len(rows),
        "by_evidence_class": dict(sorted(classifications.items())),
        "sampled_runtime_paths": retained_probes,
        "all_original_findings_still_require_review": True,
        "missing_scanner_matches_not_confirmed_remediation": True,
        "image_rootless_gvisor_certified": False,
        "worker_execution_authorized": False,
        "production_authorized": False,
        "broker_authorized": False,
        "telegram_authorized": False,
        "findings": rows,
    }
    result["evidence_fingerprint_sha256"] = hashlib.sha256(
        _DOMAIN + json.dumps(result, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"),
    ).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="CERT-A16 audit, no release")
    for key in ("base-sbom", "base-scan", "lean-sbom", "lean-scan",
                "comparison"):
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        _runner_guard()
        root = Path(os.environ["RUNNER_TEMP"]).resolve()
        output = args.output.resolve()
        if (args.output.is_symlink() or output.parent != root
                or output.name != "cert-a16-payload-audit.json"):
            raise A16Refused("A16_REPORT_MUST_STAY_IN_RUNNER_TEMP")
        documents = {}
        digests = {}
        for name, limit in (
            ("base_sbom", 40_000_000), ("base_scan", 20_000_000),
            ("lean_sbom", 40_000_000), ("lean_scan", 20_000_000),
            ("comparison", 16_384),
        ):
            obj, digest = _read(getattr(args, name), limit)
            documents[name] = obj
            digests[name] = digest
        probe = capture_fixed_payload_sha()
        result = audit(
            documents["base_sbom"], documents["base_scan"],
            documents["lean_sbom"], documents["lean_scan"],
            documents["comparison"], probe, digests,
        )
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("CERT_A16_SCANNER_MATCHED="
              + str(result["by_evidence_class"].get(
                  "SAME_ADVISORY_PACKAGE_VERSION_DETECTED_IN_LEAN", 0)))
        print("CERT_A16_SAMPLE_BYTES_RETAINED_BUT_NOT_MATCHED="
              + str(result["by_evidence_class"].get(
                  "NOT_SCANNER_MATCHED_SAMPLED_PAYLOAD_BYTES_RETAINED", 0)))
        print("CERT_A16_UNPROVEN_REMOVAL="
              + str(result["by_evidence_class"].get(
                  "NOT_SCANNER_MATCHED_PAYLOAD_REMOVAL_UNPROVEN", 0)))
        print("CERT_A16_ALL_ORIGINAL_FINDINGS_OPEN_NO_WORKER_LAUNCH")
    except (A16Refused, OSError, KeyError, ValueError) as exc:
        print(str(exc) if isinstance(exc, A16Refused)
              else "A16_AUDIT_FILE_INVALID_OR_MISSING", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
