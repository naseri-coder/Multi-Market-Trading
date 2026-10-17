"""CERT-A19: immutable Debian undici archive/Worker byte custody; no CVE closure.

Does not install .deb, run Node, run Worker, build Docker or execute user code.
A18 file parity is UNKNOWN unless an independently obtained stopped-image root
is explicitly supplied. Source publisher signing is NOT independently attested.
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

_VERSION = "5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4"
_DEB_SHA = "78ec8918d63e365bbdec6edd35bebec9e20cc931f084f24e8673badf191d100c"
_DSC_SHA = "6befcb981dea58f2fdb9bc0d78624d829090105ab955d48e617a02ead37fd44c"
_LOCK_SHA = "47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872"
_MODULE = "usr/share/nodejs/undici"
_BALANCED = "lib/balanced-pool.js"
_CACHE = "lib/interceptor/cache.js"
_FENCE = "naseri_markets/runtime_a6_dispatch_fence.py"
_REQUIRED_DENY = 'raise RuntimeA6Denied("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED")'
_SHA = re.compile(r"[a-f0-9]{64}\Z")


class A19Refused(ValueError):
    """Fixed-code refusal, never echo untrusted paths/content."""


def regular(path: Path, limit: int) -> bytes:
    try:
        if path.is_symlink():
            raise A19Refused("A19_SYMLINK_REFUSED")
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not 0 < st.st_size <= limit:
            raise A19Refused("A19_INPUT_TYPE_OR_SIZE_INVALID")
        content = path.read_bytes()
        if len(content) != st.st_size:
            raise A19Refused("A19_INPUT_CHANGED_DURING_READ")
        return content
    except OSError as exc:
        raise A19Refused("A19_REQUIRED_INPUT_UNAVAILABLE") from exc


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verify_hash(path: Path, sha: str, limit: int) -> str:
    if not _SHA.fullmatch(sha) or digest(regular(path, limit)) != sha:
        raise A19Refused("A19_ARCHIVE_HASH_MISMATCH")
    return sha


def check_lock(root: Path) -> None:
    try:
        data = json.loads(regular(root / "deploy/runtime_a2/a11_apt_closure.json", 140_000),
                          object_pairs_hook=_reject_duplicate)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, A19Refused):
            raise
        raise A19Refused("A19_LOCK_INVALID") from exc
    if not isinstance(data, dict) or data.get("closure_sha256") != _LOCK_SHA:
        raise A19Refused("A19_LOCK_IDENTITY_MISMATCH")
    entries = data.get("packages")
    if not isinstance(entries, list) or len(entries) != 372:
        raise A19Refused("A19_LOCK_PACKAGE_COUNT_MISMATCH")
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("ascii")
    locked_digest = digest(b"MMT-A11-APT-ARCHIVE-CLOSURE-V1\x00" + canonical)
    if locked_digest != _LOCK_SHA:
        raise A19Refused("A19_LOCK_CONTENT_DRIFT")
    matches = [e for e in entries if isinstance(e, dict)
               and e.get("package") == "node-undici"]
    if len(matches) != 1 or matches[0] != {
        "package": "node-undici", "architecture": "all",
        "version": _VERSION, "sha256": _DEB_SHA,
    }:
        raise A19Refused("A19_UNDICI_PIN_MISMATCH")
    fence = regular(root / _FENCE, 200_000).decode("utf-8")
    if _REQUIRED_DENY not in fence:
        raise A19Refused("A19_RUNTIME_A6_DENY_MISSING")


def _reject_duplicate(pairs: list[tuple[str, object]]) -> dict:
    obj: dict = {}
    for key, val in pairs:
        if key in obj:
            raise A19Refused("A19_DUPLICATE_LOCK_KEY")
        obj[key] = val
    return obj


def _safe_member(root: Path, relative: str) -> Path:
    candidate = root
    for part in relative.split("/"):
        if part in {"", ".", ".."}:
            raise A19Refused("A19_UNSAFE_MEMBER_PATH")
        candidate = candidate / part
        if candidate.is_symlink():
            raise A19Refused("A19_SYMLINK_MEMBER_REFUSED")
    return candidate


def file_bytes(root: Path, relative: str) -> bytes:
    return regular(_safe_member(root, relative), 300_000)


def check_mechanisms(payload: Path, a18: Path | None) -> dict:
    # Source files inside a verified Debian .deb are the authority for the
    # *package* check, not yet for the Worker container's actual file bytes.
    base = _MODULE + "/"
    code = file_bytes(payload, base + _BALANCED)
    if (b"Object.assign({}, this[kOptions])" not in code
            or b"JSON.parse(JSON.stringify" in code):
        raise A19Refused("A19_BALANCED_POOL_UNEXPECTED_MECHANISM")
    cache = _safe_member(payload, base + _CACHE)
    if cache.exists() or cache.is_symlink():
        raise A19Refused("A19_CACHE_INTERCEPTOR_PATH_PRESENT")
    report = {
        "package_balanced_pool_sha256": digest(code),
        "package_named_cache_interceptor_absent": True,
        "package_specific_json_clone_absent": True,
        "worker_byte_parity": "UNVERIFIED_A18_STOPPED_IMAGE_NOT_PROVIDED",
        "worker_balanced_pool_sha256": None,
    }
    if a18 is not None:
        observed = file_bytes(a18, base + _BALANCED)
        other_cache = _safe_member(a18, base + _CACHE)
        if other_cache.exists() or other_cache.is_symlink():
            raise A19Refused("A19_WORKER_CACHE_INTERCEPTOR_PRESENT")
        if code != observed:
            raise A19Refused("A19_WORKER_AND_DEBIAN_BYTES_DIFFER")
        report["worker_byte_parity"] = "EXACT_TWO_PATHS_MATCH_PACKAGE_SOURCE_STILL_UNVERIFIED"
        report["worker_balanced_pool_sha256"] = digest(observed)
    return report


def audit(root: Path, deb: Path, dsc: Path, payload: Path, a18: Path | None) -> dict:
    check_lock(root)
    verify_hash(deb, _DEB_SHA, 2_000_000)
    verify_hash(dsc, _DSC_SHA, 16_000)
    manifest = regular(dsc, 16_000)
    if (b"Source: node-undici\n" not in manifest
            or ("Version: " + _VERSION + "\n").encode() not in manifest
            or b"-----BEGIN PGP SIGNED MESSAGE-----" not in manifest):
        raise A19Refused("A19_DSC_SOURCE_IDENTITY_INVALID")
    observed = check_mechanisms(payload, a18)
    return {
        "stage": "CERT-A19-R5", "source_version": _VERSION,
        "debian_binary_archive_sha256": _DEB_SHA,
        "debian_dsc_sha256": _DSC_SHA,
        "source_signature_independently_verified": False,
        "source_archive_tarballs_verified": False,
        **observed,
        "resolved_cves": 0, "original_critical_high_still_review_open": 199,
        "rootless_gvisor_certified": False,
        "production_authorized": False,
        "unknown_worker_code_executed": False,
        "verdict": "PINNED_PACKAGE_BYTE_EVIDENCE_ONLY_NO_CVE_DISPOSITION",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="A19 nonproduction byte-custody audit")
    for arg in ("root", "deb", "dsc", "payload", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--a18-root", type=Path)
    args = parser.parse_args()
    try:
        if (os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
                or os.environ.get("MMT_PRODUCTION") == "1"):
            raise A19Refused("A19_NONPRODUCTION_HOSTED_CI_REQUIRED")
        temp = Path(os.environ.get("RUNNER_TEMP", "/missing")).resolve()
        if (args.output.is_symlink() or args.output.resolve().parent != temp
                or args.output.name != "cert-a19-undici-custody.json"):
            raise A19Refused("A19_OUTPUT_MUST_BE_EPHEMERAL")
        result = audit(args.root, args.deb, args.dsc, args.payload, args.a18_root)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print("A19_DEBIAN_BINARY_AND_DSC_HASH_PIN_PASS")
        print("A19_WORKER_PARITY=" + result["worker_byte_parity"])
        print("A19_ALL_199_FINDINGS_REMAIN_OPEN")
    except (A19Refused, OSError, UnicodeError) as exc:
        print(str(exc) if isinstance(exc, A19Refused) else "A19_AUDIT_INCOMPLETE",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
