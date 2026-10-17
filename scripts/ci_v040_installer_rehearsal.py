"""Offline full-platform Wheel+installer release-candidate rehearsal; NEVER publish."""
from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from scripts import mmt_v040_offline_stable_staging_v1 as staging

SOURCE_SHA = "7bbb3541fb6d63f960bee9f197fe026ed6d04608"
TREE = "511e9346d88280f3be7c80367f8822a8eaa24dd7"
SNAP = "c2554a8a1c3a46d1675e8e44429c017f6981758df012d5b5feecab353bcf9b9c"
EXPECTED_METADATA_SHA = "11d87431c863a20514541d8c2eaf70e47555d0ca2e2dbd8d1ded11c994ac01d7"
WHEEL = "multi_market_trading-0.4.0-py3-none-any.whl"
BRANCH = "ci/v040-offline-installer-rehearsal-20261018"
FILES = {
    "release_assets/v0.4.0/install.sh",
    "scripts/ci_v040_installer_rehearsal.py",
    ".github/workflows/v040-installer-rehearsal.yml",
    "docs/MMT_V040_OFFLINE_INSTALLER_REHEARSAL.md",
}
CLI = {
    "naseri-markets", "naseri-custom", "naseri-paper-demo",
    "naseri-paper-pilot", "naseri-engine-admin", "naseri-brooks-replay",
    "naseri-brooks-market", "naseri-brooks-kraken-paper",
    "naseri-brooks-paper-service",
}


def check(*cmd, cwd=None, env=None):
    return subprocess.check_output(
        cmd, cwd=cwd, env=env, stderr=subprocess.STDOUT, text=True, timeout=270,
    ).strip()


def deny(code):
    raise RuntimeError("V040_INSTALLER_REHEARSAL_REFUSED_" + code)


def source_audit(repo, branch):
    if sys.version_info[:2] != (3, 12):
        deny("REQUIRES_PYTHON312")
    if "MMT_PRODUCTION" in os.environ or os.getenv("MMT_NONPRODUCTION") != "1":
        deny("NONPRODUCTION_ONLY")
    if check("git", "rev-parse", "HEAD", cwd=repo) != SOURCE_SHA:
        deny("SOURCE_SHA_MOVED")
    if check("git", "rev-parse", "HEAD:naseri_markets", cwd=repo) != TREE:
        deny("MODULE_SOURCE_TREE_DRIFT")
    if check("git", "status", "--porcelain=v1", "--untracked-files=all", cwd=repo):
        deny("DIRTY_CANONICAL_CHECKOUT")
    if check("git", "branch", "--show-current", cwd=branch) != BRANCH:
        deny("UNAPPROVED_REHEARSAL_BRANCH")
    check("git", "merge-base", "--is-ancestor", SOURCE_SHA, "HEAD", cwd=branch)
    changed = set(check("git", "diff", "--name-only", SOURCE_SHA, "HEAD", cwd=branch).splitlines())
    if changed != FILES:
        deny("BRANCH_CHANGED_PRODUCT_SOURCE")
    for subdir in ("naseri_markets", "production_source", "platform_release"):
        if check("git", "rev-parse", "HEAD:" + subdir, cwd=branch) != check(
            "git", "rev-parse", SOURCE_SHA + ":" + subdir, cwd=branch
        ):
            deny("PRODUCT_SOURCE_MODIFIED_" + subdir)


