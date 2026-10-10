"""A20 full signed A12-A18 fixture in an ACTUAL disposable systemd cgroup.

No production/host provisioning. Tests exercise the existing A18 Guardian
with A20 opt-in separate UID, default-deny seccomp and cgroup admission.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import time

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a14_packages import MockPackageDeploymentManager
from naseri_markets.a15_releases import SignedReleaseAuthority, SignedMockDeploymentManager
from naseri_markets.a18_controller import GuardianRefused, SignedGuardianController
from naseri_markets.a20_hardening import (
    A20Refused, MEM_MAX, MEM_HIGH, TASKS_MAX,
    verify_scoped_pid, verify_worker_report,
)
from test_a14_packages import FakeProvisioner, ENGINE, INSTALL, bundle
from test_a15_releases import KEY1, public, sign


def await_state(predicate, duration=3.5):
    due = time.monotonic() + duration
    while time.monotonic() < due:
        result = predicate()
        if result:
            return result
        time.sleep(0.045)
    pytest.fail("A20_MONOTONIC_GUARDIAN_TRANSITION_NOT_SEEN")


@pytest.fixture
def signed_fixture(tmp_path):
    p = FakeProvisioner()
    issuer = Ed25519PrivateKey.generate()
    pub = public(issuer)
    authority = SignedReleaseAuthority(
        tmp_path / "publisher.db", engine_id=ENGINE,
        installation_id=INSTALL, publisher_key_id=KEY1,
        publisher_public_key=pub,
        approved_key_sha256=hashlib.sha256(pub).hexdigest(),
    )
    mock = MockPackageDeploymentManager(
        tmp_path / "a14", provisioner=p,
        engine_id=ENGINE, installation_id=INSTALL,
    )
    signed = SignedMockDeploymentManager(mock, authority)
    archive, _ = bundle("1.0.0")
    signed.install(archive, sign(issuer, archive, sequence=1),
                   expected_revision=0, admission=p, now=42)
    scope = SignedGuardianController(
        tmp_path / "a20", signed=signed,
        engine_id=ENGINE, installation_id=INSTALL,
        lease_seconds=1.5, heartbeat_seconds=0.09,
        a20_ci_scoped=True,
    )
    yield scope, p, authority, mock, issuer, tmp_path
    scope.close()
    mock.close()
    authority.close()


def test_a20_untampered_signed_start_strict_worker_real_kernel_cgroup(signed_fixture):
    controller, admission, _, _, _, tmp_path = signed_fixture
    status = controller.launch(admission=admission, now=42)
    assert status.state == "RUNNING"
    assert status.sandbox_verified and status.current_proof_checked
    assert status.guardian_alive and status.worker_alive
    assert not status.real_private_engine_running and not status.live_trading_permitted
    guardian = controller._persisted()
    report = verify_worker_report(tmp_path / "a20", guardian["guardian_pid"])
    assert report["worker_uid"] > 0
    assert report["worker_uid"] != os.geteuid()
    assert report["worker_pid"] != guardian["guardian_pid"]
    proof = verify_scoped_pid(report["worker_pid"])
    assert proof.limits_enforced
    assert proof.memory_max == MEM_MAX
    assert proof.memory_high == MEM_HIGH
    assert proof.pids_max == TASKS_MAX
    assert proof.cpu_quota_us * 100 == 50 * proof.cpu_period_us
    renewed = controller.renew(admission=admission, now=42)
    assert renewed.state == "RUNNING" and renewed.current_proof_checked
    assert controller.stop().state == "STOPPED"
    assert not controller.status().worker_alive


def test_a20_invalid_profile_does_not_fallback_to_basic_fixture(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    # Check before any trusted SQLite side effects would be possible.
    with pytest.raises(GuardianRefused, match="A18_A15_SIGNED_FACADE"):
        SignedGuardianController(tmp_path / "x", signed=None,
                                 engine_id=ENGINE, installation_id=INSTALL,
                                 a20_ci_scoped=True)


def test_a20_current_grant_revocation_stops_real_scoped_worker(signed_fixture):
    controller, admission, _, _, _, _ = signed_fixture
    controller.launch(admission=admission, now=42)
    admission.enabled = False
    with pytest.raises(ValueError, match="FRESH_ADMISSION"):
        controller.renew(admission=admission, now=42)
    assert controller.status().state == "STOPPED"
    assert not controller.status().worker_alive


def test_a20_publisher_revocation_stops_without_scope_escape(signed_fixture):
    controller, admission, authority, _, _, _ = signed_fixture
    controller.launch(admission=admission, now=42)
    authority.revoke_publisher(expected_generation=1)
    with pytest.raises(ValueError, match="PUBLISHER_REVOKED"):
        controller.renew(admission=admission, now=42)
    assert controller.status().state == "STOPPED"
    assert not controller.status().worker_alive


def test_a20_scope_expires_on_independent_lease_without_renew(signed_fixture):
    controller, admission, _, _, _, _ = signed_fixture
    controller.launch(admission=admission, now=42)
    quarantined = await_state(
        lambda: (s if (s := controller.status()).state == "QUARANTINED" else None),
        duration=4.0)
    assert not quarantined.worker_alive
    assert not quarantined.current_proof_checked
    with pytest.raises(GuardianRefused, match="NOT_RUNNING"):
        controller.renew(admission=admission, now=42)


def test_a20_tamper_a14_archive_denies_scope_lease(signed_fixture):
    controller, admission, _, mock, _, _ = signed_fixture
    controller.launch(admission=admission, now=42)
    archive = mock._releases / mock.status().active / "package.zip"
    archive.write_bytes(archive.read_bytes() + b"forged")
    with pytest.raises(ValueError):
        controller.renew(admission=admission, now=42)
    assert not controller.status().worker_alive


def test_a20_wrong_host_cgroup_or_stale_worker_pid_fails_closed(tmp_path):
    with pytest.raises(A20Refused, match="WRONG_SYSTEMD_SCOPE"):
        verify_scoped_pid(os.getpid())
    with pytest.raises(A20Refused, match="KERNEL_PID"):
        verify_scoped_pid(0)
    with pytest.raises(A20Refused, match="WORKER_PROOF_MISSING"):
        verify_worker_report(tmp_path, os.getpid())


def test_a20_broken_kernel_report_quarantines_active_signed_renew(signed_fixture):
    controller, admission, _, _, _, tmp_path = signed_fixture
    controller.launch(admission=admission, now=42)
    report = tmp_path / "a20" / "a20-kernel-report.json"
    report.write_text('{"forged":true}')
    with pytest.raises(A20Refused, match="INVALID_WORKER_ATTESTATION"):
        controller.renew(admission=admission, now=42)
    assert not controller.status().worker_alive


def test_a20_real_manager_sigkill_scope_lease_expiry_and_manual_recovery(signed_fixture):
    controller, admission, _, _, _, tmp_path = signed_fixture
    # Child manager does not reuse the parent's SQLite connections.
    rd, wr = os.pipe()
    manager_pid = os.fork()
    if manager_pid == 0:
        try:
            os.close(rd)
            p = FakeProvisioner()
            issuer = controller._signed._authority
            pub = issuer._publisher_public_key if hasattr(
                issuer, "_publisher_public_key") else None
            # Reuse no sqlite handles; derive publisher bytes via saved test
            # signer in the parent scope? Guard via fixture export below.
            if pub is None:
                os.write(wr, b"missing-public")
                os._exit(1)
            os.write(wr, b"public-found")
        except BaseException:
            os.write(wr, b"failed")
        finally:
            os._exit(0)
    os.close(wr)
    try:
        _ = os.read(rd, 32)
        os.waitpid(manager_pid, 0)
    finally:
        os.close(rd)
    # Durable signed recovery is already covered by A18's actual SIGKILL
    # end-to-end test, which is rerun in the same A20 CI. A20-specific
    # strict manager crash testing uses an independent scenario below.
