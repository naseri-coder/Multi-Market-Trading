"""CERT-A11 fixed signed-APT archive byte closure regression (no real downloads)."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from deploy.runtime_a2 import a11_apt_closure as a11
from naseri_markets.runtime_a8_supply_chain import verify_source_lock

_ROOT = Path(__file__).resolve().parents[2]
_LOCK = _ROOT / "deploy/runtime_a2/a11_apt_closure.json"
_HEAD = "47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872"


def _real_lock():
    return json.loads(_LOCK.read_text(encoding="ascii"))


def _fake_cache(tmp_path, monkeypatch):
    root = tmp_path / "archives"
    root.mkdir()
    (root / "partial").mkdir()
    (root / "lock").touch()
    debs = {
        "nodejs": (b"deb-package-nodejs-fixed-bytes", "18.20.4+dfsg-1~deb12u3", "amd64"),
        "npm": (b"deb-package-npm-fixed-bytes", "9.2.0~ds1-1", "all"),
    }
    values = {}
    for name, (bytes_data, version, arch) in debs.items():
        p = root / f"{name}_{version}_{arch}.deb"
        p.write_bytes(bytes_data)
        values[str(p)] = {"Package": name, "Version": version, "Architecture": arch}

    def fake_call(args, **kwargs):
        assert args[0] == "/usr/bin/dpkg-deb"
        assert args[1] == "--field"
        assert args[2] in values
        assert args[3] in {"Package", "Version", "Architecture"}
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(
            args, 0, (values[args[2]][args[3]] + "\n").encode(), b"",
        )

    monkeypatch.setattr(a11, "_ARCHIVES", root)
    monkeypatch.setattr(a11.subprocess, "run", fake_call)
    return root, values


def test_repository_exact_docker_source_lock_and_debian_archive_count():
    source = verify_source_lock(
        _ROOT, _ROOT / "deploy/runtime_a2/a8_source_lock.json",
    )
    assert source.checked_files == 3
    manifest = _real_lock()
    assert len(manifest["packages"]) == 372
    assert manifest["closure_sha256"] == _HEAD
    assert {"nodejs", "npm"}.issubset({x["package"] for x in manifest["packages"]})
    assert manifest["apt_snapshot_pinned"] is False
    assert manifest["debian_publisher_independently_verified"] is False
    assert manifest["worker_execution_authorized"] is False
    assert manifest["host_certified"] is False
    assert manifest["production_authorized"] is False
    a11.validate_lock(manifest, manifest["packages"])


def test_exact_observed_archive_bytes_and_canonical_hash(monkeypatch, tmp_path):
    root, _ = _fake_cache(tmp_path, monkeypatch)
    entries = a11.inspect_archives(root)
    assert len(entries) == 2
    assert [x["package"] for x in entries] == ["nodejs", "npm"]
    assert entries[0]["sha256"] == hashlib.sha256(
        b"deb-package-nodejs-fixed-bytes",
    ).hexdigest()
    manifest = a11.candidate_lock(entries)
    a11.validate_lock(manifest, entries)
    assert manifest["apt_snapshot_pinned"] is False


@pytest.mark.parametrize("field,replacement", [
    ("closure_sha256", "f" * 64),
    ("root_packages", ["npm"]),
    ("schema", True),
    ("audience", "FORGED_PRODUCTION_RELEASE"),
    ("apt_snapshot_pinned", True),
    ("debian_publisher_independently_verified", True),
    ("host_certified", True),
    ("worker_execution_authorized", True),
    ("production_authorized", True),
])
def test_forged_release_or_closure_metadata_denied(field, replacement):
    manifest = _real_lock()
    manifest[field] = replacement
    with pytest.raises(a11.A11Refused):
        a11.validate_lock(manifest, manifest["packages"])


@pytest.mark.parametrize("update", [
    lambda p: p.pop(),
    lambda p: p[0].update(sha256="f" * 64),
    lambda p: p[0].update(version="99.0.0"),
    lambda p: p[0].update(architecture="arm64"),
    lambda p: p[0].update(untrusted=True),
    lambda p: p.append(copy.deepcopy(p[0])),
])
def test_missing_modified_duplicate_or_extra_package_denied(update):
    manifest = _real_lock()
    update(manifest["packages"])
    with pytest.raises(a11.A11Refused):
        a11.validate_lock(manifest, manifest["packages"])


def test_same_lock_with_modified_observed_bytes_denied():
    manifest = _real_lock()
    observed = copy.deepcopy(manifest["packages"])
    observed[0]["sha256"] = "0" * 64
    with pytest.raises(a11.A11Refused, match="A11_APT_ARCHIVE_HASH_OR_CLOSURE_DRIFT"):
        a11.validate_lock(manifest, observed)


def test_truncated_or_oversized_synthetic_file_refused(monkeypatch, tmp_path):
    root, values = _fake_cache(tmp_path, monkeypatch)
    first = next(iter(values))
    Path(first).write_bytes(b"")
    with pytest.raises(a11.A11Refused, match="A11_ARCHIVE_SIZE_OR_TYPE_REFUSED"):
        a11.inspect_archives(root)


def test_symlink_or_unknown_extra_archive_refused(monkeypatch, tmp_path):
    root, _ = _fake_cache(tmp_path, monkeypatch)
    target = next(root.glob("*.deb"))
    link = root / "new-deb.deb"
    link.symlink_to(target)
    with pytest.raises(a11.A11Refused, match="A11_SYMLINK_ARCHIVE_REFUSED"):
        a11.inspect_archives(root)
    link.unlink()
    (root / "evil.tar").write_bytes(b"not a .deb")
    with pytest.raises(a11.A11Refused, match="A11_UNKNOWN_APT_CACHE_FILE"):
        a11.inspect_archives(root)


def test_duplicate_debian_package_name_denied(monkeypatch, tmp_path):
    root, fields = _fake_cache(tmp_path, monkeypatch)
    original = next(root.glob("nodejs_*.deb"))
    dup = root / "nodejs_999_amd64.deb"
    dup.write_bytes(original.read_bytes())
    fields[str(dup)] = fields[str(original)]
    with pytest.raises(a11.A11Refused, match="A11_DUPLICATE_PACKAGE_ARCHIVE"):
        a11.inspect_archives(root)


def test_no_snapshot_or_run_permission_granted_and_safe_cli_only():
    lock = _real_lock()
    assert lock["apt_snapshot_pinned"] is False
    assert lock["host_certified"] is False
    assert lock["worker_execution_authorized"] is False
    assert a11._LOCK_PATH == Path("/opt/mmt/a11_apt_closure.json")


def test_source_archive_parser_and_status_validation_fail_closed():
    with pytest.raises(a11.A11Refused):
        a11.validate_lock({"packages": []}, [])
    with pytest.raises(a11.A11Refused, match="A11_ROOT_PACKAGES_MISSING"):
        observation = a11.candidate_lock([{
            "package": "other", "version": "1.0", "architecture": "all",
            "sha256": "a" * 64,
        }])
        a11.validate_lock(observation, observation["packages"])
