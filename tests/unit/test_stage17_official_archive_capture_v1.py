"""Stage17 tests: fully offline transport stubs, never real venue receipts."""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime

import pytest

from naseri_markets import stage17_official_archive_capture_v1 as s17
from naseri_markets.binance_vision_archive_stage16_v1 import VisionArchiveRefused


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _synthetic_month(*, year=2024, month=1):
    first = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year, month + 1, 1, tzinfo=UTC)
    rows = []
    for n in range(int((end - first).total_seconds() / 900)):
        opened = int(first.timestamp() * 1000) + n * 900_000
        rows.append(f"{opened},100,101,99,100,10,{opened+899999},1000,10,4,400,0")
    payload = ("\n".join(rows) + "\n").encode()
    name = f"BTCUSDT-15m-{year}-{month:02d}.zip"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name[:-4] + ".csv", payload)
    blob = out.getvalue()
    check = (hashlib.sha256(blob).hexdigest() + "  " + name + "\n").encode()
    return blob, check


def _stub(monkeypatch, zip_blob, checksum):
    urls = []
    def fetch(url, limit):
        urls.append(url)
        return checksum if url.endswith(".CHECKSUM") else zip_blob
    monkeypatch.setattr(s17, "_get_exact", fetch)
    return urls


def test_transport_capture_then_actual_stage12_quality_gate(tmp_path, monkeypatch):
    blob, chk = _synthetic_month()
    urls = _stub(monkeypatch, blob, chk)
    result = s17.capture_stage17_vision_month(year=2024, month=1, operator_ack=True)
    assert result.archive.count == 2976
    assert len(urls) == 2 and urls[0].endswith("BTCUSDT-15m-2024-01.zip")
    assert urls[1] == urls[0] + ".CHECKSUM"
    assert result.operator_hashes_preapproved is False
    assert result.source_independently_authenticated is False
    assert result.historical_revision_absence_proven is False
    assert result.economic_backtest_run is False
    dst = tmp_path / "new-private-research-capture"
    report = s17.persist_research_capture(result, destination=dst)
    assert report["rows"] == 2976
    assert report["preapproved_hashes_matched"] is False
    assert report["source_independently_authenticated"] is False
    assert report["retrieval_clock_independently_attested"] is False
    assert report["production_authorized"] is False
    assert report["stage12_evidence_sha256"]
    assert (dst / "canonical-month.csv").read_bytes() == result.archive.canonical_csv_bytes
    assert (dst / "BTCUSDT-15m-2024-01.zip").read_bytes() == blob
    with pytest.raises(s17.Stage17Refused, match="FRESH_ABSOLUTE"):
        s17.persist_research_capture(result, destination=dst)


def test_preapproved_pins_are_exact_but_not_authentication(monkeypatch):
    blob, chk = _synthetic_month()
    _stub(monkeypatch, blob, chk)
    pin_zip, pin_chk = hashlib.sha256(blob).hexdigest(), hashlib.sha256(chk).hexdigest()
    result = s17.capture_stage17_vision_month(
        year=2024, month=1, operator_ack=True,
        expected_zip_sha256=pin_zip, expected_checksum_sha256=pin_chk,
    )
    assert result.operator_hashes_preapproved
    assert not result.source_independently_authenticated
    with pytest.raises(s17.Stage17Refused, match="PIN_MISMATCH"):
        s17.capture_stage17_vision_month(
            year=2024, month=1, operator_ack=True,
            expected_zip_sha256="0" * 64, expected_checksum_sha256=pin_chk,
        )


@pytest.mark.parametrize("year,month", [(2030, 12), (2019, 12), (2024, 13), (2031, 1)])
def test_invalid_or_open_month_never_makes_network_call(monkeypatch, year, month):
    def forbidden(*args, **kwargs):
        pytest.fail("network attempted for disallowed month")
    monkeypatch.setattr(s17, "_get_exact", forbidden)
    with pytest.raises(s17.Stage17Refused):
        s17.capture_stage17_vision_month(year=year, month=month, operator_ack=True)


