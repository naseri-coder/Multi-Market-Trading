"""Stage34 host probes: fake proc snapshots; real local TLS via socketpair.

No CI host is designated. No public network listener, firewall mutation,
Docker execution or production credential is involved.
"""
from __future__ import annotations

import hashlib
import json
import socket
import ssl
import threading

import pytest

pytest.importorskip("cryptography")

from naseri_markets.designated_host_readonly_probe_stage34_v1 import (
    HostLocalProbeReceipt, Stage34Refused, _approved_host,
    _real_local_tls, _socket_listeners, probe_designated_local_host,
)
from test_tls_boundary_stage31_v1 import (
    HOSTNAME, tls_material,  # noqa: F401
)

PROC_HEADER = b"  sl  local_address rem_address   st tx_queue rx_queue tr tm->when\n"
PROC4 = PROC_HEADER + (
    b"   0: 0100007F:01BB 00000000:0000 0A 0 0 0\n")
PROC6 = PROC_HEADER
SHA = "a"*64


@pytest.fixture(autouse=True)
def nonprod(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_DISPOSABLE_SANDBOX_HOST", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def test_passive_kernel_snapshot_decodes_ipv4_and_ipv6_loopback():
    assert _socket_listeners(PROC4, PROC6) == (("127.0.0.1", 443),)
    ipv6 = PROC_HEADER + (
        b"  0: 00000000000000000000000001000000:01BB "
        b"00000000000000000000000000000000:0000 0A 0 0 0\n")
    assert _socket_listeners(PROC_HEADER, ipv6) == (("::1", 443),)


@pytest.mark.parametrize("address", [
    b"00000000", b"0102A8C0", b"FFFFFFFF",
])
def test_wildcard_or_external_listener_hard_denial(address):
    proc = PROC_HEADER + b" 0: " + address + (
        b":01BB 00000000:0000 0A 0 0 0\n")
    with pytest.raises(Stage34Refused, match="NONLOOPBACK"):
        _socket_listeners(proc, PROC6)


@pytest.mark.parametrize("bad", [
    b"", b"invalid", b"\xff", b"x"*262145,
])
def test_missing_corrupt_or_oversized_proc_data_fail_closed(bad):
    with pytest.raises(Stage34Refused):
        _socket_listeners(bad, PROC6)


def test_actual_tls_handshake_over_private_socketpair_not_host_endpoint(
        tls_material, monkeypatch):  # noqa: F811
    cert_path, key_path, ca, pinned = tls_material
    client_socket, server_socket = socket.socketpair()
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    server_ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    server_ctx.load_cert_chain(str(cert_path), str(key_path))
    errors = []

    def server():
        try:
            with server_ctx.wrap_socket(server_socket, server_side=True) as tls:
                tls.settimeout(3)
                tls.recv(1)
        except (OSError, ssl.SSLError) as exc:
            errors.append(type(exc).__name__)

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    monkeypatch.setattr(socket, "create_connection",
                        lambda _where, timeout=3: client_socket)
    cipher, digest = _real_local_tls(
        hostname=HOSTNAME, port=443,
        trusted_ca_pem=ca, cert_sha256=pinned)
    assert cipher.startswith("TLS_")
    assert digest == pinned
    thread.join(timeout=4)
    assert not thread.is_alive()
    assert not errors


def test_actual_tls_pin_rejection_over_socketpair(tls_material, monkeypatch):  # noqa: F811
    cert_path, key_path, ca, pinned = tls_material
    client_socket, server_socket = socket.socketpair()
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    server_ctx.load_cert_chain(str(cert_path), str(key_path))

    def server():
        try:
            with server_ctx.wrap_socket(server_socket, server_side=True) as tls:
                tls.settimeout(3)
                tls.recv(1)
        except (OSError, ssl.SSLError):
            pass

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    monkeypatch.setattr(socket, "create_connection",
                        lambda _where, timeout=3: client_socket)
    with pytest.raises(Stage34Refused, match="TLS_PEER_PIN"):
        _real_local_tls(hostname=HOSTNAME, port=443,
                        trusted_ca_pem=ca, cert_sha256="0"*64)
    thread.join(timeout=4)
    assert not thread.is_alive()


def test_host_designation_ack_nonroot_nodename_and_production_fences(
        monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 1001)
    class U:
        nodename = "verified-disposable"
    monkeypatch.setattr("os.uname", lambda: U())
    _approved_host("sandbox_one", "verified-disposable", operator_ack=True)
    with pytest.raises(Stage34Refused, match="DESIGNATED"):
        _approved_host("sandbox_one", "other", operator_ack=True)
    with pytest.raises(Stage34Refused, match="DESIGNATED"):
        _approved_host("sandbox_one", "verified-disposable", operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage34Refused, match="DESIGNATED"):
        _approved_host("sandbox_one", "verified-disposable", operator_ack=True)


def test_explicit_host_readonly_receipt_has_no_installer_grant(
        monkeypatch, tls_material):  # noqa: F811
    _cert, _key, _ca, pinned = tls_material
    monkeypatch.setattr("os.geteuid", lambda: 1001)
    class U:
        nodename = "approved-disposable-1"
    monkeypatch.setattr("os.uname", lambda: U())
    import naseri_markets.designated_host_readonly_probe_stage34_v1 as mod
    monkeypatch.setattr(mod, "_read_proc",
                        lambda name: PROC4 if name.endswith("/tcp") else PROC6)
    monkeypatch.setattr(mod, "_trusted_ca", lambda _path: b"LOCAL_CA_FIXTURE")
    monkeypatch.setattr(mod, "_real_local_tls",
                        lambda **_k: ("TLS_AES_256_GCM_SHA384", pinned))
    receipt = probe_designated_local_host(
        host_alias="sandbox_one", expected_nodename="approved-disposable-1",
        tls_hostname=HOSTNAME, tls_port=443,
        ca_file=_cert, expected_certificate_sha256=pinned,
        operator_ack=True)
    assert isinstance(receipt, HostLocalProbeReceipt)
    assert receipt.real_loopback_tls_handshake_observed
    assert receipt.local_tls_cert_sha256 == pinned
    assert receipt.local_listener_count == 1
    assert not receipt.host_designation_independently_verified
    assert not receipt.external_tls_or_dns_verified
    assert not receipt.firewall_policy_independently_verified
    assert not receipt.outbound_network_denial_verified
    assert not receipt.reverse_proxy_verified
    assert not receipt.gvisor_isolation_verified
    assert not receipt.plugin_install_authorized
    assert not receipt.public_deployment_authorized
    assert not receipt.telegram_signal_authorized
    assert not receipt.broker_order_authorized
    obj = json.loads(receipt.evidence_json())
    assert obj["state"] == "ON_HOST_SELF_OBSERVATION_NOT_INDEPENDENT_ATTESTATION"
    assert receipt.evidence_sha256() == hashlib.sha256(
        receipt.evidence_json()).hexdigest()
    assert "LOCAL_CA_FIXTURE" not in receipt.evidence_json().decode()


def test_no_listening_443_or_external_socket_fails_before_tls(
        monkeypatch, tls_material):  # noqa: F811
    cert, *_ = tls_material
    monkeypatch.setattr("os.geteuid", lambda: 1001)
    class U:
        nodename = "approved-disposable-1"
    monkeypatch.setattr("os.uname", lambda: U())
    import naseri_markets.designated_host_readonly_probe_stage34_v1 as mod
    monkeypatch.setattr(mod, "_read_proc", lambda _p: PROC_HEADER)
    def forbid_tls(**kwargs):
        raise AssertionError("TLS must not be attempted")
    monkeypatch.setattr(mod, "_real_local_tls", forbid_tls)
    with pytest.raises(Stage34Refused, match="LISTENER_MISSING"):
        probe_designated_local_host(
            host_alias="sandbox_one", expected_nodename="approved-disposable-1",
            tls_hostname=HOSTNAME, tls_port=443,
            ca_file=cert, expected_certificate_sha256=SHA, operator_ack=True)


def test_nonpublic_port_and_root_user_are_denied(monkeypatch, tls_material):  # noqa: F811
    cert, *_ = tls_material
    monkeypatch.setattr("os.geteuid", lambda: 1001)
    class U:
        nodename = "disposable-test"
    monkeypatch.setattr("os.uname", lambda: U())
    with pytest.raises(Stage34Refused, match="PORT_443"):
        probe_designated_local_host(
            host_alias="sandbox_one", expected_nodename="disposable-test",
            tls_hostname=HOSTNAME, tls_port=8443,
            ca_file=cert, expected_certificate_sha256=SHA, operator_ack=True)
    monkeypatch.setattr("os.geteuid", lambda: 0)
    with pytest.raises(Stage34Refused, match="NONROOT_DESIGNATED"):
        probe_designated_local_host(
            host_alias="sandbox_one", expected_nodename="disposable-test",
            tls_hostname=HOSTNAME, tls_port=443,
            ca_file=cert, expected_certificate_sha256=SHA, operator_ack=True)


def test_loopback_tls_invalid_destination_or_pin_fails_closed():
    with pytest.raises(Stage34Refused):
        _real_local_tls(hostname="external.example.com", port=443,
                        trusted_ca_pem=b"bad", cert_sha256=SHA)
    with pytest.raises(Stage34Refused):
        _real_local_tls(hostname=HOSTNAME, port=True,
                        trusted_ca_pem=b"bad", cert_sha256=SHA)
