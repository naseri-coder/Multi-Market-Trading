"""R35 offline wheel preflight checks: no nonproduction install is executed."""
from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile

import pytest

from scripts import mmt_r35_offline_preview_install_v1 as r35


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def wheel(tmp_path, override=None):
    path = tmp_path / r35.FILE_NAME
    names = {
        "naseri_markets/platform_cli.py": "# inert public module\n",
        r35.DIST + "METADATA": (
            "Metadata-Version: 2.4\nName: multi-market-trading\n"
            "Version: 0.4.0rc1\nRequires-Python: >=3.12,<3.13\n"
            'Requires-Dist: python-telegram-bot==22.8; extra == "telegram-admin"\n'
        ),
        r35.DIST + "entry_points.txt": (
            "[console_scripts]\n"
            "naseri-markets = naseri_markets.platform_cli:main\n"
            "naseri-paper-demo = naseri_markets.paper_demo_cli_v1:main\n"
        ),
    }
    if override is not None:
        names.update(override)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in names.items():
            z.writestr(name, data)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_posixpath_sha_and_offline_preflight_is_readonly(tmp_path, monkeypatch):
    monkeypatch.setattr(r35, "_gate", lambda **_: None)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source, digest = wheel(private)
    destination = private / "new-install"
    answer = r35.check(wheel=source, sha256=digest, destination=destination)
    assert answer["verdict"] == "R35_OFFLINE_WHEEL_PREFLIGHT_PASS"
    assert answer["writes_performed"] is False
    assert answer["production_install_allowed"] is False
    assert answer["live_authorized"] is False
    assert not destination.exists()
    with pytest.raises(r35.R35Refused, match="SHA256_MISMATCH"):
        r35.check(wheel=source, sha256="0" * 64, destination=destination)


def test_existing_target_world_readable_parent_and_path_escape_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(r35, "_gate", lambda **_: None)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source, digest = wheel(private)
    with pytest.raises(r35.R35Refused, match="NEW_ABSOLUTE"):
        r35.check(wheel=source, sha256=digest, destination=private)
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(r35.R35Refused, match="PRIVATE_OWNED_PARENT"):
        r35.check(wheel=source, sha256=digest, destination=public / "new")
    linked = tmp_path / "linked"
    linked.symlink_to(private, target_is_directory=True)
    with pytest.raises(r35.R35Refused, match="NEW_ABSOLUTE"):
        r35.check(wheel=source, sha256=digest, destination=linked / "new")


@pytest.mark.parametrize("bad_name", [
    "naseri_markets/../steal.py", "production_source/app/main.py",
    "naseri_markets/bad.pth", "naseri_markets/.env",
    "naseri_markets/private_nyfr_core.py", "naseri_markets/r0_engine.py",
])
def test_forbidden_wheel_members_rejected(tmp_path, bad_name):
    source, _ = wheel(tmp_path, {bad_name: "hello"})
    with pytest.raises(r35.R35Refused, match="UNSAFE_WHEEL_MEMBER"):
        r35._inspect_wheel(source.read_bytes())


def test_symlink_member_rejected(tmp_path):
    f, _ = wheel(tmp_path)
    raw = io.BytesIO()
    with zipfile.ZipFile(f, "r") as original:
        with zipfile.ZipFile(raw, "w") as rewritten:
            for item in original.infolist():
                rewritten.writestr(item, original.read(item))
            link = zipfile.ZipInfo("naseri_markets/alias.py")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            rewritten.writestr(link, "../../../etc/passwd")
    with pytest.raises(r35.R35Refused, match="UNSAFE_WHEEL_MEMBER"):
        r35._inspect_wheel(raw.getvalue())


def test_declared_required_dependency_refused(tmp_path):
    f, _ = wheel(tmp_path, {r35.DIST + "METADATA": (
        "Metadata-Version: 2.4\nName: multi-market-trading\nVersion: 0.4.0rc1\n"
        "Requires-Dist: requests>=2\n"
    )})
    with pytest.raises(r35.R35Refused, match="DISTRIBUTION_OR_DEPENDENCY"):
        r35._inspect_wheel(f.read_bytes())


def test_root_install_denied_before_any_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(r35.sys, "version_info", (3, 12, 3))
    monkeypatch.setattr(r35.os, "geteuid", lambda: 0)
    with pytest.raises(r35.R35Refused, match="NONROOT_INSTALL_REQUIRED"):
        r35._gate(install=True, ack=True)
    assert list(tmp_path.iterdir()) == []


def test_production_and_missing_ack_fail_closed(monkeypatch):
    monkeypatch.setattr(r35.sys, "version_info", (3, 12, 3))
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(r35.R35Refused, match="NONPRODUCTION"):
        r35._gate(install=False, ack=False)
    monkeypatch.delenv("MMT_PRODUCTION")
    with pytest.raises(r35.R35Refused, match="ACK_REQUIRED"):
        r35._gate(install=True, ack=False)


def test_no_external_network_calls_in_install_procedure(tmp_path, monkeypatch):
    """Check-only never imports pip and never invokes subprocesses."""
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source, digest = wheel(private)
    monkeypatch.setattr(r35, "_gate", lambda **_: None)

    def must_not_run(*args, **kwargs):
        raise AssertionError("No subprocess expected in check-only")

    monkeypatch.setattr(r35.subprocess, "run", must_not_run)
    result = r35.check(wheel=source, sha256=digest,
                       destination=private / "fresh")
    assert result["writes_performed"] is False
    assert not (private / "fresh").exists()


def test_mock_isolated_install_only_pip_no_index_and_disabled_cli(
    tmp_path, monkeypatch,
):
    """Model installation argv, never execute pip, venv or third-party code."""
    from types import SimpleNamespace

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source, digest = wheel(private)
    dest = private / "new"
    monkeypatch.setattr(r35.os, "geteuid", lambda: private.stat().st_uid)
    monkeypatch.setattr(r35, "_gate", lambda **_: None)

    def fake_venv_create(self, folder):
        (folder / "bin").mkdir(parents=True)
        (folder / "bin/python").touch()

    monkeypatch.setattr(r35.venv.EnvBuilder, "create", fake_venv_create)
    commands = []

    def fake_run(args, **kwargs):
        commands.append((args, kwargs))
        if args[-1] == "--check" and args[0].endswith("naseri-markets"):
            out = json.dumps({
                "distribution": r35.NAME,
                "version": r35.VERSION,
                "mode": "OFFLINE_PREVIEW",
                "network_enabled": False,
                "orders_enabled": False,
                "telegram_enabled": False,
                "legacy_database_attached": False,
            })
        else:
            out = ""
        return SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(r35.subprocess, "run", fake_run)
    result = r35.install(wheel=source, sha256=digest, destination=dest, ack=True)
    assert result["verdict"] == "R35_INSTALLED_OFFLINE_PREVIEW_PASS_RELEASE_DENIED"
    assert (dest / r35.FILE_NAME).read_bytes() == source.read_bytes()
    assert (dest / "offline-install-report.json").stat().st_mode & 0o077 == 0
    assert len(commands) == 3
    pip_argv, pip_args = commands[0]
    assert "--no-index" in pip_argv and "--no-deps" in pip_argv
    assert "--no-cache-dir" in pip_argv
    assert pip_args["env"]["PIP_NO_INDEX"] == "1"
    assert "PYTHONPATH" not in pip_args["env"]
    assert commands[1][0][-2:] == ["pip", "check"]
    assert commands[2][0][-1] == "--check"
    assert not any("brooks" in " ".join(c[0]).lower() for c in commands)
