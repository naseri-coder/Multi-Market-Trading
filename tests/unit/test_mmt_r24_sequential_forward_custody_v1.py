"""R24 SYNTHETIC market fixtures: real receipt-chain logic, mocked TSA only."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest

from naseri_markets import brooks_forward_source_custody_stage21g_v1 as g
from naseri_markets import brooks_future_kline_admission_stage21f_v1 as f
from naseri_markets import brooks_sequential_forward_custody_mmt_r24_v1 as r24
from scripts import mmt_r24_manual_sequential_forward_custody_v1 as cli

START = datetime(2026, 10, 20, tzinfo=UTC)
BAR = timedelta(minutes=15)
PLAN = (Path(__file__).resolve().parents[2] / "docs/evidence/"
        "STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json")


def _bars(index, count):
    items = []
    for n in range(index, index + count):
        opened = int((START + n*BAR).timestamp()*1000)
        items.append([
            opened, "100", "105", "99", "102", "10",
            opened+899999, "1000", 5, "4", "400", "0",
        ])
    return json.dumps(items, separators=(",", ":")).encode("ascii")


def _observation(index, count):
    ended = START + (index+count)*BAR + timedelta(seconds=10)
    return g.Stage21GTransportObservation(
        request_url="https://fapi.binance.com" + g._query(
            first_open=START+index*BAR, bars=count,
        ),
        original_body=_bars(index,count),
        status=200, date_header=format_datetime(ended, usegmt=True),
        content_type="application/json", content_encoding="identity",
        tls_peer_certificate_sha256="a"*64, tls_version="TLSv1.3",
        request_started_utc=ended-timedelta(seconds=1),
        response_complete_utc=ended, elapsed_seconds=1.0,
    )


@pytest.fixture
def chain(tmp_path,monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION","1")
    monkeypatch.delenv("MMT_PRODUCTION",raising=False)
    monkeypatch.setenv("ST21G_EXPLICIT_MANUAL_CAPTURE","1")
    monkeypatch.setenv("MMT_R24_EXPLICIT_ONE_READONLY_GET","1")
    folder=tmp_path/"original-witness"
    folder.mkdir()
    originals={
        "exact-frozen-brooks-plan.json":PLAN.read_bytes(),
        "original-external-timestamp-response.tsr":b"SYNTHETIC-token",
        "tsa-root-public.pem":b"SYNTHETIC-root",
        "tsa-signer-public.pem":b"SYNTHETIC-signer",
    }
    monkeypatch.setattr(g,"_EXPECTED_EVIDENCE",{
        k:hashlib.sha256(v).hexdigest() for k,v in originals.items()
    })
    for name,data in originals.items():
        (folder/name).write_bytes(data)
    monkeypatch.setattr(f,"_CANONICAL_TOKEN_SHA",
        hashlib.sha256(originals["original-external-timestamp-response.tsr"]).hexdigest())
    monkeypatch.setattr(f,"_CANONICAL_CA_SHA",
        hashlib.sha256(originals["tsa-root-public.pem"]).hexdigest())
    monkeypatch.setattr(f,"_CANONICAL_SIGNER_SHA",
        hashlib.sha256(originals["tsa-signer-public.pem"]).hexdigest())
    monkeypatch.setattr(f,"verify_brooks_rfc3161_precommitment",lambda **kw:{
        "cryptographic_tsa_signature_and_imprint_valid":True,
        "independent_tsa_provider_assessed":False,
        "paper_mode_authorized":False,
        "signed_timestamp_utc":"2026-10-16T01:36:00+00:00",
    })
    first=_observation(0,1)
    monkeypatch.setattr(g,"_now",lambda:first.response_complete_utc)
    monkeypatch.setattr(g,"_download_pinned_https",lambda path:first)
    source=tmp_path/"first"
    g.run_stage21g_manual_first_window(
        witness_directory=folder,destination=source,
        number_of_closed_bars=1,operator_ack=True,
    )
    return folder,source


def _replay(chain,*rest):
    return r24.stage24_replay_all_previous_batches(
        previous_directories=(chain[1],*rest),
        witness=g._read_original_evidence(chain[0]),
        operator_ack=True,
    )


def _extend(chain,tmp_path,monkeypatch):
    source=_observation(1,4)
    monkeypatch.setattr(r24,"_now",lambda:source.response_complete_utc)
    calls=[]
    def fake_fetch(path):
        calls.append(path)
        return source
    monkeypatch.setattr(r24,"_download_pinned_https",fake_fetch)
    output=tmp_path/"next"
    result=r24.run_stage24_manual_next_batch(
        witness_directory=chain[0],previous_directories=(chain[1],),
        destination=output,number_of_closed_bars=4,operator_ack=True,
    )
    return output,result,calls


def test_one_original_batch_replayed_and_second_batch_chained(chain,tmp_path,monkeypatch):
    original=_replay(chain)
    assert original.accepted_batches==1
    assert original.next_open_utc==START+BAR
    output,result,calls=_extend(chain,tmp_path,monkeypatch)
    assert len(calls)==1
    assert "startTime=1792455300000" in calls[0]
    assert result["local_stage21c_sequence"]==2
    assert result["connected_paper_started"] is False
    assert result["source_independently_signed"] is False
    assert (output/"original-venue-response.json").read_bytes()==_bars(1,4)
    resumed=_replay(chain,output)
    assert resumed.accepted_batches==2
    assert resumed.next_open_utc==START+BAR*5
    assert resumed.previous_batch_digest!=original.previous_batch_digest


@pytest.mark.parametrize("filename",(
    "attempt.json","original-venue-response.json",
    "canonical-reviewed-closed-candles.csv",
    "stage21f-quarantine-receipt.json","source-tls-http-observation.json",
))
def test_tampered_previous_source_is_rejected(chain,filename):
    path=chain[1]/filename
    body=path.read_bytes()
    changed=bytearray(body)
    changed[len(changed)//2]^=1
    path.write_bytes(changed)
    with pytest.raises(ValueError):
        _replay(chain)


def test_missing_extra_file_symlink_and_repeated_batch_refuse(chain,tmp_path):
    leftover=chain[1]/"failure-ledger.json"
    leftover.write_bytes(b"{}")
    with pytest.raises(r24.Stage24CustodyRefused,match="UNEXPECTED"):
        _replay(chain)
    leftover.unlink()
    raw=chain[1]/"original-venue-response.json"
    data=raw.read_bytes()
    raw.unlink()
    outside=tmp_path/"outside-source"
    outside.write_bytes(data)
    raw.symlink_to(outside)
    with pytest.raises(r24.Stage24CustodyRefused):
        _replay(chain)
    raw.unlink()
    raw.write_bytes(data)
    with pytest.raises(r24.Stage24CustodyRefused):
        _replay(chain,chain[1])


def test_continuation_link_tamper_and_reorder_rejected(chain,tmp_path,monkeypatch):
    folder,_,_=_extend(chain,tmp_path,monkeypatch)
    link=folder/"stage24-previous-batch-link.json"
    link.write_bytes(b"{}")
    with pytest.raises(r24.Stage24CustodyRefused,match="PREVIOUS_LINK"):
        _replay(chain,folder)
    with pytest.raises(r24.Stage24CustodyRefused):
        r24.stage24_replay_all_previous_batches(
            previous_directories=(folder,chain[1]),
            witness=g._read_original_evidence(chain[0]),operator_ack=True,
        )


def test_expired_window_writes_gap_ledger_without_request(chain,tmp_path,monkeypatch):
    monkeypatch.setattr(r24,"_now",lambda:START+timedelta(days=2))
    monkeypatch.setattr(r24,"_download_pinned_https",lambda path:pytest.fail("network"))
    output=tmp_path/"missed"
    with pytest.raises(r24.Stage24CustodyRefused,match="NO_BACKFILL"):
        r24.run_stage24_manual_next_batch(
            witness_directory=chain[0],previous_directories=(chain[1],),
            destination=output,number_of_closed_bars=4,operator_ack=True,
        )
    ledger=json.loads((output/"gap-ledger.json").read_bytes())
    assert ledger["binance_outage_proven"] is False
    assert ledger["automatic_retry_performed"] is False
    assert ledger["permit_future_chain_to_skip_missing_bars"] is False
    with pytest.raises(r24.Stage24CustodyRefused):
        _replay(chain,output)


def test_early_window_no_files_and_no_network(chain,tmp_path,monkeypatch):
    monkeypatch.setattr(r24,"_now",lambda:START+2*BAR)
    monkeypatch.setattr(r24,"_download_pinned_https",lambda path:pytest.fail("network"))
    out=tmp_path/"too-early"
    with pytest.raises(r24.Stage24CustodyRefused,match="NOT_YET_CLOSED"):
        r24.run_stage24_manual_next_batch(
            witness_directory=chain[0],previous_directories=(chain[1],),
            destination=out,number_of_closed_bars=4,operator_ack=True,
        )
    assert not out.exists()


def test_failed_https_attempt_no_retry_and_outage_unknown(chain,tmp_path,monkeypatch):
    monkeypatch.setattr(r24,"_now",lambda:START+5*BAR+timedelta(seconds=10))
    attempts=[]
    def refuse(path):
        attempts.append(True)
        raise OSError("synthetic local connectivity failure")
    monkeypatch.setattr(r24,"_download_pinned_https",refuse)
    out=tmp_path/"failure"
    with pytest.raises(OSError):
        r24.run_stage24_manual_next_batch(
            witness_directory=chain[0],previous_directories=(chain[1],),
            destination=out,number_of_closed_bars=4,operator_ack=True,
        )
    assert len(attempts)==1
    ledger=json.loads((out/"failure-ledger.json").read_bytes())
    assert ledger["exchange_outage_proven"] is False
    assert ledger["automatic_retry_performed"] is False


def test_bad_previous_original_fails_before_next_request(chain,tmp_path,monkeypatch):
    file=chain[1]/"original-venue-response.json"
    file.write_bytes(file.read_bytes()+b" ")
    monkeypatch.setattr(r24,"_now",lambda:START+5*BAR+timedelta(seconds=10))
    monkeypatch.setattr(r24,"_download_pinned_https",lambda path:pytest.fail("network"))
    out=tmp_path/"bad"
    with pytest.raises(ValueError):
        r24.run_stage24_manual_next_batch(
            witness_directory=chain[0],previous_directories=(chain[1],),
            destination=out,number_of_closed_bars=4,operator_ack=True,
        )
    assert not out.exists()


def test_disabled_production_no_ack_and_reused_output_refused(chain,tmp_path,monkeypatch):
    monkeypatch.delenv("MMT_R24_EXPLICIT_ONE_READONLY_GET")
    with pytest.raises(r24.Stage24CustodyRefused,match="EXPLICIT"):
        r24.run_stage24_manual_next_batch(
            witness_directory=chain[0],previous_directories=(chain[1],),
            destination=tmp_path/"x",number_of_closed_bars=4,operator_ack=True,
        )
    monkeypatch.setenv("MMT_R24_EXPLICIT_ONE_READONLY_GET","1")
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(ValueError,match="NONPRODUCTION"):
        r24.run_stage24_manual_next_batch(
            witness_directory=chain[0],previous_directories=(chain[1],),
            destination=tmp_path/"x",number_of_closed_bars=4,operator_ack=True,
        )


def test_cli_capture_requires_specific_one_get_approval(monkeypatch,tmp_path):
    monkeypatch.setenv("MMT_NONPRODUCTION","1")
    monkeypatch.delenv("MMT_PRODUCTION",raising=False)
    args=[
        "--ack-research-only","--witness-dir",str(tmp_path/"witness"),
        "--prior-batch-dir",str(tmp_path/"first"),
        "capture","--bars","4","--output-dir",str(tmp_path/"next"),
    ]
    calls=[]
    monkeypatch.setattr(cli,"run_stage24_manual_next_batch",
        lambda **kwargs:calls.append(kwargs) or {"connected_paper_started":False})
    with pytest.raises(SystemExit):
        cli.main(args)
    assert not calls
    cli.main(args+["--confirm-one-readonly-public-get",
                   "I_APPROVE_ONE_NEXT_READONLY_BINANCE_GET"])
    assert len(calls)==1
    assert calls[0]["number_of_closed_bars"]==4
