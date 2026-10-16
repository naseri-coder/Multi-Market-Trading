"""R40 read-only installed synthetic PAPER negative and positive contracts.

Synthetic scratch files and a fake installed-distribution record are used in
unit tests; no actual installer, broker, signal, strategy or network is run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from naseri_markets import installed_paper_acceptance_r40_v1 as r40

REAL_GATE = r40._gate


@pytest.fixture
def fixture(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    # Only isolate test gate; real nonroot Python3.12 acceptance stays pending.
    def allow(*, operator_ack, writers_stopped):
        if operator_ack is not True or writers_stopped is not True:
            raise r40.R40Refused("R40_TEST_ACK_REQUIRED")
    monkeypatch.setattr(r40, "_gate", allow)
    home = tmp_path / "owner"
    home.mkdir(mode=0o700)
    workspace = home / "journey"
    workspace.mkdir(mode=0o700)
    (workspace / "pilot").mkdir(mode=0o700)
    for name in r40._FILES:
        f = workspace / name
        f.write_bytes(("sqlite unit evidence " + name).encode())
        f.chmod(0o600)

    wheel_root = home / "wheel-root"
    installed = wheel_root / r40._R39_RELATIVE
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"# installed pinned R39 synthetic source fixture\n")
    fingerprint = hashlib.sha256(installed.read_bytes()).hexdigest()

    class FakeDistribution:
        version = "0.4.0rc1"
        files = [r40._R39_RELATIVE]

        def __init__(self):
            self.direct_url = None

        def read_text(self, name):
            return self.direct_url if name == "direct_url.json" else None

        def locate_file(self, name):
            assert name == r40._R39_RELATIVE
            return installed

    dist = FakeDistribution()
    monkeypatch.setattr(r40, "distribution", lambda _: dist)
    monkeypatch.setattr(r40.r39, "__file__", str(installed))
    calls = []

    def mock_inspect(path, *, dry_run_signals, operator_ack, all_writers_stopped):
        calls.append((path, dry_run_signals, operator_ack, all_writers_stopped))
        return {
            "verdict": "R39_READONLY_PAPER_REOPEN_PASS_RELEASE_DENIED",
            "status": "DONE",
            "report_sha256": "a" * 64,
            "reliability_sha256": "b" * 64,
            "recovery_decision_sha256": "c" * 64,
            "files_written": False,
            "auto_retry_authorized": False,
            "live_authorized": False,
            "public_release_authorized": False,
        }

    monkeypatch.setattr(r40.r39, "inspect", mock_inspect)
    opts = {
        "workspace": workspace,
        "expected_r39_module_sha256": fingerprint,
        "dry_run_signals": True,
        "operator_ack": True,
        "all_writers_stopped": True,
    }
    return SimpleNamespace(
        opts=opts, workspace=workspace, dist=dist, installed=installed,
        calls=calls, stub=mock_inspect, monkeypatch=monkeypatch,
    )


def test_installed_r39_pinned_six_ledger_readonly_pass(fixture):
    result = r40.inspect(**fixture.opts)
    assert result["verdict"].startswith("R40_INSTALLED_SYNTHETIC_PAPER_")
    assert result["stage39_reopen_checks"] == 2
    assert len(result["ledger_sha256"]) == 6
    assert result["independent_brooks_verification"] is False
    assert result["brooks_full_core_verdict"] == "DEFERRED_R27_FROZEN"
    for flag in ("real_market_data_used", "broker_order_sent", "telegram_sent",
                 "auto_retry_authorized", "production_release_authorized",
                 "live_authorized", "files_written"):
        assert result[flag] is False
    assert len(fixture.calls) == 2


def test_no_sqlite_bytes_modified(fixture):
    original = {k: (fixture.workspace / k).read_bytes() for k in r40._FILES}
    first = r40.inspect(**fixture.opts)
    second = r40.inspect(**fixture.opts)
    assert first == second
    assert original == {k: (fixture.workspace / k).read_bytes()
                        for k in r40._FILES}


def test_wrong_independently_supplied_r39_pin_denied(fixture):
    fixture.opts["expected_r39_module_sha256"] = "0" * 64
    with pytest.raises(r40.R40Refused, match="INSTALLED_MODULE_SHA256_MISMATCH"):
        r40.inspect(**fixture.opts)
    assert not fixture.calls


def test_invalid_pin_not_taken_from_installed_package(fixture):
    fixture.opts["expected_r39_module_sha256"] = ""
    with pytest.raises(r40.R40Refused, match="INDEPENDENT_R39_MODULE_PIN"):
        r40.inspect(**fixture.opts)


def test_editable_install_is_refused(fixture):
    fixture.dist.direct_url = json.dumps({"dir_info": {"editable": True}})
    with pytest.raises(r40.R40Refused, match="EDITABLE_SOURCE_INSTALL"):
        r40.inspect(**fixture.opts)


@pytest.mark.parametrize("payload", ["[]", "null", '{"dir_info":[]}', "{"])
def test_invalid_editable_metadata_is_refused(fixture, payload):
    fixture.dist.direct_url = payload
    with pytest.raises(r40.R40Refused, match="DIRECT_URL_INVALID"):
        r40.inspect(**fixture.opts)


def test_wrong_installed_preview_version_refused(fixture):
    fixture.dist.version = "0.4.0"
    with pytest.raises(r40.R40Refused, match="PREVIEW_VERSION_MISMATCH"):
        r40.inspect(**fixture.opts)


def test_installed_missing_r39_module_refused(fixture):
    fixture.dist.files = []
    with pytest.raises(r40.R40Refused, match="INSTALLED_R39_MODULE_MISSING"):
        r40.inspect(**fixture.opts)


def test_symlink_loaded_installed_module_refused(fixture):
    other = fixture.installed.parent / "source.py"
    fixture.installed.rename(other)
    fixture.installed.symlink_to(other)
    with pytest.raises(r40.R40Refused, match="UNTRUSTED_INSTALLED_MODULE_LOCATION"):
        r40.inspect(**fixture.opts)


def test_nonprivate_workspace_refused(fixture):
    fixture.workspace.chmod(0o755)
    with pytest.raises(r40.R40Refused, match="PRIVATE_WORKSPACE_REQUIRED"):
        r40.inspect(**fixture.opts)


def test_missing_ledger_denied(fixture):
    (fixture.workspace / "pilot" / "effects.sqlite").unlink()
    with pytest.raises(r40.R40Refused, match="EVIDENCE_FILE_UNREADABLE"):
        r40.inspect(**fixture.opts)
    assert not fixture.calls


def test_ledger_symlink_denied(fixture):
    ledger = fixture.workspace / "pilot" / "runtime.sqlite"
    source = fixture.workspace / "old.sqlite"
    ledger.rename(source)
    ledger.symlink_to(source)
    with pytest.raises(r40.R40Refused, match="ABSOLUTE_UNLINKED_REGULAR_FILE"):
        r40.inspect(**fixture.opts)


def test_ledger_hardlink_denied(fixture):
    name = fixture.workspace / "pilot" / "paper.sqlite"
    os.link(name, fixture.workspace / "copy.sqlite")
    with pytest.raises(r40.R40Refused, match="UNSAFE_EVIDENCE_FILE"):
        r40.inspect(**fixture.opts)


def test_ledger_change_during_reopen_denied(fixture):
    original_inspect = fixture.stub

    def changed(*args, **kwargs):
        answer = original_inspect(*args, **kwargs)
        (fixture.workspace / "pilot" / "paper.sqlite").write_bytes(b"changed")
        return answer

    fixture.monkeypatch.setattr(r40.r39, "inspect", changed)
    with pytest.raises(r40.R40Refused, match="EVIDENCE_DRIFT"):
        r40.inspect(**fixture.opts)


def test_r39_report_consistency_drift_denied(fixture):
    calls = [0]

    def mismatch(*args, **kwargs):
        calls[0] += 1
        answer = fixture.stub(*args, **kwargs)
        if calls[0] == 2:
            answer["report_sha256"] = "d" * 64
        return answer

    fixture.monkeypatch.setattr(r40.r39, "inspect", mismatch)
    with pytest.raises(r40.R40Refused, match="REOPEN_OR_EVIDENCE_DRIFT"):
        r40.inspect(**fixture.opts)


def test_r39_quarantined_state_is_never_accepted(fixture):
    def quarantined(*_, **__):
        raise r40.r39.PaperAuthorityRefused("R39_UNCERTAIN_JOB_MANUAL_RECOVERY_ONLY")

    fixture.monkeypatch.setattr(r40.r39, "inspect", quarantined)
    with pytest.raises(r40.r39.PaperAuthorityRefused):
        r40.inspect(**fixture.opts)


def test_unsupported_live_permission_from_r39_denied(fixture):
    def unsafe(*args, **kwargs):
        answer = fixture.stub(*args, **kwargs)
        answer["live_authorized"] = True
        return answer

    fixture.monkeypatch.setattr(r40.r39, "inspect", unsafe)
    with pytest.raises(r40.R40Refused, match="REOPEN_OR_EVIDENCE_DRIFT"):
        r40.inspect(**fixture.opts)


def test_missing_operator_ack_denied(fixture):
    fixture.opts["operator_ack"] = False
    with pytest.raises(r40.R40Refused, match="TEST_ACK"):
        r40.inspect(**fixture.opts)


def test_missing_stop_writers_ack_denied(fixture):
    fixture.opts["all_writers_stopped"] = False
    with pytest.raises(r40.R40Refused, match="TEST_ACK"):
        r40.inspect(**fixture.opts)


def test_cli_missing_ack_no_result_granted(fixture, capsys):
    assert r40.main([
        "--workspace", str(fixture.workspace),
        "--expected-r39-module-sha256", fixture.opts["expected_r39_module_sha256"],
    ]) == 2
    assert "R40_PAPER_ACCEPTANCE_REFUSED" in capsys.readouterr().err


@pytest.mark.parametrize("setting", ["0", "1", "yes", ""])
def test_real_gate_any_explicit_production_variable_denied(
    monkeypatch, setting,
):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    monkeypatch.setattr(r40.os, "geteuid", lambda: 12345)
    monkeypatch.setattr(r40.sys, "version_info", (3, 12, 3))
    with pytest.raises(r40.R40Refused, match="NONROOT_PY312_STOPPED"):
        REAL_GATE(operator_ack=True, writers_stopped=True)


def test_real_gate_root_denied(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(r40.os, "geteuid", lambda: 0)
    monkeypatch.setattr(r40.sys, "version_info", (3, 12, 3))
    with pytest.raises(r40.R40Refused, match="NONROOT_PY312_STOPPED"):
        REAL_GATE(operator_ack=True, writers_stopped=True)


def test_real_gate_wrong_python_version_denied(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(r40.os, "geteuid", lambda: 12345)
    monkeypatch.setattr(r40.sys, "version_info", (3, 13, 5))
    with pytest.raises(r40.R40Refused, match="NONROOT_PY312_STOPPED"):
        REAL_GATE(operator_ack=True, writers_stopped=True)


def test_real_gate_valid_only_when_explicitly_isolated(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(r40.os, "geteuid", lambda: 12345)
    monkeypatch.setattr(r40.sys, "version_info", (3, 12, 3))
    assert REAL_GATE(operator_ack=True, writers_stopped=True) is None
