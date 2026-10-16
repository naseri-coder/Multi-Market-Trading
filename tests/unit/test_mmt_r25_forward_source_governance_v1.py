"""R25 synthetic first-source policy/correction tests; no network or true price feed.

A fake TSA is injected ONLY in the tests. The production module invokes
real R23/OpenSSL verification and previous R24 full-source replay.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest

from naseri_markets import brooks_forward_source_custody_stage21g_v1 as g
from naseri_markets import brooks_forward_source_governance_mmt_r25_v1 as r25
from naseri_markets import brooks_future_kline_admission_stage21f_v1 as f
from scripts import mmt_r25_offline_forward_provenance_review_v1 as cli

START = datetime(2026, 10, 20, tzinfo=UTC)
BAR = timedelta(minutes=15)
PLAN = (
    Path(__file__).resolve().parents[2] / "docs/evidence"
    / "STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json"
)


def _bar(*, close="102", high="105", ts=None):
    if ts is None:
        ts = int(START.timestamp()*1000)
    return [
        ts, "100", high, "99", close, "10",
        ts + 899999, "1000", 7, "4", "400", "0",
    ]


def _encode(*bars, indent=None):
    return json.dumps(list(bars), indent=indent).encode("ascii")


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setenv("ST21G_EXPLICIT_MANUAL_CAPTURE", "1")
    witness_dir = tmp_path / "witness"
    witness_dir.mkdir()
    originals = {
        "exact-frozen-brooks-plan.json": PLAN.read_bytes(),
        "original-external-timestamp-response.tsr": b"SYNTHETIC-NOT-A-TSR",
        "tsa-root-public.pem": b"SYNTHETIC-NOT-A-ROOT",
        "tsa-signer-public.pem": b"SYNTHETIC-NOT-A-SIGNER",
    }
    monkeypatch.setattr(g, "_EXPECTED_EVIDENCE", {
        name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()
    })
    monkeypatch.setattr(
        f, "_CANONICAL_TOKEN_SHA",
        hashlib.sha256(originals["original-external-timestamp-response.tsr"]).hexdigest(),
    )
    monkeypatch.setattr(
        f, "_CANONICAL_CA_SHA",
        hashlib.sha256(originals["tsa-root-public.pem"]).hexdigest(),
    )
    monkeypatch.setattr(
        f, "_CANONICAL_SIGNER_SHA",
        hashlib.sha256(originals["tsa-signer-public.pem"]).hexdigest(),
    )
    monkeypatch.setattr(f, "verify_brooks_rfc3161_precommitment", lambda **_kw: {
        "cryptographic_tsa_signature_and_imprint_valid": True,
        "independent_tsa_provider_assessed": False,
        "paper_mode_authorized": False,
        "signed_timestamp_utc": "2026-10-16T01:36:00+00:00",
    })
    monkeypatch.setattr(
        r25, "stage23_offline_witness_preflight",
        lambda **_kw: {
            "actual_external_rfc3161_signature_verified": True,
            "canonical_frozen_plan_sha256": (
                "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
            ),
            "future_market_candles_received": False,
            "paper_mode_active": False,
        },
    )
    for name, raw in originals.items():
        (witness_dir/name).write_bytes(raw)
    body = _encode(_bar())
    complete = START + BAR + timedelta(seconds=10)
    obs = g.Stage21GTransportObservation(
        request_url="https://fapi.binance.com" + g._query(first_open=START, bars=1),
        original_body=body, status=200,
        date_header=format_datetime(complete, usegmt=True),
        content_type="application/json", content_encoding="identity",
        tls_peer_certificate_sha256="a"*64, tls_version="TLSv1.3",
        request_started_utc=complete-timedelta(seconds=1),
        response_complete_utc=complete, elapsed_seconds=1.0,
    )
    monkeypatch.setattr(g, "_now", lambda: complete)
    monkeypatch.setattr(g, "_download_pinned_https", lambda _path: obs)
    first = tmp_path / "initial"
    g.run_stage21g_manual_first_window(
        witness_directory=witness_dir,
        destination=first,
        number_of_closed_bars=1,
        operator_ack=True,
    )
    assert (first/"original-venue-response.json").read_bytes() == body
    return witness_dir, first


def _compare(source, tmp_path, raw, *, folder="revision", at=None):
    later = tmp_path/"operator-supplied-later.json"
    later.write_bytes(raw)
    return r25.r25_record_untrusted_revision_observation(
        witness_directory=source[0],
        previous_directories=(source[1],),
        target_batch_index=0,
        later_original_body_path=later,
        destination=tmp_path/folder,
        operator_observed_at_utc=at or START+timedelta(days=1),
        operator_ack=True,
    )


def test_exact_14_manual_daily_windows_cover_original_signed_plan(source):
    report = r25.r25_fixed_manual_96bar_schedule(
        witness_directory=source[0],
        as_of_utc=datetime(2026, 10, 16, tzinfo=UTC),
        operator_ack=True,
    )
    rows = report["sessions"]
    assert len(rows) == 14
    assert report["closed_bar_count"] == 1344
    assert rows[0]["first_open_utc"] == "2026-10-20T00:00:00+00:00"
    assert rows[0]["earliest_start_utc"] == "2026-10-21T00:00:05+00:00"
    assert rows[0]["latest_completed_response_utc"] == (
        "2026-10-21T01:00:00+00:00"
    )
    assert rows[-1]["last_close_utc"] == "2026-11-03T00:00:00+00:00"
    assert all(row["exact_bars"] == 96 for row in rows)
    assert all(row["automatically_scheduled"] is False for row in rows)
    assert report["schedule_is_recommendation_not_signed_experiment_change"] is True
    assert report["assurance_flags"]["original_market_response_venue_signed"] is False
    assert report["assurance_flags"]["independent_receive_clock_attested"] is False
    assert report["assurance_flags"]["paper_mode_authorized"] is False
    assert report["no_network_requests"] is True


def test_manual_window_clock_states_do_not_create_jobs(source):
    before = r25.r25_fixed_manual_96bar_schedule(
        witness_directory=source[0],
        as_of_utc=START,
        operator_ack=True,
    )
    open_at = r25.r25_fixed_manual_96bar_schedule(
        witness_directory=source[0],
        as_of_utc=START+timedelta(days=1, seconds=5),
        operator_ack=True,
    )
    missed = r25.r25_fixed_manual_96bar_schedule(
        witness_directory=source[0],
        as_of_utc=START+timedelta(days=2),
        operator_ack=True,
    )
    assert before["sessions"][0]["clock_derived_window_status"] == (
        "AWAITING_LAST_CLOSED_CANDLE"
    )
    assert open_at["sessions"][0]["clock_derived_window_status"] == (
        "MANUAL_ONE_SHOT_WINDOW_ELIGIBLE_NOT_AUTHORIZED"
    )
    assert missed["sessions"][0]["clock_derived_window_status"] == (
        "OPERATOR_CAPTURE_WINDOW_EXPIRED_NOT_BACKFILLABLE"
    )


def test_without_market_capture_policy_never_certifies_source(source):
    report = r25.r25_offline_chain_governance(
        witness_directory=source[0],
        previous_directories=(),
        as_of_utc=datetime(2026,10,16,tzinfo=UTC),
        operator_ack=True,
    )
    assert report["replayed_and_checked_previous_batches"] == 0
    assert report["original_source_check_status"] == (
        "SIGNED_PLAN_ONLY_NO_PRIOR_SOURCE_EVIDENCE"
    )
    assert report["independent_source_provenance"] == "UNVERIFIED"
    assert report["authorize_continued_prospective_qualification"] is False
    assert report["historical_backfill_qualifies_as_forward"] is False


def test_replayed_one_batch_does_not_mislabel_authenticated_market(source):
    report = r25.r25_offline_chain_governance(
        witness_directory=source[0],
        previous_directories=(source[1],),
        as_of_utc=START+timedelta(days=1),
        operator_ack=True,
    )
    assert report["replayed_and_checked_previous_batches"] == 1
    assert report["next_unaccepted_first_open_utc"] == (
        "2026-10-20T00:15:00+00:00"
    )
    assert report["local_clock_indicates_possible_capture_lateness"] is True
    assert report["independent_source_provenance"] == "UNVERIFIED"
    assert report["receiver_timestamp_external_witness"] == "UNVERIFIED"
    assert report["connected_paper_enabled"] is False


def test_identical_later_bytes_recorded_as_untrusted_no_replacement(source,tmp_path):
    original=(source[1]/"original-venue-response.json").read_bytes()
    before=original
    report=_compare(source,tmp_path,original)
    out=tmp_path/"revision"
    assert report["difference_classification"] == "EXACT_RAW_BYTES_UNCHANGED"
    assert report["requires_human_source_and_methodology_review"] is False
    assert report["provider_declared_correction_independently_verified"] is False
    assert report["accepted_original_batch_was_replaced"] is False
    assert (out/"later-operator-supplied-source.json").read_bytes() == original
    assert (source[1]/"original-venue-response.json").read_bytes() == before
    with pytest.raises(r25.Stage25PolicyRefused, match="FRESH_PRIVATE"):
        _compare(source,tmp_path,original)


def test_changed_json_representation_does_not_mean_new_canonical_candle(source,tmp_path):
    report=_compare(source,tmp_path,_encode(_bar(),indent=2))
    assert report["difference_classification"] == (
        "ORIGINAL_BYTES_CHANGED_CANONICAL_CANDLES_UNCHANGED"
    )
    assert report["requires_human_source_and_methodology_review"] is True
    assert report["automatic_correction_application"] is False
    assert report["later_candidate_independently_from_binance_authenticated"] is False


def test_price_revision_is_only_operator_claim_and_stays_separate(source,tmp_path):
    report=_compare(source,tmp_path,_encode(_bar(close="103",high="106")))
    assert report["difference_classification"] == (
        "CANONICAL_SOURCE_CANDLES_CHANGED_REVIEW_REQUIRED"
    )
    assert report["original_canonical_csv_sha256"] != (
        report["later_canonical_csv_sha256"]
    )
    assert report["provider_declared_correction_independently_verified"] is False
    assert report["forward_oos_qualification_granted"] is False
    assert report["disposition"] == "REVIEW_ONLY_ORIGINAL_CHAIN_IMMUTABLE"
    assert json.loads(
        (tmp_path/"revision"/"R25-untrusted-revision-review.json").read_bytes()
    ) == report


@pytest.mark.parametrize("later", [
    b"[]", b"not a market source", _encode(_bar(ts=0)),
    _encode(_bar(close="-1")), b"null",
])
def test_invalid_candidate_is_preserved_and_never_qualified(source,tmp_path,later):
    report=_compare(source,tmp_path,later)
    assert report["difference_classification"] == (
        "UNREADABLE_OR_WRONG_WINDOW_NOT_A_VALID_SOURCE_REVISION"
    )
    assert report["later_source_shape_status"] == "SOURCE_CANDIDATE_SCHEMA_REJECTED"
    assert report["requires_human_source_and_methodology_review"] is True
    assert (tmp_path/"revision"/"later-operator-supplied-source.json").read_bytes() == later
    assert report["accepted_original_batch_was_replaced"] is False


def test_previous_batch_raw_tamper_refuses_before_writing_revision(source,tmp_path):
    path=source[1]/"original-venue-response.json"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError):
        _compare(source,tmp_path,_encode(_bar(close="103")))
    assert not (tmp_path/"revision").exists()


def test_later_evidence_symlink_and_absent_file_rejected(source,tmp_path):
    original=(source[1]/"original-venue-response.json").read_bytes()
    path=tmp_path/"outside.json"
    path.write_bytes(original)
    link=tmp_path/"linked.json"
    link.symlink_to(path)
    for candidate in (link,tmp_path/"absent.json"):
        with pytest.raises(r25.Stage25PolicyRefused,match="ABSOLUTE_ORIGINAL"):
            r25.r25_record_untrusted_revision_observation(
                witness_directory=source[0],previous_directories=(source[1],),
                target_batch_index=0,later_original_body_path=candidate,
                destination=tmp_path/"new-folder",
                operator_observed_at_utc=START+timedelta(days=1),
                operator_ack=True,
            )
    assert not (tmp_path/"new-folder").exists()


def test_bad_target_clock_and_production_not_permitted(source,tmp_path,monkeypatch):
    path=tmp_path/"later.json"
    path.write_bytes(_encode(_bar()))
    kwargs={
        "witness_directory":source[0],
        "previous_directories":(source[1],),
        "target_batch_index":0,
        "later_original_body_path":path,
        "destination":tmp_path/"out",
        "operator_observed_at_utc":START-timedelta(minutes=1),
        "operator_ack":True,
    }
    with pytest.raises(r25.Stage25PolicyRefused,match="BEFORE_BAR_CLOSE"):
        r25.r25_record_untrusted_revision_observation(**kwargs)
    kwargs["operator_observed_at_utc"]=datetime(2026,10,20)
    with pytest.raises(r25.Stage25PolicyRefused,match="UTC_AWARE"):
        r25.r25_record_untrusted_revision_observation(**kwargs)
    monkeypatch.setenv("MMT_PRODUCTION","1")
    kwargs["operator_observed_at_utc"]=START+timedelta(days=1)
    with pytest.raises(ValueError,match="NONPRODUCTION"):
        r25.r25_record_untrusted_revision_observation(**kwargs)
    assert not (tmp_path/"out").exists()


def test_operator_cli_has_only_offline_commands_and_refuses_absent_ack(
    source,monkeypatch,capsys,
):
    monkeypatch.setenv("MMT_NONPRODUCTION","1")
    monkeypatch.delenv("MMT_PRODUCTION",raising=False)
    args=["--witness-dir",str(source[0]),"schedule"]
    with pytest.raises(SystemExit):
        cli.main(args)
    monkeypatch.setattr(cli,"r25_fixed_manual_96bar_schedule",lambda **kw:{
        "no_network_requests":True,"paper_mode_authorized":False,
    })
    cli.main(["--ack-research-only",*args])
    assert '"no_network_requests": true' in capsys.readouterr().out
    parser=cli.create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--ack-research-only","--witness-dir",str(source[0]),
                           "start-live-broker"])


def test_permanent_source_witness_sha_pin_remains_canonical():
    data=PLAN.read_bytes()
    assert hashlib.sha256(data).hexdigest() == (
        "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
    )
