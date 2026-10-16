"""MMT R23 portable witness recovery and human-only future capture tests.

Synthetic ZIPs exercise packaging & gate behavior; only the optional reviewed
CI external-artifact job uses the genuine original public RFC3161 response.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from naseri_markets import brooks_termux_readiness_mmt_r23_v1 as r23
from scripts import mmt_r23_termux_brooks_manual_forward_v1 as cli


@pytest.fixture(autouse=True)
def _research_only(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _synthetic_originals():
    root = Path(__file__).resolve().parents[2]
    plan = (root / "docs/evidence/"
            "STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json")
    assert hashlib.sha256(plan.read_bytes()).hexdigest() == (
        "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
    )
    return {
        "exact-frozen-brooks-plan.json": plan.read_bytes(),
        "original-external-timestamp-response.tsr": b"SYNTHETIC-NOT-A-SIGNED-TOKEN",
        "tsa-root-public.pem": b"SYNTHETIC-ROOT-NOT-A-REAL-CERTIFICATE",
        "tsa-signer-public.pem": b"SYNTHETIC-SIGNER-NOT-A-REAL-CERTIFICATE",
        "external-rfc3161-verification-receipt.json": b"test receipt",
        "locked-unverified-economic-assumptions.json": b"test fixed research economics",
        "operator-admission-audit.json": b"test source audit",
        "plan-rfc3161-request.tsq": b"test request",
    }


def _make_zip(originals):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in originals.items():
            archive.writestr(name, raw)
    return output.getvalue()


@pytest.fixture
def fake_bundle(tmp_path, monkeypatch):
    originals = _synthetic_originals()
    raw = _make_zip(originals)
    path = tmp_path / "synthetic-witness-TEST-ONLY.zip"
    path.write_bytes(raw)
    monkeypatch.setattr(r23, "_ORIGINAL_ZIP_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(r23, "_ALL_PINS", {
        k: hashlib.sha256(v).hexdigest() for k, v in originals.items()
    })
    monkeypatch.setattr(r23, "_EXPECTED_NAMES", frozenset(originals))
    monkeypatch.setattr(r23, "_EXPECTED_EVIDENCE", {
        k: hashlib.sha256(originals[k]).hexdigest()
        for k in r23._REQUIRED_FILES
    })
    signed = {
        "signed_timestamp_utc": "2026-10-16T01:36:00+00:00",
        "cryptographic_tsa_signature_and_imprint_valid": True,
        "independent_tsa_provider_assessed": False,
        "paper_mode_authorized": False,
    }
    # Crypto verifier is mocked HERE ONLY, never in the reviewed production
    # module. The genuine OpenSSL-verified source has separate external tests.
    monkeypatch.setattr(r23, "verify_brooks_rfc3161_precommitment", lambda **_kw: signed)
    monkeypatch.setattr(r23, "_read_original_evidence", lambda folder: {
        k: (folder / k).read_bytes() for k in r23._REQUIRED_FILES
    })
    return path, originals


def test_synthetic_exact_zip_is_rejected_with_real_pins(tmp_path):
    source = tmp_path / "untrusted.zip"
    source.write_bytes(_make_zip(_synthetic_originals()))
    with pytest.raises(r23.R23ReadinessRefused, match="ZIP_SHA_MISMATCH"):
        r23.verify_exact_original_rfc3161_zip(source)


def test_exact_expected_synthetic_member_set_pins_and_prepare(fake_bundle, tmp_path):
    path, originals = fake_bundle
    assert r23.verify_exact_original_rfc3161_zip(path) == originals
    dest = tmp_path / "witness"
    receipt = r23.stage23_prepare_witness_from_original_zip(
        original_zip=path, destination=dest, operator_ack=True,
    )
    assert receipt["source_original_zip_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["independent_tsa_accreditation_approved"] is False
    assert receipt["binance_data_source_independently_signed"] is False
    assert receipt["connected_paper_active"] is False
    assert all((dest/k).read_bytes() == originals[k] for k in r23._REQUIRED_FILES)
    assert stat.S_IMODE((dest/"exact-frozen-brooks-plan.json").stat().st_mode) == 0o600
    manifest = json.loads((dest / "R23-original-artifact-manifest.json").read_bytes())
    assert manifest["source_original_zip_sha256"] == receipt["source_original_zip_sha256"]
    assert manifest["production_modified"] is False
    with pytest.raises(r23.R23ReadinessRefused, match="FRESH_PRIVATE"):
        r23.stage23_prepare_witness_from_original_zip(
            original_zip=path, destination=dest, operator_ack=True,
        )


def test_corrupted_untrusted_bundle_is_refused_before_creating_output(fake_bundle, tmp_path):
    original_zip, _ = fake_bundle
    content = bytearray(original_zip.read_bytes())
    content[-10] ^= 7
    original_zip.write_bytes(bytes(content))
    destination = tmp_path / "must-not-be-created"
    with pytest.raises(r23.R23ReadinessRefused, match="ZIP_SHA_MISMATCH"):
        r23.stage23_prepare_witness_from_original_zip(
            original_zip=original_zip, destination=destination, operator_ack=True,
        )
    assert not destination.exists()


@pytest.mark.parametrize("attack", ("unexpected","missing","oversized","linked"))
def test_bomb_missing_extra_symlink_entry_never_unpacked(fake_bundle, tmp_path, monkeypatch, attack):
    path, originals = fake_bundle
    broken = dict(originals)
    if attack == "unexpected":
        broken["../escape.txt"] = b"UNTRUSTED"
    elif attack == "missing":
        del broken["tsa-signer-public.pem"]
    elif attack == "oversized":
        broken["tsa-signer-public.pem"] = b"x" * 17000
    else:
        assert attack == "linked"
    raw = _make_zip(broken)
    if attack == "linked":
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            for name, data in broken.items():
                info = zipfile.ZipInfo(name)
                if name == "tsa-root-public.pem":
                    info.create_system = 3
                    info.external_attr = ((stat.S_IFLNK | 0o777) << 16)
                archive.writestr(info, data)
        raw = content.getvalue()
    path.write_bytes(raw)
    monkeypatch.setattr(r23, "_ORIGINAL_ZIP_SHA256", hashlib.sha256(raw).hexdigest())
    # For a source-size attack, even a matching explicit digest cannot bypass
    # the independent max-size safety bound.
    monkeypatch.setattr(r23, "_ALL_PINS", {
        k: hashlib.sha256(v).hexdigest() for k, v in broken.items()
    })
    destination = tmp_path / "never-unpacked"
    with pytest.raises(r23.R23ReadinessRefused):
        r23.stage23_prepare_witness_from_original_zip(
            original_zip=path, destination=destination, operator_ack=True,
        )
    assert not destination.exists()
    assert not (tmp_path/"escape.txt").exists()


def test_real_original_plan_dates_and_no_paper_in_status(fake_bundle, tmp_path):
    path, _ = fake_bundle
    dest = tmp_path/"evidence"
    r23.stage23_prepare_witness_from_original_zip(
        original_zip=path, destination=dest, operator_ack=True,
    )
    cases = [
        (datetime(2026,10,16,tzinfo=UTC),"AWAITING_FIRST_CLOSED_CANDLE"),
        (datetime(2026,10,20,0,15,5,tzinfo=UTC),
         "FIRST_SINGLE_BAR_CAPTURE_TIME_OPEN_MANUAL_ONLY"),
        (datetime(2026,10,20,1,15,0,tzinfo=UTC),
         "FIRST_SINGLE_BAR_CAPTURE_TIME_OPEN_MANUAL_ONLY"),
        (datetime(2026,10,20,1,15,1,tzinfo=UTC),
         "FIRST_SINGLE_BAR_WINDOW_MISSED_DO_NOT_BACKDATE"),
    ]
    for at, status in cases:
        report = r23.stage23_offline_witness_preflight(
            evidence_directory=dest, at_utc=at, operator_ack=True,
        )
        assert report["first_single_bar_window_status"] == status
        assert report["future_market_candles_received"] is False
        assert report["paper_mode_active"] is False
        assert report["actual_external_rfc3161_signature_verified"] is True
        assert report["source_original_verified"] is False
        assert report["independent_receiver_clock_verified"] is False
    with pytest.raises(r23.R23ReadinessRefused, match="UTC_AWARE"):
        r23.stage23_offline_witness_preflight(
            evidence_directory=dest,
            at_utc=datetime(2026,10,20,0,16),operator_ack=True,
        )


def test_production_and_no_ack_cannot_prepare_witness(fake_bundle,tmp_path,monkeypatch):
    source, _ = fake_bundle
    dest = tmp_path/"no-output"
    with pytest.raises(ValueError, match="NONPRODUCTION"):
        r23.stage23_prepare_witness_from_original_zip(
            original_zip=source,destination=dest,operator_ack=False,
        )
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(ValueError,match="NONPRODUCTION"):
        r23.stage23_prepare_witness_from_original_zip(
            original_zip=source,destination=dest,operator_ack=True,
        )
    assert not dest.exists()


def test_manual_cli_requires_consent_and_does_not_call_network(monkeypatch,tmp_path):
    evidence=tmp_path/"evidence"
    destination=tmp_path/"market-attempt"
    monkeypatch.setattr(cli,"stage23_offline_witness_preflight",lambda **_kw: {
        "canonical_frozen_plan_sha256":"c"*64,
    })
    calls=[]
    def no_network(**_kw):
        calls.append(_kw)
        return {
            "original_body_sha256":"a"*64,
            "receipt_sha256":"b"*64,
        }
    monkeypatch.setattr(cli,"run_stage21g_manual_first_window",no_network)
    args=[
        "--ack-research-only","capture","--evidence-dir",str(evidence),
        "--output-dir",str(destination),"--bars","1",
    ]
    with pytest.raises(SystemExit):
        cli.main(args)
    assert not calls
    cli.main(args+["--confirm-one-readonly-public-get",
                   "I_APPROVE_ONE_READONLY_PUBLIC_BINANCE_GET"])
    assert len(calls)==1
    assert calls[0]["number_of_closed_bars"]==1
    assert os.environ["ST21G_EXPLICIT_MANUAL_CAPTURE"]=="1"


def test_capture_fails_on_original_study_clock_outside_window(monkeypatch,tmp_path):
    # Status does not issue network; existing Stage21G enforces clock again
    # under its independent guard, even when invoked through this CLI.
    original = tmp_path/"absent.zip"
    with pytest.raises(r23.R23ReadinessRefused):
        r23.verify_exact_original_rfc3161_zip(original)
    parser=cli.make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--ack-research-only", "capture", "--evidence-dir", str(tmp_path),
            "--output-dir", str(tmp_path/"out"),"--bars","2",
            "--confirm-one-readonly-public-get",
            "I_APPROVE_ONE_READONLY_PUBLIC_BINANCE_GET",
        ])
