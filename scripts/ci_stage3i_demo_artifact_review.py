"""Stage 3I: cryptographic Wheel-file integrity / NONRELEASE review artifact.

No GitHub Releases, signed-publisher status, official tag, private keys, LIVE,
server, Telegram or broker. This script only inspects and runs a scratch demo.
"""
from __future__ import annotations

import base64
import configparser
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from email.parser import Parser
from pathlib import Path

from scripts import ci_stage3h_isolated_demo_wheel as prior

BASE = "7bbb3541fb6d63f960bee9f197fe026ed6d04608"
PARENT = "4f32d71486a67f60897f6eb6418de3e65ab18fc8"
BRANCH = "ci/stage3i-demo-artifact-review-20261017"
CHANGED = prior.EXPERIMENT_FILES | {
    ".github/workflows/stage3i-demo-artifact-review.yml",
    "scripts/ci_stage3i_demo_artifact_review.py",
    "docs/MMT_V0_4_0_STAGE3I_DEMO_REVIEW_ARTIFACT.md",
}
DIST_INFO = "multi_market_trading_offline_demo-0.4.0rc1.dist-info/"
AUXILIARY = frozenset({
    "METADATA", "WHEEL", "RECORD", "entry_points.txt", "top_level.txt",
    "licenses/LICENSE",
})


def reject(reason):
    raise ValueError("STAGE3I_REFUSED_" + reason)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _verify_sources(repo):
    if prior.check(["git", "branch", "--show-current"], cwd=repo) != BRANCH:
        reject("DIFFERENT_REVIEW_BRANCH")
    if prior.check(["git", "rev-parse", PARENT + "^"], cwd=repo) != BASE:
        reject("SOURCE_ANCESTRY_MISMATCH")
    # Permit a few scoped review-script fixes without rewriting Git history.
    ancestry = prior.subprocess.run(
        ["git", "merge-base", "--is-ancestor", PARENT, "HEAD"],
        cwd=repo, stdout=prior.subprocess.DEVNULL,
        stderr=prior.subprocess.DEVNULL, check=False,
    )
    depth = int(prior.check(["git", "rev-list", "--count", PARENT + "..HEAD"], cwd=repo))
    if ancestry.returncode or not 1 <= depth <= 8:
        reject("UNAPPROVED_REVIEW_BRANCH_ANCESTRY")
    if prior.check(["git", "status", "--porcelain"], cwd=repo):
        reject("DIRTY_WORKTREE")
    modified = set(prior.check([
        "git", "diff", "--name-only", BASE, "HEAD",
    ], cwd=repo).splitlines())
    if modified != CHANGED:
        reject("UNAPPROVED_SOURCE_CHANGE")
    tree_base = prior.check(["git", "rev-parse", BASE + ":naseri_markets"], cwd=repo)
    tree_now = prior.check(["git", "rev-parse", "HEAD:naseri_markets"], cwd=repo)
    if tree_base != tree_now or tree_now != "511e9346d88280f3be7c80367f8822a8eaa24dd7":
        reject("SOURCE_TREE_DRIFT")
    if len(prior.MODULES) != 19 or len(prior.CONSOLES) != 2:
        reject("EXACT_SCOPE_DRIFT")
    return tree_now


