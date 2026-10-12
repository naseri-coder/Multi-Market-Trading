"""Stage38 synthetic Linux /proc negative cases; never probe GitHub host.

The sample under test is process-local, NOT evidence of real gVisor, real
firewall enforcement or independent physical-machine authorization.
"""
from __future__ import annotations

import hashlib
import json

import pytest

pytest.importorskip("cryptography")

import naseri_markets.passive_kernel_posture_stage38_v1 as probe
from naseri_markets.passive_kernel_posture_stage38_v1 import (
    Stage38Refused, _root_mount, _routes4, _routes6, _status,
    observe_authorized_process_kernel_posture,
)

HOST = "disposable_test_one"
NODE = "disposable-test-node"
V4_HEADER = (
    b"Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
)
V4_LO = V4_HEADER + (
    b"lo 0000007F 00000000 0001 0 0 0 000000FF 0 0 0\n"
)
V6_LO = (
    b"00000000000000000000000001000000 80 "
    b"00000000000000000000000000000000 00 "
    b"00000000000000000000000000000000 "
    b"00000000 00000000 00000000 00000000 lo\n"
)
MOUNTS_RO = b"42 27 0:38 / / ro,relatime - overlay overlay ro\n"
STATUS = (
    b"Name:\tmmt-probe\n"
    b"Uid:\t1001\t1001\t1001\t1001\n"
    b"Gid:\t1001\t1001\t1001\t1001\n"
    b"CapInh:\t0000000000000000\n"
    b"CapPrm:\t0000000000000000\n"
    b"CapEff:\t0000000000000000\n"
    b"CapBnd:\t0000000000000000\n"
    b"CapAmb:\t0000000000000000\n"
    b"NoNewPrivs:\t1\n"
    b"Seccomp:\t2\n"
    b"Seccomp_filters:\t1\n"
)
SAMPLES = {
    "/proc/self/status": STATUS,
    "/proc/self/mountinfo": MOUNTS_RO,
    "/proc/self/net/route": V4_LO,
    "/proc/self/net/ipv6_route": V6_LO,
}


@pytest.fixture
def synthetic_host(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1001)
    monkeypatch.setattr(probe.os, "getegid", lambda: 1001)

    class MockUname:
        nodename = NODE

    monkeypatch.setattr(probe.os, "uname", lambda: MockUname())
    contents = dict(SAMPLES)
    monkeypatch.setattr(probe, "_read_fixed_proc",
                        lambda path, *, limit: contents[path])
    return contents


def collect():
    return observe_authorized_process_kernel_posture(
        host_alias=HOST, expected_nodename=NODE, expected_gid=1001,
        operator_ack=True,
    )


def test_synthetic_restrictive_process_reports_only_self_local_facts(
        synthetic_host):
    receipt = collect()
    assert receipt.host_alias == HOST
    assert receipt.nodename == NODE
    assert receipt.process_uid == receipt.process_gid == 1001
    assert receipt.loopback_routes_seen == 2
    assert receipt.proc_status_sha256 == hashlib.sha256(STATUS).hexdigest()
    assert receipt.proc_mountinfo_sha256 == hashlib.sha256(MOUNTS_RO).hexdigest()
    assert receipt.proc_ipv4_routes_sha256 == hashlib.sha256(V4_LO).hexdigest()
    assert receipt.proc_ipv6_routes_sha256 == hashlib.sha256(V6_LO).hexdigest()
    assert receipt.state == "LOCAL_PROCESS_KERNEL_POSTURE_ONLY_NO_RUNTIME_ATTESTATION"
    assert receipt.local_process_restrictive_snapshot is True
    for name in (
        "independent_host_identity_verified",
        "nftables_active_ruleset_independently_verified",
        "network_egress_independently_blocked",
        "other_container_gvisor_verified",
        "gvisor_escape_containment_certified",
        "public_api_deployment_authorized",
        "plugin_execution_authorized",
        "telegram_publish_authorized", "broker_order_authorized",
    ):
        assert getattr(receipt, name) is False
    assert json.loads(receipt.sanitized_json())["state"] == receipt.state
    assert receipt.digest_sha256() == hashlib.sha256(
        receipt.sanitized_json()).hexdigest()
    assert b"mmt-probe" not in receipt.sanitized_json()
    assert b"CapEff" not in receipt.sanitized_json()


@pytest.mark.parametrize("status_change", [
    ("CapEff:\t0000000000000000", "CapEff:\t0000000000000001"),
    ("CapPrm:\t0000000000000000", "CapPrm:\t0000000000000001"),
    ("CapBnd:\t0000000000000000", "CapBnd:\t0000000000000001"),
    ("CapAmb:\t0000000000000000", "CapAmb:\t0000000000000001"),
    ("CapInh:\t0000000000000000", "CapInh:\t0000000000000001"),
    ("NoNewPrivs:\t1", "NoNewPrivs:\t0"),
    ("Seccomp:\t2", "Seccomp:\t0"),
    ("Seccomp_filters:\t1", "Seccomp_filters:\t0"),
    ("Uid:\t1001\t1001\t1001\t1001", "Uid:\t0\t0\t0\t0"),
    ("Gid:\t1001\t1001\t1001\t1001", "Gid:\t1002\t1002\t1002\t1002"),
    ("Gid:\t1001\t1001\t1001\t1001", "Gid:\t1001\t0\t1001\t1001"),
])
def test_privilege_capabilities_and_unconfined_process_rejected(status_change):
    original, changed = status_change
    raw = STATUS.replace(original.encode(), changed.encode())
    with pytest.raises(Stage38Refused):
        _status(raw, expected_uid=1001, expected_gid=1001)


