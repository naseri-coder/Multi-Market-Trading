"""Stage21G synthetic TLS source and outage custody, not a real future observation."""
from __future__ import annotations

import hashlib
import json
import ssl
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets import brooks_forward_source_custody_stage21g_v1 as collector

START = datetime(2026, 10, 20, tzinfo=UTC)
_PLAN = (Path(collector.__file__).resolve().parents[1] /
         "docs/evidence/STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json")
_DATE = "Tue, 20 Oct 2026 00:15:10 GMT"
_BODY = b'[[1792454400000,"100","102","98","101","12",1792455299999,"1000",7,"5","500","0"]]'


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("ST21G_EXPLICIT_MANUAL_CAPTURE", "1")
    now = START + timedelta(minutes=15, seconds=10)
    monkeypatch.setattr(collector, "_now", lambda: now)
    folder = tmp_path / "witness"
    folder.mkdir()
    originals = {
        "exact-frozen-brooks-plan.json": _PLAN.read_bytes(),
        "original-external-timestamp-response.tsr": b"mock-only-tsr",
        "tsa-root-public.pem": b"mock-only-test-root",
        "tsa-signer-public.pem": b"mock-only-test-signer",
    }
    monkeypatch.setattr(collector, "_EXPECTED_EVIDENCE", {
        key: hashlib.sha256(value).hexdigest() for key, value in originals.items()
    })
    for name, content in originals.items():
        (folder / name).write_bytes(content)
    expected_url = "https://fapi.binance.com" + collector._query(
        first_open=START, bars=1,
    )
    observation = collector.Stage21GTransportObservation(
        request_url=expected_url,
        original_body=_BODY,
        status=200,
        date_header=_DATE,
        content_type="application/json;charset=UTF-8",
        content_encoding="identity",
        tls_peer_certificate_sha256="e" * 64,
        tls_version="TLSv1.3",
        request_started_utc=now - timedelta(seconds=1),
        response_complete_utc=now,
        elapsed_seconds=1.0,
    )
    called = []
    def fake_admit(**kwargs):
        called.append(kwargs)
        assert kwargs["declared_request_url"] == expected_url
        assert kwargs["declared_tls_verified"] is True
        assert kwargs["previous_stage21c_receipt_bytes"] is None
        assert kwargs["original_provider_body_bytes"] == _BODY
        assert kwargs["operator_ack"] is True
        return {
            "receipt_sha256": "a"*64, "verdict": "LOCAL_QUARANTINE_ONLY",
            "connected_paper_enabled": False,
        }, b"open_at,close_at,open,high,low,close,volume\n"
    monkeypatch.setattr(collector, "stage21f_admit_future_kline_batch_to_quarantine",
                        fake_admit)
    monkeypatch.setattr(collector, "_download_pinned_https", lambda path: observation)
    return folder, observation, called


def _run(folder, tmp_path, **kw):
    return collector.run_stage21g_manual_first_window(
        witness_directory=folder,
        destination=tmp_path / "source-output",
        number_of_closed_bars=kw.get("count", 1),
        operator_ack=kw.get("ack", True),
    )


def test_exact_plan_and_pinned_original_witness_files(tmp_path, monkeypatch):
    folder, _, _ = _setup(monkeypatch, tmp_path)
    checked = collector._read_original_evidence(folder)
    assert checked["exact-frozen-brooks-plan.json"] == _PLAN.read_bytes()
    assert hashlib.sha256(checked["exact-frozen-brooks-plan.json"]).hexdigest() == (
        "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
    )
    (folder/"original-external-timestamp-response.tsr").write_bytes(b"untrusted")
    with pytest.raises(collector.Stage21GRefused, match="PIN_DRIFT"):
        collector._read_original_evidence(folder)


def test_real_evidence_filename_symlink_refused(tmp_path, monkeypatch):
    folder, _, _ = _setup(monkeypatch, tmp_path)
    file = folder / "tsa-root-public.pem"
    contents = file.read_bytes()
    file.unlink()
    (tmp_path / "elsewhere.pem").write_bytes(contents)
    file.symlink_to(tmp_path / "elsewhere.pem")
    with pytest.raises(collector.Stage21GRefused, match="LINKED"):
        collector._read_original_evidence(folder)


