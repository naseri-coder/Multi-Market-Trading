"""R41 static OCI source-identity and denial tests. Never starts Docker."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from naseri_markets import secure_plugin_runtime_v1 as stage4
from scripts import mmt_r41_readonly_oci_contract_audit_v1 as r41


@pytest.fixture
def source(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    original = Path(stage4.__file__).read_bytes()
    directory = tmp_path / "source"
    directory.mkdir(mode=0o700)
    target = directory / "secure_plugin_runtime_v1.py"
    target.write_bytes(original)
    args = {
        "source": target,
        "expected_source_sha256": hashlib.sha256(original).hexdigest(),
        "operator_ack": True,
    }
    return args


def repin(args: dict, old: bytes, new: bytes) -> None:
    current = args["source"].read_bytes()
    assert old in current, "reviewed Stage4 token changed: update tests explicitly"
    changed = current.replace(old, new, 1)
    args["source"].write_bytes(changed)
    args["expected_source_sha256"] = hashlib.sha256(changed).hexdigest()


def test_real_stage4_source_static_contract_and_denials(source):
    result = r41.check_source(**source)
    assert result["verdict"] == "R41_STATIC_OCI_CONTRACT_PASS_HOST_TRIAL_PENDING"
    assert result["required_hardening_flags_observed"] == len(r41._REQUIRED)
    assert result["independent_rootless_host_tested"] is False
    assert result["gvisor_runtime_verified"] is False
    assert result["hostile_core_containment_proven"] is False
    assert result["cleanup_under_crash_proven"] is False
    assert result["public_release_authorized"] is False
    assert result["live_authorized"] is False
    assert result["files_written"] is False


def test_readonly_does_not_change_stage4_bytes(source):
    before = source["source"].read_bytes()
    first = r41.check_source(**source)
    second = r41.check_source(**source)
    assert first == second
    assert before == source["source"].read_bytes()


def test_wrong_external_source_pin_denied(source):
    source["expected_source_sha256"] = "0" * 64
    with pytest.raises(r41.R41Refused, match="SOURCE_PIN_MISMATCH"):
        r41.check_source(**source)


def test_gvisor_runtime_removed_denied_even_with_new_pin(source):
    repin(source, b"--runtime=runsc", b"--runtime=runc")
    with pytest.raises(r41.R41Refused, match="REQUIRED_GVISOR"):
        r41.check_source(**source)


def test_network_isolation_removed_denied_even_with_new_pin(source):
    repin(source, b"--network=none", b"--network=host")
    with pytest.raises(r41.R41Refused, match="REQUIRED_GVISOR"):
        r41.check_source(**source)


def test_new_privileged_flag_denied_even_if_other_flags_remain(source):
    repin(source, b'"--network=none", "--ipc=none"',
          b'"--network=none", "--privileged", "--ipc=none"')
    with pytest.raises(r41.R41Refused, match="PRIVILEGED"):
        r41.check_source(**source)


def test_rootless_daemon_probe_removed_denied(source):
    repin(source, b"def _ensure_rootless_daemon(",
          b"def _removed_rootless_daemon_probe(")
    with pytest.raises(r41.R41Refused, match="REQUIRED_FUNCTION_MISSING"):
        r41.check_source(**source)


def test_dynamic_unreviewed_command_expression_denied(source):
    repin(source, b'policy.image, "-I", "-S"',
          b'policy.image + "/unexpected", "-I", "-S"')
    with pytest.raises(r41.R41Refused, match="UNREVIEWED_COMMAND_EXPRESSION"):
        r41.check_source(**source)


def test_symlink_source_denied(source):
    real = source["source"]
    link = real.parent / "ref.py"
    link.symlink_to(real)
    source["source"] = link
    with pytest.raises(r41.R41Refused, match="STAGE4_MODULE_NAME_REQUIRED"):
        r41.check_source(**source)


def test_symlink_exact_named_source_denied(source, tmp_path):
    location = tmp_path / "alias"
    location.mkdir()
    link = location / "secure_plugin_runtime_v1.py"
    link.symlink_to(source["source"])
    source["source"] = link
    with pytest.raises(r41.R41Refused, match="SYMLINK_SOURCE_REFUSED"):
        r41.check_source(**source)


def test_hardlinked_source_denied(source):
    os.link(source["source"], source["source"].parent / "second")
    with pytest.raises(r41.R41Refused, match="BOUNDED_REGULAR_SOURCE"):
        r41.check_source(**source)


def test_wrong_module_name_denied(source):
    target = source["source"]
    wrong = target.with_name("injected_runner.py")
    target.rename(wrong)
    source["source"] = wrong
    with pytest.raises(r41.R41Refused, match="STAGE4_MODULE_NAME_REQUIRED"):
        r41.check_source(**source)


def test_nonproduction_ack_required(source):
    source["operator_ack"] = False
    with pytest.raises(r41.R41Refused, match="ACK_REQUIRED"):
        r41.check_source(**source)


@pytest.mark.parametrize("setting", ["", "0", "1", "true"])
def test_any_explicit_production_environment_denied(source, monkeypatch, setting):
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    with pytest.raises(r41.R41Refused, match="ACK_REQUIRED"):
        r41.check_source(**source)


def test_missing_source_hash_denied(source):
    source["expected_source_sha256"] = ""
    with pytest.raises(r41.R41Refused, match="ACK_REQUIRED"):
        r41.check_source(**source)


def test_cli_readonly_success_never_grants_host_proof(source, capsys):
    assert r41.main([
        "--stage4-source", str(source["source"]),
        "--expected-stage4-sha256", source["expected_source_sha256"],
        "--ack-readonly-static-review",
    ]) == 0
    import json
    obj = json.loads(capsys.readouterr().out)
    assert obj["gvisor_runtime_verified"] is False
    assert obj["hostile_core_containment_proven"] is False
    assert obj["live_authorized"] is False


def test_cli_wrong_pin_failclosed(source, capsys):
    assert r41.main([
        "--stage4-source", str(source["source"]),
        "--expected-stage4-sha256", "0" * 64,
        "--ack-readonly-static-review",
    ]) == 2
    import json
    obj = json.loads(capsys.readouterr().out)
    assert obj["verdict"] == "R41_STATIC_CONTAINMENT_REVIEW_REFUSED"
    assert obj["public_release_authorized"] is False


def test_rootless_probe_call_bypass_detected(source):
    repin(source, b"_ensure_rootless_daemon(self.policy)",
          b"_unsafe_skip_daemon_probe(self.policy)")
    with pytest.raises(r41.R41Refused, match="ROOTLESS_EVALUATION_CHAIN_MISSING"):
        r41.check_source(**source)


def test_dynamic_docker_name_expression_denied(source):
    repin(source, b'f"--name={name}"', b'f"--name={name.upper()}"')
    with pytest.raises(r41.R41Refused, match="UNREVIEWED_DYNAMIC_SWITCH"):
        r41.check_source(**source)


def test_missing_secure_host_class_denied(source):
    repin(source, b"class SecureOfflineCoreHost:",
          b"class UnreviewedCoreHost:")
    with pytest.raises(r41.R41Refused, match="HOST_CLASS_MISSING"):
        r41.check_source(**source)