def wheel_audit(wheel, staged):
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any(
            name.startswith("/") or ".." in Path(name).parts for name in names
        ):
            deny("UNSAFE_WHEEL_PATH")
        archive_files = {x for x in names if x.startswith("naseri_markets/") and x.endswith(".py")}
        disk_files = {
            "naseri_markets/" + p.name
            for p in (staged / "naseri_markets").glob("*.py")
        }
        if len(archive_files) != 226 or archive_files != disk_files:
            deny("PUBLIC_WHEEL_MODULE_DRIFT")
        for name in disk_files:
            if z.read(name) != (staged / name).read_bytes():
                deny("SOURCE_MODULE_BYTE_MISMATCH")
        dist = "multi_market_trading-0.4.0.dist-info/"
        data = {n: z.read(n) for n in names}
        rec = list(csv.reader(io.StringIO(data[dist + "RECORD"].decode())))
        if len(rec) != len(names) or len({x[0] for x in rec}) != len(names):
            deny("RECORD_FILE_LIST_MISMATCH")
        for row in rec:
            if len(row) != 3 or row[0] not in data:
                deny("RECORD_FORMAT")
            name, digest, length = row
            if name == dist + "RECORD":
                if digest or length:
                    deny("RECORD_SELF_HASH")
            else:
                expected = "sha256=" + base64.urlsafe_b64encode(
                    hashlib.sha256(data[name]).digest()
                ).rstrip(b"=").decode()
                if digest != expected or length != str(len(data[name])):
                    deny("RECORD_DIGEST_ERROR")
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read_string(data[dist + "entry_points.txt"].decode())
        if set(cfg["console_scripts"]) != CLI:
            deny("WHEEL_NINE_CLI_MISMATCH")
        metadata = data[dist + "METADATA"].decode()
        if "Version: 0.4.0" not in metadata or "Name: multi-market-trading" not in metadata:
            deny("STABLE_METADATA_VERSION_MISMATCH")
    print("V040_REAL_226_MODULE_NINE_CLI_WHEEL_RECORD_PASS")


def run_bundle_installer(bundle, root):
    runner_name = check("id", "-un")
    py = shutil.which("python3.12")
    if not py or not shutil.which("unshare") or not shutil.which("sudo"):
        deny("NO_ISOLATED_LINUX_RUNNER")
    dest = root / "installed"
    command = [
        "sudo", "-n", "unshare", "--net", "--", "runuser",
        "-u", runner_name, "--", "env", "-i",
        "PATH=" + os.environ["PATH"],
        "HOME=" + os.environ["HOME"],
        "APP_ENV=test", "MMT_NONPRODUCTION=1",
        "PYTHONDONTWRITEBYTECODE=1",
        "bash", str(bundle / "install.sh"), "--prefix", str(dest),
    ]
    test = subprocess.run(command, capture_output=True, text=True, timeout=125)
    if test.returncode:
        print("V040_INSTALL_FAILURE_STDOUT:", test.stdout[-4500:])
        print("V040_INSTALL_FAILURE_STDERR:", test.stderr[-4500:])
        deny("REAL_NO_NETWORK_INSTALL_FAILED")
    if "MMT_OFFLINE_INSTALL_SUCCESS" not in test.stdout:
        deny("INSTALL_SUCCESS_MARKER_MISSING")
    if not (dest / "venv/bin/naseri-markets").is_file():
        deny("REAL_INSTALLED_CLI_MISSING")
    print("V040_NINE_CLI_INSTALLED_NONROOT_NETNS_PASS")


