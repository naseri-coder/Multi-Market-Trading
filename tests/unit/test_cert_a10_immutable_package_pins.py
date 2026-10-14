"""CERT-A10 offline-only artifact pin contract tests; never execute Docker."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from naseri_markets.cert_a10_immutable_package_pins import (
    CertA10Refused,
    review_archive_pins,
)

_REPO = Path(__file__).resolve().parents[2]
_FILES = (
    "deploy/runtime_a2/a10_archive_pins.json",
    "deploy/runtime_a2/Dockerfile",
    "deploy/runtime_a2/a10_wasmtime.lock",
)


def _fixture(tmp_path):
    root = tmp_path / "review"
    for relative in _FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_REPO / relative, target)
    return root


def _change(root, path, before, after):
    f = root / path
    original = f.read_text()
    assert before in original
    f.write_text(original.replace(before, after, 1))


def test_real_repository_archive_pins_are_review_only():
    result = review_archive_pins(_REPO)
    assert result.pinned_artifact_entries == 3
    assert result.status == "CERT_A10_BASE_NPM_WHEEL_BYTE_PINS_AUDITED_APT_OPEN"
    assert not result.actual_apt_package_sha_verified
    assert not result.independent_registry_signature_verified
    assert not result.verified_provenance_custody
    assert not result.gvisor_host_certified
    assert not result.arbitrary_worker_execution_authorized
    assert not result.broker_authorized
    assert not result.telegram_authorized
    assert not result.production_authorized


def test_fixture_matching_expected_pins_passes(tmp_path):
    root = _fixture(tmp_path)
    assert review_archive_pins(root).pinned_artifact_entries == 3


@pytest.mark.parametrize(("file", "needle", "mutation"), [
    (_FILES[1], "FROM python:3.12-slim-bookworm@sha256:", "FROM python:3.12-slim-bookworm #"),
    (_FILES[1], "8e5d6f6733c38a72ebf5e52ddc9feded5e8580d130f508ef04f772b33f4a7d00c3e357d0ac2d98e2f290762694a454f86d795bd511e12e9a7cc2d9ba3394e04b", "0" * 128),
    (_FILES[1], "--require-hashes", "--no-deps"),
    (_FILES[1], "--offline --no-audit", "--online --no-audit"),
    (_FILES[2], "94f0288f9e1c33924995a72bb769f4c4e2885002391589dd6992cdaa35d1990a", "f" * 64),
])
def test_missing_or_forged_build_pins_refused(tmp_path, file, needle, mutation):
    root = _fixture(tmp_path)
    _change(root, file, needle, mutation)
    with pytest.raises(CertA10Refused):
        review_archive_pins(root)


@pytest.mark.parametrize(("field", "replacement"), [
    ("execution_authorized", True),
    ("independent_publisher_verified", True),
    ("host_isolation_certified", True),
    ("apt_snapshot_pinned", True),
    ("base_image", "python:3.12-slim-bookworm"),
    ("schema", True),
])
def test_manifest_mutation_or_premature_trust_refused(tmp_path, field, replacement):
    root = _fixture(tmp_path)
    file = root / _FILES[0]
    data = json.loads(file.read_text())
    data[field] = replacement
    file.write_text(json.dumps(data))
    with pytest.raises(CertA10Refused):
        review_archive_pins(root)


def test_duplicate_keys_and_untrusted_extra_properties_refused(tmp_path):
    root = _fixture(tmp_path)
    file = root / _FILES[0]
    original = file.read_text()
    file.write_text(original.replace('"schema": 1,', '"schema": 1, "schema": 1,'))
    with pytest.raises(CertA10Refused, match="CERT_A10_DUPLICATE_JSON_FIELD"):
        review_archive_pins(root)
    file.write_text(original.replace('"schema": 1,', '"schema": 1, "untrusted": true,'))
    with pytest.raises(CertA10Refused):
        review_archive_pins(root)


def test_file_symlink_and_missing_refused(tmp_path):
    root = _fixture(tmp_path)
    f = root / _FILES[2]
    saved = tmp_path / "saved"
    shutil.copyfile(f, saved)
    f.unlink()
    f.symlink_to(saved)
    with pytest.raises(CertA10Refused, match="CERT_A10_SYMLINK_NOT_ALLOWED"):
        review_archive_pins(root)
    f.unlink()
    with pytest.raises(CertA10Refused, match="CERT_A10_PIN_FILE_MISSING"):
        review_archive_pins(root)


def test_probe_never_executes_commands(tmp_path, monkeypatch):
    def forbid(*args, **kwargs):
        pytest.fail("CERT_A10_MUST_REMAIN_NO_SUBPROCESS")
    monkeypatch.setattr(subprocess, "run", forbid)
    monkeypatch.setattr(subprocess, "Popen", forbid)
    root = _fixture(tmp_path)
    assert not review_archive_pins(root).arbitrary_worker_execution_authorized


def test_invalid_root_rejected():
    with pytest.raises(CertA10Refused):
        review_archive_pins(None)