def test_missing_or_duplicate_process_security_properties_refused():
    with pytest.raises(Stage38Refused):
        _status(STATUS.replace(b"Seccomp:\t2\n", b""),
                expected_uid=1001, expected_gid=1001)
    with pytest.raises(Stage38Refused):
        _status(STATUS + b"CapEff:\t0000000000000000\n",
                expected_uid=1001, expected_gid=1001)
    with pytest.raises(Stage38Refused):
        _status(STATUS+b"broken_line\n",
                expected_uid=1001, expected_gid=1001)


@pytest.mark.parametrize("mounts", [
    MOUNTS_RO.replace(b"ro,relatime", b"rw,relatime"),
    MOUNTS_RO+b"55 20 0:44 / / ro - overlay overlay ro\n",
    b"garbled mountinfo",
    b"40 20 0:22 / /usr ro - overlay overlay ro\n",
])
def test_rw_missing_or_duplicate_rootfs_mounts_refused(mounts):
    with pytest.raises(Stage38Refused):
        _root_mount(mounts)


def test_route_parsers_allow_only_loopback_not_host_network():
    assert _routes4(V4_LO) == 1
    assert _routes6(V6_LO) == 1
    assert _routes4(V4_HEADER) == 0
    for bad in (
        V4_HEADER+b"eth0 00000000 0100A8C0 0003 0 0 0 00000000 0 0 0\n",
        V4_HEADER+b"wlan0 00000000 0100A8C0 0003 0 0 0 00000000 0 0 0\n",
        V4_HEADER+b"lo BAD 00000000 0001 0 0 0 000000FF 0 0 0\n",
        b"bad header\n",
    ):
        with pytest.raises(Stage38Refused):
            _routes4(bad)
    for bad in (
        V6_LO.replace(b" lo\n", b" eth0\n"),
        V6_LO.replace(b" 80 ", b" XX "),
        b"bad ipv6 route\n",
    ):
        with pytest.raises(Stage38Refused):
            _routes6(bad)


def test_production_and_unauthorized_host_fences_without_reading_proc(
        synthetic_host, monkeypatch):
    def never_read(path, *, limit):
        raise AssertionError("must refuse before reading any procfs")
    monkeypatch.setattr(probe, "_read_fixed_proc", never_read)
    kwargs = {
        "host_alias": HOST, "expected_nodename": NODE, "expected_gid": 1001,
        "operator_ack": True,
    }
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage38Refused):
        observe_authorized_process_kernel_posture(**kwargs)
    monkeypatch.delenv("MMT_PRODUCTION")
    for change in (
        {"operator_ack": False},
        {"expected_nodename": "unapproved"},
        {"expected_gid": 0},
        {"expected_gid": True},
        {"host_alias": "evil/../prod"},
    ):
        with pytest.raises(Stage38Refused):
            observe_authorized_process_kernel_posture(**{**kwargs, **change})
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    with pytest.raises(Stage38Refused):
        observe_authorized_process_kernel_posture(**kwargs)


def test_if_one_kernel_observation_disagrees_no_receipt_is_produced(
        synthetic_host):
    synthetic_host["/proc/self/mountinfo"] = MOUNTS_RO.replace(
        b"ro,relatime", b"rw,relatime")
    with pytest.raises(Stage38Refused, match="ROOT_FILESYSTEM"):
        collect()
    synthetic_host["/proc/self/mountinfo"] = MOUNTS_RO
    synthetic_host["/proc/self/net/route"] = (
        V4_HEADER+b"eth0 00000000 0100A8C0 0003 0 0 0 00000000 0 0 0\n")
    with pytest.raises(Stage38Refused, match="NONLOOPBACK"):
        collect()


def test_fixed_kernel_paths_only_and_no_silent_oversize_reads():
    with pytest.raises(Stage38Refused):
        probe._read_fixed_proc("/proc/self/environ", limit=32768)
    with pytest.raises(Stage38Refused):
        probe._read_fixed_proc("/etc/shadow", limit=32768)
    with pytest.raises(Stage38Refused):
        probe._read_fixed_proc("/proc/self/status", limit=999999)
    with pytest.raises(Stage38Refused):
        _status(b"x"*32769, expected_uid=1001, expected_gid=1001)


def test_cli_refuses_without_explicit_opt_in(capsys, synthetic_host):
    from naseri_markets.passive_kernel_posture_cli_stage38_v1 import main
    code = main([
        "--host-alias", HOST,
        "--expected-nodename", NODE,
        "--expected-gid", "1001",
    ])
    assert code == 2
    output = capsys.readouterr()
    assert "STAGE38_PASSIVE_PROCESS_PROBE_BLOCKED" in output.err
