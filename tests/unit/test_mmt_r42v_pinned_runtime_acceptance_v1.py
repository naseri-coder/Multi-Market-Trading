"""Synthetic, nonproduction-only negative tests for the R42-V execution gate."""
import json
import shutil
from pathlib import Path

import pytest

from scripts import mmt_r42v_pinned_runtime_acceptance_v1 as r


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    root = tmp_path / "checked"
    for rel in r.PINS:
        destination = root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).resolve().parents[2] / rel
        shutil.copy2(source, destination)
    monkeypatch.setattr(r.os, "geteuid", lambda: 1000)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    return root


def test_pinned_source_only_returns_nonacceptance(checkout):
    outcome, status = r.evaluate(checkout=checkout, ack=True, source_check_only=True)
    assert status == 3
    assert outcome["verdict"] == "R42V_SOURCE_ONLY_NOT_ACCEPTED"
    assert outcome["tests_executed"] is False
    assert outcome["live_authorized"] is False
    assert set(outcome["file_pins"]) == set(r.PINS)


def test_python313_does_not_count_as_python312_success(checkout):
    with pytest.raises(r.AcceptanceBlocked, match="REAL_PYTHON312_REQUIRED"):
        r.evaluate(checkout=checkout, ack=True)


def test_both_checks_detect_modified_original_bytes(checkout):
    for rel in r.PINS:
        file = checkout / rel
        original = file.read_bytes()
        file.write_bytes(original + b"# tampered\n")
        with pytest.raises(r.AcceptanceBlocked, match="PIN_MISMATCH"):
            r.evaluate(checkout=checkout, ack=True, source_check_only=True)
        file.write_bytes(original)


def test_refuse_missing_ack_and_any_production_env(checkout, monkeypatch):
    with pytest.raises(r.AcceptanceBlocked, match="ACK_REQUIRED"):
        r.evaluate(checkout=checkout, ack=False, source_check_only=True)
    for value in ("", "0", "false", "1"):
        monkeypatch.setenv("MMT_PRODUCTION", value)
        with pytest.raises(r.AcceptanceBlocked, match="ACK_REQUIRED"):
            r.evaluate(checkout=checkout, ack=True, source_check_only=True)
    monkeypatch.delenv("MMT_PRODUCTION")


def test_source_symlink_refused(checkout):
    rel = list(r.PINS)[0]
    f = checkout / rel
    copy = f.with_suffix(".save")
    f.rename(copy)
    f.symlink_to(copy)
    with pytest.raises(r.AcceptanceBlocked, match="SYMLINK_SOURCE"):
        r.evaluate(checkout=checkout, ack=True, source_check_only=True)


def test_cli_never_claims_pass_on_python313(checkout, capsys):
    status = r.main(["--checkout", str(checkout), "--ack-offline-only"])
    output = json.loads(capsys.readouterr().out)
    assert status == 2
    assert output["verdict"] == "R42V_ACCEPTANCE_BLOCKED"
    assert output["reason"] == "R42V_REAL_PYTHON312_REQUIRED"
    assert output["live_authorized"] is False


def test_source_check_cli_is_explicitly_nonzero(checkout, capsys):
    status = r.main(["--checkout", str(checkout), "--ack-offline-only",
                     "--source-check-only"])
    output = json.loads(capsys.readouterr().out)
    assert status == 3
    assert output["verdict"] == "R42V_SOURCE_ONLY_NOT_ACCEPTED"
    assert output["python312_accepted"] is False


def test_source_check_does_not_execute_shell_or_tests(checkout, monkeypatch):
    def unwanted(*args, **kwargs):
        raise AssertionError("preflight should never launch subprocess")
    monkeypatch.setattr(r.subprocess, "run", unwanted)
    outcome, status = r.evaluate(checkout=checkout, ack=True, source_check_only=True)
    assert status == 3
    assert outcome["tests_executed"] is False
