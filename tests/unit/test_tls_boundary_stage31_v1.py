"""Stage31 test actual TLS1.3 in MemoryBIO and in-memory ASGI authority.

No socket, public listener, production cert/key or network I/O. Certificate
and private key are ephemeral disposable GitHub test fixtures only.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import ssl
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("cryptography")
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.authenticated_developer_intake_stage29_v1 import _LOGIN_DOMAIN
from naseri_markets.offline_developer_api_stage30_v1 import Stage30Refused
from naseri_markets.tls_boundary_stage31_v1 import (
    Stage31Refused, StrictDeveloperAuthorityGate, verify_hermetic_tls_client,
)
from test_durable_isolated_core_gate_stage22_v1 import host  # noqa: F401
from test_signed_core_candidate_stage23_v1 import trusted  # noqa: F401
from test_publisher_package_registry_stage28_v1 import (
    TENANT, PUB, KEY_ID, roster, submit_args,  # noqa: F401
)
from test_authenticated_developer_intake_stage29_v1 import intake  # noqa: F401
from test_offline_developer_api_stage30_v1 import api  # noqa: F401

HOSTNAME = "developers.staging.invalid"


@pytest.fixture
def tls_material(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTNAME)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(private.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc)-timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc)+timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOSTNAME)]),
                           critical=False)
            .sign(private, hashes.SHA256()))
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    cert_path = tmp_path/"ephemeral.pem"
    key_path = tmp_path/"ephemeral.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(private_pem)
    cert_path.chmod(0o600)
    key_path.chmod(0o600)
    return cert_path, key_path, cert_pem, hashlib.sha256(cert_der).hexdigest()


def tls_context_pair(tls_material, *, hostname=HOSTNAME,
                     trusted=True, tls13=True, hostname_check=True):
    cert_path, key_path, pem, digest = tls_material
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = ssl.TLSVersion.TLSv1_3
    server.maximum_version = ssl.TLSVersion.TLSv1_3
    server.load_cert_chain(str(cert_path), str(key_path))
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client.minimum_version = (ssl.TLSVersion.TLSv1_3 if tls13
                              else ssl.TLSVersion.TLSv1_2)
    client.check_hostname = hostname_check
    client.verify_mode = ssl.CERT_REQUIRED
    if trusted:
        client.load_verify_locations(cadata=pem.decode("ascii"))
    incoming_client = ssl.MemoryBIO()
    outgoing_client = ssl.MemoryBIO()
    incoming_server = ssl.MemoryBIO()
    outgoing_server = ssl.MemoryBIO()
    c = client.wrap_bio(incoming_client, outgoing_client,
                        server_hostname=hostname)
    s = server.wrap_bio(incoming_server, outgoing_server, server_side=True)
    ready_c = ready_s = False
    for _ in range(35):
        if not ready_c:
            try:
                c.do_handshake()
                ready_c = True
            except ssl.SSLWantReadError:
                pass
        if outgoing_client.pending:
            incoming_server.write(outgoing_client.read())
        if not ready_s:
            try:
                s.do_handshake()
                ready_s = True
            except ssl.SSLWantReadError:
                pass
        if outgoing_server.pending:
            incoming_client.write(outgoing_server.read())
        if ready_c and ready_s:
            return c, digest
    raise AssertionError("Ephemeral TLS MemoryBIO handshake did not complete")


def call(edge, path="/v1/developers/challenge", data=None, *, token=None,
         headers=(), scheme="https", http_version="1.1",
         root_path="", server=None, raw_path=None,
         query=b"", method="POST", client="127.0.0.1"):
    body = canonical(data if data is not None else {})
    hdrs = [(b"host", HOSTNAME.encode("ascii"))]
    if method=="POST":
        hdrs.append((b"content-type", b"application/json"))
    if token is not None:
        hdrs.append((b"authorization", ("Bearer "+token).encode("ascii")))
    hdrs.extend(headers)
    events = []
    async def send(msg):
        events.append(msg)
    used = [False]
    async def receive():
        if used[0]:
            raise AssertionError("unexpected second ASGI receive")
        used[0] = True
        return {"type":"http.request","body": b"" if method=="GET" else body,
                "more_body":False}
    scope = {
        "type":"http","scheme":scheme,"http_version":http_version,
        "method":method,"path":path,"root_path":root_path,
        "raw_path":path.encode("ascii") if raw_path is None else raw_path,
        "query_string":query,"client":(client,9012),
        "server":server or (HOSTNAME,443),"headers":hdrs,
    }
    asyncio.run(edge(scope, receive, send))
    assert len(events)==2
    assert events[0]["type"]=="http.response.start"
    assert events[1]["type"]=="http.response.body"
    reply=json.loads(events[1]["body"])
    return events[0]["status"],reply,events[0]["headers"]


def test_actual_hermetic_tls13_cert_chain_hostname_and_digest(tls_material):
    socket, digest = tls_context_pair(tls_material)
    report = verify_hermetic_tls_client(
        socket, trusted_hostname=HOSTNAME,
        expected_certificate_sha256=digest, operator_ack=True)
    assert report.tls_version=="TLSv1.3"
    assert report.hostname==HOSTNAME
    assert report.cipher.startswith("TLS_")
    assert report.certificate_der_sha256==digest
    assert report.lab_certificate_chain_and_hostname_checked
    assert not report.public_https_service_tested
    assert not report.reverse_proxy_trust_independently_verified
    assert not report.external_host_or_kernel_attested
    assert not report.public_api_deployment_authorized
    assert not report.untrusted_core_execution_authorized
    assert not report.broker_order_authorized


def test_wrong_trust_chain_wrong_dns_name_and_missing_cert_fail(tls_material):
    with pytest.raises(ssl.SSLError):
        tls_context_pair(tls_material,trusted=False)
    with pytest.raises(ssl.SSLCertVerificationError):
        tls_context_pair(tls_material,hostname="impostor.staging.invalid")
    channel,digest=tls_context_pair(tls_material)
    with pytest.raises(Stage31Refused,match="PIN_MISMATCH"):
        verify_hermetic_tls_client(
            channel,trusted_hostname=HOSTNAME,
            expected_certificate_sha256="0"*64,operator_ack=True)
    with pytest.raises(Stage31Refused,match="PINNED_CLIENT"):
        verify_hermetic_tls_client(
            b"forged-asgi-https",trusted_hostname=HOSTNAME,
            expected_certificate_sha256=digest,operator_ack=True)


def test_tls_context_must_require_hostname_and_tls13(tls_material):
    c,d=tls_context_pair(tls_material,hostname_check=False)
    with pytest.raises(Stage31Refused,match="CLIENT_CA_HOSTNAME_TLS13"):
        verify_hermetic_tls_client(
            c,trusted_hostname=HOSTNAME,
            expected_certificate_sha256=d,operator_ack=True)
    c,d=tls_context_pair(tls_material,tls13=False)
    with pytest.raises(Stage31Refused,match="CLIENT_CA_HOSTNAME_TLS13"):
        verify_hermetic_tls_client(
            c,trusted_hostname=HOSTNAME,
            expected_certificate_sha256=d,operator_ack=True)
    c,d=tls_context_pair(tls_material)
    with pytest.raises(Stage31Refused):
        verify_hermetic_tls_client(
            c,trusted_hostname="other.staging.invalid",
            expected_certificate_sha256=d,operator_ack=True)


def test_approved_authority_wraps_real_stage30_signed_login_and_inert_zip(api):
    app, _login, _clock, signer, original = api
    edge=StrictDeveloperAuthorityGate(
        app, approved_authority=HOSTNAME,operator_ack=True)
    status,challenge,_=call(edge,data={
        "tenant_id":TENANT,"publisher":PUB,"key_id":KEY_ID})
    assert status==200,challenge
    claim=challenge["challenge"]
    sig=base64.b64encode(
        signer.sign(_LOGIN_DOMAIN+canonical(claim))).decode("ascii")
    status,ticket,headers=call(
        edge,"/v1/developers/session",
        {"challenge":claim,"signature_b64":sig})
    assert status==200,ticket
    token=ticket["token"]
    assert dict(headers)[b"cache-control"].startswith(b"no-store")
    args=submit_args(original)
    status,result,_=call(edge,"/v1/developers/quarantine",{
        "binding_id":"binding_a",
        "package_b64":base64.b64encode(args["package"]).decode("ascii"),
        "candidate_b64":base64.b64encode(args["signed_candidate"]).decode("ascii"),
    },token=token)
    assert status==202,result
    assert result["state"]=="QUARANTINED_PUBLIC_SOURCE_NOT_EXECUTABLE"
    assert not result["source_execution_authorized"]
    assert not result["broker_order_authorized"]
    assert original[1].state(TENANT,"binding_a")["state"]=="DISABLED"
    assert call(edge,"/v1/developers/me",method="GET",token=token)[0]==403


@pytest.mark.parametrize("changed", [
    {"headers":[(b"host",HOSTNAME.encode("ascii"))]},
    {"headers":[(b"host",b"attacker.invalid")]},
    {"headers":[(b"Host",HOSTNAME.encode("ascii"))]},
    {"headers":[(b"x-forwarded-proto",b"https")]},
    {"headers":[(b"forwarded",b"for=1.2.3.4")]},
    {"headers":[(b":authority",HOSTNAME.encode("ascii"))]},
    {"scheme":"http"},
    {"http_version":"1.0"},
    {"root_path":"/proxy"},
    {"server":("other.staging.invalid",443)},
    {"server":(HOSTNAME,80)},
    {"raw_path":b"/v1/developers/%63hallenge"},
    {"query":b"token=x"},
    {"path":"/v1/developers/../challenge"},
    {"path":"/v1/developers//challenge"},
])
def test_host_smuggling_forwarded_host_and_normalization_denied(api,changed):
    edge=StrictDeveloperAuthorityGate(
        api[0],approved_authority=HOSTNAME,operator_ack=True)
    args={"tenant_id":TENANT,"publisher":PUB,"key_id":KEY_ID}
    status,returned,_=call(edge,data=args,**changed)
    assert status in (400,403,405,404)
    assert returned.get("challenge") is None
    assert not api[-1][1].db.execute(
        "SELECT 1 FROM secure29_challenges").fetchone()


def test_request_headers_are_checked_before_credential_use(api):
    edge=StrictDeveloperAuthorityGate(
        api[0],approved_authority=HOSTNAME,operator_ack=True)
    assert call(edge,headers=[(b"cookie",b"session=secret")])[0]==400
    assert call(edge,headers=[(b"transfer-encoding",b"chunked")])[0]==400
    assert call(edge,headers=[(b"origin",b"https://attacker.invalid")])[0]==400
    assert call(edge,headers=[(b"authorization",b"Bearer secret")])[0]==400


def test_private_operator_ack_and_production_flip_fail_closed(api,monkeypatch):
    gateway=api[0]
    with pytest.raises(Stage31Refused):
        StrictDeveloperAuthorityGate(
            gateway,approved_authority=HOSTNAME,operator_ack=False)
    with pytest.raises(Stage31Refused):
        StrictDeveloperAuthorityGate(
            gateway,approved_authority="*.invalid",operator_ack=True)
    edge=StrictDeveloperAuthorityGate(
        gateway,approved_authority=HOSTNAME,operator_ack=True)
    monkeypatch.setenv("MMT_PRODUCTION","1")
    code,answer,_=call(edge,data={
        "tenant_id":TENANT,"publisher":PUB,"key_id":KEY_ID})
    assert code==403 and "challenge" not in answer


def test_scope_https_claim_does_not_alone_issue_tls_proof(api):
    edge=StrictDeveloperAuthorityGate(
        api[0],approved_authority=HOSTNAME,operator_ack=True)
    assert not hasattr(edge,"tls_authenticated")
    # ASGI scope metadata is easily forged by a malicious in-process
    # caller. The wrapper only checks the authority *syntax*. No test
    # may conflate this with the real SSLObject verification above.
    assert not hasattr(edge,"public_deployment_authorized")
