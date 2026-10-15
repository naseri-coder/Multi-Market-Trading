"""Offline Stage17 original-file custody without a live Internet connection.

Test ZIPs are fully SYNTHETIC; this cannot prove genuine market acquisition.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime

import pytest

from naseri_markets import stage17_official_archive_capture_v1 as stage17
from naseri_markets.binance_vision_archive_stage16_v1 import VisionArchiveRefused


@pytest.fixture(autouse=True)
def research(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def fixture_files(folder):
    first = datetime(2024, 1, 1, tzinfo=UTC)
    name = "BTCUSDT-15m-2024-01.zip"
    candles = []
    for n in range(31 * 24 * 4):
        opened = int(first.timestamp() * 1000) + 900000 * n
        candles.append(
            f"{opened},100,101,99,100,10,{opened + 899999},1000,10,4,400,0"
        )
    with io.BytesIO() as dst:
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(name[:-4] + ".csv", ("\n".join(candles) + "\n").encode())
        binary = dst.getvalue()
    check = (hashlib.sha256(binary).hexdigest() + "  " + name + "\n").encode()
    zip_path = folder / name
    check_path = folder / (name + ".CHECKSUM")
    zip_path.write_bytes(binary)
    check_path.write_bytes(check)
    return zip_path, check_path


def test_offline_original_month_end_to_end_stage12(monkeypatch, tmp_path):
    z, c = fixture_files(tmp_path)
    monkeypatch.setattr(stage17, "_get_exact",
                        lambda *_a, **_k: pytest.fail("network called in offline import"))
    capture = stage17.import_stage17_vision_month_offline(
        z, c, year=2024, month=1, operator_ack=True,
        expected_zip_sha256=hashlib.sha256(z.read_bytes()).hexdigest(),
        expected_checksum_sha256=hashlib.sha256(c.read_bytes()).hexdigest(),
    )
    assert capture.archive.count == 2976
    assert capture.operator_hashes_preapproved is True
    assert capture.source_independently_authenticated is False
    assert capture.retrieval_clock_independently_attested is False
    receipt = stage17.persist_research_capture(
        capture, destination=tmp_path / "isolated-research-receipt",
    )
    assert receipt["rows"] == 2976
    assert receipt["preapproved_hashes_matched"] is True
    assert receipt["source_independently_authenticated"] is False
    assert receipt["retrieval_clock_independently_attested"] is False


def test_absence_of_both_pins_is_explicitly_unverified(tmp_path):
    z, c = fixture_files(tmp_path)
    result = stage17.import_stage17_vision_month_offline(
        z, c, year=2024, month=1, operator_ack=True,
    )
    assert result.operator_hashes_preapproved is False
    assert result.source_independently_authenticated is False


def test_only_approved_exact_names_in_same_folder(tmp_path):
    z, c = fixture_files(tmp_path)
    bad = tmp_path / "other.CHECKSUM"
    bad.write_bytes(c.read_bytes())
    with pytest.raises(stage17.Stage17Refused, match="OFFLINE_INPUT"):
        stage17.import_stage17_vision_month_offline(
            z, bad, year=2024, month=1, operator_ack=True,
        )
    with pytest.raises(stage17.Stage17Refused, match="OFFLINE_INPUT"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=2, operator_ack=True,
        )


def test_original_data_swap_and_pin_refusal(tmp_path):
    z, c = fixture_files(tmp_path)
    with pytest.raises(stage17.Stage17Refused, match="PIN_MISMATCH"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=1, operator_ack=True,
            expected_zip_sha256="0" * 64,
            expected_checksum_sha256=hashlib.sha256(c.read_bytes()).hexdigest(),
        )
    c.write_bytes(b"0" * 64 + b"  BTCUSDT-15m-2024-01.zip\n")
    with pytest.raises(VisionArchiveRefused, match="CHECKSUM"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=1, operator_ack=True,
        )


def test_symlink_and_nonregular_file_refused(tmp_path):
    z, c = fixture_files(tmp_path)
    c.unlink()
    c.symlink_to(z)
    with pytest.raises(stage17.Stage17Refused, match="OFFLINE_FILE"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=1, operator_ack=True,
        )


def test_nonproduction_gate_precedes_file_read(tmp_path, monkeypatch):
    z, c = fixture_files(tmp_path)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(stage17.Stage17Refused, match="NONPRODUCTION"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=1, operator_ack=True,
        )
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    with pytest.raises(stage17.Stage17Refused, match="ACK"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=1, operator_ack=False,
        )


def test_size_restrictions_apply_before_decompression(tmp_path):
    z, c = fixture_files(tmp_path)
    c.write_bytes(b"x" * 257)
    with pytest.raises(stage17.Stage17Refused, match="SIZE"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=1, operator_ack=True,
        )


def test_refuse_partially_approved_hash_pair(tmp_path):
    z, c = fixture_files(tmp_path)
    with pytest.raises(stage17.Stage17Refused, match="BOTH_PREAPPROVED"):
        stage17.import_stage17_vision_month_offline(
            z, c, year=2024, month=1, operator_ack=True,
            expected_zip_sha256=hashlib.sha256(z.read_bytes()).hexdigest(),
        )