def test_manual_first_capture_preserves_original_and_transport_trace(tmp_path, monkeypatch):
    folder, _, called = _setup(monkeypatch, tmp_path)
    receipt = _run(folder, tmp_path)
    output = tmp_path/"source-output"
    assert len(called) == 1
    assert (output/"original-venue-response.json").read_bytes() == _BODY
    assert receipt["original_body_sha256"] == hashlib.sha256(_BODY).hexdigest()
    assert receipt["client_observed_tls_version"] == "TLSv1.3"
    assert receipt["client_observed_tls_peer_certificate_sha256"] == "e"*64
    assert receipt["client_clock_independently_attested"] is False
    assert receipt["provider_http_date_independently_authenticated"] is False
    assert receipt["source_venue_signature_verified"] is False
    assert receipt["actual_forward_brooks_decisions_executed"] is False
    assert receipt["forward_paper_enabled"] is False
    assert receipt["live_trading_authorized"] is False
    assert receipt["production_modified"] is False
    assert "failure-ledger.json" not in [p.name for p in output.iterdir()]
    assert (output/"stage21f-quarantine-receipt.json").is_file()
    with pytest.raises(collector.Stage21GRefused, match="FRESH"):
        _run(folder, tmp_path)


@pytest.mark.parametrize("mutate,match", [
    ({"status": 302}, "SOURCE_OBSERVATION"),
    ({"status": 403}, "SOURCE_OBSERVATION"),
    ({"date_header": ""}, "DATE_REQUIRED"),
    ({"date_header": "Mon, 19 Oct 2026 00:00:00 GMT"}, "CLOCK_DRIFT"),
    ({"content_type": "text/html"}, "SOURCE_OBSERVATION"),
    ({"content_encoding": "gzip"}, "SOURCE_OBSERVATION"),
    ({"tls_version": "TLSv1.1"}, "SOURCE_OBSERVATION"),
    ({"tls_peer_certificate_sha256": "not-a-sha"}, "SOURCE_OBSERVATION"),
    ({"elapsed_seconds": 32.0}, "SOURCE_OBSERVATION"),
    ({"request_url": "https://evil.invalid/klines"}, "SOURCE_OBSERVATION"),
])
def test_bad_http_status_header_clock_and_tls_rejected(tmp_path, monkeypatch, mutate, match):
    folder, observation, _ = _setup(monkeypatch, tmp_path)
    with pytest.raises(collector.Stage21GRefused, match=match):
        collector._prepare_admission(
            replace(observation, **mutate),
            requested_url=observation.request_url,
            last_close=START + timedelta(minutes=15),
            witness=collector._read_original_evidence(folder),
        )


def test_source_download_failure_ledger_does_not_invent_provider_outage(tmp_path, monkeypatch):
    folder, _, _ = _setup(monkeypatch, tmp_path)
    calls = []
    def denied(_path):
        calls.append(True)
        raise collector.Stage21GRefused(
            "ST21G_NETWORK_OR_TLS_FAILURE_NOT_EXCHANGE_OUTAGE"
        )
    monkeypatch.setattr(collector, "_download_pinned_https", denied)
    with pytest.raises(collector.Stage21GRefused, match="NOT_EXCHANGE_OUTAGE"):
        _run(folder, tmp_path)
    assert len(calls) == 1
    failure = json.loads((tmp_path/"source-output"/"failure-ledger.json").read_bytes())
    assert failure["provider_outage_proven"] is False
    assert failure["automatic_retry_performed"] is False
    assert failure["data_filled_or_backdated"] is False
    assert failure["paper_enabled"] is False
    assert not (tmp_path/"source-output"/"canonical-reviewed-closed-candles.csv").exists()


