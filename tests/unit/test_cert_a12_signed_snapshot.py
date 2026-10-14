"""CERT-A12 static and mock-only negative tests: no real archive access."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from deploy.runtime_a2 import a12_snapshot_verify as a12
from naseri_markets.runtime_a8_supply_chain import verify_source_lock

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "deploy/runtime_a2/a12_signed_snapshot.json"
_SOURCES = _ROOT / "deploy/runtime_a2/a12_snapshot_sources.sources"


def _lock():
    return json.loads(_MANIFEST.read_text(encoding="ascii"))


def _fixture(tmp_path, monkeypatch):
    directory = tmp_path / "sources"
    directory.mkdir()
    source = directory / "mmt-cert-a12.sources"
    source.write_bytes(_SOURCES.read_bytes())
    monkeypatch.setattr(a12, "_LOCK", _MANIFEST)
    monkeypatch.setattr(a12, "_SOURCE", source)
    monkeypatch.setattr(a12, "_SOURCES_DIR", directory)
    monkeypatch.setattr(a12, "_DEFAULT_LIST", tmp_path / "sources.list")
    return directory, source


def test_observed_three_sha256_are_frozen_and_no_authority_granted():
    a12.validate_manifest(_lock())
    pins = _lock()
    assert len(pins["release_files"]) == 3
    assert set(a12._RELEASES) == {
        "bookworm", "bookworm-updates", "bookworm-security",
    }
    for entry in pins["release_files"]:
        assert len(entry["sha256"]) == 64
        assert entry["apt_list_filename"].endswith("_InRelease")
    for key in (
        "independent_debian_publisher_custody",
        "independent_release_timestamp_witness",
        "image_reproducibly_attested",
        "rootless_gvisor_host_certified",
        "worker_execution_authorized", "broker_authorized",
        "telegram_authorized", "production_authorized",
    ):
        assert pins[key] is False
    assert pins["archival_valid_until_scope_only"] is True


def test_exact_snapshot_source_content_only_uses_signed_archival_sources(tmp_path, monkeypatch):
    directory, source = _fixture(tmp_path, monkeypatch)
    assert source.read_bytes() == a12._SOURCES_CONTENT.encode("ascii")
    a12.verify_sources()
    assert sorted(p.name for p in directory.iterdir()) == ["mmt-cert-a12.sources"]


@pytest.mark.parametrize("bad", [
    "http://snapshot.debian.org", "Check-Valid-Until: yes",
    "Signed-By: /tmp/evil.gpg", "Suites: trixie",
    "20261015T000000Z",
])
def test_source_mutation_refused_before_network(tmp_path, monkeypatch, bad):
    _, src = _fixture(tmp_path, monkeypatch)
    data = src.read_text()
    if bad.startswith("http:"):
        data = data.replace("https://snapshot.debian.org", bad)
    elif bad.startswith("Check-Valid"):
        data = data.replace("Check-Valid-Until: no", bad, 1)
    elif bad.startswith("Signed-By"):
        data = data.replace(
            "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg",
            bad, 1,
        )
    elif bad.startswith("Suites:"):
        data = data.replace("Suites: bookworm bookworm-updates", bad)
    else:
        data = data.replace("20261014T000000Z", bad, 1)
    src.write_text(data)
    with pytest.raises(a12.A12Refused, match="A12_DEBIAN_SOURCES_CHANGED"):
        a12.verify_sources()


@pytest.mark.parametrize("name", ["evil.sources", "extra.list"])
def test_extra_apt_source_refused(tmp_path, monkeypatch, name):
    directory, _ = _fixture(tmp_path, monkeypatch)
    (directory / name).write_text("deb http://example.invalid/")
    with pytest.raises(a12.A12Refused, match="A12_UNTRUSTED_ADDITIONAL_APT_SOURCE"):
        a12.verify_sources()


def test_symlink_sources_refused(tmp_path, monkeypatch):
    _, source = _fixture(tmp_path, monkeypatch)
    target = tmp_path / "target"
    target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)
    with pytest.raises(a12.A12Refused, match="A12_SYMLINK_INPUT_REFUSED"):
        a12.verify_sources()


@pytest.mark.parametrize("field,value", [
    ("schema", True),
    ("archival_valid_until_scope_only", False),
    ("independent_debian_publisher_custody", True),
    ("rootless_gvisor_host_certified", True),
    ("worker_execution_authorized", True),
    ("production_authorized", True),
    ("snapshot_timestamp", "20261015T000000Z"),
    ("base_image", "python:3.12-slim-bookworm"),
    ("debian_archive_keyring", "/tmp/keyring.gpg"),
])
def test_forged_manifest_or_permissions_rejected(field, value):
    obj = _lock()
    obj[field] = value
    with pytest.raises(a12.A12Refused):
        a12.validate_manifest(obj)


def test_modified_or_missing_release_hash_and_extra_entry_refused():
    original = _lock()
    for field, value in (
        ("sha256", "0" * 64),
        ("apt_list_filename", "debian-release-InRelease"),
        ("suite", "untrusted"),
    ):
        item = copy.deepcopy(original)
        item["release_files"][0][field] = value
        with pytest.raises(a12.A12Refused):
            a12.validate_manifest(item)
    extra = copy.deepcopy(original)
    extra["release_files"].append(extra["release_files"][0])
    with pytest.raises(a12.A12Refused):
        a12.validate_manifest(extra)


def test_lock_json_duplicate_keys_refused(tmp_path, monkeypatch):
    _, _ = _fixture(tmp_path, monkeypatch)
    injected = tmp_path / "duplicate-lock.json"
    original = _MANIFEST.read_text()
    injected.write_text(original.replace('"schema": 1,', '"schema": 1, "schema": 1,'))
    monkeypatch.setattr(a12, "_LOCK", injected)
    with pytest.raises(a12.A12Refused, match="A12_DUPLICATE_JSON_FIELD"):
        a12.verify_sources()


def _fake_gpgv(monkeypatch, *, status=b"valid", rc=0):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if status == b"valid":
            output = b"[GNUPG:] VALIDSIG " + b"A" * 40 + b" 2026\n"
        elif status == b"bad":
            output = b"[GNUPG:] BADSIG " + b"A" * 40 + b"\n"
        else:
            output = status
        return subprocess.CompletedProcess(argv, rc, output, b"")

    monkeypatch.setattr(a12.subprocess, "run", run)
    return calls


def test_actual_byte_sha_then_gpgv_signature_checked_without_shell(
    tmp_path, monkeypatch,
):
    file = tmp_path / "release_InRelease"
    file.write_bytes(b"fixed-synthetic-clearsigned-release")
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    calls = _fake_gpgv(monkeypatch)
    a12._verify_one_index(file, digest)
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:4] == ("/usr/bin/gpgv", "--keyring", str(a12._KEY), "--status-fd")
    assert argv[-1] == str(file)
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 12
    assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}


@pytest.mark.parametrize("status,rc", [
    (b"bad", 0), (b"", 0), (b"valid", 1),
    (b"[GNUPG:] REVKEYSIG\n", 0),
])
def test_missing_bad_revoked_or_failed_signature_never_accepted(
    tmp_path, monkeypatch, status, rc,
):
    file = tmp_path / "release_InRelease"
    file.write_bytes(b"synthetic")
    calls = _fake_gpgv(monkeypatch, status=status, rc=rc)
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    with pytest.raises(a12.A12Refused, match="A12_INRELEASE_SIGNATURE_NOT_VALIDATED"):
        a12._verify_one_index(file, digest)
    assert len(calls) == 1


def test_changed_index_refused_before_any_signature_call(tmp_path, monkeypatch):
    file = tmp_path / "release_InRelease"
    file.write_bytes(b"modified")
    monkeypatch.setattr(
        a12.subprocess, "run",
        lambda *a, **kw: pytest.fail("GPGV_CANNOT_RUN_AFTER_BAD_SHA"),
    )
    with pytest.raises(a12.A12Refused, match="A12_INRELEASE_BYTES_DIFFER_FROM_PIN"):
        a12._verify_one_index(file, "0" * 64)


def test_old_worker_source_hash_and_dispatch_authority_remain_unchanged():
    lock = verify_source_lock(
        _ROOT, _ROOT / "deploy/runtime_a2/a8_source_lock.json",
    )
    assert lock.checked_files == 3
    assert not lock.worker_execution_authorized