def audit_wheel(wheel, repo):
    """Validate COMPLETE wheel RECORD, files, CLI, and *original source bytes*."""
    try:
        with zipfile.ZipFile(wheel, "r") as arc:
            entries = arc.infolist()
            names = [entry.filename for entry in entries]
            if len(set(names)) != len(names) or any(
                name.startswith("/") or ".." in Path(name).parts or "\\" in name
                for name in names
            ):
                reject("DUPLICATE_OR_TRAVERSAL_MEMBER")
            source_names = {
                "naseri_markets/" + mod + ".py" for mod in prior.MODULES
            }
            accepted = source_names | {DIST_INFO + name for name in AUXILIARY}
            if not set(names).issubset(accepted):
                reject("UNEXPECTED_WHEEL_MEMBER")
            expected = source_names | {
                DIST_INFO + x for x in ("METADATA", "WHEEL", "RECORD", "entry_points.txt")
            }
            if not expected.issubset(names):
                reject("WHEEL_REQUIRED_MEMBER_MISSING")
            for info in entries:
                if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    reject("DIRECTORY_OR_LINK_MEMBER")
                if info.file_size > 3_000_000:
                    reject("OVERSIZED_WHEEL_MEMBER")
            content = {name: arc.read(name) for name in names}
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("STAGE3I_REFUSED_CORRUPT_WHEEL") from exc

    records = list(csv.reader(io.StringIO(content[DIST_INFO + "RECORD"].decode("utf-8"))))
    records_by_name = {}
    for row in records:
        if len(row) != 3 or row[0] in records_by_name:
            reject("INVALID_RECORD_ENTRY")
        records_by_name[row[0]] = (row[1], row[2])
    if set(records_by_name) != set(names):
        reject("INCOMPLETE_RECORD_FILE_LIST")
    for name, blob in content.items():
        digest, length = records_by_name[name]
        if name == DIST_INFO + "RECORD":
            if digest or length:
                reject("RECORD_SELF_DIGEST_MUST_BE_EMPTY")
        else:
            expected_hash = "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(blob).digest()
            ).rstrip(b"=").decode("ascii")
            if digest != expected_hash or length != str(len(blob)):
                reject("RECORD_HASH_OR_LENGTH_MISMATCH")

    for module in sorted(prior.MODULES):
        name = "naseri_markets/" + module + ".py"
        original = (repo / name).read_bytes()
        if content[name] != original:
            reject("WHEEL_SOURCE_DIFFERS_FROM_EXACT_GIT")

    meta = Parser().parsestr(content[DIST_INFO + "METADATA"].decode("utf-8"))
    # PEP 345 metadata may re-order comma-separated Python specifiers,
    # without changing the supported Python interval.
    got_name = meta.get("Name", "").lower().replace("_", "-")
    if got_name != prior.PACKAGE:
        reject("DISTRIBUTION_NAME_DRIFT")
    if meta.get("Version") != prior.WHEEL_VERSION:
        reject("DISTRIBUTION_VERSION_DRIFT")
    python_range = meta.get("Requires-Python", "")
    normalized_python = {item.strip() for item in python_range.split(",")}
    if normalized_python != {">=3.12", "<3.13"}:
        reject("DISTRIBUTION_PYTHON_RANGE_DRIFT")
    if meta.get_all("Requires-Dist"):
        reject("UNAPPROVED_BASE_DEPENDENCIES")
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read_string(content[DIST_INFO + "entry_points.txt"].decode("utf-8"))
    if dict(config.items("console_scripts")) != prior.CONSOLES:
        reject("EXECUTABLE_ENTRYPOINT_SCOPE_DRIFT")
    if len([x for x in names if x.endswith(".dist-info/WHEEL")]) != 1:
        reject("MULTIPLE_DIST_INFO")
    return {name: _sha(content[name]) for name in sorted(source_names)}


def _replace_wheel(wheel, output, *, target, injected=None, mutate=None):
    with zipfile.ZipFile(wheel) as reader, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as writer:
        for item in reader.infolist():
            payload = reader.read(item.filename)
            if item.filename == target and mutate is not None:
                payload = mutate(payload)
            writer.writestr(item, payload)
        if injected is not None:
            writer.writestr(injected, b"import socket\n")