def test_production_and_consent_fences_precede_all_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network attempted without approval")
    monkeypatch.setattr(s17, "_get_exact", forbidden)
    with pytest.raises(s17.Stage17Refused, match="ACK"):
        s17.capture_stage17_vision_month(year=2024, month=1, operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(s17.Stage17Refused, match="NONPRODUCTION"):
        s17.capture_stage17_vision_month(year=2024, month=1, operator_ack=True)


def test_half_pins_and_untrusted_checksum_fail_closed(monkeypatch):
    blob, chk = _synthetic_month()
    urls = _stub(monkeypatch, blob, chk)
    with pytest.raises(s17.Stage17Refused, match="BOTH_PREAPPROVED"):
        s17.capture_stage17_vision_month(
            year=2024, month=1, operator_ack=True,
            expected_zip_sha256=hashlib.sha256(blob).hexdigest(),
        )
    assert not urls
    _stub(monkeypatch, blob, b"0" * 64 + b"  other.zip\n")
    with pytest.raises(VisionArchiveRefused, match="CHECKSUM"):
        s17.capture_stage17_vision_month(year=2024, month=1, operator_ack=True)


def test_capture_contents_tampering_and_unsafe_target_refused(monkeypatch, tmp_path):
    blob, chk = _synthetic_month()
    _stub(monkeypatch, blob, chk)
    result = s17.capture_stage17_vision_month(year=2024, month=1, operator_ack=True)
    from dataclasses import replace
    forged = replace(result, original_zip=result.original_zip + b"x")
    with pytest.raises(s17.Stage17Refused, match="CHANGED"):
        s17.persist_research_capture(forged, destination=tmp_path / "never-created")
    assert not (tmp_path / "never-created").exists()
    forbidden = tmp_path / "production_source"
    forbidden.mkdir()
    with pytest.raises(s17.Stage17Refused, match="UNSAFE"):
        s17.persist_research_capture(result, destination=forbidden / "no")


def test_real_http_responses_must_match_exact_requested_url(monkeypatch):
    class Reply:
        status = 200
        headers = {"Content-Length": "3", "Content-Encoding": "identity"}
        def __init__(self, url): self.url = url
        def geturl(self): return self.url + "?redirected=yes"
        def read(self, n): return b"abc"
        def __enter__(self): return self
        def __exit__(self, *args): return False
    class Opener:
        def open(self, req, timeout):
            return Reply(req.full_url)
    monkeypatch.setattr(s17.urllib.request, "build_opener", lambda *args: Opener())
    url, _ = s17._url_and_month(2024, 1)
    with pytest.raises(s17.Stage17Refused, match="UNEXPECTED_HTTPS"):
        s17._get_exact(url, 256)


def test_response_size_limit_prevents_reading_unbounded_body(monkeypatch):
    class Reply:
        status = 200
        headers = {"Content-Length": "257"}
        def __init__(self, url): self.url = url
        def geturl(self): return self.url
        def read(self, n): pytest.fail("must not read oversize claimed payload")
        def __enter__(self): return self
        def __exit__(self, *args): return False
    class Opener:
        def open(self, req, timeout): return Reply(req.full_url)
    monkeypatch.setattr(s17.urllib.request, "build_opener", lambda *args: Opener())
    _, url = s17._url_and_month(2024, 1)
    with pytest.raises(s17.Stage17Refused, match="TOO_LARGE"):
        s17._get_exact(url, 256)


def test_refuse_non_official_endpoints_even_before_http(monkeypatch):
    monkeypatch.setattr(
        s17.urllib.request, "build_opener",
        lambda *args: pytest.fail("unexpected HTTP"),
    )
    with pytest.raises(s17.Stage17Refused, match="OFFICIAL_ENDPOINT"):
        s17._get_exact("https://example.org/market.zip", 100)
