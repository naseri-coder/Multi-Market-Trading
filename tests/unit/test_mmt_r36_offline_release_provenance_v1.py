"""R36: read-only Git↔Wheel byte audit and denial regressions (no pip or network)."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts import mmt_r36_offline_release_provenance_v1 as r36
from scripts.mmt_r35_offline_preview_install_v1 import DIST, FILE_NAME


@pytest.fixture(autouse=True)
def safe_test_env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(r36.sys, "version_info", (3, 12, 3))


def _run(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _source_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "naseri_markets").mkdir(parents=True)
    (repo / "platform_release").mkdir()
    (repo / "naseri_markets" / "__init__.py").write_text(
        '"""inert"""\n', encoding="utf-8"
    )
    (repo / "naseri_markets" / "platform_cli.py").write_text(
        "def main():\n    return 0\n", encoding="utf-8"
    )
    (repo / "platform_release" / "pyproject.toml").write_text(
        '[project]\nname = "multi-market-trading"\n'
        'version = "0.4.0rc1"\ndependencies = []\n'
        '[project.scripts]\n'
        'naseri-markets = "naseri_markets.platform_cli:main"\n'
        'naseri-paper-demo = "naseri_markets.paper_demo_cli_v1:main"\n',
        encoding="utf-8",
    )
    (repo / "platform_release" / "README.md").write_text(
        "Synthetic fixture.\n", encoding="utf-8"
    )
    _run(repo, "init", "-q")
    _run(repo, "add", "naseri_markets", "platform_release")
    _run(repo, "-c", "user.name=R36-Test", "-c",
         "user.email=r36-test@example.invalid", "commit", "-qm", "test")
    return repo, _run(repo, "rev-parse", "HEAD")


def _record(members: dict[str, bytes]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    for name, data in members.items():
        digest = base64.urlsafe_b64encode(
            hashlib.sha256(data).digest()
        ).decode().rstrip("=")
        writer.writerow([name, "sha256=" + digest, str(len(data))])
    writer.writerow([DIST + "RECORD", "", ""])
    return out.getvalue().encode()


def _make_wheel(
    repo: Path, out_dir: Path, *, tamper_module: bool = False,
    forged_record: bool = False, extra: str | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> Path:
    out_dir.mkdir()
    modules = {
        f"naseri_markets/{p.name}": p.read_bytes()
        for p in (repo / "naseri_markets").glob("*.py")
    }
    if tamper_module:
        modules["naseri_markets/platform_cli.py"] = b"def main(): return 2\n"
    scripts = (
        "[console_scripts]\n"
        "naseri-markets = naseri_markets.platform_cli:main\n"
        "naseri-paper-demo = naseri_markets.paper_demo_cli_v1:main\n"
    )
    members = {
        **modules,
        DIST + "METADATA": (
            b"Metadata-Version: 2.4\nName: multi-market-trading\n"
            b"Version: 0.4.0rc1\n"
        ),
        DIST + "WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: r36-fixture\n"
            b"Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        DIST + "entry_points.txt": scripts.encode(),
        DIST + "top_level.txt": b"naseri_markets\n",
    }
    if extra:
        members[extra] = b"unreviewed"
    members[DIST + "RECORD"] = _record(members)
    if forged_record:
        members[DIST + "RECORD"] = members[DIST + "RECORD"].replace(
            b"sha256=", b"sha256=X", 1
        )
    wheel = out_dir / FILE_NAME
    with zipfile.ZipFile(wheel, "w", compression=compression) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return wheel


def _audit(repo: Path, commit: str, wheel: Path, **extra):
    return r36.audit(
        repository=repo, wheel=wheel,
        expected_wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        expected_source_commit=commit, **extra,
    )


def test_genuine_local_git_clean_and_record_pass(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out")
    report = _audit(repo, commit, wheel)
    assert report["verdict"] == "R36_LOCAL_SOURCE_WHEEL_EQUIVALENCE_PASS_RELEASE_DENIED"
    assert report["wheel_record_verified"] is True
    assert report["source_module_bytes_match"] is True
    assert report["public_modules_verified"] == 2
    assert report["files_written"] is False
    assert report["publisher_signature_verified"] is False
    assert report["production_release_authorized"] is False


def test_wrong_external_wheel_pin_denied(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out")
    with pytest.raises(r36.R36Refused, match="BOUNDED_R35_WHEEL_CHECK_REFUSED"):
        r36.audit(
            repository=repo, wheel=wheel,
            expected_wheel_sha256="0" * 64,
            expected_source_commit=commit,
        )


def test_wrong_git_commit_pin_denied(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out")
    with pytest.raises(r36.R36Refused, match="SOURCE_COMMIT_PIN_MISMATCH"):
        r36.audit(
            repository=repo, wheel=wheel,
            expected_wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
            expected_source_commit="0" * 40,
        )
    assert len(commit) == 40


@pytest.mark.parametrize("modified", ["tracked", "untracked"])
def test_dirty_or_untracked_public_source_denied(tmp_path, modified):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out")
    if modified == "tracked":
        (repo / "naseri_markets/platform_cli.py").write_text("def main(): return 42\n")
    else:
        (repo / "naseri_markets/private_untracked.py").write_text("secret\n")
    with pytest.raises(r36.R36Refused, match="PUBLIC_SOURCE_NOT_CLEAN"):
        _audit(repo, commit, wheel)


def test_tampered_module_even_with_forged_valid_record_denied(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out", tamper_module=True)
    with pytest.raises(r36.R36Refused, match="WHEEL_MODULE_BYTES_DIFFER"):
        _audit(repo, commit, wheel)


def test_corrupted_record_denied(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out", forged_record=True)
    with pytest.raises(r36.R36Refused, match="RECORD_HASH_OR_SIZE_MISMATCH"):
        _audit(repo, commit, wheel)


def test_unreviewed_dist_info_entry_denied(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(
        repo, tmp_path / "out", extra=DIST + "UNREVIEWED_METADATA"
    )
    with pytest.raises(r36.R36Refused, match="WHEEL_SOURCE_MEMBER_SET_MISMATCH"):
        _audit(repo, commit, wheel)


def test_second_zip_payload_identical_but_bytes_differ(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "first", compression=zipfile.ZIP_STORED)
    compare = _make_wheel(repo, tmp_path / "second", compression=zipfile.ZIP_DEFLATED)
    report = _audit(repo, commit, wheel, compare_wheel=compare)
    assert report["second_wheel_same_payload"] is True
    assert report["second_wheel_identical_bytes"] is False
    assert report["verdict"] == (
        "R36_SECOND_WHEEL_PAYLOAD_EQUAL_BYTES_DIFFER_RELEASE_DENIED"
    )


def test_second_archive_changed_payload_rejected(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "first")
    compare = _make_wheel(repo, tmp_path / "second", tamper_module=True)
    with pytest.raises(r36.R36Refused, match="WHEEL_MODULE_BYTES_DIFFER"):
        _audit(repo, commit, wheel, compare_wheel=compare)


def test_readonly_audit_leaves_source_and_wheel_unchanged(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    old_status = _run(repo, "status", "--porcelain")
    report = _audit(repo, commit, wheel)
    assert report["files_written"] is False
    assert _run(repo, "status", "--porcelain") == old_status == ""
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == digest


def test_production_environment_denied(tmp_path, monkeypatch):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(r36.R36Refused, match="R36_OFFLINE_PY312_ONLY"):
        _audit(repo, commit, wheel)


def test_no_spurious_git_side_effects_or_pycache(tmp_path):
    repo, commit = _source_repo(tmp_path)
    wheel = _make_wheel(repo, tmp_path / "out")
    source_count = len(list((repo / "naseri_markets").iterdir()))
    assert _audit(repo, commit, wheel)["public_modules_verified"] == source_count
    assert not (repo / "naseri_markets" / "__pycache__").exists()
