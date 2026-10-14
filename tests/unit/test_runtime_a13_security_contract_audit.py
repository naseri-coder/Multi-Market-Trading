"""A13 focused source-only regression guards and malicious-drift fixtures."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from naseri_markets import runtime_a13_security_contract_audit as audit
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)
from naseri_markets.runtime_a13_security_contract_audit import (
    A13AuditRefused,
    audit_repository,
)

BASE = Path(__file__).resolve().parents[2]
A1 = "naseri_markets/multilang_runtime_a1.py"
A6 = "naseri_markets/runtime_a6_dispatch_fence.py"
A7 = "naseri_markets/runtime_a7_disposable_host_preflight.py"
A8 = "naseri_markets/runtime_a8_supply_chain.py"
A9 = "naseri_markets/runtime_a9_offline_intent.py"
A11 = "naseri_markets/runtime_a11_offline_witness.py"
A12 = "naseri_markets/runtime_a12_offline_recovery.py"


def _fixture(tmp_path):
    root = tmp_path / "fixture"
    for rel in (*audit._MODULES, audit._A1, audit._DOCKERFILE):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / rel, dest)
    return root


def _mutate(root, rel, old, new):
    path = root / rel
    before = path.read_text()
    assert old in before, f"expected structural anchor missing: {rel}"
    path.write_text(before.replace(old, new, 1))


def test_real_repository_audit_is_narrow_and_denies_launch():
    report = audit_repository(BASE)
    assert report.audited_files == 11
    assert report.hard_stop_checks == 3
    assert report.false_security_flag_defaults >= 25
    assert len(report.remaining_external_gates) == 6
    assert report.status == "A13_CONTRACT_CHECKS_PASS_EXTERNAL_SECURITY_GATES_BLOCKED"
    assert not report.independent_host_certified
    assert not report.media_custody_proven
    assert not report.verified_worker_image_proven
    assert not report.worker_execution_authorized
    assert not report.quarantine_release_authorized
    assert not report.broker_authorized
    assert not report.telegram_authorized
    assert not report.production_recovery_authorized


def test_a6_unconditional_denial_regression_fails(tmp_path):
    root = _fixture(tmp_path)
    _mutate(
        root, A6,
        'raise RuntimeA6Denied("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED")',
        "return None",
    )
    with pytest.raises(A13AuditRefused, match="A13_A6_UNCONDITIONAL_DENY_MISSING"):
        audit_repository(root)


def test_a6_non_denial_exception_regression_fails(tmp_path):
    root = _fixture(tmp_path)
    _mutate(
        root, A6, 'raise RuntimeA6Denied("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED")',
        'raise RuntimeError("SOME_OTHER_EXCEPTION")',
    )
    with pytest.raises(A13AuditRefused, match="A13_A6_DENY_TYPE_DRIFT"):
        audit_repository(root)


def test_a1_direct_oci_guard_removal_fails(tmp_path):
    root = _fixture(tmp_path)
    _mutate(
        root, A1,
        "    require_worker_launch(profile, payload)\n",
        "    pass  # deliberately missing launch guard\n",
    )
    with pytest.raises(A13AuditRefused, match="A13_LAUNCH_GUARD_NOT_DIRECT"):
        audit_repository(root)


def test_a1_evaluation_guard_removal_fails(tmp_path):
    root = _fixture(tmp_path)
    _mutate(
        root, A1,
        "            require_worker_launch(profile, framed)\n",
        "            pass  # deliberately missing entrypoint guard\n",
    )
    with pytest.raises(A13AuditRefused, match="A13_LAUNCH_GUARD_NOT_DIRECT"):
        audit_repository(root)


def test_a1_process_inserted_before_guard_fails(tmp_path):
    root = _fixture(tmp_path)
    _mutate(
        root, A1,
        "    require_worker_launch(profile, payload)\n",
        "    subprocess.Popen(['unexpected'])\n"
        "    require_worker_launch(profile, payload)\n",
    )
    with pytest.raises(A13AuditRefused, match="A13_OCI_PROCESS_CALL_BEFORE_A6_DENY"):
        audit_repository(root)


@pytest.mark.parametrize("rel,old,new", [
    (A9, "worker_execution_authorized: bool = False",
     "worker_execution_authorized: bool = True"),
    (A11, "independent_custody_proven: bool = False",
     "independent_custody_proven: bool = True"),
    (A12, "recovery_activated: bool = False",
     "recovery_activated: bool = True"),
    (A8, "production_authorized: bool = False",
     "production_authorized: bool = True"),
])
def test_forged_security_or_execution_defaults_fail(tmp_path, rel, old, new):
    root = _fixture(tmp_path)
    _mutate(root, rel, old, new)
    with pytest.raises(A13AuditRefused, match="A13_SECURITY_DEFAULT_GRANT_DRIFT"):
        audit_repository(root)


def test_unexpected_executor_import_into_review_module_fails(tmp_path):
    root = _fixture(tmp_path)
    with (root / A12).open("a") as file:
        file.write("\nimport subprocess\n")
    with pytest.raises(A13AuditRefused, match="A13_UNEXPECTED_EXECUTOR_IMPORT"):
        audit_repository(root)


def test_a7_readonly_preflight_process_query_is_not_launch_grant(tmp_path):
    root = _fixture(tmp_path)
    # A7 reads local host metadata; its subprocess import is intentionally
    # not confused with a user-code launch authorization in A1.
    assert "import subprocess" in (root / A7).read_text()
    report = audit_repository(root)
    assert not report.worker_execution_authorized
    assert not report.independent_host_certified


def test_symlinked_source_and_missing_recipe_fail_closed(tmp_path):
    root = _fixture(tmp_path)
    source = root / A6
    copied = root / "copy.txt"
    shutil.copyfile(source, copied)
    source.unlink()
    source.symlink_to(copied)
    with pytest.raises(A13AuditRefused, match="A13_SOURCE_SYMLINK_REFUSED"):
        audit_repository(root)
    source.unlink()
    shutil.copyfile(copied, source)
    (root / audit._DOCKERFILE).unlink()
    with pytest.raises(A13AuditRefused, match="A13_REQUIRED_SOURCE_MISSING"):
        audit_repository(root)


def test_bad_python_ast_fails_closed(tmp_path):
    root = _fixture(tmp_path)
    (root / A9).write_bytes(b"\xffnot-python")
    with pytest.raises(A13AuditRefused, match="A13_SOURCE_NOT_PARSEABLE"):
        audit_repository(root)


def test_unsupported_root_denied(tmp_path):
    with pytest.raises(A13AuditRefused, match="A13_EXPLICIT_SOURCE_ROOT_REQUIRED"):
        audit_repository(Path("relative"))
    with pytest.raises(A13AuditRefused, match="A13_REQUIRED_SOURCE_MISSING"):
        audit_repository(tmp_path)


def test_no_shell_no_worker_processes_and_a6_fence(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A13_AUDIT_MUST_NOT_LAUNCH_PROCESS")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert not audit_repository(BASE).worker_execution_authorized
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")


def test_static_checks_do_not_claim_dynamic_or_physical_security():
    verdict = audit_repository(BASE)
    assert "DISPOSABLE_HOST_REAL_GVISOR_ATTESTATION" in verdict.remaining_external_gates
    assert "OUT_OF_BAND_LATEST_CHECKPOINT_CUSTODY" in verdict.remaining_external_gates
    assert "INDEPENDENT_OCI_AND_PACKAGE_PROVENANCE" in verdict.remaining_external_gates
    assert verdict.hard_stop_checks == 3
    assert verdict.status.endswith("EXTERNAL_SECURITY_GATES_BLOCKED")