def negative_checks(bundle, root):
    manifest = (bundle / "SHA256SUMS").read_text()
    tampered = root / "tampered"
    tampered.mkdir(mode=0o700)
    shutil.copy2(bundle / "SHA256SUMS", tampered / "SHA256SUMS")
    shutil.copy2(bundle / "install.sh", tampered / "install.sh")
    shutil.copy2(bundle / "NOT_A_RELEASE.txt", tampered / "NOT_A_RELEASE.txt")
    shutil.copy2(bundle / WHEEL, tampered / WHEEL)
    with (tampered / WHEEL).open("ab") as f:
        f.write(b"forged")
    target = root / "denied-tampered"
    p = subprocess.run(
        ["bash", str(tampered / "install.sh"), "--prefix", str(target)],
        capture_output=True, text=True, timeout=15,
    )
    if p.returncode == 0 or "WHEEL_DIGEST_MISMATCH" not in p.stderr or target.exists():
        deny("TAMPERED_WHEEL_ACCEPTED")
    target2 = root / "denied-production"
    e = dict(os.environ)
    e["MMT_PRODUCTION"] = "0"
    p = subprocess.run(
        ["bash", str(bundle / "install.sh"), "--prefix", str(target2)],
        env=e, capture_output=True, text=True, timeout=15,
    )
    if p.returncode == 0 or "PRODUCTION_NOT_AUTHORIZED" not in p.stderr or target2.exists():
        deny("PRODUCTION_FLAG_ACCEPTED")
    if len(manifest.splitlines()) != 1:
        deny("MANIFEST_MULTILINE")
    print("V040_TAMPER_AND_PRODUCTION_NEGATIVE_GATES_PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", type=Path, required=True)
    ap.add_argument("--branch", type=Path, required=True)
    args = ap.parse_args()
    canonical, branch = args.canonical.resolve(), args.branch.resolve()
    source_audit(canonical, branch)
    runner_temp = Path(os.environ["RUNNER_TEMP"])
    with tempfile.TemporaryDirectory(prefix="v040-installer-", dir=runner_temp) as scratch:
        root = Path(scratch)
        root.chmod(0o700)
        wheel_paths = []
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOURCE_DATE_EPOCH": check(
                "git", "show", "-s", "--format=%ct", "HEAD", cwd=canonical
            ),
            "PIP_NO_INDEX": "1",
            "PIP_CONFIG_FILE": "/dev/null",
        }
        for n in ("a", "b"):
            staged = root / ("source-" + n)
            result = staging.stage(
                repository=canonical, destination=staged,
                expected_source_commit=SOURCE_SHA,
                expected_public_tree_sha1=TREE,
                expected_lock_sha256=SNAP,
            )
            if result["staged_metadata_sha256"] != EXPECTED_METADATA_SHA:
                deny("STABLE_OVERLAY_CHANGED")
            destination = root / ("wheels-" + n)
            destination.mkdir(mode=0o700)
            check(
                sys.executable, "-m", "pip", "wheel",
                "--no-index", "--no-build-isolation", "--no-deps",
                "--wheel-dir", str(destination), str(staged),
                env=env,
            )
            wheel = destination / WHEEL
            if not wheel.is_file():
                deny("CANONICAL_WHEEL_NOT_BUILT")
            wheel_audit(wheel, staged)
            wheel_paths.append(wheel)
        raw = [x.read_bytes() for x in wheel_paths]
        if raw[0] != raw[1]:
            deny("TWO_WHEEL_BYTES_DIFFER")
        digest = hashlib.sha256(raw[0]).hexdigest()
        bundle = runner_temp / "v040-offline-installer-review-only"
        if bundle.exists() or bundle.is_symlink():
            deny("REVIEW_BUNDLE_EXISTS")
        bundle.mkdir(mode=0o700)
        shutil.copy2(wheel_paths[0], bundle / WHEEL)
        shutil.copy2(branch / "release_assets/v0.4.0/install.sh", bundle / "install.sh")
        (bundle / "SHA256SUMS").write_text(digest + "  " + WHEEL + "\n")
        (bundle / "NOT_A_RELEASE.txt").write_text(
            "UNSIGNED INSTALLER REHEARSAL ONLY; DO NOT DISTRIBUTE AS v0.4.0.\n"
            "NO real publisher/operator signature has been authenticated.\n"
            "Existing LIVE source is unchanged; no live trading authorized.\n"
        )
        negative_checks(bundle, root)
        run_bundle_installer(bundle, root)
        report = {
            "source_commit": SOURCE_SHA,
            "source_module_count": 226,
            "distribution": "multi-market-trading",
            "wheel_version": "0.4.0",
            "wheel_sha256": digest,
            "reproducible_two_builds": True,
            "installed_nine_console_scripts": True,
            "nonroot_offline_install_test": True,
            "live_source_modified": False,
            "real_publisher_signature_verified": False,
            "official_release_authorized": False,
            "report_kind": "UNSIGNED_CI_INSTALLER_REHEARSAL_ONLY",
        }
        (bundle / "REHEARSAL_ONLY.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n"
        )
        print("V040_REVIEW_ONLY_BUNDLE_READY_SHA256=" + digest)
        print("V040_NO_OFFICIAL_TAG_OR_RELEASE_SIGNING")


if __name__ == "__main__":
    main()