def test_early_capture_and_stale_lookback_rejected_prior_to_network(tmp_path, monkeypatch):
    folder, _, _ = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(collector, "_download_pinned_https",
                        lambda _: pytest.fail("network was attempted"))
    monkeypatch.setattr(collector, "_now",
                        lambda: START + timedelta(minutes=15, seconds=4))
    with pytest.raises(collector.Stage21GRefused, match="TOO_LATE"):
        _run(folder, tmp_path)
    monkeypatch.setattr(collector, "_now",
                        lambda: START + timedelta(days=2))
    with pytest.raises(collector.Stage21GRefused, match="TOO_LATE"):
        _run(folder, tmp_path)
    assert not (tmp_path/"source-output").exists()


def test_no_unapproved_auth_or_production_and_invalid_barcount(tmp_path, monkeypatch):
    folder, _, _ = _setup(monkeypatch, tmp_path)
    monkeypatch.delenv("ST21G_EXPLICIT_MANUAL_CAPTURE", raising=False)
    with pytest.raises(collector.Stage21GRefused, match="EXPLICIT_MANUAL"):
        _run(folder, tmp_path)
    monkeypatch.setenv("ST21G_EXPLICIT_MANUAL_CAPTURE", "1")
    with pytest.raises(ValueError, match="NONPRODUCTION"):
        _run(folder, tmp_path, ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="NONPRODUCTION"):
        _run(folder, tmp_path)
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    with pytest.raises(collector.Stage21GRefused, match="1_TO_96"):
        _run(folder, tmp_path, count=97)


def test_same_window_original_revision_is_flagged_not_replaced():
    before=b'[[1792454400000,"100","101"]]'
    after=b'[[1792454400000,"100","102"]]'
    change=collector.compare_stage21g_same_window_source_bytes(
        old_original_response=before, newly_observed_response=after,
    )
    assert change["raw_source_bytes_changed"] is True
    assert change["needs_manual_correction_investigation"] is True
    assert change["replace_original_source_permitted"] is False
    assert change["provider_revision_proven"] is False
    repeat=collector.compare_stage21g_same_window_source_bytes(
        old_original_response=before, newly_observed_response=before,
    )
    assert repeat["raw_source_bytes_changed"] is False
    assert repeat["needs_manual_correction_investigation"] is False


def test_direct_tls_transport_exactly_one_no_proxy_or_retry(monkeypatch):
    started=START+timedelta(minutes=15, seconds=10)
    monkeypatch.setattr(collector,"_now",lambda:started)
    monkeypatch.setattr(collector.time, "monotonic", lambda: 40.0)
    created=[]
    class Socket:
        def getpeercert(self,binary_form=False):
            assert binary_form is True
            return b"test-ca-validated-public-certificate"
        def version(self):
            return "TLSv1.3"
    class Response:
        status=200
        def getheader(self,name,default=None):
            return {"Date":_DATE,"Content-Type":"application/json",
                    "Content-Encoding":"identity"}.get(name,default)
        def read(self,n):
            assert n == 131073
            return _BODY
    class FakeHTTPS:
        def __init__(self,host,timeout,context):
            assert host=="fapi.binance.com"
            assert timeout==15
            assert isinstance(context,ssl.SSLContext)
            assert context.verify_mode==ssl.CERT_REQUIRED
            assert context.check_hostname is True
            created.append(self)
            self.sock=None
        def connect(self):
            self.sock=Socket()
        def request(self,method,path,headers):
            assert method=="GET"
            assert path.startswith("/fapi/v1/klines?")
            assert headers["Accept-Encoding"]=="identity"
            assert "Authorization" not in headers
        def getresponse(self):
            return Response()
        def close(self):
            self.sock=None
    monkeypatch.setattr(collector.http.client,"HTTPSConnection", FakeHTTPS)
    source=collector._download_pinned_https(collector._query(first_open=START,bars=1))
    assert len(created)==1
    assert source.status==200
    assert source.original_body==_BODY
    assert source.tls_peer_certificate_sha256==hashlib.sha256(
        b"test-ca-validated-public-certificate"
    ).hexdigest()


def test_insecure_redirect_and_absent_peer_certificate_refuse(monkeypatch):
    with pytest.raises(collector.Stage21GRefused,match="ENDPOINT"):
        collector._download_pinned_https("/evil?token=1")