def exercise_negative_tamper(wheel, repo, root):
    trial = root / "modified_code.whl"
    _replace_wheel(
        wheel, trial, target="naseri_markets/contracts.py",
        mutate=lambda data: data + b"\n#malicious mutation\n",
    )
    try:
        audit_wheel(trial, repo)
    except ValueError as exc:
        if str(exc) != "STAGE3I_REFUSED_RECORD_HASH_OR_LENGTH_MISMATCH":
            raise
    else:
        reject("MUTATED_CODE_ACCEPTED")

    trial2 = root / "injected_pth.whl"
    _replace_wheel(wheel, trial2, target="not_present", injected="sitecustomize.pth")
    try:
        audit_wheel(trial2, repo)
    except ValueError as exc:
        if str(exc) != "STAGE3I_REFUSED_UNEXPECTED_WHEEL_MEMBER":
            raise
    else:
        reject("UNDECLARED_STARTUP_INJECTION_ACCEPTED")

    trial3 = root / "tampered_cli.whl"
    _replace_wheel(
        wheel, trial3, target=DIST_INFO + "entry_points.txt",
        mutate=lambda data: data + b"\nnaseri-brooks-market = x.y:main\n",
    )
    try:
        audit_wheel(trial3, repo)
    except ValueError as exc:
        if str(exc) != "STAGE3I_REFUSED_RECORD_HASH_OR_LENGTH_MISMATCH":
            raise
    else:
        reject("TAMPERED_ENTRYPOINT_ACCEPTED")
    # A stronger forgery: attacker rewrites both source AND RECORD correctly.
    # The independent pin to actual reviewed Git source still must reject it.
    trial4 = root / "rehashed_malicious_source.whl"
    with zipfile.ZipFile(wheel, "r") as original:
        original_entries = [
            (entry, original.read(entry.filename))
            for entry in original.infolist()
            if entry.filename != DIST_INFO + "RECORD"
        ]
    target = "naseri_markets/contracts.py"
    writer_bytes = io.StringIO(newline="")
    records = csv.writer(writer_bytes, lineterminator="\n")
    with zipfile.ZipFile(trial4, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for info, blob in original_entries:
            if info.filename == target:
                blob += b"\n#rehashed hostile payload\n"
            output.writestr(info, blob)
            encoded = base64.urlsafe_b64encode(hashlib.sha256(blob).digest())
            records.writerow([
                info.filename,
                "sha256=" + encoded.rstrip(b"=").decode("ascii"),
                str(len(blob)),
            ])
        records.writerow([DIST_INFO + "RECORD", "", ""])
        output.writestr(DIST_INFO + "RECORD", writer_bytes.getvalue().encode())
    try:
        audit_wheel(trial4, repo)
    except ValueError as exc:
        if str(exc) != "STAGE3I_REFUSED_WHEEL_SOURCE_DIFFERS_FROM_EXACT_GIT":
            raise
    else:
        reject("VALID_REHASHED_MALICIOUS_SOURCE_ACCEPTED")
    print("STAGE3I_4_OF_4_WHEEL_TAMPER_ATTACKS_REFUSED")


def main():
    if sys.version_info[:2] != (3, 12):
        reject("PYTHON_312_REQUIRED")
    repo = Path(__file__).resolve().parents[1]
    tree = _verify_sources(repo)
    destination = Path(os.environ["RUNNER_TEMP"]) / "mmt-stage3i-review"
    if destination.exists() or destination.is_symlink():
        reject("REVIEW_OUTPUT_ALREADY_EXISTS")
    destination.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix="stage3i-build-") as location:
        scratch = Path(location)
        scratch.chmod(0o700)
        contexts, source_digests = prior._stage(repo, scratch)
        wheel, wheel_sha256 = prior._build(contexts, scratch)
        prior._verify_wheel(wheel)
        module_digests = audit_wheel(wheel, repo)
        if set(module_digests) != {
            "naseri_markets/" + module + ".py" for module in source_digests
        }:
            reject("SOURCE_MANIFEST_INCONSISTENT")
        exercise_negative_tamper(wheel, repo, scratch)
        python = prior._validate_installed(scratch / "venv", wheel)
        prior._deny_network_end_to_end(python, scratch)
        # The review artifact is UNTRUSTED BY DESIGN: no publisher signature.
        manifest = {
            "schema": 1,
            "verdict": "STAGE3I_UNSIGNED_DEMO_REVIEW_ONLY__NOT_RELEASE_AUTHORIZED",
            "original_candidate_sha": BASE,
            "experimental_parent_sha": PARENT,
            "original_source_tree_sha1": tree,
            "wheel_sha256": wheel_sha256,
            "source_module_sha256": module_digests,
            "distribution": prior.PACKAGE,
            "version": prior.WHEEL_VERSION,
            "allowed_cli": prior.CONSOLES,
            "excluded_live_provider_proof": "BINANCE_451_BYBIT_403",
            "two_reproducible_wheels": True,
            "runtime_network_namespace_demo_passed": True,
            "tamper_negative_cases_passed": 4,
            "publisher_key_authenticated": False,
            "human_scope_approved": False,
            "release_authorized": False,
            "merge_authorized": False,
            "live_trading_authorized": False,
        }
        copy = destination / wheel.name
        shutil.copyfile(wheel, copy)
        if _sha(copy.read_bytes()) != manifest["wheel_sha256"]:
            reject("COPIED_WHEEL_SHA_MISMATCH")
        (destination / "REVIEW_ONLY.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        (destination / "NOT_A_RELEASE.txt").write_text(
            "UNSIGNED TEST-ONLY WHEEL; NO OWNER RELEASE APPROVAL.\n"
            "Do not install on production devices. Do not upload to PyPI.\n"
            "The genuine Binance/Bybit public read tests returned HTTP 451/403.\n"
            "This Wheel is a *different distribution* from multi-market-trading.\n",
            encoding="utf-8",
        )
    print("STAGE3I_COMPLETE_RECORD_ORIGINAL_GIT_BYTE_CUSTODY_PASS")
    print("STAGE3I_REAL_OFFLINE_WHEEL_INSTALLED_IN_NETWORK_NAMESPACE_PASS")
    print(json.dumps({
        "verdict": "STAGE3I_REVIEWABLE_UNSIGNED_TEST_ARTIFACT_PASS_RELEASE_BLOCKED",
        "candidate_sha": BASE,
        "wheel_sha256": wheel_sha256,
        "bundled_modules": len(module_digests),
        "cli": sorted(prior.CONSOLES),
        "external_publisher_signature": False,
        "human_approval": False,
        "official_release_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
