"""Stage21E tests never contact external TSA; real request audited in GH runner."""
from __future__ import annotations

import hashlib
import os
import stat

import pytest

from scripts import stage21e_public_tsa_precommit_v1 as stage


class FakeResponse:
    status = 200
    def __init__(self, url, content, override=None):
        self.url = override or url
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def geturl(self):
        return self.url
    def read(self, n):
        return self.content[:n]


class FakeTransport:
    def __init__(self, response_url=None):
        self.response_url = response_url
    def open(self, request, timeout):
        url = request.full_url
        return FakeResponse(
            url, b"-----BEGIN CERTIFICATE-----\n" + b"A"*200 +
            b"\n-----END CERTIFICATE-----\n",
            override=self.response_url,
        )


@pytest.fixture(autouse=True)
def research(monkeypatch, tmp_path):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.delenv("ST21E_EXPLICIT_ONE_SHOT_APPROVAL", raising=False)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))


def test_stamping_requires_exact_one_shot_ack_before_network_or_side_effect(tmp_path):
    with pytest.raises(ValueError, match="ONE_SHOT_ACK"):
        stage.main()
    assert not (tmp_path/"stage21e-brooks-future-research-precommit").exists()


def test_production_fence_precedes_network_and_directory_creation(monkeypatch,tmp_path):
    monkeypatch.setenv("ST21E_EXPLICIT_ONE_SHOT_APPROVAL", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="NO_LIVE"):
        stage.main()
    assert not (tmp_path/"stage21e-brooks-future-research-precommit").exists()


def test_only_reviewed_public_certificate_bytes_accepted():
    with pytest.raises(ValueError, match="PIN_MISMATCH"):
        stage._fetch_cert(FakeTransport(), "tsa.crt", "0"*64)


def test_unexpected_https_redirect_refused_even_with_matching_cert_pin():
    fake = FakeTransport(response_url="https://evil.invalid/signer.pem")
    expected = b"-----BEGIN CERTIFICATE-----\n" + b"A"*200 + b"\n-----END CERTIFICATE-----\n"
    with pytest.raises(ValueError, match="ENDPOINT_REFUSED"):
        stage._fetch_cert(fake, "tsa.crt", hashlib.sha256(expected).hexdigest())


def test_explicit_no_redirect_transport():
    with pytest.raises(ValueError, match="REDIRECT"):
        stage._NoRedirect().redirect_request(None, None, None, None)


def test_source_endpoints_are_https_only_and_literal_pins_are_full_sha():
    assert stage._CERT_ORIGIN == "https://freetsa.org/files/"
    assert stage._STAMP_URL == "https://freetsa.org/tsr"
    assert len(stage._ROOT_SHA256) == len(stage._SIGNER_SHA256) == 64
    assert stage._ROOT_SHA256 != stage._SIGNER_SHA256


def test_new_files_are_private_and_never_clobbered(tmp_path):
    path = stage._put(tmp_path,"original-plan.json",b"pinned")
    assert path.read_bytes() == b"pinned"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        stage._put(tmp_path,"original-plan.json",b"replay")
    assert path.read_bytes() == b"pinned"
    assert not os.path.islink(path)
