"""CERT-A18-R1: offline-only dpkg-owned JavaScript path absence proof.

Input manifests were copied from the *stopped* immutable A2 container,
and rootfs member names came from docker export of *stopped* containers.
Does not execute a strategy, accept arbitrary package names, change
images, prove upstream CVE remediation or certify a trusted host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

_PACKAGES = {
    "handlebars": ("3:4.7.7+~4.1.0-1", "usr/share/nodejs/handlebars/"),
    "node-flatted": ("3.2.7~ds-1+deb12u1", "usr/share/nodejs/flatted/"),
    "node-brace-expansion": ("2.0.1-2", "usr/share/nodejs/brace-expansion/"),
    "node-ip": ("2.0.0+~1.1.0-1", "usr/share/nodejs/ip/"),
    "node-postcss": ("8.4.20+~cs8.0.23-1+deb12u1", "usr/share/nodejs/postcss/"),
}
_CODE_EXT = (".js", ".cjs", ".mjs", ".json")
_A11_DIGEST = "47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872"
_IMAGE = re.compile(r"sha256:[a-f0-9]{64}\Z")
_MAX_TAR_LIST = 8_000_000
_MAX_PACKAGE_LIST = 240_000
_DOMAIN = b"MMT-CERT-A18-ABSENCE-REVIEW-ONLY-V1\x00"


class A18Refused(ValueError):
    """Static code only; never surface untrusted path content."""


def _load_utf8(path: Path, limit: int) -> tuple[str, str]:
    try:
        if path.is_symlink():
            raise A18Refused("A18_INPUT_SYMLINK_REFUSED")
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= limit):
            raise A18Refused("A18_EVIDENCE_MISSING_OR_SIZE_INVALID")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise A18Refused("A18_INPUT_NOT_READABLE") from exc
    return text, hashlib.sha256(raw).hexdigest()


def _normalize(path: str) -> str:
    if not path or "\x00" in path or "\r" in path:
        raise A18Refused("A18_UNSAFE_TAR_OR_DPKG_PATH")
    value = path.removeprefix("./").removeprefix("/")
    if value.endswith("/"):
        value = value[:-1]
    parts = value.split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise A18Refused("A18_UNSAFE_TAR_OR_DPKG_PATH")
    return "/".join(parts)


def _members(path: Path) -> tuple[set[str], str]:
    contents, digest = _load_utf8(path, _MAX_TAR_LIST)
    lines = contents.splitlines()
    if not 50 < len(lines) < 120_000:
        raise A18Refused("A18_UNBOUNDED_OR_MISSING_IMAGE_TREE")
    return {_normalize(item) for item in lines}, digest


def _owner_code_paths(pkg: str, path: Path) -> tuple[set[str], str]:
    content, digest = _load_utf8(path, _MAX_PACKAGE_LIST)
    code = set()
    for line in content.splitlines():
        # dpkg info/*.list uses "/." to denote the package's root directory.
        # Accept that one fixed sentinel only; do not relax any other path.
        if line == "/.":
            continue
        value = _normalize(line)
        if value.startswith(_PACKAGES[pkg][1]) and value.endswith(_CODE_EXT):
            code.add(value)
    if not 1 <= len(code) <= 3000:
        raise A18Refused("A18_DPKG_PACKAGE_HAS_NO_BOUNDED_CODE_PATHS")
    return code, digest


def _lock(root: Path) -> dict[str, str]:
    path = root / "deploy/runtime_a2/a11_apt_closure.json"
    source, _ = _load_utf8(path, 200_000)
    try:
        payload = json.loads(source)
    except ValueError as exc:
        raise A18Refused("A18_APT_LOCK_UNPARSABLE") from exc
    if (type(payload) is not dict
            or payload.get("closure_sha256") != _A11_DIGEST
            or type(payload.get("packages")) is not list
            or len(payload["packages"]) != 372):
        raise A18Refused("A18_BASELINE_ARCHIVE_LOCK_DRIFT")
    found: dict[str, str] = {}
    for entry in payload["packages"]:
        if type(entry) is not dict:
            raise A18Refused("A18_APT_ARCHIVE_INVALID")
        name, version = entry.get("package"), entry.get("version")
        if name in _PACKAGES:
            if name in found or type(version) is not str:
                raise A18Refused("A18_DUPLICATE_APT_ENTRY")
            found[name] = version
    if found != {k: v[0] for k, v in _PACKAGES.items()}:
        raise A18Refused("A18_BUILD_ONLY_PACKAGE_LOCK_VERSION_DRIFT")
    return found


def prove(
    root: Path, manifests: Path, base_paths: Path, candidate_paths: Path,
    base_image: str, candidate_image: str,
) -> dict:
    if (not _IMAGE.fullmatch(base_image) or
            not _IMAGE.fullmatch(candidate_image) or
            base_image == candidate_image):
        raise A18Refused("A18_DOCKER_IMAGE_ID_INVALID")
    _lock(root)
    base, base_sha = _members(base_paths)
    candidate, candidate_sha = _members(candidate_paths)
    if (not {"usr/bin/node", "opt/mmt/bin/runtime-a1-worker"}.issubset(
            candidate
        ) or "usr/share/nodejs/undici/undici-fetch.js" not in candidate
            or "usr/local/lib/node_modules/typescript/package.json" not in candidate):
        raise A18Refused("A18_REQUIRED_NODE_RUNTIME_DISAPPEARED")
    findings = []
    for pkg in _PACKAGES:
        paths, owner_sha = _owner_code_paths(pkg, manifests / f"{pkg}.list")
        present = paths & base
        if present != paths:
            raise A18Refused("A18_ORIGINAL_DPKG_CODE_NOT_IN_BASE_IMAGE")
        remaining = paths & candidate
        if remaining:
            raise A18Refused("A18_ORIGINAL_CODE_PATH_PRESENT_IN_CANDIDATE")
        findings.append({
            "package": pkg,
            "installed_debian_version": _PACKAGES[pkg][0],
            "original_package_path_manifest_sha256": owner_sha,
            "original_owned_code_path_count": len(paths),
            "original_owned_code_paths_present_in_original_image": len(present),
            "original_owned_code_paths_present_in_candidate": 0,
            "original_owned_code_paths_removed_from_candidate": len(paths),
            "path_absence_verified_not_global_content_absence": True,
            "fix_from_vendor_authenticated": False,
            "advisories_closed": 0,
            "status": "EXACT_OWNER_CODE_PATHS_ABSENT_ONLY_REVIEW_OPEN",
        })
    output = {
        "schema": 1,
        "stage": "CERT-A18-R1",
        "result": "FIXED_OWNER_PATH_ABSENCE_PROVEN_NO_CVE_REMEDIATION_CERTIFIED",
        "source_a17_critical_open": 18,
        "source_a17_high_open": 181,
        "baseline_image": base_image,
        "candidate_image": candidate_image,
        "baseline_tar_member_names_sha256": base_sha,
        "candidate_tar_member_names_sha256": candidate_sha,
        "owned_modules_examined": len(findings),
        "owned_code_paths_absent_from_candidate": sum(
            f["original_owned_code_paths_removed_from_candidate"] for f in findings
        ),
        "package_results": findings,
        "only_fixed_local_runner_images": True,
        "no_user_code_or_guest_process_started_by_audit": True,
        "other_code_locations_and_vulnerable_bundled_copies_not_excluded": True,
        "all_199_original_findings_remain_open": True,
        "image_isolation_certified": False,
        "publisher_signature_independently_verified": False,
        "worker_execution_authorized": False,
        "production_authorized": False,
        "telegram_authorized": False,
        "broker_authorized": False,
    }
    output["report_sha256"] = hashlib.sha256(
        _DOMAIN + json.dumps(output, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"),
    ).hexdigest()
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description="A18 exact file absence; no release")
    for name in ("original-paths", "candidate-paths", "manifests", "root",
                 "output"):
        ap.add_argument("--" + name, required=True, type=Path)
    for name in ("original-image", "candidate-image"):
        ap.add_argument("--" + name, required=True)
    args = ap.parse_args()
    try:
        requirements = {
            "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
            "MMT_CERT_A18_READ_ONLY": "1", "MMT_NONPRODUCTION": "1",
        }
        if (os.geteuid() == 0 or os.environ.get("MMT_PRODUCTION") == "1"
                or any(os.environ.get(k) != v for k, v in requirements.items())):
            raise A18Refused("A18_CI_SCOPE_OR_PRODUCTION_DENIED")
        runner = Path(os.environ.get("RUNNER_TEMP", "/nonexistent")).resolve()
        out = args.output.resolve()
        if (args.output.is_symlink() or out.parent != runner
                or out.name != "cert-a18-owner-absence.json"):
            raise A18Refused("A18_OUTPUT_NOT_EPHEMERAL")
        report = prove(
            args.root, args.manifests, args.original_paths,
            args.candidate_paths, args.original_image, args.candidate_image,
        )
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("A18_ABSENT_DEBIAN_MODULES=" + str(report["owned_modules_examined"]))
        print("A18_VERIFIED_ABSENT_ORIGINAL_CODE_PATHS="
              + str(report["owned_code_paths_absent_from_candidate"]))
        print("A18_STATUS=" + report["result"])
    except (A18Refused, OSError, KeyError, ValueError) as exc:
        print(str(exc) if isinstance(exc, A18Refused)
              else "A18_EVIDENCE_UNAVAILABLE", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
