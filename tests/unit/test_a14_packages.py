"""A14 temp-only synthetic package, fixed mock-worker and A12/A13 gating tests."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest

from naseri_markets.a14_packages import (
    MockPackageDeploymentManager, PackageRefused, inspect_bundle,
)

ENGINE = "private_example"
INSTALL = "a14_fixture_install"
DESCRIPTOR = "a" * 64


class FakeProvisioner:
    """Guard simulator for isolated filesystem/supervisor tests, NOT production proof."""

    def __init__(self):
        self.enabled = True
        self._plugins = SimpleNamespace(
            get=lambda ident: SimpleNamespace(engine_version="1.0.0")
        )

    def get(self, engine):
        return SimpleNamespace(status="OFFLINE_VERIFIED",
                               installation_id=INSTALL,
                               manifest_sha256=DESCRIPTOR, generation=1)

    def health(self, engine, *, admission, now):
        return SimpleNamespace(
            verified_offline=self.enabled and admission is self and now == 42
        )


def bundle(release, *, behavior="healthy", engine=ENGINE, installation=INSTALL,
           digest=DESCRIPTOR, generation=1, engine_version="1.0.0"):
    payload = (release + behavior).encode("ascii")
    manifest = {
        "schema_version": 1,
        "kind": "synthetic_private_data",
        "engine_id": engine,
        "engine_version": engine_version,
        "installation_id": installation,
        "manifest_sha256": digest,
        "trust_generation": generation,
        "release": release,
        "mode": "offline_paper_only",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "mock_behavior": behavior,
    }
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("payload.bin", payload)
    raw = sink.getvalue()
    return raw, hashlib.sha256(raw).hexdigest()


@pytest.fixture
def ctx(tmp_path):
    guard = FakeProvisioner()
    mgr = MockPackageDeploymentManager(
        tmp_path / "instance", provisioner=guard,
        engine_id=ENGINE, installation_id=INSTALL,
    )
    yield mgr, guard
    mgr.close()


def install(mgr, guard, release, *, behavior="healthy"):
    raw, pin = bundle(release, behavior=behavior)
    return mgr.install(raw, approved_sha256=pin,
                       expected_revision=mgr.status().revision,
                       admission=guard, now=42)


def start(mgr, guard):
    return mgr.start(expected_revision=mgr.status().revision,
                     admission=guard, now=42)


def stop(mgr):
    return mgr.stop(expected_revision=mgr.status().revision)


def rollback(mgr, guard):
    return mgr.rollback(expected_revision=mgr.status().revision,
                        admission=guard, now=42)


def test_atomic_install_mock_start_stop_upgrade_and_rollback(ctx):
    mgr, guard = ctx
    old = install(mgr, guard, "1.0.0").active
    assert mgr.status().revision == 1
    assert start(mgr, guard).state == "MOCK_RUNNING"
    assert mgr.status().owned_mock_worker_running
    assert stop(mgr).state == "STOPPED"
    upgraded = install(mgr, guard, "1.0.1")
    assert upgraded.previous == old and upgraded.active != old
    assert start(mgr, guard).state == "MOCK_RUNNING"
    stop(mgr)
    assert rollback(mgr, guard).active == old
    assert start(mgr, guard).state == "MOCK_RUNNING"
    assert stop(mgr).live_trading_permitted is False


def test_failed_mock_start_rolls_back_pointer(ctx):
    mgr, guard = ctx
    previous = install(mgr, guard, "1.0.0").active
    install(mgr, guard, "1.0.1", behavior="fail_start")
    with pytest.raises(PackageRefused, match="INJECTED_MOCK_START_FAILURE"):
        start(mgr, guard)
    assert mgr.status().active == previous
    assert mgr.status().state == "STOPPED"


def test_revision_and_revocation_fail_closed_except_stop(ctx):
    mgr, guard = ctx
    install(mgr, guard, "1.0.0")
    with pytest.raises(PackageRefused, match="STALE_REVISION"):
        mgr.start(expected_revision=0, admission=guard, now=42)
    guard.enabled = False
    with pytest.raises(PackageRefused, match="A13_FRESH_ADMISSION"):
        start(mgr, guard)
    with pytest.raises(PackageRefused, match="A13_FRESH_ADMISSION"):
        install(mgr, guard, "1.0.1")
    guard.enabled = True
    start(mgr, guard)
    guard.enabled = False
    assert stop(mgr).state == "STOPPED"
    with pytest.raises(PackageRefused, match="A13_FRESH_ADMISSION"):
        rollback(mgr, guard)


def test_restarted_manager_cannot_claim_or_take_over_running_worker(ctx):
    mgr, guard = ctx
    install(mgr, guard, "1.0.0")
    start(mgr, guard)
    other = MockPackageDeploymentManager(
        mgr._root, provisioner=guard, engine_id=ENGINE, installation_id=INSTALL
    )
    assert other.status().state == "INTERRUPTED_RECONCILIATION_REQUIRED"
    with pytest.raises(PackageRefused, match="OWNED_ELSEWHERE"):
        other.reconcile_interrupted(expected_revision=2)
    mgr._halt()  # simulate lost parent AFTER fixed worker exited, without state commit
    assert other.reconcile_interrupted(expected_revision=2).state == "STOPPED"
    with pytest.raises(PackageRefused, match="STALE_REVISION"):
        other.rollback(expected_revision=2, admission=guard, now=42)
    other.close()


def test_reject_tampering_traversal_and_untrusted_bundles(ctx):
    mgr, guard = ctx
    raw, pin = bundle("1.0.0")
    with pytest.raises(PackageRefused, match="PIN_MISMATCH"):
        inspect_bundle(raw + b"tampered", approved_sha256=pin)
    forged = io.BytesIO()
    with zipfile.ZipFile(forged, "w") as archive:
        archive.writestr("../unsafe", b"bad")
        archive.writestr("payload.bin", b"bad")
    data = forged.getvalue()
    with pytest.raises(PackageRefused, match="EXACT_ARCHIVE"):
        inspect_bundle(data, approved_sha256=hashlib.sha256(data).hexdigest())
    for variation in (
        {"installation": "wrong_install"},
        {"digest": "b" * 64},
        {"engine": "foreign_engine"},
        {"generation": 2},
    ):
        data, approved = bundle("1.0.0", **variation)
        with pytest.raises(PackageRefused, match="MISMATCH"):
            mgr.install(data, approved_sha256=approved,
                        expected_revision=0, admission=guard, now=42)
    state = install(mgr, guard, "1.0.0")
    archive = mgr._releases / state.active / "package.zip"
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(PackageRefused, match="PIN_MISMATCH"):
        start(mgr, guard)


def test_refuses_outside_temp_and_symlink_root(tmp_path):
    guard = FakeProvisioner()
    root = tmp_path / "actual"
    root.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(PackageRefused, match="TEMP_ROOT_ONLY"):
        MockPackageDeploymentManager(alias, provisioner=guard,
                                     engine_id=ENGINE, installation_id=INSTALL)
    with pytest.raises(PackageRefused, match="TEMP_ROOT_ONLY"):
        MockPackageDeploymentManager("/opt/a14_private", provisioner=guard,
                                     engine_id=ENGINE, installation_id=INSTALL)


def test_real_a12_a13_signed_grant_required_for_install_and_start(tmp_path):
    pytest.importorskip("cryptography")
    from test_a13_provisioning import (
        fixture as a13_fixture, plan, admission, digest as sha, NOW,
        ENGINE as real_engine, INSTALL as real_install,
    )

    plugins, trust, issuer, _, policy, provisioner = a13_fixture(tmp_path)
    raw_plan = plan(policy)
    prepared = provisioner.prepare(raw_plan, approved_sha256=sha(raw_plan))
    grant = admission(trust, issuer, policy)
    provisioner.verify(real_engine, expected_revision=prepared.revision,
                       admission=grant, now=NOW)
    mgr = MockPackageDeploymentManager(
        tmp_path / "packages", provisioner=provisioner,
        engine_id=real_engine, installation_id=real_install,
    )
    raw, pin = bundle("1.0.0", engine=real_engine, installation=real_install,
                      digest=policy["manifest_sha256"],
                      generation=policy["generation"])
    installed = mgr.install(raw, approved_sha256=pin, expected_revision=0,
                            admission=grant, now=NOW)
    assert installed.state == "STOPPED"
    assert mgr.start(expected_revision=1, admission=grant, now=NOW).state == "MOCK_RUNNING"
    trust.revoke_serial("a" * 32)
    with pytest.raises(PackageRefused, match="A13_FRESH_ADMISSION"):
        mgr.install(raw, approved_sha256=pin, expected_revision=2,
                    admission=grant, now=NOW)
    assert mgr.stop(expected_revision=2).state == "STOPPED"
    with pytest.raises(PackageRefused, match="A13_FRESH_ADMISSION"):
        mgr.start(expected_revision=3, admission=grant, now=NOW)
    mgr.close()
    provisioner.close()
    plugins.close()
    trust.close()
