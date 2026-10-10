"""A12 test actual mTLS owner leaf fingerprint pin before request bytes."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from naseri_markets.a11_mtls import (
    LoopbackMtlsExchange, TransportRefused, make_client_context,
    make_fixture_server_context, read_frame, send_frame,
)

OWNER_DNS = "private-owner.fixture"
CLIENT_DNS = "public-bot.fixture"


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(common):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def _certificate(key, subject, issuer, signer, *,
                 ca=False, dns=None, eku=None, expired=False):
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(_name(issuer))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(
            now - timedelta(days=1) if expired
            else now + timedelta(days=2)
        )
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), True)
    )
    if dns:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(dns)]), False,
        )
    if eku:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([eku]), False,
        )
    return builder.sign(private_key=signer, algorithm=hashes.SHA256())


def _write_cert(path, cert):
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path


def _write_key(path, key):
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    path.chmod(0o600)
    return path


@pytest.fixture()
def tls(tmp_path):
    ca_key = _key()
    ca_cert = _certificate(ca_key, "ci-fixture-ca", "ci-fixture-ca", ca_key, ca=True)
    ca_file = _write_cert(tmp_path / "ca.pem", ca_cert)
    owner_key = _key()
    owner_cert = _certificate(
        owner_key, OWNER_DNS, "ci-fixture-ca", ca_key,
        dns=OWNER_DNS, eku=ExtendedKeyUsageOID.SERVER_AUTH,
    )
    client_key = _key()
    client_cert = _certificate(
        client_key, CLIENT_DNS, "ci-fixture-ca", ca_key,
        dns=CLIENT_DNS, eku=ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    return {
        "ca": ca_file,
        "owner_cert": _write_cert(tmp_path / "owner.pem", owner_cert),
        "owner_key": _write_key(tmp_path / "owner.key", owner_key),
        "client_cert": _write_cert(tmp_path / "client.pem", client_cert),
        "client_key": _write_key(tmp_path / "client.key", client_key),
        "owner_der": owner_cert.public_bytes(serialization.Encoding.DER),
    }


async def _server(tls, accepted):
    context = make_fixture_server_context(
        ca=tls["ca"], cert=tls["owner_cert"], key=tls["owner_key"],
    )

    async def handle(reader, writer):
        try:
            blob = await asyncio.wait_for(read_frame(reader), timeout=1)
            accepted.append(blob)
            await send_frame(writer, b"fixture-ack")
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    return await asyncio.start_server(
        handle, host="127.0.0.1", port=0, ssl=context,
    )


@pytest.mark.asyncio
async def test_real_tls_pinned_owner_certificate_sends_request(tls):
    accepted = []
    server = await _server(tls, accepted)
    async with server:
        c = make_client_context(
            ca=tls["ca"], cert=tls["client_cert"], key=tls["client_key"],
        )
        exchange = LoopbackMtlsExchange(
            port=server.sockets[0].getsockname()[1],
            expected_owner_dns=OWNER_DNS, context=c,
            expected_owner_cert_sha256=hashlib.sha256(
                tls["owner_der"]
            ).hexdigest(),
        )
        assert await exchange(b"synthetic-test") == b"fixture-ack"
        assert accepted == [b"synthetic-test"]


@pytest.mark.asyncio
async def test_wrong_owner_cert_pin_rejected_before_any_request_bytes(tls):
    accepted = []
    server = await _server(tls, accepted)
    async with server:
        c = make_client_context(
            ca=tls["ca"], cert=tls["client_cert"], key=tls["client_key"],
        )
        exchange = LoopbackMtlsExchange(
            port=server.sockets[0].getsockname()[1],
            expected_owner_dns=OWNER_DNS, context=c,
            expected_owner_cert_sha256="f" * 64,
        )
        with pytest.raises(TransportRefused, match="EXCHANGE_UNAVAILABLE"):
            await exchange(b"must-not-be-delivered")
        assert accepted == []


def test_pin_bad_format_is_refused(tls):
    c = make_client_context(
        ca=tls["ca"], cert=tls["client_cert"], key=tls["client_key"],
    )
    with pytest.raises(TransportRefused, match="INVALID_OWNER_CERT_PIN"):
        LoopbackMtlsExchange(
            port=12345, expected_owner_dns=OWNER_DNS, context=c,
            expected_owner_cert_sha256="not-a-sha",
        )
