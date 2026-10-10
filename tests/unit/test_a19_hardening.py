"""A19 tested hardening gates; only disposable public fixture code ever runs."""
from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path

import pytest

from naseri_markets.a19_hardening import (
    C_GROUPS, UNIT_BASENAME, HardeningRefused, cgroup_readiness,
    export_offline_unit, run_separate_uid_kernel_probe,
    systemd_fixture_unit, validate_offline_unit,
)


def test_exact_disabled_nonproduction_unit_policy_and_bounds(tmp_path):
    content = systemd_fixture_unit()
    assert content.startswith("# Multi Market Trading / A19")
    assert "DynamicUser=yes" in content
    assert "NoNewPrivileges=yes" in content
    assert "PrivateNetwork=yes" in content
    assert "CapabilityBoundingSet=\n" in content
    assert "ProtectSystem=strict" in content
    assert "ProtectHome=yes" in content
    assert "RestrictNamespaces=yes" in content
    assert "SystemCallFilter=" in content
    assert "MemoryMax=256M" in content
    assert "MemoryHigh=192M" in content
    assert "CPUQuota=50%" in content
    assert "TasksMax=8" in content
    assert "Restart=no" in content
    assert "RefuseManualStart=yes" in content
    assert "ConditionPathExists=/run/mmt-a19-explicit-test-authorization-never-created" in content
    assert "WantedBy=" not in content
    assert "production_source" not in content
    assert "ExecStart=/usr/bin/python3 -I -S -u -c" in content
    assert "A19_INERT_FIXTURE_ONLY" in content
    assert "PrivateNetwork=yes" in content
    unit, digest = export_offline_unit(tmp_path / "policy")
    assert unit.name == UNIT_BASENAME
    assert unit.read_text() == content
    assert digest == hashlib.sha256(content.encode()).hexdigest()
    assert stat.S_IMODE(unit.stat().st_mode) == 0o600
    assert validate_offline_unit(unit) == "A19_SYSTEMD_SYNTAX_VERIFIED_NOT_ACTIVATED"
    with pytest.raises(HardeningRefused, match="PREVIEW_MUST_BE_NEW"):
        export_offline_unit(tmp_path / "policy")


def test_unit_immutable_and_symlink_denied(tmp_path):
    unit, _ = export_offline_unit(tmp_path / "policy")
    unit.write_text("[Service]\nExecStart=/bin/sh\n")
    with pytest.raises(HardeningRefused, match="FROZEN_PREVIEW"):
        validate_offline_unit(unit)
    link = tmp_path / "alias"
    link.symlink_to(tmp_path / "policy", target_is_directory=True)
    with pytest.raises(HardeningRefused, match="DISPOSABLE"):
        export_offline_unit(link)
    with pytest.raises(HardeningRefused, match="DISPOSABLE"):
        export_offline_unit("/etc/systemd/system")


def test_cgroup_controller_capability_only_never_enforced(tmp_path):
    missing = cgroup_readiness(tmp_path / "absent")
    assert not missing.cgroup_v2_seen
    assert not missing.limits_enforced
    (tmp_path / "cgroup.controllers").write_text("memory cpu pids io cpuset\n")
    ready = cgroup_readiness(tmp_path)
    assert ready.cgroup_v2_seen
    assert C_GROUPS.issubset(ready.available_controllers)
    assert ready.required_controllers_present
    assert not ready.limits_enforced
    (tmp_path / "cgroup.controllers").write_text("cpu io\n")
    insufficient = cgroup_readiness(tmp_path)
    assert not insufficient.required_controllers_present
    assert not insufficient.limits_enforced
    (tmp_path / "cgroup.controllers").write_text("bad-name!\n")
    with pytest.raises(HardeningRefused, match="STATUS_INVALID"):
        cgroup_readiness(tmp_path)


def test_strict_probe_is_fixed_and_default_deny_not_a18_allowlist():
    from naseri_markets.a19_hardening import STRICT_PROBE

    assert "sc.seccomp_init(0x00050000 | errno.EPERM)" in STRICT_PROBE
    assert "sc.seccomp_rule_add(ctx, 0x7fff0000" in STRICT_PROBE
    assert "socket.socket(socket.AF_INET" in STRICT_PROBE
    assert "os.open('/etc/passwd', os.O_RDONLY)" in STRICT_PROBE
    assert "os.fork()" in STRICT_PROBE
    assert "no_new_privs" in STRICT_PROBE
    assert "seccomp_filter" in STRICT_PROBE
    assert "private_nyfr_core" not in STRICT_PROBE
    assert "MetaTrader5" not in STRICT_PROBE


def test_host_rootless_kernel_capabilities_are_observational_only():
    # This API is not an active cgroup tenant and is deliberately read-only.
    read = cgroup_readiness()
    assert not read.limits_enforced
    assert isinstance(read.available_controllers, frozenset)


def test_separate_nonroot_uid_real_kernel_seccomp_network_file_fork_denials():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        with pytest.raises(HardeningRefused, match="GITHUB_EPHEMERAL"):
            run_separate_uid_kernel_probe()
        return
    checked = run_separate_uid_kernel_probe()
    assert checked.uid == checked.required_uid
    assert checked.uid > 0
    assert checked.uid != os.geteuid()
    assert checked.seccomp_default_deny
    assert checked.no_new_privs
    assert checked.socket_denied
    assert checked.file_open_denied
    assert checked.fork_denied
    assert not checked.real_private_engine_running
    assert not checked.live_trading_permitted
